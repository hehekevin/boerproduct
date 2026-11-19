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

class _Usage(Exception):
    """argparse 用法错误（缺必填参数）——按内容级失败处理，不中断交付链。"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(message)


def main():
    ap = _Parser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--outdir", required=True)
    try:
        args = ap.parse_args()
    except _Usage as e:
        print(json.dumps({"status": "skipped", "engine": None, "pdf": None, "pngs": 0,
                          "error": f"用法错误: {e}",
                          "hint": "用法: render_preview.py --src <docx> --outdir <dir>",
                          "note": "退出码恒 0：预览缺失不阻断交付，已如实记录。"}, ensure_ascii=False))
        return 0
    log = render(args.src, args.outdir)
    print(json.dumps({"status": log["status"], "engine": log["engine"],
                      "pdf": log["pdf"], "pngs": len(log["pngs"])}, ensure_ascii=False))
    return 0


def _safe_main():
    """顶层安全网：任何未捕获异常都记为内容级失败，退出码恒 0。"""
    try:
        return main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"status": "render_failed", "engine": None, "pdf": None, "pngs": 0,
                          "error": f"{type(e).__name__}: {e}",
                          "note": "退出码恒 0：预览缺失不阻断交付，已如实记录。"}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    sys.exit(_safe_main())
