"""assemble.py — research-track CLI (week4 convention).

Usage:
  PYTHONDONTWRITEBYTECODE=1 python assemble.py --ir <ir.json> --input /input --out /app/output

Pipeline: load case -> load IR (agent-filled from ACTUAL materials) ->
engine.validate_ir (write validation.json) -> engine.build (editable md/docx +
csv matrices + svg figures + provenance.json) -> honest result.json preserving
every output_contract key + case_id. Relative source files resolve against the
IR file's directory and the input directory.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import w4kit  # noqa: E402
import research_engine as engine  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="research engine assembler")
    ap.add_argument("--ir", required=True, help="agent-filled IR json")
    ap.add_argument("--input", default="/input", help="case input dir")
    ap.add_argument("--out", default="/app/output", help="output dir")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    case = w4kit.load_case(args.input)
    try:
        ir = w4kit.load_json(args.ir)
    except Exception as exc:
        result = {"case_id": case["case_id"], "status": "failed",
                  "kind": None, "generated_at": w4kit.utc_now(),
                  "notes": f"IR unreadable: {exc}", "artifacts": [],
                  "sources": [], "uncertainty": [{"item": "ir", "reason": str(exc)}],
                  "change_log": []}
        for key in (case.get("output_contract") or {}):
            result.setdefault(key, None)
        w4kit.write_result(out_dir, result)
        print(f"[assemble] failed: IR unreadable ({exc})")
        return 1

    ir["case_id"] = case["case_id"]
    ir["_base_dirs"] = [str(Path(args.ir).resolve().parent),
                        str(Path(args.input).resolve())]

    validation = engine.validate_ir(ir)
    w4kit.write_json(out_dir / "validation.json", validation)

    outputs, build_error = [], None
    try:
        outputs = engine.build(ir, case, out_dir)
    except Exception:
        build_error = traceback.format_exc(limit=6)
        (out_dir / "build_error.txt").write_text(build_error, encoding="utf-8")

    # honest status: success only when validation clean and build complete;
    # unverifiable quotes (binary PDFs) stay success but are declared uncertain.
    qsum = (ir.get("_computed") or {}).get("quote_check_summary") or {}
    unverifiable = sum(v for k, v in qsum.items() if k == "unverifiable")
    missing_files = any("not found" in w for w in validation["warnings"])
    if build_error and not outputs:
        status = "failed"
    elif build_error or not validation["ok"] or missing_files:
        status = "partial"
    else:
        status = "success"
    if unverifiable:
        ir.setdefault("uncertainty", []).append(
            {"item": "quote_verification",
             "reason": f"{unverifiable} 条摘录无法对二进制/缺失文件自动复核，"
                       "需人工对照原文 (human_confirm)"})

    extra = {}
    try:
        extra = engine.summarize(ir)
    except Exception:
        extra = {"summary_error": traceback.format_exc(limit=3)}
    if build_error:
        extra["build_error"] = build_error.splitlines()[-1]

    notes = ("source-bound research artifact; every claim binds source_id+"
             "paragraph_id+quote; PRISMA counts recomputed; bounded to provided sources")
    if status != "success":
        notes += f"; status={status}: " + "; ".join(
            validation["errors"][:5] or [build_error or "see validation.json"])
    result = w4kit.build_result(case, ir, outputs, status, validation,
                                extra=extra, notes=notes)
    w4kit.write_result(out_dir, result)
    print(f"[assemble] case={case['case_id']} kind={ir.get('kind')} "
          f"status={status} errors={len(validation['errors'])} "
          f"warnings={len(validation['warnings'])} outputs={len(outputs)}")
    for e in validation["errors"][:10]:
        print(f"  ERROR: {e}")
    return 0 if status in ("success", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())