#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_check.py — 统一校验器（复得现）：论断—证据—成稿逐条机检

对每条论断做 5 项机械检查（同一套函数被 CLI 与 gain_probe 消融双臂共用，
保证「同一校验器对两臂各跑一遍」的公平性）：
  bound         证据表中有该论断行且 source_id+locator 非空
  verbatim      quote 去空白后逐字包含于来源语料（防改写/防编造）
  locator       定位格式合法 [SRC:]ID:pXX|lineXX|parXX（p? 视为未定位，FAIL）
  in_draft      论断原文确实出现在成稿中（防清单与成稿两张皮）
  wording       措辞与证据等级相称（复用 strength_gate 规则，无 flags 为过）
输出 verify_report.json：逐行 {check,item,match,gate} + 汇总 + verdict。
verdict 是机器判定：FAIL 数随两臂差异变化，供增益对照；退出码恒为 0。
"""
import argparse
import json
import os
import re
import sys

STRONG_WORDS = ["证实", "证明", "确立", "首次发现", "显著", "明确表明", "毫无疑问"]
CAUSAL_WORDS = ["导致", "因此", "由于", "使得", "造成", "归因于", "证明其"]
UNIVERSAL_WORDS = ["所有", "总是", "必然", "唯一", "从未", "永远"]
HEDGE_WORDS = ["可能", "或许", "提示", "似乎", "倾向于", "推测"]
LOC_OK = re.compile(r"^[A-Za-z0-9_\-]+:(p\d+|line\d+|par\d+)$")
TYPE_GRADE = {"指南": "A", "共识": "A", "原始研究": "B", "综述": "C",
              "预印本": "D", "review": "C", "guideline": "A", "preprint": "D"}



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def load_jsonl(p):
    rows = []
    if p and os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except Exception:
            pass
    return rows


def wording_flags(text, grade, ctype):
    flags = []
    strong = any(w in text for w in STRONG_WORDS)
    hedged = any(w in text for w in HEDGE_WORDS)
    if strong and grade in ("C", "D"):
        flags.append("overclaim")
    if any(w in text for w in ["相关", "关联", "伴随"]) and \
            any(w in text for w in CAUSAL_WORDS):
        flags.append("causal_overreach")
    if any(w in text for w in UNIVERSAL_WORDS):
        flags.append("overgeneralization")
    if grade == "D" and not hedged:
        flags.append("needs_hedge")
    if ctype == "interpretive" and not hedged:
        flags.append("needs_hedge")
    return flags


def validate(claims, ev_rows, sources, draft_text, arm_tag="arm"):
    """统一校验入口：claims=list[dict], ev_rows=list[dict],
    sources=list[{id,corpus}], draft_text=str。返回 (rows, summary)。"""
    corpus = {s.get("id"): norm(s.get("corpus") or s.get("raw")) for s in sources}
    evs = {r.get("claim_id"): r for r in ev_rows if isinstance(r, dict)}
    dnorm = norm(draft_text)
    rows, fail = [], 0
    for c in claims:
        cid = c.get("claim_id")
        text = str(c.get("text") or "")
        ev = evs.get(cid)
        bound = bool(ev and ev.get("source_id") and ev.get("locator"))
        quote = norm((ev or {}).get("quote"))
        verbatim = bool(quote) and any(quote in c for c in corpus.values())
        loc = str((ev or {}).get("locator") or "")
        loc_ok = bool(loc) and bool(LOC_OK.match(loc))
        grade = TYPE_GRADE.get(str((ev or {}).get("source_type") or ""), "D") \
            if (ev and ev.get("match") == "exact") else "D"
        wflags = wording_flags(text, grade, c.get("type"))
        in_draft = dnorm and norm(text) in dnorm
        for check, ok in (("bound", bound), ("verbatim", verbatim),
                          ("locator_format", loc_ok), ("in_draft", in_draft),
                          ("wording", not wflags)):
            if not ok:
                fail += 1
            rows.append({"check": check, "item": cid, "match": bool(ok),
                         "gate": "enforced", "arm": arm_tag})
    summary = {
        "arm": arm_tag,
        "claims_total": len(claims),
        "checks_total": len(rows),
        "fail_count": fail,
        "pass_rate": round(1 - fail / len(rows), 3) if rows else None,
        "verdict": "PASS" if fail == 0 and claims else "FAIL",
        "fail_by_check": {k: sum(1 for r in rows if r["check"] == k and not r["match"])
                          for k in ("bound", "verbatim", "locator_format",
                                    "in_draft", "wording")},
    }
    return rows, summary


def main():
    ap = _ArgParser()
    ap.add_argument("--claims", default="/app/work/claims.jsonl")
    ap.add_argument("--evidence-table", default="/app/work/evidence_table.jsonl")
    ap.add_argument("--sources", default="/app/work/sources")
    ap.add_argument("--draft", default="/app/output/draft.md")
    ap.add_argument("--out", default="/app/output/verify_report.json")
    ap.add_argument("--arm-tag", default="skill")
    args = ap.parse_args()

    try:
        claims = load_jsonl(args.claims)
        ev_rows = load_jsonl(args.evidence_table)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from evidence_bind import read_sources
        sources = read_sources(args.sources)
        draft = ""
        if args.draft and os.path.exists(args.draft):
            draft = open(args.draft, encoding="utf-8", errors="ignore").read()
        rows, summary = validate(claims, ev_rows, sources, draft, args.arm_tag)
        report = {"ok": True, "summary": summary, "results": rows}
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"ok": True, "verdict": summary["verdict"],
                          "fail_count": summary["fail_count"],
                          "fail_by_check": summary["fail_by_check"],
                          "out": args.out}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "校验失败照实记录，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
