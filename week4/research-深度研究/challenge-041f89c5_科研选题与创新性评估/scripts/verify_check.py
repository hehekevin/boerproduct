#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（topic-novelty-audit）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 要素覆盖一致性：已评估选题四要素（problem/hypothesis/method/expected_
     contribution）必须非空或登记 missing_elements；feasibility 的 data/method/
     resource/time 四要素必须各有 status 与 basis；分级但要素不全未登记即违规。
  B. 口径事前声明 + 分级/排序复算：rubric（grade_rules 非空、三因子权重合计=1.0、
     declared_at 必填）必须先声明；按权重机械复算 fused_score 与期望顺序，与
     proposals[].fused_score、ranking.ordered_ids 逐位对照；分级一致性
     （overlap=covered ⇒ not_novel；breakthrough/strong ⇒ 至少一条 overlap=none；
     not_novel ⇒ 登记了 duplicate_of）。
  C. 评估回证：每条已评估选题必须有 rationale；每条 novelty_claim（overlap 非
     uncertain）必须有 closest_work_id + evidence_quote，且引文在 claims 证据链中
     逐字回证；fused_score 数字必须出现在对应 claim text/quote 中（空白归一化后
     子串匹配），未回证数字列入 unbacked_numbers 并判 FAIL。
  D. 登记完备性：grade=uncertain、missing_elements 非空、feasibility
     missing/assumption、feasibility_verdict infeasible/uncertain、冲突升级
     （escalated）都必须登记进 human_review；duplicate_of 必须在 conflicts 登记。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
ranking / fused_score / rank 归 novelty_rank.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/rubric.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

GRADES = ("breakthrough", "strong", "incremental", "not_novel", "uncertain")
OVERLAPS = ("none", "partial", "covered", "uncertain")
CLAIM_KINDS = ("method", "data", "scene", "theory")
FSTATUS = ("sufficient", "partial", "missing", "assumption")
FVERDICTS = ("feasible", "conditional", "infeasible", "uncertain")
CONF = ("high", "medium", "low")
WK = ("novelty", "feasibility", "evidence")
ELEMENTS = ("problem", "hypothesis", "method", "expected_contribution")
FEAS_KEYS = ("data", "method", "resource", "time")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠以免影响数字/英文标识之外的语义）。"""
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
    for g in ("structure", "scoring", "evidence", "review"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    props = [it for it in (inner.get("proposals") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    human_reg = inner.get("human_review") or []
    conflicts = inner.get("conflicts") or []
    ranking = inner.get("ranking") or {}
    cov = inner.get("coverage") or {}
    rubric = inner.get("rubric") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rubric_ledger", "state": rubric_state,
                            "note": "" if rubric_state == "enforced" else "/app/work/rubric.json 台账缺失，下游不得宣称已核对"})
    ranking_state = "enforced" if ranking.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "ranking_recompute", "state": ranking_state,
                            "note": "" if ranking_state == "enforced" else "ranking 未回填（novelty_rank.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, it in enumerate(props):
        pid = it.get("proposal_id") or "proposals[%d]" % i
        if it.get("novelty_grade") is not None and it.get("novelty_grade") not in GRADES:
            report["problems"].append("%s novelty_grade 枚举非法: %r（须 breakthrough/strong/incremental/not_novel/uncertain）"
                                      % (pid, it.get("novelty_grade")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (pid, it.get("confidence")))
        if it.get("feasibility_verdict") is not None and it.get("feasibility_verdict") not in FVERDICTS:
            report["problems"].append("%s feasibility_verdict 枚举非法: %r" % (pid, it.get("feasibility_verdict")))
        feas = it.get("feasibility") or {}
        for fk in FEAS_KEYS:
            fv = (feas.get(fk) or {}).get("status") if isinstance(feas.get(fk), dict) else feas.get(fk)
            if fv is not None and fv not in FSTATUS:
                report["problems"].append("%s feasibility.%s.status 枚举非法: %r（须 sufficient/partial/missing/assumption）"
                                          % (pid, fk, fv))
        for j, nc in enumerate(it.get("novelty_claims") or []):
            if not isinstance(nc, dict):
                continue
            if nc.get("overlap") is not None and nc.get("overlap") not in OVERLAPS:
                report["problems"].append("%s.novelty_claims[%d].overlap 枚举非法: %r（须 none/partial/covered/uncertain）"
                                          % (pid, j, nc.get("overlap")))
            if nc.get("kind") is not None and nc.get("kind") not in CLAIM_KINDS:
                report["problems"].append("%s.novelty_claims[%d].kind 枚举非法: %r（须 method/data/scene/theory）"
                                          % (pid, j, nc.get("kind")))

    # ---- A. 要素覆盖一致性 ----
    for i, it in enumerate(props):
        pid = it.get("proposal_id") or "proposals[%d]" % i
        if it.get("judged") is not True:
            continue
        if off("structure"):
            continue
        st = it.get("structure") or {}
        miss = [str(x) for x in (it.get("missing_elements") or [])]
        for el in ELEMENTS:
            ok = bool(str(st.get(el) or "").strip()) or el in miss
            add("proposals[%d].element_%s" % (i, el), "四要素非空或登记缺失", True, ok)
            if not ok:
                report["problems"].append("%s 要素 %s 为空且未登记 missing_elements（要素覆盖违规）" % (pid, el))
        feas = it.get("feasibility") or {}
        for fk in FEAS_KEYS:
            fv = feas.get(fk) if isinstance(feas.get(fk), dict) else {}
            ok = isinstance(fv, dict) and str(fv.get("status") or "").strip() in FSTATUS \
                 and str(fv.get("basis") or "").strip()
            add("proposals[%d].feas_%s" % (i, fk), "可行性要素 status+basis 齐备", True, ok)
            if not ok:
                report["problems"].append("%s feasibility.%s 缺 status 或 basis（可行性核查违规）" % (pid, fk))
        if it.get("novelty_grade") and not all(
                str((st.get(el) or "")).strip() or el in miss for el in ELEMENTS):
            report["problems"].append("%s 已分级但四要素不全且未登记 missing_elements" % pid)

    # ---- B. 口径事前声明 + 分级/排序复算 ----
    weights = weights_ok(rubric)
    if not off("scoring"):
        if weights is None:
            report["problems"].append("rubric 权重未事前声明或非法（三项 0-1 数值且合计=1.0，declared_at 必填）")
        else:
            if not (rubric.get("declared_at") or "").strip():
                report["problems"].append("rubric.declared_at 为空（口径须在任何分级/排序前声明）")
            if not (rubric.get("grade_rules") or []):
                report["problems"].append("rubric.grade_rules 为空（创新性分级口径须逐级声明）")
            add("rubric.weights_sum", "三项权重合计=1.0", True, True)
        if weights is not None:
            mism = 0
            for i, it in enumerate(props):
                if not it.get("factors"):
                    continue
                s = fused(weights, it.get("factors"))
                stored = it.get("fused_score")
                ok = s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) <= 1e-6
                add("proposals[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
                if not ok:
                    mism += 1
                    report["problems"].append("%s fused_score 复算不符（期望 %s，实际 %s）"
                                              % (it.get("proposal_id"), s, stored))
            scored = [(str(it.get("proposal_id")), fused(weights, it["factors"]),
                       float(it["factors"].get("novelty") or 0.0))
                      for it in props if it.get("factors")]
            ordered = [p for p, _s, _n in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
            got_ids = list(ranking.get("ordered_ids") or [])
            if got_ids and got_ids != ordered:
                report["problems"].append("ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % ordered[:6])
                add("ranking.order_recompute", "期望顺序逐位对照", True, False)
            else:
                add("ranking.order_recompute", "期望顺序逐位对照", True, True)
            ranks = sorted(it.get("rank") for it in props if isinstance(it.get("rank"), int))
            if got_ids and ranks and ranks != list(range(1, len(ranks) + 1)):
                report["problems"].append("proposals[].rank 非连续名次序列 %s" % ranks[:8])
        # 分级一致性（机械口径）
        for i, it in enumerate(props):
            pid = it.get("proposal_id") or "proposals[%d]" % i
            grade = it.get("novelty_grade")
            ovs = [str(nc.get("overlap")) for nc in (it.get("novelty_claims") or [])
                   if isinstance(nc, dict) and nc.get("overlap")]
            if grade and ovs:
                if "covered" in ovs and grade != "not_novel":
                    report["problems"].append("%s 存在 overlap=covered 创新陈述但分级为 %s（应为 not_novel）" % (pid, grade))
                if grade in ("breakthrough", "strong") and "none" not in ovs:
                    report["problems"].append("%s 分级 %s 但无任何 overlap=none 创新陈述（与声明口径矛盾）" % (pid, grade))
                if grade == "not_novel" and not it.get("duplicate_of"):
                    report["problems"].append("%s 分级 not_novel 但未登记 duplicate_of（重复项未标出）" % pid)
                add("proposals[%d].grade_consistency" % i, "分级与对照结论一致", True,
                    not (("covered" in ovs and grade != "not_novel")
                         or (grade in ("breakthrough", "strong") and "none" not in ovs)))

    # ---- C. 评估回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(props):
        pid = str(it.get("proposal_id") or i)
        if it.get("judged") is not True:
            continue
        if not off("evidence"):
            if not str(it.get("rationale") or "").strip():
                report["problems"].append("%s 已评估但 rationale 为空（评估回证缺失）" % pid)
            cl = claim_idx.get(pid) or claim_idx.get("proposals[%d]" % i) or []
            quote_bank = norm(" ".join(str(e.get("quote") or "") for c in cl
                                       for e in (c.get("evidence") or [])))
            for j, nc in enumerate(it.get("novelty_claims") or []):
                if not isinstance(nc, dict) or nc.get("overlap") == "uncertain" or not nc.get("overlap"):
                    continue
                q = norm(nc.get("evidence_quote"))
                ok = bool(str(nc.get("closest_work_id") or "").strip()) and bool(q) and q in quote_bank
                add("proposals[%d].novelty_backed[%d]" % (i, j), "对照结论 + 引文在 claims 逐字回证", True, ok)
                if not ok:
                    report["problems"].append("%s novelty_claims[%d] 对照无据（缺 closest_work_id 或引文未在 claims 逐字回证）"
                                              % (pid, j))
            if isinstance(it.get("fused_score"), (int, float)):
                sstr = str(round(float(it["fused_score"]), 4))
                n_backed = any(sstr in norm(c.get("text")) or sstr in norm(e.get("quote"))
                               for c in cl for e in (c.get("evidence") or []))
                if not n_backed:
                    report["unbacked_numbers"].append(
                        {"item": "proposals[%d].fused_score" % i, "value": sstr,
                         "reason": "已评估条目 fused_score 未出现在任何 claim text/quote 中"})

    # ---- D. 登记完备性 ----
    for i, it in enumerate(props):
        pid = str(it.get("proposal_id") or i)
        reg = [h for h in human_reg if isinstance(h, dict) and str(h.get("proposal_id")) == pid]
        need_reg = []
        if it.get("novelty_grade") == "uncertain":
            need_reg.append("grade=uncertain")
        if it.get("missing_elements"):
            need_reg.append("missing_elements 非空")
        feas = it.get("feasibility") or {}
        flagged = [fk for fk in FEAS_KEYS
                   if isinstance(feas.get(fk), dict)
                   and str(feas.get(fk).get("status") or "") in ("missing", "assumption")]
        if flagged:
            need_reg.append("feasibility %s" % ",".join(flagged))
        if it.get("feasibility_verdict") in ("infeasible", "uncertain"):
            need_reg.append("feasibility_verdict=%s" % it.get("feasibility_verdict"))
        if off("review"):
            continue
        ok = (not need_reg) or (bool(reg) and all(str(h.get("reason") or "").strip() for h in reg)
                                and all(str(h.get("needed_action") or "").strip() for h in reg))
        add("proposals[%d].human_review_registered" % i,
            "缺口/不确定 ⇒ 登记入 human_review", True, ok)
        if not ok:
            report["problems"].append("%s 存在须人工复核情形（%s）但未登记 human_review（缺 reason/needed_action）"
                                      % (pid, "；".join(need_reg)))
        if it.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and pid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("flagged", "escalated") for c in rec)
            add("proposals[%d].conflict_recorded" % i, "duplicate_of ⇒ conflicts 登记 flagged/escalated", True, resolved)
            if not resolved:
                report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 flagged/escalated 处置" % pid)
            if any(str(c.get("resolution")) == "escalated" for c in rec) and not reg:
                report["problems"].append("%s 冲突升级(escalated)但未进入 human_review" % pid)

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [it for it in props if it.get("judged") is True]

    def _complete(it):
        st = it.get("structure") or {}
        miss = [str(x) for x in (it.get("missing_elements") or [])]
        return all(str(st.get(el) or "").strip() or el in miss for el in ELEMENTS)

    def _flagged(it):
        feas = it.get("feasibility") or {}
        return any(isinstance(feas.get(fk), dict)
                   and str(feas.get(fk).get("status") or "") in ("missing", "assumption")
                   for fk in FEAS_KEYS) \
            or it.get("feasibility_verdict") in ("infeasible", "uncertain")

    if cov:
        exp = {"total_proposals": len(props), "judged": len(judged),
               "structure_complete": sum(1 for it in props if _complete(it)),
               "novelty_covered": sum(1 for it in props
                                      if it.get("novelty_grade") == "not_novel" or it.get("duplicate_of")),
               "feasibility_flagged": sum(1 for it in props if _flagged(it))}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "assessed" and len(judged) != len(props):
        report["problems"].append("verdict=assessed 但存在未评估条目（judged=false）")
    if verdict == "partially_assessed" and len(judged) == len(props):
        report["problems"].append("verdict=partially_assessed 但全部条目已评估（应为 assessed）")
    if verdict == "not_assessed" and judged:
        report["problems"].append("verdict=not_assessed 但存在已评估条目")
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
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | structure,scoring,evidence,review 子集")
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
    report["gates"].append({"gate": "novelty_rank_output",
                            "state": "enforced" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "novelty_rank.py 未回写 ranking，下游不得宣称已核对"})
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
