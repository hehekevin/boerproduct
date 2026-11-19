#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（feas-review）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 维度覆盖一致性：七类约束（假设与变量/对照组/设备材料/时间成本/参数范围/
     风险与异常/伦理与安全）逐方案覆盖；每个 check_item 的 dimension 合法；
     feasible 必须附逐字证据（防止"方案没写"被默认为"方案满足"）；conditional
     必须列出条件；unverifiable 必须写 pending_reason 并登记进 pending_review。
  B. 分级口径一致：grading_rubric 四级口径必须事前声明（declared_at + 四级边界
     非空，声明后不得调整）；coverage.per_status 汇总与实际一致；verdict 与判定
     进度一致；time_estimate.totals 按 rows 机械复算逐项对照。
  C. 判断依据回证：已判定条目必须有 rationale；feasible/conditional/infeasible
     的 evidence_quote 必须在 claims 证据链中逐字回证（空白归一化子串匹配）；
     每方案时间合计数字必须出现在 claim text/quote 中，未回证列入
     unbacked_numbers 并判 FAIL。
  D. 风险-缓解配对完备：每条风险必须有非空 mitigation.action，或显式
     escalation_to_human=true 且登记进 pending_review（转人工节点）；severity
     枚举合法；风险 dimension 合法。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；time_estimate 归 estimate_time.py，gain_evidence /
efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/grading_rubric.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DIMS = ("D1", "D2", "D3", "D4", "D5", "D6", "D7")
STATUSES = ("feasible", "conditional", "infeasible", "unverifiable")
CONF = ("high", "medium", "low")
SEV = ("high", "medium", "low")
EVID_STATUSES = ("feasible", "conditional", "infeasible")
VERDICTS = ("fully_reviewed", "partially_reviewed", "not_reviewed", "cannot_verify")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（子串回证匹配用）。"""
    return re.sub(r"\s+", "", str(s or ""))


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", rubric_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g, name in (("coverage", "coverage"), ("grading", "grading"),
                    ("evidence", "evidence"), ("risks", "risks")):
        if off(g):
            report["disabled_checks"].append(name)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    checks = [c for c in (inner.get("check_items") or []) if isinstance(c, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    confirmations = [c for c in (inner.get("confirmations") or []) if isinstance(c, dict)]
    grading = inner.get("grading_rubric") or {}
    cov = inner.get("coverage") or {}
    time_est = inner.get("time_estimate") if isinstance(inner.get("time_estimate"), dict) else {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "grading_ledger", "state": rubric_state,
                            "note": "" if rubric_state == "enforced" else "/app/work/grading_rubric.json 台账缺失，下游不得宣称已核对"})
    est_state = "enforced" if (time_est.get("totals") or time_est.get("computed_by")) else "not_found"
    report["gates"].append({"gate": "estimate_output", "state": est_state,
                            "note": "" if est_state == "enforced" else "time_estimate 未回填（estimate_time.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, c in enumerate(checks):
        cid = c.get("check_id") or "check_items[%d]" % i
        if c.get("dimension") not in DIMS:
            report["problems"].append("%s dimension 枚举非法: %r（须 D1-D7）" % (cid, c.get("dimension")))
        if c.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法: %r（须 feasible/conditional/infeasible/unverifiable）"
                                      % (cid, c.get("status")))
        if c.get("confidence") is not None and c.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (cid, c.get("confidence")))

    # ---- A. 维度覆盖一致性 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)

    n_cov = 0
    for i, c in enumerate(checks):
        cid = c.get("check_id") or "check_items[%d]" % i
        st = c.get("status")
        if c.get("judged") is True or st:
            ok_evid = (not off("coverage")) and \
                (st != "feasible" or bool(str(c.get("evidence_quote") or "").strip()))
            add("check_items[%d].status_evidence" % i, "feasible ⇒ 逐字证据（防『方案没写』默认满足）",
                not off("coverage"), ok_evid)
            if not off("coverage") and st == "feasible" and not str(c.get("evidence_quote") or "").strip():
                report["problems"].append("%s 判 feasible 但无逐字证据（evidence_quote 空——"
                                          "方案没写 ≠ 方案满足）" % cid)
                n_cov += 1
            ok_cond = (not off("coverage")) and (st != "conditional" or bool(c.get("conditions")))
            add("check_items[%d].conditional_conditions" % i, "conditional ⇒ conditions 非空（条件可执行）",
                not off("coverage"), ok_cond)
            if not off("coverage") and st == "conditional" and not c.get("conditions"):
                report["problems"].append("%s 判 conditional 但未列出条件（『有条件可行』必须写清有哪些条件）" % cid)
                n_cov += 1
            if not off("coverage") and st == "unverifiable" and not str(c.get("pending_reason") or "").strip():
                report["problems"].append("%s 判 unverifiable 但 pending_reason 为空" % cid)
                n_cov += 1

    # 每方案 × 每维度覆盖
    if not off("coverage"):
        plan_dims = {}
        for c in checks:
            plan_dims.setdefault(str(c.get("plan_id") or "?"), set()).add(c.get("dimension"))
        missing = []
        for pid in sorted(plan_dims):
            for d in DIMS:
                if d not in plan_dims[pid]:
                    missing.append("%s/%s" % (pid, d))
        declared_missing = ["%s" % m for m in (cov.get("missing_dimensions") or [])]
        ok_dim = all(m in declared_missing for m in missing)
        add("coverage.dimension_complete", "每方案×每维度 ≥1 判定或登记 missing_dimensions", True, ok_dim)
        if missing and not ok_dim:
            report["problems"].append("维度覆盖缺口未登记: %s（应写入 coverage.missing_dimensions）" % missing)
            n_cov += 1

    # unverifiable ⇒ pending_review 登记
    for i, c in enumerate(checks):
        cid = str(c.get("check_id") or i)
        if not off("coverage") and c.get("status") == "unverifiable" and c.get("judged") is True:
            reg = [p for p in pending_reg if str(p.get("item_id")) == cid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("check_items[%d].pending_registered" % i, "unverifiable ⇒ 登记入 pending_review", True, ok)
            if not ok:
                report["problems"].append("%s 判 unverifiable 但未登记进 pending_review（缺 reason/needed_action）" % cid)
                n_cov += 1

    # ---- B. 分级口径一致 ----
    n_grad = 0
    if not off("grading"):
        levels = grading.get("levels") or {}
        ok_decl = bool(str(grading.get("declared_at") or "").strip()) and \
            all(str(levels.get(s) or "").strip() for s in STATUSES)
        add("grading_rubric.declared", "四级口径事前声明（declared_at + 四级边界非空）", True, ok_decl)
        if not ok_decl:
            report["problems"].append("grading_rubric 未事前声明（declared_at 与 feasible/conditional/"
                                      "infeasible/unverifiable 四级边界必须先声明后判定）")
            n_grad += 1
        if not str(grading.get("evidence_rule") or "").strip():
            report["problems"].append("grading_rubric.evidence_rule 为空（须声明证据规则，防『没写默认满足』）")
            n_grad += 1
        # 时间合计机械复算
        rows = [r for r in (time_est.get("rows") or []) if isinstance(r, dict)]
        if rows:
            bad = 0
            recomputed = {}
            for r in rows:
                vals = [r.get(k) for k in ("equipment_h", "labor_h", "wait_h")]
                if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                    total = round(sum(float(v) for v in vals), 2)
                    pid = str(r.get("plan_id") or "unknown")
                    recomputed[pid] = round(recomputed.get(pid, 0.0) + total, 2)
                    stored = r.get("total_h")
                    if stored is None or abs(total - float(stored)) > 1e-6:
                        bad += 1
                        report["problems"].append("time_estimate.rows[%s/%s] total_h 复算不符（期望 %s，实际 %s）"
                                                  % (pid, r.get("step_id"), total, stored))
            add("time_estimate.totals_recompute", "rows 机械累加复算", True, bad == 0)
            totals = time_est.get("totals") or {}
            for pid, v in recomputed.items():
                sv = totals.get(pid)
                if not isinstance(sv, (int, float)) or abs(float(sv) - v) > 1e-6:
                    bad += 1
                    report["problems"].append("time_estimate.totals[%s] 与 rows 复算不符（期望 %s，实际 %s）"
                                              % (pid, v, sv))
            if bad:
                n_grad += bad
        # coverage.per_status 汇总一致性
        st_count = {s: sum(1 for c in checks if c.get("status") == s) for s in STATUSES}
        per_status = cov.get("per_status") or {}
        bad_ps = [s for s in STATUSES
                  if isinstance(per_status.get(s), int) and per_status[s] != st_count[s]]
        if bad_ps:
            report["problems"].append("coverage.per_status 与实际判定不符: %s" % bad_ps)
        per_dim = cov.get("per_dimension") or {}
        dim_count = {d: sum(1 for c in checks if c.get("dimension") == d) for d in DIMS}
        bad_pd = [d for d in DIMS
                  if isinstance(per_dim.get(d), int) and per_dim[d] != dim_count[d]]
        if bad_pd:
            report["problems"].append("coverage.per_dimension 与实际判定不符: %s" % bad_pd)
        if isinstance(cov.get("total_checks"), int) and cov["total_checks"] != len(checks):
            report["problems"].append("coverage.total_checks 与 check_items 条数不符（%s vs %d）"
                                      % (cov["total_checks"], len(checks)))

    # ---- C. 判断依据回证 ----
    n_evid = 0
    for i, c in enumerate(checks):
        cid = str(c.get("check_id") or i)
        st = c.get("status")
        if c.get("judged") is not True:
            continue
        if not off("evidence") and not str(c.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空（判断依据完备性）" % cid)
        if not off("evidence") and st in EVID_STATUSES:
            cl = claim_idx.get(cid) or claim_idx.get("check_items[%d]" % i) or []
            quote = norm(c.get("evidence_quote"))
            ok_q = any(quote and quote in norm(e.get("quote"))
                       for cc in cl for e in (cc.get("evidence") or [])) if quote else bool(cl)
            add("check_items[%d].evidence_backed" % i, "判断依据在 claims 证据链逐字回证", True, ok_q)
            if not ok_q:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % cid)
                n_evid += 1

    # 时间合计数字回证
    if not off("evidence") and (time_est.get("totals") or {}):
        for pid, v in (time_est.get("totals") or {}).items():
            if not isinstance(v, (int, float)):
                continue
            sstr = str(round(float(v), 2))
            backed = any(sstr in norm(cc.get("text")) or sstr in norm(e.get("quote"))
                         for cc in claims for e in (cc.get("evidence") or []))
            if not backed:
                report["unbacked_numbers"].append(
                    {"item": "time_estimate.totals[%s]" % pid, "value": sstr,
                     "reason": "时间合计数字未出现在任何 claim text/quote 中（估算依据不可复核）"})

    # ---- D. 风险-缓解配对完备 ----
    n_risk = 0
    for r_i, r in enumerate(risks):
        rid = str(r.get("risk_id") or "risks[%d]" % r_i)
        if r.get("severity") not in SEV:
            report["problems"].append("%s severity 枚举非法: %r（须 high/medium/low）" % (rid, r.get("severity")))
        if r.get("dimension") not in DIMS:
            report["problems"].append("%s dimension 枚举非法: %r（须 D1-D7）" % (rid, r.get("dimension")))
        mit = r.get("mitigation") if isinstance(r.get("mitigation"), dict) else {}
        has_action = bool(str(mit.get("action") or "").strip())
        escalated = r.get("escalation_to_human") is True
        reg = [p for p in pending_reg if str(p.get("item_id")) == rid]
        applied_r = not off("risks")
        ok_pair = has_action or (escalated and bool(reg))
        add("risks[%d].mitigation_pair" % r_i, "每条风险 ⇒ 缓解措施非空 或 转人工节点登记",
            applied_r, applied_r and ok_pair)
        if applied_r and not ok_pair:
            if not has_action and not escalated:
                report["problems"].append("%s 有风险但无缓解措施（mitigation.action 空）且未转人工"
                                          "（escalation_to_human 未置 true）" % rid)
            elif escalated and not reg:
                report["problems"].append("%s 已转人工（escalation_to_human=true）但未登记进 pending_review" % rid)
            n_risk += 1

    # 确认项：不把未经确认写成可执行事实
    for c_i, cf in enumerate(confirmations):
        if not str(cf.get("topic") or "").strip() or not str(cf.get("needed_action") or "").strip():
            report["problems"].append("confirmations[%d] 缺 topic 或 needed_action（确认项须写明待确认内容与动作）" % c_i)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    judged = [c for c in checks if c.get("judged") is True]
    if verdict not in VERDICTS:
        report["problems"].append("verdict 枚举非法或缺失: %r（须 fully/partially/not_reviewed/cannot_verify）" % verdict)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "fully_reviewed" and len(judged) != len(checks):
        report["problems"].append("verdict=fully_reviewed 但存在未判定检查项（judged=false）")
    if verdict == "partially_reviewed" and len(judged) == len(checks):
        report["problems"].append("verdict=partially_reviewed 但全部检查项已判定（应为 fully_reviewed）")
    if verdict == "not_reviewed" and judged:
        report["problems"].append("verdict=not_reviewed 但存在已判定检查项")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    report["counts"] = {"coverage_missed": n_cov, "grading_missed": n_grad,
                        "evidence_missed": n_evid, "risks_missed": n_risk}
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/grading_rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | coverage,grading,evidence,risks 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "unbacked_numbers": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    rub = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, rubric_state=rubric_state)
    est_state = "enforced" if ((res.get("result") or {}).get("time_estimate") or {}).get("totals") else "not_found"
    if not any(g.get("gate") == "estimate_output" for g in report["gates"]):
        report["gates"].append({"gate": "estimate_output", "state": est_state,
                                "note": "" if est_state == "enforced"
                                else "estimate_time.py 未回写 totals，下游不得宣称已核对"})
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["validator_verdict"] = report.get("verdict")
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（ablate=%s，检查项 %d 条全部 applied）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:"
              % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
        if len(report["problems"]) > 30:
            print("  ... 共 %d 处" % len(report["problems"]))
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
