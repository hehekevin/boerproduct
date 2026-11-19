#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与候选文献清单（lit-screen-rank）。

读取 case.json 提取 output_contract 全部字段名与候选文献（papers/candidates/items
等常见键），扫描输入目录补齐材料清单，写入骨架 result.json（全部键，待回填）
与 /app/work/rubric.json 打分口径模板（多因子权重须在任何排序前声明）。
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

CANDIDATE_KEYS = ("papers", "candidates", "items", "records", "documents",
                  "literature", "search_results", "results")


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


def _item_id(entry, idx):
    for k in ("item_id", "paper_id", "id", "doc_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "item-%02d" % (idx + 1)


def extract_candidates(case):
    """从 case.json 常见键提取候选文献清单（id + 标题线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，候选清单未提取"
    for key in CANDIDATE_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                if isinstance(e, dict):
                    for tk in ("title", "name", "paper_title"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"item_id": _item_id(e, i), "title": title,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含候选文献键（%s），请人工核对后填入 result.items" % ",".join(CANDIDATE_KEYS)


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
    cands, cand_note = extract_candidates(case)
    if cand_note:
        problems.append(cand_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None, "scope": None, "time_range": None},
            "criteria": {"inclusion": [], "exclusion": []},
            "rubric": {"weights": {"relevance": None, "quality": None, "recency": None},
                       "tie_break": ["fused_score 降序", "recency 降序", "item_id 升序"],
                       "normalization": None, "declared_at": None},
            "items": [{"item_id": c["item_id"], "source_ref": c["source_ref"],
                       "title": c["title"], "venue_type": "unknown",
                       "relevance": None, "label": "pending",
                       "criteria_hit": [], "excluded_by": [],
                       "evidence_quote": None, "evidence_location": None,
                       "confidence": None, "rationale": None,
                       "factors": {"relevance": None, "quality": None, "recency": None},
                       "fused_score": None, "rank": None,
                       "duplicate_of": None, "missing_metadata": [],
                       "pending_reason": None, "judged": False}
                      for c in cands],
            "ranking": {"ordered_ids": [], "ties": [], "top_k": None, "k_value": None,
                        "note": "score_rank.py 回填"},
            "coverage": {"total_candidates": len(cands), "judged_items": 0,
                         "keep": 0, "pending": 0, "exclude": 0,
                         "duplicates_merged": 0, "ratio": None},
            "conflicts": [],
            "pending_review": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐条判定后回填"},
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

    # 打分口径模板（事前声明：排序前必须填写权重，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rubric_path = os.path.join(args.work_dir, "rubric.json")
        if not os.path.exists(rubric_path):
            with open(rubric_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何排序之前必须声明多因子权重（三项合计=1.0）与归一化口径；"
                                   "声明后禁止调整，须与 result.rubric 一致。",
                           "declared_at": None,
                           "weights": {"relevance": None, "quality": None, "recency": None},
                           "tie_break": ["fused_score 降序", "recency 降序", "item_id 升序"],
                           "normalization": None}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("rubric 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 候选文献 %d 条"
          % (case_id, len(fields), len(all_files), len(cands)))
    for c in cands:
        print("  candidate: %s  %s" % (c["item_id"], c["title"][:60]))
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
