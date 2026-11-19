#!/usr/bin/env python3
"""extract_source.py — 科研材料提取：论文 PDF / material.json / 起始稿 pptx → 统一文本基线。

输出（--outdir 内）：
  source_text.txt   全文（分页标记 ===== PAGE n =====，页码即证据锚点）
  manifest.json     工具链、页数、图数、scanned 标志、降级记录

降级链：PyMuPDF(fitz) → pdftotext → material.json 直读 → 起始稿 pptx 文本。
全部失败也如实落 manifest（ok:false + 原因），退出码恒 0，不伪造文本。
用法: python3 extract_source.py <paper.pdf|material.json> --outdir /app/work/extracted \
        [--starting-deck /input/starting-deck.pptx]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def extract_fitz(pdf, outdir, min_size=180):
    import fitz
    doc = fitz.open(pdf)
    parts, pages_meta, figs = [], [], 0
    figdir = os.path.join(outdir, "figures")
    os.makedirs(figdir, exist_ok=True)
    for pno, page in enumerate(doc, 1):
        parts.append("===== PAGE %d =====" % pno)
        parts.append(page.get_text("text"))
        imgs = []
        for i, info in enumerate(page.get_images(full=True), 1):
            try:
                pix = fitz.Pixmap(doc, info[0])
                if pix.width < min_size or pix.height < min_size:
                    continue
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fname = "fig_p%d_%d.png" % (pno, i)
                pix.save(os.path.join(figdir, fname))
                imgs.append({"file": "figures/" + fname, "w": pix.width, "h": pix.height, "page": pno})
                figs += 1
            except Exception:
                continue
        pages_meta.append({"page": pno, "chars": len(page.get_text("text")), "images": imgs})
    return {"tool": "pymupdf", "pages": doc.page_count, "figures_total": figs,
            "pages_meta": pages_meta,
            "text": "\n".join(parts),
            "scanned": doc.page_count > 0 and all(p["chars"] < 40 for p in pages_meta)}


def extract_pdftotext(pdf, outdir):
    pt = shutil.which("pdftotext")
    if not pt:
        return None
    txt = os.path.join(outdir, "source_text.txt")
    r = subprocess.run([pt, "-layout", pdf, txt], capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(txt):
        return None
    content = open(txt, encoding="utf-8", errors="replace").read()
    return {"tool": "pdftotext", "pages": content.count("\f") + 1, "figures_total": 0,
            "scanned": len(content) < 400, "pages_meta": [],
            "note": "无 PyMuPDF：图不落盘，改整页渲染 page_render"}


def extract_material_json(path):
    """material.json 直读：抽全部字符串值拼文本（保留字段名作锚点）。"""
    data, err = None, None
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        err = str(e)
    if data is None:
        return None, err
    buf = []

    def walk(v, prefix=""):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, "%s.%s" % (prefix, k) if prefix else str(k))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, "%s[%d]" % (prefix, i))
        elif isinstance(v, str) and len(v.strip()) > 1:
            buf.append("[%s] %s" % (prefix, v))
    walk(data)
    return {"tool": "material_json", "pages": 1, "figures_total": 0, "scanned": False,
            "pages_meta": [], "text": "\n".join(buf)}, None


def deck_text(path):
    try:
        z = zipfile.ZipFile(path)
        names = sorted([n for n in z.namelist() if "slides/slide" in n and n.endswith(".xml")])
        out = []
        for i, n in enumerate(names, 1):
            root = ET.fromstring(z.read(n))
            texts = [t.text for t in root.iter("{%s}t" % NS_A) if t.text and t.text.strip()]
            out.append("===== DECK PAGE %d =====\n%s" % (i, "\n".join(texts)))
        return {"tool": "starting_deck_text", "pages": len(names), "figures_total": 0,
                "scanned": False, "pages_meta": [], "text": "\n".join(out),
                "note": "材料缺失时以起始稿文本为回证基线（弱基线，须在 uncertainty 登记）"}
    except Exception as e:
        return None, str(e)


def main():
    class P(argparse.ArgumentParser):
        def error(self, m):
            print(json.dumps({"argparse_error": m}, ensure_ascii=False))
            sys.exit(0)
    ap = P()
    ap.add_argument("source", help="论文 PDF / material.json / 材料文本")
    ap.add_argument("--outdir", default="extracted")
    ap.add_argument("--starting-deck", default=None)
    ap.add_argument("--min-size", type=int, default=180)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    meta, err = None, None
    low = args.source.lower()
    if low.endswith(".pdf") and os.path.exists(args.source):
        try:
            meta = extract_fitz(args.source, args.outdir, args.min_size)
        except Exception as e:
            err = "fitz: %s" % e
            if meta is None:
                try:
                    meta = extract_pdftotext(args.source, args.outdir)
                except Exception as e2:
                    err += " | pdftotext: %s" % e2
    elif low.endswith(".json") and os.path.exists(args.source):
        meta, err = extract_material_json(args.source)
    elif os.path.exists(args.source):
        try:
            txt = open(args.source, encoding="utf-8", errors="replace").read()
            meta = {"tool": "plain_text", "pages": txt.count("\f") + 1, "figures_total": 0,
                    "scanned": False, "pages_meta": [], "text": txt}
        except Exception as e:
            err = str(e)
    else:
        err = "source not found: %s" % args.source

    # 终极降级：起始稿文本
    if meta is None and args.starting_deck and os.path.exists(args.starting_deck):
        meta, e2 = deck_text(args.starting_deck)
        if e2:
            err = "%s | deck fallback: %s" % (err, e2)

    if meta is None:
        manifest = {"ok": False, "error": err or "no extractor available", "degrade_chain": ["fitz", "pdftotext", "material_json", "plain_text", "deck_text"]}
    else:
        manifest = {"ok": True, **{k: v for k, v in meta.items() if k != "text"}}
        if meta.get("text") is not None:
            with open(os.path.join(args.outdir, "source_text.txt"), "w", encoding="utf-8") as f:
                f.write(meta["text"])
        manifest["text_file"] = "source_text.txt"
    with open(os.path.join(args.outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: manifest.get(k) for k in ("ok", "tool", "pages", "figures_total", "scanned", "error")}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
