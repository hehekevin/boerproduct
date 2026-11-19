"""assemble — one-command arena reading pipeline.

Usage:
  python assemble.py --ir /app/work/ir.json --input /input --out /app/output

The Agent reads the ACTUAL organizer workorder/material files under /input and
fills the reading IR; this CLI deterministically validates (arena_read_engine +
readkit), builds editable artifacts + provenance, and writes an honest result.json
preserving every output_contract field and case_id. Exit 0 = validation ok,
2 = validation errors (partial result still written).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import figkit
import arena_read_engine as engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--status", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ir = figkit.load_json(args.ir)
    case = figkit.load_case(args.input)
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]

    validation = engine.validate_ir(ir, args.input)
    figkit.write_json(out_dir / "validation.json", validation)

    artifacts, extra, status = [], {}, args.status
    if validation["ok"]:
        try:
            artifacts, extra = engine.build(ir, case, out_dir, args.input)
            status = status or extra.pop("_status", "success")
        except Exception as e:  # noqa: BLE001
            status = status or "partial"
            ir.setdefault("uncertainty", []).append(
                {"item": "build", "reason": str(e), "impact": "artifacts not fully built",
                 "handling": "IR + validation saved; fix and re-run"})
    else:
        status = status or "partial"
        extra = {"kind": ir.get("kind"), "n_records": len(engine.records_of(ir))}

    figkit.write_json(out_dir / "reading_ir.json", ir)
    prov = ir.setdefault("provenance", {})
    prov["record_map"] = engine.build_record_map(ir)
    figkit.write_json(out_dir / "provenance.json", prov)

    notes = "" if validation["ok"] else "validation failed: " + "; ".join(validation["errors"])
    if validation["ok"] and validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])
    result = figkit.build_result(case, ir, artifacts, status, validation, None, notes)
    result["provenance"]["record_map"] = prov.get("record_map", {})
    result["provenance"]["source_files"] = prov.get("source_files", [])
    result["extra"] = extra
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "validation_ok": validation["ok"],
                      "errors": validation["errors"], "n_warnings": len(validation["warnings"]),
                      "n_artifacts": len(artifacts), "result": str(out_dir / "result.json")},
                     ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()