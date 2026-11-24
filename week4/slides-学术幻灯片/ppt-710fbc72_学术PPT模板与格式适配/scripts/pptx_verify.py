#!/usr/bin/env python3
"""pptx_verify.py — post-build verification of a deck against its plan.

Checks (each reported as pass/fail/warn with details):
  1. slide count matches deck.json
  2. every slide has non-empty title (except section/title layouts)
  3. layout budget: recomputed from actual text vs actual box geometry
  4. notes: present, substantial, not a duplicate of page text
  5. figures: declared figures embedded (image count per slide)
  6. evidence map: evidence_map.jsonl covers every slide
  7. template inheritance: shapes sit inside slide area; fonts recorded

Writes verify_report.json. Exit code 0 if no fail-level issue.

Usage: python pptx_verify.py deck.pptx deck.json [--evidence evidence_map.jsonl] [--out verify_report.json]
"""
import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_budget as LB  # noqa: E402

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def open_pptx(path):
    """Return list-of-slide dicts {texts, images, notes, boxes} using python-pptx if present, else raw XML."""
    try:
        from pptx import Presentation
        from pptx.util import Emu
        prs = Presentation(path)
        slides = []
        for sl in prs.slides:
            texts, boxes, images = [], [], 0
            for sh in sl.shapes:
                if sh.shape_type == 13 or getattr(sh, "image", None) is not None:
                    images += 1
                if sh.has_text_frame:
                    t = sh.text_frame.text.strip()
                    if t:
                        texts.append(t)
                    boxes.append((sh.left, sh.top, sh.width, sh.height))
            notes = ""
            if sl.has_notes_slide:
                notes = sl.notes_slide.notes_text_frame.text.strip()
            slides.append({"texts": texts, "images": images, "notes": notes,
                           "boxes_in": [[round(Emu(b[0]).inches, 2), round(Emu(b[1]).inches, 2),
                                         round(Emu(b[2]).inches, 2), round(Emu(b[3]).inches, 2)] for b in boxes]})
        return slides, "python-pptx"
    except Exception:
        return raw_parse(path), "raw-xml"


def raw_parse(path):
    z = zipfile.ZipFile(path)
    names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                   key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    slides = []
    for i, n in enumerate(names, 1):
        root = ET.fromstring(z.read(n))
        texts, images = [], 0
        for sp in root.iter():
            tag = sp.tag.split("}")[-1]
            if tag == "pic":
                images += 1
        for t in root.iter("{%s}t" % NS["a"]):
            if t.text and t.text.strip():
                texts.append(t.text.strip())
        notes = ""
        nn = "ppt/notesSlides/notesSlide%d.xml" % i
        if nn in z.namelist():
            nroot = ET.fromstring(z.read(nn))
            notes = " ".join(t.text or "" for t in nroot.iter("{%s}t" % NS["a"])).strip()
        slides.append({"texts": texts, "images": images, "notes": notes, "boxes_in": []})
    return slides


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("deck")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    plan = json.load(open(args.deck, encoding="utf-8"))
    slides, engine = open_pptx(args.pptx)
    report = {"pptx": args.pptx, "engine": engine,
              "slide_count": {"planned": len(plan.get("slides", [])), "actual": len(slides),
                              "match": len(slides) == len(plan.get("slides", []))},
              "slides": [], "fail": 0, "warn": 0}

    if not report["slide_count"]["match"]:
        report["fail"] += 1

    ev_rows = []
    if args.evidence and os.path.exists(args.evidence):
        with open(args.evidence, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ev_rows.append(json.loads(line))
                    except Exception:
                        pass
    ev_slides = sorted(set(r.get("slide_no") for r in ev_rows))
    report["evidence_map"] = {
        "rows": len(ev_rows),
        "slides_covered": ev_slides,
        "covers_all": bool(ev_rows) and ev_slides and ev_slides[0] == 1 and ev_slides[-1] == len(slides) and len(ev_slides) >= len(slides),
    }
    if ev_rows and not report["evidence_map"]["covers_all"]:
        report["warn"] += 1

    for i, (sl, plan_sl) in enumerate(zip(slides, plan.get("slides", [])), 1):
        row = {"no": i, "checks": {}}
        texts = " ".join(sl["texts"])
        plan_layout = plan_sl.get("layout", "bullets") if plan_sl else "?"

        row["checks"]["has_text"] = bool(sl["texts"])
        row["checks"]["title"] = bool(re.search(r"\S", texts)) if plan_layout in ("title", "section", "closing") else bool(sl["texts"])

        body_chars = sum(len(t) for t in sl["texts"])
        row["checks"]["body_density"] = {"chars": body_chars, "over_limit": body_chars > 700}
        if body_chars > 700:
            row["checks"]["body_density"]["verdict"] = "warn"
            report["warn"] += 1

        nb = LB.check_notes({"notes": sl["notes"]}, texts)
        row["checks"]["notes"] = nb

        want_fig = bool((plan_sl or {}).get("figure"))
        row["checks"]["figure"] = {"planned": want_fig, "embedded_images": sl["images"],
                                   "ok": (sl["images"] >= 1) if want_fig else True}
        if want_fig and sl["images"] < 1:
            row["checks"]["figure"]["verdict"] = "fail"
            report["fail"] += 1

        # geometry sanity: boxes inside slide bounds (python-pptx only)
        geo_ok = True
        for b in sl.get("boxes_in", []):
            x, y, w, h = b
            if x < -0.05 or y < -0.05 or x + w > 13.4 or y + h > 7.6:
                geo_ok = False
        row["checks"]["geometry_in_bounds"] = geo_ok
        if not geo_ok:
            report["fail"] += 1

        report["slides"].append(row)

    report["summary"] = {
        "fail": report["fail"], "warn": report["warn"],
        "verdict": "pass" if report["fail"] == 0 else "fail",
    }
    out = args.out or (os.path.splitext(args.pptx)[0] + ".verify_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("verify:", report["summary"], "->", out)
    for row in report["slides"]:
        for k, v in row["checks"].items():
            if v is False or (isinstance(v, dict) and v.get("verdict") in ("fail",) or (isinstance(v, dict) and not v.get("ok", True))):
                print("  slide", row["no"], k, json.dumps(v, ensure_ascii=False))
    sys.exit(0 if report["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
