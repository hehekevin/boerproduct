#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（cite-trace）。

同一输入跑两遍：正常模式（全部机械校验开启）与退化/基线模式（--ablate 关闭
方向覆盖/关联理由/去重三类校验），逐项对照五类可观测指标：

  1. backed_edge_ratio        来源可回指边占比（被机器逐条判定的边 / 全部边）
  2. violations_missed        客观违规漏检数（客观违规但校验层未捕获的条数）
  3. manual_review_items      需人工复核条目数（待复核 + 未判定边 + 漏检）
  4. steps_count              步骤数（校验层已执行检查项 + 流程已执行步骤）
  5. clarification_rounds     追问轮次（人工条目按每轮 3 条打包折算，公式随记录落盘）

另采集 efficiency 效率计数（自动可测：墙钟、字节数、检查项数、禁用项数），
并支持 --inject-pollution 生成污染副本做反例自测（校验器须抓到，且退出码恒 0）。

**本脚本只产出对照证据，不修改业务结论；退化模式仅用于增益对照，不得用于交付自检。**
键所有权：本脚本只写 result.gain_evidence / result.efficiency 两个键；
self_check / unbacked_numbers / gates / validator_verdict 由 verify_check 独占。
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--ablate all] [--inject-pollution]
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
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
    from verify_check import analyze, numeric_fields, flat_edges, norm  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目


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
    out = {}
    for s in report.get("self_check") or []:
        if isinstance(s, dict) and s.get("item"):
            out[s["item"]] = s
    return out


def objective_violations(res):
    """独立复算客观违规清单：返回 [{kind, item, detail}]，item 对应校验层检查项。

    与校验层分开实现（真值独立复算），每条客观违规对照检查项判定是否被捕获。
    """
    out = []
    inner = (res or {}).get("result") or {}
    if not isinstance(inner, dict):
        return out
    node_ids = {str(n.get("node_id")) for n in (inner.get("nodes") or [])
                if isinstance(n, dict) and n.get("node_id")}
    edges = flat_edges(inner)
    pend_ids = {str(p.get("item_id")) for p in (inner.get("pending_review") or [])
                if isinstance(p, dict)}
    edge_ids = set()
    for fi, (d, i, e) in enumerate(edges):
        eid = str(e.get("edge_id") or "")
        edge_ids.add(eid)
        if not str(e.get("source_ref") or "").strip():
            out.append({"kind": "edge_missing_source", "item": "edges[%d].source_ref" % fi,
                        "detail": "edge %s 无 source_ref" % eid})
        if e.get("pending") and (not str(e.get("pending_reason") or "").strip()
                                 or eid not in pend_ids):
            out.append({"kind": "edge_pending_unregistered",
                        "item": "edges[%d].pending_registered" % fi,
                        "detail": "pending 边 %s 未登记待复核" % eid})
        if str(e.get("from_id") or "") not in node_ids or \
                str(e.get("to_id") or "") not in node_ids:
            out.append({"kind": "dangling_endpoint", "item": "edges[%d].endpoints" % fi,
                        "detail": "edge %s 端点未登记" % eid})
    for i, m in enumerate(inner.get("merges") or []):
        if isinstance(m, dict) and not m.get("evidence"):
            out.append({"kind": "merge_no_evidence", "item": "merges[%d].evidence" % i,
                        "detail": "merge %s 无合并证据" % m.get("merge_id")})
    for i, r in enumerate(inner.get("related") or []):
        if isinstance(r, dict) and not str(r.get("reason") or "").strip():
            out.append({"kind": "related_no_reason", "item": "related[%d].reason" % i,
                        "detail": "关联 %s 无理由" % r.get("related_id")})
    cov = inner.get("tracking_coverage") or {}
    expected = {"backward_edges": len([1 for d, i, e in edges if d == "backward"]),
                "forward_edges": len([1 for d, i, e in edges if d == "forward"]),
                "related_items": len(inner.get("related") or []),
                "merges": len(inner.get("merges") or [])}
    for k, v in expected.items():
        if cov.get(k) is not None and cov.get(k) != v:
            out.append({"kind": "count_mismatch", "item": "coverage.counts",
                        "detail": "coverage.%s=%r 与实际 %d 不符" % (k, cov.get(k), v)})
    txt = norm(json.dumps(inner.get("pending_review") or [], ensure_ascii=False)
               + json.dumps(inner.get("material_gaps") or [], ensure_ascii=False)
               + str(cov.get("coverage_note") or ""))
    if expected["backward_edges"] == 0 and not any(
            k in txt for k in ("backward", "后向", "参考文献")):
        out.append({"kind": "backward_empty_unregistered",
                    "item": "coverage.backward_registered",
                    "detail": "后向为空且未登记原因"})
    if expected["forward_edges"] == 0 and not any(
            k in txt for k in ("forward", "前向", "施引")):
        out.append({"kind": "forward_empty_unregistered",
                    "item": "coverage.forward_registered",
                    "detail": "前向为空且未登记原因"})
    for i, p in enumerate(inner.get("paths") or []):
        if isinstance(p, dict) and p.get("reachable"):
            hops = p.get("hops") or []
            if not hops or any(str(h) not in edge_ids for h in hops):
                out.append({"kind": "dangling_hop", "item": "paths[%d].hops" % i,
                            "detail": "path %s 引用链断裂" % p.get("path_id")})
    return out


def mode_metrics(res, report, label):
    """从一次真实运行的 report 计算五项指标（全部来自实测，不臆造）。"""
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    edges = flat_edges(inner)

    # 1. 来源可回指边占比：source_ref 检查 applied=true 的边 / 全部边
    covered, uncovered_paths = 0, []
    for fi, (d, i, e) in enumerate(edges):
        entry = idx.get("edges[%d].source_ref" % fi)
        if entry is not None and entry.get("applied"):
            covered += 1
        else:
            uncovered_paths.append("%s[%d]" % (d, i))
    edge_ratio = (covered / len(edges)) if edges else None

    fields = numeric_fields(res)
    num_total = len(fields)
    num_covered = sum(1 for f in fields
                      if (idx.get(f.get("check")) or {}).get("applied"))
    num_ratio = (num_covered / num_total) if num_total else None

    # 2. 客观违规漏检数
    violations = objective_violations(res)
    caught, missed = 0, []
    for v in violations:
        entry = idx.get(v["item"])
        if entry is not None and entry.get("applied") and entry.get("match") is False:
            caught += 1
        else:
            missed.append(v)

    # 3. 需人工复核条目数：待复核 + 未判定边 + 漏检 + 未判定数值位
    manual_items = (len(inner.get("pending_review") or []) + len(uncovered_paths)
                    + len(missed) + (num_total - num_covered))

    # 4. 步骤数：校验层已执行检查项 + 流程层已完成步骤
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    checks_disabled = len(report.get("disabled_checks") or [])
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    steps_count = checks_executed + steps_done

    # 5. 追问轮次
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "unbacked_numbers": len(report.get("unbacked_numbers") or []),
        "unbacked_titles": len(report.get("unbacked_titles") or []),
        "metrics": {
            "backed_edge_ratio": edge_ratio,
            "backed_edge_ratio_pct": (round(edge_ratio * 100, 2)
                                       if edge_ratio is not None else None),
            "edges_total": len(edges),
            "edges_machine_adjudicated": covered,
            "edges_not_adjudicated": len(uncovered_paths),
            "numeric_adjudicated_ratio": num_ratio,
            "numeric_fields_total": num_total,
            "numeric_fields_machine_adjudicated": num_covered,
            "violations_objective": len(violations),
            "violations_caught": caught,
            "violations_missed": len(missed),
            "violations_missed_detail": missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {
                "pending_review_entries": len(inner.get("pending_review") or []),
                "edges_not_machine_adjudicated": len(uncovered_paths),
                "violations_missed": len(missed),
                "numbers_not_machine_adjudicated": num_total - num_covered,
            },
            "steps_count": steps_count,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": checks_disabled,
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入 5 类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    edges = flat_edges(inner)
    if edges:
        d, i, e = edges[0]
        e["source_ref"] = ""
        plan.append("首条边 source_ref 清空（来源不可回指）")
    cov = inner.get("tracking_coverage") or {}
    if isinstance(cov, dict) and "backward_edges" in cov:
        cov["backward_edges"] = (cov.get("backward_edges") or 0) + 100
        plan.append("tracking_coverage.backward_edges +100（计数与列表不符且无回证）")
    for m in inner.get("merges") or []:
        if isinstance(m, dict):
            m["evidence"] = []
            plan.append("首条 merge 证据清空（合并无据）")
            break
    for r in inner.get("related") or []:
        if isinstance(r, dict):
            r["reason"] = ""
            plan.append("首条关联理由清空（关联无据）")
            break
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    return p, plan


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--input-root", default=None)
        ap.add_argument("--out", default=None, help="对照证据落盘路径")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence/efficiency 写入 result.json 对应键")
        ap.add_argument("--ablate", default="all",
                        choices=("reasons", "dedup", "direction", "all"),
                        help="退化模式：关闭理由回证(reasons)/去重(dedup)/"
                             "方向覆盖(direction)或全部(all)")
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

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate=args.ablate, case_state=case_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    # 指标差（正常 − 退化，按 higher_is_better 方向解读）
    delta = {}
    for k in ("backed_edge_ratio", "violations_missed", "violations_caught",
              "manual_review_items", "steps_count", "clarification_rounds",
              "numeric_adjudicated_ratio"):
        a = m_normal["metrics"].get(k)
        b = m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "backed_edge_ratio",
         "mechanism": "每条引用边 source_ref 可回指检查 + 节点标题/年份逐字回证",
         "formula": "被机器 applied=true 判定 source_ref 的边 / 全部边",
         "higher_is_better": True,
         "degrade_effect": "关闭 reasons 后回证检查不再执行，边失去机器判定，占比下降"},
        {"metric": "violations_missed",
         "mechanism": "方向覆盖计数复核 + 空方向登记 + 悬空端点/跳 + 合并证据 + 关联理由",
         "formula": "客观违规条数 − 被校验层捕获条数（真值由探针独立复算）",
         "higher_is_better": False,
         "degrade_effect": "关闭对应机制后违规条目不再判 FAIL，漏检数上升"},
        {"metric": "manual_review_items",
         "mechanism": "待复核登记 + 边来源机器判定覆盖 + 漏检兜底",
         "formula": "待复核条目 + 未判定边 + 漏检 + 未判定数值位",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count",
         "mechanism": "六步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数",
         "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds",
         "mechanism": "把人工核对条目按每轮 %d 条打包（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式（--ablate %s），不是平台基础 "
        "Agent 与参赛 Agent 的平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。"
        % args.ablate,
        "退化模式仅关闭所选机制的检查，枚举/结构/运行状态等基础检查仍开启，"
        "因此退化侧漏检数是下界而非最坏情形。",
        "客观违规真值由探针独立复算（与校验层分开实现），但两者共用同一输入数据；"
        "若 result.json 本身无违规，漏检数两侧同为 0（此时该指标无区分度）。",
        "backed_edge_ratio 的分母只统计 traces.backward/forward 中的字典边；"
        "related/clusters/paths 不计入边占比。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数；"
        "其原始计数 manual_review_items 一并落盘，可换批量重算。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，"
        "契约字段校验跳过，下游不得宣称已核对。",
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
                  "ablate_mode": args.ablate,
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，"
                          "不做任何原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标方向为 higher_is_better 时表示机制带来增益；"
                               "delta=0 表示该指标在本输入上无区分度；"
                               "指标方向为 lower_is_better 时读 delta 的相反符号。",
    }

    # 污染反例自测（副本）
    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate=args.ablate, case_state=case_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "unbacked_numbers": len(p_normal.get("unbacked_numbers") or []),
                            "violations_missed": pm_n["metrics"]["violations_missed"],
                            "manual_review_items": pm_n["metrics"]["manual_review_items"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "unbacked_numbers": len(p_deg.get("unbacked_numbers") or []),
                              "violations_missed": pm_d["metrics"]["violations_missed"],
                              "manual_review_items": pm_d["metrics"]["manual_review_items"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "violations_missed": (pm_d["metrics"]["violations_missed"]
                                      - pm_n["metrics"]["violations_missed"]),
                "unbacked_numbers": (len(p_deg.get("unbacked_numbers") or [])
                                     - len(p_normal.get("unbacked_numbers") or [])),
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
            },
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。"
                    "missed_detection_delta > 0 表示退化模式漏掉的项数。",
        }

    # efficiency：自动可采集的效率计数
    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "input_files_scanned": None,
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "flow_steps_total": m_normal["metrics"]["steps_detail"]["flow_steps_total"],
        "flow_steps_done": m_normal["metrics"]["steps_detail"]["flow_steps_done"],
        "edges_total": m_normal["metrics"]["edges_total"],
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
            if isinstance(cur, dict):
                cur.setdefault("result", {})
                if isinstance(cur.get("result"), dict):
                    cur["result"]["gain_evidence"] = gain_evidence
                    cur["result"]["efficiency"] = efficiency
                save_json(args.result, cur)
        except Exception as e:
            print("[gain_probe] 回写 result.json 失败: %s" % e)

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式(%s) verdict=%s"
          % (m_normal["verdict"], args.ablate, m_degraded["verdict"]))
    for name in ("backed_edge_ratio_pct", "violations_missed", "violations_caught",
                 "manual_review_items", "steps_count", "clarification_rounds"):
        a = m_normal["metrics"].get(name)
        b = m_degraded["metrics"].get(name)
        dkey = "backed_edge_ratio" if name == "backed_edge_ratio_pct" else name
        print("  %-26s normal=%s  degraded=%s  delta=%s"
              % (name, a, b, delta.get(dkey)))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
