#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与材料清单（cite-trace）。

读取 case.json 提取 output_contract 全部字段名与种子文献信息，扫描输入目录
建立文献材料清单，写入骨架 result.json（全部键，待回填）与
declared_rules.json 追踪/关联规则声明模板。
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


def find_seed(case):
    """在 case.json 中定位种子文献信息（兼容多种键名；找不到返回 None）。

    注意：仅按键名定位，不按标签猜测内容；标题/DOI 等字段一律以实际
    文件内容为准。标题归一化不用 isalpha 类启发式（汉字 isalpha()==True
    会误判中文标题），这里只做原样提取。
    """
    if not isinstance(case, dict):
        return None
    for key in ("seed", "seed_paper", "paper", "work", "article"):
        v = case.get(key)
        if isinstance(v, dict) and (v.get("title") or v.get("doi") or v.get("seed_id")):
            return {
                "seed_id": str(v.get("seed_id") or v.get("id") or "S0"),
                "title": v.get("title"),
                "year": v.get("year"),
                "doi": v.get("doi"),
                "venue": v.get("venue"),
                "identity_keys": [],
                "variants": [],
                "source_ref": "case.json:%s" % key,
                "note": "由 build_skeleton 预提取，Step 1 复核并补 identity_keys",
            }
    return None


def scan_inputs(root):
    """递归扫描输入目录，返回 (全部文件, 引文类材料文件)。"""
    all_files, lit_files = [], []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                ext = os.path.splitext(fn)[1].lower()
                if ext in (".json", ".csv", ".bib", ".ris", ".enw", ".tsv") or \
                        any(k in fn.lower() for k in ("reference", "citation", "biblio")):
                    lit_files.append(rel)
    except Exception:
        pass
    return all_files, lit_files


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
    all_files, lit_files = scan_inputs(args.input_root)
    seed = find_seed(case)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "seed": seed or {"seed_id": None, "title": None, "year": None,
                             "doi": None, "venue": None, "identity_keys": [],
                             "variants": [], "source_ref": None,
                             "note": "Step 1 从 case.json/材料中定位种子并回填"},
            "nodes": ([{"node_id": seed["seed_id"], "title": seed.get("title"),
                        "year": seed.get("year"), "doi": seed.get("doi"),
                        "roles": ["seed"], "source_ref": seed.get("source_ref")}
                       ] if seed else []),
            "traces": {"backward": [], "forward": []},
            "related": [],
            "clusters": [],
            "network": {"foundational": [], "bridge": [], "recent_hot": [],
                        "cycles": [], "orphans": []},
            "paths": [],
            "merges": [],
            "declared_rules": [],
            "tracking_coverage": {"backward_layers_max": 0, "forward_layers_max": 0,
                                  "backward_edges": 0, "forward_edges": 0,
                                  "related_items": 0, "clusters": 0, "paths": 0,
                                  "merges": 0, "cycles_registered": 0,
                                  "orphans_registered": 0,
                                  "seed_forward_available": None,
                                  "coverage_note": "Step 2/3/4 回填：各项计数须与对应列表长度一致"},
            "pending_review": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
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

    # 追踪/关联规则声明模板（事前声明，验算前必须填写）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rules_path = os.path.join(args.work_dir, "declared_rules.json")
        if not os.path.exists(rules_path):
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump({"note": "Step 1 追踪开始前必须填写；声明后禁止事后调整。"
                                   "每行 {rule, threshold, basis, declared_at}，"
                                   "related[].confidence 判定须与声明一致",
                           "declared_by": "skill（题面未给出阈值时按保守原则自定并写明理由）",
                           "declared_at": None,
                           "rules": []}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("规则模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 引文材料 %d 个"
          % (case_id, len(fields), len(all_files), len(lit_files)))
    if seed:
        print("  seed: %s（title=%r, source=%s）" % (seed["seed_id"], seed.get("title"),
                                                     seed.get("source_ref")))
    else:
        print("  WARN: 未在 case.json 中定位到种子文献，Step 1 手工定位回填")
    for p in lit_files:
        print("  lit-material: %s" % p)
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
