#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（exp-plan-design，实验方案设计）。

对 result.json 做五组机械校验（与题面机检点逐项对应）：
  A. variables   变量表完备：每个假设 testable 且非空；独立/因变量≥1、控制变量≥1；
                 每个变量必须有操作定义 + 测量方式 + 单位（缺一判 FAIL）。
  B. controls    对照设置：groups≥2 且 controls≥1；每个对照必须写明排除哪一类混杂
                 （excludes_confound）与依据 basis；type 枚举合法；对照组必须存在于 groups。
  C. power       样本量/功效依据：每个 groups[].n 必须在 power_basis.n_registry 登记
                 （n 一致、method 非空、source 非空、alpha/power ∈ (0,1)），未登记判 FAIL。
  D. alignment   分析计划-假设对齐：每个 hypothesis_id 必须被 ≥1 条 analysis_plan 引用；
                 analysis_plan 引用的 hypothesis_id/dv_ref 必须存在；每个因变量必须有
                 对应 measurements 条目。
  E. evidence    依据与风险完备 + claims 回证：protocol 步骤非空且关键参数必须带 basis
                 （manual/pilot/literature/vendor…）；risks 非空且含判据与止损；
                 protocol 数值参数必须出现在 claims text/quote 中（空白归一化后子串
                 匹配），未回证数字列入 unbacked_numbers 判 FAIL。

另有 plan_versions 的 fused_score 机械复算（rubric 四因子权重）与期望顺序对照。
所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
plan_ranking / fused_score / rank 归 score_plan.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--marker /app/work/skill_marker.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

CTYPES = ("blank", "positive", "negative", "dose_gradient", "vehicle", "sham")
WK = ("completeness", "feasibility", "risk_coverage", "cost_efficiency")
ROLES = ("independent", "dependent", "control")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，避免影响中文/单位/数字之外的语义）。"""
    return re.sub(r"\s+", "", str(s or ""))


def weights_ok(rubric):
    w = (rubric or {}).get("weights") or {}
    vals = []
    for k in WK:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals.append(float(v))
    if abs(sum(vals) - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    if not isinstance(factors, dict):
        return None
    vals = []
    for k in WK:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        vals.append(float(v))
    return round(sum(wi * vi for wi, vi in zip(weights, vals)), 4)


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


def analyze(res, case, ablate="none", case_state="enforced", rubric_state="not_found",
            marker_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("variables", "controls", "power", "alignment", "evidence"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    hyps = [h for h in (inner.get("hypotheses") or []) if isinstance(h, dict)]
    variables = inner.get("variables") or {}
    ivs = [v for v in (variables.get("independent") or []) if isinstance(v, dict)]
    dvs = [v for v in (variables.get("dependent") or []) if isinstance(v, dict)]
    cvs = [v for v in (variables.get("control") or []) if isinstance(v, dict)]
    controls = [c for c in (inner.get("controls") or []) if isinstance(c, dict)]
    groups = [g for g in (inner.get("groups") or []) if isinstance(g, dict)]
    nreg = [r for r in ((inner.get("power_basis") or {}).get("n_registry") or [])
            if isinstance(r, dict)]
    protocol = [s for s in (inner.get("protocol") or []) if isinstance(s, dict)]
    measures = [m for m in (inner.get("measurements") or []) if isinstance(m, dict)]
    plans = [p for p in (inner.get("analysis_plan") or []) if isinstance(p, dict)]
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    versions = [v for v in (inner.get("plan_versions") or []) if isinstance(v, dict)]
    ranking = inner.get("plan_ranking") or {}
    rubric = inner.get("rubric") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubric_ledger", "state": rubric_state,
                            "note": "" if rubric_state == "enforced" else "/app/work/rubric.json 台账缺失，下游不得宣称已核对"})
    report["gates"].append({"gate": "skill_scripts", "state": marker_state,
                            "note": "" if marker_state == "enforced" else "skill_marker.json 缺失或脚本不齐，下游不得宣称已核对"})
    ranking_state = "enforced" if ranking.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "plan_ranking_recompute", "state": ranking_state,
                            "note": "" if ranking_state == "enforced" else "plan_ranking 未回填（score_plan.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, c in enumerate(controls):
        if c.get("type") not in CTYPES:
            report["problems"].append("controls[%d] type 枚举非法: %r（须 %s…）"
                                      % (i, c.get("type"), "/".join(CTYPES[:4])))
    for i, g in enumerate(groups):
        if not isinstance(g.get("n"), int) or isinstance(g.get("n"), bool) or g.get("n", 0) <= 0:
            report["problems"].append("groups[%d].n 非正整数: %r" % (i, g.get("n")))

    # ---- A. 变量表完备 ----
    add("variables.table_present", "独立/因变量≥1 且控制变量≥1", not off("variables"),
        (not off("variables")) and bool(ivs) and bool(dvs) and bool(cvs))
    if not off("variables"):
        if not ivs or not dvs or not cvs:
            report["problems"].append("变量表不完备：独立=%d 因变量=%d 控制变量=%d（各自须≥1）"
                                      % (len(ivs), len(dvs), len(cvs)))
        for i, h in enumerate(hyps):
            hid = h.get("hypothesis_id") or "hypotheses[%d]" % i
            add("hypotheses[%d].testable" % i, "假设可检验且 text 非空", True,
                bool(str(h.get("text") or "").strip()) and h.get("testable") is True)
            if not str(h.get("text") or "").strip() or h.get("testable") is not True:
                report["problems"].append("%s 须有非空 text 且 testable=true" % hid)
        all_vars = [("independent", ivs), ("dependent", dvs), ("control", cvs)]
        vdef_missing = 0
        for role, lst in all_vars:
            for j, v in enumerate(lst):
                vid = v.get("var_id") or "%s[%d]" % (role, j)
                ok = all(bool(str(v.get(k) or "").strip()) for k in
                         ("name", "operational_definition", "measurement", "unit"))
                add("variables.%s[%d].defined" % (role, j),
                    "操作定义+测量方式+单位齐全", not off("variables"), ok)
                if not ok:
                    vdef_missing += 1
                    miss = [k for k in ("name", "operational_definition", "measurement", "unit")
                            if not str(v.get(k) or "").strip()]
                    report["problems"].append("变量 %s（%s）缺少: %s" % (vid, role, "/".join(miss)))
        add("variables.complete", "全部变量要素齐备", not off("variables"), vdef_missing == 0)

    # ---- B. 对照设置 ----
    group_ids = {str(g.get("group_id") or "") for g in groups}
    if not off("controls"):
        add("controls.count", "对照组≥2 且对照设置≥1", True,
            len(groups) >= 2 and len(controls) >= 1)
        if len(groups) < 2:
            report["problems"].append("实验组设计不足：groups=%d（须≥2，处理组+对照）" % len(groups))
        if not controls:
            report["problems"].append("无对照设置：controls 为空（至少须 1 个对照）")
        for i, c in enumerate(controls):
            cid = c.get("control_id") or "controls[%d]" % i
            g_ok = str(c.get("group_id") or "") in group_ids
            add("controls[%d].group_valid" % i, "group_id 须存在于 groups", True, g_ok)
            if not g_ok:
                report["problems"].append("%s 引用的 group_id=%r 不在 groups 中"
                                          % (cid, c.get("group_id")))
            exc_ok = bool(str(c.get("excludes_confound") or "").strip())
            add("controls[%d].excludes_confound" % i, "须写明排除哪类混杂", True, exc_ok)
            if not exc_ok:
                report["problems"].append("%s 未写明排除哪一类混杂（excludes_confound 空）" % cid)
            if not str(c.get("basis") or "").strip():
                report["problems"].append("%s 未写明对照设置依据（basis 空）" % cid)

    # ---- C. 样本量/功效依据 ----
    if not off("power"):
        add("power.registry_count", "n_registry 条目数=groups 数", True, len(nreg) >= len(groups))
        if len(nreg) < len(groups):
            report["problems"].append("功效依据登记不足：n_registry=%d < groups=%d"
                                      % (len(nreg), len(groups)))
        reg_by_gid = {}
        for r in nreg:
            reg_by_gid.setdefault(str(r.get("group_id") or ""), r)
        for i, g in enumerate(groups):
            gid = str(g.get("group_id") or "groups[%d]" % i)
            r = reg_by_gid.get(gid)
            ok = (isinstance(r, dict)
                  and isinstance(r.get("n"), int) and r.get("n") == g.get("n")
                  and bool(str(r.get("method") or "").strip())
                  and bool(str(r.get("source") or "").strip()))
            add("groups[%d].n_registered" % i, "样本量须登记功效依据", not off("power"), ok)
            if not ok:
                report["problems"].append("%s 样本量 n=%r 未在 power_basis.n_registry 登记"
                                          "（缺条目或 n/method/source 不符）" % (gid, g.get("n")))
        for i, r in enumerate(nreg):
            for k in ("alpha", "power"):
                v = r.get(k)
                if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool)
                                      or not (0 < float(v) < 1)):
                    report["problems"].append("n_registry[%d].%s 须在 (0,1) 区间: %r" % (i, k, v))

    # ---- D. 分析计划-假设对齐 ----
    hyp_ids = [str(h.get("hypothesis_id") or "") for h in hyps]
    dv_ids = {str(v.get("var_id") or "") for v in dvs}
    if not off("alignment"):
        if hyps:
            covered = {str(p.get("hypothesis_id") or "") for p in plans}
            for i, h in enumerate(hyps):
                hid = str(h.get("hypothesis_id") or i)
                ok = hid in covered
                add("hypotheses[%d].analysis_aligned" % i, "假设须被分析计划引用", not off("alignment"), ok)
                if not ok:
                    report["problems"].append("假设 %s 未被任何 analysis_plan 条目引用（分析计划-假设未对齐）" % hid)
            for i, p in enumerate(plans):
                pid = str(p.get("hypothesis_id") or "")
                if pid and pid not in hyp_ids:
                    report["problems"].append("analysis_plan[%d] 引用不存在的 hypothesis_id=%r" % (i, pid))
                if p.get("dv_ref") and str(p.get("dv_ref")) not in dv_ids:
                    report["problems"].append("analysis_plan[%d] 引用不存在的因变量 dv_ref=%r" % (i, p.get("dv_ref")))
                if not str(p.get("test") or "").strip():
                    report["problems"].append("analysis_plan[%d] 缺统计检验方法（test 空）" % i)
        add("measurements.cover_dvs", "每个因变量有测量条目", not off("alignment"),
            all(any(str(m.get("dv_ref") or "") == d for m in measures) for d in dv_ids))
        uncovered = [d for d in dv_ids if not any(str(m.get("dv_ref") or "") == d for m in measures)]
        if uncovered:
            report["problems"].append("因变量缺少测量条目: %s" % ",".join(uncovered))

    # ---- E. 依据与风险 + claims 回证 ----
    if not off("evidence"):
        add("protocol.steps_present", "protocol 步骤≥1", True, bool(protocol))
        if not protocol:
            report["problems"].append("protocol 为空（实验步骤缺失）")
        param_missing_basis = 0
        for i, s in enumerate(protocol):
            if not str(s.get("action") or "").strip():
                report["problems"].append("protocol[%d] 缺 action" % i)
            for p in (s.get("params") or []) if isinstance(s.get("params"), list) else []:
                if isinstance(p, dict) and p.get("value") is not None \
                        and not str(p.get("basis") or "").strip():
                    param_missing_basis += 1
                    report["problems"].append("protocol[%d] 参数 %r 未标依据（basis 空，须 manual/pilot/literature/vendor 等）"
                                              % (i, p.get("name")))
        add("protocol.params_basis", "关键参数逐个标依据", not off("evidence"),
            param_missing_basis == 0)
        if not risks:
            report["problems"].append("risks 为空（风险与异常处置缺失）")
        for i, r in enumerate(risks):
            ok = all(bool(str(r.get(k) or "").strip()) for k in ("failure_mode", "judge_criterion", "stop_loss"))
            add("risks[%d].complete" % i, "失败模式+判据+止损齐备", not off("evidence"), ok)
            if not ok:
                report["problems"].append("risks[%d] 缺 failure_mode/judge_criterion/stop_loss 之一" % i)
        # claims 数字回证：protocol 数值参数须出现在 claims text/quote 中
        numeric_vals = []
        for i, s in enumerate(protocol):
            for p in (s.get("params") or []) if isinstance(s.get("params"), list) else []:
                if isinstance(p, dict) and isinstance(p.get("value"), (int, float)):
                    numeric_vals.append((i, p["value"]))
        if numeric_vals and not claims:
            report["problems"].append("claims 为空但 protocol 含 %d 个数值参数（回证链缺失）"
                                      % len(numeric_vals))
        claim_corpus = norm(json.dumps(claims, ensure_ascii=False)) if claims else ""
        for i, v in numeric_vals:
            if claim_corpus and str(v) not in claim_corpus:
                report["unbacked_numbers"].append(
                    {"item": "protocol[%d].params" % i, "value": str(v),
                     "reason": "参数数值未出现在任何 claim text/quote 中"})
        if report["unbacked_numbers"]:
            report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）"
                                      % len(report["unbacked_numbers"]))
        add("claims.backchain", "数值参数逐个回证 claims", not off("evidence"),
            len(report["unbacked_numbers"]) == 0 and (claims or not numeric_vals))

    # ---- plan_versions 排序复算（rubric 四因子） ----
    weights = weights_ok(rubric)
    if not off("ranking") and versions:
        if weights is None:
            report["problems"].append("rubric 权重未事前声明或非法（四因子 0-1 数值且合计=1.0，declared_at 必填）")
        else:
            if not (rubric.get("declared_at") or "").strip():
                report["problems"].append("rubric.declared_at 为空（权重须在任何排序前声明）")
            for i, v in enumerate(versions):
                s = fused(weights, v.get("factors"))
                stored = v.get("fused_score")
                ok = s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) <= 1e-6
                add("plan_versions[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
                if not ok:
                    report["problems"].append("plan_versions[%s] fused_score 复算不符（期望 %s，实际 %s）"
                                              % (v.get("version_id"), s, stored))
            scored = [(str(v.get("version_id")), fused(weights, v.get("factors")),
                       float((v.get("factors") or {}).get("feasibility") or 0.0))
                      for v in versions if v.get("factors")]
            ordered = [p for p, _s, _f in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
            got_ids = list(ranking.get("ordered_ids") or [])
            if got_ids and got_ids != ordered:
                report["problems"].append("plan_ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % ordered[:6])
                add("plan_ranking.order_recompute", "期望顺序逐位对照", True, False)
            else:
                add("plan_ranking.order_recompute", "期望顺序逐位对照", True, True)

    # ---- 覆盖面汇总一致性（始终开启） ----
    comp = inner.get("completeness") or {}
    exp = {"hypotheses_total": len(hyps), "variables_defined": len(ivs) + len(dvs) + len(cvs),
           "controls_count": len(controls), "groups_total": len(groups),
           "protocol_steps": len(protocol), "analysis_entries": len(plans)}
    bad = [k for k, v in exp.items() if isinstance(comp.get(k), int) and comp[k] != v]
    if bad:
        report["problems"].append("completeness 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "designed" and (not hyps or not protocol or not controls):
        report["problems"].append("verdict=designed 但假设/步骤/对照存在缺失")
    if verdict == "not_designed" and (hyps or protocol):
        report["problems"].append("verdict=not_designed 但已产出假设或步骤")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") \
            and not str(rs.get("reason") or "").strip():
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

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--marker", default="/app/work/skill_marker.json",
                        help="脚本标志文件（build_skeleton 落盘）")
        ap.add_argument("--rubric", default="/app/work/rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | variables,controls,power,alignment,evidence 子集")
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
    marker = load_json(args.marker)
    marker_state = "enforced" if isinstance(marker, dict) and marker.get("all_present") else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state,
                     rubric_state=rubric_state, marker_state=marker_state)
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
