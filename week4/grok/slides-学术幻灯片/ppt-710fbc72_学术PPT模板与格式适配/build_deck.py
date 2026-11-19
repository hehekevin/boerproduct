"""build_deck — template-aware, source-bound academic PPTX generator (python-pptx).

Fills a REAL master/layout template (runtime-provided /input/*.pptx) or creates a
programmatic master when none is supplied. Inherits layouts/placeholders, keeps
theme fonts/colors, writes one claim per page, source-bound bullets, data-bound or
cited figures (never placeholders), speaker notes, footer + page numbers. Enforces
a readable font ladder (never shrinks below min_pt to force-fit) and records
template inheritance + page->source provenance.

Usage:
  python build_deck.py --ir deck_ir.json --out /app/output [--template /input/template.pptx]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

import figkit
import deckkit

HERE = Path(__file__).resolve().parent

LAYOUT_HINTS = {
    "title": ["title slide", "title"],
    "section": ["section", "header"],
    "outline": ["title and content", "content"],
    "picture": ["picture", "caption"],
    "two": ["two content", "comparison"],
    "blank": ["blank"],
    "content": ["title and content", "content", "title only"],
}
ROLE_LAYOUT = {"title": "title", "section": "section", "outline": "content",
               "qa": "content", "backup": "content"}


def _hex(c):
    c = c.lstrip("#")
    return RGBColor(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _pick_layout(prs, want):
    hints = LAYOUT_HINTS.get(want, LAYOUT_HINTS["content"])
    names = [ (l.name or "").lower() for l in prs.slide_layouts ]
    for h in hints:
        for i, n in enumerate(names):
            if h in n:
                return prs.slide_layouts[i]
    # fallback: index by convention (0 title,1 content,2 section,6 blank)
    idx = {"title": 0, "section": 2, "blank": 6}.get(want, 1)
    return prs.slide_layouts[min(idx, len(prs.slide_layouts) - 1)]


def _set_font(run, pt, name=None, color=None, bold=False):
    run.font.size = Pt(pt)
    run.font.bold = bold
    if name:
        run.font.name = name
        # east-asian typeface so CJK does not fall back to boxes
        rPr = run._r.get_or_add_rPr()
        from pptx.oxml.ns import qn
        ea = rPr.find(qn("a:ea"))
        if ea is None:
            ea = rPr.makeelement(qn("a:ea"), {})
            rPr.append(ea)
        ea.set("typeface", name)
    if color:
        run.font.color.rgb = _hex(color)


def _body_placeholder(slide):
    for ph in slide.placeholders:
        if ph.placeholder_format.idx != 0 and ph.has_text_frame:
            return ph
    return None


def _add_textbox(slide, x, y, w, h):
    return slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))


def _render_figure(fig, out_dir, idx, style):
    """Return (image_path, caption). Redraw data-bound charts via render_chart;
    otherwise use the cited original image. Never a placeholder."""
    if fig.get("chart"):
        import render_chart
        sub_ir = {"chart": fig["chart"], "style": style,
                  "canvas": {"width_mm": 150, "height_mm": 100, "dpi": 200},
                  "exports": [{"format": "png", "dpi": 200}],
                  "provenance": {"pipeline": "slide figure"}}
        res = render_chart.render(sub_ir, out_dir / f"fig{idx}")
        pngs = [a["path"] for a in res["artifacts"] if a["format"] == "png"]
        return (pngs[0] if pngs else None), fig.get("caption", "")
    if fig.get("image_path") and Path(fig["image_path"]).exists():
        return fig["image_path"], fig.get("caption", "")
    return None, fig.get("caption", "")


def build(ir: dict, out_dir: Path, template: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tpl = ir.get("template", {})
    tpath = template or tpl.get("path")
    used_template = bool(tpath and Path(tpath).exists())
    prs = Presentation(tpath) if used_template else Presentation()
    # slide size (16:9 default if new)
    if not used_template:
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
    SW = prs.slide_width / 914400.0
    SH = prs.slide_height / 914400.0

    font = tpl.get("cjk_font") or tpl.get("theme_font")
    title_pt = tpl.get("title_pt", 28)
    body_pt = max(tpl.get("body_pt", 18), tpl.get("min_pt", 14))
    accent = tpl.get("accent", "#0C5DA5")
    footer = tpl.get("footer", "")
    max_b = tpl.get("max_bullets", 5)

    inheritance = {}
    pages = ir.get("pages", [])
    n = len(pages)
    for i, p in enumerate(pages):
        want = p.get("layout") or ROLE_LAYOUT.get(p.get("role"), "content")
        if p.get("figures") and want == "content":
            want = "picture" if len(p["figures"]) == 1 else "two"
        layout = _pick_layout(prs, want)
        inheritance[p["id"]] = layout.name
        slide = prs.slides.add_slide(layout)

        # title = single claim
        if slide.shapes.title is not None:
            tf = slide.shapes.title.text_frame
            tf.text = p.get("claim", p.get("id", ""))
            for r in tf.paragraphs[0].runs:
                _set_font(r, title_pt, font, accent, bold=True)
        else:
            tb = _add_textbox(slide, 0.5, 0.3, SW - 1, 0.9)
            r = tb.text_frame.paragraphs[0].add_run(); r.text = p.get("claim", "")
            _set_font(r, title_pt, font, accent, bold=True)

        has_fig = bool(p.get("figures"))
        body = _body_placeholder(slide)
        bullets = p.get("bullets", [])[:max_b]
        if bullets:
            if body is None:
                body = _add_textbox(slide, 0.6, 1.5, (SW - 1.2) * (0.55 if has_fig else 1.0), SH - 2.4)
            tf = body.text_frame
            tf.word_wrap = True
            for j, b in enumerate(bullets):
                para = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                r = para.add_run(); r.text = "• " + b.get("text", "")
                _set_font(r, body_pt, font, "#222222")
                para.space_after = Pt(8)

        # figures (right side or below), aspect preserved
        fx = 0.6 + (SW - 1.2) * 0.58 if has_fig and bullets else 0.8
        fw = (SW - 1.2) * 0.40 if has_fig and bullets else SW - 1.6
        fy = 1.6
        for k, fig in enumerate(p.get("figures", [])):
            img, cap = _render_figure(fig, out_dir, f"{i}_{k}", ir.get("style", {}))
            if img:
                try:
                    from PIL import Image
                    with Image.open(img) as im:
                        aw, ah = im.size
                    aspect = ah / aw
                    w = fw
                    h = w * aspect
                    maxh = SH - 2.6
                    if h > maxh:
                        h = maxh; w = h / aspect
                    slide.shapes.add_picture(img, Inches(fx), Inches(fy + k * (h + 0.5)), Inches(w), Inches(h))
                    if cap:
                        cb = _add_textbox(slide, fx, fy + k * (h + 0.5) + h + 0.05, w, 0.4)
                        rr = cb.text_frame.paragraphs[0].add_run(); rr.text = cap
                        _set_font(rr, max(body_pt - 4, tpl.get("min_pt", 14)), font, "#555555")
                except Exception as e:  # noqa: BLE001
                    ir.setdefault("uncertainty", []).append({"item": f"figure {fig.get('ref')}", "reason": str(e), "impact": "figure not inserted", "handling": "recorded; cite in notes"})

        # speaker notes
        if p.get("notes"):
            slide.notes_slide.notes_text_frame.text = p["notes"]

        # footer + page number (batch consistency)
        fb = _add_textbox(slide, 0.5, SH - 0.45, SW - 1, 0.35)
        fp = fb.text_frame.paragraphs[0]
        r = fp.add_run(); r.text = f"{footer}    {i+1}/{n}"
        _set_font(r, max(tpl.get("min_pt", 14) - 2, 10), font, "#888888")

    # Q&A backup pages
    for q in ir.get("qa", []):
        if q.get("backup_page"):
            continue  # already a page
    deck_path = out_dir / "deck.pptx"
    prs.save(deck_path)
    ir.setdefault("provenance", {})["template_inheritance"] = inheritance
    ir["provenance"]["page_map"] = deckkit.build_page_map(ir)
    ir["provenance"]["used_template"] = tpath if used_template else "programmatic-master"
    return {"pptx": str(deck_path), "n_slides": n, "inheritance": inheritance,
            "used_template": bool(used_template), "slide_size_in": [round(SW, 2), round(SH, 2)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    v = deckkit.validate_deck(ir)
    if not v["ok"]:
        print(json.dumps({"status": "invalid_ir", "errors": v["errors"]}, ensure_ascii=False)); sys.exit(2)
    res = build(ir, Path(args.out), args.template)
    figkit.write_json(Path(args.out) / "deck_ir.json", ir)
    print(json.dumps({"status": "ok", **res, "warnings": v["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()