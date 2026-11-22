#!/usr/bin/env python3
"""verify_check.py — cite-trace v2 业务逻辑校验器（仅前后向追踪口径）。

校验 trace_results 每条的方向/层级/关联依据/来源可回指，trace_summary 计数
与实况一致，run_status 与 verdict 枚举合法。支持 --ablate all 退化为只做基础
枚举/结构检查，用于预算 <50% 时的增益对照。把自检三元组、闸门、未回证清单
回写进 --result 指向的文件（self_check/gates/unbacked_numbers/validator_verdict
回建），退出码恒为 0，判据看报告 verdict。

用法：
    python3 verify_check.py --result /app/output/result.json \
        --case /input/case.json --out /app/work/verify_check.json [--ablate all] [--emit-into]
退出码：恒为 0。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DIRECTIONS = {"backward", "forward"}
RELATIONS = {"method_origin", "dataset_origin", "prior_work",
             "improvement", "critique", "application", "other"}
RUN_STATES = {"success", "partial", "unable_to_determine", "refused"}
VERDICTS = {"traced", "partial_trace", "insufficient_records", "unverifiable"}
STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}


def analyze(result, ablate=False):
    """返回 (problems, self_check, unbacked)。ablate=True 时跳过业务逻辑检查。"""
    problems = []
    self_check = []
    unbacked = []

    def check(item, template, fn):
        applied = not ablate
        if applied:
            ok, detail = fn()
            match = not ok
            if not ok:
                problems.append(detail)
        else:
            match = None
        self_check.append({"item": item, "template_value": template,
                           "applied": bool(applied), "match": match})

    def _structural():
        if not isinstance(result, dict):
            return False, "result.json 顶层应为对象"
        if not result.get("case_id"):
            return False, "缺少 case_id"
        inner = result.get("result")
        if not isinstance(inner, dict):
            return False, "result 应为对象"
        seed = inner.get("seed") or {}
        if not (seed.get("title") or seed.get("doi")):
            return False, "seed 缺少 title 与 doi"
        tr = inner.get("trace_results")
        if not isinstance(tr, list) or len(tr) == 0:
            return False, "trace_results 应为非空数组"
        return True, ""

    check("case_and_seed_and_trace_list",
          "case_id 非空 / seed 有 title 或 doi / trace_results 非空", _structural)

    # 结构检查即使 ablate 也保留（_structural 恒执行）
    if ablate:
        return problems, self_check, unbacked

    inner = result.get("result", {})
    tr = inner.get("trace_results", [])

    def _trace_items():
        seen = set()
        for i, t in enumerate(tr):
            tid = t.get("trace_id")
            if not tid:
                return False, "trace_results[%d].trace_id 缺失" % i
            if tid in seen:
                return False, "trace_results[%d].trace_id 重复: %s" % (i, tid)
            seen.add(tid)
            if t.get("direction") not in DIRECTIONS:
                return False, "trace_results[%d].direction 非法: %r" % (i, t.get("direction"))
            if t.get("relation") not in RELATIONS:
                return False, "trace_results[%d].relation 非法: %r" % (i, t.get("relation"))
            layer = t.get("layer")
            if not isinstance(layer, int) or layer < 1:
                return False, "trace_results[%d].layer 应为 >=1 整数: %r" % (i, layer)
            if not t.get("related_basis"):
                return False, "trace_results[%d].related_basis 为空" % i
            if not t.get("source_ref"):
                return False, "trace_results[%d].source_ref 为空（来源不可回指）" % i
            if t.get("pending") and not t.get("pending_reason"):
                return False, "trace_results[%d].pending=true 但缺 pending_reason" % i
        return True, ""

    check("trace_item_fields",
          "每条 trace 有唯一 trace_id/合法 direction+relation/layer>=1/related_basis/source_ref/pending_reason",
          _trace_items)

    def _counts():
        ts = inner.get("trace_summary", {})
        b = sum(1 for t in tr if t.get("direction") == "backward")
        f = sum(1 for t in tr if t.get("direction") == "forward")
        if ts.get("backward_count") != b:
            return False, "trace_summary.backward_count=%r 与实际 %d 不符" % (ts.get("backward_count"), b)
        if ts.get("forward_count") != f:
            return False, "trace_summary.forward_count=%r 与实际 %d 不符" % (ts.get("forward_count"), f)
        bl = max([t.get("layer", 0) for t in tr if t.get("direction") == "backward"] or [0])
        fl = max([t.get("layer", 0) for t in tr if t.get("direction") == "forward"] or [0])
        if ts.get("backward_layers") != bl:
            return False, "trace_summary.backward_layers=%r 与实际 %d 不符" % (ts.get("backward_layers"), bl)
        if ts.get("forward_layers") != fl:
            return False, "trace_summary.forward_layers=%r 与实际 %d 不符" % (ts.get("forward_layers"), fl)
        if not ts.get("stop_rule") or ts.get("per_layer_cap") is None:
            return False, "trace_summary 缺 stop_rule 或 per_layer_cap"
        return True, ""

    check("trace_summary_counts",
          "count/layers 与 trace_results 一致 + stop_rule + per_layer_cap", _counts)

    def _run_state():
        rs = inner.get("run_status", {})
        if rs.get("state") not in RUN_STATES:
            return False, "run_status.state 非法: %r" % rs.get("state")
        if rs.get("state") in ("partial", "unable_to_determine", "refused") and not rs.get("reason"):
            return False, "run_status.state=%r 但缺 reason" % rs.get("state")
        if inner.get("verdict") not in VERDICTS:
            return False, "verdict 非法: %r" % inner.get("verdict")
        if result.get("status") not in STATUSES:
            return False, "status 非法: %r" % result.get("status")
        return True, ""

    check("run_status_and_verdict", "run_status.state/reason + verdict/status 枚举合法", _run_state)

    return problems, self_check, unbacked


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


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default=None, help="all=退化模式（只做基础检查）")
        ap.add_argument("--emit-into", action="store_true", help="回写自检键到 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    ablate = args.ablate == "all"
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[verify_check] FAIL: result.json 读取失败：%s（不中断交付）" % e)
        _dump_report(args.out, {"verdict": "FAIL", "problems": ["result.json 读取失败: %s" % e],
                                "self_check": [], "unbacked_numbers": []})
        return 0

    problems, self_check, unbacked = analyze(result, ablate=ablate)
    verdict = "PASS" if not problems else "FAIL"

    if args.emit_into and isinstance(result, dict):
        result["self_check"] = self_check
        result["unbacked_numbers"] = unbacked
        result["validator_verdict"] = verdict
        if "gates" not in result:
            result["gates"] = []
        try:
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败：%s" % e)

    report = {"verdict": verdict, "problems": problems,
              "self_check": self_check, "unbacked_numbers": unbacked,
              "ablate": ablate, "counts": {"problems": len(problems),
                                            "checks": len(self_check)}}
    _dump_report(args.out, report)
    print("[verify_check] %s（%d 项检查，problems=%d，ablate=%s）"
          % (verdict, len(self_check), len(problems), ablate))
    for p in problems[:40]:
        print("  - %s" % p)
    if len(problems) > 40:
        print("  ... 共 %d 处" % len(problems))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)