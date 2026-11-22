#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架（exp-result-anomaly）。

读取 /input/case.json：提取 case_id、output_contract 全部字段、数据集/读数序列
清单（datasets/series/traces/records/data/tables/results/readings/curves 等键），
扫描输入目录补齐材料清单，写入 /app/output/result.json 骨架（全部键待回填）与
/app/work/skill_marker.json 脚本标志文件。

三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。
退出码恒为 0。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
"""
from __future__ import annotations

import argparse
import json
import os
import sys

DATA_KEYS = ("datasets", "series", "traces", "records", "data", "tables",
             "results", "experiments", "materials", "readings", "curves")

DEFAULT_THRESHOLDS = {"outlier_z": 3.0, "jump_rel": 0.5,
                      "plateau_min_points": 3, "plateau_tol_rel": 0.05}


def contract_fields(case):
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


def extract_dataset_ids(case):
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，序列清单未提取"
    for key in DATA_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                if isinstance(e, dict):
                    did = str(e.get("dataset_id") or e.get("id") or e.get("name") or "%s[%d]" % (key, i))
                    title = str(e.get("title") or e.get("name") or e.get("description") or "")[:120]
                    out.append({"dataset_id": did, "source_ref": "%s[%d]" % (key, i), "title": title})
                elif isinstance(e, (int, float)):
                    out.append({"dataset_id": "%s[%d]" % (key, i), "source_ref": "%s[%d]" % (key, i),
                                "title": "标量读数"})
    if not out and isinstance(case, dict):
        for key in DATA_KEYS:
            v = case.get(key)
            if isinstance(v, list) and v:
                out.append({"dataset_id": key, "source_ref": key, "title": ""})
    return out, note


def scan_inputs(root):
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

    problems, case, case_id = [], {}, "unknown"
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        problems.append("定位标志未命中（脚本未与 SKILL.md 同包），仍继续")

    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_id = str(case.get("case_id") or "unknown")
        else:
            problems.append("case.json 不存在: %s" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败（降级继续）: %s" % e)

    fields = contract_fields(case)
    ds_ids, ds_note = extract_dataset_ids(case)
    if ds_note:
        problems.append(ds_note)
    all_files = scan_inputs(args.input_root)

    skeleton = {
        "case_id": case_id,
        "status": "partial",
        "result": {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": "stdlib-only",
                            "seed": None, "hardware_note": "照实"},
            "contract_fields": fields,
            "dataset_ids": [d["dataset_id"] for d in ds_ids],
            "thresholds": dict(DEFAULT_THRESHOLDS),
            "anomalies": [],
            "detection": {"note": "anomaly_detect.py 回填"},
            "fallbacks": {"trend": None, "cause_list": None, "recheck": None, "followup": None},
            "gain_evidence": {"available": False, "reason": "预算过50%降级"},
            "input_files": all_files,
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        },
        "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                          "human_review": [], "summary": "骨架已落盘，待离群检测后回填"},
        "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}],
    }
    # output_contract 其余字段也纳入顶层，避免缺字段
    for f in fields:
        if f not in skeleton:
            skeleton[f] = None

    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("骨架写出失败 %s: %s" % (args.out, e))

    # 脚本标志文件
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        with open(os.path.join(args.work_dir, "skill_marker.json"), "w", encoding="utf-8") as f:
            json.dump({"skill": "exp-result-anomaly", "built_by": "build_skeleton.py",
                       "marker_hit": marker_hit}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("skill_marker 写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | marker_hit=%s | contract 字段 %d | 序列 %d | 文件 %d"
          % (case_id, marker_hit, len(fields), len(ds_ids), len(all_files)))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[build_skeleton] 骨架已写: %s" % args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（已降级，请手工落骨架）: %s" % e)
        sys.exit(0)