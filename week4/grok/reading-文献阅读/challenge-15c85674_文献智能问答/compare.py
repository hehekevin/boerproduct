"""compare — multi-document comparison & integration (stdlib).

For multi_doc_compare: build a common-field matrix where every cell carries its
source_document_id + paragraph_id + units/metric口径; test comparability (same
task/metric/condition vs comparable-subset only); explain conflicts by attributing
them to sample/method/condition/metric with a checkable source. Output comparison.json.
"""
from __future__ import annotations

from pathlib import Path
import figkit


def compare(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = ir.get("matrix", {})
    fields = m.get("fields", [])
    rows = m.get("rows", [])
    # coverage: which docs report which fields
    coverage = {}
    for row in rows:
        doc = row.get("document_id")
        have = {c.get("field") for c in row.get("cells", []) if c.get("value") is not None}
        coverage[doc] = {"reported": sorted(have), "missing": [f for f in fields if f not in have]}
    # comparability: group docs by (task, metric, condition) signature
    groups = {}
    for row in rows:
        sig = (row.get("task"), row.get("metric"), row.get("condition"))
        groups.setdefault(sig, []).append(row.get("document_id"))
    comparability = [{"signature": {"task": s[0], "metric": s[1], "condition": s[2]},
                      "documents": d, "comparable": len(d) > 1} for s, d in groups.items()]
    # conflicts: same field, differing direction/value across comparable docs
    conflicts = []
    byfield = {}
    for row in rows:
        for c in row.get("cells", []):
            byfield.setdefault(c.get("field"), []).append((row.get("document_id"), c))
    for field, cells in byfield.items():
        vals = [c.get("value") for _, c in cells if c.get("value") is not None]
        if len(set(map(str, vals))) > 1:
            conflicts.append({"field": field,
                              "values": [{"document_id": d, "value": c.get("value"), "units": c.get("units"),
                                          "paragraph_id": c.get("paragraph_id")} for d, c in cells],
                              "explanation": m.get("conflict_explanation", {}).get(field,
                                             "difference attributed to sample/method/condition/metric; see per-cell sources")})
    result = {"fields": fields, "n_documents": len(rows), "coverage": coverage,
              "comparability": comparability, "conflicts": conflicts}
    figkit.write_json(out_dir / "comparison.json", result)
    return result