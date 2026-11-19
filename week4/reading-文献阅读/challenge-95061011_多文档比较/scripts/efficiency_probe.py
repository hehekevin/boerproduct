#!/usr/bin/env python3
"""efficiency_probe.py — 效率计数落盘器（r5）。

从已交付产物中机械复算可采集的效率计数，并原样保留 Agent 自报的运行计数，
写入 result.efficiency（含采集口径与复现方式说明）。

采集口径（复算值与 gain_probe.full 完全同公式，两处必须一致）：
  matrix_cells            逐格抽取的单元格数（= 需逐格核对条目基数）
  pairwise_records        两两比较记录数
  pairwise_judged         已判定（verdict≠not_judged）的槽位数
  document_count          语料文档数
  dimension_count         比较维度数
  document_pairs          文档对数
  comparison_rounds       比对轮次 = 文档对数 × 维度数
  conflict_records        冲突登记条数
  attributable_conflicts  可归因冲突条数
  manual_review_items     需人工核对条目数（未判定槽位 + 不可归因冲突 + human_review）
  pipeline_steps          自动执行阶段数
  manual_completion_steps 完成同等交付所需的人工补做阶段数
  steps                   pipeline_steps + manual_completion_steps
  followup_rounds         追问轮次 = 需回访源文档数 + 待追问缺口种类数
  verification_items      自检条目数
  gates_total             闸门条目数
  fields_in_dictionary    字段字典条目数

model_requests / tool_calls / rework_rounds 为 Agent 运行期自报，原样保留于
agent_reported 分区，与复算值分开存放，不混用。

失败一律 exit 0；问题写入 problems 字段，verdict 照实记录。
用法：
    python3 efficiency_probe.py --result R.json [--workorder WO.json] [--out E.json] [--embed]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_matrix as cm_mod  # noqa: E402
import gain_probe as gp  # noqa: E402
from cli_guard import SafeParser, run_entry, safe_parse_args  # noqa: E402


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def count(res, wo):
    problems = []
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    matrix = inner.get("matrix") or []
    pairwise = inner.get("pairwise") or []
    syn = inner.get("synthesis") if isinstance(inner.get("synthesis"), dict) else {}
    conflicts = syn.get("conflicts") or []

    views, vproblems = gp.build_views(res, wo)
    problems.extend(vproblems)
    docs = []
    dims = []
    try:
        art = cm_mod.run_comparison(res, wo, None)
        docs = art.get("source_document_ids") or []
        dims = art.get("comparison_dimensions") or []
    except Exception:
        pass
    if not docs:
        docs = sorted(set(str(c.get("source_document_id")) for c in matrix
                           if isinstance(c, dict) and c.get("source_document_id")))
    if not dims:
        dims = list(cm_mod.DIM_KEYWORDS.keys())
    total_slots = len(list(combinations(docs, 2))) * len(dims) if len(docs) >= 2 else 0

    # 复用 gain_probe 的同一套公式，保证 followup_rounds / manual_review_items 两处一致
    full_m = gp.compute_metrics(views["full"], res, docs, dims, total_slots)

    reported = inner.get("efficiency")
    agent_reported = {}
    if isinstance(reported, dict):
        # Agent 运行期自报值可能写在 efficiency.agent_reported（探针写回后）
        # 或 efficiency 顶层（Agent 首次写入、探针尚未跑），两处都读
        src = reported.get("agent_reported")
        src = src if isinstance(src, dict) else {}
        for k in ("model_requests", "tool_calls", "rework_rounds",
                  "request_budget", "time_budget_seconds"):
            if k in src:
                agent_reported[k] = src.get(k)
            elif k in reported:
                agent_reported[k] = reported.get(k)

    pipeline_steps = len(full_m.get("stages_executed") or [])
    manual_steps = max(full_m.get("steps", 0) - pipeline_steps, 0)
    hr_items = len((res.get("uncertainties") or {}).get("human_review") or []) \
        if isinstance(res.get("uncertainties"), dict) else 0

    counts = {
        "matrix_cells": len(matrix),
        "pairwise_records": len(pairwise),
        "pairwise_judged": full_m.get("judged_slots"),
        "pairwise_not_judged": full_m.get("not_judged_slots"),
        "document_count": len(docs),
        "dimension_count": len(dims),
        "document_pairs": len(list(combinations(docs, 2))),
        "comparison_rounds": len(list(combinations(docs, 2))) * len(dims),
        "conflict_records": len(conflicts),
        "attributable_conflicts": full_m.get("attributable_conflicts"),
        "manual_review_items": full_m.get("manual_review_items"),
        "human_review_items": hr_items,
        "pipeline_steps": pipeline_steps,
        "manual_completion_steps": manual_steps,
        "steps": full_m.get("steps"),
        "followup_rounds": full_m.get("followup_rounds"),
        "verification_items": len(inner.get("verification") or []),
        "gates_total": len(inner.get("gates") or []),
        "fields_in_dictionary": len(inner.get("field_dictionary") or []),
    }

    eff = {
        "collection_method": (
            "复算口径：matrix_cells/pairwise_*/comparison_rounds/conflict_*/"
            "manual_review_items/pipeline_steps/manual_completion_steps/steps/followup_rounds "
            "由已交付 result.json 的数组长度、组合数与缺口结构机械得出（与 gain_probe.full 同公式）；"
            "model_requests/tool_calls/rework_rounds 为 Agent 运行期自报，原样保留于 "
            "agent_reported，与复算值分区存放、不混用。"
        ),
        "reproduce": (
            "python3 /skills/weekly-skill/scripts/efficiency_probe.py --result "
            "/app/output/result.json --workorder /input/comparison-workorder.json --embed"
        ),
        "counts": counts,
        "agent_reported": agent_reported,
        "notes": [
            "comparison_rounds = 文档对数 × 比较维度数（每槽位一次两两比对），"
            "未计入 Agent 语义推理的内部往返。",
            "followup_rounds = 需回访源文档数 + 待追问缺口种类数，"
            "与 gain_evidence.runs[mode=full].metrics.followup_rounds 同公式，两处数值必须一致。",
            "steps = pipeline_steps（自动执行阶段）+ manual_completion_steps"
            "（未覆盖维度数 + 不可归因冲突数，人工接手才能补齐的阶段）。",
            "平台另行记录真实模型请求数与耗时；本字段为 Skill 自测口径，不替代平台遥测。",
        ],
        "problems": problems,
    }
    return eff


def main():
    ap = SafeParser(description="效率计数器（退出码恒 0，判定看 efficiency.ok）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--embed", action="store_true")
    args = safe_parse_args(ap)
    if args is None:
        print("[efficiency_probe] FAIL: 命令行参数有误，判定按失败处理")
        return 0

    problems = []
    res = load_json(args.result)
    if res is None:
        problems.append("result.json 不存在或不是合法 JSON")
        _write({"ok": False, "problems": problems}, args.out, args.result, None, args.embed)
        print("[efficiency_probe] FAIL: result.json 不存在或不是合法 JSON")
        return 0

    wo = cm_mod.read_workorder(args.workorder)
    eff = count(res, wo)
    problems.extend(eff.get("problems") or [])
    eff["ok"] = not problems
    _write(eff, args.out, args.result, res, args.embed)

    c = eff["counts"]
    print("[efficiency_probe] ok=%s cells=%d pairwise=%d(judged=%d) rounds=%d conflicts=%d "
          "manual=%d steps=%d(%d auto+%d manual) followup=%d" % (
              eff["ok"], c["matrix_cells"], c["pairwise_records"], c["pairwise_judged"],
              c["comparison_rounds"], c["conflict_records"], c["manual_review_items"],
              c["steps"], c["pipeline_steps"], c["manual_completion_steps"],
              c["followup_rounds"]))
    for p in problems:
        print("  ! %s" % p)
    return 0


def _write(eff, out_path, result_path, res, embed):
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(eff, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
    if embed and res is not None and result_path:
        try:
            target = res.get("result") if isinstance(res.get("result"), dict) else None
            if target is None:
                res["result"] = target = {}
            target["efficiency"] = eff
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception:
            pass


if __name__ == "__main__":
    run_entry(main, "efficiency_probe")
