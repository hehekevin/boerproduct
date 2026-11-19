#!/usr/bin/env python3
"""draft_bind.py — 段落-来源绑定与引用逐字回证校验器（lit-review-bind）。

对综述草稿做两组机械校验（对应题面机检点"段落-来源绑定、引用逐字回证"）：
  A. 段落绑定：每个非空段落必须绑定 ≥1 个来源（source_ids）；source_ids 必须是
     输入文献集中真实存在的 paper_id；段落引用的 claim_ids 必须在 claims[] 存在。
  B. 逐字回证：每条 claim 的 evidence[].quote 必须逐字（空白归一化后子串匹配）
     出现在该来源文献在 case.json 中的实际正文/摘要里；case 未提供正文的文献以
     evidence_table 摘录为回证底本并登记 unverifiable_text；对不上的列入
     unbacked_quotes 并判 FAIL（编造引用在此被机械拦截）。

analyze_binding(res, case, ablate) 为纯函数（不写盘），供 verify_check/gain_probe 复用；
CLI 形式把报告落盘并可回写顶层 quote_audit（键归属：本脚本独占 quote_audit）。
退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

PAPER_KEYS = ("papers", "candidates", "items", "records", "documents",
              "literature", "references", "sources", "search_results", "results")
TEXT_KEYS = ("abstract", "text", "content", "excerpt", "fulltext", "summary")


def norm(s):
    """空白归一化（子串匹配用；不做大小写折叠以防语义误伤）。"""
    return re.sub(r"\s+", "", str(s or ""))


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def extract_texts(case):
    """paper_id -> 实际正文/摘要文本（供逐字回证）。"""
    out = {}
    if not isinstance(case, dict):
        return out
    for key in PAPER_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                pid = None
                if isinstance(e, dict):
                    for k in ("paper_id", "item_id", "id", "doc_id", "ref_id", "uid"):
                        if e.get(k):
                            pid = str(e[k])
                            break
                    txt = ""
                    for k in TEXT_KEYS:
                        if e.get(k) and str(e[k]).strip():
                            txt = str(e[k])
                            break
                elif isinstance(e, str):
                    pid, txt = None, e
                if pid:
                    out[pid] = txt
            break
    return out


def analyze_binding(res, case, ablate="none"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [],
              "unbacked_quotes": [], "unverifiable_text": [],
              "disabled_checks": [], "ablate": ablate}
    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    if off("binding"):
        report["disabled_checks"].append("binding")
    if off("quote"):
        report["disabled_checks"].append("quote")

    inner = (res or {}).get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        return report

    texts = extract_texts(case)
    all_ids = {str(it.get("paper_id")) for it in (inner.get("items") or [])
               if isinstance(it, dict) and it.get("paper_id")}
    all_ids |= set(texts.keys())
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    claim_ids = {str(c.get("claim_id")) for c in claims}
    evid_table = [e for e in (inner.get("evidence_table") or []) if isinstance(e, dict)]

    # ---- A. 段落-来源绑定 ----
    outline = inner.get("outline") or {}
    for si, s in enumerate(outline.get("sections") or []):
        if not isinstance(s, dict):
            continue
        for pi, p in enumerate(s.get("paragraphs") or []):
            if not isinstance(p, dict):
                continue
            ref = "sections[%d].paragraphs[%d]" % (si, pi)
            has_text = bool(str(p.get("text") or "").strip())
            sids = [str(x) for x in (p.get("source_ids") or [])]
            bound = bool(sids)
            report["self_check"].append({"item": "%s.source_bound" % ref,
                                         "template_value": "非空段落 ⇒ source_ids 非空",
                                         "applied": not off("binding"), "match": bound})
            if off("binding"):
                continue
            if has_text and not bound:
                report["problems"].append("%s 段落有正文但未绑定任何来源（source_ids 空）" % ref)
            for sid in sids:
                if sid not in all_ids:
                    report["problems"].append("%s 绑定的来源 %s 不在输入文献集中（来源越界）" % (ref, sid))
            for cid in (p.get("claim_ids") or []):
                if str(cid) not in claim_ids:
                    report["problems"].append("%s 引用的 claim %s 不在 claims[]（断链）" % (ref, cid))

    # ---- B. 引用逐字回证 ----
    evid_quote_by_paper = {}
    for e in evid_table:
        pid = str(e.get("paper_id") or "")
        if pid:
            evid_quote_by_paper.setdefault(pid, []).append(str(e.get("quote") or ""))
    for ci, c in enumerate(claims):
        cid = str(c.get("claim_id") or "claims[%d]" % ci)
        sids = [str(x) for x in (c.get("source_ids") or [])]
        if off("quote"):
            continue
        if not sids:
            report["problems"].append("%s 无任何来源（无来源论断）" % cid)
            continue
        for sid in sids:
            if sid not in all_ids:
                report["problems"].append("%s 的来源 %s 不在输入文献集中" % (cid, sid))
        evs = [e for e in (c.get("evidence") or []) if isinstance(e, dict)]
        if not evs:
            report["problems"].append("%s 无 evidence 回证条目" % cid)
            continue
        for e in evs:
            pid = str(e.get("paragraph_id") or "")
            quote = norm(e.get("quote"))
            base = norm(texts.get(pid, ""))
            if not base:
                alt = [norm(q) for q in evid_quote_by_paper.get(pid, []) if norm(q)]
                if alt:
                    base = alt[0]
                    if pid not in [u.get("paper_id") for u in report["unverifiable_text"]]:
                        report["unverifiable_text"].append(
                            {"paper_id": pid, "reason": "case.json 未提供正文，以 evidence_table 摘录为回证底本"})
                else:
                    report["problems"].append("%s 回证对象 %s 无可用底本（正文与 evidence_table 均为空）" % (cid, pid))
                    continue
            backed = bool(quote) and quote in base
            if not backed:
                report["unbacked_quotes"].append(
                    {"claim": cid, "paragraph_id": pid,
                     "quote": str(e.get("quote") or "")[:80],
                     "reason": "quote 未在来源正文/摘要中逐字命中（疑似编造引用）"})
        report["self_check"].append({"item": "%s.quote_backed" % cid,
                                     "template_value": "evidence.quote ⇒ 来源正文逐字命中",
                                     "applied": True,
                                     "match": all(
                                         bool(norm(e.get("quote"))) and
                                         norm(e.get("quote")) in norm(texts.get(str(e.get("paragraph_id")), ""))
                                         for e in evs)})

    if report["unbacked_quotes"]:
        report["problems"].append("存在 %d 条未逐字回证的引用（见 unbacked_quotes）"
                                  % len(report["unbacked_quotes"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 quote_audit 回写 result.json 顶层（键归属本脚本）")
        ap.add_argument("--ablate", default="none", help="none | all | binding,quote 子集")
        args = ap.parse_args()
    except Exception as e:
        print("[draft_bind] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    case = load_json(args.case)
    if not isinstance(res, dict):
        print("[draft_bind] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        save = {"verdict": "FAIL", "problems": ["result.json 不可解析"], "self_check": [],
                "unbacked_quotes": [], "unverifiable_text": [], "disabled_checks": [],
                "ablate": args.ablate}
        d = os.path.dirname(args.out) if args.out else ""
        if d:
            os.makedirs(d, exist_ok=True)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(save, f, ensure_ascii=False, indent=1)
        return 0

    report = analyze_binding(res, case if isinstance(case, dict) else {}, ablate=args.ablate)
    if args.out:
        try:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[draft_bind] 报告落盘失败: %s" % e)
    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["quote_audit"] = {k: report[k] for k in
                                      ("verdict", "unbacked_quotes", "unverifiable_text",
                                       "disabled_checks")}
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[draft_bind] 回写 quote_audit 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[draft_bind] PASS（ablate=%s，检查项 %d 条，unbacked_quotes=0）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[draft_bind] FAIL（%d 处，不中断交付；ablate=%s）:" % (len(report["problems"]), args.ablate))
        for p in report["problems"][:20]:
            print("  - %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[draft_bind] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
