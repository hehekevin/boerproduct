#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与候选选题清单（topic-novelty-audit）。

读取 case.json 提取 output_contract 全部字段名、候选选题（proposals/topics/candidates
等常见键）与已知工作清单（known_works/references/papers 等），扫描输入目录补齐材料
清单，写入骨架 result.json（全部键，待回填）、/app/work/rubric.json 分级口径模板
（任何分级/排序前必须声明）与 /app/work/known_works.json 对照台账。
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

PROPOSAL_KEYS = ("proposals", "topics", "candidates", "ideas", "research_proposals",
                 "topic_candidates", "items")
WORK_KEYS = ("known_works", "references", "papers", "literature", "works",
             "prior_work", "related_works")


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


def _pid(entry, idx):
    for k in ("proposal_id", "topic_id", "id", "item_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "T%02d" % (idx + 1)


def _wid(entry, idx):
    for k in ("work_id", "paper_id", "id", "ref_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "W%02d" % (idx + 1)


def extract_list(case, keys, idfn, prefix):
    """从 case.json 常见键提取清单（id + 标题线索）。返回 (list, note)。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，%s 未提取" % prefix
    for key in keys:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                if isinstance(e, dict):
                    for tk in ("title", "name", "topic", "paper_title", "work_title"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"id": idfn(e, i), "title": title,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, ("case.json 未含 %s 键（%s），请人工核对后填入" % (prefix, ",".join(keys)))


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
    props, prop_note = extract_list(case, PROPOSAL_KEYS, _pid, "候选选题")
    if prop_note:
        problems.append(prop_note)
    works, work_note = extract_list(case, WORK_KEYS, _wid, "已知工作")
    if work_note:
        problems.append(work_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_context": {"direction": None, "scope": None, "constraints": None},
            "criteria": {"inclusion": [], "exclusion": []},
            "rubric": {"grade_rules": [], "weights": {"novelty": None, "feasibility": None,
                                                      "evidence": None},
                       "tie_break": ["fused_score 降序", "novelty 因子降序", "proposal_id 升序"],
                       "normalization": None, "declared_at": None},
            "proposals": [{"proposal_id": p["id"], "source_ref": p["source_ref"],
                           "title": p["title"],
                           "structure": {"problem": None, "hypothesis": None,
                                         "method": None, "expected_contribution": None},
                           "missing_elements": [], "novelty_claims": [],
                           "novelty_grade": None,
                           "feasibility": {"data": {"status": None, "basis": None},
                                           "method": {"status": None, "basis": None},
                                           "resource": {"status": None, "basis": None},
                                           "time": {"status": None, "basis": None}},
                           "feasibility_verdict": None,
                           "duplicate_of": None, "confidence": None, "rationale": None,
                           "factors": {"novelty": None, "feasibility": None, "evidence": None},
                           "fused_score": None, "rank": None,
                           "missing_metadata": [], "pending_reason": None, "judged": False}
                          for p in props],
            "ranking": {"ordered_ids": [], "ties": [], "top_k": None, "k_value": None,
                        "note": "novelty_rank.py 回填"},
            "coverage": {"total_proposals": len(props), "judged": 0,
                         "structure_complete": 0, "novelty_covered": 0,
                         "feasibility_flagged": 0, "ratio": None},
            "conflicts": [], "human_review": [], "risks": [], "alternatives": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐条结构化与评估后回填"},
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

    # 分级口径模板（事前声明：任何分级/排序前必须填写，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rubric_path = os.path.join(args.work_dir, "rubric.json")
        if not os.path.exists(rubric_path):
            with open(rubric_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何分级/排序之前必须声明五级 grade_rules、三因子权重"
                                   "（合计=1.0）与归一化口径；声明后禁止调整，须与 result.rubric 一致。",
                           "declared_at": None, "grade_rules": [],
                           "weights": {"novelty": None, "feasibility": None, "evidence": None},
                           "tie_break": ["fused_score 降序", "novelty 因子降序", "proposal_id 升序"],
                           "normalization": None}, f, ensure_ascii=False, indent=1)
        works_path = os.path.join(args.work_dir, "known_works.json")
        with open(works_path, "w", encoding="utf-8") as f:
            json.dump({"note": "新颖性对照台账（build_skeleton 提取；判定必须逐条回溯到此）",
                       "known_works": works}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("rubric/known_works 台账写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 候选选题 %d 条 | 已知工作 %d 条"
          % (case_id, len(fields), len(all_files), len(props), len(works)))
    for p in props:
        print("  proposal: %s  %s" % (p["id"], p["title"][:60]))
    for w in works:
        print("  known_work: %s  %s" % (w["id"], w["title"][:60]))
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
