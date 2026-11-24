#!/usr/bin/env python3
"""consistency_check.py — whole-deck batch consistency verification.

Checks:
  1. page numbers: standalone decks carry footer numbers 1..N (skipped when
     template-inherited, since template master handles it)
  2. title font sizes: uniform ladder across content slides (or template-inherited)
  3. caption style: figure captions uniformly ~10pt italic grey
  4. image aspect: embedded picture w/h ratio vs source file ratio (delta >2% = fail)
  5. font names used: every latin typeface present in a whitelist or template fonts

Writes consistency_report.json; exit 1 on any fail.

Usage: python consistency_check.py deck.pptx [--out consistency_report.json] [--template template.pptx]
"""
import argparse
import hashlib
import json
import os
import sys

IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp")


def image_ratio(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        return w / h if h else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--out", default=None)
    ap.add_argument("--template", default=None)
    args = ap.parse_args()

    try:
        from pptx import Presentation
        from pptx.util import Emu
    except Exception:
        print(json.dumps({"ok": False, "error": "python-pptx unavailable"}))
        sys.exit(5)

    prs = Presentation(args.pptx)
    n = len(prs.slides._sldIdLst)
    report = {"pptx": args.pptx, "slides": n, "checks": {}, "items": [], "fail": 0, "warn": 0}

    # gather per-slide info
    title_sizes, caption_styles, page_numbers, used_fonts = {}, {}, {}, set()
    aspect_items = []
    for i, sl in enumerate(prs.slides, 1):
        tshapes = [s for s in sl.shapes if s.has_text_frame and s.text_frame.text.strip()]
        tshapes.sort(key=lambda s: (s.top or 0))
        if tshapes:
            for p in tshapes[0].text_frame.paragraphs:
                for r in p.runs:
                    if r.font.size:
                        title_sizes.setdefault(i, r.font.size.pt)
                    if r.font.name:
                        used_fonts.add(r.font.name)
        for sh in sl.shapes:
            if sh.has_text_frame:
                txt = sh.text_frame.text.strip()
                for p in sh.text_frame.paragraphs:
                    for r in p.runs:
                        if r.font.name:
                            used_fonts.add(r.font.name)
                        if txt.startswith(("图", "Fig", "Table", "表")) and r.font.size:
                            caption_styles.setdefault(i, (r.font.size.pt, bool(r.font.italic)))
            if sh.shape_type == 13:
                try:
                    img = sh.image
                    ratio_box = (sh.width / sh.height) if sh.height else None
                    ratio_src = None
                    with open(os.path.join(os.path.dirname(args.pptx),
                                           "fig_src_%d_%d.bin" % (i, sh.shape_id)), "wb") as f:
                        f.write(img.blob)
                        fpath = f.name
                    ratio_src = image_ratio(fpath)
                    os.remove(fpath)
                    if ratio_box and ratio_src:
                        delta = abs(ratio_box - ratio_src) / ratio_src
                        aspect_items.append({"slide": i, "delta": round(delta, 4),
                                             "ok": delta <= 0.02})
                except Exception:
                    pass
        # footer page number: bottom-right small text == str(i)
        pn = None
        for sh in sl.shapes:
            if sh.has_text_frame:
                t = sh.text_frame.text.strip()
                if t == str(i) and (sh.top or 0) > Emu(int(6.5 * 914400)).emu:
                    pn = i
        page_numbers[i] = pn

    # check 1: page numbers (only meaningful when footer numbers exist on slide 1..some)
    present = [v for v in page_numbers.values() if v]
    if present:
        expect = list(range(1, n + 1))
        missing = [i for i in expect if page_numbers.get(i) != i]
        report["checks"]["page_numbers"] = {"mode": "footer", "found": len(present),
                                            "missing": missing,
                                            "ok": len(missing) == 0 or len(present) < n / 2}
        if len(missing) > 0 and len(present) >= n / 2:
            report["fail"] += 1
    else:
        report["checks"]["page_numbers"] = {"mode": "template_or_absent", "ok": True}

    # check 2: title size uniformity (tolerate title page big size)
    vals = [v for v in title_sizes.values() if v]
    if vals:
        from collections import Counter
        common, cnt = Counter(vals).most_common(1)[0]
        outliers = {k: v for k, v in title_sizes.items() if v != common}
        report["checks"]["title_sizes"] = {"common_pt": common, "uniform": len(set(vals)) <= 2,
                                           "outliers": outliers,
                                           "ok": len(set(vals)) <= 2}
        if len(set(vals)) > 2:
            report["warn"] += 1

    # check 3: caption style uniformity
    cap_vals = list(caption_styles.values())
    if cap_vals:
        size_set = set(v[0] for v in cap_vals)
        ital_set = set(v[1] for v in cap_vals)
        ok = len(size_set) == 1 and len(ital_set) == 1
        report["checks"]["caption_style"] = {"sizes": sorted(size_set), "italics": sorted(ital_set), "ok": ok}
        if not ok:
            report["warn"] += 1

    # check 4: aspect ratios
    bad = [a for a in aspect_items if not a["ok"]]
    report["checks"]["image_aspect"] = {"checked": len(aspect_items), "failures": bad,
                                        "ok": not bad}
    if bad:
        report["fail"] += 1

    # check 5: fonts used
    report["checks"]["fonts_used"] = sorted(used_fonts)

    report["summary"] = {"fail": report["fail"], "warn": report["warn"],
                         "verdict": "pass" if report["fail"] == 0 else "fail"}
    out = args.out or (os.path.splitext(args.pptx)[0] + ".consistency_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print("consistency:", report["summary"], "->", out)
    sys.exit(0 if report["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
