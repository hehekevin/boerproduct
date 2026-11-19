#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inventory.py — 内容单元清单与转换保真对比（转得全）

scan：把稿件（md 或 docx）拆成内容单元（标题/段落/表格/图/公式/脚注/引用标记/参考文献条目），
每单元带 type/序号/规范化文本/内容哈希 → inventory.json。
compare：对照两份清单（转换前 vs 转换后），逐单元对齐（同类型按顺序+哈希+文本相似度），
输出 missing/added/changed（内容被改写）——内容单元被删除、合并、改写即被抓出。

用法:
  python3 scripts/inventory.py scan --doc draft.md --out inv_src.json
  python3 scripts/inventory.py compare --a inv_src.json --b inv_adp.json --out fidelity_report.json
退出码恒 0；verdict 如实写 JSON。
"""
import argparse, hashlib, json, os, re, sys, time, zipfile, difflib

try:
    import _rlog
except Exception:
    _rlog = None

RE_HEADING = re.compile(r"^\s*(#{1,6})\s*(.+)$")
RE_FIGNOTE = re.compile(r"^\s*(?:!\[[^\]]*\]\([^)]*\)\s*)?\**\s*(图\s*\d+|表\s*\d+|Figure\s*\d+|Fig\.?\s*\d+|Table\s*\d+)\b", re.I)
RE_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
RE_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
RE_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,，\-]\s*\d{1,3})*)\]")
RE_FORMULA = re.compile(r"\$[^$\n]+\$|\\\[(?:.|\n)*?\\\]")
RE_FOOTNOTE = re.compile(r"\[\^(\d+|[a-z]+)\]")
RE_REF_ENTRY = re.compile(r"^\s*[\[(]?(\d{1,3})[\]).]\s+\S")


def docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        lines = [re.sub(r"<[^>]+>", "", p) for p in xml.split("</w:p>")]
        return "\n".join(l for l in lines if l.strip())
    except Exception:
        return None


def norm_text(s):
    return re.sub(r"\s+", "", s or "")


def h(s):
    return hashlib.sha1(norm_text(s).encode("utf-8")).hexdigest()[:12]


def scan_md(text):
    units, in_refs, para_buf = [], False, []

    def flush():
        if para_buf:
            t = " ".join(para_buf).strip()
            if t:
                units.append({"type": "paragraph", "text": t})
            para_buf.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()  # 空行=段落分隔
            continue
        if RE_HEADING.match(line):
            flush()
            m = RE_HEADING.match(line)
            units.append({"type": "heading", "level": len(m.group(1)), "text": m.group(2).strip()})
            in_refs = bool(re.search(r"参考\s*文献|References", m.group(2), re.I))
            continue
        if RE_TABLE_SEP.match(line):
            continue
        if RE_TABLE_ROW.match(line):
            flush()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if units and units[-1]["type"] == "table":
                units[-1]["rows"].append(cells)
            else:
                units.append({"type": "table", "rows": [cells], "text": ""})
            continue
        if RE_REF_ENTRY.match(line) and (in_refs or re.match(r"^\s*\[\d+\]", line)):
            flush()
            units.append({"type": "reference", "text": line.strip()})
            continue
        m = RE_FIGNOTE.match(line)
        if m and len(line) < 220:
            flush()
            units.append({"type": "figure" if re.match(r"图|Figure|Fig", m.group(1), re.I) else "table_caption",
                          "text": line.strip().lstrip("*![]()").strip()})
            continue
        if line.strip():
            para_buf.append(line.strip())
    flush()
    return units


def build_inventory(text, doc_path):
    units = scan_md(text)
    body = "\n".join(u.get("text", "") + " " + " ".join(" ".join(r) for r in (u.get("rows") or [])) for u in units)
    counters = {}
    for u in units:
        t = u["type"]
        counters[t] = counters.get(t, 0) + 1
        u["uid"] = "%s-%02d" % (t[:4].upper(), counters[t])
        u["hash"] = h(u.get("text", "") + json.dumps(u.get("rows", []), ensure_ascii=False))
        u["chars"] = len(norm_text(u.get("text", "")))
        u.pop("rows", None)
        u.pop("level", None)
    citations = sorted({int(p.strip()) for m in RE_CITE.finditer(body) for p in re.split(r"[,，\-]", m.group(1)) if p.strip().isdigit()})
    formulas = [norm_text(m.group(0))[:60] for m in RE_FORMULA.finditer(body)]
    footnotes = sorted({m.group(1) for m in RE_FOOTNOTE.finditer(body)})
    return {"source_doc": doc_path, "total": len(units), "by_type": counters,
            "units": units, "citations": citations, "formulas": formulas[:40],
            "footnotes": footnotes}


RE_NUM_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*|第?[一二三四五六七八九十]+[章节])[、.\s]*")


def _cmp_text(u):
    """标题对比剥离编号前缀：重编号属机械适配，不视为内容改写。"""
    t = u.get("text", "")
    if u.get("type") == "heading":
        t = RE_NUM_PREFIX.sub("", t)
    return norm_text(t)


def compare(a, b):
    ua, ub = a.get("units") or [], b.get("units") or []
    used, missing, changed, matched = set(), [], [], 0
    for x in ua:
        cand = [j for j, y in enumerate(ub) if j not in used and y["type"] == x["type"]]
        exact = [j for j in cand if ub[j]["hash"] == x["hash"]]
        if exact:
            used.add(exact[0]); matched += 1; continue
        pick, best = None, 0.0
        for j in cand:
            r = difflib.SequenceMatcher(None, _cmp_text(x), _cmp_text(ub[j])).ratio()
            if r > best:
                best, pick = r, j
        if pick is not None and best >= 0.75:
            used.add(pick); matched += 1
            changed.append({"ref": x["uid"], "other": ub[pick]["uid"], "similarity": round(best, 3),
                            "before": (x.get("text") or "")[:60], "after": (ub[pick].get("text") or "")[:60]})
        else:
            missing.append({"ref": x["uid"], "type": x["type"], "text": (x.get("text") or "")[:60]})
    added = [{"ref": y["uid"], "type": y["type"], "text": (y.get("text") or "")[:60]}
             for j, y in enumerate(ub) if j not in used]
    total = len(ua) or 1
    fidelity = round(matched / total, 3)
    dropped = [c for c in (a.get("citations") or []) if c not in (b.get("citations") or [])]
    lost_f = [f for f in (a.get("formulas") or []) if f not in (b.get("formulas") or [])]
    lost_fn = [f for f in (a.get("footnotes") or []) if f not in (b.get("footnotes") or [])]
    verdict = "pass" if not (missing or dropped or lost_f or lost_fn) else (
        "changed_only" if not missing else "fail")
    return {"source_total": len(ua), "adapted_total": len(ub), "matched": matched,
            "missing": missing, "added": added, "changed": changed[:60],
            "citations_dropped": dropped, "formulas_lost": lost_f[:20], "footnotes_lost": lost_fn,
            "fidelity_rate": fidelity,
            "verdict": verdict,
            "note": "missing=内容单元丢失；changed=被改写(similarity≥0.75 记录 diff)；citations_dropped/formulas_lost=引用/公式未保留",
            "exit_code_policy": "always_zero"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["scan", "compare"], default=None)
    ap.add_argument("--doc", default=None)
    ap.add_argument("--a", default=None)
    ap.add_argument("--b", default=None)
    ap.add_argument("--out", default=None)
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None or not args.cmd:
        print(json.dumps({"ok": False, "note": "用法: inventory.py scan|compare（argparse 错误为非致命，恒 exit 0）",
                          "detail": str(err) if err else "missing command"}, ensure_ascii=False))
        return 0
    t0 = time.time()
    out = {}
    if args.cmd == "scan":
        doc = args.doc
        text = None
        if doc and os.path.exists(doc):
            if doc.lower().endswith(".docx"):
                text = docx_text(doc)
            else:
                try:
                    text = open(doc, encoding="utf-8", errors="ignore").read()
                except Exception:
                    text = None
        if not text:
            inv = {"source_doc": doc, "total": 0, "by_type": {}, "units": [], "citations": [],
                   "formulas": [], "footnotes": [], "gate": "unreadable",
                   "note": "稿件不可读：清单为空，下游不得宣称保真已核对"}
        else:
            inv = build_inventory(text, doc)
            inv["gate"] = "enforced"
        out = inv
    else:
        a = load(args.a); b = load(args.b)
        if not isinstance(a, dict) or not isinstance(b, dict):
            out = {"verdict": "fail", "gate": "unreadable",
                   "note": "清单 A/B 不可读：保真对比未运行，下游不得宣称内容未丢失"}
        else:
            out = compare(a, b)
            out["a"] = args.a; out["b"] = args.b
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        try:
            json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            out["written"] = True
        except Exception as e:
            out["written"] = False; out["write_error"] = str(e)[:200]
    print(json.dumps({"ok": True, "cmd": args.cmd,
                      "total": out.get("total") if args.cmd == "scan" else out.get("source_total"),
                      "verdict": out.get("verdict"), "out": args.out}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("inventory", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"cmd": args.cmd, "verdict": out.get("verdict")})
    return 0


def load(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
