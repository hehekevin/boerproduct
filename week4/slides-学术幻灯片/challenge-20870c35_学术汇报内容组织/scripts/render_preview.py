#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — 手写 SVG 逐页渲染（零外部依赖，无浏览器/无 node）。

从 deck 计划为每页生成 1280x720 SVG 预览 + index.html 目录；并探测平台
soffice/office-renderer 是否可把 pptx 转 PDF（有则转，无则如实登记
no_office_renderer，不伪造渲染结果）。退出码恒 0。
"""
import argparse, json, os, shutil, subprocess, sys
from xml.sax.saxutils import escape

W, H = 1280, 720
LINE_H = 44
MAX_LINES = 11


def _esc(s):
    return escape(str(s or ""))


def _wrap(text, width=34):
    out, line = [], ""
    for ch in str(text or ""):
        line += ch
        if len(line) >= width:
            out.append(line)
            line = ""
    if line:
        out.append(line)
    return out[:MAX_LINES]


def svg_slide(sl, idx, total):
    role = str(sl.get("role") or "")
    layout = str(sl.get("layout") or "bullets")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d">' % (W, H, W, H),
             '<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H)]
    if role in ("title", "closing"):
        parts.append('<text x="640" y="320" text-anchor="middle" font-size="44" '
                     'font-weight="bold" fill="#2B3A55" font-family="sans-serif">%s</text>'
                     % _esc(sl.get("title")))
        y = 390
        for ln in _wrap(sl.get("subtitle") or "", 40):
            parts.append('<text x="640" y="%d" text-anchor="middle" font-size="20" '
                         'fill="#444444" font-family="sans-serif">%s</text>' % (y, _esc(ln)))
            y += 32
    elif layout == "section":
        parts.append('<text x="640" y="380" text-anchor="middle" font-size="40" '
                     'font-weight="bold" fill="#2B5BA8" font-family="sans-serif">%s</text>'
                     % _esc(sl.get("title")))
    else:
        parts.append('<rect x="0" y="0" width="%d" height="6" fill="#2B5BA8"/>' % W)
        parts.append('<text x="50" y="80" font-size="30" font-weight="bold" fill="#2B3A55" '
                     'font-family="sans-serif">%s</text>' % _esc(sl.get("title")))
        y = 150
        claim = sl.get("claim")
        if claim:
            parts.append('<rect x="50" y="%d" width="%d" height="52" fill="#F2F5F9" '
                         'rx="8"/>' % (y - 34, W - 100))
            parts.append('<text x="66" y="%d" font-size="22" font-weight="bold" '
                         'fill="#2B5BA8" font-family="sans-serif">主张：%s</text>'
                         % (y, _esc(claim)))
            y += 66
        for b in (sl.get("bullets") or [])[:8]:
            for j, ln in enumerate(_wrap(b, 38)):
                pre = "•  " if j == 0 else "    "
                parts.append('<text x="60" y="%d" font-size="20" fill="#1A1A1A" '
                             'font-family="sans-serif">%s</text>' % (y, _esc(pre + ln)))
                y += LINE_H
                if y > H - 120:
                    break
            if y > H - 120:
                break
        tbl = (sl.get("table") or {}).get("rows")
        if tbl:
            yy = 160
            for ri, row in enumerate(tbl[:8]):
                parts.append('<text x="60" y="%d" font-size="18" %s fill="#1A1A1A" '
                             'font-family="sans-serif">%s</text>'
                             % (yy, 'font-weight="bold"' if ri == 0 else "",
                                _esc(" | ".join(str(c) for c in row[:5]))))
                yy += 36
    # 页脚：证据定位 + 页码（证据可追溯在预览层可见）
    locs = [str(e.get("locator") or "") for e in (sl.get("evidence") or [])
            if isinstance(e, dict) and e.get("locator")]
    if locs:
        parts.append('<text x="50" y="%d" font-size="13" fill="#6AA1C4" '
                     'font-family="sans-serif">证据: %s</text>'
                     % (H - 40, _esc("; ".join(locs)[:90])))
    parts.append('<text x="%d" y="%d" text-anchor="end" font-size="13" fill="#888888" '
                 'font-family="sans-serif">%d / %d</text>' % (W - 30, H - 40, idx, total))
    parts.append("</svg>")
    return "".join(parts)


def try_pdf(pptx, outdir, log):
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        log["pdf_status"] = "no_office_renderer"
        log["note"] = "本环境无 soffice/libreoffice，PDF 转换未执行；已交付 SVG 预览，不伪造渲染"
        return False
    try:
        r = subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir",
                            outdir, pptx], capture_output=True, timeout=180)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if os.path.exists(pdf):
            log["pdf_status"] = "ok"
            log["pdf"] = pdf
            return True
        log["pdf_status"] = "convert_failed"
        log["stderr"] = (r.stderr or b"").decode("utf-8", "ignore")[:300]
        return False
    except Exception as e:
        log["pdf_status"] = "convert_failed"
        log["stderr"] = str(e)[:300]
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--pptx", default=None)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    log = {"svg_ok": False, "pdf_status": "skipped_not_requested"}
    try:
        plan = json.load(open(args.plan, encoding="utf-8"))
        slides = [s for s in plan.get("slides", []) if isinstance(s, dict)]
        os.makedirs(args.outdir, exist_ok=True)
        for i, sl in enumerate(slides, start=1):
            with open(os.path.join(args.outdir, "slide_p%02d.svg" % i), "w",
                      encoding="utf-8") as f:
                f.write(svg_slide(sl, i, len(slides)))
        links = "".join('<li><a href="slide_p%02d.svg">第 %d 页 · %s</a></li>'
                        % (i, i, _esc(sl.get("title") or ""))
                        for i, sl in enumerate(slides, start=1))
        with open(os.path.join(args.outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write('<!DOCTYPE html><html><head><meta charset="utf-8">'
                    '<title>deck 预览目录（示意渲染，非正式案例结果）</title></head>'
                    '<body><h1>SVG 逐页预览（手写渲染）</h1><ul>%s</ul></body></html>' % links)
        log["svg_ok"] = True
        log["pages"] = len(slides)
        log["outdir"] = args.outdir
        if args.pptx and os.path.exists(args.pptx):
            log["requested_pdf"] = True
            try_pdf(args.pptx, args.outdir, log)
    except Exception as e:
        log["error"] = str(e)
    if args.log:
        try:
            json.dump(log, open(args.log, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
    print(json.dumps(log, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)  # 所有失败路径（含 argparse error）一律退出码 0

