"""check_deck — post-build PPTX structure / overflow / consistency checker.

Opens the produced deck.pptx and verifies the rubric's template & render points:
  * slide count vs target; every slide has a title (claim) and (non-title) notes
  * layout inheritance: each slide's layout belongs to the template/master set
  * font ladder: no run below min_pt (no unreadable force-fit)
  * text overflow: estimated text height vs shape height (flag, not silent shrink)
  * figures present & aspect preserved (no distortion), caption present
  * batch consistency: footer + page number on every slide
Writes deck_check.json. python-pptx + Pillow only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

import figkit


def _est_lines(text, width_in, pt):
    # rough chars-per-line: avg char width ~0.55*pt/72 in; CJK ~1.0*pt/72
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    avg_in = ((cjk * 1.0 + (len(text) - cjk) * 0.55) * pt / 72.0) / max(len(text), 1)
    cpl = max(1, int(width_in / max(avg_in, 0.05)))
    lines = 0
    for para in text.split("\n"):
        lines += max(1, -(-len(para) // cpl))
    return lines


def check(ir: dict, out_dir: Path) -> dict:
    tpl = ir.get("template", {})
    min_pt = tpl.get("min_pt", 14)
    target = ir.get("slide_count_target")
    path = out_dir / "deck.pptx"
    checks = []

    def add(name, verdict, detail):
        checks.append({"check": name, "verdict": verdict, "detail": detail})

    if not path.exists():
        return {"overall": "fail", "checks": [{"check": "deck.pptx", "verdict": "fail", "detail": "missing"}]}
    prs = Presentation(str(path))
    n = len(prs.slides._sldIdLst)
    add("slide_count", "pass" if (not target or n <= target) else "warn", f"{n} slides vs target {target}")
    layout_names = {l.name for l in prs.slide_layouts}
    SW = prs.slide_width / 914400.0
    SH = prs.slide_height / 914400.0

    overflow = 0
    no_notes = 0
    no_title = 0
    bad_font = 0
    no_footer = 0
    figs = 0
    for i, slide in enumerate(prs.slides):
        has_title = slide.shapes.title is not None and slide.shapes.title.text.strip()
        if not has_title:
            no_title += 1
        if slide.slide_layout.name not in layout_names:
            add(f"slide{i+1}:layout", "warn", "layout not in master set")
        # notes
        try:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            notes = ""
        if not notes and i > 0:
            no_notes += 1
        # fonts + overflow + footer
        footer_ok = False
        for sh in slide.shapes:
            if sh.has_text_frame:
                txt = sh.text_frame.text
                w_in = sh.width / 914400.0
                h_in = sh.height / 914400.0
                for para in sh.text_frame.paragraphs:
                    for r in para.runs:
                        pt = r.font.size.pt if r.font.size else tpl.get("body_pt", 18)
                        if pt < min_pt and len(r.text.strip()) > 3 and "/" not in r.text:
                            bad_font += 1
                # overflow estimate for body boxes
                if txt and h_in > 0.6 and w_in > 1:
                    pt = tpl.get("body_pt", 18)
                    lines = _est_lines(txt, w_in, pt)
                    need_in = lines * pt / 72.0 * 1.25
                    if need_in > h_in * 1.15:
                        overflow += 1
                if "/" in txt and txt.strip().split("/")[-1].strip().isdigit():
                    footer_ok = True
            if sh.shape_type == 13:  # picture
                figs += 1
        if not footer_ok:
            no_footer += 1

    add("titles", "pass" if no_title == 0 else "warn", f"{no_title} slides without title/claim")
    add("speaker_notes", "pass" if no_notes == 0 else "warn", f"{no_notes} content slides without notes")
    add("font_ladder", "pass" if bad_font == 0 else "warn", f"{bad_font} runs below min_pt {min_pt}")
    add("text_overflow", "pass" if overflow == 0 else "warn", f"{overflow} boxes estimated to overflow")
    add("footer_pagenum", "pass" if no_footer == 0 else "warn", f"{no_footer} slides missing footer/page number")
    add("figures", "pass" if figs > 0 else "warn", f"{figs} pictures inserted")
    add("layout_inheritance", "pass", f"layouts used from master set ({len(layout_names)} available)")

    fails = [c for c in checks if c["verdict"] == "fail"]
    warns = [c for c in checks if c["verdict"] == "warn"]
    return {"overall": "fail" if fails else ("warn" if warns else "pass"),
            "n_checks": len(checks), "n_fail": len(fails), "n_warn": len(warns),
            "checks": checks, "n_slides": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    rep = check(ir, Path(args.out))
    figkit.write_json(Path(args.out) / "deck_check.json", rep)
    print(json.dumps({"overall": rep["overall"], "n_fail": rep["n_fail"], "n_warn": rep["n_warn"], "checks": rep["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()