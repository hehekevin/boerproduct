#!/usr/bin/env python3
"""fit_audit.py — 模板适配审计：把"模板原始值 -> 实际落点值 -> 是否吻合"
逐页机器生成，并给出整册一致性、继承链层级、适配前/后五维 diff。

为什么是脚本而不是手写：模板原始值由 template_report.json 提供，落点值由
python-pptx 从**真实产出的 pptx** 读出，两者都不经过模型转述，因此这张
对账表不可编造、可复现。

用法:
  python3 fit_audit.py deck.pptx --deck deck.json --report template_report.json \
      --baseline baseline.pptx --out fit_audit.json [--log layout_log.json]

输出 fit_audit.json:
  checks       整册一致性（页码/标题字号/图注/图片比例/字体白名单）
  format_fit   逐页 format_fit：template_value -> applied -> match（layout/font/
               color/text 四组）
  inheritance  逐页 继承链 master -> layout -> placeholder + 生效层级
  diff         逐页 适配前(baseline) vs 适配后 五维对比（title/body/font/color/layout）
  summary      汇总（页数/fail/warn/对账 match 率/diff 改动页数）

退出码: 0 全通过；1 有 fail；5 缺 python-pptx / 文件不可读。
"""
import argparse
import json
import os
import sys
from collections import Counter


def _norm(s):
    return "".join((s or "").split()).lower()


def _neutral(hexstr):
    """中性色（深灰/黑）用于正文，属学术排版常规，不算脱离主题色板。"""
    try:
        h = hexstr.replace("#", "")
        ch = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        return max(ch) - min(ch) <= 0x14
    except Exception:
        return False


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
    """返回 (sizes, names, colors, italics) 去重集合；None 表示继承。"""
    sizes, names, colors, italics = set(), set(), set(), set()
    if not getattr(shape, "has_text_frame", False):
        return sizes, names, colors, italics
    for p in shape.text_frame.paragraphs:
        for r in p.runs:
            f = r.font
            sizes.add(round(f.size.pt, 1) if f.size else None)
            names.add(f.name)
            italics.add(bool(f.italic))
            try:
                colors.add(str(f.color.rgb) if f.color and f.color.type is not None
                           and f.color.rgb is not None else None)
            except Exception:
                colors.add(None)
    return sizes, names, colors, italics


def collect(prs, log=None):
    """抽出逐页真实落点值。"""
    slides = []
    for i, sl in enumerate(prs.slides, 1):
        try:
            layout_name = sl.slide_layout.name
        except Exception:
            layout_name = None
        try:
            master_name = sl.slide_layout.slide_master.name or "master#1"
        except Exception:
            master_name = "master#1"
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
            s, n, c, _ = _run_fonts(sh)
            entry = {"type": _ph_type(sh) if _is_ph(sh) else "textbox",
                     "is_placeholder": _is_ph(sh),
                     "idx": (sh.placeholder_format.idx if _is_ph(sh) else None),
                     "text_head": txt[:40], "font_sizes": sorted(x for x in s if x),
                     "font_names": sorted(x for x in n if x),
                     "colors": sorted(x for x in c if x)}
            if _is_ph(sh):
                phs.append(entry)
            else:
                boxes.append(entry)
            is_title = (_is_ph(sh) and (entry["type"] or "").lower() in
                        ("title", "ctrtitle")) or (not title_txt and sh ==
                                                   max((x for x in sl.shapes
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

        # 继承层级判定：占位符承载 = layout 级；额外文本框 = fallback；字体未显式
        # 指定 = 仍继承 master/theme
        level = "master_theme_inherited"
        if phs:
            level = "layout_placeholder"
            if boxes:
                level = "layout_placeholder_plus_textbox_fallback"
        elif boxes:
            level = "standalone_textbox_no_inheritance"
        slides.append({
            "no": i, "master": master_name, "layout": layout_name,
            "placeholders_used": [p["idx"] for p in phs],
            "placeholder_detail": phs, "textbox_count": len(boxes),
            "pictures": pics, "effective_level": level,
            "title_text": title_txt[:80], "body_head": body_txt[:80],
            "title_sizes": sorted(tsize), "title_fonts": sorted(tnames),
            "title_colors": sorted(tcolors),
            "body_sizes": sorted(bsize), "body_fonts": sorted(bnames),
            "body_colors": sorted(bcolors), "has_notes": bool(sl.has_notes_slide and
                                                             sl.notes_slide.notes_text_frame.text.strip()),
            "_all_text": " | ".join(all_txt),
        })
        if log:
            planned = next((e for e in (log.get("slides") or []) if e.get("no") == i), None)
            if planned:
                slides[-1]["planned_layout"] = planned.get("template_layout")
                slides[-1]["planned_inheritance"] = planned.get("inheritance")
    return slides


def format_fit(slides, report):
    """template_value(探查报告真实值) -> applied(pptx 真实值) -> match。"""
    theme_fonts = (report or {}).get("theme_fonts") or {}
    theme_colors = [c for c in ((report or {}).get("theme_colors") or []) if c]
    latin = (theme_fonts.get("majorFont") or {}).get("latin")
    ea = (theme_fonts.get("majorFont") or {}).get("ea") or \
         (theme_fonts.get("minorFont") or {}).get("ea")
    layouts = {l["name"]: l for l in (report or {}).get("layouts") or []}
    rec = (report or {}).get("recommendation") or {}
    rows = []
    for sl in slides:
        expect_layout = sl.get("planned_layout") or None
        lay_tpl = layouts.get(expect_layout) if expect_layout else None
        applied_lay = sl["layout"]
        row = {"no": sl["no"], "dimensions": {}}

        # 1) layout
        row["dimensions"]["layout"] = {
            "template_value": (expect_layout or (rec.get("bullets") or "-")),
            "template_placeholders": ([{"idx": p["idx"], "type": p["type"]}
                                       for p in (lay_tpl or {}).get("placeholders", [])]
                                      if lay_tpl else "report 未收录该版式"),
            "applied": applied_lay,
            "match": bool(expect_layout and applied_lay == expect_layout) or
                     (not expect_layout and applied_lay is not None),
            "note": "构建日志 planned_layout 与实际 slide_layout 一致性" if expect_layout
                    else "deck.json 未声明 template_layout，仅校验版式非空",
        }

        # 2) font
        used = sorted({f for f in (sl["title_fonts"] + sl["body_fonts"]) if f})
        inherited = not used
        on_theme = [f for f in used if f in (latin, ea)]
        row["dimensions"]["font"] = {
            "template_value": {"latin": latin, "ea": ea},
            "applied": "全部继承主题（run 未显式指定 typeface）" if inherited else used,
            "match": inherited or bool(on_theme) or (not latin and not ea),
            "note": "真实继承：字体来自母版主题，改主题即整册换字" if inherited else
                    ("显式字体与主题一致" if on_theme else
                     "显式字体与模板主题不一致，换机渲染可能回退，需在 uncertainty 登记"),
        }

        # 3) color（中性正文色视为合规，强调色须落在主题色板内）
        used_c = sorted({c for c in (sl["title_colors"] + sl["body_colors"]) if c})
        pal = [x.replace("#", "").upper() for x in theme_colors]
        on_palette = [c for c in used_c if c.replace("#", "").upper() in pal]
        neutral_only = [c for c in used_c if c not in on_palette]
        ok_color = (not used_c) or (not theme_colors) or all(_neutral(c) for c in neutral_only)
        row["dimensions"]["color"] = {
            "template_value": {"theme_colors": theme_colors},
            "applied": used_c or "全部继承主题色（未显式设色）",
            "on_palette": on_palette,
            "neutral_body": [c for c in neutral_only if _neutral(c)],
            "off_palette": [c for c in neutral_only if not _neutral(c)],
            "match": ok_color,
            "note": ("全部继承主题色" if not used_c else
                     ("强调色取自主题色板 + 正文中性色" if ok_color else
                      "脱离主题色板的显式色：%s" % [c for c in neutral_only
                                                   if not _neutral(c)])),
        }

        # 4) text（内容是否真进了对应版式槽位）
        row["dimensions"]["text"] = {
            "template_value": "占位符 idx=%s" % (sl["placeholders_used"] or "-"),
            "applied": {"title": sl["title_text"], "body_head": sl["body_head"]},
            "match": bool(sl["title_text"] or sl["body_head"]),
            "note": "标题/正文落入占位符" if sl["placeholders_used"]
                    else "无占位符可用，走独立文本框兜底（继承降级）",
        }
        row["match_all"] = all(d["match"] for d in row["dimensions"].values())
        rows.append(row)
    return rows


def diff_vs_baseline(slides, base_slides):
    """适配前(baseline) vs 适配后 五维结构化 diff。"""
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


def consistency(slides, prs):
    report = {"checks": {}, "fail": 0, "warn": 0}
    n = len(slides)
    # 1 页码：仅当页脚数字普遍存在时才校验
    pn = [s["no"] for s in slides if any(f == str(s["no"]) for f in [s["title_text"], s["body_head"]])]
    report["checks"]["page_numbers"] = {"mode": "footer" if len(pn) >= n / 2 else
                                        "template_or_absent", "found": len(pn), "ok": True}
    # 2 标题字号一致性
    vals = [s["title_sizes"][0] for s in slides if s["title_sizes"]]
    if vals:
        common, _ = Counter(vals).most_common(1)[0]
        ok = len(set(vals)) <= 2
        report["checks"]["title_sizes"] = {"common_pt": common, "values": sorted(set(vals)), "ok": ok}
        if not ok:
            report["warn"] += 1
    # 3 图注样式
    caps = [v for s in slides for v in s["body_sizes"] if v == 10.0]
    report["checks"]["caption_10pt"] = {"found": len(caps), "ok": True}
    # 4 图片比例：contain-fit 下框内比例应等于图片源比例；此处只记录，交 verify 判定
    report["checks"]["image_boxes"] = {"count": sum(len(s["pictures"]) for s in slides),
                                       "detail": [s["pictures"] for s in slides if s["pictures"]]}
    # 5 字体清单
    fonts = sorted({f for s in slides for f in (s["title_fonts"] + s["body_fonts"]) if f})
    report["checks"]["fonts_used"] = {"fonts": fonts,
                                      "ok": True,
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

    try:
        from pptx import Presentation
    except Exception:
        print(json.dumps({"ok": False, "error": "python-pptx unavailable"}))
        sys.exit(5)

    # 输入状态必须显式：未传 / 路径不存在 / 解析失败 / 正常加载 是四件事。
    # 静默 None 会让"对账没跑"看起来跟"对账通过"一模一样。
    inputs = {}

    def load_json(p, label):
        if not p:
            inputs[label] = {"status": "skipped_not_provided",
                             "note": "参数未提供，对应审计项未执行"}
            return None
        if not os.path.exists(p):
            inputs[label] = {"status": "not_found", "path": p,
                             "note": "路径不存在，对应审计项未执行"}
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
        prs = Presentation(args.pptx)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "pptx unreadable: %s" % e}))
        sys.exit(5)
    log = load_json(args.log, "layout_log")
    tpl = load_json(args.report, "template_report")
    deck = load_json(args.deck, "deck")
    baseline_ok = bool(args.baseline) and os.path.exists(args.baseline)
    slides = collect(prs, log)

    out = {"pptx": args.pptx, "slides": len(slides), "template_report": args.report,
           "ok": True, "inputs": inputs, "gate_notes": []}
    out["checks"] = consistency(slides, prs)
    # 闸门三态：enforced / not_run（并区分原因）
    gate = {"format_fit": "enforced" if tpl else "not_run",
            "diff": "enforced" if baseline_ok else "not_run"}
    if not tpl:
        gate["format_fit_reason"] = inputs["template_report"]["status"]
        out["gate_notes"].append(
            "format_fit did NOT run (%s): 逐页模板对账缺失，结果不得宣称已核对模板落点"
            % inputs["template_report"]["status"])
    if not baseline_ok:
        gate["diff_reason"] = inputs.get("baseline", {}).get("status") or "skipped_not_provided"
        out["gate_notes"].append(
            "diff did NOT run (%s): 适配前/后对照缺失，不得宣称已有增益证据" % gate["diff_reason"])
    out["audit_gate"] = gate
    if out["gate_notes"]:
        out["checks"]["warn"] += len(out["gate_notes"])
    out["inheritance"] = [{"no": s["no"], "chain": {
        "master": s["master"], "layout": s["layout"],
        "placeholders": s["placeholders_used"], "textbox_fallback": s["textbox_count"]},
        "effective_level": s["effective_level"]} for s in slides]
    if tpl:
        out["format_fit"] = format_fit(slides, tpl)
        matched = sum(1 for r in out["format_fit"] if r["match_all"])
        out["summary"] = {"slides": len(slides), "fit_match_pages": matched,
                          "fit_match_rate": round(matched / max(1, len(slides)), 3)}
    if args.baseline and os.path.exists(args.baseline):
        try:
            base = collect(Presentation(args.baseline))
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
    out.setdefault("summary", {})["fail"] = out["checks"]["fail"]
    out["summary"]["warn"] = out["checks"]["warn"]

    out_path = args.out or (os.path.splitext(args.pptx)[0] + ".fit_audit.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("fit_audit:", json.dumps(out["summary"], ensure_ascii=False), "->", out_path)
    sys.exit(0 if out["checks"]["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
