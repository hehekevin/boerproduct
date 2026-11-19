#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与材料清单（lit-search-pro）。

读取 case.json 提取 output_contract 全部字段名，扫描输入目录建立检索材料清单，
写入骨架 result.json（全部键，待回填）与 /app/work/query_plan.json 工作模板。
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


def scan_inputs(root):
    """递归扫描输入目录，返回 (全部文件, 检索响应材料文件)。"""
    all_files, resp_files = [], []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                low = fn.lower()
                if any(k in low for k in ("crossref", "europepmc", "pubmed", "openalex",
                                          "arxiv", "response", "material", "search")):
                    resp_files.append(rel)
    except Exception:
        pass
    return all_files, resp_files


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except SystemExit:  # argparse error 也退出码 0（题面硬约束）
        return 0
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
    all_files, resp_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": case.get("research_question") or case.get("question") or None,
            "scope": case.get("scope") if isinstance(case.get("scope"), dict) else {},
            "query_plan": [],
            "keyword_expansion": [],
            "queries_executed": [{"query_id": "q%d" % (i + 1), "round": None,
                                  "query": None, "database": None, "result_count": None,
                                  "status": "skipped", "notes": "Step 1-2 回填"}
                                 for i in range(min(len(resp_files), 8))] if resp_files else [],
            "databases_used": [],
            "papers": [],
            "dedup": {"criteria": None, "clusters_found": None,
                      "removed_duplicates": None, "dedup_rate": None, "note": "Step 3 回填"},
            "coverage": {"total_raw": None, "total_unique": None, "traceable_items": None,
                         "traceability_ratio": None, "per_db_counts": {},
                         "note": "Step 3 回填"},
            "gaps": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待 Step 1-2 回填"},
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

    # 查询计划工作模板
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        qp_path = os.path.join(args.work_dir, "query_plan.json")
        if not os.path.exists(qp_path):
            with open(qp_path, "w", encoding="utf-8") as f:
                json.dump({"note": "Step 1 由 plan_queries.py 回填；round1 核心/round2 扩展/"
                                   "round3 相关上位/round4 补漏",
                           "case_id": case_id,
                           "plan": []}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("查询计划模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 检索材料 %d 个"
          % (case_id, len(fields), len(all_files), len(resp_files)))
    for p in resp_files:
        print("  material: %s" % p)
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
