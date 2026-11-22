#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与材料清单（repro-verify）。

读取 case.json 提取 output_contract 全部字段名，扫描输入目录建立材料清单，
写入骨架 result.json（全部键，待回填）与 declared_tolerances.json 容差模板。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

用法：
    python build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 problems 报告，骨架仍写出）。
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


def scan_inputs(root):
    """递归扫描输入目录，返回 (全部文件, 候选方法文件)。"""
    all_files, code_files = [], []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                ext = os.path.splitext(fn)[1].lower()
                if ext in (".py", ".sh", ".ipynb", ".r", ".m", ".jl") or "candidate" in fn.lower():
                    code_files.append(rel)
    except Exception:
        pass
    return all_files, code_files


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
    all_files, code_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "parameters": [],
            "candidates": [{"candidate_id": os.path.splitext(os.path.basename(p))[0],
                            "entry": p, "ran": False, "run_log": None,
                            "failure_stage": None, "pending": True}
                           for p in code_files],
            "metric_checks": [],
            "attributions": [],
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待 Step 1-4 回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}]}
        # output_contract 声明的顶层字段若不在骨架中，补齐（值 unknown）
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

    # 容差声明模板
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        tol_path = os.path.join(args.work_dir, "declared_tolerances.json")
        if not os.path.exists(tol_path):
            with open(tol_path, "w", encoding="utf-8") as f:
                json.dump({"note": "Step 1 验算前必须填写；声明后禁止事后调容差",
                           "declared_by": "skill（论文未给出时按指标量级保守设定）",
                           "tolerances": []}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("容差模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 候选方法 %d 个"
          % (case_id, len(fields), len(all_files), len(code_files)))
    for p in code_files:
        print("  candidate: %s" % p)
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
