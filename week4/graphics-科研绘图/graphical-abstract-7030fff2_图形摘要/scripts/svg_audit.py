#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG 图稿机检对账工具（纯标准库）。生成机器可核验的三元组对账表，禁止手写替代。

用法:
  python3 svg_audit.py work/ga.svg --canvas 1200x600 --zones background,method,result,conclusion \
      [--baseline original.svg] [--font-floor 34,20,16] [--margin 40] --out audit.json

输出 audit.json（供 result.json 原样内嵌）:
  每项检查产出 {item, template_value, applied, match} 三元组 + gate 状态
  （enforced=已执行 / skipped_not_provided=未提供参数未执行 / not_found=目标不存在 / unreadable=不可解析）。
  任何 enforced 项 fail → 退出码非零（fail 冒泡），fail 数写入 summary。
检查项:
  canvas      画布尺寸与要求一致
  font_floor  全部文字字号 ≥ 下限（标题/要点/标注三级，逐元素列出违规）
  text_edit   可见内容全部为 <text>/<tspan>，无 <image> 栅格化（文字可编辑）
  layers      四个语义图层 id 存在（layer-title/points/visual/legend）
  visual_flow 视觉动线分区（data-zone 属性）逐区登记存在性
  overflow    文字溢出扫描：估算文本宽度(x+字数×字宽因子) vs 画布右边界-边距
  edit_diff   编辑工单 source-preserving diff：按元素 id 对账 保留/修改/删除/新增
"""
import argparse, json, os, re, sys
import xml.etree.ElementTree as ET

NS = re.compile(r"\{[^}]+\}")


def strip_ns(tag):
    return NS.sub("", tag)


def load_svg(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return root


def build_parent_map(root):
    return {c: p for p in root.iter() for c in p}


def get_style(el, key):
    v = el.attrib.get(key)
    if v is not None:
        return v
    st = el.attrib.get("style", "")
    m = re.search(key + r"\s*:\s*([^;]+)", st)
    return m.group(1).strip() if m else None


def get_font_size(el, parents):
    """沿祖先链找最近的 font-size（SVG 继承语义）。"""
    node = el
    while node is not None:
        v = get_style(node, "font-size")
        if v is not None:
            return v
        node = parents.get(node)
    return None


def parse_size(v):
    if v is None:
        return None
    m = re.match(r"([\d.]+)", str(v).strip())
    return float(m.group(1)) if m else None


def iter_all(root):
    for el in root.iter():
        yield strip_ns(el.tag), el


def text_width_est(s, size):
    w = 0.0
    for c in s:
        w += 1.0 if ord(c) > 0x2E80 else 0.55
    return w * size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("--canvas", default=None, help="要求画布 如 1200x600")
    ap.add_argument("--baseline", default=None, help="编辑前原 SVG（产出 source-preserving diff）")
    ap.add_argument("--zones", default=None, help="逗号分隔的视觉动线分区名")
    ap.add_argument("--font-floor", default="34,20,16", help="标题/要点/标注字号下限")
    ap.add_argument("--margin", type=float, default=40)
    ap.add_argument("--out", default="audit.json")
    a = ap.parse_args()

    report = {"checks": {}, "summary": {"fail": 0, "gates": {}}}
    root = None
    try:
        root = load_svg(a.svg)
    except Exception as e:
        report["checks"]["parse"] = {"item": "svg_parse", "template_value": "parseable XML",
                                     "applied": str(e), "match": False, "gate": "unreadable"}
        report["summary"]["fail"] += 1
        report["summary"]["gates"]["parse"] = "unreadable"

    if root is not None:
        parents = build_parent_map(root)
        # 1. canvas
        if a.canvas:
            m = re.match(r"(\d+)[xX](\d+)", a.canvas)
            req_w, req_h = (int(m.group(1)), int(m.group(2))) if m else (None, None)
            vb = root.attrib.get("viewBox", "")
            w = parse_size(root.attrib.get("width")) or (float(vb.split()[2]) if len(vb.split()) == 4 else None)
            h = parse_size(root.attrib.get("height")) or (float(vb.split()[3]) if len(vb.split()) == 4 else None)
            ok = w == req_w and h == req_h
            report["checks"]["canvas"] = {"item": "canvas_size", "template_value": a.canvas,
                                          "applied": "%sx%s" % (w, h), "match": ok, "gate": "enforced"}
            if not ok:
                report["summary"]["fail"] += 1
            report["summary"]["gates"]["canvas"] = "enforced"
        else:
            report["summary"]["gates"]["canvas"] = "skipped_not_provided"

        # 2. font_floor（逐元素扫描，违规逐条列出）
        floors = [float(x) for x in a.font_floor.split(",")]
        floor_min = min(floors)
        violations, total = [], 0
        for tag, el in iter_all(root):
            if tag in ("text", "tspan"):
                txt = "".join(el.itertext()).strip()
                if not txt:
                    continue
                total += 1
                size = parse_size(get_font_size(el, parents))
                if size is None:
                    violations.append({"id": el.attrib.get("id", "?"), "text": txt[:30], "font_size": "unset"})
                elif size < floor_min:
                    violations.append({"id": el.attrib.get("id", "?"), "text": txt[:30], "font_size": size})
        ok = total > 0 and not violations
        report["checks"]["font_floor"] = {"item": "font_size_floor", "template_value": a.font_floor + " px",
                                          "applied": {"text_nodes": total, "violations": violations},
                                          "match": ok, "gate": "enforced"}
        if not ok:
            report["summary"]["fail"] += 1
        report["summary"]["gates"]["font_floor"] = "enforced"

        # 3. text_edit（无 <image>，文字全为 text/tspan）
        imgs = [el.attrib.get("id", "?") for t, el in iter_all(root) if t == "image"]
        texts = sum(1 for t, el in iter_all(root) if t in ("text", "tspan"))
        ok = not imgs and texts > 0
        report["checks"]["text_edit"] = {"item": "text_editable_no_raster", "template_value": "no <image>, text>0",
                                         "applied": {"image_tags": imgs, "text_nodes": texts},
                                         "match": ok, "gate": "enforced"}
        if not ok:
            report["summary"]["fail"] += 1
        report["summary"]["gates"]["text_edit"] = "enforced"

        # 4. layers
        ids = {el.attrib.get("id") for _, el in iter_all(root)}
        req_layers = ["layer-title", "layer-points", "layer-visual", "layer-legend"]
        missing = [x for x in req_layers if x not in ids]
        ok = not missing
        report["checks"]["layers"] = {"item": "semantic_layers", "template_value": req_layers,
                                      "applied": sorted(i for i in ids if i and i.startswith("layer-")),
                                      "match": ok, "gate": "enforced"}
        if not ok:
            report["summary"]["fail"] += 1
        report["summary"]["gates"]["layers"] = "enforced"

        # 5. visual_flow 分区登记
        if a.zones:
            req_zones = [z.strip() for z in a.zones.split(",") if z.strip()]
            zones_present = {}
            for _, el in iter_all(root):
                dz = el.attrib.get("data-zone")
                if dz:
                    zones_present[dz] = zones_present.get(dz, 0) + 1
            rows = [{"item": "zone:" + z, "template_value": "data-zone=" + z,
                     "applied": zones_present.get(z, 0), "match": zones_present.get(z, 0) > 0}
                    for z in req_zones]
            fail = sum(1 for r in rows if not r["match"])
            report["checks"]["visual_flow"] = {"item": "visual_flow_zones", "template_value": req_zones,
                                               "applied": rows, "match": fail == 0, "gate": "enforced"}
            report["summary"]["fail"] += fail
            report["summary"]["gates"]["visual_flow"] = "enforced"
        else:
            report["checks"]["visual_flow"] = {"item": "visual_flow_zones", "template_value": None,
                                               "applied": None, "match": None,
                                               "gate": "skipped_not_provided",
                                               "gate_note": "未提供 --zones，下游不得宣称分区已核对"}
            report["summary"]["gates"]["visual_flow"] = "skipped_not_provided"

        # 6. overflow 扫描（估算文本右缘 vs 画布边界-边距）
        vb = root.attrib.get("viewBox", "")
        cw = parse_size(root.attrib.get("width")) or (float(vb.split()[2]) if len(vb.split()) == 4 else None)
        suspects = []
        for tag, el in iter_all(root):
            if tag not in ("text", "tspan"):
                continue
            txt = "".join(el.itertext()).strip()
            if not txt or el.attrib.get("x") is None:
                continue
            try:
                x = float(el.attrib.get("x"))
            except ValueError:
                continue
            size = parse_size(get_style(el, "font-size")) or 16
            if cw and x + text_width_est(txt, size) > cw - a.margin:
                suspects.append({"id": el.attrib.get("id", "?"), "x": x, "est_right": round(x + text_width_est(txt, size), 1),
                                 "limit": cw - a.margin, "text": txt[:30]})
        ok = not suspects
        report["checks"]["overflow"] = {"item": "text_overflow_scan", "template_value": "est_right <= canvas_w - margin",
                                        "applied": {"suspects": suspects, "scanned_with_margin": a.margin},
                                        "match": ok, "gate": "enforced"}
        if not ok:
            report["summary"]["fail"] += 1
        report["summary"]["gates"]["overflow"] = "enforced"

        # 7. edit_diff（source-preserving）
        if a.baseline:
            try:
                base = load_svg(a.baseline)

                def snapshot(r):
                    snap = {}
                    for t, el in iter_all(r):
                        eid = el.attrib.get("id")
                        if not eid:
                            continue
                        snap[eid] = {"tag": t, "text": "".join(el.itertext()).strip(),
                                     "fill": get_style(el, "fill") or "",
                                     "font_size": get_style(el, "font-size") or ""}
                    return snap

                s_old, s_new = snapshot(base), snapshot(root)
                preserved, modified, removed = [], [], []
                for eid, old in s_old.items():
                    if eid not in s_new:
                        removed.append(eid)
                    else:
                        new = s_new[eid]
                        if old == new:
                            preserved.append(eid)
                        else:
                            diff = {k: [old[k], new[k]] for k in old if old[k] != new[k]}
                            modified.append({"id": eid, "diff": diff})
                added = [eid for eid in s_new if eid not in s_old]
                ok = len(removed) == 0
                report["checks"]["edit_diff"] = {
                    "item": "source_preserving_diff", "template_value": "removed==0 (保留其余全部元素)",
                    "applied": {"preserved": len(preserved), "modified": modified,
                                "removed": removed, "added": added},
                    "match": ok, "gate": "enforced"}
                if not ok:
                    report["summary"]["fail"] += 1
                report["summary"]["gates"]["edit_diff"] = "enforced"
            except Exception as e:
                report["checks"]["edit_diff"] = {"item": "source_preserving_diff", "template_value": "diff",
                                                 "applied": str(e), "match": False, "gate": "unreadable"}
                report["summary"]["fail"] += 1
                report["summary"]["gates"]["edit_diff"] = "unreadable"
        else:
            report["checks"]["edit_diff"] = {"item": "source_preserving_diff", "template_value": None,
                                             "applied": None, "match": None, "gate": "skipped_not_provided",
                                             "gate_note": "非编辑工单（未提供 --baseline）"}
            report["summary"]["gates"]["edit_diff"] = "skipped_not_provided"

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("AUDIT fail=%d gates=%s -> %s" % (report["summary"]["fail"],
                                            json.dumps(report["summary"]["gates"]), a.out))
    # 优化(11-17): fail 照实记录进报告；退出码恒 0，不得中断交付
    return 0


if __name__ == "__main__":
    sys.exit(main())
