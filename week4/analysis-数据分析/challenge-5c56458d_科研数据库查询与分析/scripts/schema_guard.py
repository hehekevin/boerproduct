#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schema_guard.py — 结构守卫：顶层键 + output_contract 字段 + result 业务 schema 全字段。
纯报告（--out），不写 result.json。退出码恒 0；判据是报告 verdict。
"""
import argparse, json, os, sys

MARKER = "sci-db-query-analyze-v1"
REQUIRED_TOP = ["case_id", "status", "result", "claims", "uncertainties", "changelog",
                "self_check", "unbacked_numbers", "unbacked_evidence", "validator_verdict", "gates"]
REQUIRED_RESULT = ["material_gaps", "environment", "query_scope", "field_dictionary", "queries",
                   "query_results", "recompute", "boundary_registry", "query_log", "coverage",
                   "pending_review", "steps", "run_status", "verdict", "verdict_basis",
                   "gain_evidence", "efficiency"]
REQUIRED_SCOPE = {"query_scope": ["questions", "snapshot_note", "query_convention"],
                  "recompute": ["computed_by", "checks"],
                  "coverage": ["questions_total", "queries_total", "answered_questions", "empty_results", "boundary_registered", "ratio"],
                  "run_status": ["state", "reason", "manual_takeover"],
                  "gain_evidence": ["runs", "delta_normal_minus_degraded", "mechanism_to_metric_map", "boundaries", "failure_conditions"]}


def marker_hit():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md"), "r", encoding="utf-8") as f:
            return MARKER in f.read()
    except Exception:
        return False


def first_key(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    report = {"script": "schema_guard", "marker_hit": marker_hit(), "exit": 0, "verdict": "PASS", "problems": []}
    try:
        with open(a.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(a.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        P = report["problems"]
        for k in REQUIRED_TOP:
            if k not in result:
                P.append("[top] 缺顶层键: %s" % k)
        r = result.get("result")
        if not isinstance(r, dict):
            P.append("[result] result 不是对象")
            r = {}
        for k in REQUIRED_RESULT:
            if k not in r:
                P.append("[result] 缺业务键: %s" % k)
        for sect, keys in REQUIRED_SCOPE.items():
            sect_obj = r.get(sect)
            if not isinstance(sect_obj, dict):
                P.append("[%s] 缺失或非对象，无法核对子键 %s" % (sect, keys))
                continue
            for k in keys:
                if k not in sect_obj:
                    P.append("[%s] 缺子键: %s" % (sect, k))
        oc = first_key(case, ["output_contract"], [])
        fields = oc if isinstance(oc, list) else (list(oc.keys()) if isinstance(oc, dict) else [])
        for f_ in fields:
            if f_ not in result:
                P.append("[contract] 缺 output_contract 字段: %s" % f_)
        if result.get("status") not in ("answered", "partial", "insufficient_evidence", "input_error"):
            P.append("[enum] status 非法: %s" % result.get("status"))
        if (r.get("run_status") or {}).get("state") not in ("success", "partial", "unable_to_determine", "refused"):
            P.append("[enum] run_status.state 非法: %s" % (r.get("run_status") or {}).get("state"))
    except Exception as e:
        report["verdict"], report["error"] = "FAIL", str(e)
    report["verdict"] = "FAIL" if report["problems"] else report["verdict"]
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("script", "exit", "verdict", "problems", "marker_hit")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
