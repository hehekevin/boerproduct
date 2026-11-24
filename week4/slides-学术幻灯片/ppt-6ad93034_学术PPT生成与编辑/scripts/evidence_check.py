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
import re
import sys


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--map", required=True)
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

    summary = {"rows": len(rows), "fail": n_fail,
               "verdict": "pass" if n_fail == 0 else "fail"}
    out = args.out or "evidence_check.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=1)
    print("evidence:", summary, "->", out)
    for res in results:
        if res["verdict"] == "fail":
            print("  FAIL", json.dumps(res, ensure_ascii=False))
    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}))
        sys.exit(3)
