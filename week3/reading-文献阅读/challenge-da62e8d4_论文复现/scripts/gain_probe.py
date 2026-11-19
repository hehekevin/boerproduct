#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（repro-verify）。

同一输入跑两遍：正常模式（全部机械校验开启）与退化/基线模式（--ablate 关闭
可复算逐字回证与容差复算），逐项对照五类可观测指标：

  1. recomputable_ratio   可复算数值占比（被机器逐位判定的数值位 / 全部数值位）
  2. tolerance_missed     容差违规漏检数（客观违规但校验层未捕获的条数）
  3. manual_review_items  需人工核对条目数（缺材料 + 未判定数值位 + 失败候选）
  4. steps_count          步骤数（校验层已执行检查项 + 流程已执行步骤）
  5. clarification_rounds 追问轮次（人工条目按每轮 3 条打包折算，公式随记录落盘）

另采集 efficiency 效率计数（自动可测：墙钟、字节数、检查项数、禁用项数、文件数），
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
    from verify_check import analyze, numeric_fields, parse_tol  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目


# ----------------------------------------------------------------- 工具函数
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
    """self_check → {item: entry}"""
    out = {}
    for s in report.get("self_check") or []:
        if isinstance(s, dict) and s.get("item"):
            out[s["item"]] = s
    return out


def ground_truth_violations(res):
    """独立复算客观容差违规：|paper-computed| 超容差 且 结果声称 within_tolerance=true。"""
    out = []
    inner = (res or {}).get("result") or {}
    for i, mc in enumerate(inner.get("metric_checks") or []):
        if not isinstance(mc, dict):
            continue
        pv, cv = mc.get("paper_value"), mc.get("computed_value")
        if not isinstance(pv, (int, float)) or not isinstance(cv, (int, float)):
            continue
        tol = parse_tol(str(mc.get("tolerance") or ""))
        if not tol:
            continue
        mode, v = tol
        lim = (v / 100.0 * max(abs(pv), 1e-12)) if mode == "rel" else v
        obj_violation = abs(pv - cv) > lim
        claimed_inside = mc.get("within_tolerance") is True
        if obj_violation and claimed_inside:
            out.append({"index": i, "metric": mc.get("metric"),
                        "paper_value": pv, "computed_value": cv,
                        "tolerance": mc.get("tolerance"),
                        "delta": round(abs(pv - cv), 12),
                        "kind": "claimed_inside_but_outside"})
    return out


def count_files(root):
    n = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            n += len(filenames)
    except Exception:
        pass
    return n


# ----------------------------------------------------------------- 单模式指标
def mode_metrics(res, report, label):
    """从一次真实运行的 report 计算五项指标（全部来自实测，不臆造）。"""
    idx = check_index(report)
    fields = numeric_fields(res)
    total_numeric = len(fields)
    inner = (res or {}).get("result") or {}

    # 1. 可复算数值占比：被机器逐位判定（对应检查项 applied=true）的数值位占比
    covered, uncovered_paths = 0, []
    for f in fields:
        e = idx.get(f.get("check"))
        if e is not None and e.get("applied"):
            covered += 1
        else:
            uncovered_paths.append(f.get("path"))
    ratio = (covered / total_numeric) if total_numeric else None

    # 声明口径的可复算占比（result.recomputability.ratio，两模式相同，属数据属性）
    try:
        rec = inner.get("recomputability") or {}
        declared_ratio = rec.get("ratio")
    except Exception:
        declared_ratio = None

    # 2. 容差违规漏检数：客观违规未被校验层捕获的条数
    gt = ground_truth_violations(res)
    caught, missed = 0, []
    for g in gt:
        e = idx.get("metric_checks[%d].tolerance_recompute" % g["index"])
        if e is not None and e.get("applied") and e.get("match") is False:
            caught += 1
        else:
            missed.append(g)
    # 容差判定覆盖面：有多少指标行的容差被真正复算过 / 其中判定正确的条数
    tol_rows = [i for i, mc in enumerate(inner.get("metric_checks") or [])
                if isinstance(mc, dict) and mc.get("paper_value") is not None
                and mc.get("computed_value") is not None]
    tol_adjudicated = sum(1 for i in tol_rows
                           if (idx.get("metric_checks[%d].tolerance_recompute" % i) or {})
                           .get("applied"))
    tol_correct = 0
    for i in tol_rows:
        mc = inner["metric_checks"][i]
        pv, cv = mc.get("paper_value"), mc.get("computed_value")
        tol = parse_tol(str(mc.get("tolerance") or ""))
        if not tol:
            continue
        mode_, v = tol
        lim = (v / 100.0 * max(abs(pv), 1e-12)) if mode_ == "rel" else v
        truly_inside = abs(pv - cv) <= lim
        if bool(mc.get("within_tolerance")) == truly_inside:
            tol_correct += 1

    # 3. 需人工核对条目数：缺材料 + 未被机器判定的数值位 + 失败候选
    rows = (inner.get("parameters") or []) + (inner.get("metric_checks") or [])
    missing_material = [i for i, r in enumerate(rows)
                        if isinstance(r, dict) and r.get("recomputable") is False]
    failed_cands = [c.get("candidate_id") for c in (inner.get("candidates") or [])
                    if isinstance(c, dict) and not c.get("ran")]
    manual_items = (len(missing_material) + len(uncovered_paths) + len(failed_cands)
                    + len(missed))

    # 4. 步骤数：校验层已执行检查项 + 流程层已执行步骤
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
            "recomputable_ratio": ratio,
            "recomputable_ratio_pct": (round(ratio * 100, 2) if ratio is not None else None),
            "recomputable_ratio_declared": declared_ratio,
            "numeric_fields_total": total_numeric,
            "numeric_fields_machine_adjudicated": covered,
            "numeric_fields_not_adjudicated": len(uncovered_paths),
            "tolerance_violations_objective": len(gt),
            "tolerance_violations_caught": caught,
            "tolerance_missed": len(missed),
            "tolerance_missed_detail": missed,
            "tolerance_rows_total": len(tol_rows),
            "tolerance_rows_adjudicated": tol_adjudicated,
            "tolerance_verdicts_correct": tol_correct,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {
                "missing_material_items": len(missing_material),
                "numbers_not_machine_adjudicated": len(uncovered_paths),
                "failed_candidates": len(failed_cands),
                "tolerance_missed": len(missed),
            },
            "steps_count": steps_count,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": checks_disabled,
                             "flow_steps_total": steps_total,
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


# ----------------------------------------------------------------- 污染注入
def inject_pollution(res):
    """在副本上注入 6 类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []

    mcs = inner.get("metric_checks") or []
    if mcs:
        m0 = mcs[0]
        if isinstance(m0.get("paper_value"), (int, float)):
            m0["paper_value"] = 0.999999
            plan.append("metric_checks[0].paper_value 改为 0.999999（quote 无回证）")
        if isinstance(m0.get("computed_value"), (int, float)):
            m0["computed_value"] = float(m0["computed_value"]) * 1000.0
            m0["within_tolerance"] = True
            plan.append("metric_checks[0].computed_value ×1000 且仍标 within_tolerance=true"
                        "（客观超容差）")
    else:
        plan.append("（无 metric_checks，跳过数值污染）")

    params = inner.get("parameters") or []
    for prm in params:
        if isinstance(prm, dict) and prm.get("recomputable") is False:
            prm["missing_for_recompute"] = ""
            plan.append("parameters 某行 recomputable=false 但清空 missing_for_recompute")
            break

    cands = inner.get("candidates") or []
    for c in cands:
        if isinstance(c, dict) and not c.get("ran"):
            c["failure_stage"] = None
            plan.append("candidates 某行 ran=false 且清空 failure_stage")
            break

    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    return p, plan


# ----------------------------------------------------------------- 主流程
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
    for k in ("recomputable_ratio", "tolerance_missed", "tolerance_rows_adjudicated",
              "manual_review_items", "steps_count", "clarification_rounds"):
        a = m_normal["metrics"].get(k)
        b = m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "recomputable_ratio",
         "mechanism": "claims 证据链 + 数字逐字回证（value_backed / numbers_backed / "
                      "delta_backed）+ 容差复算",
         "formula": "被机器 applied=true 判定的数值位 / 全部数值位",
         "higher_is_better": True,
         "degrade_effect": "关闭回证与容差复算后，数值位不再被机器逐位判定，占比下降"},
        {"metric": "tolerance_missed",
         "mechanism": "within_tolerance 复算（objective 复算 |paper-computed| vs 事前容差）",
         "formula": "客观超容差且自称 within_tolerance=true 的条目 − 被校验层捕获的条目",
         "higher_is_better": False,
         "degrade_effect": "关闭容差复算后，超容差条目不再被判 FAIL，漏检数上升"},
        {"metric": "tolerance_rows_adjudicated",
         "mechanism": "逐行容差复算覆盖面（每条 paper/computed 齐备的指标行）",
         "formula": "tolerance_recompute 检查 applied=true 的指标行数",
         "higher_is_better": True,
         "degrade_effect": "关闭容差复算后该覆盖面归零，超容差行不再被判定"},
        {"metric": "manual_review_items",
         "mechanism": "recomputable=false 登记 + 数值位机器判定覆盖 + 候选失败登记",
         "formula": "缺材料条目 + 未判定数值位 + 失败候选 + 容差漏检",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count",
         "mechanism": "五步线性流程 + 机械校验三元组自检",
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
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式仅关闭逐字回证与容差复算，参数来源枚举、失败阶段、归因枚举、结构守卫等"
        "检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "容差违规的客观真值由探针独立复算得出（|paper-computed| 与事前容差比较），"
        "与校验层共用同一 parse_tol 实现；若容差串无法解析，该条目不计入真值。",
        "可复算数值占比的分母只统计 result.parameters / metric_checks / attributions 中的"
        "数值位；text 型参数值与无数值的条目不计入。",
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
                            "tolerance_missed": pm_n["metrics"]["tolerance_missed"],
                            "manual_review_items": pm_n["metrics"]["manual_review_items"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "unbacked_numbers": len(p_deg.get("unbacked_numbers") or []),
                              "tolerance_missed": pm_d["metrics"]["tolerance_missed"],
                              "manual_review_items": pm_d["metrics"]["manual_review_items"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "tolerance_missed": (pm_d["metrics"]["tolerance_missed"]
                                     - pm_n["metrics"]["tolerance_missed"]),
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
        "input_files_scanned": count_files(args.input_root) if args.input_root else None,
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "flow_steps_total": m_normal["metrics"]["steps_detail"]["flow_steps_total"],
        "flow_steps_done": m_normal["metrics"]["steps_detail"]["flow_steps_done"],
        "numeric_fields_total": m_normal["metrics"]["numeric_fields_total"],
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
    for name in ("recomputable_ratio_pct", "tolerance_missed", "tolerance_rows_adjudicated",
                 "manual_review_items", "steps_count", "clarification_rounds"):
        a = m_normal["metrics"].get(name)
        b = m_degraded["metrics"].get(name)
        dkey = "recomputable_ratio" if name == "recomputable_ratio_pct" else name
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
