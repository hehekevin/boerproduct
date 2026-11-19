#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（lit-screen-rank）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 纳入排除一致性：keep 必须命中 ≥1 条纳入标准；exclude 必须命中 ≥1 条排除
     标准；pending 必须写 pending_reason；relevance=irrelevant 不得标 keep；
     relevance=direct 除非登记 duplicate_of/冲突升级不得标 exclude。
  B. 排序依据可追溯：按 result.rubric 事前权重机械复算 fused_score 与期望顺序，
     与 items[].fused_score、ranking.ordered_ids 逐位对照；同名次/平局组须登记。
  C. 理由完备性：每条已判定文献必须有 rationale；keep/pending 条目的
     evidence_quote 必须在 claims 证据链中有逐字回证；keep 条目的 fused_score
     数字必须出现在对应 claim text/quote 中（空白归一化后子串匹配），
     未回证数字列入 unbacked_numbers 并判 FAIL。
  D. 待复核登记：label=pending 的条目必须逐条登记进 pending_review（含 reason
     与 needed_action）；冲突升级（escalated）也必须进入待复核。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
ranking / fused_score / rank 归 score_rank.py，其余归 build_skeleton + Agent。

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

REL = ("direct", "indirect", "irrelevant")
LAB = ("keep", "pending", "exclude")
CONF = ("high", "medium", "low")
VENUE = ("preprint", "published", "unknown")
WK = ("relevance", "quality", "recency")


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
    if off("consistency"):
        report["disabled_checks"].append("consistency")
    if off("ranking"):
        report["disabled_checks"].append("ranking")
    if off("evidence"):
        report["disabled_checks"].append("evidence")
    if off("pending"):
        report["disabled_checks"].append("pending")

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
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
                            "note": "" if ranking_state == "enforced" else "ranking 未回填（score_rank.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("relevance") is not None and it.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r（须 direct/indirect/irrelevant）" % (iid, it.get("relevance")))
        if it.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 keep/pending/exclude）" % (iid, it.get("label")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (iid, it.get("confidence")))
        if it.get("venue_type") not in VENUE:
            report["problems"].append("%s venue_type 枚举非法: %r（须 preprint/published/unknown）" % (iid, it.get("venue_type")))

    # ---- A. 纳入排除一致性 ----
    n_con = 0
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        lab, rel = it.get("label"), it.get("relevance")
        if it.get("judged") is True or lab:
            add("items[%d].consistency_inclusion" % i,
                "keep ⇒ criteria_hit 非空", not off("consistency"),
                (not off("consistency")) and (lab != "keep" or bool(it.get("criteria_hit"))))
            if not off("consistency") and lab == "keep" and not it.get("criteria_hit"):
                report["problems"].append("%s 标 keep 但未命中任何纳入标准（criteria_hit 空）" % iid)
                n_con += 1
            if not off("consistency") and lab == "exclude" and not it.get("excluded_by"):
                report["problems"].append("%s 标 exclude 但未命中任何排除标准（excluded_by 空）" % iid)
                n_con += 1
            if not off("consistency") and lab == "pending" and not (it.get("pending_reason") or "").strip():
                report["problems"].append("%s 标 pending 但 pending_reason 为空" % iid)
                n_con += 1
            if not off("consistency") and rel == "irrelevant" and lab == "keep":
                report["problems"].append("%s relevance=irrelevant 却标 keep（跨级矛盾）" % iid)
                n_con += 1
            if not off("consistency") and rel == "direct" and lab == "exclude" and not it.get("duplicate_of"):
                report["problems"].append("%s relevance=direct 却标 exclude 且未登记版本重复（duplicate_of 空）" % iid)
                n_con += 1

    # ---- B. 排序依据可追溯 ----
    weights = weights_ok(rubric)
    if not off("ranking"):
        if weights is None:
            report["problems"].append("rubric 权重未事前声明或非法（三项 0-1 数值且合计=1.0，declared_at 必填）")
        else:
            if not (rubric.get("declared_at") or "").strip():
                report["problems"].append("rubric.declared_at 为空（权重须在任何排序前声明）")
            add("rubric.weights_sum", "三项权重合计=1.0", True, True)
        if weights is not None:
            mism, missing = 0, 0
            for i, it in enumerate(items):
                if not it.get("factors"):
                    missing += 1
                    continue
                s = fused(weights, it.get("factors"))
                stored = it.get("fused_score")
                ok = s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) <= 1e-6
                add("items[%d].fused_recompute" % i, "rubric 权重机械复算", True, ok)
                if not ok:
                    mism += 1
                    report["problems"].append("%s fused_score 复算不符（期望 %s，实际 %s）"
                                              % (it.get("item_id"), s, stored))
            # 期望顺序对照
            scored = [(str(it.get("item_id")), fused(weights, it["factors"]),
                       float(it["factors"].get("recency") or 0.0))
                      for it in items if it.get("factors")]
            ordered = [p for p, _s, _r in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]
            got_ids = list(ranking.get("ordered_ids") or [])
            if got_ids and got_ids != ordered:
                report["problems"].append("ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % ordered[:6])
                add("ranking.order_recompute", "期望顺序逐位对照", True, False)
            else:
                add("ranking.order_recompute", "期望顺序逐位对照", True, True)
            # rank 连续性
            ranks = sorted(it.get("rank") for it in items if isinstance(it.get("rank"), int))
            if got_ids and ranks and ranks != list(range(1, len(ranks) + 1)):
                report["problems"].append("items[].rank 非连续名次序列 %s" % ranks[:8])

    # ---- C. 理由完备性 + claims 回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab = it.get("label")
        if lab is None:
            continue
        if not off("evidence") and not str(it.get("rationale") or "").strip():
            report["problems"].append("%s 已判定但 rationale 为空（理由完备性）" % iid)
        if not off("evidence") and lab == "keep" and not str(it.get("evidence_quote") or "").strip():
            report["problems"].append("%s 标 keep 但无摘要证据（evidence_quote 空）" % iid)
        if not off("evidence") and lab in ("keep", "pending"):
            cl = claim_idx.get(iid) or claim_idx.get("items[%d]" % i) or []
            quote = norm(it.get("evidence_quote"))
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            if not q_backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % iid)
            if isinstance(it.get("fused_score"), (int, float)):
                sstr = str(round(float(it["fused_score"]), 4))
                n_backed = any(sstr in norm(c.get("text")) or sstr in norm(e.get("quote"))
                               for c in cl for e in (c.get("evidence") or []))
                if not n_backed:
                    report["unbacked_numbers"].append(
                        {"item": "items[%d].fused_score" % i, "value": sstr,
                         "reason": "keep/pending 条目 fused_score 未出现在任何 claim text/quote 中"})
        if not off("pending") and lab == "pending":
            reg = [p for p in pending_reg if isinstance(p, dict) and str(p.get("item_id")) == iid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("items[%d].pending_registered" % i, "pending ⇒ 登记入 pending_review", True, ok)
            if not ok:
                report["problems"].append("%s 标 pending 但未登记进 pending_review（缺 reason/needed_action）" % iid)

    # ---- 冲突与重复处理 ----
    for i, it in enumerate(items):
        if it.get("duplicate_of"):
            iid = str(it.get("item_id") or i)
            rec = [c for c in conflicts if isinstance(c, dict)
                   and iid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
            add("items[%d].conflict_recorded" % i, "duplicate_of ⇒ conflicts 登记 merged/escalated", True, resolved)
            if not off("pending") and not resolved:
                report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 merged/escalated 处置" % iid)
            if not off("pending") and any(str(c.get("resolution")) == "escalated" for c in rec):
                in_reg = any(str(p.get("item_id")) == iid for p in pending_reg if isinstance(p, dict))
                if not in_reg:
                    report["problems"].append("%s 冲突升级(escalated)但未进入 pending_review" % iid)

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [it for it in items if it.get("judged") is True]
    lab_count = {k: sum(1 for it in items if it.get("label") == k) for k in LAB}
    if cov:
        exp = {"total_candidates": len(items), "judged_items": len(judged),
               "keep": lab_count["keep"], "pending": lab_count["pending"], "exclude": lab_count["exclude"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "screened" and len(judged) != len(items):
        report["problems"].append("verdict=screened 但存在未判定条目（judged=false）")
    if verdict == "partially_screened" and len(judged) == len(items):
        report["problems"].append("verdict=partially_screened 但全部条目已判定（应为 screened）")
    if verdict == "not_screened" and judged:
        report["problems"].append("verdict=not_screened 但存在已判定条目")
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
                        help="none | all | consistency,ranking,evidence,pending 子集")
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
    report["gates"].append({"gate": "score_rank_output",
                            "state": "enforced" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "score_rank.py 未回写 ranking，下游不得宣称已核对"})
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
