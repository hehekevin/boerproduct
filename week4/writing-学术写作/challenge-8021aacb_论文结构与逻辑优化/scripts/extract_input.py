#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_input.py — 读取 /input：定位稿件、切章节、写 manuscript.json + constraints.json

稿件来源优先级：case.json 内长文本字段（manuscript/draft/text/content）> /input 下最大
文本文件（txt/md/tex/pdf/docx）。切章后每段保留原文，不增删事实。
退出码恒 0；找不到稿件时 sections=[] 且 notes 如实记录（调用方应置 status=blocked）。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog

HEAD_RE = re.compile(
    r"^(#{1,6}\s*\S.{0,120}\s*$"
    r"|\d+(?:\.\d+)*[、.．]?\s*\S.{0,120}\s*$"
    r"|[一二三四五六七八九十]+[、．]\s*\S.{0,120}\s*$"
    r"|(摘\s*要|引\s*言|结\s*论|参考文献|致\s*谢|实\s*验|相\s*关\s*工\s*作|讨\s*论|展\s*望)\s*$"
    r"|(abstract|introduction|related work|methods?|results?|discussion|conclusions?|references)\s*$)",
    re.IGNORECASE)
SKIP_FILES = ("case.json", "task.md", "changelog", "resources.yaml")
TEXT_KEYS = ("manuscript", "draft", "manuscript_text", "paper_text", "text", "content", "document")


def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF 可选增强
            doc = fitz.open(path)
            return "\n".join(pg.get_text() for pg in doc), "pdf_pymupdf"
        except Exception as e:
            return None, "pdf_needs_harness_pdf_text_tool:%s" % e
    if ext == ".docx":
        try:
            from docx import Document  # python-docx 可选增强
            return "\n".join(p.text for p in Document(path).paragraphs), "docx_pythondocx"
        except Exception as e:
            return None, "docx_needs_library:%s" % e
    if ext in (".txt", ".md", ".markdown", ".tex", ".rst"):
        return open(path, encoding="utf-8", errors="ignore").read(), "text"
    return None, "unsupported"


def find_manuscript(case, input_dir):
    notes = []
    for k in TEXT_KEYS:
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, str) and len(v) > 500:
            return v, "case_json:%s" % k, notes
    cand = []
    if os.path.isdir(input_dir):
        for root, _, fs in os.walk(input_dir):
            for f in sorted(fs):
                if f.startswith(".") or f.lower() in SKIP_FILES:
                    continue
                p = os.path.join(root, f)
                cand.append((os.path.getsize(p), p))
    cand.sort(reverse=True)
    for size, p in cand:
        txt, kind = read_text(p)
        if txt is None:
            notes.append({"file": os.path.basename(p), "status": kind})
            continue
        if len(txt.strip()) > 300:
            return txt, "file:%s(%s)" % (os.path.basename(p), kind), notes
    return None, None, notes


def split_sections(text):
    sections, cur, buf = [], None, []
    for raw in text.splitlines():
        line = raw.rstrip()
        if HEAD_RE.match(line.strip()) and len(line.strip()) < 130 and not line.strip().endswith(("。", "；", "，", ".")):
            if cur is not None:
                cur["paragraphs"] = paras(buf)
                sections.append(cur)
            h = line.strip().lstrip("#").strip()
            cur = {"id": "S%02d" % (len(sections) + 1), "heading": h,
                   "level": 1 if not line.strip().startswith("#") else min(6, line.strip().count("#")),
                   "paragraphs": []}
            buf = []
        else:
            buf.append(line)
    if cur is not None:
        cur["paragraphs"] = paras(buf)
        sections.append(cur)
    if not sections and text.strip():
        sections = [{"id": "S01", "heading": "(未识别章节标题)", "level": 1, "paragraphs": paras(text.splitlines())}]
    return [s for s in sections if s["paragraphs"] or s["heading"] != "(未识别章节标题)"]


def paras(lines):
    out, buf = [], []
    for line in lines:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(" ".join(buf)); buf = []
    if buf:
        out.append(" ".join(buf))
    return out


def detect_constraints(task_text):
    det = []
    for kw, label in (("受众", "受众"), ("体裁", "体裁"), ("字数", "篇幅"), ("格式", "格式"),
                      ("引用", "引用样式"), ("双语", "双语"), ("结构", "结构要求")):
        for line in (task_text or "").splitlines():
            if kw in line and len(line) < 200:
                det.append({"kind": label, "line": line.strip()[:150]})
                break
    return det


def main():
    t0 = __import__("time").time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--task", default="/input/task.md")
    ap.add_argument("--outdir", default="/app/work")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误，按默认路径继续"}))
        return 0
    notes = []
    case = {}
    try:
        case = json.load(open(args.case, encoding="utf-8"))
    except Exception as e:
        notes.append("case.json 不可解析: %s" % e)
    case_id = case.get("case_id") or case.get("id") or "unknown_case"

    text, source, notes2 = find_manuscript(case, args.input)
    notes += notes2
    sections = []
    if text:
        sections = split_sections(text)
        if not sections:
            notes.append("稿件文本存在但未切出任何章节/段落")
    else:
        notes.append("未找到可用稿件文本；结构诊断无法开工，status 应置 blocked")

    task_text = ""
    try:
        task_text = open(args.task, encoding="utf-8", errors="ignore").read()
    except Exception:
        notes.append("task.md 缺失或不可读")
    constraints = {"task_path": args.task,
                   "task_excerpt": task_text[:2000],
                   "detected": detect_constraints(task_text)}

    manuscript = {
        "case_id": case_id,
        "source": source,
        "sections": sections,
        "stats": {"sections": len(sections),
                  "paragraphs": sum(len(s["paragraphs"]) for s in sections),
                  "chars": sum(len(p) for s in sections for p in s["paragraphs"])},
        "notes": notes,
    }
    os.makedirs(args.outdir, exist_ok=True)
    json.dump(manuscript, open(os.path.join(args.outdir, "manuscript.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(constraints, open(os.path.join(args.outdir, "constraints.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "case_id": case_id, "source": source,
                      "sections": len(sections), "notes": len(notes)}, ensure_ascii=False))
    _rlog.log_call("extract_input", argv=sys.argv[1:], seconds=__import__("time").time() - t0,
                   extra={"sections": len(sections)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
