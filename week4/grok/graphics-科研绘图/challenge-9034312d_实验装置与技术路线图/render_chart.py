"""render_chart — data-driven scientific charts with bidirectional data binding.

Core of the source_value_chart skill (and chart panels of graphical_abstract).
Every glyph (bar, point, cell, wedge) is bound to the exact source file/row/column
and value, recorded in provenance.data_map so a reviewer can trace any mark back
to the data and re-render after a data edit. Legend is generated from the same
series mapping, so legend and glyphs cannot drift apart.

Usage:
  python render_chart.py --ir figure_ir.json --out /app/output [--data path.csv]

Requires matplotlib + numpy (preinstalled scientific-python). Degrades gracefully
if optional fonts/formats are unavailable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import figkit

HERE = Path(__file__).resolve().parent


def _load_resource(name):
    return figkit.load_json(HERE / name)


def _setup_fonts(style):
    """Prefer the requested family; fall back to an available CJK font so Chinese
    labels never render as boxes. Returns the family actually used."""
    requested = style.get("font_family", "DejaVu Sans")
    available = {f.name for f in font_manager.fontManager.ttflist}
    if requested in available:
        plt.rcParams["font.family"] = requested
        return requested
    cjk_candidates = ["Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
                      "Microsoft YaHei", "SimHei", "PingFang SC", "Arial Unicode MS", "DejaVu Sans"]
    for cand in cjk_candidates:
        if cand in available:
            plt.rcParams["font.family"] = cand
            return cand
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


def _palette(style):
    pals = _load_resource("palettes.json")
    name = style.get("palette", "okabe_ito")
    return pals.get(name, pals["okabe_ito"])


def _apply_style(style):
    used_font = _setup_fonts(style)
    plt.rcParams.update({
        "font.size": style.get("base_font_pt", 8),
        "axes.linewidth": style.get("line_width_pt", 0.8),
        "axes.labelsize": style.get("base_font_pt", 8),
        "xtick.labelsize": style.get("base_font_pt", 8) - 1,
        "ytick.labelsize": style.get("base_font_pt", 8) - 1,
        "legend.fontsize": style.get("base_font_pt", 8) - 1,
        "figure.dpi": style.get("dpi", 300),
        "savefig.dpi": style.get("dpi", 300),
        "svg.fonttype": "none",  # keep text editable in SVG (not outlined)
        "pdf.fonttype": 42,      # embed TrueType fonts in PDF
        "ps.fonttype": 42,
    })
    return used_font


def _resolve_data(ir, chart, override=None):
    path = override or chart.get("data_path")
    if not path:
        # try to resolve from sources registry locator
        src = next((s for s in ir.get("sources", []) if s.get("id") == chart.get("data_source")), None)
        if src:
            loc = src.get("locator", "")
            cand = loc.split()[0] if loc else ""
            if cand and Path(cand).exists():
                path = cand
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"chart data not found: {path!r}. Bind chart.data_path to the actual source table.")
    rows = figkit.read_table(path)
    return rows, str(path)


def _series_groups(rows, chart):
    series_col = chart.get("series")
    xcol = chart.get("x")
    if series_col:
        keys = list(dict.fromkeys(str(r.get(series_col)) for r in rows))
        groups = {k: [r for r in rows if str(r.get(series_col)) == k] for k in keys}
    else:
        groups = {"": rows}
    return groups


def render(ir: dict, out_dir: Path, data_override=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    chart = ir["chart"]
    style = ir.get("style", {})
    used_font = _apply_style(style)
    colors = _palette(style)
    rows, data_path = _resolve_data(ir, chart, data_override)
    ctype = chart.get("chart_type", "bar")
    data_map = {}
    element_map = ir.setdefault("provenance", {}).setdefault("element_map", {})

    canvas = ir.get("canvas", {})
    w_in = canvas.get("width_mm", 180) / 25.4
    h_in = canvas.get("height_mm", 120) / 25.4

    if ctype == "multi_panel":
        fig, axes = plt.subplots(1, len(chart["panels"]), figsize=(w_in, h_in), squeeze=False)
        for i, panel in enumerate(chart["panels"]):
            sub = dict(chart)
            sub.update(panel)
            sub["chart_type"] = panel.get("chart_type", "bar")
            _draw_single(axes[0][i], sub, rows, colors, data_map, f"panel{chr(65+i)}")
            axes[0][i].set_title(panel.get("title", chr(65 + i)), fontsize=style.get("base_font_pt", 8) + 1, loc="left", fontweight="bold")
        fig.tight_layout()
    else:
        fig, ax = plt.subplots(figsize=(w_in, h_in))
        _draw_single(ax, chart, rows, colors, data_map, "chart")
        fig.tight_layout()

    # exports
    stem = out_dir / "figure"
    exports = ir.get("exports", [{"format": "svg"}, {"format": "pdf"}, {"format": "png"}])
    written = []
    for ex in exports:
        fmt = ex.get("format", "png")
        dpi = ex.get("dpi", style.get("dpi", 300))
        path = stem.with_suffix("." + fmt)
        try:
            fig.savefig(path, dpi=dpi, format=fmt, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            written.append({"name": path.name, "path": str(path), "format": fmt,
                            "role": fmt, "dpi": dpi})
        except Exception as e:  # noqa: BLE001 - report, don't crash the whole run
            ir.setdefault("uncertainty", []).append(
                {"item": f"export {fmt}", "reason": str(e), "impact": "format unavailable", "handling": "skipped; other formats produced"})
    plt.close(fig)

    ir["provenance"]["data_map"] = data_map
    ir["provenance"]["data_path"] = data_path
    ir["provenance"]["font_used"] = used_font
    return {"artifacts": written, "data_map": data_map, "font_used": used_font,
            "n_rows": len(rows), "data_path": data_path}


def _draw_single(ax, chart, rows, colors, data_map, prefix):
    ctype = chart.get("chart_type", "bar")
    xcol, ycol = chart.get("x"), chart.get("y")
    ecol, ekind = chart.get("error"), chart.get("error_kind", "unknown")
    groups = _series_groups(rows, chart)
    handles = []

    if ctype in ("bar", "grouped_bar"):
        xkeys = list(dict.fromkeys(str(r.get(xcol)) for r in rows))
        series_keys = list(groups.keys())
        n_s = max(1, len(series_keys))
        width = 0.8 / n_s
        for si, sk in enumerate(series_keys):
            grp = groups[sk]
            vals, errs, xs = [], [], []
            for xi, xk in enumerate(xkeys):
                match = [r for r in grp if str(r.get(xcol)) == xk]
                v = figkit.to_float(match[0].get(ycol)) if match else None
                vals.append(v if v is not None else np.nan)
                e = figkit.to_float(match[0].get(ecol)) if (match and ecol) else None
                errs.append(e if e is not None else 0)
                xs.append(xi + (si - (n_s - 1) / 2) * width)
                if match:
                    r0 = match[0]
                    row_idx = rows.index(r0)
                    gid = f"{prefix}_bar_{si}_{xi}"
                    data_map[gid] = {"file": chart.get("data_path"), "row": row_idx,
                                     "column": ycol, "value": v, "x": xk, "series": sk,
                                     "error": e, "error_kind": ekind}
            color = colors[si % len(colors)]
            label = sk if sk else (ycol or "value")
            bars = ax.bar(xs, vals, width=width, color=color, label=label,
                          edgecolor="black", linewidth=0.4,
                          yerr=errs if ecol else None,
                          error_kw={"elinewidth": 0.6, "capsize": 2})
            handles.append(bars)
        ax.set_xticks(range(len(xkeys)))
        ax.set_xticklabels(xkeys)

    elif ctype == "line":
        for si, (sk, grp) in enumerate(groups.items()):
            grp_sorted = grp
            xs = [figkit.to_float(r.get(xcol)) for r in grp_sorted]
            ys = [figkit.to_float(r.get(ycol)) for r in grp_sorted]
            color = colors[si % len(colors)]
            line, = ax.plot(xs, ys, marker="o", markersize=3, color=color,
                            label=sk or (ycol or "value"), linewidth=style_lw(chart))
            for j, r in enumerate(grp_sorted):
                gid = f"{prefix}_pt_{si}_{j}"
                data_map[gid] = {"file": chart.get("data_path"), "row": rows.index(r),
                                 "column": ycol, "value": ys[j], "x": xs[j], "series": sk}
            handles.append(line)

    elif ctype == "scatter":
        for si, (sk, grp) in enumerate(groups.items()):
            xs = [figkit.to_float(r.get(xcol)) for r in grp]
            ys = [figkit.to_float(r.get(ycol)) for r in grp]
            color = colors[si % len(colors)]
            sc = ax.scatter(xs, ys, s=18, color=color, label=sk or (ycol or "value"),
                            edgecolor="black", linewidth=0.3)
            for j, r in enumerate(grp):
                data_map[f"{prefix}_sc_{si}_{j}"] = {"file": chart.get("data_path"),
                    "row": rows.index(r), "column": ycol, "value": ys[j], "x": xs[j], "series": sk}
            handles.append(sc)

    elif ctype == "box":
        series_keys = list(groups.keys())
        data = [[figkit.to_float(r.get(ycol)) for r in groups[sk] if figkit.to_float(r.get(ycol)) is not None] for sk in series_keys]
        bp = ax.boxplot(data, labels=series_keys, patch_artist=True, widths=0.6)
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(colors[i % len(colors)])
            patch.set_edgecolor("black")
            patch.set_linewidth(0.5)
        for si, sk in enumerate(series_keys):
            for j, r in enumerate(groups[sk]):
                data_map[f"{prefix}_box_{si}_{j}"] = {"file": chart.get("data_path"),
                    "row": rows.index(r), "column": ycol, "value": figkit.to_float(r.get(ycol)), "series": sk}

    elif ctype == "heatmap":
        # rows as y categories, columns numeric; or matrix from x/y/value
        xkeys = list(dict.fromkeys(str(r.get(xcol)) for r in rows))
        ykeys = list(dict.fromkeys(str(r.get(chart.get("series"))) for r in rows)) if chart.get("series") else [""]
        mat = np.full((len(ykeys), len(xkeys)), np.nan)
        for r in rows:
            xi = xkeys.index(str(r.get(xcol)))
            yi = ykeys.index(str(r.get(chart.get("series")))) if chart.get("series") else 0
            v = figkit.to_float(r.get(ycol))
            mat[yi, xi] = v
            data_map[f"{prefix}_cell_{yi}_{xi}"] = {"file": chart.get("data_path"),
                "row": rows.index(r), "column": ycol, "value": v, "x": xkeys[xi], "y": ykeys[yi]}
        im = ax.imshow(mat, aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(xkeys))); ax.set_xticklabels(xkeys)
        ax.set_yticks(range(len(ykeys))); ax.set_yticklabels(ykeys)
        plt.colorbar(im, ax=ax, label=chart.get("unit", ycol or ""))

    elif ctype == "pie":
        vals = [figkit.to_float(r.get(ycol)) for r in rows]
        labels = [str(r.get(xcol)) for r in rows]
        wedges, _ = ax.pie(vals, labels=labels, colors=colors[:len(rows)],
                           wedgeprops={"edgecolor": "white", "linewidth": 0.5})
        for j, r in enumerate(rows):
            data_map[f"{prefix}_wedge_{j}"] = {"file": chart.get("data_path"),
                "row": rows.index(r), "column": ycol, "value": vals[j], "label": labels[j]}

    # labels, units, legend
    if chart.get("x_label"):
        ax.set_xlabel(chart["x_label"])
    elif xcol and ctype not in ("pie",):
        ax.set_xlabel(xcol + (f" ({chart['unit']})" if chart.get("unit") and ctype != "heatmap" else ""))
    if chart.get("y_label"):
        ax.set_ylabel(chart["y_label"])
    elif ycol and ctype not in ("pie", "heatmap"):
        ax.set_ylabel(ycol + (f" ({chart['unit']})" if chart.get("unit") else ""))

    if handles and ctype not in ("pie", "heatmap") and len(groups) >= 1:
        ax.legend(frameon=False, loc="best")

    # significance brackets
    for sig in chart.get("significance", []):
        try:
            a, b = sig["a"], sig["b"]
            y = sig.get("y")
            ax.plot([a, a, b, b], [y, y + 0.5, y + 0.5, y], lw=0.6, c="black")
            ax.text((a + b) / 2, y + 0.6, sig.get("label", "*"), ha="center", fontsize=7)
        except Exception:
            pass

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def style_lw(chart):
    return chart.get("_lw", 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--data", default=None)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    v = figkit.validate_ir(ir)
    if not v["ok"]:
        print(json.dumps({"status": "invalid_ir", "errors": v["errors"]}, ensure_ascii=False))
        sys.exit(2)
    res = render(ir, Path(args.out), args.data)
    figkit.write_json(Path(args.out) / "figure_ir.json", ir)
    print(json.dumps({"status": "ok", **{k: res[k] for k in ("n_rows", "data_path", "font_used")},
                      "artifacts": [a["path"] for a in res["artifacts"]],
                      "warnings": v["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()