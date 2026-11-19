#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adapt_build.py — 按规格清单适配组稿（排得对的执行端）：sections → adapted.md + adapted.docx

合并 /app/work/sections/S##.json，机械应用 checklist 规格：
  · 标题按层级连续重编号（1 / 1.1 / 2 …）
  · 题注按模板前缀重编号（图1、表1…或 Figure 1.），正文交叉引用同步替换（同号唯一时才替换，歧义留痕）
  · docx 落页边距/栏数/字号/行距（sectPr + styles），模板规格可被 format_check 逐项复验
适配动作全部记录 adapt_log.json（applied_specs / renumber / crossref_fixes / skipped），可复核。
三级容错：python-docx → stdlib 最小合法 docx → 章节全坏时输出可编辑占位文档。退出码恒 0。
"""
import argparse, glob, json, os, re, sys, time, zipfile

try:
    import _rlog
except Exception:
    _rlog = None

TWIPS_PER_CM = 567.0


def load_sections(spec):
    draft, skipped = {"title": "", "meta": {}, "sections": [], "references": [], "notes_for_human": []}, []
    files = sorted(glob.glob(os.path.join(spec, "*.json")))
    if not files:
        skipped.append([spec, "no section json files found"])
        return draft, skipped
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            skipped.append([os.path.basename(fp), "unparseable: %s" % str(e)[:120]])
            continue
        if isinstance(d, list):
            d = {"sections": d}
        if d.get("title") and not draft["title"]:
            draft["title"] = d["title"]
        draft["meta"].update(d.get("meta") or {})
        refs = d.get("references") or []
        notes = d.get("notes_for_human") or []
        if "section" in d and isinstance(d["section"], dict):
            d["sections"] = [d["section"]]
        elif ("heading" in d or "paragraphs" in d) and "sections" not in d:
            d = {"sections": [d]}  # 直接的 section 对象（references/notes 在包装前已取出）
        secs = d.get("sections") or []
        if isinstance(secs, dict):
            secs = [secs]
        draft["sections"].extend(secs)
        draft["references"].extend(refs)
        draft["notes_for_human"].extend(notes)
    draft["sections"].sort(key=lambda s: str(s.get("order") or s.get("heading") or ""))
    return draft, skipped


SKIP_NUM = re.compile(r"^\s*(摘要|abstract|参考文献|references|致谢|acknowledg|附录|appendix)\s*\S*$", re.I)


def renumber_headings(sections, log):
    counters = []
    changed = []
    for s in sections:
        lvl = max(1, min(4, int(s.get("level") or 1)))
        old = s.get("heading", "")
        stripped = re.sub(r"^\s*(\d+(?:\.\d+)*)[、.\s]+", "", old)
        if SKIP_NUM.match(stripped):
            # 前置/后置章节（摘要/参考文献等）惯例不参与章节编号
            s["heading"] = stripped
            s.pop("_num", None)
            changed.append({"from": old, "to": stripped, "note": "unnumbered_section"})
            continue
        if lvl > len(counters):
            counters.extend([0] * (lvl - len(counters)))
        counters = counters[:lvl]
        counters[lvl - 1] += 1
        num = ".".join(str(c) for c in counters)
        s["heading"] = "%s %s" % (num, stripped)
        s["_num"] = num
        changed.append({"from": old, "to": s["heading"]})
    log["heading_renumber"] = changed
    return sections


def renumber_captions(sections, log):
    """题注重编号 + 正文交叉引用同步（同旧号在全文唯一出现时才替换，歧义留痕）。"""
    counters = {"fig": 0, "tab": 0}
    old_new = {"fig": {}, "tab": {}}
    log["caption_renumber"] = []
    # 1) 扫描旧题注号
    for s in sections:
        for p in s.get("paragraphs", []):
            if isinstance(p, dict) and p.get("type") in ("figure", "table"):
                kind = "fig" if p.get("type") == "figure" else "tab"
                m = re.match(r"^\s*\**\s*(图\s*\d+|表\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|Table\s*\d+)\b", str(p.get("caption", "")), re.I)
                if m:
                    kind = "fig" if re.match(r"图|Figure|Fig", m.group(1), re.I) else "tab"
                    old_new[kind][re.sub(r"\s+", "", m.group(1))] = None
    # 2) 重新编号
    for s in sections:
        for p in s.get("paragraphs", []):
            if isinstance(p, dict) and p.get("type") in ("figure", "table"):
                kind = "fig" if p.get("type") == "figure" else "tab"
                counters[kind] += 1
                cap = str(p.get("caption", ""))
                m = re.match(r"^(\s*\**\s*)(图\s*\d+|表\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|Table\s*\d+)(\b.*)$", cap, re.I)
                if m:
                    kind = "fig" if re.match(r"图|Figure|Fig", m.group(2), re.I) else "tab"
                    key = re.sub(r"\s+", "", m.group(2))
                    new = ("图%d" if kind == "fig" else "表%d") % counters[kind]
                    p["caption"] = m.group(1) + new + m.group(3)
                    old_new[kind][key] = new
                    log["caption_renumber"].append({"from": m.group(2).strip(), "to": new})
    # 3) 正文交叉引用同步（旧号全文唯一才替换）
    fixes, ambiguous = [], []
    body_src = json.dumps([s.get("paragraphs") for s in sections], ensure_ascii=False)
    for kind, mapping in old_new.items():
        for old, new in mapping.items():
            if not new or old == new:
                continue
            pat = re.compile(r"(?<![\dA-Za-z])" + re.escape(old) + r"(?![\dA-Za-z])")
            n = len(pat.findall(body_src))
            if n == 1:
                body_src = pat.sub(new, body_src, count=1)
                fixes.append({"from": old, "to": new, "occurrences": n})
            elif n > 1:
                ambiguous.append({"token": old, "occurrences": n, "note": "旧号多处出现，替换有歧义：留待人工确认，不机械替换"})
    try:
        new_paras = json.loads(body_src)
        for s, paras in zip(sections, new_paras):
            s["paragraphs"] = paras
    except Exception:
        pass
    log["crossref_fixes"] = fixes
    log["crossref_ambiguous"] = ambiguous
    return sections


def extract_specs(checklist):
    spec = {"margin_sides": {}, "margin_cm": None, "columns": None, "body_pt": None,
            "heading_pt": None, "line_multiple": None, "applied_ids": []}
    for it in (checklist.get("items") or []) + (checklist.get("defaulted") or []):
        num = it.get("numeric")
        if not num:
            continue
        cat = it.get("category")
        if cat == "margin":
            sides = num.get("sides") or ({"top": num.get("cm"), "bottom": num.get("cm"),
                                          "left": num.get("cm"), "right": num.get("cm")}
                                         if num.get("cm") else {})
            for k, v in sides.items():
                if v is not None and spec["margin_sides"].get(k) is None:
                    spec["margin_sides"][k] = float(v)
                    spec["applied_ids"].append(it.get("item_id"))
            continue
        if cat == "columns" and spec["columns"] is None:
            spec["columns"] = num.get("count"); spec["applied_ids"].append(it.get("item_id"))
        elif cat == "font_size":
            if it.get("scope") == "heading" and spec["heading_pt"] is None:
                spec["heading_pt"] = num.get("pt"); spec["applied_ids"].append(it.get("item_id"))
            elif it.get("scope") == "body" and spec["body_pt"] is None:
                spec["body_pt"] = num.get("pt"); spec["applied_ids"].append(it.get("item_id"))
        elif cat == "line_spacing" and spec["line_multiple"] is None:
            spec["line_multiple"] = num.get("pt") if num.get("unit") == "x" else num.get("pt")
            spec["applied_ids"].append(it.get("item_id"))
    if spec["margin_sides"]:
        spec["margin_cm"] = spec["margin_sides"].get("top")  # 兼容旧键
    return spec


def _sect_pr(spec):
    sides = spec.get("margin_sides") or {}
    default = spec.get("margin_cm") or 2.54
    tw = {k: int((sides.get(k) if sides.get(k) is not None else default) * TWIPS_PER_CM)
          for k in ("top", "bottom", "left", "right")}
    cols = spec.get("columns") or 1
    return ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="%d" w:bottom="%d" w:left="%d" w:right="%d" w:header="851" w:footer="992"/>'
            '<w:cols w:num="%d"/></w:sectPr>'
            % (tw["top"], tw["bottom"], tw["left"], tw["right"], cols))


def _min_docx(path, draft, spec):
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def p(text, style=None, bold=False, size=None):
        st = f'<w:pStyle w:val="{style}"/>' if style else ""
        rpr = ("<w:rPr>" + ("<w:b/>" if bold else "") +
               (f'<w:sz w:val="{size}"/>' if size else "") + "</w:rPr>") if (bold or size) else ""
        return (f'<w:p><w:pPr>{st}</w:pPr><w:r>{rpr}<w:t xml:space="preserve">'
                f"{esc(text)}</w:t></w:r></w:p>")

    body_pt = spec.get("body_pt")
    head_pt = spec.get("heading_pt") or (body_pt or 12) + 2
    body = [p(draft.get("title") or "(无题)", style="Title")]
    for sec in draft.get("sections", []):
        lvl = min(3, sec.get("level") or 1)
        body.append(p(sec.get("heading", ""), style=f"Heading{lvl}", size=int(head_pt * 2)))
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                body.append(p(para, size=int((body_pt or 12) * 2)))
            elif para.get("type") == "table":
                if para.get("caption"):
                    body.append(p(para["caption"], bold=True))
                rows = para.get("rows", [])
                if rows:
                    trs = []
                    for r in rows:
                        tcs = "".join(
                            f'<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">{esc(c)}</w:t></w:r></w:p></w:tc>'
                            for c in r)
                        trs.append(f"<w:tr>{tcs}</w:tr>")
                    body.append('<w:tbl><w:tblPr><w:tblBorders>'
                                + '<w:top w:val="single"/><w:left w:val="single"/>'
                                + '<w:bottom w:val="single"/><w:right w:val="single"/>'
                                + "</w:tblBorders></w:tblPr>" + "".join(trs) + "</w:tbl>")
                    body.append(p(""))
            elif para.get("type") == "figure":
                body.append(p("［图: " + para.get("caption", "") +
                              (f"（来源: {para.get('source_locator','')}）" if para.get("source_locator") else "")
                              + " — 请在 Word 中插入文件 " + para.get("path", "") + "］", bold=True))
    for r in draft.get("references") or []:
        body.append(p(r))
    for n in draft.get("notes_for_human") or []:
        body.append(p("［待人工确认］" + n, bold=True))
    spacing = ('<w:spacing w:line="%d" w:lineRule="auto"/>' % int((spec.get("line_multiple") or 1.0) * 240))
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}{_sect_pr(spec)}</w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:styles xmlns:w="{W}">'
              f'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="{int(16 * 2)}"/></w:rPr></w:style>'
              + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/>'
                        f'<w:pPr><w:outlineLvl w:val="{i-1}"/>{spacing}</w:pPr>'
                        f'<w:rPr><w:b/><w:sz w:val="{int(head_pt * 2)}"/></w:rPr></w:style>' for i in (1, 2, 3))
              + f'<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/>'
                f'<w:pPr>{spacing}</w:pPr><w:rPr><w:sz w:val="{int((body_pt or 12) * 2)}"/></w:rPr></w:style>'
              "</w:styles>")
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>")
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             "</Relationships>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", drels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
    return path


def build_markdown(draft, path):
    L = [f"# {draft.get('title') or '(无题)'}", ""]
    for sec in draft.get("sections", []):
        L.append("#" * min(6, (sec.get("level") or 1) + 1) + " " + sec.get("heading", ""))
        L.append("")
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                L.append(para); L.append("")
            elif para.get("type") == "table":
                if para.get("caption"):
                    L.append(f"**{para['caption']}**"); L.append("")
                rows = para.get("rows", [])
                if rows:
                    L.append("| " + " | ".join(str(c).replace("|", "\\|") for c in rows[0]) + " |")
                    L.append("|" + "---|" * len(rows[0]))
                    for r in rows[1:]:
                        L.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
                    L.append("")
            elif para.get("type") == "figure":
                cap = para.get("caption", "")
                L.append(f"![{cap}]({para.get('path','')})" if para.get("path") else f"[图缺失: {cap}]")
                L.append("")
                L.append(f"**{cap}**" + (f"（来源: {para.get('source_locator','')}）" if para.get("source_locator") else ""))
                L.append("")
        for c in sec.get("comments", []):
            L.append(f"> [审校备注] {c}"); L.append("")
    refs = draft.get("references") or []
    if refs:
        L.append("## 参考文献"); L.append("")
        for r in refs:
            L.append(r); L.append("")
    for n in draft.get("notes_for_human") or []:
        L.append(f"> [待人工确认] {n}"); L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections-dir", required=True)
    ap.add_argument("--checklist", required=True)
    ap.add_argument("--out-docx", default="/app/output/adapted.docx")
    ap.add_argument("--out-md", default="/app/output/adapted.md")
    ap.add_argument("--adapt-log", default="/app/work/adapt_log.json")
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()
    os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
    draft, skipped = load_sections(args.sections_dir)
    cl = {}
    try:
        cl = json.load(open(args.checklist, encoding="utf-8"))
    except Exception:
        pass
    log = {"applied_specs": [], "builder": None, "skipped": skipped}
    if not draft.get("sections"):
        draft["sections"] = [{"heading": "（空稿）", "level": 1,
                              "paragraphs": ["未合并到任何章节内容；请检查 sections 目录。"]}]
        log["note"] = "sections 为空：输出可编辑占位文档"
    spec = extract_specs(cl if isinstance(cl, dict) else {})
    log["applied_specs"] = spec.get("applied_ids") or []
    renumber_headings(draft["sections"], log)
    renumber_captions(draft["sections"], log)
    info = {}
    # 统一走 stdlib 精确 XML（可复验页边距/字号/行距），不依赖 python-docx 的默认节属性
    try:
        _min_docx(args.out_docx, draft, spec)
        info["builder"] = "stdlib-spec-docx"
    except Exception as e:
        info["builder"] = "failed"
        info["build_error"] = str(e)[:200]
    build_markdown(draft, args.out_md)
    info["markdown"] = args.out_md
    info["sections_merged"] = len(draft.get("sections", []))
    info["spec_applied"] = {k: v for k, v in spec.items() if k != "applied_ids"}
    info.update({k: log.get(k) for k in ("skipped", "note") if log.get(k)})
    if args.adapt_log:
        os.makedirs(os.path.dirname(args.adapt_log) or ".", exist_ok=True)
        try:
            json.dump(log, open(args.adapt_log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            info["log_error"] = str(e)[:200]
    print(json.dumps({"ok": info.get("builder") != "failed", **info}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("adapt_build", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"builder": info.get("builder"), "sections": info.get("sections_merged"),
                              "applied_specs": len(log.get("applied_specs") or [])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
