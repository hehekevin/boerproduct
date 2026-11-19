#!/usr/bin/env python3
"""probe_input.py — 输入探查：契约字段抓取 + slide-workorder 解析 + 模板/起始稿探查。

输出 probe_report.json：
  contract      case.json 的 case_id + output_contract 全字段名（供骨架逐个回填）
  workorder     mode(generate/edit/adapt)/audience/slide_count/source_preservation/
                template_inheritance/编辑操作清单（模型据此排页与编辑，不许臆测）
  template      版式/占位符/主题字体配色/页型推荐（真实值，禁止模型手抄转述）
  starting_deck 起始稿页数/逐页文本头（编辑模式的保真对照基线）

退出码恒 0；探查失败落报告并给降级建议，不抛栈。
用法: python3 probe_input.py --input-dir /input --out /app/work/probe_report.json
"""
import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def find_file(root, names):
    """按候选名/后缀定位输入文件（直接 os 检查，不用 find|head -1）。"""
    if not root or not os.path.isdir(root):
        return None
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            lf = f.lower()
            if any(lf == n or lf.endswith(n) for n in names):
                return os.path.join(dirpath, f)
    return None


def load_json_safe(path):
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def pptx_slide_texts(path, max_pages=60):
    """stdlib 直读 pptx 逐页文本（编辑保真基线）。失败返回空+原因。"""
    try:
        z = zipfile.ZipFile(path)
        names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                       key=lambda n: int(re.search(r"(\d+)", n).group(1)))
        pages = []
        for i, n in enumerate(names[:max_pages], 1):
            root = ET.fromstring(z.read(n))
            texts = [t.text.strip() for t in root.iter("{%s}t" % NS_A) if t.text and t.text.strip()]
            pages.append({"no": i, "text_head": " | ".join(texts)[:120], "chars": sum(len(t) for t in texts)})
        return {"pages": pages, "count": len(names), "engine": "raw-xml"}
    except Exception as e:
        return {"pages": [], "count": 0, "error": str(e)[:200]}


def probe_template_pptx(path):
    """模板探查：优先 python-pptx，缺失则 raw-xml 数版式；损坏落失败报告。"""
    rep = {"template": path, "ok": False}
    try:
        from pptx import Presentation
        from pptx.util import Emu
        from pptx.oxml.ns import qn
        prs = Presentation(path)
        rep["ok"] = True
        rep["engine"] = "python-pptx"
        rep["slide_size"] = {"w_in": round(Emu(prs.slide_width).inches, 3),
                             "h_in": round(Emu(prs.slide_height).inches, 3)}
        rep["layouts"] = []
        for lay in prs.slide_layouts:
            entry = {"name": lay.name, "placeholders": []}
            for ph in lay.placeholders:
                pe = ph._element.find(qn("p:nvSpPr") + "/" + qn("p:nvPr") + "/" + qn("p:ph"))
                ptype = (pe.get("type") if pe is not None else None) or "body"
                try:
                    geom = {"x": round(Emu(ph.left).inches, 2), "y": round(Emu(ph.top).inches, 2),
                            "w": round(Emu(ph.width).inches, 2), "h": round(Emu(ph.height).inches, 2)}
                except Exception:
                    geom = None
                entry["placeholders"].append({"idx": ph.placeholder_format.idx, "type": ptype,
                                              "name": ph.name, "geom": geom})
            rep["layouts"].append(entry)
    except ImportError:
        try:
            z = zipfile.ZipFile(path)
            n_layouts = sum(1 for n in z.namelist() if re.match(r"ppt/slideLayouts/slideLayout\d+\.xml$", n))
            rep["ok"] = n_layouts > 0
            rep["engine"] = "raw-xml"
            rep["layout_count"] = n_layouts
            rep["note"] = "python-pptx 缺失，仅清点版式数；槽位几何未知，构建走 stdlib 兜底"
        except Exception as e:
            rep["error"] = str(e)[:200]
    except Exception as e:
        rep["error"] = str(e)[:200]
        rep["fallback"] = "academic_default_layouts"
    if rep.get("ok"):
        try:
            z = zipfile.ZipFile(path)
            for n in z.namelist():
                if "theme" in n and n.endswith(".xml"):
                    root = ET.fromstring(z.read(n))
                    fonts = {}
                    for tag in ("majorFont", "minorFont"):
                        el = root.find(".//{%s}%s" % (NS_A, tag))
                        if el is not None:
                            lat, ea = el.find("{%s}latin" % NS_A), el.find("{%s}ea" % NS_A)
                            fonts[tag] = {"latin": lat.get("typeface") if lat is not None else None,
                                          "ea": ea.get("typeface") if ea is not None else None}
                    rep["theme_fonts"] = fonts
                    colors = []
                    for i in range(1, 7):
                        el = root.find(".//{%s}accent%d/{%s}srgbClr" % (NS_A, i, NS_A))
                        colors.append(el.get("val") if el is not None else None)
                    rep["theme_colors"] = colors
                    break
        except Exception as e:
            rep["theme_note"] = "theme parse failed: %s" % e
    return rep


def pick_layout(rep):
    """页型推荐映射：deck layout -> 模板实存版式名。"""
    layouts = [l.get("name", "") for l in rep.get("layouts", [])]
    lowered = [(n.lower(), n) for n in layouts]

    def pick(keys):
        for k in keys:
            for low, orig in lowered:
                if k in low:
                    return orig
        return None
    return {"title": pick(["title slide", "标题", "title"]),
            "section": pick(["section", "节"]),
            "bullets": pick(["title and content", "标题和内容", "title only", "仅标题"]),
            "bullets+figure": pick(["two content", "两栏", "title and content"]),
            "figure": pick(["picture", "图片", "title only"]),
            "blank": pick(["blank", "空白"])}


def parse_workorder(data):
    """工单解析：只抄真实存在的键，缺键如实登记 unknown，不臆测。"""
    wo = data or {}
    out = {"raw_keys": sorted(wo.keys()) if isinstance(wo, dict) else []}
    out["mode"] = wo.get("mode") or wo.get("task_mode") or "unknown"
    out["audience"] = wo.get("audience") or wo.get("target_audience") or "unknown"
    sc = wo.get("slide_count") or wo.get("total_slides") or wo.get("max_slides")
    if isinstance(sc, dict):
        out["slide_count"] = {"max": sc.get("max") or sc.get("maximum"), "exact": sc.get("exact"), "min": sc.get("min")}
    elif sc is not None:
        out["slide_count"] = {"max": sc}
    else:
        out["slide_count"] = None
    out["source_preservation"] = wo.get("source_preservation") or wo.get("preserve_source") or "unknown"
    out["template_inheritance"] = wo.get("template_inheritance") or wo.get("use_template") or "unknown"
    out["language"] = wo.get("language") or "unknown"
    edits = wo.get("edits") or wo.get("edit_ops") or wo.get("operations") or []
    out["edit_ops_count"] = len(edits) if isinstance(edits, list) else 0
    out["edit_ops_head"] = edits[:10] if isinstance(edits, list) else []
    out["notes"] = wo.get("notes") or wo.get("instructions") or ""
    return out


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("--input-dir", default="/input")
    ap.add_argument("--case", default=None, help="case.json 显式路径")
    ap.add_argument("--workorder", default=None, help="slide-workorder.json 显式路径")
    ap.add_argument("--template", default=None)
    ap.add_argument("--starting-deck", default=None)
    ap.add_argument("--out", default="probe_report.json")
    args = ap.parse_args()

    rep = {"input_dir": args.input_dir, "found": {}, "warnings": []}
    case_path = args.case or find_file(args.input_dir, ["case.json"])
    wo_path = args.workorder or find_file(args.input_dir, ["slide-workorder.json", "workorder.json"])
    tpl_path = args.template or find_file(args.input_dir, ["target-template.pptx", "template.pptx"])
    deck_path = args.starting_deck or find_file(args.input_dir, ["starting-deck.pptx", "starting_deck.pptx"])

    if case_path:
        data, err = load_json_safe(case_path)
        if data is not None:
            oc = data.get("output_contract")
            if isinstance(oc, list):
                rep["contract"] = {"case_id": data.get("case_id"), "fields": list(oc)}
            else:
                rep["contract"] = {"case_id": data.get("case_id"), "raw": oc,
                                   "warning": "output_contract 非 list，模型须人工抄字段"}
            rep["found"]["case.json"] = case_path
        else:
            rep["warnings"].append("case.json 解析失败: %s" % err)
    else:
        rep["warnings"].append("case.json 未找到，契约字段须从 task.md 抄录")

    if wo_path:
        data, err = load_json_safe(wo_path)
        rep["workorder"] = parse_workorder(data) if data is not None else {"error": err}
        rep["found"]["slide-workorder.json"] = wo_path
        if data is not None:
            rep["constraints"] = {"max_slides": (rep["workorder"].get("slide_count") or {}).get("max")
                                  if isinstance(rep["workorder"].get("slide_count"), dict) else None}
    else:
        rep["workorder"] = {"error": "not_found", "note": "无工单时按 task.md 任务说明确定 mode/页数"}
        rep["constraints"] = {}

    if tpl_path:
        rep["template"] = probe_template_pptx(tpl_path)
        if rep["template"].get("ok"):
            rep["template"]["recommendation"] = pick_layout(rep["template"])
        rep["found"]["template"] = tpl_path
    else:
        rep["template"] = {"ok": False, "note": "no_template", "fallback": "academic_default_layouts"}

    if deck_path:
        rep["starting_deck"] = pptx_slide_texts(deck_path)
        rep["found"]["starting_deck"] = deck_path
    else:
        rep["starting_deck"] = {"count": 0, "note": "无起始稿：按 generate 模式从材料生成"}

    rep["mode_inference"] = "edit" if deck_path else "generate"
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        rep["_written"] = args.out
    except Exception as e:
        rep["_write_error"] = str(e)
    print(json.dumps({k: rep.get(k) for k in
                      ("contract", "workorder", "mode_inference", "found", "warnings")}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
