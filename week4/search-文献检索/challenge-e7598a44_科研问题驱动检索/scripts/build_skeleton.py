#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与材料清单（quest-search / challenge-e7598a44）。

读取 case.json 提取 output_contract 全部字段名，扫描输入目录建立科研材料清单，
写入骨架 result.json（全部业务键，待回填）与 /app/work/stop_criteria.json
停止条件事前声明模板。
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

CORPUS_EXT = (".pdf", ".txt", ".md", ".json", ".csv", ".bib", ".ris", ".enw", ".xml")
CORPUS_KEYS = ("records", "papers", "documents", "corpus", "literature", "search09", "records_list")


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
    """递归扫描输入目录，返回 (全部文件, 科研材料文件)。"""
    all_files, corpus_files = [], []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/")
                all_files.append(rel)
                if os.path.splitext(fn)[1].lower() in CORPUS_EXT and fn != "case.json":
                    corpus_files.append(rel)
    except Exception:
        pass
    return all_files, corpus_files


def scan_case_records(case):
    """扫描 case.json 中内嵌的文献记录清单（兼容常见键名），返回清单摘要。"""
    found = []
    try:
        if isinstance(case, dict):
            for k, v in case.items():
                if isinstance(v, list) and (any(kl in k.lower() for kl in CORPUS_KEYS)
                                            or k.lower() in ("records", "papers", "corpus")):
                    found.append({"key": k, "count": len(v)})
                elif isinstance(v, dict):
                    for k2, v2 in v.items():
                        if isinstance(v2, list) and any(kl in (k + k2).lower()
                                                       for kl in CORPUS_KEYS):
                            found.append({"key": "%s.%s" % (k, k2), "count": len(v2)})
    except Exception:
        pass
    return found


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
            case_id = str(case.get("case_id") or case.get("id") or "unknown")
        else:
            problems.append("case.json 不存在: %s（case_id 填 unknown）" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败（降级继续）: %s" % e)

    fields = contract_fields(case)
    all_files, corpus_files = scan_inputs(args.input_root)
    case_records = scan_case_records(case)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "research_question": {"object": None, "mechanism": None, "method": None,
                                  "time_range": None, "comparison": None,
                                  "evidence_requirements": None, "scope": None},
            "subquestions": [],
            "query_plan": [],
            "search_rounds": [],
            "candidates": [],
            "gaps": [],
            "stop_criteria": {"declared_before": None, "applied": None,
                              "stop_reason": None, "marginal_rule": None,
                              "rationale": None},
            "steps": [],
            "reproducibility": {"total_subquestions": 0, "query_covered": 0,
                                "evidence_covered": 0, "uncovered": 0, "ratio": None,
                                "note": "Step 3/4 回填：covered=有查询且有候选关联或缺口登记"},
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待 Step 1-4 回填"},
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

    # 停止条件事前声明模板（对应 declared_tolerances 的事前声明纪律）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        stop_path = os.path.join(args.work_dir, "stop_criteria.json")
        if not os.path.exists(stop_path):
            with open(stop_path, "w", encoding="utf-8") as f:
                json.dump({"note": "Step 1 检索前必须填写；声明后禁止事后放宽。"
                                   "回填 result.stop_criteria 时须与之一致。",
                           "declared_at": None,
                           "stop_criteria": {"evidence_sufficient": None,
                                             "marginal_rule": None,
                                             "manual_takeover": None}}, f,
                            ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("停止条件模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 科研材料 %d 个"
          % (case_id, len(fields), len(all_files), len(corpus_files)))
    for p in corpus_files[:20]:
        print("  material: %s" % p)
    for r in case_records:
        print("  case 内嵌记录集: %s (%d 条)" % (r["key"], r["count"]))
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
