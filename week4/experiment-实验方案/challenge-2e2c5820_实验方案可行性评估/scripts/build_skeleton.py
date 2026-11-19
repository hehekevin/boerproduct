#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与方案/资源清单（feas-review）。

读取 case.json 提取 output_contract 全部字段名与候选实验方案（plans/proposals/
schemes/candidate_plans 等常见键），扫描输入目录补齐材料清单，写入骨架
result.json（全部键，待回填）：按方案 × 七类约束（假设与变量/对照组/设备材料/
时间成本/参数范围/风险与异常/伦理与安全）预填检查项槽位，并生成
/app/work/grading_rubric.json 分级口径模板（须在任何分级判定之前声明）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 problems 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PLAN_KEYS = ("plans", "proposals", "schemes", "candidate_plans",
             "experiment_plans", "plan_versions", "plan")

# 七类约束（题面评分维度逐项对应）：假设与变量/对照组/设备材料/时间成本/
# 参数范围/风险与异常/伦理与安全
DIMENSIONS = [
    {"dimension_id": "D1", "name": "assumptions_variables", "label": "假设与变量"},
    {"dimension_id": "D2", "name": "controls", "label": "对照组"},
    {"dimension_id": "D3", "name": "equipment_materials", "label": "设备材料"},
    {"dimension_id": "D4", "name": "time_cost", "label": "时间成本"},
    {"dimension_id": "D5", "name": "parameter_ranges", "label": "参数范围"},
    {"dimension_id": "D6", "name": "risks_exceptions", "label": "风险与异常"},
    {"dimension_id": "D7", "name": "ethics_safety", "label": "伦理与安全"},
]
STATUSES = ("feasible", "conditional", "infeasible", "unverifiable")


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


def _plan_id(entry, idx):
    for k in ("plan_id", "id", "plan", "version", "name"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "PL-%s" % chr(ord("A") + idx)


def extract_plans(case):
    """从 case.json 常见键提取候选实验方案清单（plan_id + 标题线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，方案清单未提取"
    for key in PLAN_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                if isinstance(e, dict):
                    for tk in ("title", "name", "plan_title", "objective"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"plan_id": _plan_id(e, i), "title": title,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含实验方案键（%s），请人工核对后填入 result.plans" % ",".join(PLAN_KEYS)


def scan_inputs(root):
    """递归扫描输入目录，返回全部文件相对路径清单。"""
    all_files = []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                all_files.append(os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/"))
    except Exception:
        pass
    return all_files


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except Exception as e:
        print("[build_skeleton] 参数解析失败: %s" % e)
        return 0

    problems = []
    case = {}
    case_id = "unknown"

    # 一级：读 case.json
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = str(case.get("case_id") or "unknown")
        else:
            problems.append("case.json 不存在: %s（case_id 填 unknown）" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败（降级继续）: %s" % e)

    fields = contract_fields(case)
    plans, plan_note = extract_plans(case)
    if plan_note:
        problems.append(plan_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        checks = []
        for p in plans:
            for d in DIMENSIONS:
                checks.append({
                    "check_id": "%s-%s" % (p["plan_id"], d["dimension_id"]),
                    "plan_id": p["plan_id"],
                    "dimension": d["dimension_id"],
                    "item_text": None, "status": "unverifiable",
                    "conditions": [], "basis_type": None,
                    "evidence_quote": None, "evidence_location": None,
                    "rationale": None, "confidence": None,
                    "pending_reason": "待判定（骨架槽位）", "judged": False})
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "review_scope": {"objective": None, "constraints": [], "plan_ids": [p["plan_id"] for p in plans]},
            "grading_rubric": {
                "levels": {"feasible": None, "conditional": None,
                           "infeasible": None, "unverifiable": None},
                "evidence_rule": "任何 feasible/conditional/infeasible 判定必须附方案或条件清单的逐字证据；"
                                 "方案未写、条件不明一律判 unverifiable 并登记待复核，不得默认满足。",
                "declared_at": None},
            "dimensions": [dict(d) for d in DIMENSIONS],
            "plans": [{"plan_id": p["plan_id"], "title": p["title"],
                       "source_ref": p["source_ref"]} for p in plans],
            "check_items": checks,
            "time_estimate": {"rows": [], "totals": {},
                              "note": "estimate_time.py 回填（rows 由 Agent 在 Step 2 按步骤拆解填写）"},
            "coverage": {"total_checks": len(checks), "judged": 0,
                         "per_dimension": {d["dimension_id"]: 0 for d in DIMENSIONS},
                         "per_status": {s: 0 for s in STATUSES},
                         "missing_dimensions": [], "ratio": None},
            "risks": [],
            "confirmations": [],
            "pending_review": [],
            "conflicts": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐项判定后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}]}
        for f in fields:
            if f not in skeleton:
                skeleton[f] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"},
                    "changelog": []}

    # 三级：写盘（输出目录不存在则创建；仍失败则写到备用路径）
    out_path = args.out
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    except Exception:
        pass
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("骨架写出失败 %s: %s" % (out_path, e))
        try:
            fallback = os.path.join(args.work_dir or ".", "result.skeleton.json")
            os.makedirs(os.path.dirname(fallback) or ".", exist_ok=True)
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
            problems.append("骨架已写到备用路径: %s" % fallback)
        except Exception as e2:
            problems.append("备用写盘也失败: %s" % e2)

    # 分级口径模板（事前声明：任何分级判定之前必须写定，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rubric_path = os.path.join(args.work_dir, "grading_rubric.json")
        if not os.path.exists(rubric_path):
            with open(rubric_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何分级判定之前必须声明四级口径（feasible/conditional/"
                                   "infeasible/unverifiable 的判定边界）与证据规则；"
                                   "声明后禁止调整，须与 result.grading_rubric 一致。",
                           "declared_at": None,
                           "levels": {"feasible": None, "conditional": None,
                                      "infeasible": None, "unverifiable": None},
                           "evidence_rule": None}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("grading_rubric 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 候选方案 %d 个 | 检查项槽位 %d 个"
          % (case_id, len(fields), len(all_files), len(plans), len(checks)))
    for p in plans:
        print("  plan: %s  %s" % (p["plan_id"], p["title"][:60]))
    for p in problems:
        print("  WARN: %s" % p)
    print("[build_skeleton] 骨架已写: %s" % out_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（已降级，请手工落骨架）: %s" % e)
        sys.exit(0)
