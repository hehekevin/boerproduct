"""assemble — one-command pipeline from a filled Figure IR to all deliverables.

The agent extracts entities/relations/data from the actual source material into
figure_ir.json (scientific judgment stays with the agent/LLM judge). This script
then deterministically:
  1 validates the IR (scientific/self-consistency checks),
  2 renders the editable SVG source + PNG/PDF/... exports (chart or diagram),
  3 runs the export compliance check,
  4 assembles result.json preserving every original output_contract field + case_id
    with honest status, sources, uncertainty and change records.

Usage:
  python assemble.py --ir figure_ir.json --input /input --out /app/output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import figkit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True, help="filled Figure IR json")
    ap.add_argument("--input", default="/input", help="runtime input dir with case.json")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--data", default=None, help="override chart data path")
    ap.add_argument("--status", default=None, help="force status (success/partial/failed/stuck)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ir = figkit.load_json(args.ir)
    case = figkit.load_case(args.input)
    # bind case_id from the authoritative runtime case if IR left it generic
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]
    # resolve a relative chart data_path against the IR file's own directory so
    # examples and bundled tables work regardless of the caller's cwd
    ch = ir.get("chart") or {}
    dp = ch.get("data_path")
    if dp and not Path(dp).is_absolute() and not Path(dp).exists():
        cand = Path(args.ir).resolve().parent / dp
        if cand.exists():
            ch["data_path"] = str(cand)

    validation = figkit.validate_ir(ir)
    figkit.write_json(out_dir / "validation.json", validation)

    artifacts = []
    render_info = {}
    status = args.status
    if validation["ok"]:
        kind = ir.get("kind")
        try:
            if kind == "source_value_chart" or (ir.get("chart") and kind == "graphical_abstract" and not ir.get("entities")):
                import render_chart
                render_info = render_chart.render(ir, out_dir, args.data)
            else:
                import render_diagram
                render_info = render_diagram.render(ir, out_dir)
            artifacts = render_info.get("artifacts", [])
            status = status or "success"
        except Exception as e:  # noqa: BLE001 - honest partial, never fabricate
            status = status or "partial"
            ir.setdefault("uncertainty", []).append(
                {"item": "render", "reason": str(e), "impact": "figure not fully rendered",
                 "handling": "IR + validation saved; fix IR/data and re-run assemble"})
            figkit.write_json(out_dir / "figure_ir.json", ir)
    else:
        status = status or "partial"
        figkit.write_json(out_dir / "figure_ir.json", ir)

    # export compliance (only if we produced files)
    export_report = None
    if artifacts:
        try:
            import export_check
            export_report = export_check.check(ir, out_dir)
            figkit.write_json(out_dir / "export_report.json", export_report)
        except Exception as e:  # noqa: BLE001
            export_report = {"overall": "warn", "error": str(e)}

    # always persist the IR (editable source of truth) and provenance
    figkit.write_json(out_dir / "figure_ir.json", ir)
    if ir.get("provenance", {}).get("element_map") or ir.get("provenance", {}).get("data_map"):
        figkit.write_json(out_dir / "provenance.json", ir["provenance"])

    notes = ""
    if not validation["ok"]:
        notes = "IR validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])

    result = figkit.build_result(case, ir, artifacts, status, validation, export_report, notes)
    result["render_info"] = {k: render_info.get(k) for k in ("n_rows", "n_entities", "n_relations", "layout", "font_used", "data_path") if k in render_info}
    figkit.write_result(out_dir, result)

    print(json.dumps({"status": status, "validation_ok": validation["ok"],
                      "errors": validation["errors"], "n_artifacts": len(artifacts),
                      "export_overall": (export_report or {}).get("overall"),
                      "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()