#!/usr/bin/env python3
"""extract_pdf.py — pull text and figure images out of a paper PDF.

Outputs (into --outdir):
  paper_text.txt      full text, one section per page separated by
                      "===== PAGE n =====" markers (page numbers = evidence anchors)
  figures/fig_p{page}_{i}.png   embedded raster images >= --min-size px
  figures/manifest.json         what was found: per-page image count/sizes,
                      whether the PDF looks scanned (needs OCR), etc.

Strategy:
  1. PyMuPDF (fitz) if importable — text + embedded images + flags
  2. pdftotext (poppler) fallback for text
  3. If neither: honest failure (exit 4), no fake text.

Usage: python extract_pdf.py paper.pdf --outdir extracted/
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

MIN_SIZE_DEFAULT = 180


def extract_with_fitz(pdf, outdir, min_size):
    import fitz
    doc = fitz.open(pdf)
    text_parts = []
    manifest_pages = []
    figures_dir = os.path.join(outdir, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    fig_count = 0
    for pno, page in enumerate(doc, start=1):
        text_parts.append("===== PAGE %d =====" % pno)
        text_parts.append(page.get_text("text"))
        imgs = []
        for i, info in enumerate(page.get_images(full=True), start=1):
            xref = info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.width < min_size or pix.height < min_size:
                    continue
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fig_count += 1
                fname = "fig_p%d_%d.png" % (pno, i)
                pix.save(os.path.join(figures_dir, fname))
                imgs.append({"file": "figures/" + fname, "w": pix.width, "h": pix.height,
                             "page": pno})
            except Exception:
                continue
        imgs.sort(key=lambda d: -(d["w"] * d["h"]))
        manifest_pages.append({"page": pno, "chars": len(page.get_text("text")),
                               "images": imgs})
    return {
        "tool": "pymupdf",
        "pages": doc.page_count,
        "text_file": "paper_text.txt",
        "pages_meta": manifest_pages,
        "figures_total": fig_count,
        "scanned": doc.page_count > 0 and all(p["chars"] < 40 for p in manifest_pages),
    }


def extract_with_pdftotext(pdf, outdir):
    pt = shutil.which("pdftotext")
    if not pt:
        return None
    txt_out = os.path.join(outdir, "paper_text.txt")
    r = subprocess.run([pt, "-layout", pdf, txt_out], capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(txt_out):
        return None
    with open(txt_out, encoding="utf-8", errors="replace") as f:
        content = f.read()
    pages = content.count("\f") + 1
    return {"tool": "pdftotext", "pages": pages, "text_file": "paper_text.txt",
            "pages_meta": [], "figures_total": 0,
            "scanned": len(content) < 400 and pages <= 3,
            "note": "no figure extraction without PyMuPDF; render pages instead"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--outdir", default="extracted")
    ap.add_argument("--min-size", type=int, default=MIN_SIZE_DEFAULT)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    meta = None
    err = None
    try:
        meta = extract_with_fitz(args.pdf, args.outdir, args.min_size)
    except Exception as e:
        err = "fitz failed: %s" % e
        try:
            meta = extract_with_pdftotext(args.pdf, args.outdir)
        except Exception as e2:
            err += " | pdftotext failed: %s" % e2
    if meta is None:
        print(json.dumps({"ok": False, "error": err or "no extractor available"}, ensure_ascii=False))
        sys.exit(4)

    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": True, **meta}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "tool": meta["tool"], "pages": meta["pages"],
                      "figures": meta["figures_total"], "scanned": meta["scanned"],
                      "outdir": args.outdir}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(3)
