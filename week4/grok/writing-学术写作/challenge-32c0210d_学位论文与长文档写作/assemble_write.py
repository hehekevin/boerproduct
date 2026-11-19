"""assemble_write — one-command pipeline: writing IR -> editable deliverable -> checks -> result.json.

The agent reads the ACTUAL material and fills the writing IR (claims+evidence,
citations, sections, glossary, revisions, alignment, comments, mindmap tree, or
benchmark tasks) — scientific/organisational judgment stays with the agent. This
script deterministically validates, builds the editable deliverable (md+docx, or
mindmap SVG/PNG/PDF, or benchmark tasks/rubric/eval), runs consistency checks,
renders previews (office-renderer, honest fallback) and writes result.json
preserving every output_contract field + case_id with honest status/sources/
uncertainty/change log.

Usage:
  python assemble_write.py --ir writing_ir.json --input /input --out /app/output
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import figkit
import writekit


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
    if kind == "writing_benchmark":
        validation = writekit.validate_writing(ir) if ir.get("claims") else {"ok": True, "errors": [], "warnings": []}
        bv = __import__("benchkit").validate_benchmark(ir)
        validation = {"ok": validation["ok"] and bv["ok"],
                      "errors": validation["errors"] + bv["errors"],
                      "warnings": validation["warnings"] + bv["warnings"]}
    elif kind == "mind_map":
        validation = {"ok": bool(ir.get("nodes")), "errors": [] if ir.get("nodes") else ["mind_map requires nodes"], "warnings": []}
        for n in ir.get("nodes", []):
            if not n.get("source"):
                validation["warnings"].append(f"node {n.get('id')} lacks source")
    else:
        validation = writekit.validate_writing(ir)
    figkit.write_json(out_dir / "validation.json", validation)

    artifacts = []
    status = args.status
    extra = {}
    if validation["ok"]:
        try:
            if kind == "writing_benchmark":
                import benchkit
                extra = benchkit.build_benchmark(ir, out_dir)
                artifacts = extra["artifacts"]
            elif kind == "mind_map":
                import mindmap
                extra = mindmap.render(ir, out_dir)
                artifacts = extra["artifacts"]
            else:
                import docxkit
                paths = docxkit.write_manuscript(ir, out_dir)
                artifacts = [{"name": "manuscript.md", "path": paths["md"], "format": "md", "role": "md"},
                             {"name": "manuscript.docx", "path": paths["docx"], "format": "docx", "role": "docx"}]
                extra["number_issues"] = writekit.check_number_consistency(ir)
                # office-renderer preview (honest fallback)
                try:
                    import export_deck
                    ex = export_deck.export(ir, out_dir)
                    artifacts += [a for a in ex["artifacts"] if a["format"] in ("pdf", "png")]
                except Exception:
                    pass
            status = status or "success"
        except Exception as e:  # noqa: BLE001
            status = status or "partial"
            ir.setdefault("uncertainty", []).append({"item": "build", "reason": str(e), "impact": "deliverable not fully built", "handling": "IR+validation saved; fix and re-run"})
    else:
        status = status or "partial"

    figkit.write_json(out_dir / "writing_ir.json", ir)
    ir.setdefault("provenance", {})["claim_map"] = writekit.build_claim_map(ir)
    figkit.write_json(out_dir / "provenance.json", ir["provenance"])

    notes = ""
    if not validation["ok"]:
        notes = "validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])
    result = figkit.build_result(case, ir, artifacts, status, validation, None, notes)
    result["extra_checks"] = extra
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_artifacts": len(artifacts), "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()