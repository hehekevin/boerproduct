#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（merge-skill）。

同一输入跑两遍：正常模式（归一+模糊去重+冲突检测全部开启）与退化/基线模式
（--ablate all：关闭字段归一、标题模糊匹配、冲突检测），逐项对照五类可观测指标：

  1. machine_adjudicated_ratio  可复算数值位被机器逐位判定的占比
  2. dup_missed                 去重漏检数（客观跨库重复未被该模式校验层捕获）
  3. conflict_missed            冲突漏检数（客观字段冲突未被登记且未被捕获）
  4. manual_review_items        需人工核对条目数
  5. steps_count / clarification_rounds  步骤数与追问轮次（每轮 3 条折算）

另采集 efficiency 效率计数，并支持 --inject-pollution 在副本上注入污染做反例
自测（校验器须抓到，且退出码恒 0）。退化模式仅用于增益对照，不得用于交付自检。
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution]
退出码：恒为 0。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze, numeric_fields  # noqa: E402
    from dedup_core import engine_partition, clamp_policy  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check/dedup_core: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[gain_probe] 写盘失败 %s: %s" % (path, e))
        return False


def check_index(report):
    return {s.get("item"): s for s in (report.get("self_check") or [])
            if isinstance(s, dict) and s.get("item")}


def objective_truth(res):
    """独立复算客观真值（恒用正常模式引擎，与被测模式无关）：
    客观跨库重复对 / 客观字段冲突 / 误并。"""
    inner = (res or {}).get("result") or {}
    hits = inner.get("raw_hits") or []
    policy = clamp_policy(inner.get("dedup_policy") or {})
    eng = engine_partition(hits, policy, ablate="none")
    hit2rec = {}
    for m in (inner.get("merged_records") or []):
        for s in (m.get("sources") or []):
            hit2rec[s.get("hit_id")] = m.get("record_id")
    dup_missed_pairs, over_merged = [], []
    for g in eng["groups"]:
        recs = {hit2rec.get(h) for h in g}
        if len(recs) > 1:
            dup_missed_pairs.append(sorted(g))  # 同组但被拆进多条记录：漏并
    for m in (inner.get("merged_records") or []):
        if m.get("arbitration") == "manual":
            continue
        sset = {s.get("hit_id") for s in (m.get("sources") or [])}
        spans = [g for g in eng["groups"] if sset & set(g)]
        if len(spans) > 1:
            over_merged.append(m.get("record_id"))  # 一条记录横跨多个引擎组：误并
    reg = {(str(c.get("record_id")), str(c.get("field")))
           for c in (inner.get("conflicts") or []) if isinstance(c, dict)}
    obj_conflicts = [c for c in eng["conflicts"] if (c["record_id"], c["field"]) not in reg]
    return {"dup_missed_pairs": dup_missed_pairs, "over_merged": over_merged,
            "objective_conflicts": obj_conflicts, "engine_groups": len(eng["groups"])}


def mode_metrics(res, report, label, truth):
    idx = check_index(report)
    fields = numeric_fields(res)
    total_numeric = len(fields)
    inner = (res or {}).get("result") or {}
    counts = report.get("counts") or {}

    # 1. 机器逐位判定占比
    covered, uncovered_paths = 0, []
    for f in fields:
        e = idx.get(f.get("check"))
        if e is not None and e.get("applied"):
            covered += 1
        else:
            uncovered_paths.append(f.get("path"))
    ratio = (covered / total_numeric) if total_numeric else None

    # 引擎-交付划分一致性（本模式实跑结果）
    p_total = counts.get("partition_total") or 0
    p_agree = counts.get("partition_agree") or 0
    false_alarm = (p_total - p_agree) if p_total else 0
    agreement = (p_agree / p_total) if p_total else None

    # 2. 去重漏检：客观跨库重复未被该模式捕获的条数（划分复算跳过时全部漏掉）
    pm = (idx.get("engine.partition_match") or {})
    dup_missed = ((len(truth["dup_missed_pairs"]) + len(truth["over_merged"]))
                  if not pm.get("applied") else 0)

    # 3. 冲突漏检：客观未登记冲突未被该模式捕获的条数
    cr = (idx.get("conflicts.registered") or {})
    conflict_missed = len(truth["objective_conflicts"]) if not cr.get("applied") else 0

    # 4. 需人工核对：未判定数值位 + 误报划分 + 漏检 + 来源链断裂 + 失败库 + 回证失败
    hits = inner.get("raw_hits") or []
    trace_break = sum(1 for i, h in enumerate(hits)
                      if not (str(h.get("db_id") or "") and str(h.get("query_id") or "")
                              and str(h.get("raw_ref") or "")))
    failed_dbs = sum(1 for q in (inner.get("databases") or [])
                     if isinstance(q, dict)
                     and any(isinstance(x, dict) and x.get("status") == "failed"
                             and not str(x.get("failure_reason") or "").strip()
                             for x in (q.get("queries") or [])))
    unbacked = len(report.get("unbacked_numbers") or [])
    manual_items = (len(uncovered_paths) + false_alarm + dup_missed + conflict_missed
                    + trace_break + failed_dbs + unbacked)

    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_done = sum(1 for s in (inner.get("steps") or [])
                     if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0
    return {
        "mode": label, "ablate": report.get("ablate"), "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "unbacked_numbers": unbacked,
        "metrics": {
            "machine_adjudicated_ratio": ratio,
            "machine_adjudicated_ratio_pct": (round(ratio * 100, 2) if ratio is not None else None),
            "numeric_fields_total": total_numeric,
            "numeric_fields_machine_adjudicated": covered,
            "numeric_fields_not_adjudicated": len(uncovered_paths),
            "engine_agreement_ratio": agreement,
            "partition_total": p_total,
            "partition_agree": p_agree,
            "partition_false_alarm": false_alarm,
            "objective_dedup_errors": len(truth["dup_missed_pairs"]) + len(truth["over_merged"]),
            "dup_missed": dup_missed,
            "objective_conflicts_unregistered": len(truth["objective_conflicts"]),
            "conflict_missed": conflict_missed,
            "trace_broken_hits": trace_break,
            "failed_dbs_without_reason": failed_dbs,
            "manual_review_items": manual_items,
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入 6 类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    mrecs = inner.get("merged_records") or []
    for i, m in enumerate(mrecs):
        srcs = m.get("sources") or []
        if isinstance(m, dict) and len(srcs) >= 2 and m.get("arbitration") != "manual":
            half = srcs[:1]
            rest = srcs[1:]
            m["sources"] = half
            clone = copy.deepcopy(m)
            clone["record_id"] = (m.get("record_id") or "R") + "-P"
            clone["sources"] = rest
            mrecs.insert(i + 1, clone)
            plan.append("merged_records[%d] 被静默拆成两条（跨库重复未合并）" % i)
            break
    conflicts = inner.get("conflicts") or []
    if conflicts:
        removed = conflicts.pop(0)
        plan.append("删除一条字段冲突登记（%s.%s）：冲突被静默吞掉"
                    % (removed.get("record_id"), removed.get("field")))
    else:
        plan.append("（无 conflicts 可删，跳过冲突污染）")
    for h in (inner.get("raw_hits") or []):
        if isinstance(h, dict):
            h["raw_ref"] = None
            plan.append("raw_hits 某行 raw_ref 清空（来源链断裂）")
            break
    dm = inner.get("dedup_metrics") or {}
    if "duplicates_merged" in dm:
        dm["duplicates_merged"] = int(dm["duplicates_merged"]) + 5
        plan.append("dedup_metrics.duplicates_merged +5（与引擎复算不一致）")
    p["claims"] = []
    plan.append("清空 claims（数值回证缺失）")
    for d in (inner.get("databases") or []):
        if not isinstance(d, dict):
            continue
        hit = False
        for q in (d.get("queries") or []):
            if isinstance(q, dict) and q.get("status") == "failed":
                q["failure_reason"] = ""
                plan.append("库 %s 的 failed 查询清空 failure_reason（静默失败）" % d.get("db_id"))
                hit = True
                break
        if hit:
            break
    return p, plan


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence/efficiency 写入 result.json")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败（已降级）: %s" % e)
        return 0

    t0 = time.time()
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    truth = objective_truth(res)

    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal", truth)
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded", truth)
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta = {}
    for k in ("machine_adjudicated_ratio", "engine_agreement_ratio", "dup_missed",
              "conflict_missed", "manual_review_items", "steps_count", "clarification_rounds"):
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "machine_adjudicated_ratio",
         "mechanism": "数值回证（计数/相似度 claim text 回证 + 年份 quote 回证）",
         "formula": "被 applied=true 判定的数值位 / 全部数值位",
         "higher_is_better": True,
         "degrade_effect": "ablate=all 关闭回证后，数值位不再被机器逐位判定"},
        {"metric": "engine_agreement_ratio",
         "mechanism": "字段归一 + DOI/标题模糊去重引擎复算（划分逐组比对）",
         "formula": "引擎划分与交付合并记录一致的组数 / 全部组数",
         "higher_is_better": True,
         "degrade_effect": "关闭归一/模糊匹配后引擎退化，正确的跨库合并被误判为不一致"
                           "（partition_false_alarm 上升），每条不一致都需人工复核"},
        {"metric": "dup_missed",
         "mechanism": "partition_match：合并记录划分须与引擎复算逐组一致",
         "formula": "客观跨库重复（漏并+误并）未被该模式捕获的条数",
         "higher_is_better": False,
         "degrade_effect": "关闭划分复算后，静默拆分的跨库重复不再被判 FAIL，漏检上升"},
        {"metric": "conflict_missed",
         "mechanism": "conflicts.registered：引擎检出字段冲突须全部登记",
         "formula": "客观未登记冲突未被该模式捕获的条数",
         "higher_is_better": False,
         "degrade_effect": "关闭冲突检测后，字段冲突被静默吞掉，漏检上升"},
        {"metric": "manual_review_items",
         "mechanism": "来源链校验 + 失败降级登记 + 数值回证 + 漏检捕获",
         "formula": "未判定数值位 + 漏检 + 来源链断裂 + 失败库 + 回证失败",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count",
         "mechanism": "五步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数",
         "higher_is_better": None,
         "degrade_effect": "关闭检查项减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds",
         "mechanism": "把人工核对条目按每轮 %d 条打包（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "客观真值由探针用正常模式引擎独立复算（漏并对/误并/未登记冲突），与被测模式无关；"
        "两条路径共用 dedup_core 同一实现。",
        "退化模式同时关闭字段归一、标题模糊匹配与冲突检测；枚举、来源链、失败降级、"
        "运行状态等结构检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "machine_adjudicated_ratio 的分母只统计 dedup_metrics 计数 / dedup_decisions 相似度 / "
        "merged_records 年份中的数值位。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数；原始计数 "
        "manual_review_items 一并落盘，可换批量重算。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
    ]
    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约校验跳过。",
        "退化模式报告只可用于增益对照；把 --ablate 的结果当作交付自检结论即为误用。",
        "污染反例自测只在副本上注入，原 result.json 不被修改。",
    ]

    gain_evidence = {
        "probe_version": "1.0",
        "probe_tool": "scripts/gain_probe.py",
        "case_id": res.get("case_id"),
        "input": {"result_path": os.path.abspath(args.result),
                  "case_path": os.path.abspath(args.case),
                  "case_contract_state": case_state,
                  "same_input_for_both_runs": True,
                  "run_order": ["normal", "degraded"],
                  "ablate_options": "normalize（关归一）/fuzzy（关模糊匹配）/conflict（关冲突检测）/all",
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入，不做原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标方向为 higher_is_better 时表示机制带来增益；"
                               "指标方向为 lower_is_better 时读 delta 的相反符号；"
                               "delta=0 表示该指标在本输入上无区分度。",
    }

    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_truth = objective_truth(polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal", p_truth)
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded", p_truth)
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "dup_missed": pm_n["metrics"]["dup_missed"],
                            "conflict_missed": pm_n["metrics"]["conflict_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "dup_missed": pm_d["metrics"]["dup_missed"],
                              "conflict_missed": pm_d["metrics"]["conflict_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
                "dup_missed": pm_d["metrics"]["dup_missed"] - pm_n["metrics"]["dup_missed"],
                "conflict_missed": pm_d["metrics"]["conflict_missed"] - pm_n["metrics"]["conflict_missed"],
            },
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。",
        }

    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "numeric_fields_total": m_normal["metrics"]["numeric_fields_total"],
        "objective_dedup_errors": m_normal["metrics"]["objective_dedup_errors"],
        "objective_conflicts_unregistered": m_normal["metrics"]["objective_conflicts_unregistered"],
        "manual_review_items_normal": m_normal["metrics"]["manual_review_items"],
        "manual_review_items_degraded": m_degraded["metrics"]["manual_review_items"],
        "clarification_rounds_normal": m_normal["metrics"]["clarification_rounds"],
        "clarification_rounds_degraded": m_degraded["metrics"]["clarification_rounds"],
        "model_requests": None,
        "model_requests_note": "模型请求数由 Agent 侧记录（不可由本脚本采集），"
                               "交付前按实际请求次数回填；缺失时保持 null，不得臆造。",
        "reproduce": "python3 /skills/weekly-skill/scripts/gain_probe.py "
                     "--result /app/output/result.json --case /input/case.json "
                     "--work-dir /app/work --emit-into --inject-pollution",
    }

    out_path = args.out or os.path.join(args.work_dir or ".", "gain_evidence.json")
    save_json(out_path, {"gain_evidence": gain_evidence, "efficiency": efficiency})
    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["gain_evidence"] = gain_evidence
                cur["result"]["efficiency"] = efficiency
                save_json(args.result, cur)
        except Exception as e:
            print("[gain_probe] 回写 result.json 失败: %s" % e)

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式 verdict=%s"
          % (m_normal["verdict"], m_degraded["verdict"]))
    for name in ("machine_adjudicated_ratio_pct", "engine_agreement_ratio", "dup_missed",
                 "conflict_missed", "manual_review_items", "steps_count", "clarification_rounds"):
        a, b = m_normal["metrics"].get(name), m_degraded["metrics"].get(name)
        dkey = "machine_adjudicated_ratio" if name == "machine_adjudicated_ratio_pct" else name
        print("  %-28s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(dkey)))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
