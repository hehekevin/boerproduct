#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — SVG 思维导图 → PNG 真实渲染 + 像素级校验证据
尽力而为、诚实记录：环境有 cairosvg / svglib / rsvg-convert / inkscape / playwright 则渲染 PNG，
并对 PNG 做**像素校验**（尺寸非零、非空白像素占比），证据写入 render_log.json 供 result.json 引用。
没有渲染器时如实记 status=no_renderer（SVG 本身仍是可交付的渲染产物），不伪造渲染成功。

用法:
  python render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
"""
import argparse, json, os, shutil, subprocess, sys

def render_png(svg_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    png_path = os.path.join(outdir, "mindmap.png")
    log = {"src": svg_path, "png": None, "engine": None, "status": "no_renderer",
           "png_bytes": 0, "width": 0, "height": 0, "nonwhite_ratio": None, "note": ""}
    # 1) cairosvg
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1500, background_color="#ffffff")
        log["engine"] = "cairosvg"
    except Exception:
        # 2) svglib + reportlab
        try:
            from svglib.svglib import svg2rlg  # type: ignore
            from reportlab.graphics import renderPM  # type: ignore
            drawing = svg2rlg(svg_path)
            renderPM.drawToFile(drawing, png_path, fmt="PNG")
            log["engine"] = "svglib"
        except Exception:
            # 3) 命令行 rsvg-convert / inkscape
            engine_path, engine = None, None
            for name in ("rsvg-convert", "inkscape"):
                p = shutil.which(name)
                if p:
                    engine_path, engine = p, name
                    break
            if engine == "rsvg-convert":
                try:
                    subprocess.run([engine_path, "-o", png_path, "-w", "1500", svg_path],
                                   capture_output=True, timeout=120)
                    log["engine"] = "rsvg-convert"
                except Exception as e:
                    log["note"] = f"rsvg-convert failed: {str(e)[:150]}"
            elif engine == "inkscape":
                try:
                    subprocess.run([engine_path, svg_path, "--export-type=png",
                                    f"--export-filename={png_path}", "-w", "1500"],
                                   capture_output=True, timeout=120)
                    log["engine"] = "inkscape"
                except Exception as e:
                    log["note"] = f"inkscape failed: {str(e)[:150]}"
            else:
                # 4) playwright + chromium（常见于评测镜像预装）
                try:
                    from playwright.sync_api import sync_playwright  # type: ignore
                    with sync_playwright() as p:
                        browser = p.chromium.launch()
                        page = browser.new_page(viewport={"width": 1560, "height": 1100})
                        page.goto("file://" + os.path.abspath(svg_path).replace("\\", "/"))
                        page.wait_for_timeout(500)
                        page.screenshot(path=png_path, full_page=True)
                        browser.close()
                    log["engine"] = "playwright-chromium"
                except Exception:
                    log["note"] = "无 cairosvg/svglib/rsvg-convert/inkscape/playwright；未渲染 PNG。SVG 已交付。"
    if not os.path.exists(png_path):
        return log
    size = os.path.getsize(png_path)
    if size < 500:
        log["status"] = "render_failed"
        log["note"] = f"PNG 过小({size}B) 判为无效"
        os.remove(png_path)
        return log
    log["png"] = os.path.abspath(png_path)
    log["png_bytes"] = size
    # 像素校验：非空白像素占比
    try:
        from PIL import Image  # type: ignore
        img = Image.open(png_path).convert("L")
        log["width"], log["height"] = img.size
        hist = img.histogram()
        total = sum(hist)
        # 255=纯白；统计非纯白像素
        nonwhite = total - hist[255]
        log["nonwhite_ratio"] = round(nonwhite / max(total, 1), 4)
        if log["nonwhite_ratio"] < 0.01:
            log["status"] = "render_failed"
            log["note"] = "PNG 几乎全白（nonwhite_ratio<0.01），判为无效渲染"
            os.remove(png_path)
            log["png"] = None
        else:
            log["status"] = "ok"
    except Exception as e:
        # 无 PIL 时至少记录字节与尺寸证据
        log["status"] = "ok_no_pixel_check"
        log["note"] = f"无 PIL，仅字节校验: {str(e)[:100]}"
    return log

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.svg):
        print(json.dumps({"status": "error", "note": f"SVG 不存在: {args.svg}"}, ensure_ascii=False))
        return 1
    log = render_png(args.svg, args.outdir)
    rp = os.path.join(args.outdir, "render_log.json")
    os.makedirs(args.outdir, exist_ok=True)
    json.dump(log, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"status": log["status"], "engine": log["engine"], "png": log["png"],
                      "png_bytes": log["png_bytes"], "size": [log["width"], log["height"]],
                      "nonwhite_ratio": log["nonwhite_ratio"], "log": rp}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
