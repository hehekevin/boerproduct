#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_pathway.py — 生物机制图机械校验器（同一校验器服务全量臂/消融臂，机器判定）。
MARKER: bio-pathway-figure/v1

用法:
  python3 validate_pathway.py spec.json figure.svg --corpus <材料目录或文件> [--report report.json]

校验项（match=false 计入 fail_count，全部逐条明细输出）:
  1. entity_checks      节点存在/标签一致/区室属性/命名含 ASCII 字母（用 [A-Za-z] 正则，
                        禁用 isalpha——汉字 "激".isalpha() 为 True 会漏检）/evidence 引文逐字回证
  2. edge_semantics     边的 data-type 与 spec 一致；marker 端点样式与语义映射一致
                        （activation=箭头, inhibition=T棒, phosphorylation=圆点, binding=菱形…）；
                        虚线约定（translocation/recruitment）一致；引文逐字回证
  3. direction_checks   data-to 相对 data-from 的向量与 src→dst 中心向量点积 > 0（方向机器判定）
  4. compartment_checks 区室带存在且顺序与 spec 一致（细胞外→膜→胞质→核自上而下）；
                        每个节点中心落在其区室带内（膜上节点骑膜带中线）
  5. legend_checks      图例存在；图例项键集合 == 图面实际使用的边类型/节点类别集合；色块配色一致
  6. export_checks      同名 PNG 存在时调用 render_svg.py --check 做像素检查；不存在则跳过不计 fail

退出码恒 0，verdict 全部写 stdout JSON（--report 另存文件），不用退出码表达成败。
"""
import argparse, json, os, re, subprocess, sys
import xml.etree.ElementTree as ET

MARKER = "bio-pathway-figure/v1"
EDGE_STYLE = {
    "activation":      {"marker": "marker-arrow",   "dash": None},
    "inhibition":      {"marker": "marker-tbar",    "dash": None},
    "phosphorylation": {"marker": "marker-circle",  "dash": None},
    "ubiquitination":  {"marker": "marker-square",  "dash": None},
    "binding":         {"marker": "marker-diamond", "dash": None},
    "translocation":   {"marker": "marker-open",    "dash": "6,4"},
    "recruitment":     {"marker": "marker-arrow",   "dash": "6,4"},
}
NODE_COLORS = {
    "ligand": "#937860", "receptor": "#C44E52", "protein": "#4C72B0",
    "gene": "#55A868", "complex": "#DD8452", "enzyme": "#8172B3",
    "cell": "#BA7E4E", "metabolite": "#8C6D31", "other": "#8C8C8C",
}


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def read_corpus(path):
    chunks = []
    if path and os.path.isdir(path):
        for root, _, fs in os.walk(path):
            for f in sorted(fs):
                if f.lower().endswith((".txt", ".md", ".json", ".csv")):
                    try:
                        chunks.append(open(os.path.join(root, f), encoding="utf-8",
                                           errors="ignore").read())
                    except Exception:
                        pass
    elif path and os.path.exists(path):
        try:
            chunks.append(open(path, encoding="utf-8", errors="ignore").read())
        except Exception:
            pass
    return norm("".join(chunks))


def t(e):
    return e.tag.split("}")[-1]


def parse_svg(svg_path):
    tree = ET.parse(svg_path)
    nodes, edges, comps, legend, legend_items = {}, {}, [], None, []
    for e in tree.getroot().iter():
        if t(e) != "g":
            continue
        i = e.get("id") or ""
        if i.startswith("node-"):
            nodes[i[5:]] = e
        elif i.startswith("edge-"):
            edges[i[5:]] = e
        elif i == "legend":
            legend = e
        elif e.get("data-compartment"):
            comps.append(e)
    if legend is not None:
        for e in legend.iter():
            if t(e) == "g" and e.get("data-kind"):
                legend_items.append(e)
    return nodes, edges, comps, legend, legend_items


def node_info(e):
    label = "".join(x.text or "" for x in e.iter() if t(x) == "text")
    try:
        cx, cy = float(e.get("data-cx")), float(e.get("data-cy"))
    except (TypeError, ValueError):
        cx = cy = None
    return label.strip(), cx, cy


def edge_info(e):
    def pt(key):
        try:
            a, b = str(e.get(key) or "").split(",")
            return float(a), float(b)
        except Exception:
            return None, None
    line = next((x for x in e.iter() if t(x) in ("line", "path")), None)
    return (pt("data-from"), pt("data-to"),
            (line.get("marker-end") or "") if line is not None else "",
            (line.get("stroke-dasharray") or "") if line is not None else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("svg")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--tol", type=float, default=30.0, help="区室带包含判定容差 px")
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    out = {"tool": "validate_pathway", "svg": os.path.abspath(args.svg), "ok": False}
    checks = {k: [] for k in ("structure", "entity_checks", "edge_semantics",
                              "direction_checks", "compartment_checks",
                              "legend_checks", "export_checks")}
    fail = [0]

    def add(group, item):
        checks[group].append(item)
        if item.get("match") is False:
            fail[0] += 1

    try:
        with open(args.spec, encoding="utf-8") as f:
            spec = json.load(f)
        corpus = read_corpus(args.corpus)
        nodes, edges, comps, legend, legend_items = parse_svg(args.svg)
        add("structure", {"check": "svg_parse", "match": True,
                          "node_groups": len(nodes), "edge_groups": len(edges)})
        add("structure", {"check": "group_counts",
                          "nodes_svg_vs_spec": [len(nodes), len(spec.get("nodes", []))],
                          "edges_svg_vs_spec": [len(edges), len(spec.get("edges", []))],
                          "match": len(nodes) >= len(spec.get("nodes", []))
                          and len(edges) >= len(spec.get("edges", []))})
        centers = {}
        for n in spec.get("nodes", []):
            e = nodes.get(n["id"])
            lab, cx, cy = node_info(e) if e is not None else ("", None, None)
            if e is not None:
                centers[n["id"]] = (cx, cy)
            add("entity_checks", {"check": "node_present", "element_id": n["id"],
                                  "match": e is not None})
            if e is None:
                continue
            add("entity_checks", {"check": "label_match", "element_id": n["id"],
                                  "spec": n.get("label"), "svg": lab,
                                  "match": norm(lab) == norm(n.get("label"))})
            add("entity_checks", {"check": "compartment_attr", "element_id": n["id"],
                                  "spec": n.get("compartment"), "svg": e.get("data-compartment"),
                                  "match": e.get("data-compartment") == n.get("compartment")})
            # 命名规范: 实体符号应含 ASCII 字母。禁用 isalpha（汉字也是 isalpha=True）。
            has_ascii = bool(re.search(r"[A-Za-z]", n.get("label", "")))
            add("entity_checks", {"check": "naming_ascii_regex", "element_id": n["id"],
                                  "note": "用[A-Za-z]正则而非isalpha（汉字isalpha=True会漏检）",
                                  "match": has_ascii})
            q = norm(n.get("evidence"))
            add("entity_checks", {"check": "evidence_verbatim", "element_id": n["id"],
                                  "quote": n.get("evidence", ""),
                                  "match": (q in corpus) if corpus else None})
        for e in spec.get("edges", []):
            g = edges.get(e["id"])
            add("edge_semantics", {"check": "edge_present", "element_id": e["id"],
                                   "match": g is not None})
            if g is None:
                continue
            fr, to, mk, dash = edge_info(g)
            exp = EDGE_STYLE.get(e.get("type"), {"marker": "marker-arrow", "dash": None})
            add("edge_semantics", {"check": "type_attr", "element_id": e["id"],
                                   "spec": e.get("type"), "svg": g.get("data-type"),
                                   "match": g.get("data-type") == e.get("type")})
            add("edge_semantics", {"check": "arrow_style", "element_id": e["id"],
                                   "expect": exp["marker"], "svg": mk,
                                   "match": exp["marker"] in mk})
            add("edge_semantics", {"check": "dash_convention", "element_id": e["id"],
                                   "expect": exp["dash"], "svg": dash or None,
                                   "match": (dash or None) == exp["dash"]})
            q = norm(e.get("evidence"))
            add("edge_semantics", {"check": "evidence_verbatim", "element_id": e["id"],
                                   "quote": e.get("evidence", ""),
                                   "match": (q in corpus) if corpus else None})
            s, d = centers.get(e.get("src")), centers.get(e.get("dst"))
            if fr[0] is not None and to[0] is not None and s and d and s[0] is not None and d[0] is not None:
                dot = (to[0] - fr[0]) * (d[0] - s[0]) + (to[1] - fr[1]) * (d[1] - s[1])
                add("direction_checks", {"check": "vector_dot", "element_id": e["id"],
                                         "src": e.get("src"), "dst": e.get("dst"),
                                         "dot": round(dot, 1),
                                         "match": e.get("src") == e.get("dst") or dot > 0})
            else:
                add("direction_checks", {"check": "geometry_missing", "element_id": e["id"],
                                         "match": False})
        spec_comps = spec.get("compartments") or ["extracellular", "membrane", "cytoplasm", "nucleus"]
        bands = {}
        for c in comps:
            try:
                bands[c.get("data-compartment")] = (float(c.get("data-y")), float(c.get("data-h")))
            except (TypeError, ValueError):
                pass
        add("compartment_checks", {"check": "bands_present", "expect": spec_comps,
                                   "found": sorted(bands),
                                   "match": all(c in bands for c in spec_comps)})
        if bands:
            ordered = [c for c, _ in sorted(bands.items(), key=lambda kv: kv[1][0])]
            add("compartment_checks", {"check": "band_order_top_down", "order": ordered,
                                       "expect": spec_comps, "match": ordered == spec_comps})
        for n in spec.get("nodes", []):
            b = bands.get(n.get("compartment"))
            cxy = centers.get(n["id"])
            if b and cxy and cxy[0] is not None:
                inside = b[0] - args.tol <= cxy[1] <= b[0] + b[1] + args.tol
                add("compartment_checks", {"check": "node_in_band", "element_id": n["id"],
                                           "compartment": n.get("compartment"),
                                           "cy": cxy[1], "band": list(b),
                                           "match": inside})
            else:
                add("compartment_checks", {"check": "band_or_center_missing",
                                           "element_id": n["id"], "match": False})
        used_t = {e.get("type") for e in spec.get("edges", [])}
        used_c = {n.get("type") for n in spec.get("nodes", [])}
        leg_e = {g.get("data-key") for g in legend_items if g.get("data-kind") == "edge"}
        leg_n = {g.get("data-key") for g in legend_items if g.get("data-kind") == "node"}
        add("legend_checks", {"check": "legend_present", "match": legend is not None})
        add("legend_checks", {"check": "edge_keys_vs_used", "legend": sorted(leg_e),
                              "used": sorted(used_t),
                              "match": legend is not None and leg_e == used_t})
        add("legend_checks", {"check": "node_keys_vs_used", "legend": sorted(leg_n),
                              "used": sorted(used_c),
                              "match": legend is not None and leg_n == used_c})
        add("legend_checks", {"check": "legend_count_vs_encoding",
                              "legend_items": len(legend_items),
                              "edge_types": len(used_t), "node_categories": len(used_c),
                              "match": legend is not None
                              and len(legend_items) == len(used_t) + len(used_c)})
        png = os.path.splitext(os.path.abspath(args.svg))[0] + ".png"
        if os.path.exists(png):
            rs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_svg.py")
            ok_marker = os.path.exists(rs) and MARKER in open(rs, encoding="utf-8").read()
            if ok_marker:
                p = subprocess.run([sys.executable, rs, "--check", png],
                                   capture_output=True, text=True, timeout=120)
                add("export_checks", {"check": "png_pixel", "png": png,
                                      "stdout": (p.stdout or "").strip()[:200],
                                      "match": "CHECK OK" in (p.stdout or "")})
            else:
                add("export_checks", {"check": "render_svg_locator",
                                      "note": "render_svg.py 未命中标志", "match": False})
        else:
            add("export_checks", {"check": "png_pixel", "png": png, "present": False,
                                  "match": None, "note": "无 PNG，跳过（不计 fail）"})
        out.update(ok=True, pass_=fail[0] == 0, fail_count=fail[0],
                   summary={"nodes": len(spec.get("nodes", [])),
                            "edges": len(spec.get("edges", [])),
                            "check_items": sum(len(v) for v in checks.values()),
                            "corpus_chars": len(corpus)})
        out["checks"] = checks
    except Exception as ex:
        out["error"] = repr(ex)
        out["pass_"] = False
        out["fail_count"] = fail[0]
        out["checks"] = checks
    if args.report:
        try:
            with open(args.report, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception as ex2:
            out["report_error"] = repr(ex2)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)   # 含 argparse 出错：失败路径一律 exit 0
    except Exception as ex:
        print(json.dumps({"tool": "validate_pathway", "ok": False, "error": repr(ex)},
                         ensure_ascii=False))
        sys.exit(0)
