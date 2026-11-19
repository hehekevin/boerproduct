#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（exp-param-optimize，实验参数优化建议）。

对 result.json 做五组机械校验（与题面机检点逐项对应）：
  A. audit       当前参数取值审计：parameters 非空；每个参数 name/unit/domain
                 （min/max 数值且 min<=max）/current_value 数值/basis
                 （manual/pilot/literature/vendor）+ source_ref 非空，缺一判 FAIL。
  B. suggestions 优化建议完备：≥1 条；每条 param_id 存在、direction 枚举合法、
                 basis 非空、rationale 非空、expected_gain 量化（metric_ref 存在、
                 baseline/projected 数值、delta=projected−baseline 误差≤1e-6、
                 direction/set_to 类建议须有 suggested_value 数值）。
  C. coupling    耦合约束登记：constraints 非空；每条 params 非空且引用的参数存在、
                 expression 非空、source 非空、severity 枚举合法；kind=none_declared
                 的条目须给 source 说明（无耦合声明也算登记，不脑补约束）。
  D. search      寻优方法：method 枚举合法、rationale/stop_criteria/budget_note
                 非空；method=grid 须给 grid 分辨率描述；initial_points 非空。
  E. evidence    依据/风险/回证：parameter_response_map 每条 metric_id/evidence 齐；
                 每个响应指标有 measurement 口径；risks 非空且含判据与止损；
                 数值回证——parameters[].current_value、suggested_value、
                 projected 须出现在 claims text/quote（空白归一化后子串匹配），
                 未回证数字列入 unbacked_numbers 判 FAIL。

另有 strategy_versions 的 fused_score 机械复算（rubric 四因子）与期望顺序对照。
所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
strategy_ranking / fused_score / rank 归 score_strategy.py，feasibility_check
归 param_check.py，其余归 build_skeleton + Agent。

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

BASIS_ENUM = ("manual", "pilot", "literature", "vendor")
DIRECTIONS = ("up", "down", "hold", "set_to")
WK = ("information_gain", "cost_efficiency", "robustness", "risk_coverage")
METHODS = ("ofat", "grid", "rsm", "bayesian", "sequential", "staged_screening")
SEVERITIES = ("hard", "soft")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，避免影响中文/单位/数字之外的语义）。"""
    return re.sub(r"\s+", "", str(s or ""))


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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
    for g in ("audit", "suggestions", "coupling", "search", "evidence"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    params = [p for p in (inner.get("parameters") or []) if isinstance(p, dict)]
    suggs = [s for s in (inner.get("optimization_suggestions") or []) if isinstance(s, dict)]
    cons = [c for c in (inner.get("coupling_constraints") or []) if isinstance(c, dict)]
    pmap = [m for m in (inner.get("parameter_response_map") or []) if isinstance(m, dict)]
    metrics = [m for m in (inner.get("response_metrics") or []) if isinstance(m, dict)]
    search = inner.get("search_strategy") or {}
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    versions = [v for v in (inner.get("strategy_versions") or []) if isinstance(v, dict)]
    ranking = inner.get("strategy_ranking") or {}
    rubric = inner.get("rubric") or {}
    feas = inner.get("feasibility_check") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubric_ledger", "state": rubric_state,
                            "note": "" if rubric_state == "enforced" else "/app/work/rubric.json 台账缺失，下游不得宣称已核对"})
    report["gates"].append({"gate": "skill_scripts", "state": marker_state,
                            "note": "" if marker_state == "enforced" else "skill_marker.json 缺失或脚本不齐，下游不得宣称已核对"})
    ranking_state = "enforced" if ranking.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "strategy_ranking_recompute", "state": ranking_state,
                            "note": "" if ranking_state == "enforced" else "strategy_ranking 未回填（score_strategy.py 未跑），下游不得宣称已核对"})
    feas_state = "enforced" if feas.get("checked_count") is not None else "not_found"
    report["gates"].append({"gate": "param_feasibility_check", "state": feas_state,
                            "note": "" if feas_state == "enforced" else "feasibility_check 未回填（param_check.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, s in enumerate(suggs):
        if s.get("direction") not in DIRECTIONS:
            report["problems"].append("optimization_suggestions[%d] direction 枚举非法: %r（须 %s…）"
                                      % (i, s.get("direction"), "/".join(DIRECTIONS[:4])))
    if search.get("method") is not None and search.get("method") not in METHODS:
        report["problems"].append("search_strategy.method 枚举非法: %r（须 %s…）"
                                  % (search.get("method"), "/".join(METHODS[:4])))
    for i, c in enumerate(cons):
        if c.get("kind") == "none_declared":
            continue
        if c.get("severity") is not None and c.get("severity") not in SEVERITIES:
            report["problems"].append("coupling_constraints[%d] severity 枚举非法: %r" % (i, c.get("severity")))

    # ---- A. 当前参数取值审计 ----
    add("audit.table_present", "参数表≥1 且每条有当前值", not off("audit"),
        (not off("audit")) and bool(params))
    if not off("audit"):
        if not params:
            report["problems"].append("参数表为空（parameters=0，无法做当前值审计）")
        pbad = 0
        for i, p in enumerate(params):
            pid = p.get("param_id") or "parameters[%d]" % i
            dom = p.get("domain") if isinstance(p.get("domain"), dict) else {}
            ok = (all(bool(str(p.get(k) or "").strip()) for k in ("name", "unit", "basis", "source_ref"))
                  and p.get("basis") in BASIS_ENUM
                  and is_num(dom.get("min")) and is_num(dom.get("max"))
                  and float(dom["min"]) <= float(dom["max"])
                  and is_num(p.get("current_value")))
            add("parameters[%d].audited" % i, "name/unit/domain/basis/source_ref/当前值齐全", not off("audit"), ok)
            if not ok:
                pbad += 1
                miss = [k for k in ("name", "unit", "basis", "source_ref")
                        if not str(p.get(k) or "").strip()]
                if not (is_num(dom.get("min")) and is_num(dom.get("max"))):
                    miss.append("domain(min/max)")
                if not is_num(p.get("current_value")):
                    miss.append("current_value")
                if p.get("basis") not in BASIS_ENUM and str(p.get("basis") or "").strip():
                    miss.append("basis 枚举须 %s" % "/".join(BASIS_ENUM))
                report["problems"].append("参数 %s 审计不完整，缺少: %s" % (pid, "/".join(miss)))
        add("audit.complete", "全部参数审计要素齐备", not off("audit"), pbad == 0)

    # ---- B. 优化建议完备 ----
    param_ids = {str(p.get("param_id") or "") for p in params}
    metric_ids = {str(m.get("metric_id") or "") for m in metrics}
    if not off("suggestions"):
        add("suggestions.count", "优化建议≥1", True, len(suggs) >= 1)
        if not suggs:
            report["problems"].append("优化建议为空（optimization_suggestions=0）")
        gbad = 0
        for i, s in enumerate(suggs):
            sid = s.get("sugg_id") or "suggestions[%d]" % i
            ref_ok = str(s.get("param_id") or "") in param_ids
            g = s.get("expected_gain") if isinstance(s.get("expected_gain"), dict) else {}
            gain_ok = (str(g.get("metric_ref") or "") in metric_ids
                       and is_num(g.get("baseline")) and is_num(g.get("projected"))
                       and is_num(g.get("delta"))
                       and abs(float(g["projected"]) - float(g["baseline"]) - float(g["delta"])) <= 1e-6)
            need_val = s.get("direction") == "set_to"
            val_ok = (not need_val) or is_num(s.get("suggested_value"))
            ok = (ref_ok and bool(str(s.get("basis") or "").strip())
                  and bool(str(s.get("rationale") or "").strip()) and gain_ok and val_ok)
            add("suggestions[%d].complete" % i, "param_ref+依据+理由+量化收益齐备", not off("suggestions"), ok)
            if not ok:
                gbad += 1
                if not ref_ok:
                    report["problems"].append("%s 引用的 param_id=%r 不在 parameters 中" % (sid, s.get("param_id")))
                if not str(s.get("basis") or "").strip():
                    report["problems"].append("%s 未标优化依据（basis 空）" % sid)
                if not str(s.get("rationale") or "").strip():
                    report["problems"].append("%s 缺建议理由（rationale 空）" % sid)
                if not gain_ok:
                    report["problems"].append("%s 预期收益未量化或口径错误（expected_gain 须含 metric_ref/"
                                              "baseline/projected/delta 且 delta=projected−baseline）" % sid)
                if not val_ok:
                    report["problems"].append("%s 方向为 set_to 但缺数值 suggested_value" % sid)
        add("suggestions.complete", "全部建议要素齐备", not off("suggestions"), gbad == 0)

    # ---- C. 耦合约束登记 ----
    if not off("coupling"):
        add("coupling.registered", "耦合约束条目≥1（含 none_declared 声明）", not off("coupling"),
            len(cons) >= 1)
        if not cons:
            report["problems"].append("耦合约束未登记：coupling_constraints 为空"
                                      "（确无耦合也须登记 kind=none_declared 条目并给 source）")
        for i, c in enumerate(cons):
            cid = c.get("cid") or "constraints[%d]" % i
            if c.get("kind") == "none_declared":
                ok = bool(str(c.get("source") or "").strip())
                add("constraints[%d].declared" % i, "无耦合声明须给 source", not off("coupling"), ok)
                if not ok:
                    report["problems"].append("%s 声明无耦合但 source 为空" % cid)
                continue
            refs = [str(x) for x in (c.get("params") or []) if str(x).strip()]
            ok = (bool(refs) and all(x in param_ids for x in refs)
                  and bool(str(c.get("expression") or "").strip())
                  and bool(str(c.get("source") or "").strip()))
            add("constraints[%d].valid" % i, "params 引用有效+表达式+依据齐备", not off("coupling"), ok)
            if not ok:
                bad_refs = [x for x in refs if x not in param_ids]
                if bad_refs:
                    report["problems"].append("%s 引用不存在的参数: %s" % (cid, ",".join(bad_refs)))
                if not str(c.get("expression") or "").strip():
                    report["problems"].append("%s 缺约束表达式（expression 空）" % cid)
                if not str(c.get("source") or "").strip():
                    report["problems"].append("%s 缺约束来源（source 空，须设备手册/材料规格/安全阈值）" % cid)

    # ---- D. 寻优方法 ----
    if not off("search"):
        ok = (search.get("method") in METHODS
              and bool(str(search.get("rationale") or "").strip())
              and bool(str(search.get("stop_criteria") or "").strip())
              and bool(str(search.get("budget_note") or "").strip())
              and bool(str(search.get("initial_points") or "").strip()))
        add("search.strategy_complete", "method/rationale/stop_criteria/budget/initial_points 齐备",
            not off("search"), ok)
        if not ok:
            if search.get("method") not in METHODS:
                report["problems"].append("search_strategy.method 缺失或非法: %r" % search.get("method"))
            for k in ("rationale", "stop_criteria", "budget_note", "initial_points"):
                if not str(search.get(k) or "").strip():
                    report["problems"].append("search_strategy.%s 为空（收敛与停止判据须可复核）" % k)
        if search.get("method") == "grid" and not str(search.get("grid_resolution") or "").strip():
            report["problems"].append("method=grid 须登记网格分辨率（grid_resolution：各参数步长/点数）")

    # ---- E. 依据/风险/回证 ----
    if not off("evidence"):
        add("response_map.present", "参数-响应关系图非空", not off("evidence"), bool(pmap))
        if not pmap:
            report["problems"].append("参数-响应关系图为空（parameter_response_map=0）")
        for i, m in enumerate(pmap):
            ok = (str(m.get("param_id") or "") in param_ids
                  and str(m.get("metric_id") or "") in metric_ids
                  and bool(str(m.get("relation") or "").strip())
                  and bool(str(m.get("evidence") or "").strip()))
            add("response_map[%d].complete" % i, "参数/指标引用有效+关系+依据齐备", not off("evidence"), ok)
            if not ok:
                report["problems"].append("parameter_response_map[%d] 缺 param_id/metric_id/"
                                          "relation/evidence 或引用无效" % i)
        add("metrics.measurable", "每个响应指标有测量口径", not off("evidence"),
            all(bool(str(m.get("measurement") or "").strip()) for m in metrics) and bool(metrics))
        if not metrics:
            report["problems"].append("响应指标为空（response_metrics=0）")
        else:
            for i, m in enumerate(metrics):
                if not str(m.get("measurement") or "").strip():
                    report["problems"].append("response_metrics[%d] 缺测量口径（measurement 空）" % i)
        if not risks:
            report["problems"].append("risks 为空（风险与异常处置缺失）")
        for i, r in enumerate(risks):
            ok = all(bool(str(r.get(k) or "").strip()) for k in ("failure_mode", "judge_criterion", "stop_loss"))
            add("risks[%d].complete" % i, "失败模式+判据+止损齐备", not off("evidence"), ok)
            if not ok:
                report["problems"].append("risks[%d] 缺 failure_mode/judge_criterion/stop_loss 之一" % i)
        # claims 数字回证：当前值/建议值/预期收益须出现在 claims text/quote 中
        numeric_vals = []
        for i, p in enumerate(params):
            if is_num(p.get("current_value")):
                numeric_vals.append(("parameters[%d].current_value" % i, p["current_value"]))
        for i, s in enumerate(suggs):
            if is_num(s.get("suggested_value")):
                numeric_vals.append(("suggestions[%d].suggested_value" % i, s["suggested_value"]))
            g = s.get("expected_gain") if isinstance(s.get("expected_gain"), dict) else {}
            if is_num(g.get("projected")):
                numeric_vals.append(("suggestions[%d].expected_gain.projected" % i, g["projected"]))
        if numeric_vals and not claims:
            report["problems"].append("claims 为空但存在 %d 个业务数值（回证链缺失）" % len(numeric_vals))
        claim_corpus = norm(json.dumps(claims, ensure_ascii=False)) if claims else ""
        for loc, v in numeric_vals:
            if claim_corpus and str(v) not in claim_corpus:
                report["unbacked_numbers"].append(
                    {"item": loc, "value": str(v), "reason": "数值未出现在任何 claim text/quote 中"})
        if report["unbacked_numbers"]:
            report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）"
                                      % len(report["unbacked_numbers"]))
        add("claims.backchain", "业务数值逐个回证 claims", not off("evidence"),
            len(report["unbacked_numbers"]) == 0 and (claims or not numeric_vals))

    # ---- strategy_versions 排序复算（rubric 四因子） ----
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
                add("strategy_versions[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
                if not ok:
                    report["problems"].append("strategy_versions[%s] fused_score 复算不符（期望 %s，实际 %s）"
                                              % (v.get("version_id"), s, stored))
            scored = [(str(v.get("version_id")), fused(weights, v.get("factors")),
                       float((v.get("factors") or {}).get("cost_efficiency") or 0.0))
                      for v in versions if v.get("factors")]
            ordered = [p for p, _s, _f in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
            got_ids = list(ranking.get("ordered_ids") or [])
            if got_ids and got_ids != ordered:
                report["problems"].append("strategy_ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % ordered[:6])
                add("strategy_ranking.order_recompute", "期望顺序逐位对照", True, False)
            else:
                add("strategy_ranking.order_recompute", "期望顺序逐位对照", True, True)

    # ---- 覆盖面汇总一致性（始终开启） ----
    comp = inner.get("completeness") or {}
    exp = {"parameters_total": len(params), "metrics_total": len(metrics),
           "map_entries": len(pmap), "suggestions_total": len(suggs),
           "constraints_total": len(cons), "risks_total": len(risks),
           "strategy_versions": len(versions)}
    bad = [k for k, v in exp.items() if isinstance(comp.get(k), int) and comp[k] != v]
    if bad:
        report["problems"].append("completeness 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "optimized" and (not params or not suggs or not str(search.get("method") or "").strip()):
        report["problems"].append("verdict=optimized 但参数表/建议/寻优方法存在缺失")
    if verdict == "not_optimized" and (params or suggs):
        report["problems"].append("verdict=not_optimized 但已产出参数审计或优化建议")
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
                        help="none | all | audit,suggestions,coupling,search,evidence 子集")
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
