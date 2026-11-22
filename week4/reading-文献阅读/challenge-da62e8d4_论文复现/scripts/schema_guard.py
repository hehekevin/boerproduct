#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（各文献阅读 Skill 共用的最终结构校验器）。

用途：在 Skill 运行的最后阶段，校验 /app/output/result.json 是否满足
case.json 的 output_contract（全部字段名）+ 题目业务 schema，失败时打印缺失
字段清单供回填。绝不改写业务内容，只做结构校验。全捕获容错，绝不崩溃。

用法：
    python schema_guard.py --result /app/output/result.json [--case /input/case.json] [--extra-schema schema.json]
退出码：0=通过；1=结构失败。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


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
        ap.add_argument("--extra-schema", default=None,
                        help='业务 schema：{"required":[...], "arrays":{"answers":[...]}}')
        ap.add_argument("--root-array", default=None,
                        help="result.json 顶层为数组时每个元素的必需字段（逗号分隔）")
        args = ap.parse_args()
    except Exception as e:
        print("[schema_guard] 参数解析失败: %s" % e)
        return 1

    problems = []
    result = None
    try:
        if not os.path.exists(args.result):
            print("[schema_guard] FAIL: result.json 不存在：%s" % args.result)
            return 1
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[schema_guard] FAIL: result.json 读取/解析失败：%s" % e)
        return 1

    try:
        if isinstance(result, dict):
            if not result.get("case_id"):
                problems.append("缺少 case_id")
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

    if problems:
        print("[schema_guard] FAIL（%d 处）:" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        if len(problems) > 40:
            print("  ... 共 %d 处" % len(problems))
        return 1

    print("[schema_guard] PASS: 结构完整（case_id=%s）" % (
        result.get("case_id") if isinstance(result, dict) else "(array)"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[schema_guard] 未预期异常（已降级）: %s" % e)
        sys.exit(1)
