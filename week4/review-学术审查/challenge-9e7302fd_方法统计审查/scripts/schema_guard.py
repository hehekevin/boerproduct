#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（num-consistency-audit 结构校验）。

校验 /app/output/result.json 满足 case.json output_contract 全字段 + 本题业务
schema（数字一致性单方向）。只做结构校验，不改业务内容。退出码恒 0。
用法：
    schema_guard.py --result /app/output/result.json [--case /input/case.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RESULT_REQUIRED = ["material_gaps", "environment", "manuscript_overview",
                   "severity_rubric", "number_audits", "findings",
                   "conflict_summary", "unchecked", "run_status", "verdict",
                   "verdict_basis", "gain_evidence", "efficiency"]
AUDIT_REQUIRED = ["audit_id", "kind", "value", "source", "raw", "consistent",
                  "conflicts_with", "note"]
FINDING_REQUIRED = ["finding_id", "kind", "rule", "quote", "location", "severity",
                    "evidence", "revision_suggestion", "status", "conflict_ids"]
TOP_REQUIRED = ["case_id", "status", "result", "claims", "uncertainties", "changelog"]


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
        args, _unknown = ap.parse_known_args()
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print("[schema_guard] 参数解析失败（降级）: %s" % e)
        return 0

    problems = []
    result = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[schema_guard] FAIL: result.json 读取失败: %s（不中断交付）" % e)
        return 0

    if isinstance(result, dict):
        if not result.get("case_id"):
            problems.append("缺少 case_id")
        for fn in TOP_REQUIRED:
            if fn not in result:
                problems.append("缺少顶层契约字段: %s" % fn)
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            for fn in contract_fields(case):
                if fn not in result:
                    problems.append("缺少 output_contract 字段: %s" % fn)
        except Exception:
            pass
    else:
        problems.append("result.json 顶层非对象")

    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        problems.append("result 应为对象")
    else:
        for fn in RESULT_REQUIRED:
            if fn not in inner:
                problems.append("缺少业务字段: result.%s" % fn)
        for i, a in enumerate(inner.get("number_audits") or []):
            if not isinstance(a, dict):
                problems.append("number_audits[%d] 非对象" % i)
                continue
            for sf in AUDIT_REQUIRED:
                if sf not in a:
                    problems.append("number_audits[%d] 缺 %s" % (i, sf))
        for i, f in enumerate(inner.get("findings") or []):
            if not isinstance(f, dict):
                problems.append("findings[%d] 非对象" % i)
                continue
            for sf in FINDING_REQUIRED:
                if sf not in f:
                    problems.append("findings[%d] 缺 %s" % (i, sf))

    if problems:
        print("[schema_guard] FAIL（%d 处，不中断交付）:" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 0
    print("[schema_guard] PASS: 结构完整（case_id=%s）" % result.get("case_id"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[schema_guard] 未预期异常（降级，exit 0）: %s" % e)
        sys.exit(0)