"""assemble — product-arena WRITING pipeline: IR -> validate -> editable artifact -> result.json.

The Agent reads the ACTUAL organizer material under /input and fills the kind-specific
writing IR. This CLI deterministically validates (writekit + arena_write_engine),
builds the editable deliverable, runs consistency checks, and writes an honest
result.json preserving every output_contract field + case_id.

Usage:
  python assemble.py --ir <ir.json> --input /input --out /app/output [--status success|partial]

Kinds: polish / reference_manage / intro_related / methods_section / latex.
stdlib only; PYTHONDONTWRITEBYTECODE=1 recommended.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import w4kit
import writekit
import arena_write_engine as engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--status", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ir = w4kit.load_json(args.ir)
    case = w4kit.load_case(args.input)
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]

    # resolve relative figure/data paths against the IR file's directory
    ir_dir = Path(args.ir).resolve().parent
    for f in ir.get("latex", {}).get("figures", []):
        p = f.get("path")
        if p and not Path(p).is_absolute() and not Path(p).exists():
            cand = ir_dir / p
            if cand.exists():
                f["path"] = str(cand)

    validation = engine.validate_ir(ir)
    w4kit.write_json(out_dir / "validation.json", validation)

    artifacts, status, extra = [], args.status, {}
    if validation["ok"]:
        try:
            artifacts, extra = engine.build(ir, case, out_dir)
            status = status or extra.get("status", "success")
        except Exception as e:  # noqa: BLE001
            status = status or "partial"
            ir.setdefault("uncertainty", []).append(
                {"item": "build", "reason": str(e), "impact": "deliverable not fully built",
                 "handling": "IR+validation saved; fix and re-run"})
    else:
        status = status or "partial"

    w4kit.write_json(out_dir / "writing_ir.json", ir)
    prov = ir.setdefault("provenance", {})
    prov.setdefault("pipeline", "material -> writing IR -> validate -> editable artifact -> result")
    prov["claim_map"] = writekit.build_claim_map(ir)
    if extra.get("provenance"):
        prov.update(extra["provenance"])
    w4kit.write_json(out_dir / "provenance.json", prov)

    notes = ""
    if not validation["ok"]:
        notes = "validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])
    result = w4kit.build_result(case, ir, artifacts, status, validation,
                                extra.get("result_extra"), notes)
    result["extra_checks"] = extra.get("checks", {})
    w4kit.write_result(out_dir, result)
    print(json.dumps({"status": status, "kind": ir.get("kind"), "validation_ok": validation["ok"],
                      "errors": validation["errors"], "n_artifacts": len(artifacts),
                      "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()