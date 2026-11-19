#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（quest-search / challenge-e7598a44）。

同一输入跑两遍：正常模式（全部机械校验开启）与退化/基线模式（--ablate 关闭
子问题覆盖校验、相关性判定校验、缺口登记校验），逐项对照五类可观测指标：

  1. coverage_ratio       子问题查询覆盖机器判定占比（被校验层逐项判定的子问题 / 全部）
  2. relevance_missed     相关性依据缺失漏检数（客观违规但校验层未捕获的条数）
  3. manual_review_items  需人工核对条目数（未判定子问题 + 未判定候选 + 漏检违规）
  4. steps_count          步骤数（校验层已执行检查项 + 流程已完成步骤）
  5. clarification_rounds 追问轮次（人工条目按每轮 3 条打包折算，公式随记录落盘）

另采集 efficiency 效率计数（自动可测：墙钟、字节数、检查项数、禁用项数），
并支持 --inject-pollution 生成污染副本做反例自测（校验器须抓到，且退出码恒 0）。

**本脚本只产出对照证据，不修改业务结论；退化模式仅用于增益对照，不得用于交付自检。**
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into
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
    from verify_check import analyze, numeric_fields, subq_status  # noqa: E402
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


def relevance_violations(res):
    """独立复算客观违规：候选缺 relevance_basis 或 included=false 缺排除原因。"""
    out = []
    inner = (res or {}).get("result") or {}
    for i, c in enumerate(inner.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        if not str(c.get("relevance_basis") or "").strip():
            out.append({"index": i, "candidate_id": c.get("candidate_id"),
                        "kind": "relevance_basis_missing"})
        if c.get("included") is False and not str(c.get("exclusion_reason") or "").strip():
            out.append({"index": i, "candidate_id": c.get("candidate_id"),
                        "kind": "exclusion_reason_missing"})
    return out


def mode_metrics(res, report, label):
    """从一次真实运行的 report 计算五项指标（全部来自实测，不臆造）。"""
    idx = check_index(report)
    inner = (res or {}).get("result") or {}

    # 1. 子问题查询覆盖机器判定占比
    rows = subq_status(inner)
    total_subq = len(rows)
    adjudicated, not_adjudicated = 0, []
    for r in rows:
        e = idx.get("subquestions[%d].query_coverage" % r["index"])
        if e is not None and e.get("applied"):
            adjudicated += 1
        else:
            not_adjudicated.append("subquestions[%d]" % r["index"])
    ratio = (adjudicated / total_subq) if total_subq else None

    # 2. 相关性依据缺失漏检数：客观违规未被校验层捕获的条数
    gt = relevance_violations(res)
    caught, missed = 0, []
    for g in gt:
        e = idx.get("candidates[%d].relevance_basis" % g["index"]) \
            if g["kind"] == "relevance_basis_missing" \
            else idx.get("candidates[%d].exclusion_reason" % g["index"])
        if e is not None and e.get("applied") and e.get("match") is False:
            caught += 1
        else:
            missed.append(g)

    # 候选相关性判定覆盖面
    cands = inner.get("candidates") or []
    cand_adjudicated = sum(1 for i in range(len(cands))
                           if (idx.get("candidates[%d].relevance_basis" % i) or {})
                           .get("applied"))

    # 3. 需人工核对条目数：未判定子问题 + 未判定候选 + 漏检违规
    manual_items = len(not_adjudicated) + (len(cands) - cand_adjudicated) + len(missed)

    # 4. 步骤数：校验层已执行检查项 + 流程层已完成步骤
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    checks_disabled = len(report.get("disabled_checks") or [])
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    steps_total = len(steps_field)
    steps_count = checks_executed + steps_done

    # 5. 追问轮次：人工条目按每轮 3 条打包（公式落盘可复算）
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "unbacked_numbers": len(report.get("unbacked_numbers") or []),
        "metrics": {
            "coverage_ratio": ratio,
            "coverage_ratio_pct": (round(ratio * 100, 2) if ratio is not None else None),
            "subquestions_total": total_subq,
            "subquestions_machine_adjudicated": adjudicated,
            "subquestions_not_adjudicated": len(not_adjudicated),
            "relevance_violations_objective": len(gt),
            "relevance_violations_caught": caught,
            "relevance_missed": len(missed),
            "relevance_missed_detail": missed,
            "candidates_total": len(cands),
            "candidates_adjudicated": cand_adjudicated,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {
                "subquestions_not_adjudicated": len(not_adjudicated),
                "candidates_not_adjudicated": len(cands) - cand_adjudicated,
                "relevance_missed": len(missed),
            },
            "steps_count": steps_count,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": checks_disabled,
                             "flow_steps_total": steps_total,
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入 5 类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []

    cands = inner.get("candidates") or []
    for c in cands:
        if isinstance(c, dict) and str(c.get("relevance_basis") or "").strip():
            c["relevance_basis"] = ""
            plan.append("candidates 某行清空 relevance_basis（相关性判定无据）")
            break
    for c in cands:
        if isinstance(c, dict) and c.get("included") is False:
            c["exclusion_reason"] = ""
            plan.append("candidates 某行 included=false 但清空 exclusion_reason")
            break
    if cands and not any("relevance_basis" in str(x) for x in plan):
        if isinstance(cands[0], dict):
            cands[0]["relevance_basis"] = ""
            plan.append("candidates[0] 清空 relevance_basis")

    subqs = inner.get("subquestions") or []
    for s in subqs:
        if isinstance(s, dict):
            s["query_ids"] = []
            plan.append("subquestions 某行清空 query_ids（子问题失去查询覆盖）")
            break

    if inner.get("gaps"):
        plan.append("清空 gaps（缺口登记缺失，%d 条）" % len(inner["gaps"]))
        inner["gaps"] = []

    p["claims"] = []
    plan.append("清空 claims（证据链缺失，数字回证失效）")
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
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
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
                           ablate="all", case_state=case_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    # 指标差（正常 − 退化，正数表示机制带来的增益）
    delta = {}
    for k in ("coverage_ratio", "relevance_missed", "candidates_adjudicated",
              "manual_review_items", "steps_count", "clarification_rounds"):
        a = m_normal["metrics"].get(k)
        b = m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "coverage_ratio",
         "mechanism": "子问题→查询覆盖校验（query_ids 必须挂到 query_plan 中存在的查询）"
                      "+ reproducibility 计数一致性复算",
         "formula": "被机器 applied=true 判定的子问题 / 全部子问题",
         "higher_is_better": True,
         "degrade_effect": "关闭覆盖校验后，子问题不再被机器逐项判定，占比下降"},
        {"metric": "relevance_missed",
         "mechanism": "相关性判定有据校验（relevance_basis 非空 + included=false 须有排除原因）",
         "formula": "客观缺失相关性依据的候选 − 被校验层捕获的候选",
         "higher_is_better": False,
         "degrade_effect": "关闭相关性校验后，无据候选不再被判 FAIL，漏检数上升"},
        {"metric": "candidates_adjudicated",
         "mechanism": "逐候选相关性判定覆盖面（每条候选的 relevance_basis 检查）",
         "formula": "relevance_basis 检查 applied=true 的候选条数",
         "higher_is_better": True,
         "degrade_effect": "关闭相关性校验后该覆盖面归零，无据候选不再被判定"},
        {"metric": "manual_review_items",
         "mechanism": "子问题机器判定覆盖 + 候选机器判定覆盖 + 漏检违规登记",
         "formula": "未判定子问题 + 未判定候选 + 相关性漏检",
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
         "degrade_effect": "人工条目越多，回材料/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式仅关闭子问题覆盖、相关性判定、缺口登记三类校验，查询式合法性、依赖引用、"
        "枚举校验、结构守卫等检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "相关性违规的客观真值由探针独立复算得出（relevance_basis 为空 / included=false "
        "缺排除原因），与校验层共用同一 _txt 实现；两臂共用同一份输入内容。",
        "coverage_ratio 的分母只统计 result.subquestions 中的子问题行；无子问题时占比为 null。",
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
                        ablate="all", case_state=case_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "unbacked_numbers": len(p_normal.get("unbacked_numbers") or []),
                            "relevance_missed": pm_n["metrics"]["relevance_missed"],
                            "manual_review_items": pm_n["metrics"]["manual_review_items"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "unbacked_numbers": len(p_deg.get("unbacked_numbers") or []),
                              "relevance_missed": pm_d["metrics"]["relevance_missed"],
                              "manual_review_items": pm_d["metrics"]["manual_review_items"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "relevance_missed": (pm_d["metrics"]["relevance_missed"]
                                     - pm_n["metrics"]["relevance_missed"]),
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
        "subquestions_total": m_normal["metrics"]["subquestions_total"],
        "candidates_total": m_normal["metrics"]["candidates_total"],
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

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式 verdict=%s"
          % (m_normal["verdict"], m_degraded["verdict"]))
    for name in ("coverage_ratio_pct", "relevance_missed", "candidates_adjudicated",
                 "manual_review_items", "steps_count", "clarification_rounds"):
        a = m_normal["metrics"].get(name)
        b = m_degraded["metrics"].get(name)
        dkey = "coverage_ratio" if name == "coverage_ratio_pct" else name
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
