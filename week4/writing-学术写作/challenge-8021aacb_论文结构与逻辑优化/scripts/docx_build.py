#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""docx_build.py — draft.json → 可编辑 docx + md（三级容错）
用法: python docx_build.py /app/work/revised_draft.json --out-docx /app/output/revised.docx --out-md /app/output/revised.md
draft.json: {"title":…,"sections":[{"heading":…,"source":"原§2 para1","paragraphs":["…"]}]}
容错: ①python-docx 正常构建 ②md 必出 ③docx 失败则登记，exit 0
"""
import argparse, json, os, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--out-docx", default="/app/output/revised.docx")
    ap.add_argument("--out-md", default="/app/output/revised.md")
    args = ap.parse_args()
    try:
        draft = json.load(open(args.draft, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "draft.json 不可解析: %s" % e}, ensure_ascii=False))
        return 0
    title = draft.get("title") or "Revised Draft"
    sections = draft.get("sections") or []
    md_lines = ["# " + title, ""]
    for sec in sections:
        h = sec.get("heading") or ""
        if h: md_lines += ["## " + h, ""]
        src = sec.get("source")
        if src: md_lines += ["*（来源映射：%s）*" % src, ""]
        md_lines += [p + "\n" for p in sec.get("paragraphs") or []]
        md_lines.append("")
    os.makedirs(os.path.dirname(args.out_md) or ".", exist_ok=True)
    open(args.out_md, "w", encoding="utf-8").write("\n".join(md_lines))
    docx_ok, err = False, None
    try:
        from docx import Document
        doc = Document()
        doc.add_heading(title, 0)
        for sec in sections:
            if sec.get("heading"): doc.add_heading(sec["heading"], 1)
            if sec.get("source"): doc.add_paragraph("来源映射：" + sec["source"])
            for p in sec.get("paragraphs") or []: doc.add_paragraph(p)
        os.makedirs(os.path.dirname(args.out_docx) or ".", exist_ok=True)
        doc.save(args.out_docx); docx_ok = True
    except Exception as e:
        err = str(e)
    print(json.dumps({"ok": True, "md": args.out_md, "docx": args.out_docx if docx_ok else None,
                      "docx_error": err}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
