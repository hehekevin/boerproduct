#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — SVG 思维导图 → PNG 真实渲染 + 像素级校验证据

渲染引擎按序尝试（全部失败也不中断交付）：
  1) cairosvg            2) svglib+reportlab     3) rsvg-convert     4) inkscape
  5) playwright/chromium 6) 平台 CLI（pdf-render-tool / chromium / google-chrome …）
  7) 内置纯标准库光栅器（无任何第三方依赖，始终可用；仅支持本包生成的 SVG 子集：
     rect / line / path(三次贝塞尔) / text，文本用内置 5x7 ASCII 点阵，非 ASCII 字符
     画为实心方块并在 render_log 标注 glyph_mode）
每条路径都对 PNG 做三重校验：字节数 >500、尺寸非零、非空白像素占比 ≥0.01。
无渲染器时如实记 status=no_renderer / glyph_fallback，绝不伪造渲染证据；SVG 本身照常交付。

用法:
  python3 render_preview.py --svg /app/output/mindmap.svg --outdir /app/output/previews
退出码恒 0。
"""
import argparse, json, os, shutil, subprocess, sys, zlib


class _SafeParser(argparse.ArgumentParser):
    """参数错误时退出码恒 0——只提示用法，不以非零码中断交付流程。"""

    def error(self, message):
        try:
            sys.stderr.write("[arg-error] " + str(message) + "\n")
            sys.stderr.write("[arg-error] 用法见 --help；本脚本失败路径退出码恒 0。\n")
        except Exception:
            pass
        sys.exit(0)

import xml.etree.ElementTree as ET

SVG_NS = "{http://www.w3.org/2000/svg}"

# 5x7 ASCII 点阵字体（每字 5 列 × 7 行，'1' 表示亮点）。仅用于无依赖兜底光栅。
_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000",) * 7,
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ";": ("00000", "01100", "01100", "00000", "01100", "00100", "01000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "\\": ("10000", "01000", "01000", "00100", "00010", "00010", "00001"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "#": ("01010", "01010", "11111", "01010", "11111", "01010", "01010"),
    "*": ("00000", "10101", "01110", "11111", "01110", "10101", "00000"),
    "'": ("00100", "00100", "00000", "00000", "00000", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "<": ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    ">": ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "^": ("00100", "01010", "10001", "00000", "00000", "00000", "00000"),
    "@": ("01110", "10001", "10111", "10101", "10111", "10000", "01110"),
    "&": ("01100", "10010", "10100", "01000", "10101", "10010", "01101"),
}


def _hex2rgb(c):
    c = (c or "#000000").strip()
    if c.startswith("rgb"):
        try:
            p = c[c.find("(") + 1:c.find(")")].split(",")
            return (int(p[0]), int(p[1]), int(p[2]))
        except Exception:
            return (0, 0, 0)
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    if len(c) != 7:
        return (0, 0, 0)
    try:
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
    except Exception:
        return (0, 0, 0)


class Canvas:
    """最小 RGB 画布：填充矩形 / 画线 / 位图字。"""

    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w, self.h = w, h
        self.buf = bytearray(bytes(bg) * (w * h))

    def px(self, x, y, rgb, alpha=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if alpha >= 1.0:
                self.buf[i] = rgb[0]; self.buf[i + 1] = rgb[1]; self.buf[i + 2] = rgb[2]
            else:
                for k in range(3):
                    self.buf[i + k] = int(self.buf[i + k] * (1 - alpha) + rgb[k] * alpha)

    def rect(self, x, y, w, h, rgb, fill=True, stroke=None, sw=1.0):
        x0, y0 = int(round(x)), int(round(y))
        x1, y1 = int(round(x + w)), int(round(y + h))
        if fill:
            row = bytes(rgb) * max(0, x1 - x0)
            for yy in range(max(0, y0), min(self.h, y1)):
                i = (yy * self.w + max(0, x0)) * 3
                self.buf[i:i + len(row)] = row
        if stroke:
            t = max(1, int(round(sw)))
            for k in range(t):
                for xx in range(x0, x1):
                    self.px(xx, y0 + k, stroke); self.px(xx, y1 - 1 - k, stroke)
                for yy in range(y0, y1):
                    self.px(x0 + k, yy, stroke); self.px(x1 - 1 - k, yy, stroke)

    def line(self, x1, y1, x2, y2, rgb, width=1.0):
        x1, y1, x2, y2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        t = max(1, int(round(width)))
        guard = 0
        while True:
            for oy in range(-(t // 2), t - t // 2):
                for ox in range(-(t // 2), t - t // 2):
                    self.px(x1 + ox, y1 + oy, rgb)
            if (x1 == x2 and y1 == y2) or guard > 20000:
                break
            guard += 1
            e2 = 2 * err
            if e2 > -dy:
                err -= dy; x1 += sx
            if e2 < dx:
                err += dx; y1 += sy

    def bezier(self, p0, p1, p2, p3, rgb, width=1.0, steps=48):
        for i in range(steps + 1):
            t = i / steps
            mt = 1 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
            self.px(int(round(x)), int(round(y)), rgb)
            self.px(int(round(x)) + 1, int(round(y)), rgb)

    def text(self, x, y, s, rgb, size=13, anchor="middle"):
        if not s:
            return
        s = str(s)
        scale = max(1, int(round(size / 7.0)))
        cw, chh = 6 * scale, 8 * scale
        total = len(s) * cw
        if anchor == "middle":
            x = x - total / 2.0
        elif anchor == "end":
            x = x - total
        for idx, ch in enumerate(s):
            up = ch.upper()
            if up in _FONT:
                g = _FONT[up]
                for ry, rowbits in enumerate(g):
                    for rx, bit in enumerate(rowbits):
                        if bit == "1":
                            for dy in range(scale):
                                for dx in range(scale):
                                    self.px(int(x + idx * cw + rx * scale + dx),
                                            int(y + ry * scale + dy), rgb)
            else:
                # 非 ASCII：画空心方框占位（render_log 标注 glyph_mode=ascii+hollow_blocks）
                bx, by, bs = int(x + idx * cw), int(y), max(3, chh - 3)
                for dy in range(bs):
                    for dx in range(bs):
                        if dx == 0 or dy == 0 or dx == bs - 1 or dy == bs - 1:
                            self.px(bx + dx, by + dy, rgb)

    def save_png(self, path):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.buf[y * stride:(y + 1) * stride]

        def chunk(tag, data):
            return (len(data).to_bytes(4, "big") + tag + data +
                    zlib.crc32(tag + data).to_bytes(4, "big"))

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", self.w.to_bytes(4, "big") + self.h.to_bytes(4, "big") +
                     bytes([8, 2, 0, 0, 0]))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        png += chunk(b"IEND", b"")
        with open(path, "wb") as f:
            f.write(png)
        return len(png)


def _parse_path(d):
    """仅解析 'M x y C x1 y1 x2 y2 x y' 结构（本包 map_build 生成的形式）。"""
    try:
        toks = d.replace(",", " ").split()
        pts, i = [], 0
        cur = None
        while i < len(toks):
            t = toks[i]
            if t == "M":
                cur = (float(toks[i + 1]), float(toks[i + 2])); pts.append(("M", cur)); i += 3
            elif t == "C":
                c1 = (float(toks[i + 1]), float(toks[i + 2]))
                c2 = (float(toks[i + 3]), float(toks[i + 4]))
                p = (float(toks[i + 5]), float(toks[i + 6]))
                pts.append(("C", c1, c2, p)); i += 7
            else:
                i += 1
        return pts
    except Exception:
        return []


def rasterize_svg(svg_path, png_path, width=1500):
    """内置纯标准库光栅器：只支持本包生成的 SVG 子集。返回 (engine, glyph_mode)。"""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vb = (root.get("viewBox") or "0 0 1500 1000").split()
    vw = float(vb[2]) if len(vb) > 2 else 1500.0
    vh = float(vb[3]) if len(vb) > 3 else 1000.0
    W = int(width)
    H = max(1, int(round(W * vh / vw)))
    cv = Canvas(W, H)
    scale = W / vw
    glyph_mode = "ascii+hollow_blocks"

    for el in root.iter():
        tag = el.tag.replace(SVG_NS, "")
        try:
            if tag == "rect":
                x = float(el.get("x", 0)) * scale
                y = float(el.get("y", 0)) * scale
                w = float(el.get("width", 0)) * scale
                h = float(el.get("height", 0)) * scale
                fill = el.get("fill", "#fff")
                op = float(el.get("fill-opacity", 1) or 1)
                stroke = el.get("stroke")
                rgb = _hex2rgb(fill)
                if rgb == (255, 255, 255) and not stroke:
                    continue
                cv.rect(x, y, w, h, rgb, fill=fill != "none", stroke=_hex2rgb(stroke) if stroke else None,
                        sw=max(1, int(round(float(el.get("stroke-width", 1) or 1) * scale))))
                if op < 1.0:
                    pass
            elif tag == "line":
                x1 = float(el.get("x1", 0)) * scale; y1 = float(el.get("y1", 0)) * scale
                x2 = float(el.get("x2", 0)) * scale; y2 = float(el.get("y2", 0)) * scale
                cv.line(x1, y1, x2, y2, _hex2rgb(el.get("stroke", "#000")),
                        max(1, float(el.get("stroke-width", 1) or 1) * scale))
            elif tag == "path":
                segs = _parse_path(el.get("d", ""))
                cur = None
                for seg in segs:
                    if seg[0] == "M":
                        cur = seg[1]
                    elif seg[0] == "C" and cur:
                        p0 = (cur[0] * scale, cur[1] * scale)
                        p1 = (seg[1][0] * scale, seg[1][1] * scale)
                        p2 = (seg[2][0] * scale, seg[2][1] * scale)
                        p3 = (seg[3][0] * scale, seg[3][1] * scale)
                        cv.bezier(p0, p1, p2, p3, _hex2rgb(el.get("stroke", "#000")),
                                  max(1, float(el.get("stroke-width", 1) or 1) * scale))
                        cur = seg[3]
            elif tag == "text":
                x = float(el.get("x", 0)) * scale
                y = float(el.get("y", 0)) * scale
                size = float(el.get("font-size", 12) or 12) * scale
                txt = "".join(el.itertext())
                cv.text(x, y - size, txt, _hex2rgb(el.get("fill", "#000")),
                        size=size, anchor=el.get("text-anchor", "start"))
        except Exception:
            continue
    cv.save_png(png_path)
    return "builtin-rasterizer", glyph_mode


def _png_nonwhite_ratio(path):
    """纯标准库 PNG 解码 → 非空白像素占比（真实像素校验，零依赖）。

    支持本渲染器自己产出的 RGB/RGBA/灰度、8bit、非隔行 PNG。
    返回 (width, height, ratio) 或 None（解析不了时返回 None，调用方降级为字节校验）。
    """
    try:
        data = open(path, "rb").read()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        pos, idat, w, h, depth, ctype, interlace = 8, bytearray(), 0, 0, 8, 2, 0
        while pos + 8 <= len(data):
            ln = int.from_bytes(data[pos:pos + 4], "big")
            tag = data[pos + 4:pos + 8]
            body = data[pos + 8:pos + 8 + ln]
            if tag == b"IHDR":
                w = int.from_bytes(body[0:4], "big")
                h = int.from_bytes(body[4:8], "big")
                depth = body[8]
                ctype = body[9]
                interlace = body[12]
            elif tag == b"IDAT":
                idat += body
            elif tag == b"IEND":
                break
            pos += 12 + ln
        if not w or not h or depth != 8 or interlace != 0 or ctype not in (0, 2, 4, 6):
            return None
        ch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
        raw = zlib.decompress(bytes(idat))
        stride = w * ch
        out = bytearray(stride * h)
        prev = bytearray(stride)
        p = 0
        for y in range(h):
            ft = raw[p]; p += 1
            line = bytearray(raw[p:p + stride]); p += stride
            if ft == 1:
                for i in range(ch, stride):
                    line[i] = (line[i] + line[i - ch]) & 0xFF
            elif ft == 2:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 0xFF
            elif ft == 3:
                for i in range(stride):
                    a = line[i - ch] if i >= ch else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
            elif ft == 4:
                for i in range(stride):
                    a = line[i - ch] if i >= ch else 0
                    b = prev[i]
                    c = prev[i - ch] if i >= ch else 0
                    pp = a + b - c
                    pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                    pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                    line[i] = (line[i] + pr) & 0xFF
            out[y * stride:(y + 1) * stride] = line
            prev = line
        nonwhite = 0
        total = 0
        for y in range(h):
            base = y * stride
            for x in range(w):
                i = base + x * ch
                total += 1
                if ch >= 3:
                    px = (out[i], out[i + 1], out[i + 2])
                else:
                    px = (out[i], out[i], out[i])
                if px != (255, 255, 255):
                    nonwhite += 1
        return w, h, round(nonwhite / max(total, 1), 4)
    except Exception:
        return None


def _try_cli_engine(png_path, svg_path):
    """平台预装渲染 CLI（pdf-render-tool / chromium 等）按序尝试。"""
    candidates = [
        (["chromium", "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
          "--screenshot=" + png_path, "--window-size=1560,1100",
          "file://" + os.path.abspath(svg_path).replace("\\", "/")], "chromium-cli"),
        (["google-chrome", "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
          "--screenshot=" + png_path, "--window-size=1560,1100",
          "file://" + os.path.abspath(svg_path).replace("\\", "/")], "chrome-cli"),
        (["wkhtmltoimage", "--width", "1500", png_path, svg_path], "wkhtmltoimage"),
    ]
    for cmd, name in candidates:
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            subprocess.run([exe] + cmd[1:], capture_output=True, timeout=120)
            if os.path.exists(png_path) and os.path.getsize(png_path) > 500:
                return name
        except Exception:
            pass
    return None


def render_png(svg_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    png_path = os.path.join(outdir, "mindmap.png")
    log = {"src": os.path.abspath(svg_path), "png": None, "engine": None, "status": "no_renderer",
           "png_bytes": 0, "width": 0, "height": 0, "nonwhite_ratio": None,
           "glyph_mode": None, "engines_tried": [], "note": ""}
    for p in (png_path,):
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    # 1) cairosvg
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=1500, background_color="#ffffff")
        log["engine"] = "cairosvg"
        log["engines_tried"].append("cairosvg")
    except Exception:
        log["engines_tried"].append("cairosvg:missing")
        # 2) svglib + reportlab
        try:
            from svglib.svglib import svg2rlg  # type: ignore
            from reportlab.graphics import renderPM  # type: ignore
            drawing = svg2rlg(svg_path)
            renderPM.drawToFile(drawing, png_path, fmt="PNG")
            log["engine"] = "svglib"
            log["engines_tried"].append("svglib")
        except Exception:
            log["engines_tried"].append("svglib:missing")
            # 3) rsvg-convert / inkscape
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
                log["engines_tried"].append("rsvg/inkscape:missing")
                # 4) playwright + chromium
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
                    log["engines_tried"].append("playwright")
                except Exception:
                    log["engines_tried"].append("playwright:missing")
                    # 5) 平台 CLI
                    got = _try_cli_engine(png_path, svg_path)
                    if got:
                        log["engine"] = got
                        log["engines_tried"].append(got)
                    else:
                        log["engines_tried"].append("cli:missing")
                        # 6) 内置纯标准库光栅器（始终可用）
                        try:
                            eng, gm = rasterize_svg(svg_path, png_path)
                            log["engine"] = eng
                            log["glyph_mode"] = gm
                            log["engines_tried"].append("builtin-rasterizer")
                            log["note"] = ("无第三方渲染器；使用内置纯标准库光栅器，"
                                           "文本用 5x7 ASCII 点阵，非 ASCII 字符以方块占位。")
                        except Exception as e:
                            log["note"] = f"内置光栅器失败: {str(e)[:150]}；SVG 已交付。"

    if not os.path.exists(png_path):
        log["status"] = "no_renderer"
        log["note"] = (log["note"] or "") + " 未产出 PNG；SVG 本身是交付物。"
        return log
    size = os.path.getsize(png_path)
    if size < 500:
        log["status"] = "render_failed"
        log["note"] = f"PNG 过小({size}B) 判为无效"
        try:
            os.remove(png_path)
        except Exception:
            pass
        return log
    log["png"] = os.path.abspath(png_path)
    log["png_bytes"] = size
    try:
        from PIL import Image  # type: ignore
        img = Image.open(png_path).convert("L")
        log["width"], log["height"] = img.size
        hist = img.histogram()
        total = sum(hist)
        nonwhite = total - hist[255]
        log["nonwhite_ratio"] = round(nonwhite / max(total, 1), 4)
        if log["nonwhite_ratio"] < 0.01:
            log["status"] = "render_failed"
            log["note"] = "PNG 几乎全白（nonwhite_ratio<0.01），判为无效渲染"
            os.remove(png_path)
            log["png"] = None
        else:
            log["status"] = "ok"
    except Exception:
        # 无 PIL 时用纯标准库 PNG 解码做真实像素校验（零依赖）
        got = _png_nonwhite_ratio(png_path)
        if got:
            log["width"], log["height"], log["nonwhite_ratio"] = got
            if log["nonwhite_ratio"] < 0.01:
                log["status"] = "render_failed"
                log["note"] = "PNG 几乎全白（nonwhite_ratio<0.01），判为无效渲染"
                try:
                    os.remove(png_path)
                except Exception:
                    pass
                log["png"] = None
            else:
                log["status"] = "ok"
                log["pixel_check"] = "builtin-png-decoder"
        else:
            try:
                with open(png_path, "rb") as f:
                    head = f.read(26)
                log["width"] = int.from_bytes(head[16:20], "big")
                log["height"] = int.from_bytes(head[20:24], "big")
                log["nonwhite_ratio"] = None
                log["status"] = "ok_bytes_only"
                log["note"] = (log["note"] or "") + " PNG 像素无法解码，仅字节与尺寸校验。"
            except Exception as e:
                log["status"] = "ok_bytes_only"
                log["note"] = f"PNG 头解析失败: {str(e)[:100]}"
    return log


def main():
    ap = _SafeParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    if not os.path.exists(args.svg):
        print(json.dumps({"status": "error", "note": f"SVG 不存在: {args.svg}（退出码恒 0）"},
                         ensure_ascii=False))
        return 0
    try:
        log = render_png(args.svg, args.outdir)
    except Exception as e:
        log = {"src": args.svg, "png": None, "engine": None, "status": "render_failed",
               "png_bytes": 0, "width": 0, "height": 0, "nonwhite_ratio": None,
               "note": f"渲染异常: {str(e)[:200]}；SVG 已交付。"}
    rp = os.path.join(args.outdir, "render_log.json")
    try:
        os.makedirs(args.outdir, exist_ok=True)
        json.dump(log, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"写 render_log 失败: {e}（退出码恒 0）"},
                         ensure_ascii=False))
        return 0
    print(json.dumps({"status": log["status"], "engine": log["engine"], "png": log["png"],
                      "png_bytes": log["png_bytes"], "size": [log["width"], log["height"]],
                      "nonwhite_ratio": log["nonwhite_ratio"], "glyph_mode": log.get("glyph_mode"),
                      "log": rp}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200], "note": "退出码恒 0"},
                         ensure_ascii=False))
        sys.exit(0)
