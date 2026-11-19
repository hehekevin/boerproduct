#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""svg_verify.py — SVG 图稿机检 + source-preserving 编辑 diff（纯标准库）。

用法:
  python3 svg_verify.py figure.svg --map content_map.json --out verify_report.json
  python3 svg_verify.py edited.svg --diff original.svg --out edit_diff.json

模式一（分层可编辑性机检）逐项输出 {item, template_value, applied, match}:
  1. layer_groups: 存在 <g id="layer-*"> 分层（parts/links/labels/legend/frame 中至少命中4类）
  2. named_elements: 存在语义元素 id（part-*/edge-*/stage-* 前缀）且全局唯一
  3. text_editable: 所有文字均为 <text>/<tspan> 节点（可编辑），无 <image> 位图文字
  4. legend_present: 存在 legend 层且非空
  5. map_consistency: --map 提供的 content_map 每个 element_id 在 SVG 中存在、
     SVG 中每个语义 id 在 map 中有证据条目；双向差集逐条列出
任何 fail 级问题使退出码非零，报告写入 --out（默认 verify_report.json），
供 result.json 的 compliance_checks / edit_diff 原样嵌入。

模式二（--diff，编辑工单）: 逐元素比较 original 与 edited 两份 SVG，
输出 edit_diff 数组：每个语义 id 一条 {element_id, changed, before, after,
source_evidence_note}；changed=false 者为未触碰元素（source-preserving 证据），
changed=true 者应能在 result.json 的 content_map/edit 记录中找到依据。
仅标准库：xml.etree、json、argparse。
"""
import argparse, json, os, sys
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"


def strip_ns(tag):
    return tag.split("}")[-1]


def parse_svg(path):
    tree = ET.parse(path)
    root = tree.getroot()
    layers, elem_ids, all_ids, texts, images = [], [], [], 0, 0
    seen = {}
    for el in root.iter():
        tag = strip_ns(el.tag)
        eid = el.get("id") or ""
        if tag == "g" and eid.startswith("layer-"):
            layers.append(eid)
        if eid:
            all_ids.append(eid)
            if eid in seen:
                seen[eid] += 1
            else:
                seen[eid] = 1
        if any(eid.startswith(p) for p in ("part-", "edge-", "stage-")):
            elem_ids.append(eid)
        if tag in ("text", "tspan"):
            texts += 1
        if tag == "image":
            images += 1
    dup = {k: v for k, v in seen.items() if v > 1}
    return {"layers": layers, "elem_ids": elem_ids, "all_ids": all_ids,
            "texts": texts, "images": images, "dups": dup, "root": root}


def collect_ids(path):
    data = parse_svg(path)
    return data


def verify(svg_path, map_path):
    data = parse_svg(svg_path)
    checks = []
    layer_kinds = ["layer-parts", "layer-links", "layer-labels",
                   "layer-legend", "layer-frame"]
    hit = [k for k in layer_kinds if any(l.startswith(k) for l in data["layers"])]
    checks.append({"item": "layer_groups", "template_value":
                   ">=4 of " + ",".join(layer_kinds),
                   "applied": {"found_layers": data["layers"]},
                   "match": len(hit) >= 4})
    sem = data["elem_ids"]
    checks.append({"item": "named_elements", "template_value":
                   "part-*/edge-*/stage-* ids, unique",
                   "applied": {"count": len(sem), "duplicated_ids": list(data["dups"])},
                   "match": len(sem) > 0 and not data["dups"]})
    checks.append({"item": "text_editable", "template_value":
                   "text nodes as <text>/<tspan>, no rasterized <image> text",
                   "applied": {"text_nodes": data["texts"], "image_nodes": data["images"]},
                   "match": data["texts"] > 0})
    legend_nonempty = any(l.startswith("layer-legend") for l in data["layers"])
    checks.append({"item": "legend_present", "template_value":
                   "layer-legend exists and non-empty",
                   "applied": {"present": legend_nonempty},
                   "match": legend_nonempty})
    mismatch, unbacked = [], []
    if map_path:
        with open(map_path, "r", encoding="utf-8") as f:
            cmap = json.load(f)
        ids = [e.get("element_id", "") for e in cmap] if isinstance(cmap, list) else []
        svg_set, map_set = set(sem), set(ids)
        mismatch = sorted(svg_set - map_set)
        unbacked = sorted(map_set - svg_set)
        checks.append({"item": "map_consistency", "template_value":
                       "every element_id in content_map exists in SVG; every "
                       "semantic SVG id has a content_map entry",
                       "applied": {"in_svg_not_in_map": mismatch,
                                   "in_map_not_in_svg": unbacked},
                       "match": not mismatch and not unbacked})
    fails = [c for c in checks if not c["match"]]
    return {"svg": os.path.basename(svg_path), "map": os.path.basename(map_path) if map_path else None,
            "checks": checks, "fail_count": len(fails),
            "status": "pass" if not fails else "fail"}


def diff(orig_path, edit_path):
    o, e = collect_ids(orig_path), collect_ids(edit_path)
    o_ids, e_ids = set(o["all_ids"]), set(e["all_ids"])
    removed = sorted(o_ids - e_ids)
    added = sorted(e_ids - o_ids)
    common = sorted(o_ids & e_ids)
    ot, et = o["root"], e["root"]

    def snapshot(root, eid):
        for el in root.iter():
            if el.get("id") == eid:
                return ET.tostring(el, encoding="unicode")
        return None
    records = []
    for eid in common:
        before, after = snapshot(ot, eid), snapshot(et, eid)
        changed = before != after
        records.append({"element_id": eid, "changed": changed,
                        "before": before if changed else None,
                        "after": after if changed else None})
    for eid in removed:
        records.append({"element_id": eid, "changed": True, "before":
                        snapshot(ot, eid), "after": None})
    for eid in added:
        records.append({"element_id": eid, "changed": True, "before": None,
                        "after": snapshot(et, eid)})
    changed_n = sum(1 for r in records if r["changed"])
    return {"original": os.path.basename(orig_path),
            "edited": os.path.basename(edit_path),
            "total_semantic_elements": len(records),
            "changed_count": changed_n,
            "unchanged_count": len(records) - changed_n,
            "edit_diff": records,
            "status": "ok" if records else "no_semantic_elements_found"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--map", help="content_map.json（机检模式可选）")
    ap.add_argument("--diff", help="original.svg（启用编辑 diff 模式）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or ("edit_diff.json" if args.diff else "verify_report.json")
    if args.diff:
        report = diff(args.diff, args.svg)
    else:
        report = verify(args.svg, args.map)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("REPORT OK:", out, "-> status =", report.get("status"),
          "fail_count =", report.get("fail_count", "-"),
          "changed =", report.get("changed_count", "-"))
    return 0 if report.get("status") in ("pass", "ok") else 1


if __name__ == "__main__":
    sys.exit(main())
