#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_build.py — 把结构化稿件 JSON 构建为可编辑 Word（.docx）+ Markdown
输入 draft 结构（draft.json）:
{
  "title": "...", "meta": {...},
  "sections": [
     {"heading": "1 选题背景与意义", "level": 1,
      "paragraphs": ["...文本...", {"type":"table","caption":"表1 ...","rows":[[...],[...]]},
                     {"type":"figure","caption":"图1 ...","path":"fig1.png","source_locator":"M02:p3"}],
      "comments": ["审校备注(可选)"]}
  ],
  "references": ["[1] ..."],
  "notes_for_human": ["需要人工确认的事项"]
}

支持分批防截断: 位置参数可传多个 draft 分片（draft_part1.json draft_part2.json ...），
sections 依序合并、references 去重合并、meta 逐键合并——单次响应只写一小片，
规避 16384 token 截断丢失全文。
容错: 脏分片跳过并登记；全部分片无效时仍产出最小可编辑稿件（占位标题+说明），
绝不静默产生空文件。
"""
import argparse, json, os, sys, zipfile


def merge_drafts(paths):
    draft = {"title": "", "meta": {}, "sections": [], "references": [], "notes_for_human": []}
    skipped = []
    for p in paths or []:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            skipped.append({"file": p, "reason": str(e)[:150]})
            continue
        if not isinstance(d, dict):
            skipped.append({"file": p, "reason": "not a dict"})
            continue
        if not draft["title"] and d.get("title"):
            draft["title"] = str(d["title"])
        if isinstance(d.get("meta"), dict):
            draft["meta"].update(d["meta"])
        if isinstance(d.get("sections"), list):
            draft["sections"].extend(s for s in d["sections"] if isinstance(s, dict))
        for r in d.get("references") or []:
            if r and r not in draft["references"]:
                draft["references"].append(r)
        for n in d.get("notes_for_human") or []:
            if n and n not in draft["notes_for_human"]:
                draft["notes_for_human"].append(n)
    return draft, skipped


def _md_escape(s):
    return str(s).replace("|", "\\|")


def build_markdown(draft, path):
    L = ["# " + (draft.get("title") or "(未命名开题报告)"), ""]
    for k, v in (draft.get("meta") or {}).items():
        L.append("- **%s**: %s" % (k, v))
    if draft.get("meta"):
        L.append("")
    for sec in draft.get("sections", []):
        L.append("#" * min(6, (sec.get("level") or 1) + 1) + " " + str(sec.get("heading", "")))
        L.append("")
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                L.append(para)
                L.append("")
            elif isinstance(para, dict) and para.get("type") == "table":
                if para.get("caption"):
                    L.append("**%s**" % para["caption"])
                    L.append("")
                rows = para.get("rows") or []
                if rows:
                    L.append("| " + " | ".join(_md_escape(c) for c in rows[0]) + " |")
                    L.append("|" + "---|" * len(rows[0]))
                    for r in rows[1:]:
                        L.append("| " + " | ".join(_md_escape(c) for c in r) + " |")
                    L.append("")
            elif isinstance(para, dict) and para.get("type") == "figure":
                cap = para.get("caption", "")
                src = para.get("source_locator", "")
                L.append("[%s]()" % cap if not para.get("path") else "![%s](%s)" % (cap, para["path"]))
                L.append("")
                L.append("**%s**%s" % (cap, ("（来源: %s）" % src) if src else ""))
                L.append("")
        for c in sec.get("comments", []):
            L.append("> [审校备注] %s" % c)
            L.append("")
    refs = draft.get("references") or []
    if refs:
        L.append("## 参考文献")
        L.append("")
        for r in refs:
            L.append(str(r))
            L.append("")
    for n in draft.get("notes_for_human") or []:
        L.append("> [待人工确认] %s" % n)
        L.append("")
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path


def _min_docx(path, draft):
    """stdlib 兜底：生成合法可打开的最小 docx（标题+段落+表格）。"""
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def p(text, style=None, bold=False):
        st = '<w:pStyle w:val="%s"/>' % style if style else ""
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return ('<w:p><w:pPr>%s</w:pPr><w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                % (st, rpr, esc(text)))

    body = [p(draft.get("title") or "(未命名)", style="Title")]
    for sec in draft.get("sections", []):
        body.append(p(sec.get("heading", ""), style="Heading%d" % min(3, sec.get("level") or 1)))
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                body.append(p(para))
            elif isinstance(para, dict) and para.get("type") == "table":
                if para.get("caption"):
                    body.append(p(para["caption"], bold=True))
                rows = para.get("rows") or []
                if rows:
                    trs = []
                    for r in rows:
                        tcs = "".join(
                            '<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p></w:tc>'
                            % esc(c) for c in r)
                        trs.append("<w:tr>%s</w:tr>" % tcs)
                    body.append('<w:tbl><w:tblPr><w:tblBorders>'
                                '<w:top w:val="single"/><w:left w:val="single"/>'
                                '<w:bottom w:val="single"/><w:right w:val="single"/>'
                                "</w:tblBorders></w:tblPr>" + "".join(trs) + "</w:tbl>")
                    body.append(p(""))
            elif isinstance(para, dict) and para.get("type") == "figure":
                body.append(p("［图: %s%s — 请在 Word 中插入文件 %s］"
                              % (para.get("caption", ""),
                                 ("（来源: %s）" % para["source_locator"]) if para.get("source_locator") else "",
                                 para.get("path", "")), bold=True))
    for r in draft.get("references") or []:
        body.append(p(r))
    for n in draft.get("notes_for_human") or []:
        body.append(p("［待人工确认］" + str(n), bold=True))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s"><w:body>%s<w:sectPr/></w:body></w:document>'
                % (W, "".join(body)))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<w:styles xmlns:w="%s">'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
              % W
              + "".join('<w:style w:type="paragraph" w:styleId="Heading%d"><w:name w:val="heading %d"/><w:pPr><w:outlineLvl w:val="%d"/></w:pPr><w:rPr><w:b/><w:sz w:val="%d"/></w:rPr></w:style>'
                        % (i, i, i - 1, 32 - 4 * i) for i in (1, 2, 3))
              + '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')
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
        d.add_heading(draft.get("title") or "(未命名)", 0)
        for k, v in (draft.get("meta") or {}).items():
            d.add_paragraph("%s: %s" % (k, v))
        for sec in draft.get("sections", []):
            d.add_heading(sec.get("heading", ""), min(4, sec.get("level") or 1))
            for para in sec.get("paragraphs", []):
                if isinstance(para, str):
                    d.add_paragraph(para)
                elif isinstance(para, dict) and para.get("type") == "table":
                    if para.get("caption"):
                        cp = d.add_paragraph(para["caption"])
                        if cp.runs:
                            cp.runs[0].bold = True
                    rows = para.get("rows") or []
                    if rows:
                        ncols = max(len(r) for r in rows)
                        t = d.add_table(rows=len(rows), cols=ncols)
                        try:
                            t.style = "Table Grid"
                        except Exception:
                            pass
                        for i, r in enumerate(rows):
                            for j, c in enumerate(r):
                                t.cell(i, j).text = str(c)
                    d.add_paragraph("")
                elif isinstance(para, dict) and para.get("type") == "figure":
                    cap = para.get("caption", "")
                    if para.get("path") and os.path.exists(para["path"]):
                        try:
                            d.add_picture(para["path"], width=Pt(360))
                        except Exception:
                            pass
                    pp = d.add_paragraph(cap if not para.get("source_locator")
                                         else "%s（来源: %s）" % (cap, para["source_locator"]))
                    if pp.runs:
                        pp.runs[0].bold = True
            for c in sec.get("comments", []):
                d.add_paragraph("[审校备注] " + str(c))
        for r in draft.get("references") or []:
            d.add_paragraph(str(r))
        for n in draft.get("notes_for_human") or []:
            d.add_paragraph("[待人工确认] " + str(n))
        d.save(path)
        return {"builder": "python-docx", "file": path}
    except Exception as e:
        _min_docx(path, draft)
        return {"builder": "stdlib-min-docx(fallback)", "file": path, "reason": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft_json", nargs="+", help="一个或多个 draft 分片 JSON，依序合并")
    ap.add_argument("--out-docx", default="/app/output/proposal.docx")
    ap.add_argument("--out-md", default="/app/output/proposal.md")
    args = ap.parse_args()

    draft, skipped = merge_drafts(args.draft_json)
    if not draft["sections"] and not draft["title"]:
        draft["title"] = "(开题报告占位 — 分片全部无效，请检查 draft 输入)"
        draft["notes_for_human"].append(
            "docx_build 收到的分片全部无效: %s；本文件为保证可编辑交付的占位，请在修复后重跑。" %
            json.dumps(skipped, ensure_ascii=False))
    os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.out_md) or ".", exist_ok=True)
    info = build_docx(draft, args.out_docx)
    build_markdown(draft, args.out_md)
    info["markdown"] = args.out_md
    info["sections"] = len(draft["sections"])
    info["skipped_parts"] = skipped
    print(json.dumps({"ok": bool(draft["sections"]), **info}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
