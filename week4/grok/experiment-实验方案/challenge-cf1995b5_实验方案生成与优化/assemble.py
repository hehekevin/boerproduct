"""assemble.py — week4 EXPERIMENT track CLI (shared by all 5 experiment skills).

Usage:
  PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output

Contract (ENGINE_CONVENTION.md):
  1. load_case(input); load IR; ir["case_id"] = case["case_id"]
  2. engine.validate_ir(ir) -> validation.json (honest partial on errors)
  3. engine.build(ir, case, out) -> editable artifacts + provenance.json + report.md
  4. w4kit.build_result(...) preserves every output_contract key + case_id;
     result.json carries honest status/sources/uncertainty/change_log.
  5. Relative data paths in the IR resolve against the IR file's directory,
     then the input directory.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import w4kit
import experiment_engine


def main() -> int:
    ap = argparse.ArgumentParser(description="experiment track assembler")
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

    validation = experiment_engine.validate_ir(ir)
    w4kit.write_json(out_dir / "validation.json", validation)

    outputs, summary, build_error = [], {}, None
    try:
        outputs = experiment_engine.build(ir, case, out_dir)
        sp = out_dir / "_summary.json"
        if sp.exists():
            summary = w4kit.load_json(sp)
            sp.unlink()
    except Exception as e:  # honest partial: keep validation + whatever exists
        build_error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    if build_error:
        status = "partial" if outputs else "failed"
        ir.setdefault("uncertainty", []).append(
            {"item": "build", "reason": build_error, "handling": "human_confirm"})
    elif validation["errors"]:
        status = "partial"
    else:
        status = experiment_engine.compute_status(ir, validation, summary)

    notes = ("experiment engine: design/feasibility/parameter/compare/anomaly computed "
             "from IR filled from actual input files; arithmetic via safe_eval/stats; "
             "quotes verified against actual paragraph text where readable; "
             "reported vs inferred distinguished; gaps flagged human_confirm.")
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