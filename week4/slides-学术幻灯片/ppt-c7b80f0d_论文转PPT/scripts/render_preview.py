#!/usr/bin/env python3
"""render_preview.py — deck.pptx -> deck.pdf -> per-page PNGs, with honest logging.

Tries, in order:
  PDF:    soffice | libreoffice | loffice (LibreOffice), then MS PowerPoint COM (Windows)
  PNG:    pdftoppm | mutool | gs | python3 fitz (PyMuPDF)

Writes render_log.json: tool used, page count, per-page files, bytes, failures.
Never fakes a success: if no renderer exists, records status "no_renderer"
and exits 3 (caller should still keep pptx and report honestly).

Usage: python3 render_preview.py deck.pptx --outdir previews/ [--log render_log.json]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys


def which_any(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def soffice_pdf(pptx, outdir):
    soffice = which_any(["soffice", "libreoffice", "loffice"])
    if not soffice:
        # common install paths
        for pat in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                    "/usr/bin/soffice", "/usr/local/bin/soffice", "/opt/libreoffice/program/soffice"):
            if os.path.exists(pat):
                soffice = pat
                break
    if not soffice:
        return None, "no soffice/libreoffice binary"
    cmd = [soffice, "--headless", "--norestore", "--convert-to", "pdf",
           "--outdir", outdir, os.path.abspath(pptx)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180, text=True)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if os.path.exists(pdf):
            return pdf, "soffice ok (rc=%s)" % r.returncode
        return None, "soffice rc=%s stderr=%s" % (r.returncode, (r.stderr or "")[:300])
    except Exception as e:
        return None, "soffice failed: %s" % e


def pngs_from_pdf(pdf, outdir, stem):
    pdftoppm = which_any(["pdftoppm", "mutool", "gs"])
    if pdftoppm:
        base = os.path.join(outdir, stem)
        try:
            if os.path.basename(pdftoppm) == "pdftoppm":
                subprocess.run([pdftoppm, "-png", "-r", "110", pdf, base],
                               capture_output=True, timeout=180)
            elif os.path.basename(pdftoppm) == "mutool":
                subprocess.run([pdftoppm, "draw", "-o", base + "-page%d.png", "-r", "110", pdf],
                               capture_output=True, timeout=180)
            else:
                subprocess.run([pdftoppm, "-sDEVICE=png16m", "-r110", "-o",
                                base + "-page-%03d.png", pdf], capture_output=True, timeout=180)
            pngs = sorted(glob.glob(base + "*.png"))
            if pngs:
                return pngs, os.path.basename(pdftoppm)
        except Exception:
            pass
    try:
        import fitz
        doc = fitz.open(pdf)
        pngs = []
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=110)
            out = os.path.join(outdir, "%s-%02d.png" % (stem, i))
            pix.save(out)
            pngs.append(out)
        return pngs, "pymupdf"
    except Exception:
        pass
    return [], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    outdir = args.outdir or (os.path.splitext(args.pptx)[0] + "_previews")
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.pptx))[0]
    log = {"pptx": args.pptx, "outdir": outdir, "steps": [], "status": None}

    pdf, note = soffice_pdf(args.pptx, outdir)
    log["steps"].append({"step": "pdf", "tool": "soffice", "ok": bool(pdf), "note": note})
    result = {"pdf": pdf, "pngs": [], "png_tool": None}

    if not pdf:
        try:
            import win32com.client  # type: ignore
            ppt_app = win32com.client.Dispatch("PowerPoint.Application")
            pres = ppt_app.Presentations.Open(os.path.abspath(args.pptx), WithWindow=False)
            out_pdf = os.path.join(outdir, stem + ".pdf")
            pres.SaveAs(out_pdf, 32)
            pres.Close()
            pdf = out_pdf if os.path.exists(out_pdf) else None
            log["steps"].append({"step": "pdf", "tool": "powerpoint-com", "ok": bool(pdf)})
        except Exception as e:
            log["steps"].append({"step": "pdf", "tool": "powerpoint-com",
                                 "ok": False, "note": str(e)[:200]})
        result["pdf"] = pdf

    if pdf:
        pngs, tool = pngs_from_pdf(pdf, outdir, stem)
        result["pngs"] = pngs
        result["png_tool"] = tool
        log["steps"].append({"step": "png", "tool": tool or "none",
                             "ok": bool(pngs), "count": len(pngs)})

    if result["pdf"] and result["pngs"]:
        log["status"] = "ok"
        code = 0
    elif result["pdf"]:
        log["status"] = "pdf_only_no_png"
        code = 2
    else:
        log["status"] = "no_renderer"
        code = 3

    sizes = {}
    for key in ("pdf",):
        if result.get(key):
            sizes[key] = os.path.getsize(result[key])
    result["sizes_bytes"] = sizes
    log["result"] = result

    log_path = args.log or os.path.join(outdir, "render_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print(json.dumps({"status": log["status"], "pdf": result["pdf"],
                      "pngs": len(result["pngs"]), "log": log_path}, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
