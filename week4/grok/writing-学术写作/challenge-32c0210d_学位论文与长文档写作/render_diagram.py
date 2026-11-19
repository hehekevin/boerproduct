"""render_diagram — source-bound schematics, mechanisms, pathways, apparatus.

Renders relationship_schematic / mechanism_pathway / apparatus_route /
graphical_abstract from the Figure IR. The scientific content (entities, typed &
directed relations, compartments) is extracted by the agent from the actual
source material; this module turns it into a correct, editable figure:

  * semantic arrow grammar — activation (filled head) vs inhibition (flat bar) vs
    binding (plain) vs transport (open/dashed) are distinct; direction preserved,
  * compartment-aware layout: groups become separated bands/regions so membrane,
    cytoplasm, nucleus never overlap; within a band nodes flow by pathway rank,
  * a reserved legend strip so the legend never collides with the drawing,
  * a layered editable SVG (svgkit) AND consistent PNG/PDF exports (matplotlib),
    both driven by one computed layout so they cannot diverge,
  * element->source provenance for every node and edge.

Usage:
  python render_diagram.py --ir figure_ir.json --out /app/output
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Ellipse
from matplotlib import font_manager

import figkit
import svgkit

HERE = Path(__file__).resolve().parent

# arrow grammar: (svg marker_end, dash, matplotlib arrowstyle)
EDGE_GRAMMAR = {
    "activates":   ("arr-activate", None, "-|>"),
    "inhibits":    ("bar-inhibit", None, "-["),
    "binds":       (None, None, "-"),
    "modifies":    ("arr-activate", "2,1", "-|>"),
    "transports":  ("arr-open", "3,1", "-|>"),
    "contains":    (None, "1,1", "-"),
    "parallel":    (None, None, "-"),
    "upstream_of": ("arr-activate", None, "-|>"),
    "causes":      ("arr-activate", None, "-|>"),
    "sequence":    ("arr-activate", None, "-|>"),
    "feedback":    ("arr-activate", "2,1", "-|>"),
    "connects":    (None, None, "-"),
    "flows_to":    ("arr-activate", None, "-|>"),
    "part_of":     (None, "1,1", "-"),
    "compares":    (None, "2,2", "-"),
    "encodes":     ("arr-open", None, "-|>"),
}
EDGE_LABEL = {
    "activates": "activates", "inhibits": "inhibits", "binds": "binds",
    "modifies": "modifies", "transports": "transports", "contains": "contains",
    "sequence": "step order", "flows_to": "material flow", "feedback": "feedback",
    "upstream_of": "upstream of", "causes": "causes", "part_of": "part of",
    "parallel": "parallel", "connects": "connects", "compares": "compares", "encodes": "encodes",
}
COMPARTMENT_ORDER = {"membrane": 0, "extracellular": 0, "cytoplasm": 1, "cytosol": 1,
                     "nucleus": 2, "nuclear": 2, "organelle": 1}


def _res(name):
    return figkit.load_json(HERE / name)


def _fonts(style):
    available = {f.name for f in font_manager.fontManager.ttflist}
    req = style.get("font_family", "DejaVu Sans")
    if req in available:
        return req
    for c in ["Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei", "Microsoft YaHei", "SimHei", "DejaVu Sans"]:
        if c in available:
            return c
    return "DejaVu Sans"


def _tint(hexcolor: str, f: float = 0.85) -> str:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r = round(r + (255 - r) * f); g = round(g + (255 - g) * f); b = round(b + (255 - b) * f)
    return f"#{r:02x}{g:02x}{b:02x}"


def _ranks(entities, relations):
    ent_ids = {e["id"] for e in entities}
    indeg = defaultdict(int)
    adj = defaultdict(list)
    for r in relations:
        if r["type"] in figkit.DIRECTED_RELATIONS and r.get("direction", "forward") != "none":
            a, b = r["from"], r["to"]
            if a in ent_ids and b in ent_ids and a != b:
                adj[a].append(b)
                indeg[b] += 1
                indeg.setdefault(a, 0)
    rank = {e["id"]: 0 for e in entities}
    q = deque([eid for eid in ent_ids if indeg.get(eid, 0) == 0])
    seen = set(q)
    while q:
        u = q.popleft()
        for v in adj[u]:
            rank[v] = max(rank[v], rank[u] + 1)
            if v not in seen:
                seen.add(v); q.append(v)
    maxr = max(rank.values(), default=0)
    for eid in ent_ids:
        if eid not in seen:
            maxr += 1; rank[eid] = maxr
    return rank


def compute_layout(ir: dict) -> dict:
    canvas = ir.get("canvas", {})
    W = canvas.get("width_mm", 180)
    H = canvas.get("height_mm", 120)
    margin = 8
    legend_w = 40 if (ir.get("relations") or ir.get("entities")) else 0
    draw_w = W - legend_w - 2 * margin
    entities = ir.get("entities", [])
    relations = ir.get("relations", [])
    groups = ir.get("groups", [])
    ent_by_id = {e["id"]: e for e in entities}
    rank = _ranks(entities, relations)

    group_of = {}
    for g in groups:
        for m in g.get("members", []):
            group_of[m] = g["id"]
    for e in entities:
        if e.get("group"):
            group_of[e["id"]] = e["group"]

    compartments = [g for g in groups if g.get("kind") in ("compartment", "membrane")]
    positions = {}
    group_boxes = {}

    def node_size(e):
        w = max(16, min(30, 4 + 1.6 * len(str(e.get("label", "")))))
        return w, 10

    if compartments and entities:
        # vertical bands, one per compartment, ordered membrane->cyto->nucleus
        comps = sorted(compartments, key=lambda g: (COMPARTMENT_ORDER.get(g.get("label", "").lower().split()[0], 1), groups.index(g)))
        # include any ungrouped entities in a final band
        band_h = (H - 2 * margin) / len(comps)
        for bi, g in enumerate(comps):
            members = [e for e in entities if group_of.get(e["id"]) == g["id"]]
            if not members:
                continue
            members.sort(key=lambda e: (rank[e["id"]], e["id"]))
            n = len(members)
            y_center = margin + (bi + 0.55) * band_h
            for i, e in enumerate(members):
                w, h = node_size(e)
                x = margin + (i + 0.5) * draw_w / n
                positions[e["id"]] = {"x": x, "y": y_center, "w": w, "h": h}
            pad = 4
            xs = [positions[m["id"]] for m in members]
            x0 = min(p["x"] - p["w"] / 2 for p in xs) - pad
            x1 = max(p["x"] + p["w"] / 2 for p in xs) + pad
            y0 = margin + bi * band_h + 1
            y1 = margin + (bi + 1) * band_h - 1
            group_boxes[g["id"]] = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "label": g.get("label", g["id"])}
        # ungrouped entities: place in a spare row at bottom of drawing area
        un = [e for e in entities if e["id"] not in positions]
        for i, e in enumerate(un):
            w, h = node_size(e)
            positions[e["id"]] = {"x": margin + (i + 0.5) * draw_w / max(len(un), 1), "y": H - margin - h, "w": w, "h": h}
    elif relations and any(r["type"] in figkit.DIRECTED_RELATIONS for r in relations):
        by_rank = defaultdict(list)
        for e in entities:
            by_rank[rank[e["id"]]].append(e["id"])
        nr = max(by_rank.keys(), default=0) + 1
        for r_idx in sorted(by_rank):
            col = by_rank[r_idx]
            n = len(col)
            x = margin + (r_idx + 0.5) * draw_w / nr
            for i, eid in enumerate(col):
                e = ent_by_id[eid]
                w, h = node_size(e)
                y = margin + (i + 0.5) * (H - 2 * margin) / n
                positions[eid] = {"x": x, "y": y, "w": w, "h": h}
    else:
        gids = list(dict.fromkeys(group_of.get(e["id"], "_") for e in entities)) or ["_"]
        ng = len(gids)
        gw = draw_w / ng
        for gi, g in enumerate(gids):
            members = [e for e in entities if group_of.get(e["id"], "_") == g]
            cols = max(1, int(len(members) ** 0.5))
            rows_n = (len(members) + cols - 1) // cols
            for i, e in enumerate(members):
                w, h = node_size(e)
                cx = margin + gi * gw + (i % cols + 0.5) * gw / cols
                cy = margin + (i // cols + 0.5) * (H - 2 * margin) / max(rows_n, 1)
                positions[e["id"]] = {"x": cx, "y": cy, "w": w, "h": h}
            if g != "_":
                gg = next((x for x in groups if x["id"] == g), None)
                if gg:
                    group_boxes[g] = {"x": margin + gi * gw + 1, "y": margin, "w": gw - 2, "h": H - 2 * margin, "label": gg.get("label", g)}

    # edge routing: bow long / feedback / inhibition edges away from the straight
    # forward chain so they never overlap collinear activation edges.
    import math
    edge_routes = {}
    for r in relations:
        a, b = positions.get(r["from"]), positions.get(r["to"])
        if not a or not b:
            continue
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        dist = math.hypot(dx, dy) or 1.0
        long = dist > 45
        if r["type"] in ("feedback", "inhibits") and long:
            rad = 0.3
        elif long:
            rad = -0.2
        else:
            rad = 0.0
        # perpendicular unit vector for label placement
        px, py = -dy / dist, dx / dist
        off = rad * dist * 0.5
        mx, my = (a["x"] + b["x"]) / 2 + px * off, (a["y"] + b["y"]) / 2 + py * off
        edge_routes[r["id"]] = {"rad": rad, "label_x": mx, "label_y": my - 2}
    ir["layout"] = {"algorithm": "compartment_bands" if compartments else ("topological" if relations else "grouped_grid"),
                    "positions": positions, "group_boxes": group_boxes,
                    "legend_x": W - legend_w + 2, "edge_routes": edge_routes}
    return ir["layout"]


def _node_shape(category):
    if category in ("cell", "sample", "concept"):
        return "ellipse"
    return "rect"


def build_scene(ir, font, colors, borders):
    canvas = ir.get("canvas", {})
    style = ir.get("style", {})
    pos = ir["layout"]["positions"]
    gboxes = ir["layout"]["group_boxes"]
    legend_x = ir["layout"].get("legend_x", canvas.get("width_mm", 180) - 38)
    pal = _res("palettes.json")
    edge_colors = pal["semantic_edges"]
    base_pt = style.get("base_font_pt", 8)
    layers = {"groups": [], "edges": [], "nodes": [], "labels": [], "legend": []}

    for gid, b in gboxes.items():
        layers["groups"].append({"type": "rect", "id": f"group_{gid}", "x": b["x"], "y": b["y"],
                                 "w": b["w"], "h": b["h"], "fill": "#f6f9fc", "stroke": "#9bb3cc",
                                 "stroke_width": 0.4, "rx": 2, "dash": "3,1.5"})
        layers["labels"].append({"type": "text", "x": b["x"] + 2, "y": b["y"] + 3, "text": b["label"],
                                 "anchor": "start", "font_pt": base_pt, "font_weight": "bold",
                                 "fill": "#33526e", "font_family": font})

    used_edge_types = []
    routes = ir["layout"].get("edge_routes", {})
    for r in ir.get("relations", []):
        a, b = pos.get(r["from"]), pos.get(r["to"])
        if not a or not b:
            continue
        rtype = r["type"]
        if rtype not in used_edge_types:
            used_edge_types.append(rtype)
        marker, dash, _ = EDGE_GRAMMAR.get(rtype, (None, None, "-"))
        col = edge_colors.get(rtype, "#000000")
        rt = routes.get(r["id"], {"rad": 0})
        rad = rt.get("rad", 0)
        if rad:
            # quadratic curve bowed perpendicular to the straight line
            dx, dy = b["x"] - a["x"], b["y"] - a["y"]
            dist = (dx * dx + dy * dy) ** 0.5 or 1
            px, py = -dy / dist, dx / dist
            cx = (a["x"] + b["x"]) / 2 + px * rad * dist
            cy = (a["y"] + b["y"]) / 2 + py * rad * dist
            layers["edges"].append({"type": "path", "id": f"edge_{r['id']}",
                                    "d": f"M {a['x']},{a['y']} Q {cx},{cy} {b['x']},{b['y']}",
                                    "stroke": col, "stroke_width": 0.6, "dash": dash,
                                    "marker_end": marker, "source": r.get("source"),
                                    "source_locator": r.get("source_locator"), "category": rtype})
        else:
            layers["edges"].append({"type": "line", "id": f"edge_{r['id']}", "x1": a["x"], "y1": a["y"],
                                    "x2": b["x"], "y2": b["y"], "stroke": col, "stroke_width": 0.6,
                                    "dash": dash, "marker_end": marker, "source": r.get("source"),
                                    "source_locator": r.get("source_locator"), "category": rtype})
        if r.get("label"):
            layers["labels"].append({"type": "text", "x": rt.get("label_x", (a["x"] + b["x"]) / 2),
                                     "y": rt.get("label_y", (a["y"] + b["y"]) / 2 - 2),
                                     "text": r["label"], "font_pt": base_pt - 1.5, "fill": col, "font_family": font})

    used_categories = []
    for e in ir.get("entities", []):
        p = pos.get(e["id"])
        if not p:
            continue
        cat = e.get("category", "concept")
        if cat not in used_categories:
            used_categories.append(cat)
        fill = _tint(colors.get(cat, "#0072B2"))
        border = borders.get(cat, "#222222")
        if _node_shape(cat) == "ellipse":
            layers["nodes"].append({"type": "ellipse", "id": f"node_{e['id']}", "cx": p["x"], "cy": p["y"],
                                    "rx": p["w"] / 2, "ry": p["h"] / 2, "fill": fill, "stroke": border,
                                    "stroke_width": 0.5, "source": e.get("source"),
                                    "source_locator": e.get("source_locator"), "category": cat})
        else:
            layers["nodes"].append({"type": "rect", "id": f"node_{e['id']}", "x": p["x"] - p["w"] / 2,
                                    "y": p["y"] - p["h"] / 2, "w": p["w"], "h": p["h"], "fill": fill,
                                    "stroke": border, "stroke_width": 0.5, "rx": 1.5,
                                    "source": e.get("source"), "source_locator": e.get("source_locator"), "category": cat})
        layers["labels"].append({"type": "text", "id": f"label_{e['id']}", "x": p["x"], "y": p["y"],
                                 "text": e["label"], "font_pt": base_pt, "fill": "#000000",
                                 "font_style": "italic" if cat == "gene" else None,
                                 "font_family": font, "source": e.get("source"), "category": cat})

    # legend in reserved right strip
    lx, ly = legend_x, 8
    if used_edge_types:
        layers["legend"].append({"type": "text", "x": lx, "y": ly, "text": "Relations", "anchor": "start",
                                 "font_pt": base_pt - 1, "font_weight": "bold", "font_family": font})
        for i, rt in enumerate(used_edge_types):
            yy = ly + 5 + i * 5
            marker, dash, _ = EDGE_GRAMMAR.get(rt, (None, None, "-"))
            col = edge_colors.get(rt, "#000000")
            layers["legend"].append({"type": "line", "x1": lx, "y1": yy, "x2": lx + 8, "y2": yy,
                                     "stroke": col, "stroke_width": 0.6, "dash": dash, "marker_end": marker})
            layers["legend"].append({"type": "text", "x": lx + 10, "y": yy, "text": EDGE_LABEL.get(rt, rt),
                                     "anchor": "start", "font_pt": base_pt - 1.5, "font_family": font})
    cy = ly + 5 + len(used_edge_types) * 5 + 4
    if used_categories:
        layers["legend"].append({"type": "text", "x": lx, "y": cy, "text": "Entities", "anchor": "start",
                                 "font_pt": base_pt - 1, "font_weight": "bold", "font_family": font})
        for i, cat in enumerate(used_categories):
            yy = cy + 5 + i * 5
            layers["legend"].append({"type": "rect", "x": lx, "y": yy - 1.5, "w": 5, "h": 3,
                                     "fill": _tint(colors.get(cat, "#0072B2")), "stroke": borders.get(cat, "#222"), "stroke_width": 0.3})
            layers["legend"].append({"type": "text", "x": lx + 7, "y": yy, "text": cat, "anchor": "start",
                                     "font_pt": base_pt - 1.5, "font_family": font})

    scene = {"canvas": canvas, "title": ir.get("title", ""),
             "desc": f"case {ir.get('case_id')} | kind {ir.get('kind')} | source-bound editable figure",
             "layers": [{"id": f"layer-{k}", "label": k, "elements": v} for k, v in layers.items()]}
    return scene, used_edge_types, used_categories


def _mpl_mirror(ir, out_dir, font, colors, borders, written):
    canvas = ir.get("canvas", {})
    style = ir.get("style", {})
    W, H = canvas.get("width_mm", 180), canvas.get("height_mm", 120)
    pos = ir["layout"]["positions"]
    gboxes = ir["layout"]["group_boxes"]
    legend_x = ir["layout"].get("legend_x", W - 38)
    pal = _res("palettes.json")
    edge_colors = pal["semantic_edges"]
    base_pt = style.get("base_font_pt", 8)
    plt.rcParams.update({"font.family": font, "font.size": base_pt, "svg.fonttype": "none",
                         "pdf.fonttype": 42, "ps.fonttype": 42, "axes.unicode_minus": False})
    fig = plt.figure(figsize=(W / 25.4, H / 25.4), dpi=style.get("dpi", 300))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H, facecolor=canvas.get("background", "#ffffff"), edgecolor="none"))
    for gid, b in gboxes.items():
        ax.add_patch(FancyBboxPatch((b["x"], b["y"]), b["w"], b["h"], boxstyle="round,pad=0.4",
                                    facecolor="#f6f9fc", edgecolor="#9bb3cc", linewidth=0.4, linestyle=(0, (3, 1.5))))
        ax.text(b["x"] + 2, b["y"] + 3, b["label"], fontsize=base_pt, fontweight="bold", color="#33526e", va="center", ha="left")
    used_edges = []
    routes = ir["layout"].get("edge_routes", {})
    for r in ir.get("relations", []):
        a, b = pos.get(r["from"]), pos.get(r["to"])
        if not a or not b:
            continue
        if r["type"] not in used_edges:
            used_edges.append(r["type"])
        _, dash, arrowstyle = EDGE_GRAMMAR.get(r["type"], (None, None, "-"))
        col = edge_colors.get(r["type"], "#000000")
        ls = (0, (2, 1)) if dash else "-"
        rt = routes.get(r["id"], {"rad": 0})
        rad = rt.get("rad", 0)
        conn = f"arc3,rad={rad}" if rad else "arc3,rad=0"
        ax.add_patch(FancyArrowPatch((a["x"], a["y"]), (b["x"], b["y"]), arrowstyle=arrowstyle,
                                     mutation_scale=11, color=col, linewidth=0.8, linestyle=ls,
                                     shrinkA=14, shrinkB=14, connectionstyle=conn))
        if r.get("label"):
            ax.text(rt.get("label_x", (a["x"] + b["x"]) / 2), rt.get("label_y", (a["y"] + b["y"]) / 2 - 2),
                    r["label"], fontsize=base_pt - 1.5, color=col, ha="center")
    used_cats = []
    for e in ir.get("entities", []):
        p = pos.get(e["id"])
        if not p:
            continue
        cat = e.get("category", "concept")
        if cat not in used_cats:
            used_cats.append(cat)
        fill = _tint(colors.get(cat, "#0072B2"))
        border = borders.get(cat, "#222222")
        if _node_shape(cat) == "ellipse":
            ax.add_patch(Ellipse((p["x"], p["y"]), p["w"], p["h"], facecolor=fill, edgecolor=border, linewidth=0.5))
        else:
            ax.add_patch(FancyBboxPatch((p["x"] - p["w"] / 2, p["y"] - p["h"] / 2), p["w"], p["h"],
                                        boxstyle="round,pad=0.3", facecolor=fill, edgecolor=border, linewidth=0.5))
        ax.text(p["x"], p["y"], e["label"], ha="center", va="center", fontsize=base_pt,
                fontstyle="italic" if cat == "gene" else "normal")
    # legend
    lx, ly = legend_x, 8
    if used_edges:
        ax.text(lx, ly, "Relations", fontsize=base_pt - 1, fontweight="bold", ha="left", va="center")
        for i, rt in enumerate(used_edges):
            yy = ly + 5 + i * 5
            _, dash, arrowstyle = EDGE_GRAMMAR.get(rt, (None, None, "-"))
            col = edge_colors.get(rt, "#000000")
            ls = (0, (2, 1)) if dash else "-"
            ax.add_patch(FancyArrowPatch((lx, yy), (lx + 8, yy), arrowstyle=arrowstyle, mutation_scale=9,
                                         color=col, linewidth=0.8, linestyle=ls))
            ax.text(lx + 10, yy, EDGE_LABEL.get(rt, rt), fontsize=base_pt - 1.5, ha="left", va="center")
    cy = ly + 5 + len(used_edges) * 5 + 4
    if used_cats:
        ax.text(lx, cy, "Entities", fontsize=base_pt - 1, fontweight="bold", ha="left", va="center")
        for i, cat in enumerate(used_cats):
            yy = cy + 5 + i * 5
            ax.add_patch(Rectangle((lx, yy - 1.5), 5, 3, facecolor=_tint(colors.get(cat, "#0072B2")), edgecolor=borders.get(cat, "#222"), linewidth=0.3))
            ax.text(lx + 7, yy, cat, fontsize=base_pt - 1.5, ha="left", va="center")

    stem = out_dir / "figure"
    for ex in ir.get("exports", [{"format": "png"}, {"format": "pdf"}]):
        fmt = ex.get("format", "png")
        if fmt == "svg":
            continue
        path = stem.with_suffix("." + fmt)
        try:
            fig.savefig(path, dpi=ex.get("dpi", style.get("dpi", 300)), format=fmt, facecolor=fig.get_facecolor())
            written.append({"name": path.name, "path": str(path), "format": fmt, "role": fmt,
                            "dpi": ex.get("dpi", style.get("dpi", 300))})
        except Exception as e:  # noqa: BLE001
            ir.setdefault("uncertainty", []).append({"item": f"export {fmt}", "reason": str(e),
                                                     "impact": "format unavailable", "handling": "skipped"})
    plt.close(fig)


def render(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    style = ir.get("style", {})
    font = _fonts(style)
    compute_layout(ir)
    pal = _res("palettes.json")
    cats = list(dict.fromkeys(e.get("category", "concept") for e in ir.get("entities", [])))
    qual = pal.get(style.get("palette", "okabe_ito"), pal["okabe_ito"])
    colors = {c: qual[i % len(qual)] for i, c in enumerate(cats)}
    borders = {c: qual[i % len(qual)] for i, c in enumerate(cats)}
    scene, used_edges, used_cats = build_scene(ir, font, colors, borders)
    svg_path = svgkit.write_svg(out_dir / "figure.svg", scene)
    written = [{"name": "figure.svg", "path": str(svg_path), "format": "svg", "role": "svg"}]
    _mpl_mirror(ir, out_dir, font, colors, borders, written)

    emap = ir.setdefault("provenance", {}).setdefault("element_map", {})
    for e in ir.get("entities", []):
        emap[f"node_{e['id']}"] = {"source": e.get("source"), "source_locator": e.get("source_locator"),
                                   "glyph": "node", "label": e["label"], "category": e.get("category")}
    for r in ir.get("relations", []):
        emap[f"edge_{r['id']}"] = {"source": r.get("source"), "source_locator": r.get("source_locator"),
                                   "glyph": "edge", "type": r["type"], "from": r["from"], "to": r["to"]}
    ir["legend"] = {"edge_types": used_edges, "items": [{"label": c, "color": colors[c]} for c in used_cats],
                    "auto_from_data": False}
    ir["provenance"]["font_used"] = font
    return {"artifacts": written, "font_used": font, "layout": ir["layout"]["algorithm"],
            "n_entities": len(ir.get("entities", [])), "n_relations": len(ir.get("relations", []))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ir = figkit.load_json(args.ir)
    v = figkit.validate_ir(ir)
    if not v["ok"]:
        print(json.dumps({"status": "invalid_ir", "errors": v["errors"]}, ensure_ascii=False))
        sys.exit(2)
    res = render(ir, Path(args.out))
    figkit.write_json(Path(args.out) / "figure_ir.json", ir)
    print(json.dumps({"status": "ok", **{k: res[k] for k in ("font_used", "layout", "n_entities", "n_relations")},
                      "artifacts": [a["path"] for a in res["artifacts"]], "warnings": v["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()