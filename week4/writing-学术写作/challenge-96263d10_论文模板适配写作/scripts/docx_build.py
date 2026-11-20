#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_build.py — 把 draft.json 构建为可编辑 Word(.docx)+Markdown，样式按模板规格真实绑定

draft.json 结构:
{
  "title": "...",
  "meta": {...},
  "style_spec": {                       // 来自 format_mapping 的 applied 值（缺省用内置默认）
     "heading": {"1": {"font":"黑体","size_pt":16,"bold":true,"align":"center"},
                 "2": {"font":"黑体","size_pt":14,"bold":true}},
     "body":   {"font":"宋体","size_pt":12,"line_spacing":1.5,"first_line_indent_pt":24},
     "caption":{"font":"宋体","size_pt":10.5,"position":"below_figure_above_table"},
     "reference": {"style":"gbt7714","font":"宋体","size_pt":10.5}
  },
  "sections": [{"heading":"1 引言","level":1,"paragraphs":["...", {"type":"table","caption":"表1 ...","rows":[[..]]},
                {"type":"figure","caption":"图1 ...","path":"fig1.png"}]}],
  "references": ["[1] ..."],
  "notes_for_human": ["..."]
}
容错: python-docx → stdlib 最小 docx（样式值同步写入 styles.xml）；均失败时仍产出 .md 并如实报告。
"""
import argparse, json, os, sys, zipfile

def _apply_styles_pydocx(d, spec):
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    ALIGN = {"center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT,
             "justify": WD_ALIGN_PARAGRAPH.JUSTIFY, "left": WD_ALIGN_PARAGRAPH.LEFT}
    try:
        styles = d.styles
        def set_st(name, sp):
            try:
                st = styles[name]
            except Exception:
                return
            f = st.font
            if sp.get("font"):
                f.name = sp["font"]
                try:  # 中文字体需设 eastAsia
                    from docx.oxml.ns import qn
                    st.element.rPr.rFonts.set(qn("w:eastAsia"), sp["font"])
                except Exception:
                    pass
            if sp.get("size_pt"):
                f.size = Pt(sp["size_pt"])
            if "bold" in sp:
                f.bold = bool(sp["bold"])
            pf = st.paragraph_format
            if sp.get("align") in ALIGN:
                pf.alignment = ALIGN[sp["align"]]
            if sp.get("line_spacing"):
                pf.line_spacing = sp["line_spacing"]
            if sp.get("first_line_indent_pt"):
                pf.first_line_indent = Pt(sp["first_line_indent_pt"])
        hs = spec.get("heading") or {}
        for lv in ("1", "2", "3"):
            if lv in hs:
                set_st(f"Heading {lv}", hs[lv])
        if spec.get("body"):
            set_st("Normal", spec["body"])
    except Exception:
        pass

def build_docx(draft, path):
    spec = draft.get("style_spec") or {}
    try:
        import docx  # type: ignore
        from docx.shared import Pt
        d = docx.Document()
        _apply_styles_pydocx(d, spec)
        d.add_heading(draft.get("title", ""), 0)
        for k, v in (draft.get("meta") or {}).items():
            d.add_paragraph(f"{k}: {v}")
        for sec in draft.get("sections", []):
            d.add_heading(sec.get("heading", ""), min(4, sec.get("level") or 1))
            for para in sec.get("paragraphs", []):
                if isinstance(para, str):
                    d.add_paragraph(para)
                elif para.get("type") == "table":
                    cap = para.get("caption", "")
                    if cap:  # 表题注在表上
                        pp = d.add_paragraph(cap)
                        cs = spec.get("caption") or {}
                        if pp.runs:
                            pp.runs[0].bold = True
                            if cs.get("size_pt"):
                                pp.runs[0].font.size = Pt(cs["size_pt"])
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
                    if para.get("path") and os.path.exists(para["path"]):
                        try:
                            d.add_picture(para["path"], width=Pt(360))
                        except Exception:
                            pass
                    cap = para.get("caption", "")  # 图题注在图下
                    pp = d.add_paragraph(cap)
                    cs = spec.get("caption") or {}
                    if pp.runs:
                        pp.runs[0].bold = True
                        if cs.get("size_pt"):
                            pp.runs[0].font.size = Pt(cs["size_pt"])
            for c in sec.get("comments", []):
                d.add_paragraph("[审校备注] " + c)
        for r in draft.get("references") or []:
            d.add_paragraph(r)
        for n in draft.get("notes_for_human") or []:
            d.add_paragraph("[待人工确认] " + n)
        d.save(path)
        return {"builder": "python-docx", "file": path}
    except Exception as e:
        reason = str(e)[:200]
    # 二级: stdlib 最小 docx
    try:
        _min_docx(path, draft, spec)
        return {"builder": "stdlib-min-docx(fallback)", "file": path, "reason": reason}
    except Exception as e2:
        return {"builder": "failed", "file": None, "reason": reason + " | fallback: " + str(e2)[:150]}

def _min_docx(path, draft, spec):
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    def halfpt(sp, key="size_pt"):
        v = (sp or {}).get(key)
        return str(int(v * 2)) if v else None
    hs = spec.get("heading") or {}
    bs = spec.get("body") or {}
    styles = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:styles xmlns:w="{W}">']
    def style_xml(sid, name, sp, outline=None):
        rpr = "<w:rPr>" + ("<w:b/>" if sp.get("bold") else "") + \
              (f'<w:sz w:val="{halfpt(sp)}"/>' if sp.get("size_pt") else "") + \
              (f'<w:rFonts w:ascii="{sp["font"]}" w:eastAsia="{sp["font"]}"/>' if sp.get("font") else "") + \
              "</w:rPr>"
        ppr = "<w:pPr>" + (f'<w:outlineLvl w:val="{outline}"/>' if outline is not None else "") + \
              (f'<w:jc w:val="{sp["align"]}"/>' if sp.get("align") else "") + "</w:pPr>"
        return f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>{ppr}{rpr}</w:style>'
    styles.append(style_xml("Title", "Title", {"bold": True, "size_pt": 16, "align": "center"}))
    for i in (1, 2, 3):
        styles.append(style_xml(f"Heading{i}", f"heading {i}", hs.get(i, hs.get(str(i), {"bold": True})), outline=i - 1))
    styles.append(style_xml("Normal", "Normal", bs))
    styles.append("</w:styles>")
    styles = "".join(styles)
    def p(text, style=None):
        st = f'<w:pStyle w:val="{style}"/>' if style else ""
        return f'<w:p><w:pPr>{st}</w:pPr><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    body = [p(draft.get("title", ""), "Title")]
    for sec in draft.get("sections", []):
        body.append(p(sec.get("heading", ""), f"Heading{min(3, sec.get('level') or 1)}"))
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                body.append(p(para))
            elif para.get("type") == "table":
                if para.get("caption"):
                    body.append(p(para["caption"]))
                rows = para.get("rows", [])
                if rows:
                    trs = "".join("<w:tr>" + "".join(
                        f'<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">{c}</w:t></w:r></w:p></w:tc>' for c in r)
                        + "</w:tr>" for r in rows)
                    body.append(f'<w:tbl><w:tblPr><w:tblBorders><w:top w:val="single"/>'
                                '<w:bottom w:val="single"/></w:tblBorders></w:tblPr>' + trs + "</w:tbl>")
            elif para.get("type") == "figure":
                body.append(p("［图: " + para.get("caption", "") + " — 请在 Word 中插入文件 " + para.get("path", "") + "］"))
    for r in draft.get("references") or []:
        body.append(p(r))
    for n in draft.get("notes_for_human") or []:
        body.append(p("［待人工确认］" + n))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}<w:sectPr/></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", drels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)

def build_markdown(draft, path):
    L = [f"# {draft.get('title','(无题)')}", ""]
    for sec in draft.get("sections", []):
        L += ["#" * min(6, (sec.get("level") or 1) + 1) + " " + sec.get("heading", ""), ""]
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                L += [para, ""]
            elif para.get("type") == "table":
                if para.get("caption"):
                    L += [f"**{para['caption']}**", ""]
                rows = para.get("rows", [])
                if rows:
                    L += ["| " + " | ".join(str(c).replace("|", "\\|") for c in rows[0]) + " |",
                          "|" + "---|" * len(rows[0])]
                    L += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows[1:]]
                    L.append("")
            elif para.get("type") == "figure":
                L += [f"![{para.get('caption','')}]({para.get('path','')})",
                      f"**{para.get('caption','')}**", ""]
    refs = draft.get("references") or []
    if refs:
        L += ["## 参考文献", ""] + [r for r in refs] + [""]
    for n in draft.get("notes_for_human") or []:
        L += [f"> [待人工确认] {n}", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))
    return path

def try_render(docx_path, outdir):
    """可选渲染：环境有 libreoffice/soffice 才执行；失败如实返回不阻断。"""
    import shutil, subprocess
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return {"rendered": False, "reason": "libreoffice/soffice 不可用，跳过预览渲染"}
    os.makedirs(outdir, exist_ok=True)
    try:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, docx_path],
                       timeout=120, capture_output=True)
        pdf = os.path.join(outdir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
        return {"rendered": os.path.exists(pdf), "pdf": pdf if os.path.exists(pdf) else None}
    except Exception as e:
        return {"rendered": False, "reason": str(e)[:150]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft_json")
    ap.add_argument("--out-docx", default="/app/output/draft.docx")
    ap.add_argument("--out-md", default="/app/output/draft.md")
    ap.add_argument("--render-dir", default=None)
    args = ap.parse_args()
    draft = json.load(open(args.draft_json, encoding="utf-8"))
    os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
    info = build_docx(draft, args.out_docx)
    build_markdown(draft, args.out_md)
    info["markdown"] = args.out_md
    info["md_ok"] = os.path.exists(args.out_md) and os.path.getsize(args.out_md) > 0
    if args.render_dir:
        info["render"] = try_render(args.out_docx, args.render_dir)
    # 写盘自检
    info["self_check"] = {"docx_exists": os.path.exists(args.out_docx) if info.get("file") else False,
                          "docx_size": os.path.getsize(args.out_docx) if os.path.exists(args.out_docx) else 0,
                          "md_exists": info["md_ok"]}
    print(json.dumps({"ok": True, **info}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
