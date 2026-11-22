#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架（exp-param-domain，关键参数可行域约束）。

读取 case.json 提取 case_id + output_contract 全部字段名 + 研究目标/约束/材料，
写入最小骨架 result.json（关键参数识别与可行域约束单方向），并落标志文件
skill_marker.json（脚本定位走标志文件校验，不靠路径假设）。三级容错：任何一级
失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

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
import platform

GOAL_KEYS = ("research_question", "goal", "question", "objective", "topic", "task_goal")
MATERIAL_KEYS = ("materials", "resources", "reagents", "equipment", "supplies")
CONSTRAINT_KEYS = ("constraints", "budget", "time_window", "restrictions",
                   "prospective_contracts", "prospective_resource")
EXPECTED_SCRIPTS = ("build_skeleton.py", "param_check.py", "verify_check.py")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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


def first_text(obj, keys):
    for k in keys:
        v = (obj or {}).get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for vk in ("question", "goal", "text", "description"):
                s = v.get(vk)
                if isinstance(s, str) and s.strip():
                    return s.strip()
    return None


def first_list(obj, keys):
    for k in keys:
        v = (obj or {}).get(k)
        if isinstance(v, list) and v:
            return v
    return []


def check_scripts(work_dir):
    here = os.path.dirname(os.path.abspath(__file__))
    status = {s: os.path.exists(os.path.join(here, s)) for s in EXPECTED_SCRIPTS}
    marker = {"skill_root": here, "scripts": status,
              "all_present": all(status.values()),
              "note": "脚本定位以本标志文件为准，路径假设不作为依据"}
    try:
        os.makedirs(work_dir or ".", exist_ok=True)
        with open(os.path.join(work_dir, "skill_marker.json"), "w", encoding="utf-8") as f:
            json.dump(marker, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return marker


def build_inner(question, constraints, materials):
    return {
        "material_gaps": [] if materials else ["科研材料清单未从 case.json 提取到，待人工核对"],
        "environment": {"python_version": platform.python_version(),
                        "packages": "stdlib-only", "hardware_note": "照实"},
        "research_question": {"question": question, "scope": None,
                              "constraints": constraints},
        "parameters": [],          # 关键参数 3-6 个（name/current/range/unit/basis/step）
        "constraints": [],         # 耦合约束（若有）；确无耦合登记 none_declared
        "feasibility_check": {"tool": "scripts/param_check.py", "note": "param_check.py 回填"},
        "risks": [],               # 极简单兜底一条
        "confirmations": [],
        "completeness": {"parameters_total": 0, "constraints_total": 0},
        "steps": [],
        "run_status": {"state": None, "reason": None, "manual_takeover": []},
        "verdict": None,           # feasible | partially_feasible | infeasible | cannot_verify
        "verdict_basis": None,
        "gain_evidence": {"available": False,
                          "reason": "本题精简策略：不做正常/退化双重增益对照（预算保护降级）"},
    }


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except Exception as e:
        print("[build_skeleton] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    case = {}
    case_id = "unknown"

    try:
        if os.path.exists(args.case):
            case = load_json(args.case) or {}
            case_id = str(case.get("case_id") or "unknown")
        else:
            problems.append("case.json 不存在: %s（case_id 填 unknown）" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败（降级继续）: %s" % e)

    fields = contract_fields(case)
    question = first_text(case, GOAL_KEYS)
    materials = first_list(case, MATERIAL_KEYS)
    constraints = first_text(case, CONSTRAINT_KEYS)
    if not question:
        problems.append("未找到研究目标键（%s），请人工核对后填 result.research_question"
                        % ",".join(GOAL_KEYS))
    if not materials:
        problems.append("未找到科研材料键（%s），材料清单记入 material_gaps 待人工核对"
                        % ",".join(MATERIAL_KEYS))
    marker = check_scripts(args.work_dir)

    try:
        skeleton = {
            "case_id": case_id,
            "status": "partial",
            "result": build_inner(question, constraints, materials),
            "claims": [],
            "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                              "human_review": [],
                              "summary": "骨架已落盘，待关键参数可域项逐条填写"},
            "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}],
        }
        for f in fields:
            if f not in skeleton:
                skeleton[f] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"},
                    "changelog": []}

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

    print("[build_skeleton] case_id=%s | contract字段 %d 个 | 材料条目 %d 个"
          % (case_id, len(fields), len(materials)))
    if question:
        print("  研究目标: %s" % question[:80])
    print("  脚本标志文件: all_present=%s（%d/%d）"
          % (marker.get("all_present"), sum(1 for v in marker["scripts"].values() if v),
             len(marker["scripts"])))
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