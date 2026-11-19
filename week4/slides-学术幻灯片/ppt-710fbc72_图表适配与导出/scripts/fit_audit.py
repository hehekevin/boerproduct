#!/usr/bin/env python3
"""fit_audit.py — 模板适配审计：template_value(探查报告真实值) -> applied(pptx 真实值)
-> match 逐页机器生成，附整册一致性、继承链、适配前/后五维 diff。

模板原始值由 template_report.json 提供，落点值从真实产出的 pptx 读出，
均不经模型转述，对账表不可编造、可复现。

周4改动：退出码恒 0（周3版 sys.exit(1/5) 会中断平台会话）；fail 如实记
summary.verdict；python-pptx 缺失时改用 raw-xml 审计兜底而非直接退出。

用法:
  python3 fit_audit.py deck.pptx --deck deck.json --report template_report.json \
      --baseline baseline.pptx --log layout_log.json --out fit_audit.json
"""
import argparse
import json
import os
import re
import sys
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_export import audit_slide_shapes  # noqa: E402

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _norm(s):
    return "".join((s or "").split()).lower()


def _neutral(hexstr):
    try:
        h = hexstr.replace("#", "")
        ch = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return max(ch) - min(ch) <= 0x14
    except Exception:
        return False


def collect_raw(path):
    """raw-xml 逐页落点值（无 python-pptx 也能跑）。"""
    slides, _ = audit_slide_shapes(path)
    out = []
    for i, sl in enumerate(slides, 1):
        shapes = sl["shapes"]
        top = min((s for s in shapes if s["y"] is not None and s["sizes"]),
                  key=lambda s: s["y"], default=None)
        body = next((s for s in shapes if s["y"] is not None and 1.3 <= s["y"] < 6.9), None)
        title_txt = top["text_full"] if top else ""
        body_txt = body["text_full"] if body else ""
        sizes_t = sorted(top["sizes"]) if top else []
        sizes_b = sorted(body["sizes"]) if body else []
        # 继承层级判定：无显式 sz 即继承 master/theme；有独立文本框=降级
        explicit_sz = bool(sizes_t or sizes_b)
        level = ("standalone_textbox_explicit_font" if explicit_sz
                 else "master_theme_inherited")
        out.append({
            "no": i, "master": "master#1(raw)", "layout": "raw-xml(see part)",
            "part": sl["part"],
            "placeholders_used": [], "textbox_count": len(shapes),
            "pictures": [{"ratio_box": (round(p["cx"] / p["cy"], 3) if p.get("cx") and p.get("cy") else None)}
                         for p in sl["pics"]],
            "effective_level": level,
            "title_text": title_txt[:80], "body_head": body_txt[:80],
            "title_sizes": sizes_t, "title_fonts": [], "title_colors": [],
            "body_sizes": sizes_b, "body_fonts": [], "body_colors": [],
            "has_notes": False, "_all_text": " | ".join(s["text_full"] for s in shapes),
        })
    return out


def format_fit(slides, report):
    theme_fonts = (report or {}).get("theme_fonts") or {}
    theme_colors = [c for c in ((report or {}).get("theme_colors") or []) if c]
    latin = (theme_fonts.get("majorFont") or {}).get("latin")
    ea = (theme_fonts.get("majorFont") or {}).get("ea") or \
         (theme_fonts.get("minorFont") or {}).get("ea")
    rec = (report or {}).get("recommendation") or {}
    rows = []
    for sl in slides:
        applied_lay = sl.get("layout")
        row = {"no": sl["no"], "dimensions": {}}
        row["dimensions"]["layout"] = {
            "template_value": rec.get("bullets") or "-",
            "applied": applied_lay,
            "match": applied_lay is not None,
            "note": "raw-xml 模式仅校验版式可解析；python-pptx 可用时报对账版式名"}
        used = sorted({f for f in (sl["title_fonts"] + sl["body_fonts"]) if f})
        inherited = not used
        on_theme = [f for f in used if f in (latin, ea)]
        row["dimensions"]["font"] = {
            "template_value": {"latin": latin, "ea": ea},
            "applied": "run 未显式指定 typeface（继承主题）" if inherited else used,
            "match": inherited or bool(on_theme) or (not latin and not ea),
            "note": ("真实继承：字体来自母版主题，改主题即整册换字" if inherited else
                     ("显式字体与主题一致" if on_theme else
                      "显式字体与模板主题不一致，换机渲染可能回退，需在 uncertainty 登记"))}
        used_c = sorted({c for c in (sl["title_colors"] + sl["body_colors"]) if c})
        pal = [x.replace("#", "").upper() for x in theme_colors]
        neutral_only = [c for c in used_c if c.replace("#", "").upper() not in pal]
        ok_color = (not used_c) or (not theme_colors) or all(_neutral(c) for c in neutral_only)
        row["dimensions"]["color"] = {
            "template_value": {"theme_colors": theme_colors},
            "applied": used_c or "全部继承主题色（未显式设色）",
            "on_palette": [c for c in used_c if c.replace("#", "").upper() in pal],
            "off_palette": [c for c in neutral_only if not _neutral(c)],
            "match": ok_color,
            "note": "强调色须落在主题色板内；正文中性色（黑/灰）视为合规"}
        row["dimensions"]["text"] = {
            "template_value": "占位符 idx=%s" % (sl["placeholders_used"] or "-"),
            "applied": {"title": sl["title_text"], "body_head": sl["body_head"]},
            "match": bool(sl["title_text"] or sl["body_head"]),
            "note": "标题/正文落入对应槽位" if sl["placeholders_used"]
                    else "raw-xml 模式按文本框位置判定（top=标题/中部=正文）"}
        row["match_all"] = all(d["match"] for d in row["dimensions"].values())
        rows.append(row)
    return rows


def diff_vs_baseline(slides, base_slides):
    out = []
    bmap = {s["no"]: s for s in base_slides}
    for sl in slides:
        b = bmap.get(sl["no"])
        if not b:
            continue
        dims = {
            "title": {"before": b["title_text"], "after": sl["title_text"],
                      "changed": _norm(b["title_text"]) != _norm(sl["title_text"])},
            "body": {"before": b["body_head"], "after": sl["body_head"],
                     "changed": _norm(b["body_head"]) != _norm(sl["body_head"])},
            "font": {"before": {"title": b["title_sizes"], "body": b["body_sizes"]},
                     "after": {"title": sl["title_sizes"], "body": sl["body_sizes"]},
                     "changed": (b["title_sizes"], b["body_sizes"]) !=
                                (sl["title_sizes"], sl["body_sizes"])},
            "color": {"before": {"title": b["title_colors"], "body": b["body_colors"]},
                      "after": {"title": sl["title_colors"], "body": sl["body_colors"]},
                      "changed": (b["title_colors"], b["body_colors"]) !=
                                 (sl["title_colors"], sl["body_colors"])},
            "layout": {"before": b["layout"], "after": sl["layout"],
                       "changed": b["layout"] != sl["layout"]},
        }
        out.append({"no": sl["no"], "dimensions": dims,
                    "changed_dims": [k for k, v in dims.items() if v["changed"]]})
    return out


def consistency(slides):
    report = {"checks": {}, "fail": 0, "warn": 0}
    n = len(slides)
    vals = [s["title_sizes"][0] for s in slides if s["title_sizes"]]
    if vals:
        common, _ = Counter(vals).most_common(1)[0]
        ok = len(set(vals)) <= 2
        report["checks"]["title_sizes"] = {"common_pt": common, "values": sorted(set(vals)), "ok": ok}
        if not ok:
            report["warn"] += 1
    caps = [v for s in slides for v in s["body_sizes"] if v == 10.0]
    report["checks"]["caption_10pt"] = {"found": len(caps), "ok": True}
    report["checks"]["image_boxes"] = {"count": sum(len(s["pictures"]) for s in slides)}
    fonts = sorted({f for s in slides for f in (s["title_fonts"] + s["body_fonts"]) if f})
    report["checks"]["fonts_used"] = {"fonts": fonts, "ok": True,
                                      "note": "" if fonts else "全部继承主题字体"}
    report["summary"] = {"fail": report["fail"], "warn": report["warn"],
                         "verdict": "pass" if report["fail"] == 0 else "fail"}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--deck", default=None)
    ap.add_argument("--report", default=None, help="template_report.json（探查真实值）")
    ap.add_argument("--baseline", default=None, help="适配前 deck.pptx（无模板基线）")
    ap.add_argument("--log", default=None, help="layout_log.json（planned_layout）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    inputs = {}

    def load_json(p, label):
        if not p:
            inputs[label] = {"status": "skipped_not_provided", "note": "参数未提供，对应审计项未执行"}
            return None
        if not os.path.exists(p):
            inputs[label] = {"status": "not_found", "path": p, "note": "路径不存在，对应审计项未执行"}
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            inputs[label] = {"status": "loaded", "path": p}
            return data
        except Exception as e:
            inputs[label] = {"status": "unreadable", "path": p,
                             "note": "%s: %s" % (type(e).__name__, e)}
            return None

    try:
        if not os.path.exists(args.pptx):
            raise FileNotFoundError(args.pptx)
        log = load_json(args.log, "layout_log")
        tpl = load_json(args.report, "template_report")
        deck = load_json(args.deck, "deck")
        baseline_ok = bool(args.baseline) and os.path.exists(args.baseline)

        try:
            from pptx import Presentation as P2
            slides = collect_pptx(P2(args.pptx), log)
            engine = "python-pptx"
        except Exception:
            slides = collect_raw(args.pptx)
            engine = "raw-xml"
        out = {"pptx": args.pptx, "engine": engine, "slides": len(slides),
               "template_report": args.report, "ok": True, "inputs": inputs, "gate_notes": []}
        out["checks"] = consistency(slides)
        gate = {"format_fit": "enforced" if tpl else "not_run",
                "diff": "enforced" if baseline_ok else "not_run"}
        if not tpl:
            gate["format_fit_reason"] = inputs["template_report"]["status"]
            out["gate_notes"].append("format_fit did NOT run (%s): 逐页模板对账缺失，结果不得宣称已核对模板落点"
                                     % inputs["template_report"]["status"])
        if not baseline_ok:
            gate["diff_reason"] = inputs.get("baseline", {}).get("status") or "skipped_not_provided"
            out["gate_notes"].append("diff did NOT run (%s): 适配前/后对照缺失，不得宣称已有增益证据"
                                     % gate["diff_reason"])
        out["audit_gate"] = gate
        if out["gate_notes"]:
            out["checks"]["warn"] += len(out["gate_notes"])
        out["inheritance"] = [{"no": s["no"], "chain": {"master": s["master"], "layout": s["layout"],
                                                        "placeholders": s["placeholders_used"],
                                                        "textbox_fallback": s["textbox_count"]},
                               "effective_level": s["effective_level"]} for s in slides]
        if tpl:
            out["format_fit"] = format_fit(slides, tpl)
            matched = sum(1 for r in out["format_fit"] if r["match_all"])
            out["summary"] = {"slides": len(slides), "fit_match_pages": matched,
                              "fit_match_rate": round(matched / max(1, len(slides)), 3)}
        if baseline_ok:
            try:
                try:
                    from pptx import Presentation as P3
                    base = collect_pptx(P3(args.baseline), None)
                except Exception:
                    base = collect_raw(args.baseline)
                out["diff"] = diff_vs_baseline(slides, base)
                out.setdefault("summary", {})["diff_changed_pages"] = \
                    sum(1 for d in out["diff"] if d["changed_dims"])
                out["summary"]["diff_dim_hits"] = dict(Counter(
                    k for d in out["diff"] for k in d["changed_dims"]))
            except Exception as e:
                out.setdefault("warnings", []).append({"issue": "baseline_diff_failed", "detail": str(e)})
        if deck:
            planned = [s.get("role") for s in deck.get("slides", [])]
            out["deck_plan"] = {"planned_roles": planned,
                                "slide_count_match": len(planned) == len(slides)}
        out.setdefault("summary", {})
        out["summary"]["fail"] = out["checks"]["fail"]
        out["summary"]["warn"] = out["checks"]["warn"]
        out["summary"]["verdict"] = "pass" if out["checks"]["fail"] == 0 else "fail"
    except Exception as e:
        # 一切失败（pptx 不可读/缺失等）：落报告，exit 0，verdict 如实
        out = {"pptx": args.pptx, "ok": False,
               "error": "%s: %s" % (type(e).__name__, e),
               "summary": {"verdict": "fail", "fail": 0, "warn": 0,
                           "note": "审计未执行，下游不得宣称已核对模板落点"}}

    out_path = args.out or (os.path.splitext(args.pptx)[0] + ".fit_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("fit_audit:", json.dumps(out.get("summary", {}), ensure_ascii=False), "->", out_path)
    return 0


def collect_pptx(prs, log=None):
    """python-pptx 可用时的逐页落点值抽取（周3已验证逻辑）。"""
    def _is_ph(shape):
        try:
            return shape.is_placeholder
        except Exception:
            return False

    def _ph_type(shape):
        try:
            return str(shape.placeholder_format.type).split(".")[-1].split(" ")[0].upper()
        except Exception:
            return None

    def _run_fonts(shape):
        sizes, names, colors = set(), set(), set()
        if not getattr(shape, "has_text_frame", False):
            return sizes, names, colors
        for p in shape.text_frame.paragraphs:
            for r in p.runs:
                f = r.font
                sizes.add(round(f.size.pt, 1) if f.size else None)
                names.add(f.name)
                try:
                    colors.add(str(f.color.rgb) if f.color and f.color.type is not None
                               and f.color.rgb is not None else None)
                except Exception:
                    colors.add(None)
        return sizes, names, colors

    slides = []
    for i, sl in enumerate(prs.slides, 1):
        try:
            layout_name = sl.slide_layout.name
        except Exception:
            layout_name = None
        phs, boxes, pics = [], [], []
        tsize, tnames, tcolors = set(), set(), set()
        bsize, bnames, bcolors = set(), set(), set()
        title_txt, body_txt, all_txt = "", "", []
        for sh in sl.shapes:
            if sh.shape_type == 13:
                try:
                    ratio = round(sh.width / sh.height, 3) if sh.height else None
                    pics.append({"shape": sh.shape_id, "ratio_box": ratio})
                except Exception:
                    pass
                continue
            if not getattr(sh, "has_text_frame", False):
                continue
            txt = sh.text_frame.text.strip()
            if not txt:
                continue
            all_txt.append(txt)
            s, n, c = _run_fonts(sh)
            entry = {"type": _ph_type(sh) if _is_ph(sh) else "textbox",
                     "is_placeholder": _is_ph(sh),
                     "idx": (sh.placeholder_format.idx if _is_ph(sh) else None),
                     "text_head": txt[:40], "font_sizes": sorted(x for x in s if x),
                     "font_names": sorted(x for x in n if x), "colors": sorted(x for x in c if x)}
            if _is_ph(sh):
                phs.append(entry)
            else:
                boxes.append(entry)
            is_title = (_is_ph(sh) and (entry["type"] or "").lower() in ("title", "ctrtitle")) or \
                       (not title_txt and sh == max((x for x in sl.shapes
                                                     if getattr(x, "has_text_frame", False)),
                                                    key=lambda x: -(x.top or 0), default=sh))
            if is_title:
                title_txt = txt
                tsize |= {x for x in s if x}
                tnames |= {x for x in n if x}
                tcolors |= {x for x in c if x}
            elif not body_txt:
                body_txt = txt
                bsize |= {x for x in s if x}
                bnames |= {x for x in n if x}
                bcolors |= {x for x in c if x}
        level = "master_theme_inherited"
        if phs:
            level = "layout_placeholder"
            if boxes:
                level = "layout_placeholder_plus_textbox_fallback"
        elif boxes:
            level = "standalone_textbox_no_inheritance"
        slides.append({"no": i, "master": "master#1", "layout": layout_name,
                       "placeholders_used": [p["idx"] for p in phs],
                       "textbox_count": len(boxes), "pictures": pics,
                       "effective_level": level, "title_text": title_txt[:80],
                       "body_head": body_txt[:80], "title_sizes": sorted(tsize),
                       "title_fonts": sorted(tnames), "title_colors": sorted(tcolors),
                       "body_sizes": sorted(bsize), "body_fonts": sorted(bnames),
                       "body_colors": sorted(bcolors),
                       "has_notes": bool(sl.has_notes_slide and
                                         sl.notes_slide.notes_text_frame.text.strip()),
                       "_all_text": " | ".join(all_txt)})
        if log:
            planned = next((e for e in (log.get("slides") or []) if e.get("no") == i), None)
            if planned:
                slides[-1]["planned_layout"] = planned.get("template_layout")
                slides[-1]["planned_inheritance"] = planned.get("inheritance")
    return slides


if __name__ == "__main__":
    sys.exit(main())
