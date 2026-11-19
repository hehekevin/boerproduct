#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（exp-plan-compare，实验方案比较与选择）。

对 result.json 做六组机械校验（与题面机检点逐项对应）：
  A. rubric        权重事前声明：五维权重（scientific_value/feasibility/cost/
                   duration/risk_control）为非负数值且合计=1.0；declared_at 非空；
                   与 /app/work/rubric.json 台账一致（台账存在时）。
  B. comparability 比较口径统一：comparability.dimensions 声明五维定义；每个候选
                   方案在全部五维上都有 score+basis+evidence_ref（缺一格判 FAIL）。
  C. evidence      打分依据回证：每个格子 evidence_ref 必须指向存在的 claim 且
                   claim 带非空 quote；选中方案 protocol 数值参数须出现在 claims
                   （空白归一化后子串匹配）→ unbacked_numbers；risks 须含判据止损。
  D. ranking       总分复算一致：fused_score 与 rubric 权重机械复算一致（±1e-6）；
                   plan_ranking.ordered_ids 与复算顺序逐位一致；同分记入 ties。
  E. sensitivity   敏感性分析存在且可复算：variants 非空（≥2 方案时）、每变体
                   winner 与独立复算一致、overall_stable 一致、flip_conditions 一致。
  F. choice        选择与放弃登记：final_choice.chosen_id == 排序第 1；全部落选
                   方案都有非空 rejection_reason；choice_reasons 非空。

所有检查项产出三元组 {item, template_value, applied, match}。**键归属**：本脚本
只写顶层 self_check / gates / unbacked_numbers / validator_verdict 四键；
gain_evidence / efficiency 归 gain_probe.py，plan_ranking / sensitivity /
fused_score / rank 归 score_plan.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--marker /app/work/skill_marker.json] [--rubric /app/work/rubric.json] \
        [--out /app/work/verify_check.json] [--ablate none|all|rubric,comparability,...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from score_plan import WEIGHT_KEYS, compute_sensitivity, fused, order_ids, \
        scored_pairs, weights_ok
except Exception as e:  # pragma: no cover
    WEIGHT_KEYS = ("scientific_value", "feasibility", "cost", "duration", "risk_control")

    def _missing(*_a, **_k):
        return None
    compute_sensitivity = fused = order_ids = scored_pairs = weights_ok = _missing
    print("[verify_check] 无法导入 score_plan（排序/敏感性复算降级）: %s" % e)

ABLATE_GROUPS = ("rubric", "comparability", "evidence", "ranking", "sensitivity", "choice")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，避免影响中文/单位/数字之外的语义）。"""
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


def cell_valid(c):
    """factors_detail 单格有效性：score 数值 + basis 非空 + evidence_ref 非空。"""
    if not isinstance(c, dict):
        return False
    v = c.get("score")
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and 0.0 <= float(v) <= 1.0
            and bool(str(c.get("basis") or "").strip())
            and bool(str(c.get("evidence_ref") or "").strip()))


def analyze(res, case, ablate="none", case_state="enforced", rubric_state="not_found",
            marker_state="not_found", ledger=None):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ABLATE_GROUPS:
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    versions = [v for v in (inner.get("plan_versions") or []) if isinstance(v, dict)]
    ranking = inner.get("plan_ranking") or {}
    rubric = inner.get("rubric") or {}
    comp = inner.get("comparability") or {}
    sens = inner.get("sensitivity") or {}
    choice = inner.get("final_choice") or {}
    chosen = str(choice.get("chosen_id") or "")
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    protocol = [s for s in (inner.get("protocol") or []) if isinstance(s, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    claim_ids = {str(c.get("claim_id") or "") for c in claims}

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
    sens_state = "enforced" if sens.get("available") else "not_found"
    report["gates"].append({"gate": "sensitivity_recompute", "state": sens_state,
                            "note": "" if sens_state == "enforced" else "result.sensitivity 未回填或不可用（score_plan.py 敏感性未跑），下游不得宣称已核对"})

    # ---- A. 权重事前声明 ----
    weights = weights_ok(rubric) if callable(weights_ok) else None
    if not off("rubric"):
        add("rubric.weights_valid", "五维权重非负数值且合计=1.0", True, weights is not None)
        if weights is None:
            report["problems"].append("rubric 权重未事前声明或非法（五维非负数值且合计=1.0）")
        da_ok = bool(str(rubric.get("declared_at") or "").strip())
        add("rubric.declared_at", "declared_at 必填（任何排序之前声明）", True, da_ok)
        if not da_ok:
            report["problems"].append("rubric.declared_at 为空（权重须在任何方案排序前声明，之后禁止调整）")
        led_w = (ledger or {}).get("weights") if isinstance(ledger, dict) else None
        if isinstance(led_w, dict) and weights is not None \
                and all(isinstance(led_w.get(k), (int, float))
                        and not isinstance(led_w.get(k), bool) for k in WEIGHT_KEYS):
            same = all(abs(float(led_w[k]) - weights[k]) <= 1e-6 for k in WEIGHT_KEYS)
            add("rubric.ledger_match", "与 /app/work/rubric.json 台账一致", True, same)
            if not same:
                report["problems"].append("result.rubric.weights 与 rubric.json 台账不一致（声明后禁止调整）")

    # ---- B. 比较口径统一 ----
    cells_total, cells_bad, cells_backed = 0, 0, 0
    if not off("comparability"):
        dims = [d for d in (comp.get("dimensions") or []) if isinstance(d, dict)]
        dim_names = {str(d.get("dim") or "") for d in dims}
        dims_ok = all(str(d.get("definition") or "").strip() for d in dims) \
            and set(WEIGHT_KEYS).issubset(dim_names)
        add("comparability.dimensions_declared", "五维口径定义逐条声明", True, dims_ok)
        if not dims_ok:
            miss = [k for k in WEIGHT_KEYS if k not in dim_names]
            empty = [str(d.get("dim")) for d in dims if not str(d.get("definition") or "").strip()]
            report["problems"].append("comparability.dimensions 缺维度 %s 或 definition 为空 %s"
                                      % (miss, empty))
        for i, v in enumerate(versions):
            pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
            fd = v.get("factors_detail") if isinstance(v.get("factors_detail"), dict) else {}
            for k in WEIGHT_KEYS:
                cells_total += 1
                ok = cell_valid(fd.get(k))
                if ok:
                    cells_backed += 1
                else:
                    cells_bad += 1
                    report["problems"].append("%s.factors_detail.%s 缺 score(0-1)/basis/evidence_ref 之一"
                                              % (pid, k))
        add("comparability.cells_complete", "每方案×每维度 score+basis+evidence_ref 齐备",
            True, cells_total > 0 and cells_bad == 0)

    # ---- C. 打分依据回证 ----
    if not off("evidence"):
        backed_ok = True
        for i, v in enumerate(versions):
            pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
            fd = v.get("factors_detail") if isinstance(v.get("factors_detail"), dict) else {}
            for k in WEIGHT_KEYS:
                c = fd.get(k)
                if not isinstance(c, dict):
                    continue
                ref = str(c.get("evidence_ref") or "")
                cl = next((x for x in claims if str(x.get("claim_id") or "") == ref), None)
                quote_ok = bool(cl) and any(
                    isinstance(e, dict) and str(e.get("quote") or "").strip()
                    for e in (cl.get("evidence") or []))
                if not quote_ok:
                    backed_ok = False
                    report["problems"].append("%s.factors_detail.%s 的 evidence_ref=%r 未指向"
                                              "带非空 quote 的 claim（依据回证断裂）" % (pid, k, ref))
        add("evidence.score_backchain", "逐维度打分依据回证 claims（quote 非空）", True,
            cells_total > 0 and backed_ok)
        # 选中方案 protocol 数值参数回证
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
        add("evidence.protocol_params", "选中方案数值参数逐字回证", True,
            len(report["unbacked_numbers"]) == 0 and (claims or not numeric_vals))
        add("evidence.risks_complete", "风险含失败模式+判据+止损", True,
            bool(risks) and all(str(r.get(k) or "").strip()
                                for r in risks for k in ("failure_mode", "judge_criterion", "stop_loss")))
        if not risks or any(not str(r.get(k) or "").strip()
                            for r in risks for k in ("failure_mode", "judge_criterion", "stop_loss")):
            report["problems"].append("risks 为空或缺 failure_mode/judge_criterion/stop_loss")

    # ---- D. 总分复算一致 ----
    if not off("ranking") and callable(fused) and weights:
        if len(scored_pairs(versions, weights)) < 2:
            report["problems"].append("可参与复算的候选方案 %d 个（<2），无法构成比较"
                                      % len(scored_pairs(versions, weights)))
        for i, v in enumerate(versions):
            pid = str(v.get("plan_id") or "plan_versions[%d]" % i)
            s = fused(weights, v.get("factors")) if weights else None
            stored = v.get("fused_score")
            ok = s is not None and isinstance(stored, (int, float)) \
                and abs(s - float(stored)) <= 1e-6
            add("plan_versions[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
            if not ok:
                report["problems"].append("plan_versions[%s] fused_score 复算不符（期望 %s，实际 %s）"
                                          % (pid, s, stored))
        ordered = order_ids(scored_pairs(versions, weights)) if weights else []
        got_ids = list(ranking.get("ordered_ids") or [])
        order_ok = bool(ordered) and (not got_ids or got_ids == ordered)
        add("plan_ranking.order_recompute", "期望顺序逐位对照", True, order_ok)
        if not order_ok:
            report["problems"].append("plan_ranking.ordered_ids 与机械复算顺序不一致（期望 %s）"
                                      % ordered[:6])

    # ---- E. 敏感性分析存在且可复算 ----
    if not off("sensitivity") and callable(compute_sensitivity) and weights:
        n_scored = len(scored_pairs(versions, weights))
        if n_scored >= 2:
            expect = compute_sensitivity(versions, weights)
            add("sensitivity.present", "敏感性分析存在（variants 非空）", True,
                bool(sens.get("available")) and bool(sens.get("variants")))
            if not (sens.get("available") and sens.get("variants")):
                report["problems"].append("result.sensitivity 缺失或 variants 为空"
                                          "（敏感性分析为机检必查项）")
            else:
                got = {str(v.get("variant")): v for v in (sens.get("variants") or [])
                       if isinstance(v, dict)}
                mism = [v["variant"] for v in (expect.get("variants") or [])
                        if got.get(v["variant"], {}).get("winner_id") != v["winner_id"]]
                stable_ok = bool(sens.get("overall_stable")) == bool(expect.get("overall_stable"))
                flips_ok = len(sens.get("flip_conditions") or []) == len(expect.get("flip_conditions") or [])
                add("sensitivity.recompute_match", "逐变体 winner 与独立复算一致", True,
                    not mism and stable_ok and flips_ok)
                if mism:
                    report["problems"].append("sensitivity.variants 有 %d 个变体 winner 与复算不符"
                                              "（首例 %s）" % (len(mism), mism[0]))
                if not stable_ok:
                    report["problems"].append("sensitivity.overall_stable 与复算不符"
                                              "（期望 %s）" % expect.get("overall_stable"))
                if not flips_ok:
                    report["problems"].append("sensitivity.flip_conditions 条数与复算不符"
                                              "（期望 %d）" % len(expect.get("flip_conditions") or []))
            if sens.get("available") and sens.get("overall_stable") is False \
                    and not (choice.get("choice_reasons") or []):
                report["problems"].append("overall_stable=false 但 final_choice.choice_reasons 为空"
                                          "（须说明权重翻转条件）")

    # ---- F. 最终选择与放弃理由登记 ----
    if not off("choice"):
        top = (ranking.get("ordered_ids") or [None])[0]
        top_ok = bool(chosen) and (top is None or chosen == str(top))
        add("choice.top_consistent", "chosen_id == plan_ranking 第 1 名", True, top_ok)
        if not top_ok:
            report["problems"].append("final_choice.chosen_id=%r 与 plan_ranking 第 1 名 %r 不一致"
                                      % (chosen, top))
        add("choice.reasons", "选择理由非空", True,
            bool(choice.get("choice_reasons") or []))
        if not (choice.get("choice_reasons") or []):
            report["problems"].append("final_choice.choice_reasons 为空（最终选择理由缺失）")
        rejected = [r for r in (choice.get("rejected") or []) if isinstance(r, dict)]
        scored_ids = {str(p) for p, _s, _r in (scored_pairs(versions, weights)
                                               if (callable(scored_pairs) and weights) else [])}
        missing = [pid for pid in scored_ids
                   if pid != chosen and not any(
                       str(r.get("plan_id") or "") == pid
                       and str(r.get("rejection_reason") or "").strip() for r in rejected)]
        add("choice.rejections_registered", "全部落选方案登记放弃理由", True,
            not missing)
        if missing:
            report["problems"].append("落选方案缺放弃理由登记: %s" % ",".join(missing))
        for j, r in enumerate(rejected):
            if str(r.get("plan_id") or "") == chosen:
                report["problems"].append("final_choice.rejected[%d] 把选中方案也登记为放弃" % j)

    # ---- 覆盖面汇总一致性（始终开启） ----
    comp_sum = inner.get("completeness") or {}
    exp = {"candidates_total": len(versions), "dimensions_declared":
           len([d for d in (comp.get("dimensions") or []) if isinstance(d, dict)]),
           "sensitivity_variants": len(sens.get("variants") or []),
           "rejected_registered": len([r for r in (choice.get("rejected") or [])
                                       if isinstance(r, dict)]),
           "claims_total": len(claims)}
    if not off("comparability"):
        # 比较口径组被关闭时 cells 计数为 0 属关闭副作用，不参与汇总比对
        exp["scored_cells"] = cells_total
        exp["backed_cells"] = cells_backed
    bad = [k for k, v in exp.items() if isinstance(comp_sum.get(k), int) and comp_sum[k] != v]
    if bad:
        report["problems"].append("completeness 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    hyps = inner.get("hypotheses") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "selected" and (not ranking.get("ordered_ids") or not chosen
                                  or not hyps or not protocol):
        report["problems"].append("verdict=selected 但排序/选择/假设/步骤存在缺失")
    if verdict == "not_selected" and versions:
        report["problems"].append("verdict=not_selected 但已登记候选方案")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") \
            and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")
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
                        help="none | all | rubric,comparability,evidence,ranking,sensitivity,choice 子集")
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
                     rubric_state=rubric_state, marker_state=marker_state, ledger=rub)
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
        print("[verify_check] PASS（ablate=%s，检查项 %d 条）"
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
