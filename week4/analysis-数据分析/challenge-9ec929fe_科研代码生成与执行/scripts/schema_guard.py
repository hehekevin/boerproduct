#!/usr/bin/env python3
"""schema_guard.py — 结构守卫（sci-code-exec，通用）。

校验 result.json 的结构完整性：output_contract 全部字段 + 本题业务 schema 全部
键一个不缺（缺键就点名，不判断业务对错——业务对错归 verify_check.py）。报告
写入 --out，退出码恒为 0。

用法：
    python3 schema_guard.py --result /app/output/result.json --case /input/case.json \
        --out /app/work/schema_guard.json
"""
from __future__ import annotations

import argparse
import json
import sys

TOP_REQUIRED = ("case_id", "status", "result", "claims", "uncertainties", "changelog")
TOP_OPTIONAL_EMIT = ("self_check", "gates", "unbacked_numbers", "unbacked_evidence",
                     "validator_verdict")
RESULT_REQUIRED = ("material_gaps", "environment", "task_scope", "data_dictionary",
                   "cleaning_rules", "requirements", "code_artifacts", "coverage_map",
                   "steps", "execution_traces", "stats", "recompute", "anomalies",
                   "coverage", "conflicts", "pending_review", "run_status", "verdict",
                   "verdict_basis", "gain_evidence", "efficiency")
ENV_FIELDS = ("python_version", "packages", "seed", "hardware_note")
RUN_STATUS_FIELDS = ("state", "reason", "manual_takeover")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        args = ap.parse_args()
    except Exception as e:
        print("[schema_guard] 参数解析失败（已降级）: %s" % e)
        return 0

    problems, checks = [], []
    res = load_json(args.result)
    if not isinstance(res, dict):
        problems.append("result.json 不存在或不可解析: %s" % args.result)
        report = {"verdict": "FAIL", "problems": problems, "checks": checks}
        _dump(args.out, report)
        print("[schema_guard] FAIL（%d 处）" % len(problems))
        return 0

    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"

    for k in TOP_REQUIRED:
        ok = k in res
        checks.append({"item": "top.%s" % k, "applied": True, "match": ok})
        if not ok:
            problems.append("缺顶层必需键: %s" % k)
    for k in TOP_OPTIONAL_EMIT:
        checks.append({"item": "top.%s (emit)" % k, "applied": k in res, "match": True})

    inner = res.get("result")
    if isinstance(inner, dict):
        for k in RESULT_REQUIRED:
            ok = k in inner
            checks.append({"item": "result.%s" % k, "applied": True, "match": ok})
            if not ok:
                problems.append("缺 result 业务键: %s" % k)
        env = inner.get("environment")
        if isinstance(env, dict):
            for k in ENV_FIELDS:
                checks.append({"item": "result.environment.%s" % k, "applied": True,
                              "match": k in env})
                if k not in env:
                    problems.append("缺 result.environment.%s" % k)
        rs = inner.get("run_status")
        if isinstance(rs, dict):
            for k in RUN_STATUS_FIELDS:
                checks.append({"item": "result.run_status.%s" % k, "applied": True,
                              "match": k in rs})
                if k not in rs:
                    problems.append("缺 result.run_status.%s" % k)
    else:
        problems.append("result 非对象")

    if case_state == "enforced":
        for fname in contract_fields(case):
            ok = fname in res
            checks.append({"item": "contract.%s" % fname, "applied": True, "match": ok})
            if not ok:
                problems.append("缺 output_contract 字段: %s" % fname)

    verdict = "PASS" if not problems else "FAIL"
    report = {"verdict": verdict, "problems": problems, "checks": checks,
              "case_contract": case_state}
    _dump(args.out, report)
    print("[schema_guard] %s（检查项 %d 条，问题 %d 处）"
          % (verdict, len(checks), len(problems)))
    for p in problems[:20]:
        print("  - %s" % p)
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        import os
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[schema_guard] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
