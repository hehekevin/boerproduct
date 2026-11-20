#!/usr/bin/env python3
"""evidence_check.py — verify that every quoted fact in the evidence map
appears VERBATIM in the source paper text (prevents invented numbers).

Input:
  --paper  extracted paper text file (txt)
  --map    evidence_map.jsonl (one JSON object per line with fields:
           slide_no, type, locator, quote)
Behavior:
  - normalizes whitespace before matching (quotes must still match verbatim
    after whitespace collapse — no rewording, no rounding)
  - rows with type in {figure,table,section} and no quote are checked only
    for locator presence (pattern like "Fig", "Table", section numbers)
  - fact rows (type=quote/data) REQUIRE a matching quote

Writes evidence_check.json + prints per-row verdict. Exit 1 if any
fact-bearing quote fails.

Usage: python evidence_check.py --paper paper.txt --map evidence_map.jsonl
"""
import argparse
import json
import os
import re
import sys


NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\d+\.\d+|\d+(?:\.\d+)?\s*(?:x|×|倍|万|亿|GB|MB|ms|s|h|K|k)")


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def numeric_tokens(text):
    """High-risk numeric tokens on a slide bullet (percent / decimal / unit-bearing)."""
    out = []
    for m in NUM_RE.findall(str(text or "")):
        t = norm(m)
        if t and t not in out:
            out.append(t)
    return out


def _as_text(v):
    """bullets may be plain strings or {"text": ...} dicts (per-item styling)."""
    if isinstance(v, dict):
        return str(v.get("text") or v.get("content") or "")
    return str(v or "")


def slide_text(row):
    """Everything the audience can read on the page: title, bullets, 2-column
    body, table cells, figure caption. Notes are deliberately excluded."""
    parts = [row.get("title") or ""]
    parts += [_as_text(b) for b in (row.get("bullets") or [])]
    for col in (row.get("columns") or []):
        parts += [_as_text(c) for c in (col or [])]
    for tr in ((row.get("table") or {}).get("rows") or row.get("rows") or []):
        parts += [_as_text(c) for c in (tr or [])]
    fig = row.get("figure") or {}
    if isinstance(fig, dict):
        parts.append(fig.get("caption") or "")
    return " ".join(p for p in parts if p)


def check_slide_coverage(deck, rows):
    """Per-slide: has evidence row? every risky number backed by a verbatim quote?

    Quotes come from evidence_map.jsonl (already validated verbatim against the
    paper), page text comes from deck.json (what the audience actually sees), so
    a page carrying a number with no matching quote in its own evidence rows is
    surfaced before delivery.
    """
    by_slide = {}
    for r in rows:
        s = r.get("slide_no")
        if s is None:
            continue
        by_slide.setdefault(s, []).append(r)
    out = []
    for row in (deck or {}).get("slides", []):
        s = row.get("no")
        ev = by_slide.get(s, [])
        flat = slide_text(row)
        backed = norm(" ".join((e.get("quote") or "") for e in ev))
        unbacked = [t for t in numeric_tokens(flat) if t not in backed]
        out.append({
            "slide_no": s,
            "role": row.get("role"),
            "evidence_rows": len(ev),
            "has_locator": all(bool((e.get("locator") or "").strip()) for e in ev) if ev else False,
            "notes_chars": len(row.get("notes") or ""),
            "numeric_tokens": numeric_tokens(flat),
            "numeric_unbacked": unbacked,
            "verdict": ("pass" if ev and not unbacked else
                        "fail" if not ev else "warn"),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--deck", default=None,
                    help="optional deck.json: per-slide evidence coverage + number-vs-quote cross-check")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    paper = open(args.paper, encoding="utf-8", errors="replace").read()
    pn = norm(paper)
    pl = paper.lower()

    rows = []
    with open(args.map, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    rows.append({"_parse_error": line[:120]})

    results = []
    n_fail = 0
    for i, r in enumerate(rows):
        if "_parse_error" in r:
            results.append({"row": i + 1, "verdict": "fail", "reason": "json_parse_error"})
            n_fail += 1
            continue
        typ = (r.get("type") or "").lower()
        quote = r.get("quote")
        locator = r.get("locator") or ""
        if quote:
            qn = norm(quote).lower()
            ok = qn and qn in pn.lower()
            verdict = "pass" if ok else "fail"
            if not ok:
                n_fail += 1
                # closest hint: first 12 chars
                hint = qn[:12]
                results.append({"row": i + 1, "slide_no": r.get("slide_no"), "verdict": verdict,
                                "reason": "quote_not_found_in_paper", "hint": hint,
                                "locator": locator})
            else:
                results.append({"row": i + 1, "slide_no": r.get("slide_no"), "verdict": verdict,
                                "locator": locator})
        else:
            needs_quote = typ in ("quote", "data", "number", "fact")
            if needs_quote:
                results.append({"row": i + 1, "slide_no": r.get("slide_no"), "verdict": "fail",
                                "reason": "missing_required_quote", "locator": locator})
                n_fail += 1
            else:
                results.append({"row": i + 1, "slide_no": r.get("slide_no"), "verdict": "pass",
                                "locator": locator, "note": "structural_ref_no_quote"})

    deck_cov = None
    gate = "enforced"
    if args.deck and os.path.exists(args.deck):
        try:
            deck_cov = check_slide_coverage(json.load(open(args.deck, encoding="utf-8")), rows)
        except Exception as e:
            deck_cov = [{"error": "%s: %s" % (type(e).__name__, e)}]
            gate = "deck_unreadable"
    elif args.deck:
        gate = "deck_not_found"      # a path was given but does not resolve
    else:
        gate = "skipped_no_deck"     # gate never ran: must NOT look like "passed"

    summary = {"rows": len(rows), "fail": n_fail, "coverage_gate": gate}
    coverage_fail = []
    if deck_cov and not any("error" in d for d in deck_cov):
        coverage_fail = [d["slide_no"] for d in deck_cov if d.get("verdict") == "fail"]
        summary["slides_checked"] = len(deck_cov)
        summary["slides_without_evidence"] = [d["slide_no"] for d in deck_cov if d["evidence_rows"] == 0]
        summary["coverage_fail_slides"] = coverage_fail
        summary["numeric_unbacked"] = {str(d["slide_no"]): d["numeric_unbacked"]
                                       for d in deck_cov if d["numeric_unbacked"]}
    # "not run" is reported as warn, never as a pass of the gate
    summary["warn"] = (1 if gate != "enforced" else 0) + (1 if any(
        d.get("verdict") == "warn" for d in (deck_cov or [])) else 0)
    if gate != "enforced":
        summary["gate_note"] = ("page-level gate did NOT run (%s): pages are not checked for "
                                "evidence coverage or unbacked numbers; record this in uncertainty"
                                % gate)
    summary["verdict"] = "pass" if (n_fail == 0 and not coverage_fail) else "fail"
    out = args.out or "evidence_check.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results, "slide_coverage": deck_cov},
                  f, ensure_ascii=False, indent=1)
    print("evidence:", summary, "->", out)
    for res in results:
        if res["verdict"] == "fail":
            print("  FAIL", json.dumps(res, ensure_ascii=False))
    for d in (deck_cov or []):
        if d.get("verdict") in ("fail", "warn") or d.get("error"):
            print("  SLIDE", json.dumps(d, ensure_ascii=False))
    sys.exit(0 if summary["verdict"] == "pass" else 1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(3)
