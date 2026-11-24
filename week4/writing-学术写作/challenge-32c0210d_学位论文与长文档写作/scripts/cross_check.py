#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross_check.py — 学位论文跨章节一致性校验（基于登记簿）
检查: 1) 术语别名违规；2) 符号冲突（同符号多义）；3) 定义重复/矛盾；4) 结论引用失配；
5) 图表编号跨章错位。
"""
import argparse, json, os, re, sys
from collections import defaultdict

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registers", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    regs = [json.loads(l) for l in open(args.registers, encoding="utf-8") if l.strip()]
    draft = open(args.draft, encoding="utf-8").read()
    problems = []

    # 1) 术语别名违规：登记簿 canonical 应出现；aliases 出现于首次定义之后 → 违规
    term_viol = []
    for r in regs:
        if r.get("kind") != "term":
            continue
        canon = r.get("canonical") or r.get("key")
        if not canon:
            continue
        first = re.search(re.escape(canon), draft)
        for a in r.get("aliases") or []:
            for m in re.finditer(re.escape(a), draft):
                if first and m.start() < first.start():
                    continue
                ctx = draft[max(0, m.start() - len(canon) - 2):m.end() + 2]
                if canon in ctx:
                    continue  # "规范名（别名）"定义形式
                term_viol.append({"term": canon, "alias": a,
                                  "line": draft[:m.start()].count("\n") + 1})
    if term_viol:
        problems.append({"type": "term_violations", "count": len(term_viol), "detail": term_viol[:20]})

    # 2) 符号冲突：登记簿同 key 不同 canonical
    sym = defaultdict(set)
    for r in regs:
        if r.get("kind") == "symbol" and r.get("key") and r.get("canonical"):
            sym[r["key"]].add(r["canonical"])
    sym_conf = {k: sorted(v) for k, v in sym.items() if len(v) > 1}
    if sym_conf:
        problems.append({"type": "symbol_conflicts", "detail": sym_conf})

    # 3) 定义重复
    defs = [r for r in regs if r.get("kind") == "definition"]
    seen, dup = {}, []
    for r in defs:
        k = (r.get("key") or "").strip()
        if k in seen:
            dup.append({"key": k, "where": [seen[k], r.get("first_used")]})
        seen[k] = r.get("first_used")
    if dup:
        problems.append({"type": "duplicate_definitions", "detail": dup[:10]})

    # 4) 结论引用失配：正文引用 C\d+.\d+（如 结论3.2）需在登记簿 conclusions 中存在
    con_keys = {re.sub(r"\s", "", str(r.get("key") or r.get("canonical") or "")) for r in regs
                if r.get("kind") == "conclusion"}
    con_refs = set(re.findall(r"结论\s*(\d+(?:\.\d+)*)", draft)) | set(re.findall(r"C(\d+\.\d+)", draft))
    missing = [c for c in con_refs if c and c not in con_keys and ("结论" + c) not in con_keys]
    if con_refs and missing:
        problems.append({"type": "conclusion_mismatch", "missing": sorted(missing)[:20]})

    # 5) 图表编号跨章有序（图3-1 → 图3-2 → 图4-1）
    figs = re.findall(r"图\s*(\d+)[-–](\d+)", draft)
    seq = [(int(a), int(b)) for a, b in figs]
    per_ch = defaultdict(list)
    for a, b in seq:
        per_ch[a].append(b)
    fig_bad = {ch: v for ch, v in per_ch.items() if v != sorted(set(v))}
    if fig_bad:
        problems.append({"type": "figure_numbering", "detail": fig_bad})

    hard = [p for p in problems if p["type"] in ("term_violations", "symbol_conflicts",
                                                  "duplicate_definitions", "conclusion_mismatch",
                                                  "figure_numbering")]
    report = {"registers": len(regs), "problems": problems, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "hint": "fail 项回对应章节修复；aliases 首次定义处允许出现。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "registers": len(regs),
                      "types": [p["type"] for p in problems]}, ensure_ascii=False))
    return 1 if hard else 0

if __name__ == "__main__":
    sys.exit(main())
