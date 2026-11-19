#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_template.py — 模板识别（认得准）：从模板/格式要求文件抽取可逐项核对的规格清单

扫描 /input 下模板与格式要求材料（md/txt/docx/task.md），逐行规则抽取：
  页边距/栏数/字号(正文·标题·题注)/行距/标题层级与字体/图表题注(位置·前缀·三线表)/
  参考文献样式/导出格式/摘要字数/必需章节
每个条目带来源锚点 {file,line,quote}，可逐条回溯；同一类目不同来源值不一致 → conflicts。
模板文件缺失时回退 task.md；再无则只产 defaulted 通用项并如实标注，不硬凑规格。

输出 checklist.json：{items, conflicts, required_sections, sources, gates, note}
退出码恒 0：识别失败/文件不可读如实写入 gates，不阻断交付。
"""
import argparse, json, os, re, sys, time, zipfile

try:
    import _rlog
except Exception:
    _rlog = None

ZH_SIZE = {"二号": 22, "小二": 18, "三号": 16, "小三": 15, "四号": 14, "小四": 12,
           "五号": 10.5, "小五": 9, "六号": 7.5}

# 页边距专用：按边独立抽取，避免「上下/左右」混在同一行时漏抓；sides 记录适用的边
MARGIN_PATS = [
    (r"(?:上下|上下边距|top\s*(?:and|/)\s*bottom)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("top", "bottom")),
    (r"(?:左右|左右边距|left\s*(?:and|/)\s*right)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("left", "right")),
    (r"(?:上|top)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("top",)),
    (r"(?:下|bottom)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("bottom",)),
    (r"(?:左|left)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("left",)),
    (r"(?:右|right)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("right",)),
    (r"(?:页边距|margins?)[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*cm", ("top", "bottom", "left", "right")),
]

# (类目, 名称, checkable, check_type, [正则...])  —— 正则第一个捕获组=值
RULES = [
    ("columns", "栏数", "docx", "enum",
     [r"双栏|两栏|two[- ]column|double[- ]column", r"单栏|one[- ]column|single[- ]column", r"栏数[:：]?\s*([12])"]),
    ("font_size", "正文字号", "docx", "numeric",
     [r"(?:正文|body(?:\s*text)?|行文)[^\d\n。;；]{0,12}([0-9]+(?:\.[0-9]+)?)\s*(?:pt|磅)",
      r"(?:正文|body)[\u4e00-\u9fff]{0,8}(小四|五号|小五|四号|三号|小二|二号)",
      r"(?:正文字体|中文字体)[^\d\n。;；]{0,10}(小四|五号|小五|四号|三号)"]),
    ("font_size", "标题字号", "docx", "numeric",
     [r"(?:标题|heading|题目)[^\d\n。;；]{0,14}([0-9]+(?:\.[0-9]+)?)\s*(?:pt|磅)",
      r"(?:各级标题|标题)[\u4e00-\u9fff]{0,10}(小四|四号|三号|小三|小二|二号)"]),
    ("line_spacing", "行距", "docx", "numeric",
     [r"([0-9]+(?:\.[0-9]+)?)\s*倍(?:行距)?", r"行距[^\d\n]{0,6}([0-9]+(?:\.[0-9]+)?)\s*(?:倍|磅)"]),
    ("caption", "图表题注", "md", "pattern",
     [r"(图|表|Figure|Fig\.?|Table)\s*[0-9]+\s*(?:题(?:注|目)?|caption|说明)[^\n。;；]{0,20}(?:在|位于)?\s*(下方|下|上方|上|below|above)",
      r"题注[^\n。;；]{0,24}", r"三线表", r"图表题注[^\n。;；]{0,24}"]),
    ("caption", "题注前缀", "md", "pattern",
     [r"(?:编号|前缀|标注)[^\n。;；]{0,10}(图\s*[0-9]+|Figure\s*[0-9]+|Fig\.\s*[0-9]+|表\s*[0-9]+|Table\s*[0-9]+)",
      r"(?:采用|使用|格式为)[^\n。;；]{0,6}(图\s*[0-9]+|Figure\s*[0-9]+|表\s*[0-9]+|Table\s*[0-9]+)"]),
    ("citation", "参考文献样式", "md", "enum",
     [r"GB\s*/?\s*T\s*7714", r"顺序编码制", r"著者[-—-]出版年", r"APA", r"Vancouver", r"IEEE",
      r"参考文献(?:格式|样式)[^\n。;；]{0,20}"]),
    ("export", "导出格式", "process", "record",
     [r"(?:导出|交付|提交)(?:格式)?[^\n。;；]{0,24}(?:PDF|DOCX|DOC|Word|LaTeX)"]),
    ("abstract", "摘要字数", "md", "numeric",
     [r"摘要[^\d\n。;；]{0,20}([0-9]{2,4})\s*[~～\-—到]{0,2}\s*([0-9]{2,4})?\s*(?:字|词)"]),
]

SECTION_KEYS = [
    ("摘要", r"摘要|Abstract"), ("引言", r"引言|绪论|Introduction"),
    ("文献综述", r"文献综述|相关工作|Related\s*Work"), ("材料与方法", r"材料与方法|方法|Methods?"),
    ("结果", r"结果|Results?"), ("讨论", r"讨论|Discussion"),
    ("结论", r"结论|Conclusion"), ("参考文献", r"参考文献|References"),
    ("附录", r"附录|Appendix"), ("致谢", r"致谢|Acknowledg"),
]


def docx_text(path):
    """stdlib 解 docx 文本（按 </w:p> 断行）；失败返回 None。"""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        lines = [re.sub(r"<[^>]+>", "", p) for p in xml.split("</w:p>")]
        return "\n".join(l for l in lines if l.strip())
    except Exception:
        return None


def read_sources(indir):
    """收集候选模板来源：文件名含模板/template/格式/要求/规范 的文件 + task.md + case.json。"""
    srcs = []
    for root, _, fs in os.walk(indir):
        for f in sorted(fs):
            low = f.lower()
            fp = os.path.join(root, f)
            if low.endswith((".md", ".txt")) or low.endswith(".docx"):
                tag = "template" if re.search(r"模板|template|格式|要求|规范|style|guide", f, re.I) else "material"
                if tag == "template" or low in ("task.md", "readme.md"):
                    srcs.append((fp, tag))
            elif low == "case.json":
                srcs.append((fp, "case"))
    return srcs


def zh2pt(name):
    return ZH_SIZE.get(name)


def scan_margin(line, fname, lineno):
    """页边距按边独立抽取；已被更宽模式覆盖的匹配不重复登记。"""
    items, spans = [], []
    for pat, sides in MARGIN_PATS:
        m = re.search(pat, line, re.I)
        if not m:
            continue
        if any(m.start() < e and m.end() > s for s, e in spans):
            continue
        spans.append((m.start(), m.end()))
        try:
            v = float(m.group(1))
        except Exception:
            continue
        items.append({
            "category": "margin", "name": "页边距(%s)" % "/".join(sides), "checkable": "docx",
            "check_type": "numeric",
            "template_value": re.sub(r"\s+", " ", m.group(0)).strip()[:80],
            "numeric": {"sides": {s: v for s in sides}}, "scope": None,
            "source": {"file": fname, "line": lineno, "quote": line.strip()[:80]},
        })
    return items


def scan_text(text, fname):
    items, lines = [], text.splitlines()
    for i, line in enumerate(lines, 1):
        items.extend(scan_margin(line, fname, i))
        for cat, name, checkable, ctype, pats in RULES:
            for pat in pats:
                m = re.search(pat, line, re.I)
                if not m:
                    continue
                val = m.group(0)
                numeric = None
                try:
                    if cat == "margin":
                        numeric = {"cm": float(m.group(1))}
                    elif cat in ("font_size", "line_spacing"):
                        g = m.group(1)
                        numeric = {"pt": zh2pt(g)} if not re.match(r"^[0-9.]+$", g) else (
                            {"pt": float(g), "unit": "pt" if "pt" in val or "磅" in val else "x" if ctype == "numeric" and "倍" in val else "pt"})
                    elif cat == "columns":
                        numeric = {"count": 2 if re.search(r"双栏|两栏|two|double|[2２]", val, re.I) else 1}
                    elif cat == "abstract":
                        lo = int(m.group(1))
                        hi = int(m.group(2)) if m.group(2) else lo
                        if re.search(r"不超过|不多于|不超过|少于|至多|≤|within", val, re.I):
                            lo = 0
                        numeric = {"min": lo, "max": hi}
                except Exception:
                    numeric = None
                items.append({
                    "category": cat, "name": name, "checkable": checkable, "check_type": ctype,
                    "template_value": re.sub(r"\s+", " ", val).strip()[:80],
                    "numeric": numeric,
                    "scope": ("heading" if "标题" in name else "body" if cat == "font_size" else None),
                    "source": {"file": fname, "line": i, "quote": line.strip()[:80]},
                })
                break
    return items


def extract(indir, case):
    srcs = read_sources(indir)
    all_items, sources, unreadable = [], [], []
    for fp, tag in srcs:
        fname = os.path.basename(fp)
        text = None
        try:
            if fp.endswith(".docx"):
                text = docx_text(fp)
            elif fp.endswith(".json"):
                obj = json.load(open(fp, encoding="utf-8"))
                text = json.dumps(obj, ensure_ascii=False)
            else:
                text = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception as e:
            unreadable.append({"file": fname, "error": str(e)[:120]})
        if not text:
            continue
        sources.append({"file": fname, "tag": tag})
        all_items.extend(scan_text(text, fname))
        if tag == "case" and isinstance(case, dict):
            for k in ("format_requirements", "template", "format"):
                v = case.get(k)
                if isinstance(v, (dict, list, str)):
                    all_items.extend(scan_text(json.dumps(v, ensure_ascii=False), "case.json:%s" % k))
    # 依赖 default 的通用项（如实标注 defaulted）
    req = []
    corpus = "\n".join((open(fp, encoding="utf-8", errors="ignore").read()
                        if not fp.endswith((".docx", ".json")) else (docx_text(fp) or ""))
                       for fp, _ in srcs if os.path.exists(fp))
    for label, pat in SECTION_KEYS:
        if re.search(pat, corpus or "", re.I):
            req.append(label)
    defaulted = []
    if req:
        defaulted.append({"category": "sections", "name": "必需章节", "checkable": "md",
                          "check_type": "list", "template_value": req, "numeric": None, "scope": None,
                          "source": {"file": "task.md/materials", "line": None, "quote": "由材料语料中出现顺序推导"}})
    # 冲突检测：同类目+同 scope，数值不同
    conflicts = []
    groups = {}
    for it in all_items:
        if it["numeric"] is None:
            continue
        key = (it["category"], it["scope"])
        groups.setdefault(key, []).append(it)
    for (cat, scope), its in groups.items():
        if cat == "margin":
            # 页边距按边组合分组：上下 与 左右 是不同规格，不是冲突；同边数值不一致才是冲突
            by_sides = {}
            for i in its:
                key = tuple(sorted((i["numeric"].get("sides") or {}).keys()))
                by_sides.setdefault(key, []).append(i)
            for key, grp in by_sides.items():
                vals = {json.dumps(i["numeric"]["sides"], sort_keys=True) for i in grp}
                if len(vals) > 1:
                    conflicts.append({"category": cat, "scope": "/".join(key),
                                      "variants": [{"value": i["numeric"]["sides"], "source": i["source"]} for i in grp],
                                      "note": "同一边的页边距数值不一致：以任务指定口径优先，否则并列记录并列入 uncertainty"})
            continue
        vals = {json.dumps(i["numeric"], sort_keys=True) for i in its}
        if len(vals) > 1:
            conflicts.append({"category": cat, "scope": scope,
                              "variants": [{"value": i["numeric"], "source": i["source"]} for i in its],
                              "note": "不同来源规格冲突：以任务指定口径优先，否则并列记录并列入 uncertainty"})
    # 统一编号：items + defaulted 逐条 item_id，供 adapt_build/format_check/gain_evidence 引用
    for i, it in enumerate(all_items + defaulted, 1):
        it.setdefault("item_id", "F%02d" % i)
    return {"items": all_items, "defaulted": defaulted, "conflicts": conflicts,
            "required_sections": req, "sources": sources, "unreadable": unreadable}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/work/checklist.json")
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()
    case = {}
    try:
        case = json.load(open(args.case, encoding="utf-8"))
    except Exception:
        case = {}
    gates = {"input_dir": "enforced" if os.path.isdir(args.input) else "not_found"}
    if not os.path.isdir(args.input):
        cl = {"items": [], "defaulted": [], "conflicts": [], "required_sections": [],
              "sources": [], "unreadable": [{"file": args.input, "error": "input dir not found"}],
              "gates": gates, "note": "输入目录不存在：未识别到任何模板规格，下游不得宣称已核对。"}
    else:
        cl = extract(args.input, case)
        gates["template_found"] = "enforced" if cl["sources"] else "not_found"
        gates["items_extracted"] = "enforced" if cl["items"] else ("defaulted_only" if cl["defaulted"] else "not_found")
        gates["unreadable_sources"] = cl["unreadable"] or None
        cl["gates"] = gates
        cl["note"] = ("规格条目均可按 source{file,line,quote} 回溯；conflicts 需人工裁决后写入 uncertainty；"
                      "defaulted 条目为材料推导默认值，非模板明文。")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    try:
        json.dump(cl, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out_ok = True
    except Exception as e:
        out_ok = False
        cl["write_error"] = str(e)[:200]
    print(json.dumps({"ok": out_ok, "items": len(cl.get("items") or []),
                      "defaulted": len(cl.get("defaulted") or []), "conflicts": len(cl.get("conflicts") or []),
                      "required_sections": cl.get("required_sections") or [], "out": args.out}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("extract_template", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"items": len(cl.get("items") or []), "conflicts": len(cl.get("conflicts") or [])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
