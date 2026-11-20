#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_materials.py — 提取材料 + 真实探查模板规格 + 内容单元盘点（三级容错）

三个模式（可同跑）:
  --extract   把输入目录所有材料抽为带锚点 [SRC:<mid>:<loc>] 的纯文本 + materials_manifest.json
  --probe     对模板类 docx 真实读取 styles/sectPr，输出 probe_report.json（观测原值，禁止编造）
  --inventory 对稿件类材料建立内容单元清单 content_inventory.jsonl（零丢失对账依据）

容错: python-docx → zipfile+XML → 原始标记兜底；任一失败不中断整体，逐条如实记录。
"""
import argparse, hashlib, json, os, re, sys, zipfile

def _sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]

def _docx_paras(path):
    paras = []
    try:
        import docx  # type: ignore
        d = docx.Document(path)
        for p in d.paragraphs:
            t = p.text.strip()
            if t:
                paras.append((p.style.name if p.style else "Normal", t))
        for tbl in d.tables:
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    paras.append(("Table", " | ".join(cells)))
        return paras, "python-docx"
    except Exception:
        pass
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        out = []
        for pm in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
            t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", pm)).strip()
            if t:
                out.append(("Normal", t))
        return out, "zipfile-fallback"
    except Exception as e:
        return [], "error:" + str(e)

def _pdf_pages(path):
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        return [pg.get_text("text") for pg in doc], "pymupdf"
    except Exception:
        pass
    try:
        from pypdf import PdfReader  # type: ignore
        return [(pg.extract_text() or "") for pg in PdfReader(path).pages], "pypdf"
    except Exception as e:
        return [], "error:" + str(e)

def _txt_units(p):
    raw = open(p, "r", encoding="utf-8", errors="ignore").read()
    return [(f"line{j}", l.strip()) for j, l in enumerate(raw.splitlines(), 1) if l.strip()]

def write_txt(outdir, mid, blocks, src_name):
    os.makedirs(outdir, exist_ok=True)
    fp = os.path.join(outdir, f"{mid}.txt")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(f"===== SOURCE {mid}: {src_name} =====\n")
        for loc, t in blocks:
            if t.strip():
                f.write(f"[SRC:{mid}:{loc}] {t.strip()}\n")
    return fp

EMU = 914400  # EMU per inch; twips = EMU/635

# ---------- 模板真实探查 ----------
def _tw2cm(v):
    try:
        return round(int(v) / 567.0, 2)
    except Exception:
        return None

def probe_docx(path):
    """从 docx 真实读取样式与页面设置。返回 (observed_list, engine)。"""
    observed, engine = [], "python-docx"
    try:
        import docx  # type: ignore
        from docx.shared import Pt as _Pt
        d = docx.Document(path)
        seen = set()
        for s in d.styles:
            try:
                if s.type is not None and getattr(s, "font", None):
                    f = s.font
                    size = f.size.pt if f.size else None
                    name = f.name
                    rec = {"style": s.name, "font": name, "size_pt": size,
                           "bold": f.bold, "italic": f.italic}
                    try:
                        rec["align"] = str(s.paragraph_format.alignment)
                        rec["line_spacing"] = str(s.paragraph_format.line_spacing)
                        rec["space_before_pt"] = s.paragraph_format.space_before.pt if s.paragraph_format.space_before else None
                        rec["space_after_pt"] = s.paragraph_format.space_after.pt if s.paragraph_format.space_after else None
                    except Exception:
                        pass
                    key = json.dumps(rec, sort_keys=True, ensure_ascii=False)
                    if rec["style"] not in seen and (size or name):
                        seen.add(rec["style"])
                        observed.append(rec)
            except Exception:
                continue
        try:
            sec = d.sections[0]
            observed.append({"page": {
                "page_width_cm": round(sec.page_width.cm, 2) if sec.page_width else None,
                "page_height_cm": round(sec.page_height.cm, 2) if sec.page_height else None,
                "margin_top_cm": round(sec.top_margin.cm, 2) if sec.top_margin else None,
                "margin_bottom_cm": round(sec.bottom_margin.cm, 2) if sec.bottom_margin else None,
                "margin_left_cm": round(sec.left_margin.cm, 2) if sec.left_margin else None,
                "margin_right_cm": round(sec.right_margin.cm, 2) if sec.right_margin else None,
                "orientation": str(sec.orientation)}})
        except Exception as e:
            observed.append({"page": {"error": str(e)[:120]}})
        try:
            sec = d.sections[0]
            cols = sec._sectPr.xpath('./w:cols/@w:num')
            observed.append({"columns": cols[0] if cols else "1(default)"})
        except Exception:
            observed.append({"columns": "unreadable"})
        return observed, "python-docx"
    except Exception:
        pass
    # 二级: zipfile + XML
    try:
        with zipfile.ZipFile(path) as z:
            engine = "xml-fallback"
            try:
                sx = z.read("word/styles.xml").decode("utf-8", "ignore")
                for m in re.finditer(r'<w:style [^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', sx, re.S):
                    sid, body = m.group(1), m.group(2)
                    font = re.search(r'<w:rFonts[^>]*w:ascii="([^"]+)"', body)
                    sz = re.search(r'<w:sz w:val="(\d+)"', body)
                    bold = "<w:b/>" in body
                    jc = re.search(r'<w:jc w:val="([^"]+)"', body)
                    if font or sz:
                        observed.append({"style": sid, "font": font.group(1) if font else None,
                                         "size_pt": round(int(sz.group(1)) / 2, 1) if sz else None,
                                         "bold": bold, "align": jc.group(1) if jc else None})
            except Exception:
                pass
            try:
                dx = z.read("word/document.xml").decode("utf-8", "ignore")
                sect = re.search(r"<w:sectPr.*?</w:sectPr>", dx, re.S)
                if sect:
                    s = sect.group(0)
                    pg = re.search(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', s)
                    mar = re.search(r'<w:pgMar w:top="(-?\d+)" w:right="(-?\d+)" w:bottom="(-?\d+)" w:left="(-?\d+)"', s)
                    cols = re.search(r'<w:cols w:num="(\d+)"', s)
                    observed.append({"page": {
                        "page_width_cm": _tw2cm(pg.group(1)) if pg else None,
                        "page_height_cm": _tw2cm(pg.group(2)) if pg else None,
                        "margin_top_cm": _tw2cm(mar.group(1)) if mar else None,
                        "margin_right_cm": _tw2cm(mar.group(2)) if mar else None,
                        "margin_bottom_cm": _tw2cm(mar.group(3)) if mar else None,
                        "margin_left_cm": _tw2cm(mar.group(4)) if mar else None},
                        "columns": cols.group(1) if cols else "1(default)"})
            except Exception:
                pass
        return observed, engine
    except Exception as e:
        return [{"error": str(e)[:200]}], "error"

def probe_text(path):
    """文本类格式要求：标记为文本条款，逐行给 locator（由模型在 mapping 中引用行号）。"""
    lines = _txt_units(path)
    return [{"text_clause_count": len(lines), "note": "文本条款，引用 txt 中行号 locator"}], "text-lines"

def do_probe(materials, outdir):
    report = {"probes": [], "note": "observed 为模板文件真实读取值，未经解释；逐条原样进入 result.json.format_spec"}
    for m in materials:
        p = m["abs"]
        obs, engine = (probe_docx(p) if m["kind"] == "docx" else
                       probe_text(p) if m["kind"] in ("txt", "md", "pdf", "html") else
                       ([{"error": "kind %s not probeable" % m["kind"]}], "skip"))
        report["probes"].append({"material": m["id"], "path": m["path"], "engine": engine,
                                 "observed": obs})
    os.makedirs(outdir, exist_ok=True)
    fp = os.path.join(outdir, "probe_report.json")
    json.dump(report, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return fp, report

def do_extract(files, outdir):
    manifest = {"input_root": files[0][1] if files else "", "materials": [], "notes": []}
    n_ok = 0
    for i, (rel, p) in enumerate(files, 1):
        mid = "M%02d" % i
        ext = os.path.splitext(p)[1].lower()
        kind = {".docx": "docx", ".pdf": "pdf", ".txt": "txt", ".md": "md", ".csv": "csv",
                ".tsv": "tsv", ".json": "json", ".html": "html", ".htm": "html",
                ".bib": "bib", ".tex": "tex", ".xlsx": "xlsx"}.get(ext, "other")
        entry = {"id": mid, "path": rel, "abs": p, "kind": kind, "sha1_12": _sha1(p),
                 "extracted": False, "engine": None, "chars": 0, "units": 0}
        try:
            if kind == "docx":
                paras, engine = _docx_paras(p)
                blocks = [(f"para{j}", t) for j, (_s, t) in enumerate(paras, 1)]
            elif kind == "pdf":
                pages, engine = _pdf_pages(p)
                blocks = [(f"p{j}", t) for j, t in enumerate(pages, 1) if t.strip()] if pages else []
                if not pages:
                    entry["engine"] = engine
                    manifest["materials"].append(entry)
                    continue
            elif kind in ("txt", "md", "csv", "tsv", "json", "html", "bib", "tex"):
                blocks, engine = _txt_units(p), "plain"
            elif kind == "xlsx":
                rows, engine = [], "xlsx-skip(转 csv 后处理)"
                blocks = []
            else:
                entry["engine"] = "skipped-binary"
                manifest["materials"].append(entry)
                continue
            fp = write_txt(outdir, mid, blocks, rel)
            n = sum(1 for _l, t in blocks if t.strip())
            entry.update(extracted=n > 0, engine=engine,
                         chars=sum(len(t) for _l, t in blocks), units=n)
            if entry["extracted"]:
                n_ok += 1
        except Exception as e:
            entry["engine"] = "error:" + str(e)[:150]
        manifest["materials"].append(entry)
    manifest["summary"] = {"total": len(files), "extracted": n_ok}
    os.makedirs(outdir, exist_ok=True)
    mp = os.path.join(outdir, "materials_manifest.json")
    json.dump(manifest, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return mp, manifest

def do_inventory(manifest, outdir):
    """稿件材料：每个抽取单元一行（含 locator），作为零丢失对账清单。"""
    fp = os.path.join(outdir, "content_inventory.jsonl")
    n = 0
    with open(fp, "w", encoding="utf-8") as out:
        for m in manifest["materials"]:
            txtp = os.path.join(outdir, f"{m['id']}.txt")
            if not (m.get("extracted") and os.path.exists(txtp)):
                continue
            for line in open(txtp, encoding="utf-8"):
                line = line.strip()
                if not line.startswith("[SRC:"):
                    continue
                loc_end = line.index("]")
                loc = line[len(f"[SRC:{m['id']}:") + 0:loc_end].replace(m["id"] + ":", "", 1)
                text = line[loc_end + 1:].strip()
                kind = "table" if text.startswith("Table") or " | " in text[:80] else \
                       "heading" if re.match(r"^#{1,6}\s|^\d+(\.\d+)*\s*\S|^第.+[章章节]", text[:20]) else "body"
                out.write(json.dumps({"mid": m["id"], "locator": loc, "kind": kind,
                                      "text": text[:300]}, ensure_ascii=False) + "\n")
                n += 1
    return fp, n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"))
    ap.add_argument("--outdir", default="/app/work/extracted")
    ap.add_argument("--modes", default="extract,probe,inventory")
    args = ap.parse_args()
    modes = set(args.modes.split(","))
    inp = args.input
    files = []
    for root, _d, fns in os.walk(inp):
        for fn in sorted(fns):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, inp).replace("\\", "/")
            files.append((rel, p))
    out = {"ok": True, "modes": sorted(modes)}
    if "extract" in modes:
        mp, manifest = do_extract(files, args.outdir)
        out.update(manifest=mp, summary=manifest["summary"])
    else:
        mp = os.path.join(args.outdir, "materials_manifest.json")
        manifest = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"materials": []}
    if "probe" in modes:
        fp, report = do_probe(manifest["materials"], args.outdir)
        out.update(probe_report=fp,
                   probe_engines=[b.get("engine") for b in report["probes"]])
    if "inventory" in modes:
        fp, n = do_inventory(manifest, args.outdir)
        out.update(content_inventory=fp, inventory_units=n)
    print(json.dumps(out, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
