#!/usr/bin/env python3
"""pptx_build.py — deck.json -> deck.pptx with pre-flight layout budget.

Preferred path: python-pptx (better fidelity, template inheritance).
Fallback path: pptx_minimal (pure stdlib, always works offline).

Usage:
  python3 pptx_build.py deck.json out.pptx [template.pptx] [--log layout_log.json]

Behavior:
  1. Runs layout_budget on every slide; shrinks fonts along the ladder or
     flags "trim" when even the floor size overflows.
  2. If a template is given AND python-pptx is available, clones the template
     and fills its own blank/layout placeholders only if usable; otherwise
     builds standalone slides (template master untouched where possible).
  3. Writes layout_log.json recording every size decision (auditable).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_budget as LB  # noqa: E402

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    HAVE_PPTX = True
except Exception:
    HAVE_PPTX = False


def _layout_catalog(prs):
    """Map layout name + its placeholder types for template slot filling."""
    from pptx.oxml.ns import qn
    cat = []
    for lay in prs.slide_layouts:
        phs = []
        try:
            for ph in lay.placeholders:
                el = ph._element
                pe = el.find(qn("p:nvSpPr") + "/" + qn("p:nvPr") + "/" + qn("p:ph"))
                ptype = pe.get("type") if pe is not None else None
                phs.append({"idx": ph.placeholder_format.idx, "type": ptype or "body",
                            "name": ph.name})
        except Exception:
            pass
        cat.append({"layout": lay, "name": lay.name, "placeholders": phs})
    return cat


def _pick_template_layout(cat, want):
    """Keyword mapping deck layout -> template layout object (best match)."""
    keymap = {
        "title": ("title slide", "标题幻灯片", "title", "标题"),
        "closing": ("title slide", "thank", "title", "标题"),
        "section": ("section header", "节标题", "title", "标题"),
        "bullets": ("title and content", "标题和内容", "1 title and content", "title only", "标题"),
        "bullets+figure": ("two content", "两栏内容", "title and content", "title only", "标题"),
        "two-col": ("two content", "两栏内容", "two content", "title only"),
        "table": ("title only", "仅标题", "title and content", "blank"),
        "figure": ("title only", "仅标题", "picture", "title and content", "blank"),
        "blank": ("blank", "空白"),
    }
    keys = keymap.get(want, keymap["bullets"])
    lowered = [(k["name"].lower(), k) for k in cat]
    for key in keys:
        for name, entry in lowered:
            if key.lower() in name:
                return entry
    # fallback: layout with a title placeholder, else blank-ish last layout
    for name, entry in lowered:
        if any(p["type"] in ("title", "ctrTitle") for p in entry["placeholders"]):
            return entry
    return cat[-1] if cat else None


def _fill_placeholder(ph, text, size=None, bold=None, italic=None, color=None,
                      latin=None, ea=None, clear=True):
    tf = ph.text_frame
    if clear:
        tf.clear()
    lines = text if isinstance(text, list) else [text]
    first = True
    for line in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run()
        r.text = str(line)
        if size is not None:
            r.font.size = Pt(size)
        if bold is not None:
            r.font.bold = bold
        if italic is not None:
            r.font.italic = italic
        if color is not None:
            r.font.color.rgb = color
        if latin:
            r.font.name = latin
        if ea:
            try:
                rPr = r._r.get_or_add_rPr()
                from pptx.oxml.ns import qn
                ea_el = rPr.find(qn("a:ea"))
                if ea_el is None:
                    ea_el = rPr.makeelement(qn("a:ea"), {})
                    rPr.append(ea_el)
                ea_el.set("typeface", ea)
            except Exception:
                pass


def _theme_accent(report):
    """模板主题 accent1，用于强调色（真实继承主题色而非自造配色）。"""
    try:
        cols = [c for c in (report or {}).get("theme_colors") or [] if c and len(c) == 6]
        return RGBColor.from_string(cols[0]) if cols else None
    except Exception:
        return None


def build_with_pythonpptx(spec, out_path, template_path=None, log=None, report=None):
    try:
        prs = Presentation(template_path) if template_path else Presentation()
    except Exception as e:
        # 模板不可用：降级为学术默认版式，如实登记，不中断构建
        if log is not None:
            log["warnings"].append({"issue": "template_unusable",
                                    "detail": "%s: %s" % (type(e).__name__, e),
                                    "fallback": "academic_default_layout"})
        template_path = None
        prs = Presentation()
    if not template_path:
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
    blank = None
    try:
        for lay in prs.slide_layouts:
            if lay.name.lower() in ("blank", "空白"):
                blank = lay
                break
        if blank is None:
            blank = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[-1]
    except Exception:
        blank = prs.slide_layouts[-1]
    catalog = _layout_catalog(prs) if template_path else []

    DARK = RGBColor(0x2B, 0x3A, 0x55)
    BODY = RGBColor(0x1A, 0x1A, 0x1A)
    GREY = RGBColor(0x55, 0x55, 0x55)
    META = RGBColor(0x80, 0x80, 0x80)
    BLUE = RGBColor(0x2B, 0x5B, 0xA8)

    def set_font(run, size, bold=False, italic=False, color=BODY, latin=None, ea=None):
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        if color is not None:
            run.font.color.rgb = color
        if latin:
            run.font.name = latin
        if ea:
            try:
                rPr = run._r.get_or_add_rPr()
                from pptx.oxml.ns import qn
                ea_el = rPr.find(qn("a:ea"))
                if ea_el is None:
                    ea_el = rPr.makeelement(qn("a:ea"), {})
                    rPr.append(ea_el)
                ea_el.set("typeface", ea)
            except Exception:
                pass

    def add_text(slide, x, y, w, h, wrap_text=True):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = wrap_text
        try:
            tf.auto_size = None
        except Exception:
            pass
        return tb, tf

    def para(tf, text, size, bullet=False, bold=False, italic=False, color=BODY,
             align=None, first=False, latin=None, ea=None):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        if align:
            p.alignment = align
        try:
            p.space_after = Pt(6)
        except Exception:
            pass
        r = p.add_run()
        r.text = str(text)
        set_font(r, size, bold, italic, color, latin, ea)
        return p

    def _ph_by_type(placeholder_list, *types):
        for ph in placeholder_list:
            el = ph._element
            from pptx.oxml.ns import qn
            pe = el.find(qn("p:nvSpPr") + "/" + qn("p:nvPr") + "/" + qn("p:ph"))
            pt = (pe.get("type") if pe is not None else None) or "body"
            if pt in types:
                return ph
        return None

    meta = spec.get("deck_meta", {})
    # 有模板且 deck_meta 未显式指定字体 -> 完全不设 typeface，交给母版主题继承
    # （真实继承：改主题即整册换字，run 上不残留硬化字体）
    if template_path and not (meta.get("font_latin") or meta.get("font_ea")):
        latin = ea = None
        inherit_fonts = True
    else:
        latin = meta.get("font_latin", "Arial")
        ea = meta.get("font_ea", "Noto Sans CJK SC")
        inherit_fonts = False
    accent = _theme_accent(report) if template_path else None
    BLUE = accent or BLUE
    if template_path:
        # 占位符内标题颜色不显式设置 -> 继承版式/母版主题色（真实继承，改主题即变色）
        DARK = None
    if log is not None:
        log["font_mode"] = "theme_inherit" if inherit_fonts else "explicit"
        log["accent_color"] = str(accent) if accent else None

    for idx, sl in enumerate(spec.get("slides", []), start=1):
        layout = sl.get("layout", "bullets")
        tsize = sl.get("title_size", 28)
        bsize = sl.get("body_size", 18) or 18
        tentry = _pick_template_layout(catalog, layout) if catalog else None
        slide = prs.slides.add_slide(tentry["layout"] if tentry else blank)
        used_phs = []
        inherit = "standalone"
        title_ph = body_ph = None
        if tentry is not None:
            phs = list(slide.placeholders)
            title_ph = _ph_by_type(phs, "title", "ctrTitle")
            body_ph = _ph_by_type(phs, "body", "subTitle", "objText")
            inherit = "real" if (title_ph is not None or body_ph is not None) else "standalone"
            if title_ph is not None:
                used_phs.append(title_ph.placeholder_format.idx)
            if body_ph is not None:
                used_phs.append(body_ph.placeholder_format.idx)
        if log is not None:
            entry = next((e for e in (log.get("slides") or []) if e.get("no") == idx), None)
            if entry is None:
                entry = {"no": idx}
                log.setdefault("slides", []).append(entry)
            entry.update({"template_layout": tentry["name"] if tentry else None,
                          "placeholders_used": used_phs, "inheritance": inherit})

        # page number: standalone path only (template masters usually carry their own)
        if inherit == "standalone":
            _, tf = add_text(slide, 12.4, 7.05, 0.7, 0.35, wrap_text=False)
            para(tf, str(idx), 10, color=META, align=PP_ALIGN.RIGHT, first=True, latin=latin, ea=ea)

        if layout in ("title", "closing"):
            if title_ph is not None:
                _fill_placeholder(title_ph, sl.get("title", ""), size=tsize + 8, bold=True,
                                  color=DARK, latin=latin, ea=ea)
            else:
                _, tf = add_text(slide, 1.0, 2.7, 11.33, 1.3)
                para(tf, sl.get("title", ""), tsize + 8, bold=True, color=DARK,
                     align=PP_ALIGN.CENTER, first=True, latin=latin, ea=ea)
            sub = sl.get("subtitle")
            if sub:
                lines = sub if isinstance(sub, list) else [sub]
                if body_ph is not None:
                    _fill_placeholder(body_ph, lines, size=16, color=GREY, latin=latin, ea=ea)
                else:
                    _, tf = add_text(slide, 1.0, 4.0, 11.33, 1.4)
                    for i, line in enumerate(lines):
                        para(tf, line, 16, color=GREY, align=PP_ALIGN.CENTER,
                             first=(i == 0), latin=latin, ea=ea)
        elif layout == "section":
            if title_ph is not None:
                _fill_placeholder(title_ph, sl.get("title", ""), size=34, bold=True,
                                  color=BLUE, latin=latin, ea=ea)
            else:
                _, tf = add_text(slide, 1.0, 3.0, 11.33, 1.5)
                para(tf, sl.get("title", ""), 34, bold=True, color=BLUE,
                     align=PP_ALIGN.CENTER, first=True, latin=latin, ea=ea)
        else:
            if title_ph is not None:
                _fill_placeholder(title_ph, sl.get("title", ""), size=tsize, bold=True,
                                  color=DARK, latin=latin, ea=ea)
            else:
                _, tf = add_text(slide, 0.6, 0.35, 12.13, 0.9)
                para(tf, sl.get("title", ""), tsize, bold=True, color=DARK, first=True, latin=latin, ea=ea)

            fig = sl.get("figure")
            body_w = 12.13
            if fig and fig.get("path") and os.path.exists(fig["path"]):
                if layout == "figure":
                    bx, by, bw, bh = 1.2, 1.35, 10.9, 5.0
                else:
                    bx, by, bw, bh = 8.35, 1.45, 4.35, 4.6
                    body_w = 7.5
                try:
                    # contain-fit: compute via PIL if available else fix width
                    from PIL import Image
                    with Image.open(fig["path"]) as im:
                        iw, ih = im.size
                    scale = min(bw / (iw / 96.0), bh / (ih / 96.0))
                    w_in, h_in = iw / 96.0 * scale, ih / 96.0 * scale
                    slide.shapes.add_picture(fig["path"], Inches(bx + (bw - w_in) / 2),
                                             Inches(by + (bh - h_in) / 2),
                                             Inches(w_in), Inches(h_in))
                    if fig.get("caption"):
                        cy = by + bh + 0.08
                        _, ctf = add_text(slide, bx, min(cy, 6.9), bw, 0.5)
                        para(ctf, fig["caption"], 10, italic=True, color=GREY,
                             align=PP_ALIGN.CENTER if layout == "figure" else None,
                             first=True, latin=latin, ea=ea)
                except Exception as e:
                    if log is not None:
                        log.setdefault("warnings", []).append(
                            {"slide": idx, "issue": "figure_embed_failed", "detail": str(e)})

            if layout == "table":
                rows = sl.get("table", {}).get("rows") or sl.get("rows") or []
                if rows:
                    nrows, ncols = len(rows), max(len(r) for r in rows)
                    gt = slide.shapes.add_table(nrows, ncols, Inches(0.7), Inches(1.5),
                                                Inches(11.9), Inches(min(0.5 * nrows, 5.2))).table
                    for ri, row in enumerate(rows):
                        for ci in range(ncols):
                            cell = gt.cell(ri, ci)
                            cell.text = str(row[ci]) if ci < len(row) else ""
                            for p in cell.text_frame.paragraphs:
                                for r in p.runs:
                                    set_font(r, sl.get("body_size", 13), bold=(ri == 0))
            elif layout == "two-col":
                cols = sl.get("columns", [[], []])[:2]
                colw = 5.85
                for ci, col in enumerate(cols):
                    _, ctf = add_text(slide, 0.6 + ci * (colw + 0.35), 1.45, colw, 5.3)
                    for i, b in enumerate(col):
                        t = b.get("text", "") if isinstance(b, dict) else str(b)
                        para(ctf, "• " + t if not t.startswith("• ") else t,
                             bsize, first=(i == 0), latin=latin, ea=ea)
            else:
                if body_ph is not None and layout != "bullets+figure":
                    _fill_placeholder(body_ph, ["• " + (b.get("text", "") if isinstance(b, dict) else str(b))
                                                for b in sl.get("bullets", [])],
                                      size=bsize, latin=latin, ea=ea)
                else:
                    _, btf = add_text(slide, 0.6, 1.45, body_w, 5.3)
                    bullets = sl.get("bullets", [])
                    for i, b in enumerate(bullets):
                        if isinstance(b, dict):
                            para(btf, b.get("text", ""), b.get("size", bsize),
                                 bold=b.get("bold", False), color=b.get("color", BODY),
                                 first=(i == 0), latin=latin, ea=ea)
                        else:
                            para(btf, b, bsize, first=(i == 0), latin=latin, ea=ea)
        if sl.get("notes"):
            slide.notes_slide.notes_text_frame.text = sl["notes"]

    prs.save(out_path)
    return out_path


def build_fallback(spec, out_path):
    import pptx_minimal
    return pptx_minimal.build(spec, out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("deck")
    ap.add_argument("out")
    ap.add_argument("template", nargs="?", default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--report", default=None, help="template_report.json（用于继承主题强调色）")
    args = ap.parse_args()

    with open(args.deck, "r", encoding="utf-8") as f:
        spec = json.load(f)
    report = None
    if args.report and os.path.exists(args.report):
        try:
            with open(args.report, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception:
            report = None
    log = {"builder": None, "template": args.template, "slides": [], "warnings": []}

    # pre-flight layout budget on body area
    for i, sl in enumerate(spec.get("slides", []), 1):
        layout = sl.get("layout", "bullets")
        if layout in ("title", "closing", "section"):
            b = {"font_pt": sl.get("title_size", 28), "action": "ok"}
        elif layout == "two-col":
            b = LB.budget_slide(sl, 5.7, 5.1)
        elif layout == "figure":
            b = {"font_pt": sl.get("body_size", 18), "action": "ok"}
        elif layout == "bullets+figure":
            b = LB.budget_slide(sl, 7.4, 5.1)
        else:
            b = LB.budget_slide(sl, 11.5, 5.1)
        sl.setdefault("body_size", b["font_pt"])
        if b.get("action") == "shrunk":
            sl["body_size"] = b["font_pt"]
        if b.get("action") == "trim" and sl.get("bullets"):
            sl["body_size"] = max(b["font_pt"], LB.MIN_FLOOR)
            log["warnings"].append({"slide": i, "issue": "content_exceeds_page",
                                    "detail": "even %dpt overflows; trim content" % b["font_pt"]})
        tb = LB.budget_title(sl, 12.0, sl.get("title_size", 28))
        if not tb["fits"]:
            sl["title_size"] = 24
            log["warnings"].append({"slide": i, "issue": "title_too_long",
                                    "detail": "%d lines at 28pt; title reduced to 24pt" % tb["lines"]})
        nb = LB.check_notes(sl, " ".join(
            (x.get("text", "") if isinstance(x, dict) else str(x)) for x in sl.get("bullets", []) or []))
        log["slides"].append({"no": i, "layout": layout, "body_font_pt": sl.get("body_size"),
                              "title_font_pt": sl.get("title_size"), "notes": nb,
                              "budget": {k: b[k] for k in ("font_pt", "action") if k in b}})

    template = args.template if args.template and os.path.exists(args.template) else None
    if template is None and args.template:
        log["warnings"].append({"issue": "template_not_found", "detail": args.template})

    if HAVE_PPTX:
        log["builder"] = "python-pptx"
        build_with_pythonpptx(spec, args.out, template, log, report)
    else:
        log["builder"] = "pptx_minimal(fallback, stdlib-only)"
        build_fallback(spec, args.out)
        for e in log.get("slides", []):
            e["inheritance"] = "standalone_minimal_fallback"
        if template:
            log["warnings"].append({"issue": "template_requires_pythonpptx",
                                    "detail": "python-pptx unavailable; built standalone deck"})

    log_path = args.log or (os.path.splitext(args.out)[0] + ".layout_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print("pptx:", args.out)
    print("log :", log_path)
    print("builder:", log["builder"], "| warnings:", len(log["warnings"]))
    for w in log["warnings"]:
        print("  warn:", json.dumps(w, ensure_ascii=False))


if __name__ == "__main__":
    main()
