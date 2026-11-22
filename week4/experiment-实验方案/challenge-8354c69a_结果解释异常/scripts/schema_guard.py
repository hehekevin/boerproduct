#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（exp-result-anomaly 结构校验器）。

校验 /app/output/result.json 是否满足 case.json 的 output_contract 全字段 +
本题业务 schema。只做结构校验，不改业务内容。退出码恒为 0。

用法：
    python3 schema_guard.py --result /app/output/result.json [--case /input/case.json] [--out 报告路径]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RESULT_REQUIRED = ["material_gaps", "environment", "contract_fields", "dataset_ids",
                   "thresholds", "anomalies", "detection", "input_files",
                   "run_status", "verdict", "verdict_basis"]
TOP_REQUIRED = ["case_id", "status", "result", "uncertainties", "changelog"]
ANOMALY_REQUIRED = ["anomaly_id", "dataset_id", "dimension", "object_ref",
                    "anomaly_type", "observed_value", "unit", "threshold_used",
                    "severity", "baseline", "baseline_ref", "deviation",
                    "evidence_location", "possible_cause"]


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


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        args = ap.parse_args()
    except Exception as e:
        print("[schema_guard] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    result = None
    try:
        if not os.path.exists(args.result):
            problems.append("result.json 不存在")
        else:
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)
    except Exception as e:
        problems.append("result.json 读取/解析失败: %s" % e)

    if result is not None:
        try:
            if isinstance(result, dict):
                if not result.get("case_id"):
                    problems.append("缺少 case_id")
                for f in TOP_REQUIRED:
                    if f not in result:
                        problems.append("缺少顶层字段: %s" % f)
                if os.path.exists(args.case):
                    try:
                        with open(args.case, "r", encoding="utf-8") as f:
                            case = json.load(f)
                        for f in contract_fields(case):
                            if f not in result:
                                problems.append("缺少 output_contract 字段: %s" % f)
                    except Exception as e:
                        problems.append("case.json 读取失败（跳过契约校验）: %s" % e)
        except Exception as e:
            problems.append("契约校验异常: %s" % e)

        try:
            inner = result.get("result") if isinstance(result, dict) else None
            if not isinstance(inner, dict):
                problems.append("result 应为对象")
            else:
                for f in RESULT_REQUIRED:
                    if f not in inner:
                        problems.append("缺少业务字段: result.%s" % f)
                for i, a in enumerate(inner.get("anomalies") or []):
                    if not isinstance(a, dict):
                        problems.append("anomalies[%d] 不是对象" % i)
                        continue
                    for sf in ANOMALY_REQUIRED:
                        if sf not in a:
                            problems.append("anomalies[%d] 缺少子字段: %s" % (i, sf))
                det = inner.get("detection") or {}
                if isinstance(det, dict) and "thresholds_used" not in det:
                    problems.append("detection 缺少键: thresholds_used")
        except Exception as e:
            problems.append("业务字段校验异常: %s" % e)

    report = {"ok": not problems, "verdict": "PASS" if not problems else "FAIL",
              "problems": problems, "counts": {"problems": len(problems)}}
    try:
        if args.out:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

    if problems:
        print("[schema_guard] FAIL（%d 处）:" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        return 0
    print("[schema_guard] PASS: 结构完整（case_id=%s）" % (
        result.get("case_id") if isinstance(result, dict) else "(array)"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[schema_guard] 未预期异常（已降级）: %s" % e)
        sys.exit(0)