#!/usr/bin/env python3
"""gate_verify.py — 学术 PPT 双模式校验器（构建前闸门 / 构建后校验）。

模式：
  PLAN   gate_verify.py PLAN deck.json --source source_text.txt --evidence ev.jsonl --out gate.json
  构建后  gate_verify.py deck.pptx deck.json --source ... --evidence ... --out verify.json

闸门（四态：enforced / skipped_not_provided / not_found / unreadable，未跑≠通过）：
  A content_gate   内容对齐：quote 逐字回证材料原文 + 页面数字回证同页 quote
  B structure_gate 结构校验：页数约束、备注规范、要点≤5、单页密度、布局预算

消融开关（增益层专用，正常调用不得使用）：
  --skip-content-gate    关闭内容对齐闸门（模拟基础 Agent 不做证据回证）
  --skip-structure-gate  关闭结构校验（模拟基础 Agent 不做版面预算）

退出码恒 0：verdict 照实写 JSON，fail 不冒泡中断平台会话。
注意：分词/计数一律用正则，不用 str.isalpha（汉字 isalpha==True 会误判）。
"""
import argparse
import json
import math
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
QUOTE_TYPES = {"quote", "data", "number", "fact"}
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\d+\.\d+|\d+(?:\.\d+)?\s*(?:x|×|倍|万|亿|GB|MB|ms|s|h|K|k)")
_CJK = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF\u3000-\u303F]")
LADDER = [18, 16, 14, 12, 11, 10]
LINE_SPACING, PARA_SPACING_PT = 1.32, 6.0


# ---------- 版面预算（确定性，构建前防溢出） ----------
def text_em_width(text, font_pt):
    cjk = len(_CJK.findall(text))
    return cjk * font_pt * 1.0 + (len(text) - cjk) * font_pt * 0.55


def measure_lines(text, box_width_in, font_pt):
    box_pt = max(box_width_in * 72.0, 1.0)
    return max(1, math.ceil(text_em_width(text, font_pt) / box_pt))


def budget_slide(slide, box_w_in=11.5, box_h_in=5.0):
    bullets = list(slide.get("bullets") or [])
    for col in slide.get("columns") or []:
        bullets.extend(col)
    rows = (slide.get("table") or {}).get("rows") or []
    for fs in LADDER:
        total = sum(measure_lines(b.get("text", "") if isinstance(b, dict) else str(b),
                                  box_w_in, fs) for b in bullets)
        total += len(rows) + sum(measure_lines(" ".join(map(str, r)), box_w_in, fs) - 1 for r in rows)
        need = total * fs * LINE_SPACING + max(0, len(bullets) - 1) * PARA_SPACING_PT
        if need <= box_h_in * 72.0:
            return {"font_pt": fs, "fits": True, "lines_total": total, "action": "ok" if fs == LADDER[0] else "shrunk"}
    return {"font_pt": LADDER[-1], "fits": False, "lines_total": total, "action": "trim"}


def check_notes(slide, body_text):
    notes = (slide.get("notes") or "").strip()
    if not notes:
        return {"ok": False, "reason": "notes_missing"}
    if len(notes) < 40:
        return {"ok": False, "reason": "notes_too_short", "len": len(notes)}
    if len(notes) > 800:
        return {"ok": False, "reason": "notes_too_long", "len": len(notes)}
    body = re.sub(r"\s+", "", body_text or "")
    nn = re.sub(r"\s+", "", notes)
    if body and nn[:len(body)] == body:
        return {"ok": False, "reason": "notes_duplicate_body"}
    inter = set(body) & set(nn)
    if body and len(inter) / max(1, len(set(body) | set(nn))) > 0.85:
        return {"ok": False, "reason": "notes_near_duplicate"}
    return {"ok": True, "len": len(notes)}


# ---------- 解析 ----------
def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def numeric_tokens(text):
    out = []
    for m in NUM_RE.findall(str(text or "")):
        t = _norm(m)
        if t and t not in out:
            out.append(t)
    return out


def slide_flat(row):
    parts = [row.get("title") or row.get("claim") or ""]
    for b in row.get("bullets") or []:
        parts.append(b.get("text", "") if isinstance(b, dict) else str(b))
    for col in row.get("columns") or []:
        parts.extend(b.get("text", "") if isinstance(b, dict) else str(b) for b in col or [])
    for r in ((row.get("table") or {}).get("rows") or row.get("rows") or []):
        parts.extend(str(c) for c in r)
    parts.append((row.get("figure") or {}).get("caption") or "")
    return " ".join(parts)


def load_ev_rows(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        rows.append({"_parse_error": line[:120]})
    except Exception:
        pass
    return rows


def input_status(path, provided):
    if not provided:
        return {"status": "skipped_not_provided", "path": None}
    if not os.path.exists(path):
        return {"status": "not_found", "path": path}
    return {"status": "loaded", "path": path}


# ---------- 闸门 A：内容对齐 ----------
def check_content_gate(ev_rows, source_path):
    try:
        src = open(source_path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        return {"status": "unreadable", "error": "%s: %s" % (type(e).__name__, e),
                "rows": 0, "fail": 0, "fails": []}
    sn = _norm(src).lower()
    fails, n_checked = [], 0
    for i, r in enumerate(ev_rows):
        if "_parse_error" in r:
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"), "reason": "evidence_json_parse_error"})
            continue
        typ = (r.get("type") or "").lower()
        quote, locator = r.get("quote"), r.get("locator") or ""
        if quote:
            n_checked += 1
            qn = _norm(quote).lower()
            if not qn or qn not in sn:
                fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                              "reason": "quote_not_found_in_source", "hint": qn[:12], "locator": locator})
        elif typ in QUOTE_TYPES:
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"), "reason": "missing_required_quote"})
        elif not locator.strip():
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"), "reason": "structural_ref_missing_locator"})
    return {"status": "enforced", "rows": len(ev_rows), "quotes_checked": n_checked,
            "fail": len(fails), "fails": fails}


def check_numeric_backing(deck, ev_rows):
    by_slide = {}
    for r in ev_rows:
        s = r.get("slide_no")
        if s is not None:
            by_slide.setdefault(s, []).append(r)
    out = []
    for row in (deck or {}).get("slides", []):
        ev = by_slide.get(row.get("no"), [])
        flat = slide_flat(row)
        backed = _norm(" ".join((e.get("quote") or "") for e in ev))
        unbacked = [t for t in numeric_tokens(flat) if t not in backed]
        out.append({"slide_no": row.get("no"), "evidence_rows": len(ev),
                    "numeric_tokens": numeric_tokens(flat), "numeric_unbacked": unbacked,
                    "verdict": "pass" if (ev and not unbacked) else ("fail" if not ev else "warn")})
    return out


def build_slides_embed(deck, ev_rows):
    by_slide = {}
    for r in ev_rows:
        s = r.get("slide_no")
        if s is not None:
            by_slide.setdefault(s, []).append({"type": r.get("type"), "locator": r.get("locator"),
                                               "quote": r.get("quote"), "figure_mode": r.get("figure_mode")})
    return [{"no": row.get("no"), "role": row.get("role"), "title": row.get("title") or row.get("claim"),
             "bullets": row.get("bullets"), "columns": row.get("columns"), "table": row.get("table"),
             "figure": row.get("figure"), "notes": row.get("notes"), "evidence": by_slide.get(row.get("no"), [])}
            for row in (deck or {}).get("slides", [])]


# ---------- 闸门 B：结构校验 ----------
def check_structure_gate(deck, constraints=None):
    constraints = constraints or {}
    fails, per_page = [], []
    slides = (deck or {}).get("slides", [])
    max_n = constraints.get("max_slides")
    if max_n and len(slides) > int(max_n):
        fails.append({"reason": "slide_count_over_limit", "count": len(slides), "limit": int(max_n)})
    for row in slides:
        issues = []
        flat = slide_flat(row)
        nb = check_notes({"notes": row.get("notes") or ""}, flat)
        if not nb.get("ok"):
            issues.append("notes:%s" % nb.get("reason"))
        if len(row.get("bullets") or []) > 5:
            issues.append("too_many_bullets(%d)" % len(row.get("bullets")))
        if len(flat) > 700:
            issues.append("page_too_dense(%d chars)" % len(flat))
        bud = budget_slide(row)
        if not bud["fits"]:
            issues.append("layout_over_budget(font=%s)" % bud["font_pt"])
        if not (row.get("title") or row.get("claim")):
            issues.append("title_missing")
        if issues:
            per_page.append({"slide_no": row.get("no"), "issues": issues})
            fails.extend({"slide_no": row.get("no"), "reason": x} for x in issues)
    return {"status": "enforced", "fail": len(fails), "fails": fails, "pages": per_page}


# ---------- pptx 读取（构建后模式） ----------
def open_pptx(path):
    try:
        from pptx import Presentation
        prs = Presentation(path)
        slides = []
        for sl in prs.slides:
            texts, images = [], 0
            for sh in sl.shapes:
                if sh.shape_type == 13:
                    images += 1
                if sh.has_text_frame and sh.text_frame.text.strip():
                    texts.append(sh.text_frame.text.strip())
            notes = sl.notes_slide.notes_text_frame.text.strip() if sl.has_notes_slide else ""
            slides.append({"texts": texts, "images": images, "notes": notes})
        return slides, "python-pptx"
    except Exception:
        return raw_parse(path), "raw-xml"


def raw_parse(path):
    z = zipfile.ZipFile(path)
    names = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                   key=lambda n: int(re.search(r"(\d+)", n).group(1)))
    slides = []
    for i, n in enumerate(names, 1):
        root = ET.fromstring(z.read(n))
        texts = [t.text.strip() for t in root.iter("{%s}t" % NS_A) if t.text and t.text.strip()]
        images = sum(1 for e in root.iter() if e.tag.split("}")[-1] == "pic")
        notes = ""
        nn = "ppt/notesSlides/notesSlide%d.xml" % i
        if nn in z.namelist():
            nroot = ET.fromstring(z.read(nn))
            notes = " ".join(t.text or "" for t in nroot.iter("{%s}t" % NS_A)).strip()
        slides.append({"texts": texts, "images": images, "notes": notes})
    return slides


# ---------- 主流程 ----------
def run(args, mode):
    plan = {}
    try:
        plan = json.load(open(args.deck, encoding="utf-8"))
    except Exception as e:
        plan = {"slides": [], "_deck_unreadable": str(e)}
    constraints = {}
    if args.constraints and os.path.exists(args.constraints):
        try:
            constraints = json.load(open(args.constraints, encoding="utf-8"))
        except Exception:
            pass
    st_ev = input_status(args.evidence, bool(args.evidence))
    st_src = input_status(args.source, bool(args.source))
    ev_rows = load_ev_rows(args.evidence) if st_ev["status"] == "loaded" else []

    report = {"mode": mode, "deck": args.deck, "fail": 0, "warn": 0,
              "inputs": {"evidence": st_ev, "source": st_src}, "ablation": {
                  "content_gate": not args.skip_content_gate,
                  "structure_gate": not args.skip_structure_gate}}

    if args.skip_content_gate:
        report["content_gate"] = {"status": "ablated_off", "note": "消融臂：内容对齐闸门关闭，污染漏检计入对照", "fail": 0, "fails": []}
    elif st_src["status"] == "loaded" and ev_rows:
        report["content_gate"] = check_content_gate(ev_rows, args.source)
        report["fail"] += report["content_gate"]["fail"]
    else:
        reason = st_src["status"] if st_src["status"] != "loaded" else "skipped_no_evidence"
        report["content_gate"] = {"status": reason, "note": "内容对齐闸门未执行，下游不得宣称已核对", "fail": 0, "fails": []}
        report["warn"] += 1

    cov = []
    if ev_rows and not args.skip_content_gate:
        cov = check_numeric_backing(plan, ev_rows)
        report["fail"] += sum(1 for c in cov if c["verdict"] == "fail")
        report["warn"] += sum(1 for c in cov if c["verdict"] == "warn")
    report["slide_coverage"] = cov
    report["slides_embed"] = build_slides_embed(plan, ev_rows)

    if args.skip_structure_gate:
        report["structure_gate"] = {"status": "ablated_off", "note": "消融臂：结构校验关闭", "fail": 0, "fails": []}
    else:
        report["structure_gate"] = check_structure_gate(plan, constraints)
        report["fail"] += report["structure_gate"]["fail"]

    if mode == "verify":
        slides, engine = open_pptx(args.pptx)
        report["engine"] = engine
        report["slide_count"] = {"planned": len(plan.get("slides", [])), "actual": len(slides),
                                 "match": len(slides) == len(plan.get("slides", []))}
        if not report["slide_count"]["match"]:
            report["fail"] += 1
        for i, sl in enumerate(slides, 1):
            if not sl["texts"]:
                report["fail"] += 1
                report.setdefault("empty_slides", []).append(i)

    report["summary"] = {"fail": report["fail"], "warn": report["warn"],
                         "verdict": "pass" if report["fail"] == 0 else "fail",
                         "content_gate_status": report["content_gate"]["status"],
                         "content_gate_fails": report["content_gate"]["fail"],
                         "structure_gate_fails": report["structure_gate"]["fail"],
                         "numeric_unbacked": {c["slide_no"]: c["numeric_unbacked"] for c in cov if c["numeric_unbacked"]}}
    out = args.out or "gate_report.json"
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(json.dumps({"write_error": str(e)}, ensure_ascii=False))
    print(json.dumps({"mode": mode, "summary": report["summary"]}, ensure_ascii=False))
    return 0


class Exit0Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({"argparse_error": message, "note": "退出码 0，verdict 由报告照实传递"}, ensure_ascii=False))
        sys.exit(0)


def main():
    ap = Exit0Parser()
    ap.add_argument("pptx", help="deck.pptx 路径，或字面量 PLAN 表示构建前闸门")
    ap.add_argument("deck")
    ap.add_argument("--source", default=None, help="材料全文文本（quote 逐字回证依据）")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--constraints", default=None, help="workorder 约束 json（max_slides 等）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-content-gate", action="store_true")
    ap.add_argument("--skip-structure-gate", action="store_true")
    args = ap.parse_args()
    # 恒 0：argparse 错误也由 here 包装兜底；verdict 照实写报告
    try:
        run(args, "plan_gate" if args.pptx.upper() == "PLAN" else "verify")
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"fatal": str(e), "note": "校验器内部异常，退出码 0，verdict 未产出"}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
