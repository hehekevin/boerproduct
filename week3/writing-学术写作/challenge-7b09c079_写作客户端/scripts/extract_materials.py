#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_materials.py — 学术写作赛道通用材料提取器
把 /input 下所有材料（docx/pdf/txt/md/csv/tsv/xlsx/json/html）抽取为带锚点的纯文本，
产出 materials_manifest.json（路径/类型/字符数/sha1/摘要），供后续事实台账与写作阶段引用。

用法:
  python3 extract_materials.py --input /input --outdir /app/work/extracted [--case /input/case.json]

设计原则:
- 只依赖环境预装库；缺失时逐格式降级（python-docx→zipfile解析XML；PyMuPDF/pypdf→报告不可提取）。
- 每个材料产出一个 .txt，内部用锚点行 [SRC:<mid>:p<n>|line<n>] 标注位置，模型写作时引用 locator。
- 不改写、不翻译、不补全任何原文内容；扫描件/加密件如实标记 extracted:false。
"""
import argparse, hashlib, json, os, re, sys, zipfile

def _sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]

def _docx_text(path):
    """python-docx 优先，缺失则用 zipfile+XML 提取段落文本（含表格）。"""
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
        return [(s, t) for s, t in paras], "python-docx"
    except Exception:
        pass
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        out = []
        for pm in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
            texts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", pm)
            t = "".join(texts).strip()
            if t:
                out.append(("Normal", t))
        return out, "zipfile-fallback"
    except Exception as e:
        return [], f"error:{e}"

def _pdf_text(path):
    """PyMuPDF 优先，其次 pypdf；都失败则标记不可提取。"""
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        pages = []
        for i, page in enumerate(doc, 1):
            pages.append(page.get_text("text"))
        return pages, "pymupdf"
    except Exception:
        pass
    try:
        from pypdf import PdfReader  # type: ignore
        r = PdfReader(path)
        pages = []
        for pg in r.pages:
            try:
                pages.append(pg.extract_text() or "")
            except Exception:
                pages.append("")
        return pages, "pypdf"
    except Exception as e:
        return [], f"error:{e}"

def _xlsx_text(path):
    rows = []
    try:
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                vals = ["" if v is None else str(v) for v in row]
                if any(v.strip() for v in vals):
                    rows.append(f"[{ws.title}] " + " | ".join(vals))
        return rows, "openpyxl"
    except Exception:
        pass
    try:
        import csv, io
        with zipfile.ZipFile(path) as z:
            # 共享字符串
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                ss = z.read("xl/sharedStrings.xml").decode("utf-8", "ignore")
                shared = [re.sub(r"<[^>]+>", "", m) for m in re.findall(r"<si>(.*?)</si>", ss, re.S)]
            for name in z.namelist():
                if re.match(r"xl/worksheets/sheet\d+\.xml", name):
                    data = z.read(name).decode("utf-8", "ignore")
                    for rm in re.findall(r"<row[^>]*>(.*?)</row>", data, re.S):
                        cells = []
                        for cm in re.findall(r"<c[^>]*?(?: t=\"(\w+)\")?[^>]*>(?:<v>([^<]*)</v>)?", rm):
                            t, v = cm
                            if t == "s" and v:
                                try: cells.append(shared[int(v)])
                                except Exception: cells.append(v)
                            else: cells.append(v or "")
                        if any(c.strip() for c in cells):
                            rows.append(" | ".join(cells))
        return rows, "zipfile-fallback"
    except Exception as e:
        return [], f"error:{e}"

ANCHOR = "[SRC:{mid}:{loc}]"

def write_txt(outdir, mid, blocks, src_name):
    """blocks: list of (loc_label, text)。写出带锚点行前缀的纯文本。"""
    os.makedirs(outdir, exist_ok=True)
    fp = os.path.join(outdir, f"{mid}.txt")
    lines = [f"===== SOURCE {mid}: {src_name} ====="]
    for loc, text in blocks:
        t = text.strip()
        if t:
            lines.append(f"{ANCHOR.format(mid=mid, loc=loc)} {t}")
    with open(fp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return fp, sum(len(l) for l in lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--outdir", default="/app/work/extracted")
    ap.add_argument("--case", default=None, help="case.json 路径，用于识别声明的材料字段")
    try:
        args = ap.parse_args()
    except SystemExit:
        print("[extract_materials] 参数解析失败（退出码 0，不中断交付）")
        return 0
    try:
        return _run(args)
    except Exception as e:
        # 退出码契约：任何路径都退出 0；结论由打印的 verdict 照实记录，不中断交付。
        print(json.dumps({"ok": False, "verdict": "fail", "error": str(e)[:300],
                          "outdir": args.outdir}, ensure_ascii=False))
        print("[extract_materials] FAIL: %s（退出码 0，不中断交付）" % str(e)[:200])
        return 0


def _run(args):
    inp = args.input
    files = []
    for root, _dirs, fnames in os.walk(inp):
        for fn in sorted(fnames):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, inp).replace("\\", "/")
            if fn.lower().endswith((".docx", ".pdf", ".txt", ".md", ".markdown", ".csv", ".tsv",
                                    ".xlsx", ".xls", ".json", ".html", ".htm", ".rtf", ".bib",
                                    ".tex", ".doc", ".pptx")):
                files.append((rel, p))
            elif not fn.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".bin")):
                files.append((rel, p))

    manifest = {"input_root": inp, "materials": [], "case_declared": None, "notes": []}

    # case.json 单独解析并内嵌
    case_path = args.case
    if case_path is None:
        for rel, p in files:
            if os.path.basename(p) == "case.json":
                case_path = p
                break
    case_obj = None
    if case_path and os.path.exists(case_path):
        try:
            case_obj = json.load(open(case_path, encoding="utf-8"))
            manifest["case_declared"] = {k: case_obj[k] for k in list(case_obj)[:20]}
        except Exception as e:
            manifest["notes"].append(f"case.json parse failed: {e}")

    ext_map = {".docx": "docx", ".pdf": "pdf", ".txt": "txt", ".md": "md", ".markdown": "md",
               ".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx", ".xls": "xlsx", ".json": "json",
               ".html": "html", ".htm": "html", ".bib": "bib", ".tex": "tex"}
    n_ok = 0
    for i, (rel, p) in enumerate(files, 1):
        mid = "M%02d" % i
        ext = os.path.splitext(p)[1].lower()
        kind = ext_map.get(ext, "other")
        entry = {"id": mid, "path": rel, "abs": p, "kind": kind, "sha1_12": _sha1(p),
                 "extracted": False, "engine": None, "txt": None, "chars": 0, "units": 0}
        try:
            if kind == "docx":
                paras, engine = _docx_text(p)
                blocks = [(f"para{j}", t) for j, (_s, t) in enumerate(paras, 1)]
                fp, n = write_txt(args.outdir, mid, blocks, rel)
                entry.update(extracted=True, engine=engine, txt=os.path.relpath(fp, args.outdir), chars=n, units=len(blocks))
            elif kind == "pdf":
                pages, engine = _pdf_text(p)
                if isinstance(pages, list) and pages:
                    blocks = [(f"p{j}", t) for j, t in enumerate(pages, 1) if t.strip()]
                    total = sum(len(t) for t in pages)
                    fp, n = write_txt(args.outdir, mid, blocks, rel)
                    entry.update(extracted=total > 40, engine=engine, txt=os.path.relpath(fp, args.outdir), chars=n, units=len(blocks))
                    if total <= 40:
                        entry["engine"] = engine + " (likely scanned; OCR needed)"
                else:
                    entry["engine"] = engine
            elif kind in ("txt", "md", "csv", "tsv", "json", "html", "bib", "tex"):
                raw = open(p, "r", encoding="utf-8", errors="ignore").read()
                lines = raw.splitlines()
                blocks = [(f"line{j}", t) for j, t in enumerate(lines, 1) if t.strip()]
                fp, n = write_txt(args.outdir, mid, blocks, rel)
                entry.update(extracted=True, engine="plain", txt=os.path.relpath(fp, args.outdir), chars=n, units=len(blocks))
            elif kind == "xlsx":
                rows, engine = _xlsx_text(p)
                blocks = [(f"row{j}", t) for j, t in enumerate(rows, 1)]
                fp, n = write_txt(args.outdir, mid, blocks, rel)
                entry.update(extracted=bool(rows), engine=engine, txt=os.path.relpath(fp, args.outdir), chars=n, units=len(blocks))
            else:
                entry["engine"] = "skipped-binary-or-unknown"
        except Exception as e:
            entry["engine"] = f"error:{e}"
        if entry["extracted"]:
            n_ok += 1
        manifest["materials"].append(entry)

    manifest["summary"] = {"total": len(files), "extracted": n_ok}
    os.makedirs(args.outdir, exist_ok=True)
    mp = os.path.join(args.outdir, "materials_manifest.json")
    json.dump(manifest, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "manifest": mp, "summary": manifest["summary"],
                      "materials": [{ "id": m["id"], "path": m["path"], "kind": m["kind"],
                                      "extracted": m["extracted"], "chars": m["chars"]} for m in manifest["materials"]]},
                     ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
