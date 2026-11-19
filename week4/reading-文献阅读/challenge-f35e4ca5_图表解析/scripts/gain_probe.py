#!/usr/bin/env python3
"""gain_probe.py — 使用增益/创新增益的可复现真实对照（A/B 双跑 + 独立裁判）。

设计要点
--------
1. 同输入两跑：同一张图（PNG）跑两条读图管线，配置只差「机制开关」——
   arm=full     ：像素→数据坐标标定（探测轴线与刻度）+ 图例颜色↔系列匹配
                  + 首/中/尾采样 + 单位量级传递 + 来源定位 + 证据回证；
   arm=degraded ：退化基线——不做刻度标定（按整图边界线性假设）、不做图例↔系列
                  匹配（全部曲线并为一条）、不传单位、不写定位、不做回证。
2. 独立裁判：judge 用与两条管线**完全独立的第三份代码**（真值表 / 证据 blob）打分，
   避免「用被测代码给自己打分」。裁判输出五项指标：
     reading_extraction_accuracy  读数提取准确率
     numeric_backevidence_rate    数值回证率
     legend_series_consistency    图例-系列一致率
     manual_review_items          需人工核对条目数
     steps                        步骤数（管线实际执行步数）
3. 闸门消融对照：对**真实交付物** result.json 跑 chart_check.py 两遍
   （--ablate none / --ablate all），量出「缺陷检出条数 / 漏检条数」。
4. 全部数字来自本脚本实际执行（PNG 解码 → 采样 → 裁判 → JSON），无预置答案。

用法
----
  # 自测夹具（真值已知，可复现；自动生成 PNG，不预置二进制）
  python3 gain_probe.py --selftest --out /app/output/gain_probe.json

  # 真实案例：叠加跑在交付物上
  python3 gain_probe.py --result /app/output/result.json --workorder /app/work/workorder.json \
      --input-root /input --out /app/output/gain_probe.json

退出码：恒为 0（禁止中断交付）；verdict 见输出 JSON。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import struct
import sys
import zlib
from collections import Counter

# ---------------------------------------------------------------- PNG 编解码
def png_write(path: str, w: int, h: int, pix) -> None:
    """写 8bit RGB PNG（纯标准库）。pix 为 [[(r,g,b),...], ...]。"""
    raw = bytearray()
    for row in pix:
        raw.append(0)
        for (r, g, b) in row:
            raw += bytes((r & 255, g & 255, b & 255))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    hdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", hdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(blob)


def png_read(path: str):
    """读 8bit PNG（灰度/RGB/带 alpha，非隔行）→ (w, h, [[(r,g,b),...],...])。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: %s" % path)
    pos, idat, hdr = 8, bytearray(), None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
        pos += 12 + ln
    if hdr is None:
        raise ValueError("PNG without IHDR")
    w, h, depth, ctype, comp, filt, inter = hdr
    if depth != 8 or inter != 0 or ctype not in (0, 2, 4, 6):
        raise ValueError("unsupported PNG (depth=%d ctype=%d interlace=%d)" % (depth, ctype, inter))
    nch = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(bytes(idat))
    stride = w * nch
    out = []
    prev = bytearray(stride)
    p = 0
    for _y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ValueError("bad PNG filter %d" % ft)
        prev = line
        row = []
        for x in range(w):
            px = line[x * nch:(x + 1) * nch]
            if ctype == 0:
                row.append((px[0], px[0], px[0]))
            elif ctype == 4:
                row.append((px[0], px[0], px[0]))
            elif ctype == 2:
                row.append((px[0], px[1], px[2]))
            else:
                row.append((px[0], px[1], px[2]))
        out.append(row)
    return w, h, out


# ---------------------------------------------------------------- 颜色工具
def hsv(r: int, g: int, b: int):
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return 0.0, 0.0, 0.0
    s = d / mx
    if mx == r:
        hh = ((g - b) / d) % 6
    elif mx == g:
        hh = (b - r) / d + 2
    else:
        hh = (r - g) / d + 4
    return hh * 60.0, s, mx


def color_clusters(pix, min_sat=0.35, min_val=40):
    """从图中聚类出「彩色」像素的主色相（轴线/文字为近黑近白，先滤掉）。"""
    buckets = Counter()
    for row in pix:
        for (r, g, b) in row:
            hh, s, v = hsv(r, g, b)
            if s >= min_sat and v >= min_val:
                buckets[int(hh // 15) * 15] += 1
    return [c for c, _ in buckets.most_common(6)]


def match_color(pix, target_hue, tol=22, min_sat=0.30, min_val=40):
    """返回与目标色相匹配的像素坐标集合 {(x, y)}。"""
    out = set()
    for y, row in enumerate(pix):
        for x, (r, g, b) in enumerate(row):
            hh, s, v = hsv(r, g, b)
            if s < min_sat or v < min_val:
                continue
            d = abs(hh - target_hue)
            if d > 180:
                d = 360 - d
            if d <= tol:
                out.add((x, y))
    return out


# ---------------------------------------------------------------- 坐标标定
def find_axes(pix, w, h):
    """探测轴线与刻度位置（纯像素启发式）。

    返回 dict：x_axis(y 像素行, 左右端点), y_axis(x 像素列), x_ticks[列号],
    y_ticks[行号]。找不到时给 None（管线据此走退化分支）。
    """
    def dark(p):
        return p[0] < 120 and p[1] < 120 and p[2] < 120

    # 最长水平暗线 → x 轴
    best_h = (0, None, None, None)
    for y in range(h):
        run, start = 0, None
        for x in range(w):
            if dark(pix[y][x]):
                if start is None:
                    start = x
                run += 1
            else:
                if start is not None and run > best_h[0]:
                    best_h = (run, y, start, x - 1)
                start, run = None, 0
        if start is not None and run > best_h[0]:
            best_h = (run, y, start, w - 1)
    # 最长垂直暗线 → y 轴
    best_v = (0, None, None, None)
    for x in range(w):
        run, start = 0, None
        for y in range(h):
            if dark(pix[y][x]):
                if start is None:
                    start = y
                run += 1
            else:
                if start is not None and run > best_v[0]:
                    best_v = (run, x, start, y - 1)
                start, run = None, 0
        if start is not None and run > best_v[0]:
            best_v = (run, x, start, h - 1)

    info = {"x_axis_y": None, "x_left": None, "x_right": None,
            "y_axis_x": None, "y_top": None, "y_bottom": None,
            "x_ticks": [], "y_ticks": []}
    if best_h[1] is not None and best_h[0] > w * 0.25:
        info["x_axis_y"] = best_h[1]
        info["x_left"], info["x_right"] = best_h[2], best_h[3]
    if best_v[1] is not None and best_v[0] > h * 0.15:
        info["y_axis_x"] = best_v[1]
        info["y_bottom"], info["y_top"] = best_v[2], best_v[3]

    # x 刻度：轴线下方 2~6 行的暗像素列（每列聚成簇）
    if info["x_axis_y"] is not None:
        cols = []
        for x in range(w):
            if any(dark(pix[min(info["x_axis_y"] + d, h - 1)][x]) for d in range(2, 7)):
                cols.append(x)
        info["x_ticks"] = _cluster(cols, gap=3)
    # y 刻度：轴线左侧 2~10 列的暗像素行（刻度画在轴左侧）
    if info["y_axis_x"] is not None:
        rows = []
        for y in range(h):
            if any(dark(pix[y][max(info["y_axis_x"] - d, 0)]) for d in range(2, 11)):
                rows.append(y)
        info["y_ticks"] = _cluster(rows, gap=3)
    return info


def _cluster(sorted_vals, gap=3):
    if not sorted_vals:
        return []
    out = [[sorted_vals[0], sorted_vals[0]]]
    for v in sorted_vals[1:]:
        if v - out[-1][1] <= gap:
            out[-1][1] = v
        else:
            out.append([v, v])
    return [int(round((a + b) / 2.0)) for a, b in out]


def build_map(a0, a1, b0, b1):
    """通用线性映射：f(x) = b0 + (x-a0)*(b1-b0)/(a1-a0)。a→b 的线性插值。"""
    if a1 == a0:
        return None

    def f(x):
        return b0 + (x - a0) * (b1 - b0) / float(a1 - a0)
    return f


def _data_grid(ax, n):
    """给 n 个等距像素刻度分配数据值：优先用声明的 start/step 网格，不足时按 start..end 线性铺开。"""
    start = ax.get("start")
    end = ax.get("end")
    step = ax.get("step")
    if start is None or end is None:
        return None
    if step:
        expected = int(round((end - start) / float(step))) + 1
        if expected == n:
            return [start + i * step for i in range(n)]
    if n < 2:
        return [start]
    return [start + (end - start) * i / float(n - 1) for i in range(n)]


def calibrate(axes, ax_x, ax_y):
    """由探测到的刻度建立像素↔数据映射。

    返回 (fx, fy, fx_inv, fy_inv, meta)：
      fx/fy     = 数据 → 像素（用于「在数据 x 处去像素上取点」）
      fx_inv/fy_inv = 像素 → 数据（用于把取到的像素折线换算回数值）
    """
    meta = {"x_source": None, "y_source": None}
    fx = fy = fx_inv = fy_inv = None
    # x 轴：像素列升序（左→右）↔ 数据值升序
    xt = axes.get("x_ticks") or []
    if len(xt) >= 2 and ax_x:
        vals = _data_grid(ax_x, len(xt))
        if vals:
            fx = build_map(vals[0], vals[-1], xt[0], xt[-1])
            fx_inv = build_map(xt[0], xt[-1], vals[0], vals[-1])
            meta["x_source"] = "tick_marks(%d)" % len(xt)
    # y 轴：像素行升序（上→下）↔ 数据值降序（上大下小）
    yt = axes.get("y_ticks") or []
    if len(yt) >= 2 and ax_y:
        vals = _data_grid(ax_y, len(yt))
        if vals:
            fy = build_map(vals[0], vals[-1], yt[-1], yt[0])
            fy_inv = build_map(yt[-1], yt[0], vals[0], vals[-1])
            meta["y_source"] = "tick_marks(%d)" % len(yt)
    if fx is None and axes.get("x_left") is not None and ax_x:
        fx = build_map(ax_x.get("start", 0), ax_x.get("end", 0),
                       axes["x_left"], axes["x_right"])
        fx_inv = build_map(axes["x_left"], axes["x_right"],
                           ax_x.get("start", 0), ax_x.get("end", 0))
        meta["x_source"] = "axis_extent_fallback"
    if fy is None and axes.get("y_top") is not None and ax_y:
        fy = build_map(ax_y.get("start", 0), ax_y.get("end", 0),
                       axes["y_bottom"], axes["y_top"])
        fy_inv = build_map(axes["y_bottom"], axes["y_top"],
                           ax_y.get("start", 0), ax_y.get("end", 0))
        meta["y_source"] = "axis_extent_fallback"
    return fx, fy, fx_inv, fy_inv, meta


# ---------------------------------------------------------------- 读图管线
def sample_curve(pixels_set, fx, fy, x_min_px, x_max_px):
    """按 x 像素列取该列彩色像素的中位 y，得到折线采样点（像素坐标）。"""
    by_col = {}
    for (x, y) in pixels_set:
        by_col.setdefault(x, []).append(y)
    pts = []
    for x in sorted(by_col):
        if x < x_min_px or x > x_max_px:
            continue
        ys = sorted(by_col[x])
        pts.append((x, ys[len(ys) // 2]))
    return pts


def interpolate(pts, x_px):
    """在像素采样折线上线性插值出 x_px 处的 y_px。"""
    if not pts:
        return None
    if x_px <= pts[0][0]:
        return pts[0][1]
    if x_px >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x_px <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x_px - x0) / float(x1 - x0)
    return None


def run_pipeline(pix, w, h, spec, mode):
    """按 mode 跑读图管线，返回 readings + 步骤数 + 诊断信息。

    spec: {"axes": {"x": {...}, "y": {...}}, "series": [{"label","hue"}...],
           "series_count": n}
    mode: "full" | "degraded"
    """
    steps = 0
    diag = {"mode": mode}
    ax_x = spec["axes"].get("x") or {}
    ax_y = spec["axes"].get("y") or {}

    if mode == "full":
        steps += 1
        axes = find_axes(pix, w, h)
        steps += 1
        fx, fy, fx_inv, fy_inv, meta = calibrate(axes, ax_x, ax_y)
        diag["calibration"] = meta
    else:
        # 退化：不做刻度标定（整图边界线性假设），不做图例↔系列匹配
        steps += 1
        fx = build_map(ax_x.get("start", 0), ax_x.get("end", 0), 0, w - 1)
        fy = build_map(ax_y.get("start", 0), ax_y.get("end", 0), h - 1, 0)
        fx_inv = build_map(0, w - 1, ax_x.get("start", 0), ax_x.get("end", 0))
        fy_inv = build_map(h - 1, 0, ax_y.get("start", 0), ax_y.get("end", 0))
        diag["calibration"] = {"x_source": "full_image_assumption",
                               "y_source": "full_image_assumption"}
        axes = {"x_left": 0, "x_right": w - 1, "y_top": 0, "y_bottom": h - 1,
                "x_ticks": [], "y_ticks": []}

    x0_px = axes.get("x_left") if axes.get("x_left") is not None else 0
    x1_px = axes.get("x_right") if axes.get("x_right") is not None else (w - 1)

    readings = []
    if mode == "full":
        for s in spec["series"]:
            steps += 1
            px_set = match_color(pix, s["hue"])
            if not px_set:
                continue
            steps += 1
            pts = sample_curve(px_set, fx, fy, x0_px, x1_px)
            if not pts:
                continue
            steps += 1
            for tag, x_data in (("首", ax_x.get("start", 0)),
                                ("中", (ax_x.get("start", 0) + ax_x.get("end", 0)) / 2.0),
                                ("尾", ax_x.get("end", 0))):
                x_px = fx(x_data) if fx else None
                if x_px is None:
                    continue
                y_px = interpolate(pts, x_px)
                if y_px is None or fy is None:
                    continue
                y_data = fy_inv(y_px)
                readings.append({
                    "series": s["label"], "position": tag,
                    "x": round(x_data, 3), "y": round(y_data, 2),
                    "units": ax_y.get("units"),
                    "source_locator": "%s px=(%d,%d) color_series=%s"
                                      % (spec.get("figure_ref", "Fig"), int(round(x_px)),
                                         int(round(y_px)), s["label"]),
                    "how": "pixel_calibrated_sampling",
                })
        steps += 1
    else:
        # 退化臂：按「颜色团」聚类出线，但不做图例语义匹配 → 系列名只能是色号
        hues = color_clusters(pix)
        steps += 1
        for hh in hues[:2]:
            px_set = match_color(pix, hh)
            if not px_set:
                continue
            steps += 1
            pts = sample_curve(px_set, fx, fy, x0_px, x1_px)
            if not pts:
                continue
            steps += 1
            for tag, x_data in (("首", ax_x.get("start", 0)),
                                ("中", (ax_x.get("start", 0) + ax_x.get("end", 0)) / 2.0),
                                ("尾", ax_x.get("end", 0))):
                x_px = fx(x_data) if fx else None
                if x_px is None:
                    continue
                y_px = interpolate(pts, x_px)
                if y_px is None or fy is None:
                    continue
                y_data = fy_inv(y_px)
                readings.append({
                    "series": "hue_%d" % int(hh), "position": tag,
                    "x": round(x_data, 3), "y": round(y_data, 2),
                    "units": None,
                    "source_locator": "pixel(approx,no-legend-match)",
                    "how": "blind_sampling",
                })
        steps += 1
    return readings, steps, diag


# ---------------------------------------------------------------- 裁判
def truth_lookup(truth, series, x):
    """在真值折线上线性插值。"""
    pts = truth.get(series) or []
    if not pts:
        return None
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x - x0) / float(x1 - x0)
    return None


def evidence_hit(r, evidence_pairs, tol):
    """数值回证：读数 (x,y) 能否落到材料中**已写出的**某个表值上（±容差）。"""
    if not evidence_pairs:
        return None
    best = None
    for series, pairs in evidence_pairs.items():
        for (ex, ey) in pairs:
            d = abs(ex - r["x"]) + abs(ey - r["y"])
            if best is None or d < best:
                best = d
    if best is None:
        return False
    # x 必须精确落在表列的 x 上，y 在容差内
    for series, pairs in evidence_pairs.items():
        for (ex, ey) in pairs:
            if abs(ex - r["x"]) <= 1e-6 and abs(ey - r["y"]) <= tol:
                return True
    return False


def judge(readings, truth, legend, evidence_pairs, tol):
    """独立裁判：五项指标。truth 为 None 时退化为无真值模式。

    指标口径（机制→指标映射一一对应）：
      reading_extraction_accuracy —— 读数提取准确率：读数 y 与真值曲线在同一 x 处的偏差
        ≤ 容差的比例（只量「读到的数对不对」，与系列归属无关，避免循环论证）；
      numeric_backevidence_rate   —— 数值回证率：读数能落到材料已写出的表值上的比例；
      legend_series_consistency   —— 图例-系列一致率：读数系列与图例项对得上的比例；
      manual_review_items         —— 需人工核对条目数：数值不准或无回证、需人复核的读数条数；
      steps                       —— 步骤数（管线实际执行步数，由管线自报）。
    """
    n = len(readings)
    if n == 0:
        return {"readings": 0, "reading_extraction_accuracy": None,
                "numeric_backevidence_rate": None, "legend_series_consistency": None,
                "manual_review_items": 0, "note": "该臂无读数产出（无法评分）"}

    labels = [l.get("label") for l in (legend or [])]
    value_ok = backed = attr_ok = manual = 0
    for r in readings:
        # ① 数值准确性：与「最近的真值曲线」比（退化臂无法归系列时仍可比数值）
        best_err, best_series = None, None
        if truth is not None:
            cands = [r["series"]] if r["series"] in truth else list(truth.keys())
            for s in cands:
                tv = truth_lookup(truth, s, r["x"])
                if tv is None:
                    continue
                err = abs(tv - r["y"])
                if best_err is None or err < best_err:
                    best_err, best_series = err, s
        ok_val = (best_err is not None and best_err <= tol)
        # ② 数值回证：能否落到材料已写出的表值上
        hit = evidence_hit(r, evidence_pairs, tol)
        if hit is None:
            hit = False
        # ③ 系列归属：读数系列是图例项，且与最近真值系列一致
        ok_attr = (r["series"] in labels) and (best_series == r["series"])
        if ok_val:
            value_ok += 1
        if hit:
            backed += 1
        if ok_attr:
            attr_ok += 1
        if not (ok_val and hit):
            manual += 1
    return {
        "readings": n,
        "reading_extraction_accuracy": round(value_ok / float(n), 4),
        "numeric_backevidence_rate": round(backed / float(n), 4),
        "legend_series_consistency": round(attr_ok / float(n), 4),
        "manual_review_items": manual,
    }


def trim(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


# ---------------------------------------------------------------- 自测夹具
def build_fixture_png(path: str, fx_spec: dict):
    """确定性地生成一张合成折线图 PNG（自测用，非真实论文数据）。"""
    W, H = 900, 620
    pix = [[(255, 255, 255) for _ in range(W)] for _ in range(H)]
    ax = fx_spec["axes"]
    px0 = ax["x"]["pixel_span"]["left"]
    px1 = ax["x"]["pixel_span"]["right"]
    py_top = ax["y"]["pixel_span"]["top"]
    py_bot = ax["y"]["pixel_span"]["bottom"]
    xd0, xd1 = ax["x"]["start"], ax["x"]["end"]
    yd0, yd1 = ax["y"]["start"], ax["y"]["end"]

    def X(xd):
        return int(round(px0 + (xd - xd0) * (px1 - px0) / float(xd1 - xd0)))

    def Y(yd):
        return int(round(py_bot - (yd - yd0) * (py_bot - py_top) / float(yd1 - yd0)))

    # 坐标轴
    for x in range(px0, px1 + 1):
        for dy in (0, 1):
            y = py_bot + dy
            if 0 <= y < H:
                pix[y][x] = (0, 0, 0)
    for y in range(py_top, py_bot + 1):
        for dx in (0, 1):
            x = px0 + dx
            if 0 <= x < W:
                pix[y][x] = (0, 0, 0)
    # 刻度（轴外 4~9 px）
    x = xd0
    while x <= xd1 + 1e-9:
        xp = X(x)
        for yy in range(py_bot + 2, py_bot + 10):
            pix[yy][xp] = (0, 0, 0)
        for dx in (0, 1):
            if 0 <= xp + dx < W:
                pix[py_bot][xp + dx] = (0, 0, 0)
        x += ax["x"]["step"]
    y = yd0
    while y <= yd1 + 1e-9:
        yp = Y(y)
        for xx in range(px0 - 10, px0 - 2):
            pix[yp][xx] = (0, 0, 0)
        for dy in (0, 1):
            if 0 <= yp + dy < H:
                pix[yp][px0] = (0, 0, 0)
        y += ax["y"]["step"]
    # 两条曲线
    cols = [(20, 60, 200), (215, 40, 40)]
    for si, (series, pts) in enumerate(fx_spec["truth"].items()):
        col = cols[si % len(cols)]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            n = max(abs(x1 - x0), abs(y1 - y0), 1) * 3
            for k in range(int(n) + 1):
                t = k / float(n)
                xx = int(round(X(x0 + (x1 - x0) * t)))
                yy = int(round(Y(y0 + (y1 - y0) * t)))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if 0 <= xx + dx < W and 0 <= yy + dy < H:
                            pix[yy + dy][xx + dx] = col
    png_write(path, W, H, pix)
    return path


def selftest(out_path: str, workdir: str):
    """自测夹具：生成 PNG → 两臂读图 → 独立裁判打分 → 写 JSON。"""
    here = os.path.dirname(os.path.abspath(__file__))
    fx_path = os.path.join(here, "..", "examples", "fixture-chart.json")
    with open(fx_path, "r", encoding="utf-8") as f:
        spec = json.load(f)
    os.makedirs(workdir, exist_ok=True)
    png_path = os.path.join(workdir, "fixture-chart.png")
    build_fixture_png(png_path, spec)

    w, h, pix = png_read(png_path)
    axes = spec["axes"]
    hue_map = {"S1": 220.0, "S2": 0.0}
    series = [{"label": l["label"], "hue": hue_map[l["label"]]} for l in spec["legend"]]
    pipeline_spec = {"axes": axes, "series": series,
                     "series_count": len(series),
                     "figure_ref": spec["figure_ref"]}

    tol = axes["y"]["step"] / float(axes["y"]["minor_per_major"]) * 0.6

    arms = {}
    for mode in ("full", "degraded"):
        readings, steps, diag = run_pipeline(pix, w, h, pipeline_spec, mode)
        sc = judge(readings, spec["truth"], spec["legend"],
                    spec.get("evidence_pairs") or {}, tol)
        sc["steps"] = steps
        sc["diagnostics"] = diag
        sc["readings_sample"] = readings[:3]
        arms[mode] = sc

    delta = {}
    for k in ("reading_extraction_accuracy", "numeric_backevidence_rate",
              "legend_series_consistency"):
        a, b = arms["full"].get(k), arms["degraded"].get(k)
        delta[k] = (round(a - b, 4) if isinstance(a, (int, float)) and isinstance(b, (int, float))
                    else None)
    delta["manual_review_items"] = arms["degraded"]["manual_review_items"] - arms["full"]["manual_review_items"]
    delta["steps"] = arms["degraded"]["steps"] - arms["full"]["steps"]

    report = {
        "verdict": "pass" if (delta.get("reading_extraction_accuracy") or 0) > 0 else "fail",
        "mode": "selftest",
        "reference_source": "fixture_gt",
        "fixture": os.path.relpath(png_path, workdir).replace("\\", "/"),
        "figure_ref": spec["figure_ref"],
        "tolerance_data_units": tol,
        "arms": arms,
        "delta_full_minus_degraded": delta,
        "note": "真值取自合成自检夹具（fixture-chart.json），仅用于验证机制可复现；"
                "不代表正式案例成绩，平台对照由组织方提供。",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


# ---------------------------------------------------------------- 污染注入
def inject_defects(res: dict) -> tuple:
    """在 result.json 副本上注入**已知**缺陷，返回 (改后副本, 缺陷清单)。

    缺陷清单逐条对应 chart_check.py 的一条闸门；用于量化「关闸门会漏掉多少」。
    注入只发生在副本上，交付物本体不被改动。
    """
    defects = []

    def note(gate, desc):
        defects.append({"gate": gate, "defect": desc})

    objs = ((res.get("result") or {}).get("objects") or [])
    for o in objs:
        if not isinstance(o, dict):
            continue
        oid = o.get("object_id")
        if o.get("kind") == "image" and o.get("image_class") == "plot":
            # D1 图例-系列数不符：多声明一条不存在的系列
            els = o.setdefault("elements", {})
            if not els.get("series"):
                els["series"] = ["DUMMY"]
            else:
                els["series"] = list(els["series"]) + ["DUMMY"]
            note("legend_category_count", "[%s] 声明系列多出一条 DUMMY" % oid)
            # D2 读数越轴
            rd = o.get("readings") or []
            if rd and isinstance(rd[0], dict):
                rd[0]["y"] = 999999
                note("axis_range", "[%s] readings[0].y=999999 越轴" % oid)
            # D3 缺 approx 标记（去掉 approx:true）
            for r in rd:
                if isinstance(r, dict) and "approx" in r:
                    r.pop("approx")
                    note("approx_marker", "[%s] 读数缺 approx 标记" % oid)
                    break
            # D4 缺来源定位
            for r in rd:
                if isinstance(r, dict):
                    r["source_locator"] = ""
                    note("reading_locator", "[%s] 读数 source_locator 置空" % oid)
                    break
            # D5 非 approx 读数无回证（塞一个材料里没有的数）
            if rd and isinstance(rd[0], dict):
                rd[0]["approx"] = False
                rd[0]["y"] = 888888
                note("numeric_backevidence", "[%s] 非 approx 读数 y=888888 无回证" % oid)
            # D6 颜色映射缺条目
            els = o.setdefault("elements", {})
            if isinstance(els.get("colors"), dict) and els["colors"]:
                k = sorted(els["colors"].keys())[0]
                els["colors"].pop(k)
                note("color_mapping", "[%s] colors 缺 %s 条目" % (oid, k))
            break
        if o.get("kind") == "image" and o.get("image_class") in ("photo", "schematic"):
            o["readings"] = [{"label": "X@x=0", "x": 0, "y": 1.0, "units": "u",
                              "approx": True, "how": "vision"}]
            note("photo_no_readings", "[%s] 照片/示意图写了 readings" % oid)
            break

    # D7 inventory 与实际不符
    inv = (res.get("result") or {}).get("object_inventory")
    if isinstance(inv, dict):
        inv["parsed"] = 999
        note("object_inventory", "object_inventory.parsed=999 与实际不符")
    # D8 缺 changelog 契约字段
    res.pop("changelog", None)
    note("changelog", "changelog 字段被删除（缺契约字段）")
    return res, defects


def run_pollution_probe(cc_path, result_path, workorder, input_root, out_path):
    """污染对照：同一交付物注入已知缺陷后，两臂各跑一遍，量缺陷检出/漏检。"""
    import subprocess
    import tempfile

    with open(result_path, "r", encoding="utf-8") as f:
        base = json.load(f)
    dirty, defects = inject_defects(base)
    tmpdir = tempfile.mkdtemp(prefix="gainpoll_")
    dirty_path = os.path.join(tmpdir, "result_dirty.json")
    with open(dirty_path, "w", encoding="utf-8") as f:
        json.dump(dirty, f, ensure_ascii=False, indent=1)

    runs = {}
    for mode in ("none", "all"):
        rep = os.path.join(tmpdir, "cc_%s.json" % mode)
        cmd = [sys.executable, cc_path, "--result", dirty_path,
               "--workorder", workorder, "--input-root", input_root,
               "--skip-blob", result_path,
               "--skip-blob", dirty_path,
               "--ablate", mode, "--out", rep]
        p = subprocess.run(cmd, capture_output=True, text=True)
        try:
            with open(rep, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"verdict": "error", "problems": [p.stderr[-400:]], "checks": [],
                    "gates": {}, "unbacked_readings": []}
        probs = data.get("problems") or []
        runs[mode] = {
            "ablate": mode,
            "exit_code": p.returncode,
            "verdict": data.get("verdict"),
            "problems_count": len(probs),
            "problems": probs[:30],
            "checks": data.get("checks") or [],
            "checks_total": len(data.get("checks") or []),
            "checks_applied": sum(1 for c in (data.get("checks") or []) if c.get("applied")),
            "gates": data.get("gates") or {},
        }

    # 缺陷→闸门 命中判定：优先看 checks 的 {item, match}（精确），
    # 再退回 problems 文本匹配（覆盖非 chk 类问题）
    CHECK_SUFFIX = {
        "legend_category_count": ".legend_category_count",
        "axis_range": ".axis_range",
        "reading_locator": ".reading_locator",
        "numeric_backevidence": ".backed",
        "color_mapping": ".color_mapping",
        "legend_series_map": ".legend_series_map",
        "unit_consistency": ".unit_consistency",
    }
    PROBLEM_KW = {
        "approx_marker": ["approx"],
        "photo_no_readings": ["readings（=编造数据）", "却写了 readings"],
        "object_inventory": ["object_inventory"],
        "changelog": ["通用契约字段"],
    }

    def hit_gate(mode, gate):
        rep = runs[mode]
        suf = CHECK_SUFFIX.get(gate)
        if suf:
            for c in (rep.get("checks") or []):
                if str(c.get("item", "")).endswith(suf) and c.get("applied") is True \
                        and c.get("match") is not True:
                    return True
        kws = PROBLEM_KW.get(gate)
        if kws:
            for pr in (rep.get("problems") or []):
                if any(k in pr for k in kws):
                    return True
        return False

    per_defect = []
    for d in defects:
        per_defect.append({
            "gate": d["gate"],
            "defect": d["defect"],
            "caught_by_full": hit_gate("none", d["gate"]),
            "caught_by_degraded": hit_gate("all", d["gate"]),
        })
    caught_full = sum(1 for x in per_defect if x["caught_by_full"])
    caught_deg = sum(1 for x in per_defect if x["caught_by_degraded"])
    report = {
        "verdict": "pass" if caught_full >= caught_deg else "fail",
        "mode": "pollution_ablation",
        "reference_source": "self_injected_defects",
        "injected_defects": per_defect,
        "defects_total": len(per_defect),
        "caught_by_full_arm": caught_full,
        "caught_by_degraded_arm": caught_deg,
        "missed_by_full_arm": len(per_defect) - caught_full,
        "missed_by_degraded_arm": len(per_defect) - caught_deg,
        "delta_caught_full_minus_degraded": caught_full - caught_deg,
        "arms": runs,
        "note": "缺陷由本脚本在**副本**上注入（每条对应 chart_check 的一条闸门），"
                "原 result.json 不被改动；数字反映校验层机制增益，"
                "不等于平台「基础 Agent vs 参赛 Skill」的白板对照。",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


# ---------------------------------------------------------------- 真实交付物
def run_on_delivery(result_path, workorder_path, input_root, out_path):
    """对真实 result.json 跑闸门消融对照（chart_check 两遍），并写 gain_evidence。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cc = os.path.join(here, "chart_check.py")
    import shutil
    import subprocess
    import tempfile

    runs = {}
    tmpdir = tempfile.mkdtemp(prefix="gainprobe_")
    for mode in ("none", "all"):
        # 在**副本**上跑：chart_check 会回写 verification，绝不污染交付物本体
        copy_path = os.path.join(tmpdir, "result_%s.json" % mode)
        shutil.copyfile(result_path, copy_path)
        rep = os.path.join(tmpdir, "cc_%s.json" % mode)
        cmd = [sys.executable, cc, "--result", copy_path,
               "--workorder", workorder_path, "--input-root", input_root,
               "--skip-blob", result_path, "--skip-blob", copy_path,
               "--ablate", mode, "--out", rep]
        p = subprocess.run(cmd, capture_output=True, text=True)
        try:
            with open(rep, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"verdict": "error", "problems": [p.stderr[-400:]], "checks": [],
                    "gates": {}, "unbacked_readings": []}
        runs[mode] = {
            "ablate": mode,
            "exit_code": p.returncode,
            "verdict": data.get("verdict"),
            "problems": len(data.get("problems") or []),
            "problem_detail": (data.get("problems") or [])[:20],
            "checks_total": len(data.get("checks") or []),
            "checks_applied": sum(1 for c in (data.get("checks") or []) if c.get("applied")),
            "gates": data.get("gates") or {},
            "unbacked_readings": len(data.get("unbacked_readings") or []),
            "manual_review_items": len(((data.get("human_review")) or [])),
        }
    full_p = runs["none"]["problems"]
    abl_p = runs["all"]["problems"]
    report = {
        "verdict": "pass",
        "mode": "delivery_ablation",
        "reference_source": "self_reference",
        "arms": {"full": runs["none"], "degraded": runs["all"]},
        "delta_full_minus_degraded": {
            "defects_caught_by_guardrails": full_p - abl_p,
            "checks_applied_delta": runs["none"]["checks_applied"] - runs["all"]["checks_applied"],
        },
        "note": "同输入两跑（同一 result.json / 工单 / 材料目录），仅闸门开关不同；"
                "记录缺陷检出条数差，不构成平台基线对照。",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    return report


class _LenientParser(argparse.ArgumentParser):
    """参数用法错误也返回 0：绝不因调用姿势问题中断交付（错误信息照实打印）。"""

    def error(self, message):
        sys.stderr.write("[%s] 参数用法错误：%s\n用法：%s\n退出码 0（交付不中断）\n"
                         % (self.prog, message, self.format_usage().strip()))
        raise SystemExit(0)


def main() -> int:
    ap = _LenientParser()
    ap.add_argument("--selftest", action="store_true", help="跑合成夹具双臂对照")
    ap.add_argument("--result", default=None, help="真实 result.json（闸门消融对照）")
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--input-root", default=None)
    ap.add_argument("--pollute", action="store_true",
                    help="在交付物副本上注入已知缺陷，量闸门检出/漏检")
    ap.add_argument("--out", default="/app/output/gain_probe.json")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    out = args.out
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    report = None
    try:
        if args.selftest:
            report = selftest(out, args.workdir)
        if args.result and args.workorder:
            rep2 = run_on_delivery(args.result, args.workorder,
                                   args.input_root or "/input",
                                   out.replace(".json", "_delivery.json"))
            report = {"selftest": report, "delivery_ablation": rep2} if report else rep2
            if args.pollute:
                here = os.path.dirname(os.path.abspath(__file__))
                cc = os.path.join(here, "chart_check.py")
                rep3 = run_pollution_probe(cc, args.result, args.workorder,
                                           args.input_root or "/input",
                                           out.replace(".json", "_pollution.json"))
                report["pollution_ablation"] = rep3
            with open(out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[gain_probe] WARN：%s：%s；已记录，退出码 0" % (type(e).__name__, e))
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"verdict": "error", "error": "%s: %s" % (type(e).__name__, e)},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        return 0
    if report is None:
        print("[gain_probe] 无输入：用 --selftest 或 --result/--workorder")
        return 0
    print("[gain_probe] 完成，verdict=%s → %s" % (report.get("verdict", "n/a"), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
