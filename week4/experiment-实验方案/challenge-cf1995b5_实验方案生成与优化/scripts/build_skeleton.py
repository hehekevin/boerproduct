#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与方案要素清单（exp-plan-design）。

读取 case.json 提取 output_contract 全部字段名与研究目标/材料/约束（goal/
research_question/question/objective 等常见键），扫描输入目录补齐材料清单，
写入骨架 result.json（全部键，待回填）与 /app/work/rubric.json 方案比较口径
模板（权重须在任何排序之前声明）。同时校验本 Skill 脚本是否齐备并落
标志文件 skill_marker.json（脚本定位走标志文件校验，不靠路径假设）。
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

GOAL_KEYS = ("research_question", "goal", "question", "objective", "topic", "task_goal")
MATERIAL_KEYS = ("materials", "resources", "reagents", "equipment", "supplies")
CONSTRAINT_KEYS = ("constraints", "budget", "time_window", "restrictions")

EXPECTED_SCRIPTS = ("build_skeleton.py", "score_plan.py", "verify_check.py",
                    "schema_guard.py", "gain_probe.py")


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


def check_scripts(work_dir):
    """标志文件校验式定位：逐个核对脚本文件存在性，落 skill_marker.json。"""
    here = os.path.dirname(os.path.abspath(__file__))
    status = {}
    for s in EXPECTED_SCRIPTS:
        status[s] = os.path.exists(os.path.join(here, s))
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
    question = first_text(case, GOAL_KEYS)
    materials = first_list(case, MATERIAL_KEYS)
    constraints = first_text(case, CONSTRAINT_KEYS)
    if not question:
        problems.append("未找到研究目标键（%s），请人工核对后填 result.research_question"
                        % ",".join(GOAL_KEYS))
    if not materials:
        problems.append("未找到科研材料键（%s），材料清单记入 material_gaps 待人工核对"
                        % ",".join(MATERIAL_KEYS))
    all_files = scan_inputs(args.input_root)
    marker = check_scripts(args.work_dir)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [] if materials else ["科研材料清单未从 case.json 提取到，待人工核对"],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": question, "scope": None,
                                  "constraints": constraints},
            "rubric": {"weights": {"completeness": None, "feasibility": None,
                                   "risk_coverage": None, "cost_efficiency": None},
                       "tie_break": ["fused_score 降序", "feasibility 降序", "version_id 升序"],
                       "normalization": None, "declared_at": None},
            "hypotheses": [],
            "variables": {"independent": [], "dependent": [], "control": []},
            "controls": [],
            "groups": [],
            "power_basis": {"n_registry": []},
            "protocol": [],
            "measurements": [],
            "analysis_plan": [],
            "risks": [],
            "confirmations": [],
            "plan_versions": [],
            "plan_ranking": {"ordered_ids": [], "ties": [], "top_k": None, "k_value": None,
                             "note": "score_plan.py 回填"},
            "completeness": {"hypotheses_total": 0, "variables_defined": 0,
                             "controls_count": 0, "groups_total": 0,
                             "protocol_steps": 0, "analysis_entries": 0,
                             "aligned_hypotheses": 0, "ratio": None},
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待方案要素逐项填写后回填"},
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

    # 方案比较口径模板（事前声明：排序前必须填写权重，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rubric_path = os.path.join(args.work_dir, "rubric.json")
        if not os.path.exists(rubric_path):
            with open(rubric_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何方案排序之前必须声明四因子权重（合计=1.0）与归一化口径；"
                                   "声明后禁止调整，须与 result.rubric 一致。",
                           "declared_at": None,
                           "weights": {"completeness": None, "feasibility": None,
                                       "risk_coverage": None, "cost_efficiency": None},
                           "tie_break": ["fused_score 降序", "feasibility 降序", "version_id 升序"],
                           "normalization": None}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("rubric 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 输入文件 %d 个 | 材料条目 %d 个"
          % (case_id, len(fields), len(all_files), len(materials)))
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
