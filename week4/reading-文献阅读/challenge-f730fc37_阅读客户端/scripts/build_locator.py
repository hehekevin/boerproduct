#!/usr/bin/env python3
"""build_locator.py — 构建段落级定位索引（paragraph-json/txt/md/pdf），支持关键词定位。
全异常捕获，任何输入都写出 locator.json（失败写空索引+原因）。自测：--selftest。"""
from __future__ import annotations
import argparse, json, os, re, sys

def clean(s):
    return re.sub(r"\s+", "", str(s or ""))

def index_paragraph_list(paras):
    out = []
    for i, p in enumerate(paras):
        try:
            if isinstance(p, dict):
                pid = str(p.get("paragraph_id") or p.get("id") or p.get("section_id") or ("p%02d" % (i + 1)))
                txt = str(p.get("text") or p.get("content") or p.get("body") or p.get("sentence") or "")
                page = p.get("page") or p.get("page_number")
                heading = p.get("heading") or p.get("title") or p.get("section") or None
            else:
                pid, txt, page, heading = "p%02d" % (i + 1), str(p), None, None
            if not txt.strip():
                continue
            out.append({"paragraph_id": pid, "page": page, "heading": heading,
                        "offset_start": 0, "offset_end": len(txt), "text": txt})
        except Exception:
            continue
    return out

def index_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    out = []
    try:
        chunks = [c.strip() for c in re.split(r"\n\s*\n", raw) if c.strip()]
        off = 0
        for i, c in enumerate(chunks):
            try:
                start = raw.find(c[:50], off)
                if start < 0:
                    start = off
                heading = None
                m = re.match(r"^#{1,6}\s+(.+)", c)
                if m:
                    heading = m.group(1)[:80]
                out.append({"paragraph_id": "p%02d" % (i + 1), "page": None, "heading": heading,
                            "offset_start": start, "offset_end": start + len(c), "text": c})
                off = start + len(c)
            except Exception:
                continue
    except Exception:
        pass
    if not out and raw.strip():
        out = [{"paragraph_id": "p01", "page": None, "heading": None,
                "offset_start": 0, "offset_end": len(raw), "text": raw.strip()}]
    return out

def index_pdf(path):
    doc = None
    try:
        import fitz
        doc = fitz.open(path)
    except Exception:
        try:
            from pypdf import PdfReader
            doc = PdfReader(path)
            blocks_mode = "pypdf"
        except Exception as e:
            return None, "pdf-lib-unavailable(%s)" % type(e).__name__
    out = []
    try:
        for pno in range(len(doc)):
            try:
                page = doc[pno]
                blocks = page.get_text("blocks") if hasattr(page, "get_text") else []
                bi = 0
                for b in blocks or []:
                    txt = str(b[4] if isinstance(b, (list, tuple)) else b).strip()
                    if not txt:
                        continue
                    bi += 1
                    out.append({"paragraph_id": "pg%02d-b%02d" % (pno + 1, bi), "page": pno + 1,
                                "heading": None, "offset_start": 0, "offset_end": len(txt), "text": txt})
                if not blocks and hasattr(page, "extract_text"):
                    txt = (page.extract_text() or "").strip()
                    if txt:
                        for bi, seg in enumerate([s for s in re.split(r"\n\s*\n", txt) if s.strip()] or [txt]):
                            out.append({"paragraph_id": "pg%02d-p%02d" % (pno + 1, bi + 1), "page": pno + 1,
                                        "heading": None, "offset_start": 0, "offset_end": len(seg), "text": seg.strip()})
            except Exception:
                continue
    except Exception:
        pass
    try:
        if doc is not None:
            doc.close()
    except Exception:
        pass
    if not out:
        return [], "scanned_no_text_layer"
    return out, None

def find_paragraphs(locator, keyword):
    hits = []
    kw = clean(keyword)
    if not kw:
        return hits
    for p in locator.get("paragraphs", []):
        try:
            pos = clean(p["text"]).find(kw)
            if pos >= 0:
                hits.append({"paragraph_id": p["paragraph_id"], "page": p.get("page"),
                             "heading": p.get("heading"), "char_hit_rate": round(pos / max(1, len(p["text"])), 3)})
        except Exception:
            continue
    return hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/work/locator.json")
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--find", default=None, help="关键词定位：输出命中段落清单")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest(a)

    def write(loc):
        try:
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(loc, f, ensure_ascii=False, indent=1)
            return True
        except Exception as e:
            print("[build_locator] FAIL: 写出失败: %s" % e)
            return False

    try:
        with open(a.case, "r", encoding="utf-8", errors="replace") as f:
            case = json.load(f)
    except Exception as e:
        case = {}
        print("[build_locator] WARN: case.json 读取失败: %s" % e)

    # --find 模式：读已有 locator 做关键词定位
    if a.find is not None:
        try:
            with open(a.out, "r", encoding="utf-8") as f:
                loc = json.load(f)
        except Exception:
            loc = {"paragraphs": []}
        hits = find_paragraphs(loc, a.find)
        print(json.dumps({"keyword": a.find, "hits": hits}, ensure_ascii=False, indent=1))
        return 0

    paras, mtype, note = None, None, None
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections", "sentences", "blocks"):
        v = case.get(key)
        if isinstance(v, list) and v:
            paras, mtype = index_paragraph_list(v), "paragraph-json"
            break
    if paras is None:
        try:
            for root, _d, files in os.walk(a.input_root):
                pdfs = sorted(fn for fn in files if fn.lower().endswith(".pdf"))
                texts = sorted(fn for fn in files if fn.lower().endswith((".txt", ".md")))
                if pdfs:
                    paras, note = index_pdf(os.path.join(root, pdfs[0]))
                    mtype = "pdf"
                    break
                if texts:
                    fp = os.path.join(root, texts[0])
                    paras, mtype, note = index_text(fp), os.path.splitext(texts[0])[1].lstrip("."), fp
                    break
        except Exception as e:
            note = "walk-failed: %s" % e
    if paras is None:
        paras, mtype, note = [], "unknown", "no indexable material found"
    loc = {"case_id": case.get("case_id"), "material_type": mtype,
           "paragraphs": paras, "count": len(paras), "note": note}
    if write(loc):
        print("[build_locator] type=%s paragraphs=%d note=%s -> %s" % (mtype, len(paras), note, a.out))
        return 0 if paras else 1
    return 1

def selftest(a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        # 正例1：paragraph-json
        cp = os.path.join(td, "case.json")
        with open(cp, "w", encoding="utf-8") as f:
            json.dump({"case_id": "T1", "paragraphs": [
                {"paragraph_id": "p01", "text": "Alpha method improves recall by 12%. ", "page": 1},
                {"paragraph_id": "p02", "text": "Beta baseline fails on scanned input."}], "output_contract": {}}, f)
        o1 = os.path.join(td, "l1.json")
        r = subprocess_run(["--case", cp, "--out", o1, "--input-root", td])
        loc = json.load(open(o1, encoding="utf-8"))
        if loc["count"] != 2:
            print("  [selftest] 正例1 段落数错误 FAIL"); ok = False
        # 正例2：关键词定位（locator 已存在于 o1）
        r2 = subprocess_run(["--case", cp, "--out", o1, "--find", "Alpha method"])
        if '"hits": []' in r2 or not r2.strip():
            print("  [selftest] 正例2 关键词定位失败 FAIL"); ok = False
        # 反例1：case 缺失 → 仍写出空索引
        o3 = os.path.join(td, "l3.json")
        subprocess_run(["--case", os.path.join(td, "ghost.json"), "--out", o3, "--input-root", td])
        loc3 = json.load(open(o3, encoding="utf-8"))
        if "paragraphs" not in loc3:
            print("  [selftest] 反例1: case 缺失时未写出索引 FAIL"); ok = False
        # 反例2：二进制乱码 txt
        tp = os.path.join(td, "bad.txt")
        with open(tp, "wb") as f:
            f.write(bytes(range(256)) * 4)
        o4 = os.path.join(td, "l4.json")
        subprocess_run(["--case", cp, "--out", o4, "--input-root", td])
        if not os.path.exists(o4):
            print("  [selftest] 反例2 未写出 FAIL"); ok = False
    print("[build_locator] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

def subprocess_run(args):
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        old_argv = sys.argv
        sys.argv = ["build_locator.py"] + args
        try:
            main()
        except SystemExit:
            pass
        except Exception as e:
            print("EXC %s" % e)
        finally:
            sys.argv = old_argv
    return buf.getvalue()

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_locator] 兜底异常: %s" % e)
        sys.exit(1)
