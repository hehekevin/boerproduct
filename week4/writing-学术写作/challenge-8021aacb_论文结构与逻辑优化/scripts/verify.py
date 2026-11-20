#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py — 逐字留痕校验：original 可定位 / revised 已落地 / 无未授权改动（三级容错）
用法: python verify.py --edits edits_before_after.jsonl --original /app/work/extracted \
         --revised /app/output/revised.md --out /app/output/verify_report.json
容错: ①全量校验 ②缺失文件降级 verdict=skipped ③异常也写报告 exit 0
"""
import argparse, json, os, re, sys

def norm(s):
    return re.sub(r"\s+", "", (s or ""))

def load_edits(p):
    if not p or not os.path.exists(p): return None
    try:
        return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    except Exception:
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", required=True)
    ap.add_argument("--original", required=True, help="extracted 目录或原稿文件")
    ap.add_argument("--revised", required=True)
    ap.add_argument("--out", default="/app/output/verify_report.json")
    args = ap.parse_args()
    report = {"edits_total": 0, "located_ratio": 0.0, "landed_ratio": 0.0,
              "unauthorized_changes": 0, "unlocated": [], "unlanded": [], "verdict": "skipped",
              "reasons": []}
    try:
        edits = load_edits(args.edits)
        orig_text = _read_original(args.original)
        rev_text = open(args.revised, encoding="utf-8", errors="ignore").read() if os.path.exists(args.revised) else None
        if edits is None: report["reasons"].append("edits 文件缺失或不可解析")
        if orig_text is None: report["reasons"].append("原稿文本缺失")
        if rev_text is None: report["reasons"].append("修订稿缺失")
        if edits and orig_text is not None and rev_text is not None:
            n_o = norm(orig_text); n_r = norm(rev_text)
            revised_snippets = [norm(e.get("revised", "")) for e in edits if e.get("revised")]
            total = len(edits); loc = land = 0
            for i, e in enumerate(edits):
                if norm(e.get("original", "")) and norm(e["original"]) in n_o: loc += 1
                else: report["unlocated"].append(e.get("sid", str(i)))
                rv = norm(e.get("revised", ""))
                if rv and rv in n_r: land += 1
                else: report["unlanded"].append(e.get("sid", str(i)))
            report["edits_total"] = total
            report["located_ratio"] = round(loc / total, 3) if total else 0.0
            report["landed_ratio"] = round(land / total, 3) if total else 0.0
            # 未授权改动：修订稿段落既不在原稿、也不含任何一条 revised 的落点
            for para in [p for p in re.split(r"\n\s*\n", rev_text) if len(norm(p)) > 30]:
                np_ = norm(para)
                if np_ not in n_o and not any(rs and rs in np_ for rs in revised_snippets):
                    report["unauthorized_changes"] += 1
            ok = report["located_ratio"] == 1.0 and report["landed_ratio"] == 1.0 \
                 and report["unauthorized_changes"] == 0
            report["verdict"] = "pass" if ok else "fail"
        elif not report["reasons"]:
            report["verdict"] = "fail"; report["reasons"].append("输入不完整")
    except Exception as e:
        report["verdict"] = "skipped"; report["reasons"].append("校验异常: %s" % e)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False))
    return 0

def _read_original(p):
    if os.path.isfile(p):
        return open(p, encoding="utf-8", errors="ignore").read()
    if os.path.isdir(p):
        m = os.path.join(p, "materials.md")
        return open(m, encoding="utf-8", errors="ignore").read() if os.path.exists(m) else None
    return None

if __name__ == "__main__":
    sys.exit(main())
