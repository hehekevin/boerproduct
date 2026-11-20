#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — docx → PDF/PNG 预览（可选，失败不阻塞）
用法: python render_preview.py --src /app/output/revised.docx --outdir /app/output/previews
容错: ①soffice/libreoffice ②docx2pdf ③跳过并登记，exit 0
"""
import argparse, json, os, shutil, subprocess, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/app/output/revised.docx")
    ap.add_argument("--outdir", default="/app/output/previews")
    args = ap.parse_args()
    log = {"src": args.src, "rendered": False, "pdf": None, "png": None, "tool": None, "reason": None}
    try:
        if not os.path.exists(args.src):
            log["reason"] = "源文件不存在: %s" % args.src
        else:
            os.makedirs(args.outdir, exist_ok=True)
            soffice = shutil.which("soffice") or shutil.which("libreoffice")
            pdf = os.path.join(args.outdir, os.path.splitext(os.path.basename(args.src))[0] + ".pdf")
            if soffice:
                subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                                "--outdir", args.outdir, args.src],
                               capture_output=True, timeout=120)
                if os.path.exists(pdf): log.update({"rendered": True, "pdf": pdf, "tool": "soffice"})
            if not log["rendered"]:
                try:
                    from docx2pdf import convert
                    convert(args.src, pdf); 
                    if os.path.exists(pdf): log.update({"rendered": True, "pdf": pdf, "tool": "docx2pdf"})
                except Exception as e2:
                    log["reason"] = "soffice/docx2pdf 均不可用: %s" % e2
            if log["rendered"]:
                try:
                    import fitz
                    pg = fitz.open(pdf)[0]
                    png = os.path.join(args.outdir, os.path.splitext(os.path.basename(pdf))[0] + ".png")
                    pg.get_pixmap(dpi=110).save(png); log["png"] = png
                except Exception:
                    log["png"] = None  # PDF 已足够核验
    except Exception as e:
        log["reason"] = str(e)
    os.makedirs(os.path.dirname(args.outdir) or ".", exist_ok=True)
    json.dump(log, open(os.path.join(args.outdir, "render_log.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(log, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
