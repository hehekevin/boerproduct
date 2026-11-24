#!/usr/bin/env python3
"""probe_template.py — dump a template .pptx's real structure so the agent can
fill the right slots instead of blind-copying into the default layout.

Output template_report.json:
  slide_size, masters(count), layouts[{name, placeholders[{idx,type,name,geom}]}],
  theme_fonts(major/minor latin+ea), theme_colors(accent list), notes_master(bool),
  recommendation: which layout to use for each deck.json layout.

Usage: python probe_template.py template.pptx --out template_report.json
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    try:
        from pptx import Presentation
        from pptx.util import Emu
        from pptx.oxml.ns import qn
    except Exception:
        print(json.dumps({"ok": False, "error": "python-pptx unavailable"}))
        sys.exit(5)

    prs = Presentation(args.template)
    report = {"template": args.template, "ok": True,
              "slide_size": {"w_in": round(Emu(prs.slide_width).inches, 3),
                             "h_in": round(Emu(prs.slide_height).inches, 3)},
              "masters": len(prs.slide_masters), "layouts": []}

    for lay in prs.slide_layouts:
        entry = {"name": lay.name, "placeholders": []}
        for ph in lay.placeholders:
            el = ph._element
            pe = el.find(qn("p:nvSpPr") + "/" + qn("p:nvPr") + "/" + qn("p:ph"))
            ptype = (pe.get("type") if pe is not None else None) or "body"
            geom = None
            try:
                geom = {"x": round(Emu(ph.left).inches, 2), "y": round(Emu(ph.top).inches, 2),
                        "w": round(Emu(ph.width).inches, 2), "h": round(Emu(ph.height).inches, 2)}
            except Exception:
                pass
            entry["placeholders"].append({"idx": ph.placeholder_format.idx, "type": ptype,
                                          "name": ph.name, "geom": geom})
        report["layouts"].append(entry)

    # theme fonts/colors from master's theme part
    try:
        theme = prs.slide_masters[0].element.getroottree()
        import zipfile
        z = zipfile.ZipFile(args.template)
        theme_xml = None
        for n in z.namelist():
            if "theme" in n and n.endswith(".xml"):
                theme_xml = z.read(n).decode("utf-8", errors="replace")
                break
        if theme_xml:
            from xml.etree import ElementTree as ET
            root = ET.fromstring(theme_xml)
            ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            fonts = {}
            for tag in ("majorFont", "minorFont"):
                el = root.find(".//a:%s" % tag, ns)
                if el is not None:
                    lat = el.find("a:latin", ns)
                    ea = el.find("a:ea", ns)
                    fonts[tag] = {"latin": lat.get("typeface") if lat is not None else None,
                                  "ea": ea.get("typeface") if ea is not None else None}
            report["theme_fonts"] = fonts
            colors = []
            for i in range(1, 7):
                el = root.find(".//a:accent%d" % i, ns)
                if el is not None:
                    srgb = el.find("a:srgbClr", ns)
                    colors.append(srgb.get("val") if srgb is not None else None)
            report["theme_colors"] = colors
    except Exception as e:
        report["theme_note"] = "theme parse failed: %s" % e

    # recommendation: map deck layouts to this template's layouts
    def pick(keys):
        lowered = [(l["name"].lower(), l) for l in report["layouts"]]
        for key in keys:
            for name, entry in lowered:
                if key.lower() in name:
                    return entry["name"]
        return None

    report["recommendation"] = {
        "title": pick(["title slide", "标题", "title"]),
        "section": pick(["section", "节"]),
        "bullets": pick(["title and content", "标题和内容", "title only", "仅标题"]),
        "bullets+figure": pick(["two content", "两栏", "title and content"]),
        "two-col": pick(["two content", "两栏"]),
        "table": pick(["title only", "仅标题"]),
        "figure": pick(["picture", "图片", "title only"]),
        "blank": pick(["blank", "空白"]),
    }
    report["warnings"] = []
    if not report["layouts"]:
        report["warnings"].append("no layouts found; template may be corrupt")
    if all(not l["placeholders"] for l in report["layouts"]):
        report["warnings"].append("no placeholders in any layout; slot filling impossible, use standalone boxes over cloned template")

    out = args.out or "template_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("template probe:", len(report["layouts"]), "layouts, fonts:",
          json.dumps(report.get("theme_fonts", {}), ensure_ascii=False), "->", out)


if __name__ == "__main__":
    main()
