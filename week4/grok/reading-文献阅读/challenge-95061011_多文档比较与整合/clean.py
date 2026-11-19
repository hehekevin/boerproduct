"""clean — literature-data cleaning & standardization (stdlib).

For data_cleaning: unify field names/types/allowed values; convert units preserving
the ORIGINAL value + conversion formula + precision; merge duplicates by an
explainable key (never merge different experiments/substances); emit anomalies and
pending-confirm items. Every record keeps its source. Deterministic + auditable.
"""
from __future__ import annotations

import re
from pathlib import Path
import figkit

# factor to base unit (SI-ish). compound handled by simple prefix*unit.
PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0,
          "k": 1e3, "M": 1e6, "G": 1e9}
BASE = {"M": 1.0, "g": 1.0, "L": 1.0, "m": 1.0, "s": 1.0, "V": 1.0, "A": 1.0, "K": 1.0, "mol": 1.0, "Pa": 1.0, "J": 1.0, "W": 1.0, "Hz": 1.0}


def parse_unit(u):
    u = (u or "").strip()
    m = re.match(r"^([pnuµmkMG]?)([A-Za-z]+)$", u)
    if not m:
        return None
    pre, base = m.groups()
    if base not in BASE:
        return None
    return PREFIX.get(pre, 1.0), base


def convert(value, from_u, to_u):
    a, b = parse_unit(from_u), parse_unit(to_u)
    if not a or not b or a[1] != b[1]:
        return None
    factor = a[0] / b[0]
    return {"from": from_u, "to": to_u, "factor": factor,
            "formula": f"value[{to_u}] = value[{from_u}] * {factor:g}",
            "converted": value * factor}


def normalize_field(name, mapping):
    return mapping.get(name.strip().lower(), name.strip())


def dedup_key(rec, keys):
    return tuple(str(rec.get(k, "")).strip().lower() for k in keys)


def clean(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    c = ir.get("cleaning", {})
    mapping = c.get("field_mapping", {})
    allowed = c.get("allowed_values", {})
    keys = c.get("dedup_keys", ["source", " substance", "condition"])
    records, anomalies, pending = [], [], []
    seen = {}
    for r in c.get("records", []):
        rec = dict(r)
        rec["normalized_field"] = normalize_field(r.get("field", ""), mapping)
        # unit conversion
        if r.get("unit") and c.get("target_unit"):
            cv = convert(float(r.get("original", r.get("value", 0))), r["unit"], c["target_unit"])
            if cv:
                rec["unit_conversion"] = cv
                rec["value"] = cv["converted"]
                rec["units"] = c["target_unit"]
            else:
                anomalies.append({"id": r.get("id"), "issue": f"cannot convert {r['unit']}->{c['target_unit']}", "handling": "keep original; pending"})
                pending.append(r.get("id"))
        # allowed values
        av = allowed.get(rec["normalized_field"])
        if av and rec.get("value") not in av and str(rec.get("value")) not in [str(x) for x in av]:
            anomalies.append({"id": r.get("id"), "issue": f"value {rec.get('value')} not in allowed set", "handling": "pending confirm"})
            pending.append(r.get("id"))
        # dedup
        k = dedup_key(rec, keys)
        if k in seen:
            anomalies.append({"id": r.get("id"), "issue": f"duplicate of {seen[k]} by key {keys}", "handling": "merged; keep both sources"})
            rec["merged_with"] = seen[k]
        else:
            seen[k] = r.get("id")
        records.append(rec)
    result = {"records": records, "anomalies": anomalies, "pending": pending,
              "n_records": len(records), "n_anomalies": len(anomalies)}
    figkit.write_json(out_dir / "cleaned.json", result)
    return result