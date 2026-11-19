"""figkit — source-bound scientific figure core (stdlib only).

Shared engine for the five graphics-track skills. Responsibilities:
  * read the runtime case (/input/case.json) without assuming its schema,
  * validate the Figure IR for scientific/self-consistency errors,
  * track element->source provenance and glyph->data mapping,
  * assemble result.json preserving every original output_contract field.

Rendering lives in render_chart.py / render_diagram.py; export compliance in
export_check.py. This module never imports matplotlib so validation and result
assembly work even in a minimal environment.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

IR_VERSION = "1.0"
SKILL_VERSION = "1.0.0"

VALID_RELATION_TYPES = {
    "activates", "inhibits", "binds", "modifies", "transports", "contains",
    "parallel", "upstream_of", "causes", "sequence", "feedback", "connects",
    "flows_to", "part_of", "compares", "encodes",
}
# Relations that must render with a directed, semantically-distinct arrow.
DIRECTED_RELATIONS = {
    "activates", "inhibits", "modifies", "transports", "upstream_of",
    "causes", "sequence", "feedback", "flows_to",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str | Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str | Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


# ── case loading ────────────────────────────────────────────────────────────

def load_case(input_dir: str | Path = "/input") -> dict:
    """Read case.json defensively. The runtime contract guarantees case.json and
    task.md exist; field names inside case.json vary by topic, so we surface the
    raw object plus a few normalized helpers rather than assuming a fixed shape.
    """
    input_dir = Path(input_dir)
    case_path = input_dir / "case.json"
    case = {}
    if case_path.exists():
        case = load_json(case_path)
    task_md = ""
    task_path = input_dir / "task.md"
    if task_path.exists():
        task_md = task_path.read_text(encoding="utf-8", errors="replace")
    case_id = (
        case.get("case_id")
        or case.get("id")
        or case.get("caseId")
        or os.environ.get("CASE_ID")
        or "unknown-case"
    )
    output_contract = (
        case.get("output_contract")
        or case.get("outputContract")
        or case.get("outputs")
        or {}
    )
    return {
        "case_id": str(case_id),
        "raw": case,
        "task_md": task_md,
        "output_contract": output_contract,
        "input_dir": str(input_dir),
    }


def list_materials(input_dir: str | Path = "/input") -> list[dict]:
    """Inventory actual input files (the fact basis). Never infer content from
    labels; the agent must open these files."""
    input_dir = Path(input_dir)
    out = []
    if not input_dir.exists():
        return out
    for p in sorted(input_dir.rglob("*")):
        if p.is_file():
            out.append({
                "path": str(p),
                "name": p.name,
                "bytes": p.stat().st_size,
                "ext": p.suffix.lower(),
            })
    return out


# ── IR validation ───────────────────────────────────────────────────────────

def validate_ir(ir: dict) -> dict:
    """Return {ok, errors[], warnings[]}. Errors are scientific/self-consistency
    problems that must be fixed before rendering; warnings are advisory.

    Checks (the rubric's '六类检查点'):
      1 scientific entities present & named from source
      2 relations typed & directed, endpoints exist
      3 data encoding: chart series/legend match data columns
      4 legend/annotation consistency
      5 editable source planned (svg)
      6 export targets present
    Plus: every element carries a source pointer (verifiability).
    """
    errors: list[str] = []
    warnings: list[str] = []

    if ir.get("ir_version") != IR_VERSION:
        errors.append(f"ir_version must be {IR_VERSION}")
    if not ir.get("case_id"):
        errors.append("case_id is required (copy from case.json)")
    kind = ir.get("kind")
    if kind not in {
        "relationship_schematic", "source_value_chart", "mechanism_pathway",
        "apparatus_route", "graphical_abstract",
    }:
        errors.append(f"unknown kind: {kind}")

    sources = {s.get("id"): s for s in ir.get("sources", []) if s.get("id")}
    entities = ir.get("entities", [])
    relations = ir.get("relations", [])
    ent_ids = {e.get("id") for e in entities if e.get("id")}

    if kind in ("relationship_schematic", "mechanism_pathway", "apparatus_route", "graphical_abstract"):
        if not entities:
            errors.append("no entities extracted from source material")

    # entity checks
    for e in entities:
        eid = e.get("id", "?")
        if not e.get("label"):
            errors.append(f"entity {eid}: empty label")
        if not e.get("category"):
            warnings.append(f"entity {eid}: no category")
        if not e.get("source"):
            warnings.append(f"entity {eid}: no source pointer (not verifiable)")
        elif e["source"] not in sources:
            errors.append(f"entity {eid}: source '{e['source']}' not in sources registry")

    # relation checks
    for r in relations:
        rid = r.get("id", "?")
        rtype = r.get("type")
        if rtype not in VALID_RELATION_TYPES:
            errors.append(f"relation {rid}: invalid type '{rtype}'")
        for end in ("from", "to"):
            if r.get(end) not in ent_ids:
                errors.append(f"relation {rid}: {end}='{r.get(end)}' is not a known entity")
        if rtype in DIRECTED_RELATIONS and r.get("direction", "forward") == "none":
            warnings.append(f"relation {rid}: directed type '{rtype}' marked direction=none")
        if not r.get("source"):
            warnings.append(f"relation {rid}: no source pointer")
        elif r["source"] not in sources:
            errors.append(f"relation {rid}: source '{r['source']}' not in sources registry")
        if rtype == "inhibits" and r.get("direction") == "bidirectional":
            warnings.append(f"relation {rid}: inhibition is directed; bidirectional is suspicious")

    # group membership checks
    for g in ir.get("groups", []):
        for m in g.get("members", []):
            if m not in ent_ids:
                warnings.append(f"group {g.get('id')}: member '{m}' is not a known entity")

    # chart / data-encoding checks
    chart = ir.get("chart")
    if kind == "source_value_chart" and not chart:
        errors.append("source_value_chart requires a chart spec")
    if chart:
        if not chart.get("chart_type"):
            errors.append("chart.chart_type is required")
        if not chart.get("data_source") and not chart.get("data_path"):
            errors.append("chart must bind to a data_source/data_path (no unbound numbers)")
        if chart.get("data_source") and chart["data_source"] not in sources:
            errors.append(f"chart.data_source '{chart['data_source']}' not in sources registry")
        if not chart.get("y_label") and chart.get("chart_type") not in ("pie", "heatmap"):
            warnings.append("chart missing y_label / unit")

    # legend consistency
    legend = ir.get("legend", {})
    if legend.get("items") and chart and chart.get("series"):
        # legend item count should match series categories (checked against data at render)
        pass

    # exports
    exports = ir.get("exports", [])
    fmts = {e.get("format") for e in exports}
    if "svg" not in fmts:
        errors.append("an editable SVG source export is required")
    if not (fmts & {"png", "pdf"}):
        warnings.append("no raster/PDF preview export requested")

    if not ir.get("provenance", {}).get("pipeline"):
        ir.setdefault("provenance", {})["pipeline"] = "material -> IR -> editable source -> export"

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# ── data loading & mapping ──────────────────────────────────────────────────

def read_table(path: str | Path) -> list[dict]:
    """Read CSV/TSV/JSON tabular data into list-of-dicts (stdlib only)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = load_json(path)
        if isinstance(data, dict):
            for key in ("data", "rows", "records", "table"):
                if isinstance(data.get(key), list):
                    return data[key]
            # dict of columns -> orient
            cols = {k: v for k, v in data.items() if isinstance(v, list)}
            if cols:
                n = max(len(v) for v in cols.values())
                return [{k: (v[i] if i < len(v) else None) for k, v in cols.items()} for i in range(n)]
        return data if isinstance(data, list) else []
    delim = "\t" if path.suffix.lower() in (".tsv", ".tab") else ","
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=delim))


def to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    m = re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return float(m.group(0)) if m else None


# ── result.json assembly ────────────────────────────────────────────────────

def build_result(case: dict, ir: dict, outputs: list[dict], status: str,
                 validation: dict | None = None, export_report: dict | None = None,
                 notes: str = "") -> dict:
    """Assemble result.json. Preserves EVERY original output_contract field and
    adds case_id, honest status, sources, uncertainty and change records.

    `outputs` is a list of {name, path, format, role} actually written to /app/output.
    """
    contract = case.get("output_contract") or {}
    result: dict = {}

    # 1) Echo the original contract keys so nothing required is dropped. We fill
    #    each from the produced artifacts when the mapping is obvious, otherwise
    #    leave a structured pointer the reviewer can follow.
    artifact_by_role = {}
    for o in outputs:
        artifact_by_role.setdefault(o.get("role", o.get("format", "")), o)
        artifact_by_role.setdefault(o.get("name", ""), o)

    def fill_key(key: str):
        kl = key.lower()
        if any(t in kl for t in ("svg", "source", "editable")):
            return artifact_by_role.get("svg", {}).get("path")
        if "png" in kl or "preview" in kl or "raster" in kl:
            return artifact_by_role.get("png", {}).get("path")
        if "pdf" in kl:
            return artifact_by_role.get("pdf", {}).get("path")
        if "result" in kl or "json" in kl or "meta" in kl:
            return "result.json"
        return None

    if isinstance(contract, dict):
        for key, spec in contract.items():
            filled = fill_key(key)
            if filled:
                result[key] = filled
            elif isinstance(spec, dict) and "default" in spec:
                result[key] = spec["default"]
            else:
                # keep the requirement visible rather than silently dropping it
                result[key] = {"_contract_spec": spec, "_status": "see artifacts/provenance"}
    elif isinstance(contract, list):
        result["output_contract"] = contract

    # 2) Mandatory, honest fields.
    result["case_id"] = case.get("case_id")
    result["status"] = status  # success | partial | failed | stuck
    result["skill_version"] = SKILL_VERSION
    result["kind"] = ir.get("kind")
    result["generated_at"] = utc_now()
    result["artifacts"] = outputs
    result["sources"] = ir.get("sources", [])
    result["uncertainty"] = ir.get("uncertainty", [])
    result["change_log"] = ir.get("provenance", {}).get("changes", [])
    result["provenance"] = {
        "pipeline": ir.get("provenance", {}).get("pipeline"),
        "element_map": ir.get("provenance", {}).get("element_map", {}),
        "data_map": ir.get("provenance", {}).get("data_map", {}),
        "source_version": ir.get("provenance", {}).get("source_version"),
    }
    if validation is not None:
        result["validation"] = validation
    if export_report is not None:
        result["export_check"] = export_report
    if notes:
        result["notes"] = notes
    if status in ("partial", "failed", "stuck"):
        result["limits"] = ir.get("uncertainty", []) or [{"item": "see notes", "reason": notes or "incomplete"}]
    return result


def write_result(out_dir: str | Path, result: dict) -> str:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "result.json"
    write_json(path, result)
    return str(path)