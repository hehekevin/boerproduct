#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（lit-track-incremental）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 事件-标签一致性（event/label）：label=push 须 event∈{new,version_update,backfill}
     且 in_window 不为 False 且 relevance=direct 且有摘要证据；event=out_of_window
     须标 exclude；event=duplicate 须 related_to + conflicts 登记 merged/escalated；
     event=retraction 须登记进 version_chains 且不得 push；label=hold 须有
     pending_reason 并登记 pending_review；label=exclude 须有 excluded_by；
     event 无法机械判定（null）时不得 push。
  B. 时效排序可复算：window.start/end 为 ISO 日期且 start<=end、timezone 已声明；
     rubric 权重（relevance/recency/confidence 合计=1.0、declared_at 非空）机械复算
     track_score，与 items[].track_score、ranking.ordered_ids 逐位对照
     （track_score 降序 → published_date 降序 → item_id 升序）；rank 连续。
  C. 证据链回证：已判定条目 rationale 非空；push 条目 evidence_quote 须在 claims
     证据链中有逐字回证；push/hold 条目 track_score 数字须出现在对应 claim
     text/quote 中（空白归一化后子串匹配），未回证数字列入 unbacked_numbers 并判
     FAIL；dedup_key 须与按 title/doi/arxiv 机械重算结果一致（归一化规则可复算，
     \\w 含 CJK，不用 isalpha）。
  D. 登记完整性：hold 逐条登记 pending_review；duplicate_of/related_to 在
     conflicts 登记 merged/escalated；escalated 须进入待复核；version_update/
     retraction 条目须登记进 version_chains；source_registry 非空且每条目有
     source_ref；coverage 汇总与实际条目一致。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
ranking / dedup_key / event / track_score / rank / version_chains 归 track_engine.py，
其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--policy /app/work/track_policy.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from track_engine import dedup_key_of, fused, parse_date, weights_ok  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[verify_check] 无法导入 track_engine: %s" % e)
    sys.exit(0)

REL = ("direct", "indirect", "irrelevant")
LAB = ("push", "hold", "exclude")
CONF = ("high", "medium", "low")
VENUE = ("preprint", "published", "unknown")
EVENT = ("new", "version_update", "duplicate", "backfill", "retraction", "out_of_window")
PUSHABLE = ("new", "version_update", "backfill")


def norm(s):
    """空白归一化（不做大小写折叠以免影响数字/英文标识之外的语义）。"""
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


def analyze(res, case, ablate="none", case_state="enforced", policy_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("consistency", "order", "evidence", "registry"):
        if off(g):
            report["disabled_checks"].append(g)

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
    chains = inner.get("version_chains") or []
    registry = inner.get("source_registry") or []
    ranking = inner.get("ranking") or {}
    cov = inner.get("coverage") or {}
    rubric = inner.get("rubric") or {}
    window = inner.get("window") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "policy_ledger", "state": policy_state,
                            "note": "" if policy_state == "enforced" else "/app/work/track_policy.json 台账缺失，下游不得宣称已核对"})
    rank_state = "enforced" if ranking.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "ranking_recompute", "state": rank_state,
                            "note": "" if rank_state == "enforced" else "ranking 未回填（track_engine.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("relevance") is not None and it.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r（须 direct/indirect/irrelevant）" % (iid, it.get("relevance")))
        if it.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 push/hold/exclude）" % (iid, it.get("label")))
        if it.get("event") is not None and it.get("event") not in EVENT:
            report["problems"].append("%s event 枚举非法: %r（须 new/version_update/duplicate/backfill/retraction/out_of_window）" % (iid, it.get("event")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (iid, it.get("confidence")))
        if it.get("venue_type") not in VENUE:
            report["problems"].append("%s venue_type 枚举非法: %r（须 preprint/published/unknown）" % (iid, it.get("venue_type")))

    # ---- A. 事件-标签一致性 ----
    chain_members = {str(m) for ch in chains if isinstance(ch, dict)
                     for m in (ch.get("member_ids") or [])}
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        lab, ev, rel = it.get("label"), it.get("event"), it.get("relevance")
        if it.get("judged") is True or lab:
            add("items[%d].consistency_event_label" % i,
                "push ⇒ 可推送事件 + 窗内 + direct + 有证据", not off("consistency"),
                (not off("consistency")) and (lab != "push" or (
                    ev in PUSHABLE and it.get("in_window") is not False
                    and rel == "direct" and bool(str(it.get("evidence_quote") or "").strip()))))
            if not off("consistency") and lab == "push":
                if ev not in PUSHABLE:
                    report["problems"].append("%s 标 push 但 event=%r 不可推送（须 new/version_update/backfill）" % (iid, ev))
                if it.get("in_window") is False:
                    report["problems"].append("%s 标 push 但 in_window=False（窗外条目不得推送）" % iid)
                if rel != "direct":
                    report["problems"].append("%s 标 push 但 relevance=%r（须 direct）" % (iid, rel))
                if not str(it.get("evidence_quote") or "").strip():
                    report["problems"].append("%s 标 push 但无摘要证据（evidence_quote 空）" % iid)
            if not off("consistency") and ev == "out_of_window" and lab != "exclude":
                report["problems"].append("%s event=out_of_window 但 label=%r（须 exclude）" % (iid, lab))
            if not off("consistency") and ev == "duplicate" and not it.get("related_to"):
                report["problems"].append("%s event=duplicate 但 related_to 为空（须指向保留条目）" % iid)
            if not off("consistency") and ev == "retraction" and lab == "push":
                report["problems"].append("%s event=retraction 却标 push（撤稿只可登记/提示，不得作为新文献推送）" % iid)
            if not off("consistency") and lab == "hold" and not str(it.get("pending_reason") or "").strip():
                report["problems"].append("%s 标 hold 但 pending_reason 为空" % iid)
            if not off("consistency") and lab == "exclude" and not it.get("excluded_by"):
                report["problems"].append("%s 标 exclude 但 excluded_by 为空（须写排除依据）" % iid)
            if not off("consistency") and rel == "irrelevant" and lab == "push":
                report["problems"].append("%s relevance=irrelevant 却标 push（跨级矛盾）" % iid)

    # ---- B. 时效排序可追溯 ----
    if not off("order"):
        wstart, wend = parse_date(window.get("start")), parse_date(window.get("end"))
        tz_ok = bool(str(window.get("timezone") or "").strip())
        add("window.iso_consistency", "start<=end 且为 ISO 日期且 timezone 已声明", True,
            bool(wstart and wend and wstart <= wend and tz_ok))
        if not (wstart and wend and wstart <= wend and tz_ok):
            report["problems"].append("window 声明非法（start<=end 且 ISO 日期且 timezone 非空）: %r" % window)
        weights = weights_ok(rubric)
        if weights is None:
            report["problems"].append("rubric 权重未事前声明或非法（relevance/recency/confidence 0-1 且合计=1.0）")
        else:
            if not (rubric.get("declared_at") or "").strip():
                report["problems"].append("rubric.declared_at 为空（权重须在任何排序前声明）")
            add("rubric.weights_sum", "三项权重合计=1.0", True, True)
            mism = 0
            for i, it in enumerate(items):
                if not it.get("factors"):
                    continue
                s = fused(weights, it.get("factors"))
                stored = it.get("track_score")
                ok = s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) <= 1e-6
                add("items[%d].score_recompute" % i, "rubric 权重机械复算 track_score", True, ok)
                if not ok:
                    mism += 1
                    report["problems"].append("%s track_score 复算不符（期望 %s，实际 %s）"
                                              % (it.get("item_id"), s, stored))
            # 期望顺序：track_score 降序 → published_date 降序 → item_id 升序
            scored = [(str(it.get("item_id")), fused(weights, it["factors"]),
                       parse_date(it.get("published_date")) or "0000-00-00")
                      for it in items if it.get("factors")]
            ordered = sorted(scored, key=lambda t: str(t[0]))
            ordered.sort(key=lambda t: t[2], reverse=True)
            ordered = sorted(ordered, key=lambda t: -t[1]) if ordered else ordered
            # 稳定排序叠加：先 item_id，再日期降序，再分数降序 → 等价于 (score desc, date desc, id asc)
            exp_ids = [p for p, _s, _d in ordered]
            got_ids = list(ranking.get("ordered_ids") or [])
            if got_ids and exp_ids and got_ids != exp_ids:
                report["problems"].append("ranking.ordered_ids 与机械复算顺序不一致（期望 %s…）" % exp_ids[:6])
                add("ranking.order_recompute", "期望顺序逐位对照", True, False)
            elif exp_ids:
                add("ranking.order_recompute", "期望顺序逐位对照", True, True)
            ranks = sorted(it.get("rank") for it in items if isinstance(it.get("rank"), int))
            if got_ids and ranks and ranks != list(range(1, len(ranks) + 1)):
                report["problems"].append("items[].rank 非连续名次序列 %s" % ranks[:8])

    # ---- C. 证据链 + claims 回证 + dedup_key 复算 ----
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
        # dedup_key 机械复算对照（归一化规则可复算）
        if not off("evidence"):
            recomputed = dedup_key_of(it)
            stored = it.get("dedup_key")
            ok = bool(recomputed) and stored == recomputed
            add("items[%d].dedup_recompute" % i, "dedup_key 按 doi>arxiv>title_norm 复算", True, ok)
            if not ok:
                report["problems"].append("%s dedup_key 与机械复算不符（存储 %r，复算 %r）" % (iid, stored, recomputed))
        if not off("evidence") and lab in ("push", "hold"):
            cl = claim_idx.get(iid) or claim_idx.get("items[%d]" % i) or []
            quote = norm(it.get("evidence_quote"))
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            if not q_backed:
                report["problems"].append("%s 的证据在 claims 证据链中无逐字回证" % iid)
            if isinstance(it.get("track_score"), (int, float)):
                sstr = str(round(float(it["track_score"]), 4))
                n_backed = any(sstr in norm(c.get("text")) or sstr in norm(e.get("quote"))
                               for c in cl for e in (c.get("evidence") or []))
                if not n_backed:
                    report["unbacked_numbers"].append(
                        {"item": "items[%d].track_score" % i, "value": sstr,
                         "reason": "push/hold 条目 track_score 未出现在任何 claim text/quote 中"})

    # ---- D. 登记完整性 ----
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab, ev = it.get("label"), it.get("event")
        if not off("registry") and lab == "hold":
            reg = [p for p in pending_reg if isinstance(p, dict) and str(p.get("item_id")) == iid]
            ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                 and all(str(p.get("needed_action") or "").strip() for p in reg)
            add("items[%d].hold_registered" % i, "hold ⇒ 登记入 pending_review", True, ok)
            if not ok:
                report["problems"].append("%s 标 hold 但未登记进 pending_review（缺 reason/needed_action）" % iid)
        if it.get("related_to"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and iid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
            add("items[%d].duplicate_recorded" % i, "related_to ⇒ conflicts 登记 merged/escalated", True, resolved)
            if not off("registry") and not resolved:
                report["problems"].append("%s 标记 related_to 但 conflicts 未登记 merged/escalated 处置" % iid)
            if not off("registry") and any(str(c.get("resolution")) == "escalated" for c in rec):
                in_reg = any(str(p.get("item_id")) == iid for p in pending_reg if isinstance(p, dict))
                if not in_reg:
                    report["problems"].append("%s 冲突升级(escalated)但未进入 pending_review" % iid)
        if not off("registry") and ev in ("version_update", "retraction") and iid not in chain_members:
            report["problems"].append("%s event=%s 但未登记进 version_chains（成员缺失）" % (iid, ev))

    if not off("registry") and items and not registry:
        report["problems"].append("source_registry 为空（每次增量须登记来源清单）")
    if not off("registry"):
        for i, it in enumerate(items):
            if not str(it.get("source_ref") or "").strip():
                report["problems"].append("%s 缺 source_ref（来源定位）"
                                          % (it.get("item_id") or "items[%d]" % i))

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [it for it in items if it.get("judged") is True]
    if cov:
        exp = {"total": len(items), "judged": len(judged),
               "push": sum(1 for it in items if it.get("label") == "push"),
               "hold": sum(1 for it in items if it.get("label") == "hold"),
               "exclude": sum(1 for it in items if it.get("label") == "exclude"),
               "new": sum(1 for it in items if it.get("event") == "new"),
               "version_update": sum(1 for it in items if it.get("event") == "version_update"),
               "duplicates_merged": sum(1 for it in items if it.get("event") == "duplicate"),
               "backfilled": sum(1 for it in items if it.get("event") == "backfill"),
               "retracted": sum(1 for it in items if it.get("event") == "retraction"),
               "out_of_window": sum(1 for it in items if it.get("event") == "out_of_window"),
               "in_window": sum(1 for it in items if it.get("in_window") is True)}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "tracked" and len(judged) != len(items):
        report["problems"].append("verdict=tracked 但存在未判定条目（judged=false）")
    if verdict == "partially_tracked" and len(judged) == len(items) and items:
        report["problems"].append("verdict=partially_tracked 但全部条目已判定（应为 tracked）")
    if verdict == "not_tracked" and judged:
        report["problems"].append("verdict=not_tracked 但存在已判定条目")
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
        ap.add_argument("--policy", default="/app/work/track_policy.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | consistency,order,evidence,registry 子集")
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
    pol = load_json(args.policy) if os.path.exists(args.policy) else None
    policy_state = "enforced" if isinstance(pol, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, policy_state=policy_state)
    report["gates"].append({"gate": "track_engine_output",
                            "state": "enforced" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("ranking") or {}).get("ordered_ids")
                            else "track_engine.py 未回写 ranking，下游不得宣称已核对"})
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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
