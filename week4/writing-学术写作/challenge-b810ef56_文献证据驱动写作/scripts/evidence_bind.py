#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_bind.py — 论断—来源关联：为每条论断匹配支撑来源与逐字证据

输入 claims.jsonl（claim_split 产出）与来源材料目录 /app/work/sources：
  · M01.txt…  来源全文，文件内建议用 [SRC:M01:p3|line12] 形式标注定位锚点
  · manifest.jsonl（可选）每行 {"id":"M01","type":"原始研究|综述|指南|预印本|…"}
输出 evidence_table.jsonl：每条论断一行
  {"claim_id","source_id","locator","quote","source_type","support_scope","match"}

匹配策略（纯标准库，机械可复核）：
  1) 数字优先：论断中的数值与来源句中数值完全一致者候选；
  2) 字面覆盖：候选句与论断的最长公共子串长度排序；
  3) quote 必须是来源原文的逐字子串（去空白比对），不得改写。
无法找到证据时 match="none"，不编造——留待 strength_gate / verify_check 判 FAIL。
退出码恒为 0。
"""
import argparse
import json
import os
import re
import sys

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
LOC_RE = re.compile(r"\[SRC:([A-Za-z0-9_\-]+):(p\d+|line\d+|par\d+)[^\]]*\]")
TYPE_DEFAULT = {"综述": "review", "指南": "guideline", "预印本": "preprint"}



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


def read_sources(src_dir):
    """读取来源目录，返回 [{id, type, corpus(去空白), raw}]。校验式存在性检查。"""
    sources = []
    if not src_dir or not os.path.isdir(src_dir):
        return sources
    manifest = {m.get("id"): m.get("type") for m in load_jsonl(
        os.path.join(src_dir, "manifest.jsonl")) if isinstance(m, dict)}
    for fn in sorted(os.listdir(src_dir)):
        if not fn.lower().endswith((".txt", ".md", ".jsonl")) or fn == "manifest.jsonl":
            continue
        sid = os.path.splitext(fn)[0]
        try:
            raw = open(os.path.join(src_dir, fn), encoding="utf-8",
                       errors="ignore").read()
        except Exception:
            continue
        sources.append({"id": sid, "type": manifest.get(sid) or "原始研究",
                        "raw": raw, "corpus": norm(raw)})
    return sources


def sentences_of(raw):
    parts = re.split(r"[。；！？\n]", raw)
    return [p.strip() for p in parts if len(norm(p)) >= 8]


def locator_of(sid, raw, pos):
    """在句首位置往前找最近的 [SRC:...] 锚点；找不到给文件级定位。"""
    best = None
    for m in LOC_RE.finditer(raw):
        if m.start() <= pos:
            best = m
        else:
            break
    if best:
        return "%s:%s" % (best.group(1), best.group(2))
    return "%s:p?" % sid


def lcs_len(a, b):
    # 短文本最长公共子串（论断≤300字、句长有限，O(n*m) 可接受）
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b):
            if ca == cb:
                cur[j + 1] = prev[j] + 1
                if cur[j + 1] > best:
                    best = cur[j + 1]
        prev = cur
    return best


def bind_one(claim, sources):
    nums = set(claim.get("numbers") or [])
    ctext = norm(claim.get("text"))
    best = None  # (score, source, sentence, locator)
    for src in sources:
        for sent in sentences_of(src["raw"]):
            pos = src["raw"].find(sent)
            snum = set(NUM_RE.findall(sent))
            score = lcs_len(ctext, norm(sent))
            if nums and snum:
                score += 12 * len(nums & snum)  # 数字一致强加权
            if nums and not snum:
                score -= 4
            if best is None or score > best[0]:
                best = (score, src, sent, locator_of(src["id"], src["raw"], pos))
    if not best or best[0] < 8:
        return {"claim_id": claim.get("claim_id"), "source_id": None,
                "locator": None, "quote": None,
                "source_type": None, "support_scope": None, "match": "none"}
    score, src, sent, loc = best
    q = norm(sent)
    ok_quote = q in src["corpus"]  # 逐字子串校验（防改写）
    return {"claim_id": claim.get("claim_id"), "source_id": src["id"],
            "locator": loc, "quote": sent,
            "source_type": src["type"],
            "support_scope": "partial" if lcs_len(ctext, q) < max(10, len(ctext) // 2) else "full",
            "match": "exact" if ok_quote else "none"}


def main():
    ap = _ArgParser()
    ap.add_argument("--claims", default="/app/work/claims.jsonl")
    ap.add_argument("--sources", default="/app/work/sources")
    ap.add_argument("--out", default="/app/work/evidence_table.jsonl")
    args = ap.parse_args()

    try:
        claims = load_jsonl(args.claims)
        sources = read_sources(args.sources)
        if not claims:
            print(json.dumps({"ok": False, "bound": 0,
                              "note": "claims 为空或文件缺失，跳过绑定"}, ensure_ascii=False))
            return 0
        rows = [bind_one(c, sources) for c in claims]
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        bound = sum(1 for r in rows if r["match"] == "exact")
        print(json.dumps({"ok": True, "claims": len(rows), "bound_exact": bound,
                          "bound_none": sum(1 for r in rows if r["match"] == "none"),
                          "sources": [s["id"] for s in sources],
                          "out": args.out}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "绑定失败不阻断，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
