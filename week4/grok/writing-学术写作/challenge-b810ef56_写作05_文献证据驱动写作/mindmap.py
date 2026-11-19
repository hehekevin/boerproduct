"""mindmap — source-bound, editable mind map from a tree IR (stdlib SVG + matplotlib).

For the mind_map workorder: nodes carry label + source/evidence; hierarchy is a tidy
horizontal tree; cross-links express typed relations (causal/dependency/contrast/
temporal/citation/support/conflict) with distinct styles; evidence tags attach to
nodes. Emits a layered editable SVG (svgkit) + consistent PNG/PDF. No invented
nodes/edges: every node/relation must cite the material.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

import figkit
import svgkit

REL_STYLE = {
    "causal": ("#D55E00", "-|>", None),
    "dependency": ("#0072B2", "-|>", None),
    "contrast": ("#CC79A7", "-", "2,2"),
    "temporal": ("#009E73", "-|>", None),
    "citation": ("#56B4E9", "-|>", "2,1"),
    "support": ("#009E73", "-|>", None),
    "conflict": ("#D55E00", "-[", "2,2"),
    "contains": ("#999999", "-", "1,1"),
}


def _layout(ir):
    """Tidy horizontal tree: root left, depth->x, leaf order->y."""
    nodes = {n["id"]: n for n in ir.get("nodes", [])}
    children = {nid: [] for nid in nodes}
    roots = []
    for n in ir.get("nodes", []):
        p = n.get("parent")
        if p and p in nodes:
            children[p].append(n["id"])
        else:
            roots.append(n["id"])
    pos = {}
    leaf_y = [0.0]

    def place(nid, depth):
        kids = children[nid]
        if not kids:
            y = leaf_y[0]; leaf_y[0] += 1.0
        else:
            ys = [place(k, depth + 1) for k in kids]
            y = sum(ys) / len(ys)
        pos[nid] = {"x": depth, "y": y}
        return y

    for r in roots:
        place(r, 0)
    maxd = max((p["x"] for p in pos.values()), default=0)
    maxy = max((p["y"] for p in pos.values()), default=0)
    return pos, maxd, maxy


def render(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    pos, maxd, maxy = _layout(ir)
    nodes = {n["id"]: n for n in ir.get("nodes", [])}
    hw = {nid: max(15, min(25, 2 + 0.8 * len(str(n.get("label", nid))))) for nid, n in nodes.items()}
    W = 60 + maxd * 60
    H = 30 + maxy * 16
    canvas = {"width_mm": W, "height_mm": H, "background": "#ffffff"}
    layers = {"edges": [], "nodes": [], "labels": [], "links": [], "legend": []}

    def xy(nid):
        p = pos[nid]
        return 20 + p["x"] * 60, 15 + p["y"] * 16

    # tree edges (contains)
    for n in ir.get("nodes", []):
        if n.get("parent") and n["parent"] in pos:
            x1, y1 = xy(n["parent"]); x2, y2 = xy(n["id"])
            a, b = hw[n["parent"]], hw[n["id"]]
            layers["edges"].append({"type": "path", "id": f"tree_{n['id']}",
                                    "d": f"M {x1+a},{y1} C {x1+a+12},{y1} {x2-b-12},{y2} {x2-b},{y2}",
                                    "stroke": "#9bb3cc", "stroke_width": 0.4})
    # nodes + labels + evidence tag
    for nid, n in nodes.items():
        x, y = xy(nid)
        depth = pos[nid]["x"]
        w = hw[nid]
        fill = "#0C5DA5" if depth == 0 else ("#e8f0fa" if depth == 1 else "#ffffff")
        tcol = "#ffffff" if depth == 0 else "#000000"
        layers["nodes"].append({"type": "rect", "id": f"node_{nid}", "x": x - w, "y": y - 5,
                                "w": 2 * w, "h": 10, "fill": fill, "stroke": "#0C5DA5",
                                "stroke_width": 0.4, "rx": 2, "source": n.get("source"),
                                "source_locator": n.get("source_locator")})
        layers["labels"].append({"type": "text", "x": x, "y": y, "text": n.get("label", nid),
                                 "font_pt": 8 if depth else 9, "fill": tcol,
                                 "font_weight": "bold" if depth == 0 else None,
                                 "source": n.get("source")})
        if n.get("evidence"):
            layers["labels"].append({"type": "text", "x": x, "y": y + 6.5, "text": "[" + n["evidence"] + "]",
                                     "font_pt": 5.5, "fill": "#666666"})
    # cross relation links
    used = []
    for r in ir.get("relations", []):
        a, b = pos.get(r["from"]), pos.get(r["to"])
        if not a or not b:
            continue
        x1, y1 = xy(r["from"]); x2, y2 = xy(r["to"])
        col, arrow, dash = REL_STYLE.get(r["type"], ("#000000", "-|>", None))
        if r["type"] not in used:
            used.append(r["type"])
        layers["links"].append({"type": "path", "id": f"rel_{r['id']}",
                                "d": f"M {x1},{y1+5} Q {(x1+x2)/2},{max(y1,y2)+14} {x2},{y2+5}",
                                "stroke": col, "stroke_width": 0.5, "dash": dash,
                                "marker_end": "arr-activate" if arrow == "-|>" else ("bar-inhibit" if arrow == "-[" else None),
                                "source": r.get("source"), "category": r["type"]})
    # legend
    lx, ly = W - 34, 8
    layers["legend"].append({"type": "text", "x": lx, "y": ly, "text": "Relations", "anchor": "start",
                             "font_pt": 7, "font_weight": "bold"})
    for i, rt in enumerate(used):
        yy = ly + 5 + i * 5
        col, arrow, dash = REL_STYLE.get(rt, ("#000", "-|>", None))
        layers["legend"].append({"type": "line", "x1": lx, "y1": yy, "x2": lx + 8, "y2": yy,
                                 "stroke": col, "stroke_width": 0.5, "dash": dash,
                                 "marker_end": "arr-activate" if arrow == "-|>" else None})
        layers["legend"].append({"type": "text", "x": lx + 10, "y": yy, "text": rt, "anchor": "start", "font_pt": 6})

    scene = {"canvas": canvas, "title": ir.get("title", "mind map"),
             "desc": f"case {ir.get('case_id')} source-bound mind map",
             "layers": [{"id": f"layer-{k}", "label": k, "elements": v} for k, v in layers.items()]}
    svg = svgkit.write_svg(out_dir / "mindmap.svg", scene)
    written = [{"name": "mindmap.svg", "path": str(svg), "format": "svg", "role": "svg"}]

    # matplotlib mirror for PNG/PDF
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42, "svg.fonttype": "none"})
    fig = plt.figure(figsize=(W / 25.4, H / 25.4), dpi=200)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    for n in ir.get("nodes", []):
        if n.get("parent") and n["parent"] in pos:
            x1, y1 = xy(n["parent"]); x2, y2 = xy(n["id"])
            ax.plot([x1 + hw[n["parent"]], x2 - hw[n["id"]]], [y1, y2], color="#9bb3cc", lw=0.5)
    for nid, n in nodes.items():
        x, y = xy(nid); d = pos[nid]["x"]; w = hw[nid]
        fc = "#0C5DA5" if d == 0 else ("#e8f0fa" if d == 1 else "#ffffff")
        ax.add_patch(FancyBboxPatch((x - w, y - 5), 2 * w, 10, boxstyle="round,pad=0.3",
                                    facecolor=fc, edgecolor="#0C5DA5", lw=0.4))
        ax.text(x, y, n.get("label", nid), ha="center", va="center",
                fontsize=8 if d else 9, color="#fff" if d == 0 else "#000",
                fontweight="bold" if d == 0 else "normal")
    for r in ir.get("relations", []):
        if r["from"] in pos and r["to"] in pos:
            x1, y1 = xy(r["from"]); x2, y2 = xy(r["to"])
            col, arrow, dash = REL_STYLE.get(r["type"], ("#000", "-|>", None))
            ax.add_patch(FancyArrowPatch((x1, y1 + 5), (x2, y2 + 5), arrowstyle=arrow,
                                         mutation_scale=8, color=col, lw=0.6,
                                         linestyle=(0, (2, 1)) if dash else "-",
                                         connectionstyle="arc3,rad=0.2"))
    for ex in ir.get("exports", [{"format": "png"}, {"format": "pdf"}]):
        fmt = ex.get("format", "png")
        if fmt == "svg":
            continue
        p = out_dir / f"mindmap.{fmt}"
        try:
            fig.savefig(p, dpi=200, format=fmt, facecolor="white")
            written.append({"name": p.name, "path": str(p), "format": fmt, "role": fmt})
        except Exception:
            pass
    plt.close(fig)
    ir.setdefault("provenance", {})["node_map"] = {nid: {"source": n.get("source"), "label": n.get("label")} for nid, n in nodes.items()}
    return {"artifacts": written, "n_nodes": len(nodes), "n_relations": len(ir.get("relations", []))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    res = render(ir, Path(args.out))
    figkit.write_json(Path(args.out) / "mindmap_ir.json", ir)
    print(json.dumps({"status": "ok", **res}, ensure_ascii=False))


if __name__ == "__main__":
    main()