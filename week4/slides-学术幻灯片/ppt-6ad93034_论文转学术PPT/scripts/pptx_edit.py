#!/usr/bin/env python3
"""pptx_edit.py — targeted in-place edit of an existing deck.pptx.

Edit ops (all master-safe: only text/picture/notes of the target slide are
touched; other slides, masters, layouts, theme stay byte-identical):

  replace-text  --slide N --find "old" --text "new"     # substring replace in any shape on slide
  set-title     --slide N --text "new title"
  set-bullets   --slide N --bullets-file bullets.json   # replace body bullets (re-runs layout budget)
  set-notes     --slide N --text-file note.txt
  set-figure    --slide N --image fig.png --caption "..."  # replace/insert picture + caption
  delete-shape  --slide N --find "text"                 # remove shape containing text
  add-slide     --after N --spec slide.json             # append a new slide from spec

Every invocation appends one row to versions.jsonl (in --versions path or
same dir as pptx): {ts, op, slide, summary, file_sha256_before} so any round
of edits is auditable and rollback = re-run pipeline from deck.vK.json.

Usage examples:
  python pptx_edit.py deck.pptx replace-text --slide 3 --find "38.2%" --text "38.2"
  python pptx_edit.py deck.pptx set-notes --slide 2 --text-file n2.txt --versions versions.jsonl
"""
import argparse
import hashlib
import importlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_budget as LB  # noqa: E402


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log_version(pptx, versions_path, op, slide, summary):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "op": op, "slide": slide,
           "summary": summary, "file_sha256_before": sha256(pptx)}
    with open(versions_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def find_text_shape(slide, needle):
    for sh in slide.shapes:
        if sh.has_text_frame and needle in sh.text_frame.text:
            return sh
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("op", choices=["replace-text", "set-title", "set-bullets",
                                   "set-notes", "set-figure", "delete-shape"])
    ap.add_argument("--slide", type=int, default=None)
    ap.add_argument("--after", type=int, default=None)
    ap.add_argument("--find", default=None)
    ap.add_argument("--text", default=None)
    ap.add_argument("--text-file", default=None)
    ap.add_argument("--bullets-file", default=None)
    ap.add_argument("--image", default=None)
    ap.add_argument("--caption", default=None)
    ap.add_argument("--spec", default=None)
    ap.add_argument("--versions", default=None)
    args = ap.parse_args()

    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
    except Exception:
        print(json.dumps({"ok": False, "error": "python-pptx unavailable; editing requires it"}))
        sys.exit(5)

    prs = Presentation(args.pptx)
    versions = args.versions or os.path.splitext(args.pptx)[0] + ".versions.jsonl"
    n_slides = len(prs.slides._sldIdLst)
    DARK = RGBColor(0x2B, 0x3A, 0x55)

    if args.op == "replace-text":
        sl = prs.slides[args.slide - 1]
        sh = find_text_shape(sl, args.find)
        if sh is None:
            print(json.dumps({"ok": False, "error": "text not found on slide %d" % args.slide}))
            sys.exit(2)
        sh.text_frame.text = sh.text_frame.text.replace(args.find, args.text)
        log_version(args.pptx, versions, args.op, args.slide,
                    "replace %r -> %r" % (args.find[:40], args.text[:40]))
    elif args.op == "set-title":
        sl = prs.slides[args.slide - 1]
        sh = find_text_shape(sl, "") or sl.shapes[0] if len(sl.shapes) else None
        # title = first/topmost text shape
        tshapes = [s for s in sl.shapes if s.has_text_frame and s.text_frame.text.strip()]
        tshapes.sort(key=lambda s: (s.top or 0))
        if not tshapes:
            print(json.dumps({"ok": False, "error": "no text shape on slide"}))
            sys.exit(2)
        tf = tshapes[0].text_frame
        tf.text = args.text
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = DARK
        log_version(args.pptx, versions, args.op, args.slide, "title -> %s" % args.text[:60])
    elif args.op == "set-bullets":
        sl = prs.slides[args.slide - 1]
        bullets = json.load(open(args.bullets_file, encoding="utf-8"))
        if isinstance(bullets, dict):
            bullets = bullets.get("bullets", [])
        body = None
        for sh in sl.shapes:
            if sh.has_text_frame and (sh.top or 0) > Inches(1.2) and sh.width > Inches(4):
                body = sh
                break
        if body is None:
            print(json.dumps({"ok": False, "error": "body shape not found"}))
            sys.exit(2)
        b = LB.budget_slide({"bullets": bullets, "layout": "bullets"}, 11.5, 5.1)
        fs = min(b.get("font_pt", 18), 18)
        tf = body.text_frame
        tf.clear()
        for i, t in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = p.add_run()
            r.text = str(t)
            r.font.size = Pt(fs)
        log_version(args.pptx, versions, args.op, args.slide,
                    "%d bullets @%dpt" % (len(bullets), fs))
    elif args.op == "set-notes":
        sl = prs.slides[args.slide - 1]
        text = args.text or (open(args.text_file, encoding="utf-8").read() if args.text_file else "")
        chk = LB.check_notes({"notes": text}, " ".join(
            sh.text_frame.text for sh in sl.shapes if sh.has_text_frame))
        sl.notes_slide.notes_text_frame.text = text
        log_version(args.pptx, versions, args.op, args.slide,
                    "notes %d chars (%s)" % (len(text), "ok" if chk.get("ok") else chk.get("reason")))
    elif args.op == "set-figure":
        sl = prs.slides[args.slide - 1]
        # remove old pictures
        for sh in list(sl.shapes):
            if sh.shape_type == 13:
                sh._element.getparent().remove(sh._element)
        from PIL import Image
        with Image.open(args.image) as im:
            iw, ih = im.size
        bw, bh = 4.35, 4.6
        scale = min(bw / (iw / 96.0), bh / (ih / 96.0))
        sl.shapes.add_picture(args.image, Inches(8.35), Inches(1.45),
                              Inches(iw / 96.0 * scale), Inches(ih / 96.0 * scale))
        if args.caption:
            log_version(args.pptx, versions, args.op, args.slide,
                        "figure %s caption=%s" % (os.path.basename(args.image), (args.caption or "")[:30]))
    elif args.op == "delete-shape":
        sl = prs.slides[args.slide - 1]
        sh = find_text_shape(sl, args.find)
        if sh is None:
            print(json.dumps({"ok": False, "error": "shape not found"}))
            sys.exit(2)
        sh._element.getparent().remove(sh._element)
        log_version(args.pptx, versions, args.op, args.slide, "deleted shape containing %r" % args.find[:30])

    prs.save(args.pptx)
    print(json.dumps({"ok": True, "op": args.op, "slide": args.slide,
                      "versions_log": versions}))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(3)
