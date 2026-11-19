#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_skeleton.py — Step 0 落骨架 + 数据集/问题清单 + 查询口径模板。
退出码恒 0；失败也写完整骨架（status=input_error）。键归属：基础键全部归本脚本。
"""
import argparse, copy, json, os, sys, time

MARKER = "sci-db-query-analyze-v1"
MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "未知", "缺失"}

# 标识符合法性：显式 ASCII/中文字符集判定，禁止用 isalpha()（汉字 isalpha()==True 会误放行）
import re
IDENT_RE = re.compile(r"^[\w.\-\u4e00-\u9fff]+$", re.UNICODE)


def ident_ok(s):
    return isinstance(s, str) and bool(IDENT_RE.match(s)) and not s.strip() == ""


def marker_hit():
    try:
        skill = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md")
        with open(skill, "r", encoding="utf-8") as f:
            return MARKER in f.read()
    except Exception:
        return False


def first_key(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def load_case(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_rows(ds):
    """行兼容 list[dict] 与 {columns:[], rows:[[...]]} 矩阵；返回 (rows, columns)。"""
    rows = first_key(ds, ["rows", "records", "data", "samples"])
    cols = first_key(ds, ["columns", "fields", "schema"]) or []
    if isinstance(rows, dict) and "columns" in rows:
        cols = rows["columns"]; rows = rows.get("rows", [])
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        if not cols and rows:
            cols = ["col_%d" % i for i in range(len(rows[0]))]
        rows = [dict(zip(cols, r)) for r in rows]
    return rows or [], cols or []


def extract_datasets(case):
    out = []
    raw = first_key(case, ["datasets", "tables", "snapshots", "data", "sources"], [])
    if isinstance(raw, dict):
        raw = [{"dataset_id": k, **(v if isinstance(v, dict) else {"rows": v})} for k, v in raw.items()]
    for i, ds in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(ds, dict):
            continue
        did = first_key(ds, ["dataset_id", "id", "name", "table", "table_name"], "ds-%02d" % (i + 1))
        rows, cols = normalize_rows(ds)
        out.append({"dataset_id": did, "columns": cols if cols else (list(rows[0].keys()) if rows else []),
                    "row_count": len(rows), "source_ref": "datasets[%d]" % i, "rows": rows})
    return out


def extract_questions(case):
    raw = first_key(case, ["questions", "tasks", "query_tasks", "requests", "analyses"], [])
    out = []
    for i, q in enumerate(raw if isinstance(raw, list) else []):
        if isinstance(q, str):
            out.append({"question_id": "Q%02d" % (i + 1), "text": q, "intent": "unknown"})
        elif isinstance(q, dict):
            out.append({"question_id": first_key(q, ["question_id", "id", "qid"], "Q%02d" % (i + 1)),
                        "text": first_key(q, ["text", "question", "prompt", "description"], ""),
                        "intent": first_key(q, ["intent", "type"], "unknown")})
    return out


def skeleton(case_id, contract_fields, datasets, questions, note):
    result = {
        "material_gaps": [], "environment": {"python_version": sys.version.split()[0], "packages": "stdlib-only",
        "seed": None, "hardware_note": None},
        "query_scope": {"questions": questions, "snapshot_note": note, "query_convention": {
            "filter_ops": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "nin", "contains", "between", "isnull", "notnull"],
            "agg_fns": ["count", "sum", "avg", "min", "max", "nunique"],
            "missing_tokens": sorted(MISSING_TOKENS),
            "empty_result_rule": "row_count==0 必须登记 boundary_registry，不静默丢弃"}},
        "field_dictionary": [], "queries": [], "query_results": [], "recompute": {"computed_by": None, "checks": []},
        "boundary_registry": [], "query_log": [],
        "coverage": {"questions_total": len(questions), "queries_total": 0, "answered_questions": 0,
                     "empty_results": 0, "boundary_registered": 0, "ratio": 0.0},
        "pending_review": [], "steps": [], "run_status": {"state": "partial", "reason": "skeleton written", "manual_takeover": []},
        "verdict": "not_appraised", "verdict_basis": "骨架已落，未执行查询",
        "gain_evidence": {"runs": [], "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [], "boundaries": [], "failure_conditions": []},
        "efficiency": {"wall_clock_seconds_total": None, "checker_runs": 0, "model_requests": None, "reproduce": ""},
    }
    for f in contract_fields:
        result[f] = result.get(f, None)
    return {"case_id": case_id, "status": "partial", "result": result, "claims": [],
            "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [], "summary": ""},
            "changelog": [{"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "change": "skeleton written by build_skeleton.py"}],
            "self_check": [], "unbacked_numbers": [], "unbacked_evidence": [], "validator_verdict": None,
            "gates": [{"gate": "case_contract", "state": "enforced", "note": note}]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work-dir", default="/app/work")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    os.makedirs(a.work_dir, exist_ok=True)
    note, case_id, contract, datasets, questions = "", None, [], [], []
    try:
        case = load_case(a.case)
        case_id = first_key(case, ["case_id", "id", "caseId"], None)
        oc = first_key(case, ["output_contract", "outputContract"], [])
        contract = oc if isinstance(oc, list) else (list(oc.keys()) if isinstance(oc, dict) else [])
        datasets = extract_datasets(case)
        questions = extract_questions(case)
        note = "case.json loaded; datasets=%d questions=%d" % (len(datasets), len(questions))
        if not datasets:
            note += "; WARN: no datasets detected — 按 SKILL.md 手工核对键名"
    except Exception as e:
        note = "case load failed: %s" % e
    sk = skeleton(case_id, contract, datasets, questions, note)
    try:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(sk, f, ensure_ascii=False, indent=2)
        ledger = {"declared_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "query_convention": sk["result"]["query_scope"]["query_convention"],
                  "datasets": [{k: v for k, v in d.items() if k != "rows"} for d in datasets]}
        with open(os.path.join(a.work_dir, "query_scope.json"), "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)
    except Exception as e:
        note += "; write failed: %s" % e
    print(json.dumps({"script": "build_skeleton", "marker_hit": marker_hit(), "exit": 0,
                      "datasets": len(datasets), "questions": len(questions), "note": note}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
