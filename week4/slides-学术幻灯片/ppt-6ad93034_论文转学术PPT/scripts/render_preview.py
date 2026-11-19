#!/usr/bin/env python3
"""render_preview.py — presentation.pptx → PDF 导出 → 逐页预览，降级链 + 如实登记。

链路：
  PDF:  soffice/libreoffice → PowerPoint COM(Windows) → PyMuPDF 页级 SVG 兜底
  PNG:  pdftoppm/mutool/gs/PyMuPDF
无任何渲染器时 status=no_renderer 如实登记（不伪造 PDF/PNG），退出码恒 0。

用法: python3 render_preview.py presentation.pptx --outdir /app/output/previews --log render_log.json
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def which_any(names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def soffice_pdf(pptx, outdir):
    soffice = which_any(["soffice", "libreoffice", "loffice"])
    for pat in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                "/usr/bin/soffice", "/usr/local/bin/soffice", "/opt/libreoffice/program/soffice"):
        if os.path.exists(pat):
            soffice = pat
            break
    if not soffice:
        return None, "no soffice binary"
    try:
        r = subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf",
                            "--outdir", outdir, os.path.abspath(pptx)],
                           capture_output=True, timeout=180, text=True)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if os.path.exists(pdf):
            return pdf, "soffice ok"
        return None, "soffice rc=%s %s" % (r.returncode, (r.stderr or "")[:200])
    except Exception as e:
        return None, "soffice failed: %s" % e


def svg_fallback(pptx, outdir):
    """无 Office 渲染器：stdlib 直读 pptx，逐页手绘 SVG 预览（零外部依赖）。"""
    try:
        z = zipfile.ZipFile(pptx)
        names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                       key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        W, H = 1280, 720
        outs = []
        from xml.sax.saxutils import escape
        for i, n in enumerate(names, 1):
            root = ET.fromstring(z.read(n))
            items = []
            for sp in root.iter("{http://schemas.openxmlformats.org/presentationml/2006/main}sp"):
                off = sp.find(".//{%s}off" % NS_A)
                ext = sp.find(".//{%s}ext" % NS_A)
                texts = [t.text for t in sp.iter("{%s}t" % NS_A) if t.text and t.text.strip()]
                if not texts:
                    continue
                x = int(off.get("x")) / 12192000 * W if off is not None else 40
                y = int(off.get("y")) / 6858000 * H if off is not None else 40
                cx = int(ext.get("cx")) / 12192000 * W if ext is not None else W - 80
                items.append((x, y, min(cx, W - x - 10), " ".join(texts)[:600]))
            svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">' % (W, H, W, H),
                   '<rect width="%d" height="%d" fill="white"/>' % (W, H)]
            for x, y, w, txt in items:
                fs = 20 if y < H * 0.2 else 14
                svg.append('<text x="%d" y="%d" font-size="%d" fill="#1A1A1A" font-family="sans-serif">%s</text>'
                           % (int(x) + 8, int(y) + fs + 6, fs, escape(txt)))
            svg.append("</svg>")
            out = os.path.join(outdir, "slide-%02d.svg" % i)
            with open(out, "w", encoding="utf-8") as f:
                f.write("".join(svg))
            outs.append(out)
        return outs
    except Exception:
        return []


def pngs_from_pdf(pdf, outdir, stem):
    tool = which_any(["pdftoppm", "mutool", "gs"])
    if tool:
        base = os.path.join(outdir, stem)
        try:
            bn = os.path.basename(tool)
            if bn == "pdftoppm":
                subprocess.run([tool, "-png", "-r", "110", pdf, base], capture_output=True, timeout=180)
            elif bn == "mutool":
                subprocess.run([tool, "draw", "-o", base + "-page%d.png", "-r", "110", pdf],
                               capture_output=True, timeout=180)
            else:
                subprocess.run([tool, "-sDEVICE=png16m", "-r110", "-o", base + "-page-%03d.png", pdf],
                               capture_output=True, timeout=180)
            pngs = sorted(glob.glob(base + "*.png"))
            if pngs:
                return pngs, bn
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
        return [], None


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("pptx")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    outdir = args.outdir or (os.path.splitext(args.pptx)[0] + "_previews")
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.pptx))[0]
    log = {"pptx": args.pptx, "outdir": outdir, "steps": [], "degrade_chain": []}

    pdf, note = soffice_pdf(args.pptx, outdir)
    log["steps"].append({"step": "pdf", "tool": "soffice", "ok": bool(pdf), "note": note})
    result = {"pdf": pdf, "pngs": [], "svgs": [], "png_tool": None}
    if not pdf:
        try:
            import win32com.client  # noqa
            app = win32com.client.Dispatch("PowerPoint.Application")
            pres = app.Presentations.Open(os.path.abspath(args.pptx), WithWindow=False)
            out_pdf = os.path.join(outdir, stem + ".pdf")
            pres.SaveAs(out_pdf, 32)
            pres.Close()
            pdf = out_pdf if os.path.exists(out_pdf) else None
            log["steps"].append({"step": "pdf", "tool": "powerpoint-com", "ok": bool(pdf)})
        except Exception as e:
            log["steps"].append({"step": "pdf", "tool": "powerpoint-com", "ok": False, "note": str(e)[:160]})
        result["pdf"] = pdf

    if result["pdf"]:
        pngs, tool = pngs_from_pdf(result["pdf"], outdir, stem)
        result["pngs"], result["png_tool"] = pngs, tool
        log["steps"].append({"step": "png", "tool": tool or "none", "ok": bool(pngs), "count": len(pngs)})
        log["status"] = "ok" if pngs else "pdf_only_no_png"
    else:
        log["degrade_chain"].append({"stage": "render", "fallback": "svg_preview",
                                     "reason": "no PDF renderer available"})
        svgs = svg_fallback(args.pptx, outdir)
        result["svgs"] = svgs
        log["steps"].append({"step": "svg", "tool": "stdlib", "ok": bool(svgs), "count": len(svgs)})
        log["status"] = "svg_only_no_pdf" if svgs else "no_renderer"
        if not svgs:
            log["degrade_chain"].append({"stage": "render", "fallback": "none",
                                         "reason": "pptx unreadable by stdlib"})

    result["sizes_bytes"] = {k: os.path.getsize(result[k]) for k in ("pdf",) if result.get(k)}
    log["result"] = {k: (len(v) if isinstance(v, list) else v) for k, v in result.items() if k != "svgs"}
    log_path = args.log or os.path.join(outdir, "render_log.json")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log["log_write_error"] = str(e)
    print(json.dumps({"status": log["status"], "pdf": result["pdf"],
                      "pngs": len(result["pngs"]), "svgs": len(result["svgs"]), "log": log_path},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
