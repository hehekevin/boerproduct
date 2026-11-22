#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（各文献阅读 Skill 共用的最终校验器）。

用途：在 Skill 运行的最后阶段，校验 /app/output/result.json 是否满足
case.json 的 output_contract（全部字段名）+ 本题业务 schema，并在失败时
打印缺失字段清单，供 Agent 回填后重跑。绝不改写业务内容，只做结构校验。

用法：
    python schema_guard.py --result /app/output/result.json \
        [--case /input/case.json] [--extra-schema schema.json]

退出码：0=通过；1=结构失败（打印缺失/多余字段）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def contract_fields(case: dict) -> list:
    """从 case.json 提取 output_contract 字段名（兼容多种排布）。"""
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None:
        return []
    if isinstance(oc, dict):
        # 通用契约：键=字段名，值=说明文字。全部键视为必填字段。
        # 兼容 {"fields":[...]} 显式列表排布。
        for key in ("fields", "required_fields", "result.json", "result"):
            v = oc.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
        return [str(k) for k in oc.keys()]
    if isinstance(oc, list):
        return [str(x) for x in oc]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--extra-schema", default=None,
                    help="题目业务 schema：{\"required\":[...], \"arrays\":{\"answers\":[...子字段]}}")
    ap.add_argument("--root-array", default=None,
                    help="若 result.json 顶层是数组且每个元素都需满足同一 schema，给出元素内必需字段（逗号分隔）")
    args = ap.parse_args()

    problems = []
    if not os.path.exists(args.result):
        print("[schema_guard] FAIL: result.json 不存在：%s" % args.result)
        return 1

    try:
        result = load_json(args.result)
    except Exception as e:
        print("[schema_guard] FAIL: result.json 不是合法 JSON：%s" % e)
        return 1

    # 1) case_id 必须存在
    if isinstance(result, dict):
        if not result.get("case_id"):
            problems.append("缺少 case_id")
        # 2) output_contract 全字段
        if os.path.exists(args.case):
            try:
                case = load_json(args.case)
                for f in contract_fields(case):
                    if f not in result:
                        problems.append("缺少 output_contract 字段: %s" % f)
            except Exception as e:
                problems.append("case.json 读取失败（跳过契约校验）: %s" % e)

    # 3) 题目业务 schema
    if args.extra_schema and os.path.exists(args.extra_schema):
        sch = load_json(args.extra_schema)
        for f in sch.get("required", []):
            if isinstance(result, dict) and f not in result:
                problems.append("缺少业务字段: %s" % f)
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

    # 4) 顶层数组模式（逐案例的题）
    if args.root_array and isinstance(result, list):
        need = [x for x in args.root_array.split(",") if x]
        for i, item in enumerate(result):
            if not isinstance(item, dict):
                problems.append("result[%d] 不是对象" % i)
                continue
            for f in need:
                if f not in item:
                    problems.append("result[%d] 缺少字段: %s" % (i, f))

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
    sys.exit(main())
