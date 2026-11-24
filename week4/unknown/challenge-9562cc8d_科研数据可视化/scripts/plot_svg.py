#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plot_svg.py — 手写 SVG 科研图表渲染器（零第三方依赖，无 matplotlib）。

用法:
  python3 plot_svg.py --chart line --data data.csv --x 时间 --y 温度 \
      --title "..." --xlabel "时间" --xunit "s" --ylabel "温度" --yunit "℃" \
      --source "数据来源: ..." --out figure.svg
  --chart 支持 line | scatter | bar | stacked_bar | histogram
  （--no-selfdesc 为消融开关：剥离标题/来源/单位/图例，供 gain_probe 对照实测）

自描述与可回证设计（verify_check.py 逐点复算的锚点）:
  · 标题/来源/轴标目+单位/图例全部为 <text> 节点（可编辑、可机检）
  · 轴组携带 data-min/data-max/data-px-min/data-px-max 刻度元数据；
    两轴统一公式 p(v)=pxmin+(v-vmin)/(vmax-vmin)*(pxmax-pxmin)
  · 每个数据标记携带原始数值 data-x/data-xv/data-y(/data-series/data-bottom/
    data-bin-*)，像素坐标由 verify_check 依据轴元数据独立复算
  · bar/stacked 柜位公式：slot=(PR-PL)/n，rect 左缘=PL+(idx+0.2)*slot，
    宽=0.6*slot，n=类别数（分类横轴在 axis-x data-categories 以"|"分隔）
退出码恒 0，结论写进 stdout JSON。
"""
import argparse, json, math, os, sys
from xml.sax.saxutils import escape

# CHARTVIZ-MARKER: plot_svg

W, H = 900, 560
L, R, T, B = 80, 60, 70, 80
PL, PR, PT, PB = L, W - R, T, H - B
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
# 防汉字陷阱：本包一律用 ASCII 数值正则判定数字，禁用 str.isalpha
NUM_RE = None  # 实际判定复用 chart_select.is_number


def nice_ticks(vmin, vmax, n=6):
    if vmax <= vmin:
        vmax = vmin + 1
    raw = (vmax - vmin) / max(1, n)
    k = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = next((c * k for c in (1, 2, 5, 10) if raw <= c * k), 10 * k)
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    ticks, v = [], lo
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    return ticks


def fmt(v):
    if abs(v - round(v)) < 1e-9 and abs(v) < 1e7:
        return str(int(round(v)))
    return "%.4g" % v


def fattr(v):
    """data-* 属性专用：全精度输出，供 verify_check 逐点复算（fmt 的 %.4g 会引入复算误差）。"""
    return "%.10g" % float(v)


def axis_scale(vmin, vmax):
    if vmin == vmax:
        vmin, vmax = vmin - 1, vmax + 1
    ticks = nice_ticks(vmin, vmax)
    return min(ticks[0], vmin), max(ticks[-1], vmax), ticks


def to_px(v, vmin, vmax, pxmin, pxmax):
    return pxmin + (v - vmin) / (vmax - vmin) * (pxmax - pxmin)


def num(s):
    try:
        return float(str(s).strip())
    except Exception:
        return None


def group_rows(rows, x, y, series, agg="mean", numeric_x=False):
    """按 (x[,series]) 聚合 y（mean/sum），数值缺失行跳过并登记。
    numeric_x 仅在折线/散点时开启：分类柱状图的类别必须保留原始字符串，
    不能被 num() 转成 float（否则与 CSV 类别字符串对不上）。"""
    buckets, skipped = {}, []
    for i, r in enumerate(rows):
        xv = r.get(x, "")
        if numeric_x and num(xv) is not None:
            xv = num(xv)
        yv = num(r.get(y, ""))
        if yv is None or xv in ("", None):
            skipped.append({"row": i, "reason": "y 或 x 缺失/非数值，已跳过"})
            continue
        key = str(r.get(series)) if series else "__all__"
        buckets.setdefault((xv, key), []).append(yv)
    out = []
    for (xv, key), vals in buckets.items():
        out.append({"x": xv, "series": key, "n": len(vals),
                    "y": (sum(vals) / len(vals)) if agg == "mean" else sum(vals)})
    def xkey(p):
        f = p["x"] if isinstance(p["x"], float) else None
        return (0, f, "") if f is not None else (1, 0.0, str(p["x"]))
    out.sort(key=lambda p: (xkey(p), p["series"]))
    return out, skipped


def build_svg(chart, rows, header, x, y, series=None, agg="mean", bins=10,
              title="", xlabel="", ylabel="", xunit="", yunit="", source="",
              no_selfdesc=False):
    exc = []
    if chart == "histogram":  # 直方图直接对 x 列全量分箱，不依赖 y 列
        raw_all = [num(r.get(x, "")) for r in rows]
        missing = sum(1 for v in raw_all if v is None)
        raw_x = [v for v in raw_all if v is not None]
        skipped = []
        if missing:
            exc.append({"item": "hist_missing_values",
                        "detail": "%d 行 x 列缺失/非数值，未计入分箱" % missing})
        pts = [{"x": v, "series": "__all__", "y": 0.0, "n": 1} for v in raw_x]
    else:
        pts, skipped = group_rows(rows, x, y, series,
                                  agg="sum" if chart == "stacked_bar" else agg,
                                  numeric_x=chart in ("line", "scatter"))
        exc += [{"row": s["row"], "detail": s["reason"]} for s in skipped]
    if not pts:
        exc.append({"item": "no_plottable_rows", "detail": "无可用数值行，交付空框架图"})
    if no_selfdesc:
        title, xunit, yunit, source = "", "", "", ""

    if chart == "histogram":  # 分箱计数在定标前完成，y 轴量纲=频数
        allx = [p["x"] for p in pts]
        hist_lo, hist_hi = (min(allx), max(allx)) if allx else (0, 1)
        hist_bwid = (hist_hi - hist_lo) / max(1, bins) if hist_hi > hist_lo else 1.0
        counts = [0] * max(1, bins)
        for v in allx:
            k = min(max(1, bins) - 1, int((v - hist_lo) / hist_bwid) if hist_bwid else 0)
            counts[k] += 1
    yvals = (list(counts) if chart == "histogram"
             else [p["y"] for p in pts] + [p.get("bottom", 0.0) for p in pts])
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="Noto Sans CJK SC, SimHei, sans-serif">'
           % (W, H, W, H)]
    svg.append('<g id="layer-frame"><rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/></g>' % (W, H))

    # ---- Y 轴刻度元数据 ----
    ymin_d, ymax_d = (min(yvals), max(yvals)) if yvals else (0, 1)
    if chart in ("bar", "stacked_bar", "histogram"):
        ymin_d = min(0.0, ymin_d)
    yv0, yv1, yticks = axis_scale(ymin_d, ymax_d)
    if chart == "histogram":
        yv0 = 0
    ypx = lambda v: to_px(v, yv0, yv1, PB, PT)
    baseline = ypx(max(0, yv0))

    # ---- X 轴 ----
    xcat = chart in ("bar", "stacked_bar")
    if xcat:
        cats = sorted({str(p["x"]) for p in pts})
        n = max(1, len(cats))
        slot = (PR - PL) / n
        centers = {c: PL + (i + 0.5) * slot for i, c in enumerate(cats)}
        x_attr = ('data-categories="%s" data-min="0" data-max="%d" '
                  'data-px-min="%s" data-px-max="%s"' % (
                      escape("|".join(cats)), n - 1,
                      fmt(centers[cats[0]]), fmt(centers[cats[-1]])))
        xt = [(c, centers[c]) for c in cats]
        xdisp = (xlabel or x or "")
    elif chart == "histogram":
        allx = [float(p["x"]) for p in pts if isinstance(p["x"], float)]
        lo, hi = (min(allx), max(allx)) if allx else (0, 1)
        bwid = (hi - lo) / max(1, bins) if hi > lo else 1.0
        xv0, xv1, xticks = axis_scale(lo, lo + bwid * max(1, bins))
        x_attr = 'data-min="%s" data-max="%s" data-px-min="%d" data-px-max="%d"' % (
            fattr(xv0), fattr(xv1), PL, PR)
        xt = [(fmt(t), to_px(t, xv0, xv1, PL, PR)) for t in xticks]
        xdisp = (xlabel or x or "")
    else:  # line / scatter
        all_num = all(isinstance(p["x"], float) for p in pts) and pts
        if all_num:
            xv0, xv1, xticks = axis_scale(min(p["x"] for p in pts),
                                          max(p["x"] for p in pts))
            for p in pts:
                p["xv"] = p["x"]
            x_attr = 'data-min="%s" data-max="%s" data-px-min="%d" data-px-max="%d"' % (
                fattr(xv0), fattr(xv1), PL, PR)
            xt = [(fmt(t), to_px(t, xv0, xv1, PL, PR)) for t in xticks]
        else:  # datetime/文本横轴：按出现序等距，data-min/max 为索引区间
            order = {}
            for p in pts:
                s = str(p["x"])
                if s not in order:
                    order[s] = len(order)
                p["xv"] = float(order[s])
            n = max(1, len(order))
            xmin_i, xmax_i = -0.5, n - 0.5
            x_attr = ('data-categorical-index="1" data-min="%s" data-max="%s" '
                      'data-px-min="%d" data-px-max="%d"' % (fattr(xmin_i), fattr(xmax_i), PL, PR))
            xt = [(s, to_px(float(k), xmin_i, xmax_i, PL, PR))
                  for s, k in sorted(order.items(), key=lambda kv: kv[1])]
        xdisp = (xlabel or x or "")

    svg.append('<g id="layer-axis">')
    svg.append('<g id="axis-x" %s data-label="%s" data-unit="%s">' % (
        x_attr, escape(xdisp), escape(xunit)))
    svg.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333" stroke-width="1.5"/>' % (PL, PB, PR, PB))
    for lab, px in xt:
        svg.append('<g class="tick-x"><line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#333"/>'
                   '<text x="%.2f" y="%d" font-size="12" text-anchor="middle">%s</text></g>'
                   % (px, PB, px, PB + 5, px, PB + 20, escape(str(lab))))
    xfull = xdisp + ((" (%s)" % xunit) if xunit else "")
    svg.append('<text id="xlabel" x="%d" y="%d" font-size="14" text-anchor="middle">%s</text>'
               % ((PL + PR) // 2, H - 28, escape(xfull)))
    svg.append('</g>')
    svg.append('<g id="axis-y" data-min="%s" data-max="%s" data-px-min="%d" data-px-max="%d" '
               'data-label="%s" data-unit="%s">' % (
                   fattr(yv0), fattr(yv1), PB, PT, escape(ylabel or y or ""), escape(yunit)))
    svg.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333" stroke-width="1.5"/>' % (PL, PT, PL, PB))
    for t in yticks:
        py = ypx(t)
        if PT - 2 <= py <= PB + 2:
            svg.append('<g class="tick-y"><line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#999"/>'
                       '<text x="%d" y="%.2f" font-size="12" text-anchor="end">%s</text></g>'
                       % (PL - 6, py, PL, py, PL - 9, py + 4, escape(fmt(t))))
    yfull = (ylabel or y or "") + ((" (%s)" % yunit) if yunit else "")
    svg.append('<text id="ylabel" x="22" y="%d" font-size="14" text-anchor="middle" '
               'transform="rotate(-90 22 %d)">%s</text>' % ((PT + PB) // 2, (PT + PB) // 2, escape(yfull)))
    svg.append('</g></g>')

    # ---- 数据标记层 ----
    svg.append('<g id="layer-marks">')
    if chart in ("line", "scatter"):
        ser_names = sorted({p["series"] for p in pts})
        for si, sname in enumerate(ser_names):
            col = PALETTE[si % len(PALETTE)]
            sp = [p for p in pts if p["series"] == sname and p.get("xv") is not None]
            svg.append('<g id="series-%d" data-name="%s" data-color="%s">' % (si, escape(str(sname)), col))
            if chart == "line" and len(sp) > 1:
                svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' % (
                    col, " ".join("%.2f,%.2f" % (to_px(p["xv"], xv0, xv1, PL, PR), ypx(p["y"]))
                                  for p in sp)))
            for i, p in enumerate(sp):
                svg.append('<g id="pt-%03d" data-x="%s" data-xv="%s" data-y="%s" data-series="%s">'
                           '<circle cx="%.2f" cy="%.2f" r="3.5" fill="%s"/></g>' % (
                               i, escape(str(p["x"])), fattr(p["xv"]), fattr(p["y"]),
                               escape(str(sname)), to_px(p["xv"], xv0, xv1, PL, PR),
                               ypx(p["y"]), col))
            svg.append('</g>')
    elif chart == "bar":
        cats = sorted({str(p["x"]) for p in pts})
        n = max(1, len(cats))
        slot = (PR - PL) / n
        bw = slot * 0.6
        for i, p in enumerate(sorted(pts, key=lambda q: (cats.index(str(q["x"])), q["series"]))):
            k = cats.index(str(p["x"]))
            pxb = PL + (k + 0.2) * slot
            top = ypx(p["y"])
            yr, hgt = (top, baseline - top) if p["y"] >= 0 else (baseline, top - baseline)
            svg.append('<rect id="bar-%03d" data-x="%s" data-y="%s" x="%.2f" y="%.2f" '
                       'width="%.2f" height="%.2f" fill="%s"/>' % (
                           i, escape(str(p["x"])), fattr(p["y"]), pxb, yr, bw, max(0.5, hgt), PALETTE[0]))
            svg.append('<text class="value-label" x="%.2f" y="%.2f" font-size="11" '
                       'text-anchor="middle">%s</text>' % (pxb + bw / 2, top - 4, escape(fmt(p["y"]))))
    elif chart == "stacked_bar":
        cats = sorted({str(p["x"]) for p in pts})
        ser_names = sorted({p["series"] for p in pts})
        n = max(1, len(cats))
        slot = (PR - PL) / n
        bw = slot * 0.6
        per_cat = {}
        for p in pts:
            per_cat[(str(p["x"]), p["series"])] = p["y"]
        idx = 0
        for ci, cat in enumerate(cats):
            bottom = 0.0
            for si, sname in enumerate(ser_names):
                v = per_cat.get((cat, sname), 0.0)
                top = bottom + v
                pxb = PL + (ci + 0.2) * slot
                y1, y2 = ypx(top), ypx(bottom)
                svg.append('<rect id="seg-%03d" data-x="%s" data-series="%s" data-y="%s" '
                           'data-bottom="%s" x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (
                               idx, escape(cat), escape(str(sname)), fattr(v), fattr(bottom),
                               pxb, min(y1, y2), bw, max(0.5, abs(y2 - y1)),
                               PALETTE[si % len(PALETTE)]))
                bottom = top
                idx += 1
    elif chart == "histogram":
        for k, c in enumerate(counts):
            b0, b1 = hist_lo + k * hist_bwid, hist_lo + (k + 1) * hist_bwid
            x1 = to_px(b0, xv0, xv1, PL, PR)
            x2 = to_px(b1, xv0, xv1, PL, PR)
            top = ypx(c)
            svg.append('<rect id="bin-%03d" data-bin-start="%s" data-bin-end="%s" data-count="%d" '
                       'x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="#ffffff"/>' % (
                           k, fattr(b0), fattr(b1), c, x1, top, max(0.5, x2 - x1),
                           max(0.5, baseline - top), PALETTE[0]))
    svg.append('</g>')

    # ---- 标注层（自描述） ----
    svg.append('<g id="layer-labels">')
    if title:
        svg.append('<text id="chart-title" x="%d" y="34" font-size="18" text-anchor="middle" '
                   'font-weight="bold">%s</text>' % (W // 2, escape(title)))
    if source:
        svg.append('<text id="chart-source" x="%d" y="%d" font-size="11">%s</text>'
                   % (L, H - 8, escape(source)))
    svg.append('<text id="n-note" x="%d" y="52" font-size="11">n=%d 个绘图数据点%s</text>'
               % (L, len(pts), ("；跳过 %d 行缺失" % len(skipped)) if skipped else ""))
    svg.append('</g>')

    # ---- 图例 ----
    svg.append('<g id="layer-legend">')
    ser_names = (sorted({str(p["series"]) for p in pts}) if chart != "histogram"
                 else [y or "频数"])
    for si, sname in enumerate(ser_names[:6]):
        col = PALETTE[si % len(PALETTE)]
        lx = PR - 40
        svg.append('<g id="legend-item-%d" data-series="%s">'
                   '<rect x="%d" y="%d" width="14" height="10" fill="%s"/>'
                   '<text x="%d" y="%d" font-size="12">%s</text></g>' % (
                       si, escape(sname), lx - 130, PT + 8 + si * 18, col,
                       lx - 110, PT + 17 + si * 18, escape(sname)))
    svg.append('</g>')
    svg.append('</svg>')
    return ("\n".join(svg),
            {"chart": chart, "n_marks": len(pts), "skipped_rows": len(skipped),
             "y_axis": {"min": fattr(yv0), "max": fattr(yv1)},
             "selfdesc": not no_selfdesc, "exceptions": exc})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chart", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--x", required=True)
    ap.add_argument("--y", default=None, help="直方图可省略（分箱只依赖 --x 列）")
    ap.add_argument("--series", default=None)
    ap.add_argument("--agg", default="mean", choices=["mean", "sum"])
    ap.add_argument("--bins", type=int, default=10)
    ap.add_argument("--title", default="")
    ap.add_argument("--xlabel", default="")
    ap.add_argument("--ylabel", default="")
    ap.add_argument("--xunit", default="")
    ap.add_argument("--yunit", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", default="figure.svg")
    ap.add_argument("--no-selfdesc", action="store_true", help="消融开关")
    args = ap.parse_args()
    out = {"ok": False}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from chart_select import read_csv
        if args.chart != "histogram" and not args.y:
            raise ValueError("除 histogram 外必须提供 --y 数值列")
        rows, header = read_csv(args.data)
        svg, meta = build_svg(args.chart, rows, header, args.x, args.y,
                              args.series, args.agg, args.bins, args.title,
                              args.xlabel, args.ylabel, args.xunit, args.yunit,
                              args.source, args.no_selfdesc)
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(svg)
        out.update(meta)
        out.update({"ok": True, "svg": args.out})
    except Exception as e:
        out = {"ok": False, "error": str(e), "chart": args.chart,
               "status": "render_failed_svg_not_written"}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
