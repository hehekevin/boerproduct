"""assemble_read — one-command pipeline: reading IR -> structured result -> checks -> result.json.

The agent reads the ACTUAL material and fills the reading IR (items/answers with
locators+status+reported/inferred, claims+support, matrix, formulas, cleaning,
reproduction, coverage). This script deterministically validates, runs the domain
helper (clean/formula/compare/benchmark), emits the structured deliverable
(answers.json / fields.json / comparison.json / cleaned.json / formula_check.json /
reading_result.md) and writes result.json preserving every output_contract field +
case_id with honest status/sources/uncertainty.

Usage:
  python assemble_read.py --ir reading_ir.json --input /input --out /app/output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import figkit
import readkit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--status", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    ir = figkit.load_json(args.ir)
    case = figkit.load_case(args.input)
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]
    kind = ir.get("kind")

    # week4: auto-discover organizer workorder files and guarantee one result per
    # requested field/claim/question (honest insufficient_evidence for gaps).
    workorders = readkit.load_workorders(args.input)
    coverage_added = {}
    if kind != "reading_benchmark":
        coverage_added = readkit.apply_coverage(ir, workorders)
    figkit.write_json(out_dir / "workorders.json",
                      {"files": workorders["files"], "requests": workorders["requests"],
                       "auto_added": coverage_added})

    if kind == "reading_benchmark":
        import benchkit
        bv = benchkit.validate_benchmark(ir)
        validation = bv
    else:
        validation = readkit.validate_reading(ir)
    figkit.write_json(out_dir / "validation.json", validation)

    artifacts = []
    extra = {}
    status = args.status
    if validation["ok"]:
        try:
            if kind == "data_cleaning":
                import clean
                extra["cleaning"] = clean.clean(ir, out_dir)
                artifacts.append({"name": "cleaned.json", "path": str(out_dir / "cleaned.json"), "format": "json", "role": "json"})
            elif kind == "formula_reasoning":
                import formula
                extra["formula"] = formula.check_all(ir, out_dir)
                artifacts.append({"name": "formula_check.json", "path": str(out_dir / "formula_check.json"), "format": "json", "role": "json"})
            elif kind == "multi_doc_compare":
                import compare
                extra["comparison"] = compare.compare(ir, out_dir)
                artifacts.append({"name": "comparison.json", "path": str(out_dir / "comparison.json"), "format": "json", "role": "json"})
            elif kind == "reading_benchmark":
                import benchkit
                extra["benchmark"] = benchkit.build_benchmark(ir, out_dir)
                artifacts += extra["benchmark"]["artifacts"]
            # structured reading result (items/answers/claims/matrix) for all kinds
            structured = {"case_id": ir.get("case_id"), "kind": kind,
                          "items": ir.get("items", []), "answers": ir.get("items", []),
                          "claims": ir.get("claims", []), "matrix": ir.get("matrix", {}),
                          "formulas": ir.get("formulas", []), "figures": ir.get("figures", []),
                          "reproduction": ir.get("reproduction", {}),
                          "coverage": ir.get("coverage", {}), "unanswered_parts": ir.get("unanswered_parts", [])}
            figkit.write_json(out_dir / "reading_result.json", structured)
            artifacts.append({"name": "reading_result.json", "path": str(out_dir / "reading_result.json"), "format": "json", "role": "json"})
            # readable markdown summary
            md = [f"# Reading result — {ir.get('case_id')} ({kind})", ""]
            for it in ir.get("items", []):
                md.append(f"- **{it.get('field_id') or it.get('question_id') or it.get('id')}**: "
                          f"{it.get('value', it.get('answer', ''))} [{it.get('kind', '')}/{it.get('status', '')}] "
                          f"units={it.get('units', '')} evidence={len(it.get('evidence', []))}")
            (out_dir / "reading_result.md").write_text("\n".join(md), encoding="utf-8")
            artifacts.append({"name": "reading_result.md", "path": str(out_dir / "reading_result.md"), "format": "md", "role": "md"})
            status = status or "success"
        except Exception as e:  # noqa: BLE001
            status = status or "partial"
            ir.setdefault("uncertainty", []).append({"item": "build", "reason": str(e), "impact": "result not fully built", "handling": "IR+validation saved; fix and re-run"})
    else:
        status = status or "partial"

    figkit.write_json(out_dir / "reading_ir.json", ir)
    ir.setdefault("provenance", {})["item_map"] = readkit.build_item_map(ir)
    figkit.write_json(out_dir / "provenance.json", ir["provenance"])
    notes = "" if validation["ok"] else "validation failed: " + "; ".join(validation["errors"])
    if validation["ok"] and validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])
    result = figkit.build_result(case, ir, artifacts, status, validation, None, notes)
    result["extra"] = {k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk in ("n_records", "n_anomalies", "n_formulas", "n_documents", "n_tasks")}) for k, v in extra.items()}
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_artifacts": len(artifacts), "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()