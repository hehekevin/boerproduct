#!/usr/bin/env python3
"""layout_budget.py — deterministic pre-flight layout budget for slides.

Estimates, for a given text box width and font size, how many lines a bullet
needs (CJK chars ~1.0 em, Latin ~0.55 em) and whether the whole body fits the
box height. Used BEFORE building the pptx so overflow is prevented by
stepping the font down along a fixed ladder (18 -> 16 -> 14 -> 12 -> 11 -> 10)
instead of letting PowerPoint shrink text unpredictably.

API:
  measure_lines(text, box_width_in, font_pt) -> int
  budget_slide(slide, box_w_in, box_h_in, ladder=[...]) -> dict
     returns {"font_pt", "fits": bool, "lines_total", "height_needed_pt",
              "height_avail_pt", "action"} where action is "ok"|"shrunk"|"trim"
"""
import math
import re

LINE_SPACING = 1.32          # line height multiplier
PARA_SPACING_PT = 6.0        # extra spacing after each paragraph
LADDER = [18, 16, 14, 12, 11, 10]
MIN_FLOOR = 10               # never go below this; report trim instead

_CJK = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF\u3000-\u303F]")


def text_em_width(text, font_pt):
    """Width of text in points."""
    cjk = len(_CJK.findall(text))
    latin = len(text) - cjk
    return cjk * font_pt * 1.0 + latin * font_pt * 0.55


def measure_lines(text, box_width_in, font_pt):
    box_pt = box_width_in * 72.0
    w = text_em_width(text, font_pt)
    if w <= 0:
        return 1
    return max(1, math.ceil(w / box_pt))


def budget_slide(slide, box_w_in, box_h_in, ladder=None, floor=None):
    ladder = ladder or LADDER
    floor = floor or MIN_FLOOR
    bullets = []
    if slide.get("bullets"):
        bullets.extend(slide["bullets"])
    for col in slide.get("columns", []) or []:
        bullets.extend(col)
    # table rows count as ~1 line each at body size
    tbl = slide.get("table") or {}
    rows = tbl.get("rows") or []

    best = None
    for fs in ladder:
        if fs < floor:
            break
        total_lines = 0
        for b in bullets:
            t = b.get("text", "") if isinstance(b, dict) else str(b)
            total_lines += measure_lines(t, box_w_in, fs)
        total_lines += len(rows) + sum(measure_lines(" ".join(r), box_w_in, fs) - 1 for r in rows)
        need = total_lines * fs * LINE_SPACING + max(0, len(bullets) - 1) * PARA_SPACING_PT
        avail = box_h_in * 72.0
        if need <= avail:
            best = {"font_pt": fs, "fits": True, "lines_total": total_lines,
                    "height_needed_pt": round(need, 1), "height_avail_pt": round(avail, 1),
                    "action": "ok" if fs == ladder[0] else "shrunk"}
            break
        best = {"font_pt": fs, "fits": False, "lines_total": total_lines,
                "height_needed_pt": round(need, 1), "height_avail_pt": round(avail, 1),
                "action": "trim"}
    if best is None:
        fs = floor
        total_lines = sum(measure_lines(
            (b.get("text", "") if isinstance(b, dict) else str(b)), box_w_in, fs) for b in bullets)
        best = {"font_pt": fs, "fits": False, "lines_total": total_lines,
                "height_needed_pt": None, "height_avail_pt": box_h_in * 72.0, "action": "trim"}
    return best


def budget_title(slide, box_w_in, font_pt, max_lines=2):
    lines = measure_lines(slide.get("title", ""), box_w_in, font_pt)
    return {"lines": lines, "fits": lines <= max_lines}


def check_notes(slide, body_text):
    """Notes must exist, be substantial, and not duplicate the page text."""
    notes = (slide.get("notes") or "").strip()
    if not notes:
        return {"ok": False, "reason": "notes_missing"}
    if len(notes) < 40:
        return {"ok": False, "reason": "notes_too_short", "len": len(notes)}
    if len(notes) > 800:
        return {"ok": False, "reason": "notes_too_long", "len": len(notes)}
    body = re.sub(r"\s+", "", body_text or "")
    nn = re.sub(r"\s+", "", notes)
    if body and nn[: len(body)] == body:
        return {"ok": False, "reason": "notes_duplicate_body"}
    inter = set(body) & set(nn)
    ratio = len(inter) / max(1, len(set(body) | set(nn)))
    if body and ratio > 0.85:
        return {"ok": False, "reason": "notes_near_duplicate", "jaccard": round(ratio, 2)}
    return {"ok": True, "len": len(notes)}


if __name__ == "__main__":
    import json
    import sys
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    for i, s in enumerate(spec.get("slides", []), 1):
        print(i, budget_slide(s, 11.5, 5.0))
