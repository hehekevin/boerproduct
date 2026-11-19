#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — 交付物渲染预览（docx/md → PDF/PNG）
尽力而为、诚实记录：环境有 soffice/libreoffice/docx2pdf 则渲染并记录引擎；
没有渲染器时如实记 status=no_renderer，不伪造渲染成功。

用法:
  python3 render_preview.py --src /app/output/draft.docx --outdir /app/output/previews
"""
import argparse, json, os, shutil, subprocess, sys

def find_engine():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p, name
    for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 "/usr/bin/soffice", "/usr/local/bin/soffice",
                 "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(cand):
            return cand, "soffice"
    try:
        import docx2pdf  # type: ignore
        return "docx2pdf", "docx2pdf"
    except Exception:
        pass
    return None, None

def render(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    engine_path, engine = find_engine()
    log = {"src": src, "outdir": outdir, "engine": engine, "status": "no_renderer",
           "pdf": None, "pngs": []}
    if not engine:
        log["note"] = "环境中无 soffice/libreoffice/docx2pdf；未渲染。请如实记录，勿伪造。"
        json.dump(log, open(os.path.join(outdir, "render_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return log
    base = os.path.splitext(os.path.basename(src))[0]
    try:
        if engine == "docx2pdf":
            out_pdf = os.path.join(outdir, base + ".pdf")
            import docx2pdf  # type: ignore
            docx2pdf.convert(src, out_pdf)
        else:
            subprocess.run([engine_path, "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, src],
                           capture_output=True, timeout=180)
        pdf = os.path.join(outdir, base + ".pdf")
        if os.path.exists(pdf) and os.path.getsize(pdf) > 200:
            log["status"] = "ok"; log["pdf"] = os.path.abspath(pdf)
            # PDF→PNG（尽力）
            try:
                import fitz  # type: ignore
                doc = fitz.open(pdf)
                pngs = []
                for i, page in enumerate(doc, 1):
                    pix = page.get_pixmap(dpi=110)
                    fp = os.path.join(outdir, f"{base}_p{i}.png")
                    pix.save(fp); pngs.append(fp)
                    if i >= 8:
                        break
                log["pngs"] = pngs
            except Exception as e:
                log["png_note"] = f"pdf->png skipped: {e}"
        else:
            log["status"] = "render_failed"
            log["note"] = "转换命令执行但未得到有效 PDF"
    except Exception as e:
        log["status"] = "render_failed"
        log["error"] = str(e)[:400]
    json.dump(log, open(os.path.join(outdir, "render_log.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return log

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    try:
        log = render(args.src, args.outdir)
    except Exception as e:
        log = {"src": args.src, "outdir": args.outdir, "engine": None, "status": "render_failed",
               "pdf": None, "pngs": [], "error": str(e)[:300]}
        try:
            os.makedirs(args.outdir, exist_ok=True)
            json.dump(log, open(os.path.join(args.outdir, "render_log.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
    print(json.dumps({"status": log["status"], "engine": log["engine"],
                      "pdf": log["pdf"], "pngs": len(log["pngs"])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
