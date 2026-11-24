#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_export.py — SVG → PNG/PDF 发表级导出 + 像素校验（零第三方依赖，多渲染器回退链）。

用法:
  python3 render_export.py figure.svg --outdir out --png --pdf --dpi 300
  python3 render_export.py figure.png --check --min-width 800

回退链: cairosvg(Python库) → rsvg-convert → inkscape → chromium/chrome headless。
已知风险：cairosvg 已装但缺原生 libcairo 时 import 抛 OSError 而非 ImportError，
故 except 必须用 Exception（实测教训，见 SKILL.md 异常表）。
像素检查用纯标准库 PNG 解码（zlib+IDAT 抽样），输出非背景像素占比等 render_evidence。
所有失败路径退出码恒 0：降级结论打印 "RENDER DEGRADED"，如实登记，SVG 源文件照常交付。
"""
import argparse, os, shutil, struct, subprocess, sys, zlib

# CHARTVIZ-MARKER: render_export


def probe(cmd):
    return shutil.which(cmd) is not None


def render_with_cairosvg(svg, out, dpi):
    try:
        import cairosvg  # noqa
    except Exception:  # 必须捕获 Exception：缺原生库时是 OSError 不是 ImportError
        return False
    try:
        if out.endswith(".png"):
            cairosvg.svg2png(url=svg, write_to=out, dpi=dpi)
        else:
            cairosvg.svg2pdf(url=svg, write_to=out)
        return True
    except Exception as e:
        print("cairosvg failed:", e, file=sys.stderr)
        return False


def render_with_cmd(svg, out, dpi, tool):
    try:
        if tool == "rsvg-convert":
            subprocess.run(["rsvg-convert", "--dpi-x", str(dpi), "--dpi-y", str(dpi),
                            "-o", out, svg], check=True, timeout=120)
        elif tool == "inkscape":
            subprocess.run(["inkscape", svg, "--export-type=" + ("png" if out.endswith(".png") else "pdf"),
                            "--export-filename=" + out, "--export-dpi=" + str(dpi)],
                           check=True, timeout=180)
        else:
            return False
        return True
    except Exception as e:
        print(tool, "failed:", e, file=sys.stderr)
        return False


def render_with_browser(svg, out, dpi):
    for b in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        if probe(b):
            try:
                scale = max(1, int(dpi / 96))
                svg_abs = os.path.abspath(svg).replace("\\", "/")
                if not svg_abs.startswith("/"):
                    svg_abs = "/" + svg_abs
                subprocess.run([b, "--headless", "--disable-gpu", "--no-sandbox",
                                "--screenshot=" + os.path.abspath(out),
                                "--window-size=1600,1200",
                                "--force-device-scale-factor=" + str(scale),
                                "file://" + svg_abs], check=True, timeout=120,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                print(b, "failed:", e, file=sys.stderr)
    return False


def png_stats(path):
    """抽样统计非背景像素比例（纯标准库：解 IDAT + zlib）。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, w, h, depth, ctype = 8, b"", 0, 0, 0, 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", chunk[:10])
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    try:
        raw = zlib.decompress(idat)
    except Exception:
        return None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype, 3)
    if depth != 8:
        return None
    stride = w * ch + 1
    nonbg = sampled = 0
    for y in range(0, h, max(1, h // 100)):
        row = raw[y * stride + 1:y * stride + 1 + w * ch]
        for x in range(0, w, max(1, w // 100)):
            px = row[x * ch:(x + 1) * ch]
            if len(px) < ch:
                continue
            sampled += 1
            if ctype == 6 and px[3] == 0:
                continue
            if all(v >= 250 for v in px[:3]) or (ctype == 0 and px[0] >= 250):
                continue
            nonbg += 1
    return {"width": w, "height": h, "sampled": sampled,
            "nonbg_ratio": round(nonbg / max(1, sampled), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--check", action="store_true", help="检查 PNG 像素而非渲染")
    ap.add_argument("--min-width", type=int, default=800)
    args = ap.parse_args()

    if args.check:
        if not os.path.exists(args.input):
            print("CHECK FAIL: file not found:", args.input)
            return 0
        st = png_stats(args.input)
        if st is None:
            print("CHECK FAIL: cannot parse PNG:", args.input)
            return 0
        ok = st["width"] >= args.min_width and st["nonbg_ratio"] > 0.01
        print(("CHECK OK " if ok else "CHECK SUSPECT ") + repr(st))
        return 0

    os.makedirs(args.outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.input))[0]
    results = {}
    if args.png:
        out = os.path.join(args.outdir, base + ".png")
        done = (render_with_cairosvg(args.input, out, args.dpi)
                or (probe("rsvg-convert") and render_with_cmd(args.input, out, args.dpi, "rsvg-convert"))
                or (probe("inkscape") and render_with_cmd(args.input, out, args.dpi, "inkscape"))
                or render_with_browser(args.input, out, args.dpi))
        ok = done and os.path.exists(out) and os.path.getsize(out) > 1024
        results["png"] = out if ok else None
        if ok:
            st = png_stats(out)
            print("PNG OK:", out, st)
        else:
            print("PNG FAIL: no renderer produced a valid file")
    if args.pdf:
        out = os.path.join(args.outdir, base + ".pdf")
        done = (render_with_cairosvg(args.input, out, args.dpi)
                or (probe("rsvg-convert") and render_with_cmd(args.input, out, args.dpi, "rsvg-convert"))
                or (probe("inkscape") and render_with_cmd(args.input, out, args.dpi, "inkscape")))
        ok = done and os.path.exists(out) and os.path.getsize(out) > 1024
        results["pdf"] = out if ok else None
        print(("PDF OK: " + out) if ok else "PDF FAIL")
    if not results or any(v is None for v in results.values()):
        print('RENDER DEGRADED: 无可用渲染器（如实登记 renderer_unavailable，'
              '退出码 0，SVG 源文件照常交付；render_evidence 填 unknown）')
        return 0
    print("RENDER EVIDENCE:", results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
