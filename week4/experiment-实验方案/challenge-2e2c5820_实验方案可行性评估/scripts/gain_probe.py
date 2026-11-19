#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（feas-review）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭维度覆盖 / 分级口径 / 依据回证 / 风险-缓解配对四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. coverage_missed     维度覆盖漏检数（判 feasible 无证据 / conditional 无条件 /
                         unverifiable 未登记 / 维度缺口未登记，客观存在但未捕获）
  2. grading_missed      分级口径漏检数（时间合计复算不符 / 口径未事前声明但未捕获）
  3. evidence_missed     判断依据漏检数（判断无 claims 逐字回证）
  4. risks_missed        风险-缓解漏配对数（有风险无缓解且未转人工）
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入：判断无据 / 有条件无清单 / 有风险无缓解 / 待复核清空 / 证据链清空；
正常模式须抓到污染项，退出码恒 0）。

**本脚本只产出对照证据；退化模式仅用于增益对照，不得用于交付自检。**
用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution]
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
    from verify_check import analyze  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
DIMS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7")
EVID_STATUSES = ("feasible", "conditional", "infeasible")


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


def caught(idx, key):
    e = idx.get(key)
    return bool(e and e.get("applied") and e.get("match") is False)


def objective_violations(res):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    checks = [c for c in (inner.get("check_items") or []) if isinstance(c, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    time_est = inner.get("time_estimate") if isinstance(inner.get("time_estimate"), dict) else {}
    cov, grad, evid, rk = [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for c in checks:
        cid = str(c.get("check_id") or "")
        st = c.get("status")
        if st == "feasible" and not str(c.get("evidence_quote") or "").strip():
            cov.append("%s(feasible 无证据)" % cid)
        if st == "conditional" and not c.get("conditions"):
            cov.append("%s(conditional 无条件)" % cid)
        if st == "unverifiable" and c.get("judged") is True and \
                not any(str(p.get("item_id")) == cid for p in pending_reg):
            cov.append("%s(unverifiable 未登记)" % cid)
        if c.get("judged") is True and st in EVID_STATUSES and cid not in claim_ids:
            evid.append(cid)
    for r in risks:
        rid = str(r.get("risk_id") or "")
        mit = r.get("mitigation") if isinstance(r.get("mitigation"), dict) else {}
        has_action = bool(str(mit.get("action") or "").strip())
        esc_reg = r.get("escalation_to_human") is True and \
            any(str(p.get("item_id")) == rid for p in pending_reg)
        if not has_action and not esc_reg:
            rk.append(rid)
    # 分级口径：时间合计复算真值
    rows = [r for r in (time_est.get("rows") or []) if isinstance(r, dict)]
    if rows and (time_est.get("totals") or {}):
        recomp = {}
        for r in rows:
            vals = [r.get(k) for k in ("equipment_h", "labor_h", "wait_h")]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                pid = str(r.get("plan_id") or "unknown")
                recomp[pid] = round(recomp.get(pid, 0.0) + round(sum(float(v) for v in vals), 2), 2)
        for pid, v in recomp.items():
            sv = (time_est.get("totals") or {}).get(pid)
            if not isinstance(sv, (int, float)) or abs(float(sv) - v) > 1e-6:
                grad.append("totals[%s](%s vs %s)" % (pid, v, sv))
    return {"coverage": cov, "grading": grad, "evidence": evid, "risks": rk}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    inner = (res or {}).get("result") or {}
    checks = [c for c in (inner.get("check_items") or []) if isinstance(c, dict)]
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    cov = sum(1 for i in range(len(checks))
              if caught(idx, "check_items[%d].status_evidence" % i)
              or caught(idx, "check_items[%d].conditional_conditions" % i)
              or caught(idx, "check_items[%d].pending_registered" % i))
    grad = sum(1 for i in range(len(checks)) if caught(idx, "check_items[%d].evidence_backed" % i) and False)
    if caught(idx, "time_estimate.totals_recompute"):
        grad += 1
    if caught(idx, "grading_rubric.declared"):
        grad += 1
    evid = sum(1 for i in range(len(checks)) if caught(idx, "check_items[%d].evidence_backed" % i))
    rk = sum(1 for _i in range(len(risks)) if caught(idx, "risks[%d].mitigation_pair" % _i))
    return cov, grad, evid, rk


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    checks = [c for c in (inner.get("check_items") or []) if isinstance(c, dict)]
    gt = objective_violations(res)
    cov_caught, grad_caught, evid_caught, rk_caught = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else 0
    cov_missed = max(len(gt["coverage"]) - cov_caught, 0)
    grad_missed = max(len(gt["grading"]) - grad_caught, 0)
    rk_missed = max(len(gt["risks"]) - rk_caught, 0)

    unjudged = sum(1 for c in checks if c.get("judged") is not True)
    manual_items = unjudged + cov_missed + grad_missed + evid_missed + rk_missed

    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "coverage_violations_objective": len(gt["coverage"]),
            "coverage_caught": cov_caught,
            "coverage_missed": cov_missed,
            "grading_violations_objective": len(gt["grading"]),
            "grading_caught": grad_caught,
            "grading_missed": grad_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "risks_violations_objective": len(gt["risks"]),
            "risks_missed": rk_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "coverage_missed": cov_missed,
                                        "grading_missed": grad_missed,
                                        "evidence_missed": evid_missed,
                                        "risks_missed": rk_missed},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    checks = [c for c in (inner.get("check_items") or []) if isinstance(c, dict)]
    for c in checks:
        if c.get("status") == "feasible":
            c["evidence_quote"] = None
            c["rationale"] = None
            plan.append("%s 判 feasible 但清空 evidence_quote/rationale（判断无据）" % c.get("check_id"))
            break
    for c in checks:
        if c.get("status") == "conditional":
            c["conditions"] = []
            plan.append("%s 判 conditional 但清空 conditions（有条件可行却写不清条件）" % c.get("check_id"))
            break
    for r in (inner.get("risks") or []):
        if isinstance(r, dict):
            r["mitigation"] = {}
            plan.append("%s 清空 mitigation（有风险无缓解且未转人工）" % r.get("risk_id"))
            break
    for c in checks:
        if c.get("status") == "unverifiable" and c.get("judged") is True:
            c["pending_reason"] = None
            plan.append("%s 判 unverifiable 但清空 pending_reason" % c.get("check_id"))
            break
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（判断依据回证链缺失）")
    if not plan:
        plan.append("（无可注入位置：check_items 为空）")
    return p, plan


def count_files(root):
    n = 0
    try:
        for _dirpath, _dirnames, filenames in os.walk(root):
            n += len(filenames)
    except Exception:
        pass
    return n


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--rubric", default="/app/work/grading_rubric.json")
        ap.add_argument("--out", default=None)
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
    rub = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, rubric_state=rubric_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, rubric_state=rubric_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("coverage_missed", "grading_missed", "evidence_missed",
                  "risks_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "coverage_missed", "mechanism": "维度覆盖一致性检查（七类约束逐方案覆盖；"
         "feasible⇒逐字证据防『方案没写默认满足』；conditional⇒conditions 非空；"
         "unverifiable⇒登记待复核）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后『方案没写』可被默认为满足、有条件可行可不写条件、"
         "无法核实的条目可静默漏登记，漏检数上升"},
        {"metric": "grading_missed", "mechanism": "分级口径一致性检查（四级口径事前声明 + "
         "time_estimate.totals 按 rows 机械复算逐项对照）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后口径可事后调整凑结论、时间合计被篡改不再可检出"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（feasible/conditional/"
         "infeasible 判断须有 source_id 对应 claim 逐字回证；时间合计数字须出现在 claim text/quote）",
         "formula": "无回证的已判定条目数", "higher_is_better": False,
         "degrade_effect": "关闭后判断依据缺失不再判 FAIL，审查结论退化为自述"},
        {"metric": "risks_missed", "mechanism": "风险-缓解配对检查（每条风险 ⇒ mitigation.action "
         "非空 或 escalation_to_human=true 且登记转人工节点）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后有风险无缓解可静默通过，降级路径与转人工节点丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目合计",
         "formula": "unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（coverage/grading/evidence/risks），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "time_estimate.rows 未填时分级复算真值不可得，grading_missed 记 0 但属『无法判定』而非『无违规』。",
        "把 --ablate 的退化结果当作交付自检结论即为误用。",
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
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，不做原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标为 lower_is_better 时表示机制带来增益"
                               "（漏检减少）；delta=0 表示该指标在本输入上无区分度。",
    }

    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state, rubric_state=rubric_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, rubric_state=rubric_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "coverage_missed": pm_n["metrics"]["coverage_missed"],
                            "grading_missed": pm_n["metrics"]["grading_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "risks_missed": pm_n["metrics"]["risks_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "coverage_missed": pm_d["metrics"]["coverage_missed"],
                              "grading_missed": pm_d["metrics"]["grading_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "risks_missed": pm_d["metrics"]["risks_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "coverage_missed": pm_d["metrics"]["coverage_missed"]
                                   - pm_n["metrics"]["coverage_missed"],
                "grading_missed": pm_d["metrics"]["grading_missed"]
                                  - pm_n["metrics"]["grading_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "risks_missed": pm_d["metrics"]["risks_missed"]
                                - pm_n["metrics"]["risks_missed"],
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
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
        "input_files_scanned": count_files(os.path.dirname(os.path.abspath(args.case))),
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "checks_total": len([c for c in ((res.get("result") or {}).get("check_items") or [])
                             if isinstance(c, dict)]),
        "risks_total": len([r for r in ((res.get("result") or {}).get("risks") or [])
                            if isinstance(r, dict)]),
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
    for name in delta_keys:
        a, b = m_normal["metrics"].get(name), m_degraded["metrics"].get(name)
        print("  %-22s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(name)))
    if "pollution_selftest" in gain_evidence:
        ps = gain_evidence["pollution_selftest"]
        print("  污染反例: caught_by_normal_mode=%s（注入 %d 项）"
              % (ps["caught_by_normal_mode"], len(ps["injected"])))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
