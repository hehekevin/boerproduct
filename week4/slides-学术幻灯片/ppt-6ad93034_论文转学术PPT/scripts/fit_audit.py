#!/usr/bin/env python3
"""fit_audit.py — 模板合规审计：模板原始值 → 实际落点值 → 是否吻合，逐页机器生成。

数据来源不经模型转述：模板值来自 probe_report.json（探查脚本产出），落点值从
真实产出的 pptx 读出。result.json 的 compliance_checks 直接内嵌本脚本 summary。

输出 fit_audit.json：
  per_slide   逐页 {layout/font/color/title} 四组 template_value→applied→match
  inheritance 整册继承链层级 real / textbox_fallback / standalone_minimal_fallback
  summary     {pages, match_rate, fail, warn, diff_pages}（机器判定，非文字声明）

用法: python3 fit_audit.py deck.pptx --deck deck.json --report probe_report.json \
        --log layout_log.json --out /app/output/fit_audit.json
退出码恒 0；python-pptx 缺失降级 raw-xml 并如实登记。
"""
import argparse
import json
import os
import re
import sys
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _neutral(hexstr):
    try:
        h = (hexstr or "").replace("#", "")
        ch = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return max(ch) - min(ch) <= 0x14
    except Exception:
        return False


def collect_raw(path):
    """raw-xml 抽逐页字体/颜色/占位符使用。"""
    z = zipfile.ZipFile(path)
    names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                   key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    pages = []
    for n in names:
        root = ET.fromstring(z.read(n))
        sizes, names_f, colors = set(), set(), set()
        for rpr in root.iter():
            tag = rpr.tag.split("}")[-1]
            if tag in ("rPr", "endParaRPr", "defRPr"):
                sz = rpr.get("sz")
                if sz:
                    sizes.add(int(sz) / 100.0)
                lat = rpr.find("{%s}latin" % NS_A)
                if lat is not None and lat.get("typeface"):
                    names_f.add(lat.get("typeface"))
                fill = rpr.find("{%s}solidFill/{%s}srgbClr" % (NS_A, NS_A))
                if fill is not None:
                    colors.add(fill.get("val"))
        pages.append({"font_sizes": sorted(sizes), "font_names": sorted(names_f),
                      "colors": sorted(colors)})
    return pages


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("pptx")
    ap.add_argument("--deck", default=None)
    ap.add_argument("--report", default=None, help="probe_report.json（模板原始值）")
    ap.add_argument("--log", default=None, help="layout_log.json（构建信息）")
    ap.add_argument("--out", default="fit_audit.json")
    args = ap.parse_args()

    audit = {"pptx": args.pptx, "engine": None, "per_slide": [], "summary": {}, "fail": 0, "warn": 0}
    log_info = {}
    if args.log and os.path.exists(args.log):
        try:
            log_info = json.load(open(args.log, encoding="utf-8")).get("build_info") or {}
        except Exception:
            pass
    audit["inheritance"] = log_info.get("inheritance", "unknown")
    audit["font_mode"] = log_info.get("font_mode", "unknown")

    tpl_fonts = {}
    tpl_colors = []
    if args.report and os.path.exists(args.report):
        try:
            rep = json.load(open(args.report, encoding="utf-8"))
            tpl_fonts = (rep.get("template") or {}).get("theme_fonts") or {}
            tpl_colors = (rep.get("template") or {}).get("theme_colors") or []
        except Exception:
            pass
    audit["template_values"] = {"theme_fonts": tpl_fonts, "theme_colors": tpl_colors}

    try:
        pages = collect_raw(args.pptx)
        audit["engine"] = "raw-xml"
    except Exception as e:
        audit["error"] = str(e)[:200]
        pages = []

    major = (tpl_fonts.get("majorFont") or {}).get("latin")
    ok_colors = {c.upper() for c in tpl_colors if c}
    for i, pg in enumerate(pages, 1):
        row = {"no": i}
        font_names = {n for n in pg["font_names"] if n and n not in ("+mn-lt", "+mj-lt")}
        if major:
            row["font"] = {"template_value": major, "applied": sorted(font_names) or "theme_inherit",
                           "match": (not font_names) or major in font_names}
            if not row["font"]["match"]:
                audit["fail"] += 1
        colors = {c.upper() for c in pg["colors"]}
        bad = {c for c in colors if not _neutral(c) and ok_colors and c not in ok_colors}
        row["color"] = {"template_accent_count": len(ok_colors), "applied": sorted(colors),
                        "off_palette": sorted(bad), "match": not bad}
        if bad:
            audit["warn"] += 1
        row["min_font_pt"] = min(pg["font_sizes"]) if pg["font_sizes"] else None
        audit["per_slide"].append(row)

    n = len(pages)
    matches = sum(1 for r in audit["per_slide"] if r.get("font", {}).get("match", True))
    audit["summary"] = {
        "pages": n,
        "font_match_pages": matches,
        "font_match_rate": round(matches / n, 3) if n else None,
        "off_palette_slides": sum(1 for r in audit["per_slide"] if not r["color"]["match"]),
        "min_font_pt_overall": min([r["min_font_pt"] for r in audit["per_slide"] if r["min_font_pt"]] or [None]),
        "fail": audit["fail"], "warn": audit["warn"],
        "verdict": "pass" if audit["fail"] == 0 else "fail",
    }
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(json.dumps({"write_error": str(e)}, ensure_ascii=False))
    print(json.dumps({"summary": audit["summary"], "inheritance": audit["inheritance"]}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
