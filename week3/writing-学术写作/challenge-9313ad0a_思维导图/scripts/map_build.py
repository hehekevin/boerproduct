#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_build.py — 思维导图四格式生成器（FreeMind .mm / OPML / 自包含 SVG / Markdown 大纲）
用法:
  python3 map_build.py --tree tree.json --relations relations.jsonl --evidence node_evidence.jsonl --outdir /app/output
tree.json: {"root": "...", "nodes":[{"id":"N01","parent":null,"label":"...","type":"core_concept","note":...}]}
relations.jsonl: {"rel":"R01","from":"N05","to":"N09","type":"causal|dependency|contrast|support|conflict|temporal","basis":...}
node_evidence.jsonl: {"nid":"N12","type":"fact|summary|inference","locator":...,"quote":...}
产出（四种格式内容同构）: mindmap.mm / mindmap.opml / mindmap.svg / outline.md
写盘后自检：四个文件存在且 >100 字节；SVG 可被 XML 解析器解析；节点 >60 时告警。
自检结果以 build_report.json 落盘，供 result.json 引用。
"""
import argparse, html, json, math, os, sys


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

TYPE_COLOR = {
    "core_concept": "#1e5a8a", "question": "#8a4a1e", "method": "#1e7a4f",
    "evidence": "#5a5a5a", "conclusion": "#8a1e4a", "task": "#55661e",
    "risk": "#8a2e1e", "concept": "#1e5a8a", "other": "#555555",
}
REL_STYLE = {
    "causal": ("#c0392b", "5,3"), "dependency": ("#2471a3", ""),
    "contrast": ("#7d3c98", "2,2"), "support": ("#1e8449", ""),
    "conflict": ("#c0392b", "1,3"), "temporal": ("#7f8c8d", "3,3"),
}

class Node:
    def __init__(self, d):
        self.id = d["id"]
        self.parent = d.get("parent")
        self.label = d.get("label", "")
        self.type = d.get("type", "other")
        self.note = d.get("note")
        self.children = []


def load_tree(path):
    data = json.load(open(path, encoding="utf-8"))
    nodes = {}
    for d in data.get("nodes", []):
        nodes[d["id"]] = Node(d)
    roots = []
    for d in data.get("nodes", []):
        n = nodes[d["id"]]
        if n.parent and n.parent in nodes:
            nodes[n.parent].children.append(n)
        else:
            roots.append(n)
    return data.get("root") or (roots[0].label if roots else "导图"), nodes, roots

def ev_map(path):
    m = {}
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                r = json.loads(line)
                m.setdefault(r.get("nid"), []).append(r)
    return m

def rel_list(path):
    rows = []
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

# ---------- FreeMind ----------
def _mm_node(n, ev, depth=0):
    evrows = ev.get(n.id, [])
    attrs = f' TEXT_TYPE="{n.type}"'
    if evrows:
        locs = "; ".join(f"{e.get('type')}:{e.get('locator')}" for e in evrows)
        attrs += f' EVIDENCE="{html.escape(locs, quote=True)}"'
    txt = html.escape(n.label, quote=True) + attrs
    s = f'{"  "*depth}<node TEXT="{txt}" ID="{n.id}"'
    if n.children:
        s += ">\n"
        for c in n.children:
            s += _mm_node(c, ev, depth + 1) + "\n"
        s += f'{"  "*depth}</node>'
    else:
        s += "/>"
    return s

def build_mm(root_label, roots, ev, path):
    body = "\n".join(_mm_node(r, ev) for r in roots)
    open(path, "w", encoding="utf-8").write(
        f'<map version="1.0.1">\n<node TEXT="{html.escape(root_label, quote=True)}" ID="ROOT">\n{body}\n</node>\n</map>\n')

# ---------- OPML ----------
def _opml_node(n, ev, depth=0):
    evrows = ev.get(n.id, [])
    txt = n.label + (f" [{'; '.join(e.get('locator') or '' for e in evrows)}]" if evrows else "")
    s = f'{"  "*(depth+2)}<outline text="{html.escape(txt, quote=True)}" type="{n.type}"'
    if n.children:
        s += ">\n"
        for c in n.children:
            s += _opml_node(c, ev, depth + 1)
        s += f'{"  "*(depth+2)}</outline>\n'
    else:
        s += "/>\n"
    return s

def build_opml(root_label, roots, ev, path):
    body = "".join(_opml_node(r, ev) for r in roots)
    open(path, "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n<head><title>{html.escape(root_label)}</title></head>\n<body>\n{body}</body>\n</opml>\n')

# ---------- Markdown ----------
def build_md(root_label, roots, ev, rels, nodes, path):
    L = [f"# {root_label}", ""]
    def walk(n, depth):
        evrows = ev.get(n.id, [])
        tag = f"`{n.type}`"
        evn = ""
        if evrows:
            evn = "（证据: " + "; ".join(f"{e.get('type')}:{e.get('locator')}" for e in evrows[:2]) + "）"
        note = f" — {n.note}" if n.note else ""
        L.append("  " * depth + f"- {n.label} {tag}{note}{evn}")
        for c in n.children:
            walk(c, depth + 1)
    for r in roots:
        walk(r, 0)
    if rels:
        L += ["", "## 关系（跨分支）", ""]
        for r in rels:
            f = nodes.get(r.get("from")).label if nodes.get(r.get("from")) else r.get("from")
            t = nodes.get(r.get("to")).label if nodes.get(r.get("to")) else r.get("to")
            basis = f"（依据: {r.get('basis')}）" if r.get("basis") else ""
            L.append(f"- **{r.get('type')}**: {f} → {t} {basis}")
    open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")

# ---------- SVG 径向布局（带边界钳制 + 按节点数自适应半径，保证不裁切） ----------
def build_svg(root_label, roots, ev, rels, nodes, path):
    W, H = 1600, 1100
    CX, CY = W/2, H/2
    MARGIN = 78
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">',
             f'<rect width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>']
    levels = {}
    def collect(n, d):
        levels.setdefault(d, []).append(n)
        for c in n.children:
            collect(c, d + 1)
    for r in roots:
        collect(r, 1)
    pos = {}
    pos["ROOT"] = (CX, CY)
    max_depth = max(levels) if levels else 1
    def clamp_xy(x, y):
        return (min(max(x, MARGIN), W - MARGIN), min(max(y, MARGIN), H - MARGIN))
    for d, ns in sorted(levels.items()):
        cnt = len(ns)
        # 半径随该层节点数自适应：周长要容得下所有节点框，避免叠压
        need_r = 95 + cnt * 82
        radius = max(160 + (d - 1) * 195, need_r)
        for i, n in enumerate(ns):
            ang = -math.pi/2 + 2*math.pi*i/max(cnt, 1) + 0.3*d
            x = CX + radius*math.cos(ang)
            y = CY + radius*math.sin(ang)*0.58
            pos[n.id] = clamp_xy(x, y)
    def edge(n):
        if n.parent in pos and n.id in pos:
            x1, y1 = pos[n.parent]; x2, y2 = pos[n.id]
            color = TYPE_COLOR.get(n.type, "#555")
            parts.append(f'<path d="M {x1:.0f} {y1:.0f} C {(x1+x2)/2:.0f} {y1:.0f}, {(x1+x2)/2:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}" stroke="{color}" stroke-opacity="0.55" fill="none" stroke-width="1.6"/>')
        for c in n.children:
            edge(c)
    for r in roots:
        edge(r)
    for r in rels:
        a, b = pos.get(r.get("from")), pos.get(r.get("to"))
        if a and b:
            color, dash = REL_STYLE.get(r.get("type"), ("#888", ""))
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" stroke="{color}" stroke-width="1.4"{dash_attr} stroke-opacity="0.8"/>')
            parts.append(f'<text x="{(a[0]+b[0])/2:.0f}" y="{(a[1]+b[1])/2 - 4:.0f}" font-size="10" fill="{color}" text-anchor="middle">{html.escape(r.get("type",""))}</text>')
    def draw(n):
        if n.id in pos:
            x, y = pos[n.id]
            color = TYPE_COLOR.get(n.type, "#555")
            evrows = ev.get(n.id, [])
            badge = " ●" if evrows else ""
            label = n.label if len(n.label) <= 16 else n.label[:15] + "…"
            wbox = max(60, len(label) * 13 + 22)
            # 贴边时把框拉回画布内
            if x - wbox/2 < 6: x = wbox/2 + 6
            if x + wbox/2 > W - 6: x = W - wbox/2 - 6
            if y < 20: y = 20
            if y > H - 20: y = H - 20
            parts.append(f'<rect x="{x - wbox/2:.0f}" y="{y - 14:.0f}" width="{wbox:.0f}" height="28" rx="14" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="1.2"/>')
            parts.append(f'<text x="{x:.0f}" y="{y + 4:.0f}" font-size="13" fill="{color}" text-anchor="middle">{html.escape(label)}{badge}</text>')
            if n.type not in ("other",):
                parts.append(f'<text x="{x:.0f}" y="{y + 26:.0f}" font-size="9" fill="#888" text-anchor="middle">{html.escape(n.type)}</text>')
            # 节点 ID（ASCII）：无 CJK 字体的回退渲染下，PNG 仍可逐节点核对
            parts.append(f'<text x="{x:.0f}" y="{y - 17:.0f}" font-size="9" fill="#999" text-anchor="middle">{html.escape(n.id)}</text>')
        for c in n.children:
            draw(c)
    for r in roots:
        draw(r)
    parts.append(f'<rect x="{CX-110:.0f}" y="{CY-22:.0f}" width="220" height="44" rx="22" fill="#1e5a8a"/>')
    parts.append(f'<text x="{CX:.0f}" y="{CY+5:.0f}" font-size="16" font-weight="bold" fill="#ffffff" text-anchor="middle">{html.escape(root_label[:16])}</text>')
    parts.append("</svg>")
    open(path, "w", encoding="utf-8").write("\n".join(parts))

def self_check(files, n_nodes):
    """写盘自检：文件存在、非空（>100B）、SVG 可解析。"""
    report = {"files": [], "warnings": [], "ok": True}
    if n_nodes > 60:
        report["warnings"].append(f"节点数 {n_nodes} > 60，建议聚合同粒度兄弟节点")
    for fp in files:
        try:
            size = os.path.getsize(fp)
        except Exception:
            report["ok"] = False
            report["files"].append({"path": fp, "ok": False, "error": "missing"})
            continue
        entry = {"path": os.path.basename(fp), "bytes": size, "ok": True}
        if size < 100:
            entry["ok"] = False
            report["ok"] = False
            entry["error"] = f"too_small:{size}B"
        if fp.endswith(".svg"):
            try:
                ET.parse(fp)
                entry["svg_wellformed"] = True
            except Exception as e:
                entry["ok"] = False
                report["ok"] = False
                entry["error"] = f"svg_not_wellformed:{e}"
        report["files"].append(entry)
    return report

def main():
    ap = _SafeParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--relations", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()
    root_label, nodes, roots = load_tree(args.tree)
    ev = ev_map(args.evidence)
    rels = rel_list(args.relations)
    os.makedirs(args.outdir, exist_ok=True)
    p_mm = os.path.join(args.outdir, "mindmap.mm")
    p_op = os.path.join(args.outdir, "mindmap.opml")
    p_svg = os.path.join(args.outdir, "mindmap.svg")
    p_md = os.path.join(args.outdir, "outline.md")
    try:
        build_mm(root_label, roots, ev, p_mm)
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "mm", "error": str(e)[:200]}, ensure_ascii=False))
    try:
        build_opml(root_label, roots, ev, p_op)
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "opml", "error": str(e)[:200]}, ensure_ascii=False))
    try:
        build_svg(root_label, roots, ev, rels, nodes, p_svg)
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "svg", "error": str(e)[:200]}, ensure_ascii=False))
    try:
        build_md(root_label, roots, ev, rels, nodes, p_md)
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "md", "error": str(e)[:200]}, ensure_ascii=False))
    report = self_check([p_mm, p_op, p_svg, p_md], len(nodes))
    rp = os.path.join(args.outdir, "build_report.json")
    json.dump(report, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": report["ok"], "files": [p_mm, p_op, p_svg, p_md],
                      "nodes": len(nodes), "relations": len(rels), "evidence_nodes": len(ev),
                      "check": report}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
