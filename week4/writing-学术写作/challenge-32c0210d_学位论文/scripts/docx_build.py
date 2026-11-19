#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_build.py — 把结构化稿件 JSON 构建为可编辑 Word（.docx）+ Markdown
输入 draft 结构（draft.json）:
{
  "title": "...", "meta": {...},
  "sections": [
     {"heading": "1 引言", "level": 1,
      "paragraphs": ["...文本...", {"type":"table","caption":"表1 ...","rows":[[...],[...]]},
                     {"type":"figure","caption":"图1 ...","path":"fig1.png","source_locator":"Fig.1 p.3"}],
      "comments": ["审校备注(可选)"]}
  ],
  "references": ["[1] ...", "[2] ..."],
  "notes_for_human": ["需要人工确认的事项"]
}
输出: draft.docx（python-docx 可用则真 docx；缺失时 stdlib 兜底生成合法最小 docx）+ draft.md
始终同步产出 Markdown 版本（作者可直接编辑复核）。
"""
import argparse, json, os, re, sys, zipfile

def _md_escape(s):
    return s.replace("|", "\\|")

def build_markdown(draft, path):
    L = [f"# {draft.get('title','(无题)')}", ""]
    meta = draft.get("meta") or {}
    if meta:
        for k, v in meta.items():
            L.append(f"- **{k}**: {v}")
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
                src = para.get("source_locator", "")
                L.append(f"![{cap}]({para.get('path','')})" if para.get("path") else f"[图缺失: {cap}]")
                L.append("")
                L.append(f"**{cap}**" + (f"（来源: {src}）" if src else ""))
                L.append("")
        for c in sec.get("comments", []):
            L.append(f"> [审校备注] {c}")
            L.append("")
    refs = draft.get("references") or []
    if refs:
        L.append("## 参考文献"); L.append("")
        for r in refs: L.append(r); L.append("")
    for n in draft.get("notes_for_human") or []:
        L.append(f"> [待人工确认] {n}"); L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path

def _normalize(draft):
    """兼容两种输入形态：
      A) 完整稿 {"title","meta","sections":[...],"references":[...],"notes_for_human":[...]}
      B) 逐章稿 {"title","chapters":[{"ch","title","text"/"paragraphs"}],"references":[...]}
    统一转成 A 的 sections 形态，保证 SKILL.md 的 draft_all.json 与本脚本真正接上线。
    """
    if not isinstance(draft, dict):
        return {"title": "", "sections": []}
    if isinstance(draft.get("sections"), list):
        return draft
    chapters = draft.get("chapters") or draft.get("chapter_drafts") or []
    sections = []
    for c in chapters:
        if not isinstance(c, dict):
            continue
        heading = ("%s %s" % (str(c.get("ch") or "").strip(),
                              str(c.get("title") or "").strip())).strip() or str(c.get("title") or "")
        paras = []
        body = c.get("text") or c.get("content") or ""
        if isinstance(body, str):
            paras = [b for b in body.split("\n\n") if b.strip()]
        elif isinstance(body, list):
            paras = body
        elif isinstance(c.get("paragraphs"), list):
            paras = c["paragraphs"]
        sections.append({"heading": heading, "level": 1, "paragraphs": paras,
                         "comments": c.get("comments") or []})
    out = dict(draft)
    out["sections"] = sections
    out.setdefault("references", draft.get("references") or [])
    out.setdefault("notes_for_human", draft.get("notes_for_human") or draft.get("needs_human") or [])
    return out


def _min_docx(path, draft):
    """stdlib 兜底：生成合法可打开的最小 docx（标题+段落+表格）。"""
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    def p(text, style=None, bold=False, size=None):
        st = f'<w:pStyle w:val="{style}"/>' if style else ""
        rpr = ("<w:rPr>" + ("<w:b/>" if bold else "") +
               (f'<w:sz w:val="{size}"/>' if size else "") + "</w:rPr>") if (bold or size) else ""
        return (f'<w:p><w:pPr>{st}</w:pPr><w:r>{rpr}<w:t xml:space="preserve">'
                f"{text}</w:t></w:r></w:p>")
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
                    for i, r in enumerate(rows):
                        tcs = "".join(
                            f'<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">{c}</w:t></w:r></w:p></w:tc>'
                            for c in r)
                        trs.append(f"<w:tr>{tcs}</w:tr>")
                    body.append(f'<w:tbl><w:tblPr><w:tblBorders>'
                                + '<w:top w:val="single"/><w:left w:val="single"/>'
                                + '<w:bottom w:val="single"/><w:right w:val="single"/>'
                                + "</w:tblBorders></w:tblPr>" + "".join(trs) + "</w:tbl>")
                    body.append(p(""))
            elif para.get("type") == "figure":
                body.append(p("［图: " + para.get("caption", "") + (f"（来源: {para.get('source_locator','')}）" if para.get("source_locator") else "") + " — 请在 Word 中插入文件 " + para.get("path", "") + "］", bold=True))
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
                        d.add_paragraph(para["caption"]).runs and None
                        d.paragraphs[-1].runs[0].bold = True
                    rows = para.get("rows", [])
                    if rows:
                        t = d.add_table(rows=len(rows), cols=len(rows[0]))
                        t.style = "Table Grid"
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
                d.add_paragraph("[审校备注] " + c).runs[0].italic = True
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
    ap.add_argument("draft_json")
    ap.add_argument("--out-docx", default="/app/output/draft.docx")
    ap.add_argument("--out-md", default="/app/output/draft.md")
    args = ap.parse_args()
    try:
        draft = json.load(open(args.draft_json, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:300],
                          "note": "输入不可读，未产出文档；不中断交付流程。"},
                         ensure_ascii=False))
        return 0
    draft = _normalize(draft)
    os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
    info = build_docx(draft, args.out_docx)
    build_markdown(draft, args.out_md)
    info["markdown"] = args.out_md
    print(json.dumps({"ok": True, **info}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
