#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pathway_svg.py — 生物机制图/通路图分层 SVG 渲染器（零第三方依赖）。
MARKER: bio-pathway-figure/v1

用法:
  python3 pathway_svg.py spec.json --out /app/output/figure.svg [--ablate edge_semantics,compartment,legend]

spec.json（由 Agent 依机制材料抽取生成，实体/关系逐条带 verbatim evidence 引文）:
{
  "title": "...", "source": "材料路径",
  "compartments": ["extracellular","membrane","cytoplasm","nucleus"],
  "nodes": [{"id","label","type","compartment","source","evidence"}],
  "edges": [{"id","src","dst","type","evidence"}]
}

行为:
  1. 区室分层布局（细胞外/膜/胞质/核），compartment=membrane 的节点骑在膜带中线（跨膜约束）。
  2. 相互作用语义→可区分箭头: activation=实线箭头, inhibition=T形短棒, phosphorylation=圆点端,
     ubiquitination=方点端, binding=菱形端, translocation=空心箭头+虚线, recruitment=虚线箭头。
  3. 分层命名: <g id="compartment-*"/"node-*"/"edge-*"/"legend">，图元带 data-source/data-evidence，
     可在矢量编辑器逐层改标签后重新导出（可编辑源文件）。
  4. --ablate 仅用于增益对照臂: edge_semantics=全部退化为普通箭头; compartment=取消区室分层;
     legend=取消图例。正常执行绝不带 --ablate。
所有失败路径 exit 0，结论写 stdout JSON，不用退出码表达成败。
"""
import argparse, hashlib, json, os, sys
from xml.sax.saxutils import escape

MARKER = "bio-pathway-figure/v1"

NODE_COLORS = {
    "ligand": "#937860", "receptor": "#C44E52", "protein": "#4C72B0",
    "gene": "#55A868", "complex": "#DD8452", "enzyme": "#8172B3",
    "cell": "#BA7E4E", "metabolite": "#8C6D31", "other": "#8C8C8C",
}
EDGE_STYLE = {
    "activation":      {"marker": "marker-arrow",   "dash": None},
    "inhibition":      {"marker": "marker-tbar",    "dash": None},
    "phosphorylation": {"marker": "marker-circle",  "dash": None},
    "ubiquitination":  {"marker": "marker-square",  "dash": None},
    "binding":         {"marker": "marker-diamond", "dash": None},
    "translocation":   {"marker": "marker-open",    "dash": "6,4"},
    "recruitment":     {"marker": "marker-arrow",   "dash": "6,4"},
}
EDGE_DESC = {
    "activation": "激活/促进", "inhibition": "抑制", "phosphorylation": "磷酸化",
    "ubiquitination": "泛素化", "binding": "结合", "translocation": "转运/易位",
    "recruitment": "募集",
}
DEFAULT_COMPARTMENTS = ["extracellular", "membrane", "cytoplasm", "nucleus"]
BAND_H = {"extracellular": 190, "membrane": 110, "cytoplasm": 300, "nucleus": 300}
CANVAS_W, TOP = 1240, 110
FONT = "Helvetica, Arial, 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
EDGE_COLOR = {"inhibition": "#B23A48", "activation": "#2E6E8E"}


def esc(s):
    return escape(str(s))


def label_w(label):
    return sum(9 if ord(c) < 128 else 16 for c in str(label))


def node_box(label):
    return max(96, label_w(label) + 30), 46


def band_layout(comps):
    ys, y = {}, TOP
    for c in comps:
        ys[c] = (y, BAND_H.get(c, 200))
        y += BAND_H.get(c, 200)
    return ys, y


def place_nodes(spec, comps, band_ys, ablate_compartment):
    """返回 {node_id: (cx, cy, w, h)}"""
    pos = {}
    nodes = spec.get("nodes", [])
    if ablate_compartment:
        for i, n in enumerate(nodes):
            w, h = node_box(n.get("label", n["id"]))
            pos[n["id"]] = (200 + (i % 4) * 300, 160 + (i // 4) * 130, w, h)
        return pos
    by_comp = {}
    for n in nodes:
        by_comp.setdefault(n.get("compartment", "cytoplasm"), []).append(n)
    for c in comps:
        for i, n in enumerate(by_comp.get(c, [])):
            w, h = node_box(n.get("label", n["id"]))
            cx = CANVAS_W * (i + 1) / (len(by_comp[c]) + 1)
            cy = band_ys[c][0] + band_ys[c][1] / 2.0  # membrane 节点骑膜带中线
            pos[n["id"]] = (cx, cy, w, h)
    return pos


def rect_ray(hw, hh, ux, uy):
    tx = hw / abs(ux) if abs(ux) > 1e-9 else float("inf")
    ty = hh / abs(uy) if abs(uy) > 1e-9 else float("inf")
    return min(tx, ty)


def edge_svg(e, pos, ablate_semantics):
    nid = e.get("id", "edge")
    t = e.get("type", "activation")
    st = EDGE_STYLE.get(t, {"marker": "marker-arrow", "dash": None})
    if ablate_semantics:
        st = {"marker": "marker-arrow", "dash": None}  # 消融臂：全部退化普通箭头
    src, dst = e.get("src"), e.get("dst")
    if src not in pos or dst not in pos:
        return ""
    color = EDGE_COLOR.get(t, EDGE_COLOR.get("default", "#444444"))
    dash = ' stroke-dasharray="%s"' % st["dash"] if st["dash"] else ""
    ev = esc(e.get("evidence", ""))
    common = ('data-type="%s" data-src="%s" data-dst="%s" data-evidence="%s"'
              % (esc(t), esc(src), esc(dst), ev))
    title = "<title>%s: %s -[%s]-&gt; %s | %s</title>" % (
        esc(nid), esc(src), esc(t), esc(dst), ev)
    if src == dst:  # 自反馈环
        cx, cy, w, h = pos[src]
        d = "M %.1f,%.1f A %.1f %.1f 0 1 1 %.1f,%.1f" % (
            cx - w / 2 - 6, cy, w / 2 + 34, 46, cx + w / 2 + 6, cy)
        body = ('<path d="%s" fill="none" stroke="#444" stroke-width="2.4"%s '
                'marker-end="url(#%s)"/>' % (d, dash, st["marker"]))
        return '<g id="edge-%s" %s>%s%s</g>' % (esc(nid), common, title, body)
    p1 = pos[src][:2]
    p2 = pos[dst][:2]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ln = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / ln, dy / ln
    t1 = rect_ray(pos[src][2] / 2, pos[src][3] / 2, ux, uy)
    t2 = rect_ray(pos[dst][2] / 2, pos[dst][3] / 2, ux, uy)
    x1, y1 = p1[0] + ux * (t1 + 4), p1[1] + uy * (t1 + 4)
    x2, y2 = p2[0] - ux * (t2 + 12), p2[1] - uy * (t2 + 12)
    body = ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#444" '
            'stroke-width="2.4"%s marker-end="url(#%s)"/>' % (
                x1, y1, x2, y2, dash, st["marker"]))
    return ('<g id="edge-%s" %s data-from="%.1f,%.1f" data-to="%.1f,%.1f">%s%s</g>'
            % (esc(nid), common, x1, y1, x2, y2, title, body))


def markers_svg():
    m = {
        "marker-arrow": '<path d="M0,0 L10,5 L0,10 z" fill="#444"/>',
        "marker-tbar": '<line x1="9" y1="0" x2="9" y2="10" stroke="#B23A48" stroke-width="3"/>',
        "marker-circle": '<circle cx="5" cy="5" r="3.2" fill="#FFF" stroke="#444" stroke-width="1.6"/>',
        "marker-square": '<rect x="2" y="2" width="6" height="6" fill="#FFF" stroke="#444" stroke-width="1.6"/>',
        "marker-diamond": '<path d="M5,0 L10,5 L5,10 L0,5 z" fill="#FFF" stroke="#444" stroke-width="1.4"/>',
        "marker-open": '<path d="M0,0 L10,5 L0,10" fill="none" stroke="#444" stroke-width="2"/>',
    }
    out = ["<defs>"]
    for mid, body in m.items():
        out.append('<marker id="%s" viewBox="0 0 10 10" refX="9" refY="5" '
                   'markerWidth="9" markerHeight="9" orient="auto">%s</marker>'
                   % (mid, body))
    out.append("</defs>")
    return "".join(out)


def legend_svg(spec, edges, nodes, ablate_legend):
    if ablate_legend:
        return "", 0
    types = sorted({e.get("type", "activation") for e in edges})
    cats = sorted({n.get("type", "other") for n in nodes})
    items = []
    y = 0
    for t in types:
        items.append('<g id="legend-edge-%s" data-kind="edge" data-key="%s">'
                     '<line x1="0" y1="%d" x2="56" y2="%d" stroke="#444" stroke-width="2.4"%s '
                     'marker-end="url(#%s)"/><text x="66" y="%d" font-family="%s" '
                     'font-size="14">%s — %s</text></g>'
                     % (t, t, y + 8, y + 8,
                        ' stroke-dasharray="%s"' % EDGE_STYLE[t]["dash"] if EDGE_STYLE[t]["dash"] else "",
                        EDGE_STYLE[t]["marker"], y + 13, FONT, t, EDGE_DESC.get(t, "")))
        y += 26
    for c in cats:
        col = NODE_COLORS.get(c, NODE_COLORS["other"])
        items.append('<g id="legend-node-%s" data-kind="node" data-key="%s">'
                     '<rect x="0" y="%d" width="26" height="15" fill="%s" fill-opacity="0.25" '
                     'stroke="%s" stroke-width="1.6"/><text x="66" y="%d" font-family="%s" '
                     'font-size="14">%s</text></g>'
                     % (c, c, y, col, col, y + 13, FONT, c))
        y += 26
    if not items:
        return "", 0
    h = y + 34
    box = ('<g id="legend" data-note="图例与图面箭头样式/节点配色一一对应">'
           '<rect x="0" y="0" width="320" height="%d" fill="#FFFFFF" stroke="#999" '
           'stroke-width="1"/><text x="10" y="20" font-family="%s" font-size="15" '
           'font-weight="bold">Legend</text><g transform="translate(14,32)">%s</g></g>'
           % (h, FONT, "".join(items)))
    return box, h


def build_svg(spec, ablate):
    comps = spec.get("compartments") or DEFAULT_COMPARTMENTS
    ablate_sem = "edge_semantics" in ablate
    ablate_comp = "compartment" in ablate
    ablate_leg = "legend" in ablate
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    band_ys, bottom = band_layout([] if ablate_comp else comps)
    pos = place_nodes(spec, [] if ablate_comp else comps, band_ys, ablate_comp)
    legend, leg_h = legend_svg(spec, edges, nodes, ablate_leg)
    W, H = CANVAS_W, max(bottom, 240) + (leg_h + 50 if legend else 40)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="0 0 %d %d" font-family="%s">' % (W, H, W, H, FONT)]
    out.append("<title>%s</title>" % esc(spec.get("title", "mechanism diagram")))
    prov = {"generated_by": "pathway_svg.py " + MARKER,
            "spec_sha256": hashlib.sha256(
                json.dumps(spec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
            "ablate": sorted(ablate), "nodes": len(nodes), "edges": len(edges),
            "source": spec.get("source", "")}
    out.append("<metadata>%s</metadata>" % esc(json.dumps(prov, ensure_ascii=False)))
    out.append(markers_svg())
    out.append('<rect x="0" y="0" width="%d" height="%d" fill="#FFFFFF"/>' % (W, H))
    out.append('<text x="24" y="42" font-size="21" font-weight="bold">%s</text>'
               % esc(spec.get("title", "")))
    out.append('<text x="24" y="68" font-size="13" fill="#666">source: %s</text>'
               % esc(spec.get("source", "")))
    if not ablate_comp:
        for c in comps:
            y0, h = band_ys[c]
            out.append('<g id="compartment-%s" data-compartment="%s" data-y="%d" data-h="%d">'
                       '<rect x="16" y="%d" width="%d" height="%d" fill="#F2F6FA" stroke="#B9C7D6" '
                       'stroke-width="1"/><text x="26" y="%d" font-size="15" fill="#33526B" '
                       'font-weight="bold">%s</text></g>'
                       % (c, c, y0, h, y0, W - 32, h, y0 + 22, esc(c)))
    out.append('<g id="edges">' + "".join(edge_svg(e, pos, ablate_sem) for e in edges) + "</g>")
    body = []
    for n in nodes:
        nid = n["id"]
        cx, cy, w, h = pos[nid]
        t = n.get("type", "other")
        col = NODE_COLORS.get(t, NODE_COLORS["other"])
        italic = ' font-style="italic"' if t == "gene" else ""
        body.append('<g id="node-%s" data-type="%s" data-compartment="%s" data-cx="%.1f" '
                    'data-cy="%.1f" data-source="%s" data-evidence="%s">'
                    '<title>%s | 来源: %s</title>'
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="8" fill="%s" '
                    'fill-opacity="0.22" stroke="%s" stroke-width="2"/>'
                    '<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="middle" '
                    'font-size="17"%s>%s</text></g>'
                    % (esc(nid), esc(t), esc(n.get("compartment", "cytoplasm")), cx, cy,
                       esc(n.get("source", "")), esc(n.get("evidence", "")),
                       esc(n.get("label", nid)), esc(n.get("source", "")),
                       cx - w / 2, cy - h / 2, w, h, col, col, cx, cy, italic,
                       esc(n.get("label", nid))))
    out.append('<g id="nodes">' + "".join(body) + "</g>")
    if legend:
        out.append('<g transform="translate(%d,%d)">%s</g>' % (W - 348, H - leg_h - 16, legend))
    out.append("</svg>")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", default="/app/output/figure.svg")
    ap.add_argument("--ablate", default="")
    args = ap.parse_args()
    out = {"tool": "pathway_svg", "ok": False}
    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        ablate = {t for t in args.ablate.split(",") if t in {"edge_semantics", "compartment", "legend"}}
        svg = build_svg(spec, ablate)
        d = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(svg)
        out.update(ok=True, svg=os.path.abspath(args.out),
                   nodes=len(spec.get("nodes", [])), edges=len(spec.get("edges", [])),
                   legend_items=(len({e.get("type") for e in spec.get("edges", [])})
                                 + len({n.get("type") for n in spec.get("nodes", [])}))
                   if "legend" not in ablate else 0,
                   ablate=sorted(ablate))
    except Exception as ex:
        out["error"] = repr(ex)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)   # 含 argparse 出错：失败路径一律 exit 0
    except Exception as ex:
        print(json.dumps({"tool": "pathway_svg", "ok": False, "error": repr(ex)},
                         ensure_ascii=False))
        sys.exit(0)
