#!/usr/bin/env python3
"""schema_guard.py — 输出契约守卫（kbqa-cite 最终结构校验器）。

用途：在 Skill 运行的最后阶段，校验 /app/output/result.json 是否满足
case.json 的 output_contract（全部字段名）+ 本题业务 schema，失败时打印缺失
字段清单供回填。绝不改写业务内容，只做结构校验。全捕获容错，绝不崩溃。

用法：
    python3 schema_guard.py --result /app/output/result.json [--case /input/case.json] [--out 报告路径]
退出码：恒为 0（PASS/FAIL 记录在 stdout 与 --out 报告，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 本题业务 schema：result 内必备的键（题面输出要求表逐项对应）
RESULT_REQUIRED = [
    "material_gaps", "environment", "knowledge_base", "questions", "answers",
    "gaps", "retrieval", "coverage", "conflicts", "steps",
    "run_status", "verdict", "verdict_basis", "gain_evidence", "efficiency",
]
QUESTION_REQUIRED = ["question_id", "question", "decomposed", "subquestions"]
SUBQ_REQUIRED = ["sub_id", "sub_question"]
ANSWER_REQUIRED = ["sub_id", "question_id", "sub_question", "status",
                   "confidence", "sentences", "miss_reason"]
SENTENCE_REQUIRED = ["sentence_id", "text", "source_entry", "quote",
                     "quote_location", "confidence"]
GAP_REQUIRED = ["sub_id", "missing_topic", "needed_action", "kind"]
ENTRY_REQUIRED = ["entry_id", "source_ref", "kind"]
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
        inner = result.get("result") if isinstance(result, dict) else None
        if not isinstance(inner, dict):
            problems.append("result 应为对象")
        else:
            for fname in RESULT_REQUIRED:
                if fname not in inner:
                    problems.append("缺少业务字段: result.%s" % fname)
            for i, e in enumerate((inner.get("knowledge_base") or {}).get("entries") or []):
                if isinstance(e, dict):
                    for sf in ENTRY_REQUIRED:
                        if sf not in e:
                            problems.append("knowledge_base.entries[%d] 缺少子字段: %s" % (i, sf))
            for i, q in enumerate(inner.get("questions") or []):
                if not isinstance(q, dict):
                    problems.append("questions[%d] 不是对象" % i)
                    continue
                for sf in QUESTION_REQUIRED:
                    if sf not in q:
                        problems.append("questions[%d] 缺少子字段: %s" % (i, sf))
                for j, sq in enumerate(q.get("subquestions") or []):
                    if isinstance(sq, dict):
                        for sf in SUBQ_REQUIRED:
                            if sf not in sq:
                                problems.append("questions[%d].subquestions[%d] 缺少子字段: %s" % (i, j, sf))
            for i, a in enumerate(inner.get("answers") or []):
                if not isinstance(a, dict):
                    problems.append("answers[%d] 不是对象" % i)
                    continue
                for sf in ANSWER_REQUIRED:
                    if sf not in a:
                        problems.append("answers[%d] 缺少子字段: %s" % (i, sf))
                for j, s in enumerate(a.get("sentences") or []):
                    if isinstance(s, dict):
                        for sf in SENTENCE_REQUIRED:
                            if sf not in s:
                                problems.append("answers[%d].sentences[%d] 缺少子字段: %s" % (i, j, sf))
            for i, g in enumerate(inner.get("gaps") or []):
                if isinstance(g, dict):
                    for sf in GAP_REQUIRED:
                        if sf not in g:
                            problems.append("gaps[%d] 缺少子字段: %s" % (i, sf))
            ret = inner.get("retrieval") or {}
            if isinstance(ret, dict):
                for wk in ("queries", "miss_registered", "index_tool"):
                    if wk not in ret:
                        problems.append("retrieval 缺少键: %s" % wk)
    except Exception as e:
        problems.append("业务字段校验异常: %s" % e)

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
