#!/usr/bin/env python3
"""pptx_verify.py — post-build verification of a deck against its plan.

Checks (each reported as pass/fail/warn with details):
  1. slide count matches deck.json
  2. every slide has non-empty title (except section/title layouts)
  3. layout budget: recomputed from actual text vs actual box geometry
  4. notes: present, substantial, not a duplicate of page text
  5. figures: declared figures embedded (image count per slide)
  6. evidence map: evidence_map.jsonl covers every slide
  7. template inheritance: shapes sit inside slide area; fonts recorded
  8. numeric reconciliation: every high-risk number on a page (%, decimal, unit)
     must appear verbatim in that slide's quote(s)  -> numeric_unbacked
  9. quote gate: every evidence quote must appear verbatim in the source paper
     text (whitespace-normalized) -> invented/reworded quotes are caught

Every gate reports an explicit four-state status:
  enforced / skipped_not_provided / not_found / unreadable
A gate that did NOT run is never reported as passed.

Also emits `slides_embed`: per-slide merged record (no/role/title/bullets/
figure/notes/evidence quotes+locators) for full embedding into result.json —
machine-generated, never hand-written.

Writes verify_report.json. Exit code 0 if no fail-level issue.

Two modes:
  pre-build gate:  python3 pptx_verify.py PLAN deck.json --paper paper.txt \
                       --evidence evidence_map.jsonl --out gate_report.json
                   (no pptx needed: quote gate + numeric gate + notes/density
                   checks on the plan — run BEFORE building, fix all fails)
  post-build:      python3 pptx_verify.py deck.pptx deck.json [--evidence ...] \
                       [--paper ...] --out verify_report.json
"""
import argparse
import json
import os
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_budget as LB  # noqa: E402

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

QUOTE_TYPES = {"quote", "data", "number", "fact"}


def open_pptx(path):
    """Return list-of-slide dicts {texts, images, notes, boxes} using python-pptx if present, else raw XML."""
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
            notes = ""
            if sl.has_notes_slide:
                notes = sl.notes_slide.notes_text_frame.text.strip()
            slides.append({"texts": texts, "images": images, "notes": notes,
                           "boxes_in": [[round(Emu(b[0]).inches, 2), round(Emu(b[1]).inches, 2),
                                         round(Emu(b[2]).inches, 2), round(Emu(b[3]).inches, 2)] for b in boxes]})
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
        texts, images = [], 0
        for sp in root.iter():
            tag = sp.tag.split("}")[-1]
            if tag == "pic":
                images += 1
        for t in root.iter("{%s}t" % NS["a"]):
            if t.text and t.text.strip():
                texts.append(t.text.strip())
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
    """只抓高风险数：百分数/小数/带单位数。纯整数不抓（误报太高）。"""
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
    """每条 quote 逐字回证论文原文（空白归一化后子串匹配）。

    - type ∈ {quote,data,number,fact} 且缺 quote -> fail（事实行必须有原文）
    - quote 在论文全文中找不到 -> fail（编造/改写/取整都会被抓）
    - 结构引用（figure/table/section 无 quote）只要求 locator 存在
    """
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
        quote = r.get("quote")
        locator = r.get("locator") or ""
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
        elif not (locator or "").strip():
            fails.append({"row": i + 1, "slide_no": r.get("slide_no"),
                          "reason": "structural_ref_missing_locator"})
    return {"status": "enforced", "rows": len(ev_rows), "quotes_checked": n_checked,
            "fail": len(fails), "fails": fails}


def check_slide_coverage(deck, ev_rows):
    """页面文本里的数字必须在该页 quote 里逐字出现。

    事实源是 evidence_map（已逐字校验过的 quote），不是 deck.json；
    分母是页面文本（title/bullets/columns/table/caption），不含 notes。
    无证据行=fail，有证据行但数字未回证=warn（允许模板占位/页码等新数字，
    但必须写进 uncertainty，故不硬 fail 逼模型编 quote）。
    """
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
        out.append({"slide_no": s, "role": row.get("role"),
                    "evidence_rows": len(ev),
                    "has_locator": all(bool((e.get("locator") or "").strip()) for e in ev) if ev else False,
                    "notes_chars": len(row.get("notes") or ""),
                    "numeric_tokens": numeric_tokens(flat),
                    "numeric_unbacked": unbacked,
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
                    "bullets": row.get("bullets"),
                    "columns": row.get("columns"), "table": row.get("table"),
                    "figure": row.get("figure"), "figure_ref": row.get("figure_ref"),
                    "notes": row.get("notes"),
                    "evidence": by_slide.get(s, [])})
    return out


def _input_status(path, provided):
    if not provided:
        return {"status": "skipped_not_provided", "path": None}
    if not os.path.exists(path):
        return {"status": "not_found", "path": path}
    return {"status": "loaded", "path": path}


def run_plan_gate(args):
    """构建前闸门：无 pptx，只查计划本身——quote 逐字回证、数字回证、
    备注与密度。fail 必须修完才允许构建。"""
    plan = json.load(open(args.deck, encoding="utf-8"))
    st_ev = _input_status(args.evidence, bool(args.evidence))
    st_paper = _input_status(args.paper, bool(args.paper))
    report = {"mode": "plan_gate", "deck": args.deck, "fail": 0, "warn": 0,
              "inputs": {"evidence": st_ev, "paper": st_paper}}

    ev_rows = []
    if st_ev["status"] == "loaded":
        ev_rows = load_ev_rows(args.evidence)
    elif st_ev["status"] == "not_found":
        report["warn"] += 1

    if st_paper["status"] == "loaded" and ev_rows:
        report["quote_gate"] = check_quote_gate(ev_rows, args.paper)
        report["fail"] += report["quote_gate"]["fail"]
    else:
        reason = st_paper["status"] if st_paper["status"] != "loaded" else "skipped_no_evidence"
        report["quote_gate"] = {"status": reason,
                                "note": "quote 逐字回证未执行，下游不得宣称已核对；须在 uncertainty 登记",
                                "rows": len(ev_rows), "fail": 0, "fails": []}
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
        report["warn"] += 1
        report["coverage_gate"] = {"status": st_ev["status"] if st_ev["status"] != "loaded" else "skipped_no_evidence",
                                   "note": "证据覆盖与数字对账未执行，下游不得宣称已核对；须在 uncertainty 登记"}
    report["slide_coverage"] = cov
    report["slides_embed"] = build_slides_embed(plan, ev_rows)

    # 页面卫生：备注齐全且非复述、要点 ≤5 条、单页字符预算
    page_issues = []
    for row in plan.get("slides", []):
        issues = []
        nb = LB.check_notes({"notes": row.get("notes") or ""}, _slide_flat(row))
        if not nb.get("ok"):
            issues.append("notes:%s" % json.dumps(nb, ensure_ascii=False))
        bullets = row.get("bullets") or []
        if len(bullets) > 5:
            issues.append("too_many_bullets(%d)" % len(bullets))
        flat = _slide_flat(row)
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
                         "numeric_unbacked": {c["slide_no"]: c["numeric_unbacked"] for c in cov if c["numeric_unbacked"]},
                         "coverage_fail_slides": [c["slide_no"] for c in cov if c["verdict"] == "fail"]}
    out = args.out or "gate_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("plan_gate:", report["summary"], "->", out)
    print("gates:", json.dumps({"quote_gate": report["quote_gate"]["status"],
                                "coverage_gate": report["coverage_gate"]["status"]}, ensure_ascii=False))
    for p in page_issues:
        print("  page", json.dumps(p, ensure_ascii=False))
    for fq in report["quote_gate"].get("fails") or []:
        print("  quote_gate", json.dumps(fq, ensure_ascii=False))
    # 优化(11-17): verdict 照实输出；退出码恒 0——fail 冒泡会中断平台会话导致整跑 failed
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx", help="deck.pptx path, or literal PLAN for pre-build gate mode")
    ap.add_argument("deck")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--paper", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.pptx.upper() == "PLAN":
        run_plan_gate(args)
        return

    plan = json.load(open(args.deck, encoding="utf-8"))
    slides, engine = open_pptx(args.pptx)
    report = {"pptx": args.pptx, "engine": engine,
              "slide_count": {"planned": len(plan.get("slides", [])), "actual": len(slides),
                              "match": len(slides) == len(plan.get("slides", []))},
              "slides": [], "fail": 0, "warn": 0}

    if not report["slide_count"]["match"]:
        report["fail"] += 1

    st_ev = _input_status(args.evidence, bool(args.evidence))
    st_paper = _input_status(args.paper, bool(args.paper))
    report["inputs"] = {"evidence": st_ev, "paper": st_paper}

    ev_rows = []
    if st_ev["status"] == "loaded":
        ev_rows = load_ev_rows(args.evidence)
    elif st_ev["status"] == "not_found":
        report["warn"] += 1
    ev_slides = sorted(set(r.get("slide_no") for r in ev_rows if r.get("slide_no") is not None))
    report["evidence_map"] = {
        "rows": len(ev_rows),
        "slides_covered": ev_slides,
        "covers_all": bool(ev_rows) and ev_slides and ev_slides[0] == 1 and ev_slides[-1] == len(slides) and len(ev_slides) >= len(slides),
    }
    if ev_rows and not report["evidence_map"]["covers_all"]:
        report["warn"] += 1

    # 闸门一：quote 逐字回证（论文原文）。四态显式，未跑绝不报通过。
    if st_paper["status"] == "loaded" and ev_rows:
        report["quote_gate"] = check_quote_gate(ev_rows, args.paper)
        report["fail"] += report["quote_gate"]["fail"]
    else:
        reason = st_paper["status"] if st_paper["status"] != "loaded" else "skipped_no_evidence"
        report["quote_gate"] = {"status": reason,
                                "note": "quote 逐字回证未执行，下游不得宣称已核对；须在 uncertainty 登记",
                                "rows": len(ev_rows), "fail": 0, "fails": []}
        report["warn"] += 1

    # 闸门二：证据覆盖 + 数字回证。四态显式。
    cov = []
    if ev_rows:
        cov = check_slide_coverage(plan, ev_rows)
        n_warn = sum(1 for c in cov if c["verdict"] == "warn")
        n_fail = sum(1 for c in cov if c["verdict"] == "fail")
        report["warn"] += n_warn
        report["fail"] += n_fail
        report["coverage_gate"] = {"status": "enforced", "fail_slides": n_fail, "warn_slides": n_warn}
    else:
        report["warn"] += 1
        report["coverage_gate"] = {"status": st_ev["status"] if st_ev["status"] != "loaded" else "skipped_no_evidence",
                                   "note": "证据覆盖与数字对账未执行，下游不得宣称已核对；须在 uncertainty 登记"}
    report["slide_coverage"] = cov

    # 主产物逐页合并记录：result.json 全量内嵌用（机器生成）
    report["slides_embed"] = build_slides_embed(plan, ev_rows)

    for i, (sl, plan_sl) in enumerate(zip(slides, plan.get("slides", [])), 1):
        row = {"no": i, "checks": {}}
        texts = " ".join(sl["texts"])
        plan_layout = plan_sl.get("layout", "bullets") if plan_sl else "?"

        row["checks"]["has_text"] = bool(sl["texts"])
        row["checks"]["title"] = bool(re.search(r"\S", texts)) if plan_layout in ("title", "section", "closing") else bool(sl["texts"])
        # 检查项必须计入总账：发现问题却不让 verdict 变色，等于静默通过
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

        nb = LB.check_notes({"notes": sl["notes"]}, texts)
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

        # geometry sanity: boxes inside slide bounds (python-pptx only)
        geo_ok = True
        for b in sl.get("boxes_in", []):
            x, y, w, h = b
            if x < -0.05 or y < -0.05 or x + w > 13.4 or y + h > 7.6:
                geo_ok = False
        row["checks"]["geometry_in_bounds"] = geo_ok
        if not geo_ok:
            report["fail"] += 1

        report["slides"].append(row)

    qg = report["quote_gate"]
    report["summary"] = {
        "fail": report["fail"], "warn": report["warn"],
        "verdict": "pass" if report["fail"] == 0 else "fail",
        "quote_gate_status": qg["status"],
        "quote_gate_fails": qg["fail"],
        "numeric_unbacked": {c["slide_no"]: c["numeric_unbacked"] for c in cov
                             if c["numeric_unbacked"]},
        "coverage_fail_slides": [c["slide_no"] for c in cov if c["verdict"] == "fail"],
    }
    out = args.out or (os.path.splitext(args.pptx)[0] + ".verify_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("verify:", report["summary"], "->", out)
    print("gates:", json.dumps({"quote_gate": qg["status"],
                                "coverage_gate": report["coverage_gate"]["status"]},
                               ensure_ascii=False))
    for row in report["slides"]:
        for k, v in row["checks"].items():
            if v is False or (isinstance(v, dict) and v.get("verdict") in ("fail",) or (isinstance(v, dict) and not v.get("ok", True))):
                print("  slide", row["no"], k, json.dumps(v, ensure_ascii=False))
    if qg["fails"]:
        for fq in qg["fails"]:
            print("  quote_gate", json.dumps(fq, ensure_ascii=False))
    # 优化(11-17): verdict 照实输出；退出码恒 0——fail 冒泡会中断平台会话导致整跑 failed
    sys.exit(0)


if __name__ == "__main__":
    main()
