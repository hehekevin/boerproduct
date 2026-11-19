#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_build.py — 把结构化稿件构建为可编辑 Word（.docx）+ Markdown
支持两种输入（互斥）:
1) 单文件 draft.json:
{
  "title": "...", "meta": {...},
  "sections": [{"heading": "1 引言", "level": 1,
                "paragraphs": ["...", {"type":"table","caption":"...","rows":[[...]]},
                               {"type":"figure","caption":"...","path":"...","source_locator":"..."}],
                "comments": ["审校备注(可选)"]}],
  "references": ["[1] ..."], "notes_for_human": ["待人工确认"]
}
2) --sections-dir /app/work/sections：分章节小文件（防单响应截断）。
   扫描 S*.json / s*.json / *.section.json，按文件名排序合并；
   每个文件可含 {"title","meta","section":{...}} 或 {"sections":[...]} 或直接一个 section 对象；
   references/notes_for_human 数组跨文件拼接。任一文件损坏则跳过并记录（不阻塞其余章节）。

三级容错：python-docx 可用→真 docx；缺失→stdlib 最小合法 docx；JSON 全坏→输出仅含错误说明的可编辑文档。
"""
import argparse, glob, json, os, re, sys, zipfile, time

try:
    import _rlog
except Exception:
    _rlog = None


def load_sections(spec):
    """返回 (draft_dict, skipped:[文件名,原因])"""
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
        if "section" in d and isinstance(d["section"], dict):
            d["sections"] = [d["section"]]
        elif ("heading" in d or "paragraphs" in d) and "sections" not in d:
            d = {"sections": [d]}  # 直接的 section 对象
        secs = d.get("sections") or []
        if isinstance(secs, dict):
            secs = [secs]
        draft["sections"].extend(secs)
        draft["references"].extend(d.get("references") or [])
        draft["notes_for_human"].extend(d.get("notes_for_human") or [])
    draft["sections"].sort(key=lambda s: str(s.get("order") or s.get("heading") or ""))
    return draft, skipped


def _md_escape(s):
    return s.replace("|", "\\|")


def build_markdown(draft, path):
    L = [f"# {draft.get('title','(无题)')}", ""]
    for k, v in (draft.get("meta") or {}).items():
        L.append(f"- **{k}**: {v}")
    if draft.get("meta"):
        L.append("")
    for sec in draft.get("sections", []):
        L.append("#" * min(6, (sec.get("level") or 1) + 1) + " " + sec.get("heading", ""))
        L.append("")
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                L.append(para); L.append("")
            elif para.get("type") == "table":
                if para.get("caption"): L.append(f"**{para['caption']}**"); L.append("")
                rows = para.get("rows", [])
                if rows:
                    L.append("| " + " | ".join(_md_escape(str(c)) for c in rows[0]) + " |")
                    L.append("|" + "---|" * len(rows[0]))
                    for r in rows[1:]:
                        L.append("| " + " | ".join(_md_escape(str(c)) for c in r) + " |")
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
        for r in refs: L.append(r); L.append("")
    for n in draft.get("notes_for_human") or []:
        L.append(f"> [待人工确认] {n}"); L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path


def _min_docx(path, draft):
    """stdlib 兜底：生成合法可打开的最小 docx（标题+段落+表格）。"""
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    def p(text, style=None, bold=False, size=None):
        st = f'<w:pStyle w:val="{style}"/>' if style else ""
        rpr = ("<w:rPr>" + ("<w:b/>" if bold else "") +
               (f'<w:sz w:val="{size}"/>' if size else "") + "</w:rPr>") if (bold or size) else ""
        return (f'<w:p><w:pPr>{st}</w:pPr><w:r>{rpr}<w:t xml:space="preserve">'
                f"{esc(text)}</w:t></w:r></w:p>")
    body = [p(draft.get("title", ""), style="Title")]
    for sec in draft.get("sections", []):
        body.append(p(sec.get("heading", ""), style=f"Heading{min(3, sec.get('level') or 1)}"))
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                body.append(p(para))
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
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}'
                f'<w:sectPr/></w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:styles xmlns:w="{W}">'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
              + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:pPr><w:outlineLvl w:val="{i-1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="{32-4*i}"/></w:rPr></w:style>' for i in (1, 2, 3))
              + '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
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


def build_docx(draft, path):
    try:
        import docx  # type: ignore
        from docx.shared import Pt
        d = docx.Document()
        d.add_heading(draft.get("title", ""), 0)
        for k, v in (draft.get("meta") or {}).items():
            d.add_paragraph(f"{k}: {v}")
        for sec in draft.get("sections", []):
            d.add_heading(sec.get("heading", ""), min(4, sec.get("level") or 1))
            for para in sec.get("paragraphs", []):
                if isinstance(para, str):
                    d.add_paragraph(para)
                elif para.get("type") == "table":
                    if para.get("caption"):
                        d.add_paragraph(para["caption"])
                        if d.paragraphs[-1].runs:
                            d.paragraphs[-1].runs[0].bold = True
                    rows = para.get("rows", [])
                    if rows:
                        t = d.add_table(rows=len(rows), cols=len(rows[0]))
                        try:
                            t.style = "Table Grid"
                        except Exception:
                            pass
                        for i, r in enumerate(rows):
                            for j, c in enumerate(r):
                                t.cell(i, j).text = str(c)
                    d.add_paragraph("")
                elif para.get("type") == "figure":
                    cap = para.get("caption", "")
                    if para.get("path") and os.path.exists(para["path"]):
                        try:
                            d.add_picture(para["path"], width=Pt(360))
                        except Exception:
                            pass
                    pp = d.add_paragraph(cap if not para.get("source_locator") else f"{cap}（来源: {para['source_locator']}）")
                    if pp.runs: pp.runs[0].bold = True
            for c in sec.get("comments", []):
                pp = d.add_paragraph("[审校备注] " + c)
                if pp.runs: pp.runs[0].italic = True
        for r in draft.get("references") or []:
            d.add_paragraph(r)
        for n in draft.get("notes_for_human") or []:
            pp = d.add_paragraph("[待人工确认] " + n)
            if pp.runs: pp.runs[0].bold = True
        d.save(path)
        return {"builder": "python-docx", "file": path}
    except Exception as e:
        _min_docx(path, draft)
        return {"builder": "stdlib-min-docx(fallback)", "file": path, "reason": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft_json", nargs="?", default=None, help="单文件 draft.json（与 --sections-dir 二选一）")
    ap.add_argument("--sections-dir", default=None, help="分章节目录（S*.json，按名合并）")
    ap.add_argument("--out-docx", default="/app/output/draft.docx")
    ap.add_argument("--out-md", default="/app/output/draft.md")
    args = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
    skipped = []
    if args.sections_dir:
        draft, skipped = load_sections(args.sections_dir)
    elif args.draft_json:
        try:
            draft = json.load(open(args.draft_json, encoding="utf-8"))
        except Exception as e:
            draft = {"title": "（构建失败，原文档无法解析）", "sections": [{"heading": "说明", "level": 1,
                     "paragraphs": ["draft.json 解析失败: %s。请修复后重跑；本文档为可编辑占位。" % str(e)[:200]]}]}
            skipped.append([args.draft_json, "unparseable"])
    else:
        draft = {"title": "（无输入）", "sections": [{"heading": "说明", "level": 1,
                 "paragraphs": ["未提供 draft_json 或 --sections-dir。"]}]}
    if not draft.get("sections"):
        draft.setdefault("sections", [{"heading": "（空稿）", "level": 1,
                                       "paragraphs": ["未合并到任何章节内容；请检查 sections 目录。"]}])
    info = build_docx(draft, args.out_docx)
    build_markdown(draft, args.out_md)
    info["markdown"] = args.out_md
    info["sections_merged"] = len(draft.get("sections", []))
    if skipped:
        info["skipped"] = skipped
    print(json.dumps({"ok": True, **info}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("docx_build", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"builder": info.get("builder"), "sections_merged": info.get("sections_merged"),
                              "skipped": len(info.get("skipped") or [])})
    return 0


if __name__ == "__main__":
    sys.exit(main())
