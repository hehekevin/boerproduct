#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_split.py — 论断切分：把成稿拆成可判定的论断单元（文献证据驱动写作）

从成稿 markdown 中切出逐条论断（一个可判定单元一条），分类并预标注：
  type: numeric（含数值/统计量）/ citation（含 [n] 或 (作者, 年份)）/ factual / interpretive
  hedged: 是否已有限定语（可能/提示/或许/一般认为…）
  strong_wording: 是否用了强断言词（证实/证明/显著/确立/首次…）
  universal: 是否含全称词（所有/总是/必然/唯一…）——过度概括风险

切分注意：小数点、编号 [1]、年份 "2021." 不作为句界；中文按 。；！？ 切。
汉字陷阱：不用 str.isalpha 判词（汉字 isalpha 为 True 会误判），统一用 ASCII 正则。
退出码恒为 0：解析失败也打印说明后正常退出。
"""
import argparse
import json
import os
import re
import sys

# 句界：中文句号/分号/叹号/问号后必切（中文无空格）；英文句号后跟空白才切（防小数/缩写）
SENT_SPLIT = re.compile(r"(?<=[。；！？])(?=.)|(?<=[^0-9]\.)(?=\s)")
STRONG_WORDS = ["证实", "证明", "确立", "首次发现", "显著", "明确表明", "毫无疑问", "彻底"]
HEDGE_WORDS = ["可能", "或许", "提示", "似乎", "倾向于", "一般认为", "在…条件下",
               "一定程度上", "有待", "推测", "approximately", "suggest", "may"]
UNIVERSAL_WORDS = ["所有", "总是", "必然", "唯一", "从未", "永远", "all ", "always", "never"]
CITATION_RE = re.compile(r"\[\d+(?:[,，\-]\d+)*\]|\([^()]{0,40}(?:19|20)\d{2}[a-z]?\)")
# 定位标记（M01:p3 / （M01:p3|line12） / [SRC:...]）不是论断内容：分类与取数前剥离
LOCATOR_MARK_RE = re.compile(r"[（(]SRC:[^（）)]*[）)]|[（(]M[0-9]{1,4}:p[0-9]+[^（）)]*[）)]|\[SRC:[^\]]*\]")
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
SECTION_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.M)



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def classify(text):
    t = LOCATOR_MARK_RE.sub("", str(text or ""))
    typ = "factual"
    if NUM_RE.search(t):
        typ = "numeric"
    if CITATION_RE.search(t):
        typ = "citation" if typ != "numeric" else "numeric"
    if re.search(r"(相关|关联|伴随|提示|可能机制|association|correlat)", t):
        typ = "interpretive" if typ == "factual" else typ
    return typ


def split_claims(md_text):
    claims, cid = [], 0
    section = None
    # 记录每个句子所在章节标题
    spans = []
    for m in SECTION_RE.finditer(md_text):
        spans.append((m.start(), m.group(1)))
    for raw in re.split(r"\n+", md_text):
        pass
    pos = 0
    lines = md_text.split("\n")
    for line in lines:
        hm = re.match(r"^#{1,6}\s*(.+?)\s*$", line)
        if hm:
            section = hm.group(1)
            continue
        if not line.strip():
            continue
        for sent in SENT_SPLIT.split(line):
            s = sent.strip(" \t*->")
            if len(s) < 6:  # 过短（标题残留/连接词）不成论断
                continue
            cid += 1
            core = LOCATOR_MARK_RE.sub("", s)
            cit = CITATION_RE.search(s)
            claims.append({
                "claim_id": "C%02d" % cid,
                "section": section,
                "text": s[:300],
                "type": classify(s),
                "hedged": any(w in core for w in HEDGE_WORDS),
                "strong_wording": any(w in core for w in STRONG_WORDS),
                "universal": any(w in core.lower() for w in UNIVERSAL_WORDS),
                "numbers": NUM_RE.findall(core)[:8],
                "citation": cit.group(0) if cit else None,
            })
    return claims


def main():
    ap = _ArgParser()
    ap.add_argument("--draft", default="/app/output/draft.md")
    ap.add_argument("--out", default="/app/work/claims.jsonl")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    try:
        if args.selftest:
            ok = split_claims("本研究中药物A显著降低血压（p<0.05）[1]。可能与机制相关。")
            good = ok and ok[0]["type"] == "numeric" and ok[0]["strong_wording"]
            print(json.dumps({"selftest": "PASS" if good else "FAIL",
                              "n": len(ok)}, ensure_ascii=False))
            return 0
        if not os.path.exists(args.draft):
            out = {"ok": False, "claims": 0,
                   "note": "draft 不存在，跳过切分；请先由模型产出成稿"}
            print(json.dumps(out, ensure_ascii=False))
            return 0
        text = open(args.draft, encoding="utf-8", errors="ignore").read()
        claims = split_claims(text)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for c in claims:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        by_type = {}
        for c in claims:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        print(json.dumps({"ok": True, "claims_total": len(claims),
                          "by_type": by_type,
                          "strong_wording": sum(1 for c in claims if c["strong_wording"]),
                          "unhedged_interpretive":
                              sum(1 for c in claims
                                  if c["type"] == "interpretive" and not c["hedged"]),
                          "out": args.out}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "切分失败不阻断，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
