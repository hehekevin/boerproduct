#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（各文献阅读 Skill 共用的最终结构校验器）。

用途：在 Skill 运行的最后阶段，校验 /app/output/result.json 是否满足
case.json 的 output_contract（全部字段名）+ 题目业务 schema，失败时打印缺失
字段清单供回填。绝不改写业务内容，只做结构校验。全捕获容错，绝不崩溃。

用法：
    python3 schema_guard.py --result /app/output/result.json [--case /input/case.json] [--extra-schema schema.json]
退出码：恒为 0（PASS/FAIL 记录在 stdout 与 --out 报告，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 本题业务 schema：result 内必备的键（题面输出要求表逐项对应）
RESULT_REQUIRED = [
    "material_gaps", "environment", "parameters", "candidates", "metric_checks",
    "attributions", "steps", "declared_tolerances", "recomputability",
    "run_status", "verdict", "verdict_basis", "gain_evidence", "efficiency",
]
TOP_REQUIRED = ["case_id", "status", "result", "claims", "uncertainties", "changelog"]


def contract_fields(case):
    """从 case.json 提取 output_contract 字段名（兼容多种排布）。"""
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
        ap.add_argument("--out", default=None, help="结构校验报告落盘路径")
        ap.add_argument("--extra-schema", default=None,
                        help='业务 schema：{"required":[...], "arrays":{"answers":[...]}}')
        ap.add_argument("--root-array", default=None,
                        help="result.json 顶层为数组时每个元素的必需字段（逗号分隔）")
        ap.add_argument("--skip-business", action="store_true",
                        help="只校验 output_contract，跳过本题业务 schema")
        args = ap.parse_args()
    except Exception as e:
        print("[schema_guard] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    result = None
    try:
        if not os.path.exists(args.result):
            print("[schema_guard] FAIL: result.json 不存在：%s（不中断交付）" % args.result)
            _dump_report(args.out, {"ok": False, "verdict": "FAIL",
                                     "problems": ["result.json 不存在"], "counts": {}})
            return 0
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[schema_guard] FAIL: result.json 读取/解析失败：%s（不中断交付）" % e)
        _dump_report(args.out, {"ok": False, "verdict": "FAIL",
                                 "problems": ["result.json 读取/解析失败：%s" % e],
                                 "counts": {}})
        return 0

    try:
        if isinstance(result, dict):
            if not result.get("case_id"):
                problems.append("缺少 case_id")
            for fname in TOP_REQUIRED:
                if fname not in result:
                    problems.append("缺少顶层契约字段: %s" % fname)
            if os.path.exists(args.case):
                try:
                    with open(args.case, "r", encoding="utf-8") as f:
                        case = json.load(f)
                    for fname in contract_fields(case):
                        if fname not in result:
                            problems.append("缺少 output_contract 字段: %s" % fname)
                except Exception as e:
                    problems.append("case.json 读取失败（跳过契约校验）: %s" % e)
    except Exception as e:
        problems.append("契约校验异常: %s" % e)

    try:
        if not args.skip_business and isinstance(result, dict):
            inner = result.get("result")
            if not isinstance(inner, dict):
                problems.append("result 应为对象")
            else:
                for fname in RESULT_REQUIRED:
                    if fname not in inner:
                        problems.append("缺少业务字段: result.%s" % fname)
    except Exception as e:
        problems.append("业务字段校验异常: %s" % e)

    try:
        if args.extra_schema and os.path.exists(args.extra_schema):
            with open(args.extra_schema, "r", encoding="utf-8") as f:
                sch = json.load(f)
            for fname in sch.get("required", []):
                if isinstance(result, dict) and fname not in result:
                    problems.append("缺少业务字段: %s" % fname)
            for arr, sub in (sch.get("arrays") or {}).items():
                v = result.get(arr) if isinstance(result, dict) else None
                if v is None:
                    problems.append("缺少数组字段: %s" % arr)
                    continue
                if not isinstance(v, list):
                    problems.append("%s 应为数组，实际: %s" % (arr, type(v).__name__))
                    continue
                for i, item in enumerate(v):
                    if not isinstance(item, dict):
                        problems.append("%s[%d] 不是对象" % (arr, i))
                        continue
                    for sf in sub:
                        if sf not in item:
                            problems.append("%s[%d] 缺少子字段: %s" % (arr, i, sf))
    except Exception as e:
        problems.append("业务 schema 校验异常: %s" % e)

    try:
        if args.root_array and isinstance(result, list):
            need = [x for x in args.root_array.split(",") if x]
            for i, item in enumerate(result):
                if not isinstance(item, dict):
                    problems.append("result[%d] 不是对象" % i)
                    continue
                for fname in need:
                    if fname not in item:
                        problems.append("result[%d] 缺少字段: %s" % (i, fname))
    except Exception as e:
        problems.append("顶层数组校验异常: %s" % e)

    report = {"ok": not problems, "verdict": "PASS" if not problems else "FAIL",
              "problems": problems,
              "counts": {"problems": len(problems)}}
    _dump_report(args.out, report)
    if problems:
        print("[schema_guard] FAIL（%d 处，不中断交付）:" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        if len(problems) > 40:
            print("  ... 共 %d 处" % len(problems))
        return 0

    print("[schema_guard] PASS: 结构完整（case_id=%s）" % (
        result.get("case_id") if isinstance(result, dict) else "(array)"))
    return 0


def _dump_report(out_path, report):
    if not out_path:
        return
    try:
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
        print("[schema_guard] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
