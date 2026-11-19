"""assemble.py — week4 SEARCH track CLI (shared by all 11 search skills).

Usage:
  PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output

Contract (ENGINE_CONVENTION.md):
  1. load_case(input); load IR; ir["case_id"] = case["case_id"]
  2. search_engine.validate_ir(ir) -> validation.json (honest partial on errors)
  3. search_engine.build(ir, case, out) -> main artifact + report.md + records.csv
     + provenance.json + search_ir.json
  4. w4kit.build_result(...) preserves every output_contract key + case_id;
     result.json carries honest status/sources/uncertainty/change_log.
  5. Relative data paths in the IR resolve against the IR file's directory,
     then the input directory.

Status policy (honest, never inflated):
  failed  — IR unreadable or build raised with no artifacts written
  partial — build raised after some artifacts, OR validation errors, OR any
            uncertainty entry flagged human_confirm (unresolved gap)
  success — validation clean, build clean, no unresolved human_confirm gaps
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import w4kit
import search_engine


def compute_status(ir: dict, validation: dict) -> str:
    if validation.get("errors"):
        return "partial"
    for u in ir.get("uncertainty", []):
        if u.get("handling") == "human_confirm":
            return "partial"
    return "success"


def main() -> int:
    ap = argparse.ArgumentParser(description="search track assembler")
    ap.add_argument("--ir", required=True, help="agent-filled IR json")
    ap.add_argument("--input", default="/input", help="case input dir")
    ap.add_argument("--out", default="/app/output", help="output dir")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    case = w4kit.load_case(args.input)

    ir_path = Path(args.ir)
    try:
        ir = w4kit.load_json(ir_path)
    except (OSError, json.JSONDecodeError) as e:
        result = {"case_id": case["case_id"], "status": "failed",
                  "error": f"cannot load IR: {e}",
                  "sources": [], "uncertainty": [
                      {"item": "ir", "reason": str(e), "handling": "human_confirm"}]}
        w4kit.write_result(out_dir, result)
        print(json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False))
        return 1

    ir["case_id"] = case["case_id"]
    ir["_ir_dir"] = str(ir_path.resolve().parent)
    ir.setdefault("provenance", {}).setdefault("pipeline",
        "actual material -> IR -> validate -> compute -> artifact -> result")

    validation = search_engine.validate_ir(ir)
    w4kit.write_json(out_dir / "validation.json", validation)

    outputs, build_error = [], None
    try:
        outputs = search_engine.build(ir, case, out_dir)
    except Exception as e:  # honest partial: keep validation + whatever exists
        build_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    summary = ir.get("_summary", {})
    if build_error:
        status = "partial" if outputs else "failed"
        ir.setdefault("uncertainty", []).append(
            {"item": "build", "reason": build_error, "handling": "human_confirm"})
    else:
        status = compute_status(ir, validation)

    notes = ("search engine: dedup/rank/screen/citation-BFS/coverage/incremental/"
             "PRISMA/appraisal/cross-language/patent computation performed on the IR "
             "filled from ACTUAL organizer-provided local materials; no live remote "
             "search, no fabricated records/citations/legal status.")
    if validation["errors"]:
        notes += " IR validation errors present; see validation.json."
    result = w4kit.build_result(case, ir, outputs, status, validation=validation,
                                extra={"summary": summary}, notes=notes)
    if build_error:
        result["build_error"] = build_error
    w4kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "case_id": case["case_id"],
                      "n_outputs": len(outputs), "summary": summary,
                      "errors": validation["errors"],
                      "warnings": validation["warnings"][:10]},
                     ensure_ascii=False, indent=2))
    return 0 if status in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())