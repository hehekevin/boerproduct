#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（read-note-harvest，阅读批注与知识沉淀）。

对 result.json 做五组机械校验（与题面机检点逐项对应）：
  A. location  批注位置可回证：已判定批注必须有 locator 与 quote；quote 必须在
     claims 证据链中有逐字回证（空白归一化后子串匹配）。
  B. type      类型口径一致：ann_type 必须命中事前声明的 annotation_vocab 四类型
     （question/supplement/challenge/association）；vocab.declared_at 必填；
     anchor_kind 须在载体枚举内；confidence 枚举合法。
  C. card      卡片三要素完备：每张知识卡片 point/evidence/source 一个不缺；
     evidence 引用的 ann_id 必须真实存在，且卡片证据摘录必须逐字来自所引批注
     的 quote（防止卡片证据脱离原文）。
  D. theme     归纳有依据：每个主题 member_anns ≥2 且全部真实存在；basis 非空；
     归纳不得把不存在的批注连成一片（防关键词重合式过度连接）。
  E. toverify  待查证登记：needs_verify=true 的批注必须逐条登记进 to_verify
     （含 question 与 needed_action）；duplicate_of 未在 conflicts 登记处置的
     一并判违规。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
retrieval / theme_stats 归 index_search.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--vocab /app/work/type_vocab.json] [--out /app/work/verify_check.json] [--ablate all]
    --ablate none | all | location,type,card,theme,toverify 子集
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ANN_TYPES = ("question", "supplement", "challenge", "association")
ANCHORS = ("highlight", "underline", "margin", "handwritten", "webclip",
           "ocr", "text_selection", "unknown")
CONF = ("high", "medium", "low")
GROUPS = ("location", "type", "card", "theme", "toverify")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠；中文/英文标识按原文匹配）。"""
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


def vocab_types(vocab):
    """返回事前声明的合法类型 id 集合；未声明返回 None。"""
    t = (vocab or {}).get("types")
    if not isinstance(t, list) or not t:
        return None
    ids = []
    for e in t:
        tid = e.get("type_id") if isinstance(e, dict) else None
        if isinstance(tid, str) and tid.strip():
            ids.append(tid.strip())
    return ids or None


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", vocab_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in GROUPS:
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    cards = [c for c in (inner.get("cards") or []) if isinstance(c, dict)]
    themes = [t for t in (inner.get("themes") or []) if isinstance(t, dict)]
    to_verify = inner.get("to_verify") or []
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    conflicts = inner.get("conflicts") or []
    cov = inner.get("coverage") or {}
    vocab = inner.get("annotation_vocab") or {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "vocab_ledger", "state": vocab_state,
                            "note": "" if vocab_state == "enforced" else "/app/work/type_vocab.json 台账缺失，下游不得宣称已核对"})

    legal_types = vocab_types(vocab)

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, a in enumerate(anns):
        aid = a.get("ann_id") or "annotations[%d]" % i
        if a.get("confidence") is not None and a.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (aid, a.get("confidence")))
        if a.get("anchor_kind") is not None and a.get("anchor_kind") not in ANCHORS:
            report["problems"].append("%s anchor_kind 枚举非法: %r（须 %s…）"
                                      % (aid, a.get("anchor_kind"), ",".join(ANCHORS[:4])))

    # ---- A. 批注位置可回证 ----
    n_loc = 0
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, a in enumerate(anns):
        aid = str(a.get("ann_id") or i)
        if a.get("judged") is not True:
            continue
        if not off("location"):
            ok_loc = bool(str(a.get("locator") or "").strip())
            add("annotations[%d].locator_present" % i, "已判定 ⇒ locator 非空", True, ok_loc)
            if not ok_loc:
                report["problems"].append("%s 已判定但 locator 为空（批注位置缺失）" % aid)
                n_loc += 1
            quote = norm(a.get("quote"))
            cl = claim_idx.get(aid) or []
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            add("annotations[%d].quote_backed" % i, "quote 在 claims 逐字回证", True, q_backed)
            if not q_backed:
                report["problems"].append("%s 的 quote 在 claims 证据链中无逐字回证（锚点错位风险）" % aid)
                n_loc += 1

    # ---- B. 类型口径一致 ----
    n_type = 0
    if not off("type"):
        if not legal_types:
            report["problems"].append("annotation_vocab.types 未事前声明（四类型口径缺失）")
        if not str(vocab.get("declared_at") or "").strip():
            report["problems"].append("annotation_vocab.declared_at 为空（口径须在任何批注判定前声明）")
        for i, a in enumerate(anns):
            aid = str(a.get("ann_id") or i)
            at = a.get("ann_type")
            ok = at is None or (legal_types is not None and at in legal_types)
            add("annotations[%d].type_in_vocab" % i, "ann_type 命中事前口径", True, ok)
            if not ok:
                report["problems"].append("%s ann_type=%r 不在事前声明口径内（类型口径漂移）"
                                          % (aid, at))
                n_type += 1

    # ---- C. 卡片三要素完备 ----
    n_card = 0
    ann_quotes = {str(a.get("ann_id") or i): norm(a.get("quote")) for i, a in enumerate(anns)}
    for i, c in enumerate(cards):
        cid = str(c.get("card_id") or i)
        if not off("card"):
            ok_point = bool(str(c.get("point") or "").strip())
            ok_ev = bool(c.get("evidence"))
            ok_src = bool(str(c.get("source") or "").strip())
            add("cards[%d].three_elements" % i, "point/evidence/source 三要素", True,
                ok_point and ok_ev and ok_src)
            if not (ok_point and ok_ev and ok_src):
                report["problems"].append("%s 三要素不完备（point=%s evidence=%s source=%s）"
                                          % (cid, ok_point, ok_ev, ok_src))
                n_card += 1
            for j, ev in enumerate(c.get("evidence") or []):
                if not isinstance(ev, dict):
                    continue
                ref = str(ev.get("ann_id") or "")
                ok_ref = ref in ann_quotes
                add("cards[%d].evidence[%d].ann_exists" % (i, j), "引用批注真实存在", True, ok_ref)
                if not ok_ref:
                    report["problems"].append("%s evidence 引用不存在的批注: %s" % (cid, ref))
                    n_card += 1
                q = norm(ev.get("quote"))
                if q and ref in ann_quotes:
                    ok_q = q in ann_quotes[ref]
                    add("cards[%d].evidence[%d].quote_derived" % (i, j),
                        "卡片摘录逐字来自所引批注", True, ok_q)
                    if not ok_q:
                        report["problems"].append("%s evidence[%d] 摘录与批注 %s 原文不符（脱离原文）"
                                                  % (cid, j, ref))
                        n_card += 1

    # ---- D. 归纳有依据 ----
    n_theme = 0
    ann_ids = {str(a.get("ann_id") or i) for i, a in enumerate(anns)}
    for i, t in enumerate(themes):
        tid = str(t.get("theme_id") or i)
        if not off("theme"):
            members = [str(x) for x in (t.get("member_anns") or [])]
            ok_n = len(members) >= 2
            ok_exist = all(m in ann_ids for m in members)
            ok_basis = bool(str(t.get("basis") or "").strip())
            add("themes[%d].basis_grounded" % i, "member_anns≥2 且全部存在 + basis 非空",
                True, ok_n and ok_exist and ok_basis)
            if not ok_n or not ok_basis:
                report["problems"].append("%s 归纳依据不足（member_anns=%d 条，须≥2；basis=%s）"
                                          % (tid, len(members), ok_basis))
                n_theme += 1
            if not ok_exist:
                bad = [m for m in members if m not in ann_ids]
                report["problems"].append("%s member_anns 含不存在的批注: %s（过度连接）"
                                          % (tid, bad))
                n_theme += 1

    # ---- E. 待查证登记 ----
    n_tov = 0
    tv_ids = {str(p.get("related_anns") or "") for p in to_verify if isinstance(p, dict)}
    for p in to_verify:
        if isinstance(p, dict):
            for r in (p.get("related_anns") or []):
                tv_ids.add(str(r))
    for i, a in enumerate(anns):
        aid = str(a.get("ann_id") or i)
        if not off("toverify") and a.get("needs_verify") is True:
            ok_reg = aid in tv_ids
            ok_field = any(isinstance(p, dict) and aid in [str(x) for x in (p.get("related_anns") or [])]
                           and str(p.get("question") or "").strip()
                           and str(p.get("needed_action") or "").strip()
                           for p in to_verify)
            add("annotations[%d].toverify_registered" % i, "needs_verify ⇒ 登记 to_verify", True,
                ok_reg and ok_field)
            if not (ok_reg and ok_field):
                report["problems"].append("%s needs_verify=true 但未登记进 to_verify（缺 question/needed_action）" % aid)
                n_tov += 1
        if a.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and aid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
            add("annotations[%d].conflict_recorded" % i, "duplicate_of ⇒ conflicts 登记", True, resolved)
            if not off("toverify") and not resolved:
                report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 merged/escalated 处置" % aid)
                n_tov += 1

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [a for a in anns if a.get("judged") is True]
    by_type = {}
    for a in anns:
        at = a.get("ann_type")
        if at:
            by_type[at] = by_type.get(at, 0) + 1
    if cov:
        exp = {"total_annotations": len(anns), "judged": len(judged),
               "cards_total": len(cards), "themes_total": len(themes),
               "to_verify_total": len(to_verify)}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "extracted" and len(judged) != len(anns):
        report["problems"].append("verdict=extracted 但存在未判定批注（judged=false）")
    if verdict == "partially_extracted" and anns and len(judged) == len(anns):
        report["problems"].append("verdict=partially_extracted 但全部批注已判定（应为 extracted）")
    if verdict == "not_extracted" and judged:
        report["problems"].append("verdict=not_extracted 但存在已判定批注")
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

    counts = {"location": n_loc, "type": n_type, "card": n_card,
              "theme": n_theme, "toverify": n_tov}
    if any(counts.values()):
        report["problems"].append("分组违规计数: %s" % counts)
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--vocab", default="/app/work/type_vocab.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | location,type,card,theme,toverify 子集")
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
    vb = load_json(args.vocab) if os.path.exists(args.vocab) else None
    vocab_state = "enforced" if isinstance(vb, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, vocab_state=vocab_state)
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
