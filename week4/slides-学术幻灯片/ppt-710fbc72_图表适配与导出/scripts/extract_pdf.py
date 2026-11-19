#!/usr/bin/env python3
"""extract_pdf.py — 论文 PDF 提取：文本锚点 + 图表导出 + manifest。

输出（写入 --outdir）:
  paper_text.txt           全文，按 "===== PAGE n =====" 分页（页码=证据锚点）
  figures/fig_p{page}_{i}.png   内嵌位图 >= --min-size px
  manifest.json            每页字符数/图数/是否扫描件

策略：PyMuPDF(fitz) > pdftotext > 无提取器时如实落 fail manifest。
材料非 PDF（markdown/txt）时直接复制为 paper_text.txt 并登记 note。
失败路径退出码恒 0，结论走 JSON。

用法: python3 extract_pdf.py paper.pdf --outdir /app/work/extracted
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
    text_parts, manifest_pages = [], []
    figures_dir = os.path.join(outdir, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    fig_count = 0
    for pno, page in enumerate(doc, start=1):
        t = page.get_text("text")
        text_parts.append("===== PAGE %d =====" % pno)
        text_parts.append(t)
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
                imgs.append({"file": "figures/" + fname, "w": pix.width, "h": pix.height, "page": pno})
            except Exception:
                continue
        imgs.sort(key=lambda d: -(d["w"] * d["h"]))
        manifest_pages.append({"page": pno, "chars": len(t), "images": imgs})
    return {"tool": "pymupdf", "pages": doc.page_count, "text_file": "paper_text.txt",
            "pages_meta": manifest_pages, "figures_total": fig_count,
            "scanned": doc.page_count > 0 and all(p["chars"] < 40 for p in manifest_pages)}


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


def extract_plain_text(src, outdir):
    """非 PDF 材料（txt/md/json）：整文件复制为 paper_text.txt。"""
    dst = os.path.join(outdir, "paper_text.txt")
    shutil.copyfile(src, dst)
    with open(dst, encoding="utf-8", errors="replace") as f:
        content = f.read()
    return {"tool": "plain_copy", "pages": None, "text_file": "paper_text.txt",
            "pages_meta": [], "figures_total": 0, "scanned": False,
            "note": "非 PDF 材料：locator 用章节标题而非页码"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--outdir", default="extracted")
    ap.add_argument("--min-size", type=int, default=MIN_SIZE_DEFAULT)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    meta, err = None, None
    lower = (args.pdf or "").lower()
    if not os.path.exists(args.pdf):
        err = "not_found: %s" % args.pdf
    elif lower.endswith((".txt", ".md", ".json", ".csv")):
        try:
            meta = extract_plain_text(args.pdf, args.outdir)
        except Exception as e:
            err = "plain_copy failed: %s" % e
    elif lower.endswith(".pdf"):
        try:
            meta = extract_with_fitz(args.pdf, args.outdir, args.min_size)
        except Exception as e:
            err = "fitz failed: %s" % e
            try:
                meta = extract_with_pdftotext(args.pdf, args.outdir)
            except Exception as e2:
                err += " | pdftotext failed: %s" % e2
    else:
        try:
            meta = extract_with_fitz(args.pdf, args.outdir, args.min_size)
        except Exception:
            try:
                meta = extract_plain_text(args.pdf, args.outdir)
            except Exception as e:
                err = "unrecognized format and both extractors failed: %s" % e

    if meta is None:
        manifest = {"ok": False, "error": err or "no extractor available",
                    "fallback": "locator_by_section_title", "warnings": ["extraction_failed"]}
        with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print(json.dumps(manifest, ensure_ascii=False))
        return 0

    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": True, **meta}, f, ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "tool": meta["tool"], "pages": meta["pages"],
                      "figures": meta["figures_total"], "scanned": meta["scanned"],
                      "outdir": args.outdir}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
