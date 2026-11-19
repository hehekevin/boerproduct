"""assemble_deck — one-command pipeline: Deck IR -> editable PPTX -> checks -> render -> result.json.

The agent extracts the narrative (question/method/result/conclusion), per-page
claims, source-bound bullets, figure refs and speaker notes from the ACTUAL paper
into deck_ir.json (scientific/organisational judgment stays with the agent). This
script deterministically builds the template-aware PPTX, checks structure/overflow/
consistency, renders PDF/PNG (office-renderer, honest fallback), and writes
result.json preserving every output_contract field + case_id with honest status,
sources, page-level evidence map, uncertainty and change log.

Usage:
  python assemble_deck.py --ir deck_ir.json --input /input --out /app/output [--template /input/template.pptx]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import figkit
import deckkit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ir", required=True)
    ap.add_argument("--input", default="/input")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--template", default=None)
    ap.add_argument("--status", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    ir = figkit.load_json(args.ir)
    case = figkit.load_case(args.input)
    if case.get("case_id") and case["case_id"] != "unknown-case":
        ir["case_id"] = case["case_id"]
    # resolve relative figure image_path / chart data_path / template against IR dir
    for p in ir.get("pages", []):
        for f in p.get("figures", []):
            ip = f.get("image_path")
            if ip and not Path(ip).is_absolute() and not Path(ip).exists():
                cand = Path(args.ir).resolve().parent / ip
                if cand.exists():
                    f["image_path"] = str(cand)
            ch = f.get("chart") or {}
            dp = ch.get("data_path")
            if dp and not Path(dp).is_absolute() and not Path(dp).exists():
                cand = Path(args.ir).resolve().parent / dp
                if cand.exists():
                    ch["data_path"] = str(cand)

    validation = deckkit.validate_deck(ir)
    figkit.write_json(out_dir / "validation.json", validation)

    artifacts = []
    status = args.status
    build_info = {}
    check_rep = None
    export_rep = None
    if validation["ok"]:
        try:
            import build_deck
            build_info = build_deck.build(ir, out_dir, args.template)
            artifacts.append({"name": "deck.pptx", "path": build_info["pptx"], "format": "pptx", "role": "pptx"})
            import check_deck
            check_rep = check_deck.check(ir, out_dir)
            figkit.write_json(out_dir / "deck_check.json", check_rep)
            import export_deck
            ex = export_deck.export(ir, out_dir)
            artifacts = ex["artifacts"]
            export_rep = ex["report"]
            status = status or ("success" if export_rep.get("true_render") else "partial")
        except Exception as e:  # noqa: BLE001
            status = status or "partial"
            ir.setdefault("uncertainty", []).append({"item": "build", "reason": str(e), "impact": "deck not fully built", "handling": "IR+validation saved; fix and re-run"})
            figkit.write_json(out_dir / "deck_ir.json", ir)
    else:
        status = status or "partial"
        figkit.write_json(out_dir / "deck_ir.json", ir)

    figkit.write_json(out_dir / "deck_ir.json", ir)
    if ir.get("provenance", {}).get("page_map"):
        figkit.write_json(out_dir / "provenance.json", ir["provenance"])

    notes = ""
    if not validation["ok"]:
        notes = "deck validation failed: " + "; ".join(validation["errors"])
    elif validation["warnings"]:
        notes = "warnings: " + "; ".join(validation["warnings"][:6])

    result = figkit.build_result(case, ir, artifacts, status, validation, export_rep, notes)
    result["deck_info"] = {k: build_info.get(k) for k in ("n_slides", "used_template", "slide_size_in") if k in build_info}
    result["deck_check"] = check_rep
    figkit.write_result(out_dir, result)
    print(json.dumps({"status": status, "validation_ok": validation["ok"], "errors": validation["errors"],
                      "n_slides": build_info.get("n_slides"), "n_artifacts": len(artifacts),
                      "deck_check": (check_rep or {}).get("overall"), "export": (export_rep or {}).get("overall"),
                      "result": str(out_dir / "result.json")}, ensure_ascii=False, indent=2))
    sys.exit(0 if validation["ok"] else 2)


if __name__ == "__main__":
    main()