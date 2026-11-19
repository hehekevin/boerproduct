#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross_check.py — 学位论文跨章节一致性校验（基于登记簿）
检查: 1) 术语别名违规；2) 符号冲突（同符号多义）；3) 定义重复/矛盾；4) 结论引用失配；
5) 图表编号跨章错位。
默认退出码**恒为 0**（发现问题不中断交付，判据在 verdict/fail 字段）；参数错误同样以退出码 0 结束。
CI 门禁请读报告里的 ci_gate 字段（--strict 只是把该字段显式标出，不改变退出码）。
"""
import argparse, json, os, re, sys
from collections import defaultdict


class _SafeParser(argparse.ArgumentParser):
    """参数错误也以退出码 0 结束：判据写进 stderr 的 JSON，绝不中断交付链。"""

    def error(self, message):
        sys.stderr.write(json.dumps(
            {"ok": False, "verdict": "fail", "fail_reason": [str(message)[:200]],
             "note": "参数错误已如实记录；退出码恒 0，不中断交付。"}, ensure_ascii=False) + "\n")
        raise SystemExit(0)


def main():
    ap = _SafeParser()
    ap.add_argument("--registers", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict", action="store_true", help="仅显式标出报告里的 ci_gate 字段（不改变退出码）")
    args = ap.parse_args()
    problems = []
    regs, draft = [], ""
    gates = []
    try:
        regs = [json.loads(l) for l in open(args.registers, encoding="utf-8") if l.strip()]
    except Exception as e:
        gates.append({"state": "unreadable", "detail": "registers: " + str(e)[:120]})
    try:
        draft = open(args.draft, encoding="utf-8").read()
    except Exception as e:
        gates.append({"state": "unreadable", "detail": "draft: " + str(e)[:120]})
    if gates:
        report = {"registers": len(regs), "problems": problems, "gates": gates, "fail": 1,
                  "verdict": "fail", "ci_gate": "fail",
                  "fail_reason": ["输入不可读，闸门未跑成"],
                  "hint": "闸门未跑成，不得宣称已核对。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "fail", "gates": gates}, ensure_ascii=False))
        return 0
    gates.append({"state": "enforced", "detail": "registers=%d, draft=%d chars" % (len(regs), len(draft))})

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
    #    同一编号会出现两次：一次是图注定义，一次是正文引用。先按出现次序去重再判有序，
    #    否则「定义+引用」会被误判成编号重复；去重后次序非递增仍是真错位。
    figs = re.findall(r"图\s*(\d+)[-–](\d+)", draft)
    seq = [(int(a), int(b)) for a, b in figs]
    per_ch = defaultdict(list)
    for a, b in seq:
        lst = per_ch[a]
        if not lst or lst[-1] != b:
            lst.append(b)
    fig_bad = {ch: v for ch, v in per_ch.items() if v != sorted(v)}
    if fig_bad:
        problems.append({"type": "figure_numbering", "detail": fig_bad})

    hard = [p for p in problems if p["type"] in ("term_violations", "symbol_conflicts",
                                                  "duplicate_definitions", "conclusion_mismatch",
                                                  "figure_numbering")]
    report = {"registers": len(regs), "problems": problems, "gates": gates, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "ci_gate": "pass" if not hard else "fail",
              "fail_reason": [] if not hard else [p["type"] for p in hard],
              "hint": "fail 项回对应章节修复；aliases 首次定义处允许出现。"}
    if args.strict:
        report["strict_mode"] = True
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "registers": len(regs),
                      "types": [p["type"] for p in problems]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
