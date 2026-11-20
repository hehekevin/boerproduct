#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_materials.py — 抽取 /input 下材料为带定位标记的文本（三级容错）
用法: python extract_materials.py --input /input --outdir /app/work/extracted
产物: extracted/materials.md（含 M01: 来源标记，段落可定位）+ manifest.json（含 gaps）
容错: ①常规解析 ②替代解析(docx用zip+XML) ③降级登记 gap，exit 0 永不阻塞
"""
import argparse, json, os, re, sys, zipfile

DOCX_EXT = (".docx",); TEXT_EXT = (".md", ".txt", ".tex", ".bib")

def read_docx(path):
    try:
        import docx
        d = docx.Document(path)
        return "\n\n".join(p.text.strip() for p in d.paragraphs if p.text.strip())
    except Exception:
        pass
    try:  # 二级：zip + XML 正则
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        paras = re.split(r"</w:p>", xml)
        out = []
        for p in paras:
            txt = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()
            if txt: out.append(txt)
        return "\n\n".join(out)
    except Exception:
        return None

def read_pdf(path):
    for mod, fn in (("pdfminer.high_level", "extract_text"), ("PyPDF2", None)):
        try:
            if mod == "pdfminer.high_level":
                from pdfminer.high_level import extract_text
                return extract_text(path)
            import PyPDF2
            r = PyPDF2.PdfReader(path)
            return "\n\n".join((pg.extract_text() or "") for pg in r.pages)
        except Exception:
            continue
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--outdir", default="/app/work/extracted")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    manifest, sections, gaps = {"sources": [], "gaps": []}, [], []
    src = args.input
    if not os.path.isdir(src):  # 三级：目录缺失也要交付骨架
        gaps.append("input 目录不存在: %s" % src)
    else:
        files = sorted(os.listdir(src))
        mid = 0
        for fn in files:
            p = os.path.join(src, fn)
            if not os.path.isfile(p): continue
            ext = os.path.splitext(fn)[1].lower()
            text = None
            if ext in TEXT_EXT or fn == "case.json" or fn == "task.md":
                try: text = open(p, encoding="utf-8", errors="ignore").read()
                except Exception: text = None
            elif ext in DOCX_EXT:
                text = read_docx(p)
                if text is None: gaps.append("docx 解析失败: %s（需人工/平台工具）" % fn)
            elif ext == ".pdf":
                text = read_pdf(p)
                if text is None: gaps.append("PDF 解析失败: %s（可用平台 pdf-text-tool 后重跑）" % fn)
            if fn == "case.json":
                manifest["case"] = _load_case(p); continue
            if fn == "task.md":
                manifest["task"] = {"path": p}; continue
            if text and text.strip() and fn != "task.md":
                mid += 1; mtag = "M%02d" % mid
                manifest["sources"].append({"id": mtag, "file": fn, "chars": len(text)})
                sections.append("## %s | %s\n\n%s" % (mtag, fn, text))
            elif ext not in (".json",):
                gaps.append("未抽取到文本: %s" % fn)
    with open(os.path.join(args.outdir, "materials.md"), "w", encoding="utf-8") as f:
        f.write("# 待诊断材料（来源标记版）\n\n" + "\n\n---\n\n".join(sections))
    manifest["gaps"] = gaps
    json.dump(manifest, open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "sources": len(manifest["sources"]), "gaps": gaps}, ensure_ascii=False))
    return 0

def _load_case(p):
    try:
        c = json.load(open(p, encoding="utf-8"))
        return {"case_id": c.get("case_id") or c.get("id"),
                "contract_fields": (c.get("output_contract") or {})}
    except Exception:
        return {"case_id": None, "contract_fields": {}}

if __name__ == "__main__":
    sys.exit(main())
