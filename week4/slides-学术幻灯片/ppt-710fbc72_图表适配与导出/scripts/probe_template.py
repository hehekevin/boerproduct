#!/usr/bin/env python3
"""probe_template.py — 纯标准库模板探查（zipfile + ElementTree，无 python-pptx 依赖）。

读模板 .pptx 的真实结构，产出 template_report.json：
  slide_size, masters, layouts[{name, placeholders[{idx,type,name,geom}]}],
  theme_fonts(major/minor latin+ea), theme_colors(accent1-6), recommendation。

周4改进：不再依赖 python-pptx —— 评测沙箱无 pip，纯标准库探查永远可用，
探查失败（损坏/非pptx/路径不存在）写 fail 报告并如实登记，退出码恒 0。

用法: python3 probe_template.py <模板.pptx> --out /app/work/template_report.json
"""
import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EMU_IN = 914400

PH_TYPE_MAP = {"title": "title", "ctrTitle": "title", "body": "body", "subTitle": "subtitle",
               "pic": "picture", "tbl": "table", "ftr": "footer", "sldNum": "slide_number",
               "dt": "date"}


def _emu_to_in(v):
    try:
        return round(int(v) / EMU_IN, 2)
    except Exception:
        return None


def _parse_placeholders(root):
    out = []
    for sp in root.iter("{%s}sp" % NS_P):
        ph = sp.find("{%s}nvSpPr/{%s}nvPr/{%s}ph" % (NS_P, NS_P, NS_P))
        if ph is None:
            continue
        name_el = sp.find("{%s}nvSpPr/{%s}cNvPr" % (NS_P, NS_P))
        xfrm = sp.find("{%s}spPr/{%s}xfrm" % (NS_P, NS_A))
        geom = None
        if xfrm is not None:
            off, ext = xfrm.find("{%s}off" % NS_A), xfrm.find("{%s}ext" % NS_A)
            if off is not None and ext is not None:
                geom = {"x": _emu_to_in(off.get("x")), "y": _emu_to_in(off.get("y")),
                        "w": _emu_to_in(ext.get("cx")), "h": _emu_to_in(ext.get("cy"))}
        raw = ph.get("type") or "body"
        out.append({"idx": int(ph.get("idx") or 0),
                    "type": PH_TYPE_MAP.get(raw, raw),
                    "raw_type": raw,
                    "name": (name_el.get("name") if name_el is not None else None) or "",
                    "geom": geom})
    return out


def _theme_from_zip(z):
    fonts, colors = {}, []
    theme_names = sorted(n for n in z.namelist()
                         if re.match(r"ppt/theme/theme\d+\.xml$", n))
    if not theme_names:
        return fonts, colors, "no theme part found"
    root = ET.fromstring(z.read(theme_names[0]))
    for tag in ("majorFont", "minorFont"):
        el = root.find(".//{%s}%s" % (NS_A, tag))
        if el is not None:
            lat, ea = el.find("{%s}latin" % NS_A), el.find("{%s}ea" % NS_A)
            fonts[tag] = {"latin": lat.get("typeface") if lat is not None else None,
                          "ea": ea.get("typeface") if ea is not None else None}
    for i in range(1, 7):
        el = root.find(".//{%s}accent%d" % (NS_A, i))
        if el is not None:
            srgb = el.find("{%s}srgbClr" % NS_A)
            colors.append(srgb.get("val") if srgb is not None else None)
    return fonts, colors, None


def probe(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    report = {"template": path, "ok": True, "probe_engine": "stdlib-zipfile"}

    pres = ET.fromstring(z.read("ppt/presentation.xml"))
    sz = pres.find("{%s}sldSz" % NS_P)
    report["slide_size"] = {"w_in": _emu_to_in(sz.get("cx")) if sz is not None else None,
                            "h_in": _emu_to_in(sz.get("cy")) if sz is not None else None}

    master_names = sorted(n for n in names if re.match(r"ppt/slideMasters/slideMaster\d+\.xml$", n))
    report["masters"] = len(master_names)

    layout_names = sorted((n for n in names if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n)),
                          key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    layouts = []
    for n in layout_names:
        root = ET.fromstring(z.read(n))
        csl = root.find("{%s}cSld" % NS_P)
        entry = {"name": (csl.get("name") if csl is not None else None) or os.path.basename(n),
                 "part": n, "placeholders": _parse_placeholders(root)}
        layouts.append(entry)
    report["layouts"] = layouts
    report["theme_fonts"], report["theme_colors"], theme_note = _theme_from_zip(z)
    if theme_note:
        report["theme_note"] = theme_note

    # 母版占位符（版式继承的最终兜底）
    master_phs = []
    for n in master_names:
        master_phs.extend(_parse_placeholders(ET.fromstring(z.read(n))))
    report["master_placeholders"] = master_phs

    # 页型推荐映射（与 pptx_build 的 keymap 同源）
    def pick(keys):
        for key in keys:
            for entry in layouts:
                if key.lower() in entry["name"].lower():
                    return entry["name"]
        return None

    report["recommendation"] = {
        "title": pick(["title slide", "标题幻灯片", "标题"]),
        "section": pick(["section", "节标题"]),
        "bullets": pick(["title and content", "标题和内容", "title only", "仅标题"]),
        "bullets+figure": pick(["two content", "两栏内容", "title and content"]),
        "two-col": pick(["two content", "两栏内容"]),
        "table": pick(["title only", "仅标题"]),
        "figure": pick(["picture", "图片", "title only"]),
        "blank": pick(["blank", "空白"]),
    }
    warnings = []
    if not layouts:
        warnings.append("no layouts found; template may be corrupt")
    if all(not l["placeholders"] for l in layouts):
        warnings.append("no placeholders in any layout; use standalone boxes over cloned template")
    report["warnings"] = warnings
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or "template_report.json"

    report = None
    if not os.path.exists(args.template):
        report = {"template": args.template, "ok": False, "error": "not_found",
                  "fallback": "academic_default_layouts",
                  "warnings": ["template_path_not_found"]}
    else:
        try:
            report = probe(args.template)
        except Exception as e:
            report = {"template": args.template, "ok": False,
                      "error": "%s: %s" % (type(e).__name__, e),
                      "fallback": "academic_default_layouts",
                      "warnings": ["template_unusable"]}
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "write_report_failed: %s" % e}, ensure_ascii=False))
        return 0
    print(json.dumps({"ok": report.get("ok", False),
                      "layouts": len(report.get("layouts", []) or []),
                      "fonts": report.get("theme_fonts", {}),
                      "fallback": report.get("fallback"),
                      "out": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
