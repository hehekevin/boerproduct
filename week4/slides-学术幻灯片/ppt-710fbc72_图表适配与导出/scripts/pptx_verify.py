#!/usr/bin/env python3
"""pptx_verify.py — 双模式闸门中枢（构建前 PLAN / 构建后 pptx），含版面预算。

构建前闸门（无 pptx 也跑）：
  quote 闸门：每条证据 quote 空白归一化后逐字出现在论文原文（改写/取整即抓）
  数字闸门：页面百分数/小数/带单位数必须在该页 quote 里逐字出现 (numeric_unbacked)
  覆盖闸门：每页至少一条证据行
  页面卫生：notes 40-800 字非复述、要点 ≤5 条、单页 ≤700 字符
构建后模式：页数/标题/密度/notes/图/几何 + quote_gate。
版面预算（内联，周3版 measure_lines 恒返 0 的缺陷已修复）：
  CJK≈1.0em、Latin≈0.55em，阶梯 18→16→14→12→11→10，10pt 仍溢出=trim 删内容。

闸门四态：enforced / skipped_not_provided / not_found / unreadable —— 未跑绝不报通过。
退出码恒 0：verdict/报告如实传递，非零退出码会中断平台会话。
"""
import argparse
import json
import math
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
QUOTE_TYPES = {"quote", "data", "number", "fact"}

# ---- 版面预算（内联模块，供 pptx_build 复用） ----
LINE_SPACING = 1.32
PARA_SPACING_PT = 6.0
LADDER = [18, 16, 14, 12, 11, 10]
MIN_FLOOR = 10  # 阶梯下限：10pt 仍溢出=trim 删内容，不许再缩到不可读
_CJK = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF\u3000-\u303F]")


def text_em_width(text, font_pt):
    cjk = len(_CJK.findall(text))
    latin = len(text) - cjk
    return cjk * font_pt * 1.0 + latin * font_pt * 0.55


def measure_lines(text, box_width_in, font_pt):
    """估算行数。注意：不用 str.isalpha 分类（汉字 isalpha()==True 会误判），用 CJK 区段正则。"""
    box_pt = box_width_in * 72.0
    w = text_em_width(text, font_pt)
    if w <= 0 or box_pt <= 0:
        return 1
    return max(1, math.ceil(w / box_pt))


def budget_slide(slide, box_w_in, box_h_in, ladder=None, floor=None):
    ladder = ladder or LADDER
    floor = floor or MIN_FLOOR
    bullets = list(slide.get("bullets") or [])
    for col in slide.get("columns", []) or []:
        bullets.extend(col)
    rows = (slide.get("table") or {}).get("rows") or []
    best = None
    for fs in ladder:
        if fs < floor:
            break
        total = sum(measure_lines((b.get("text", "") if isinstance(b, dict) else str(b)),
                                  box_w_in, fs) for b in bullets)
        total += len(rows) + sum(measure_lines(" ".join(r), box_w_in, fs) - 1 for r in rows)
        need = total * fs * LINE_SPACING + max(0, len(bullets) - 1) * PARA_SPACING_PT
        avail = box_h_in * 72.0
        ok = need <= avail
        best = {"font_pt": fs, "fits": ok, "lines_total": total,
                "height_needed_pt": round(need, 1), "height_avail_pt": round(avail, 1),
                "action": ("ok" if fs == ladder[0] else "shrunk") if ok else "trim"}
        if ok:
            break
    if best is None:
        fs = floor
        total = sum(measure_lines((b.get("text", "") if isinstance(b, dict) else str(b)),
                                  box_w_in, fs) for b in bullets)
        best = {"font_pt": fs, "fits": False, "lines_total": total,
                "height_needed_pt": None, "height_avail_pt": box_h_in * 72.0, "action": "trim"}
    return best


def budget_title(slide, box_w_in, font_pt, max_lines=2):
    lines = measure_lines(slide.get("title", ""), box_w_in, font_pt)
    return {"lines": lines, "fits": lines <= max_lines}


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
    if body and nn[: len(body)] == body:
        return {"ok": False, "reason": "notes_duplicate_body"}
    if body:
        ratio = len(set(body) & set(nn)) / max(1, len(set(body) | set(nn)))
        if ratio > 0.85:
            return {"ok": False, "reason": "notes_near_duplicate", "jaccard": round(ratio, 2)}
    return {"ok": True, "len": len(notes)}


# ---- pptx 解析（python-pptx 优先，raw-xml 兜底） ----
def open_pptx(path):
    try:
        from pptx import Presentation
        from pptx.util import Emu
        prs = Presentation(path)
        slides = []
        for sl in prs.slides:
            texts, boxes, images = [], [], 0
            for sh in sl.shapes:
                if sh.shape_type == 13 or getattr(sh, "image", None) is not None:
                    images += 1
                if sh.has_text_frame:
                    t = sh.text_frame.text.strip()
                    if t:
                        texts.append(t)
                    boxes.append((sh.left, sh.top, sh.width, sh.height))
            notes = sl.notes_slide.notes_text_frame.text.strip() if sl.has_notes_slide else ""
            slides.append({"texts": texts, "images": images, "notes": notes,
                           "boxes_in": [[round(Emu(b[0]).inches, 2), round(Emu(b[1]).inches, 2),
                                         round(Emu(b[2]).inches, 2), round(Emu(b[3]).inches, 2)]
                                        for b in boxes]})
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
        images = sum(1 for sp in root.iter() if sp.tag.split("}")[-1] == "pic")
        texts = [t.text.strip() for t in root.iter("{%s}t" % NS["a"]) if t.text and t.text.strip()]
        notes = ""
        nn = "ppt/notesSlides/notesSlide%d.xml" % i
        if nn in z.namelist():
            nroot = ET.fromstring(z.read(nn))
            notes = " ".join(t.text or "" for t in nroot.iter("{%s}t" % NS["a"])).strip()
        slides.append({"texts": texts, "images": images, "notes": notes, "boxes_in": []})
    return slides


def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\d+\.\d+|\d+(?:\.\d+)?\s*(?:x|×|倍|万|亿|GB|MB|ms|s|h|K|k)")


def numeric_tokens(text):
    out = []
    for m in NUM_RE.findall(str(text or "")):
        t = _norm(m)
        if t and t not in out:
            out.append(t)
    return out


def _slide_flat(row):
    parts = [row.get("title") or ""]
    for b in row.get("bullets") or []:
        parts.append(b.get("text", "") if isinstance(b, dict) else str(b))
    for col in row.get("columns") or []:
        for b in col or []:
            parts.append(b.get("text", "") if isinstance(b, dict) else str(b))
    for r in ((row.get("table") or {}).get("rows") or row.get("rows") or []):
        parts.extend(str(c) for c in r)
    parts.append(((row.get("figure") or {}).get("caption") or ""))
    return " ".join(parts)


def load_ev_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    rows.append({"_parse_error": line[:120]})
    return rows


def check_quote_gate(ev_rows, paper_path):
    """quote 逐字回证论文原文（空白归一化子串匹配）。"""
    try:
        paper = open(paper_path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        return {"status": "unreadable", "error": "%s: %s" % (type(e).__name__, e),
                "rows": 0, "fail": 0, "fails": []}
    pn = _norm(paper).lower()
    fails, n_checked = [], 0
    for i, r in enumerate(ev_rows):
        if "_parse_error" in r:
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                          "reason": "evidence_json_parse_error"})
            continue
        typ = (r.get("type") or "").lower()
        quote, locator = r.get("quote"), (r.get("locator") or "")
        if quote:
            n_checked += 1
            qn = _norm(quote).lower()
            if not qn or qn not in pn:
                fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                              "reason": "quote_not_found_in_paper",
                              "hint": qn[:12], "locator": locator})
        elif typ in QUOTE_TYPES:
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                          "reason": "missing_required_quote", "locator": locator})
        elif not locator.strip():
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                          "reason": "structural_ref_missing_locator"})
    return {"status": "enforced", "rows": len(ev_rows), "quotes_checked": n_checked,
            "fail": len(fails), "fails": fails}


def check_slide_coverage(deck, ev_rows):
    """页面数字必须在该页 quote 里逐字出现；无证据行=fail。"""
    by_slide = {}
    for r in ev_rows:
        s = r.get("slide_no")
        if s is not None:
            by_slide.setdefault(s, []).append(r)
    out = []
    for row in (deck or {}).get("slides", []):
        s = row.get("no")
        ev = by_slide.get(s, [])
        flat = _slide_flat(row)
        backed = _norm(" ".join((e.get("quote") or "") for e in ev))
        unbacked = [t for t in numeric_tokens(flat) if t not in backed]
        out.append({"slide_no": s, "role": row.get("role"), "evidence_rows": len(ev),
                    "has_locator": all(bool((e.get("locator") or "").strip()) for e in ev) if ev else False,
                    "notes_chars": len(row.get("notes") or ""),
                    "numeric_tokens": numeric_tokens(flat), "numeric_unbacked": unbacked,
                    "verdict": "pass" if (ev and not unbacked) else ("fail" if not ev else "warn")})
    return out


def build_slides_embed(deck, ev_rows):
    """逐页合并 plan 与证据行，供 result.json 全量内嵌（机器生成，禁止手写）。"""
    by_slide = {}
    for r in ev_rows:
        s = r.get("slide_no")
        if s is not None:
            by_slide.setdefault(s, []).append(
                {"type": r.get("type"), "locator": r.get("locator"),
                 "quote": r.get("quote"), "figure_mode": r.get("figure_mode")})
    out = []
    for row in (deck or {}).get("slides", []):
        s = row.get("no")
        out.append({"no": s, "role": row.get("role"),
                    "title": row.get("title") or row.get("claim"),
                    "bullets": row.get("bullets"), "columns": row.get("columns"),
                    "table": row.get("table"), "figure": row.get("figure"),
                    "figure_ref": row.get("figure_ref"), "notes": row.get("notes"),
                    "evidence": by_slide.get(s, [])})
    return out


def _input_status(path, provided):
    if not provided:
        return {"status": "skipped_not_provided", "path": None}
    if not os.path.exists(path):
        return {"status": "not_found", "path": path}
    return {"status": "loaded", "path": path}


def run_gates(plan, ev_rows, paper_path):
    """公共闸门集（PLAN 与构建后模式共用；gain_evidence --ablate 也复用）。"""
    report = {"fail": 0, "warn": 0}
    st_paper = _input_status(paper_path, bool(paper_path))
    if st_paper["status"] == "loaded" and ev_rows:
        report["quote_gate"] = check_quote_gate(ev_rows, paper_path)
        report["fail"] += report["quote_gate"]["fail"]
    else:
        reason = st_paper["status"] if st_paper["status"] != "loaded" else "skipped_no_evidence"
        report["quote_gate"] = {"status": reason, "rows": len(ev_rows), "fail": 0, "fails": [],
                                "note": "quote 逐字回证未执行，下游不得宣称已核对；须在 uncertainty 登记"}
        report["warn"] += 1
    cov = []
    if ev_rows:
        cov = check_slide_coverage(plan, ev_rows)
        n_warn = sum(1 for c in cov if c["verdict"] == "warn")
        n_fail = sum(1 for c in cov if c["verdict"] == "fail")
        report["warn"] += n_warn
        report["fail"] += n_fail
        report["coverage_gate"] = {"status": "enforced", "fail_slides": n_fail, "warn_slides": n_warn}
    else:
        report["coverage_gate"] = {"status": "skipped_no_evidence",
                                   "note": "证据覆盖与数字对账未执行，下游不得宣称已核对"}
        report["warn"] += 1
    report["slide_coverage"] = cov
    return report


def run_plan_gate(args):
    plan = json.load(open(args.deck, encoding="utf-8"))
    st_ev = _input_status(args.evidence, bool(args.evidence))
    report = {"mode": "plan_gate", "deck": args.deck, "inputs": {"evidence": st_ev}}

    ev_rows = []
    if st_ev["status"] == "loaded":
        ev_rows = load_ev_rows(args.evidence)
    elif st_ev["status"] == "not_found":
        report["warn"] = 1

    g = run_gates(plan, ev_rows, args.paper)
    report.update(g)
    report["slides_embed"] = build_slides_embed(plan, ev_rows)

    page_issues = []
    for row in plan.get("slides", []):
        issues = []
        flat = _slide_flat(row)
        nb = check_notes({"notes": row.get("notes") or ""}, flat)
        if not nb.get("ok"):
            issues.append("notes:%s" % json.dumps(nb, ensure_ascii=False))
        if len(row.get("bullets") or []) > 5:
            issues.append("too_many_bullets(%d)" % len(row.get("bullets")))
        if len(flat) > 700:
            issues.append("page_too_dense(%d chars)" % len(flat))
        if issues:
            page_issues.append({"slide_no": row.get("no"), "issues": issues})
    report["page_hygiene"] = page_issues
    report["fail"] += len(page_issues)

    report["summary"] = {"fail": report["fail"], "warn": report["warn"],
                         "verdict": "pass" if report["fail"] == 0 else "fail",
                         "quote_gate_status": report["quote_gate"]["status"],
                         "quote_gate_fails": report["quote_gate"]["fail"],
                         "numeric_unbacked": {c["slide_no"]: c["numeric_unbacked"]
                                              for c in report["slide_coverage"] if c["numeric_unbacked"]},
                         "coverage_fail_slides": [c["slide_no"] for c in report["slide_coverage"]
                                                  if c["verdict"] == "fail"]}
    out = args.out or "gate_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("plan_gate:", json.dumps(report["summary"], ensure_ascii=False), "->", out)
    for p in page_issues:
        print("  page", json.dumps(p, ensure_ascii=False))
    for fq in report["quote_gate"].get("fails") or []:
        print("  quote_gate", json.dumps(fq, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx", help="deck.pptx path, or literal PLAN for pre-build gate mode")
    ap.add_argument("deck")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--paper", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.pptx.upper() == "PLAN":
        try:
            return run_plan_gate(args)
        except Exception as e:
            with open(args.out or "gate_report.json", "w", encoding="utf-8") as f:
                json.dump({"mode": "plan_gate", "ok": False,
                           "error": "%s: %s" % (type(e).__name__, e),
                           "summary": {"verdict": "fail", "fail": 0, "warn": 0}}, f,
                          ensure_ascii=False, indent=1)
            print("plan_gate crashed (registered honestly, exit 0):", e)
            return 0

    plan = json.load(open(args.deck, encoding="utf-8"))
    slides, engine = open_pptx(args.pptx)
    report = {"pptx": args.pptx, "engine": engine,
              "slide_count": {"planned": len(plan.get("slides", [])), "actual": len(slides),
                              "match": len(slides) == len(plan.get("slides", []))},
              "fail": 0, "warn": 0}
    if not report["slide_count"]["match"]:
        report["fail"] += 1

    st_ev = _input_status(args.evidence, bool(args.evidence))
    report["inputs"] = {"evidence": st_ev}
    ev_rows = []
    if st_ev["status"] == "loaded":
        ev_rows = load_ev_rows(args.evidence)
    elif st_ev["status"] == "not_found":
        report["warn"] += 1
    ev_slides = sorted(set(r.get("slide_no") for r in ev_rows if r.get("slide_no") is not None))
    report["evidence_map"] = {"rows": len(ev_rows), "slides_covered": ev_slides,
                              "covers_all": bool(ev_rows) and ev_slides
                              and ev_slides[0] == 1 and ev_slides[-1] == len(slides)
                              and len(ev_slides) >= len(slides)}
    if ev_rows and not report["evidence_map"]["covers_all"]:
        report["warn"] += 1

    g = run_gates(plan, ev_rows, args.paper)
    report.update(g)
    report["slides_embed"] = build_slides_embed(plan, ev_rows)

    for i, (sl, plan_sl) in enumerate(zip(slides, plan.get("slides", [])), 1):
        row = {"no": i, "checks": {}}
        texts = " ".join(sl["texts"])
        plan_layout = plan_sl.get("layout", "bullets") if plan_sl else "?"
        row["checks"]["has_text"] = bool(sl["texts"])
        row["checks"]["title"] = bool(re.search(r"\S", texts)) if plan_layout in (
            "title", "section", "closing") else bool(sl["texts"])
        if not row["checks"]["has_text"]:
            row["checks"]["has_text_verdict"] = "fail"
            report["fail"] += 1
        if not row["checks"]["title"] and plan_layout not in ("figure", "blank"):
            row["checks"]["title_verdict"] = "fail"
            report["fail"] += 1
        body_chars = sum(len(t) for t in sl["texts"])
        row["checks"]["body_density"] = {"chars": body_chars, "over_limit": body_chars > 700}
        if body_chars > 700:
            row["checks"]["body_density"]["verdict"] = "warn"
            report["warn"] += 1
        nb = check_notes({"notes": sl["notes"]}, texts)
        row["checks"]["notes"] = nb
        if not nb.get("ok"):
            row["checks"]["notes"]["verdict"] = "fail"
            report["fail"] += 1
        want_fig = bool((plan_sl or {}).get("figure"))
        row["checks"]["figure"] = {"planned": want_fig, "embedded_images": sl["images"],
                                   "ok": (sl["images"] >= 1) if want_fig else True}
        if want_fig and sl["images"] < 1:
            row["checks"]["figure"]["verdict"] = "fail"
            report["fail"] += 1
        geo_ok = True
        for b in sl.get("boxes_in", []):
            x, y, w, h = b
            if x < -0.05 or y < -0.05 or x + w > 13.4 or y + h > 7.6:
                geo_ok = False
        row["checks"]["geometry_in_bounds"] = geo_ok
        if not geo_ok:
            report["fail"] += 1
        report.setdefault("slides", []).append(row)

    report["summary"] = {
        "fail": report["fail"], "warn": report["warn"],
        "verdict": "pass" if report["fail"] == 0 else "fail",
        "quote_gate_status": report["quote_gate"]["status"],
        "quote_gate_fails": report["quote_gate"]["fail"],
        "numeric_unbacked": {c["slide_no"]: c["numeric_unbacked"] for c in report["slide_coverage"]
                             if c["numeric_unbacked"]},
        "coverage_fail_slides": [c["slide_no"] for c in report["slide_coverage"]
                                 if c["verdict"] == "fail"]}
    out = args.out or (os.path.splitext(args.pptx)[0] + ".verify_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("verify:", json.dumps(report["summary"], ensure_ascii=False), "->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
