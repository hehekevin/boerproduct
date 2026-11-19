#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_extractor.py — 论点—论据映射（结构诊断创新点）

从 manuscript.json 逐句抽取「论断句」与其证据标记（数值/统计量/引用[n]/图表引用），
输出 claim_evidence_map.jsonl：每条论断标注证据在同句/同段/缺失，供 structure_check
的论证链检测复用，也作为 result.json 的 fact_source_mapping 主表。
注意：判定一律用正则，不用 str.isalpha()（对汉字恒真，会误判）。
退出码恒 0。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog

CLAIM_RE = re.compile(
    r"(本文|本研究|我们|作者)[^。；！？]{0,30}(提出|构建|设计|实现|证明|证实|发现|表明|验证)"
    r"|((提出|构建|设计)了?[^。；！？]{2,24}(方法|模型|框架|算法|体系|方案))"
    r"|(结果表明|实验表明|结果显示|数据表明|分析表明|由此可见|综上|这说明|证明了|证实了|表明该)")
EVID_NUM = re.compile(r"\d+(?:\.\d+)?%|n\s*=\s*\d+|p\s*[<=]\s*\d*\.\d+|\d+(?:\.\d+)?\s*(?:倍|个|条|名|次|只|例|份|组)")
EVID_CITE = re.compile(r"\[\d+(?:[,，、\-]\s*\d+)*\]|文献\s*\[?\d+\]?")
EVID_FIG = re.compile(r"图\s*\d+|表\s*\d+|figure\s*\d+|table\s*\d+", re.IGNORECASE)
SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])")


def sentences(para):
    return [s.strip() for s in SENT_SPLIT.split(para) if s.strip()]


def evidence_of(sent):
    marks = []
    if EVID_NUM.search(sent):
        marks.append("number")
    if EVID_CITE.search(sent):
        marks.append("citation")
    if EVID_FIG.search(sent):
        marks.append("figure")
    return marks


def extract(manuscript):
    rows, stats = [], {"claims_total": 0, "same_sentence": 0, "same_paragraph": 0, "none": 0}
    for sec in manuscript.get("sections", []):
        for pi, para in enumerate(sec.get("paragraphs", []), 1):
            sents = sentences(para)
            for si, sent in enumerate(sents, 1):
                if not CLAIM_RE.search(sent):
                    continue
                marks = evidence_of(sent)
                if marks:
                    support = "same_sentence"
                elif any(evidence_of(s2) for s2 in sents):
                    support = "same_paragraph"
                else:
                    support = "none"
                stats["claims_total"] += 1
                stats[support] += 1
                rows.append({
                    "claim_id": "C%03d" % (len(rows) + 1),
                    "section": sec["heading"], "paragraph": pi, "sentence": si,
                    "quote": sent[:80],
                    "claim_markers": sorted(set(m.group(0) for m in CLAIM_RE.finditer(sent)))[:4],
                    "evidence_markers": marks,
                    "support": support,
                })
    return rows, stats


def main():
    t0 = __import__("time").time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", default="/app/work/manuscript.json")
    ap.add_argument("--out", default="/app/work/claim_evidence_map.jsonl")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误"}))
        return 0
    rows, stats = [], {"claims_total": 0, "same_sentence": 0, "same_paragraph": 0, "none": 0}
    try:
        ms = json.load(open(args.manuscript, encoding="utf-8"))
        rows, stats = extract(ms)
    except Exception as e:
        stats["error"] = str(e)
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        written = True
    except Exception as e:
        stats["write_error"] = str(e)
        written = False
    print(json.dumps({"ok": True, "written": written, "stats": stats}, ensure_ascii=False))
    _rlog.log_call("claim_extractor", argv=sys.argv[1:], seconds=__import__("time").time() - t0,
                   extra=stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
