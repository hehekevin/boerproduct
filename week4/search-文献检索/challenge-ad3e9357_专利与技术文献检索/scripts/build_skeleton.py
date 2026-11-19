#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与候选清单（patent-search-verify）。

读取 case.json 提取 output_contract 全部字段名与候选条目（专利/论文常见键），
扫描输入目录补齐材料清单，写入骨架 result.json（全部键，待回填）与
/app/work/ledger.json 检索口径与授权边界台账（任何筛选之前须事前声明）。
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

CANDIDATE_KEYS = ("patents", "papers", "publications", "patent_candidates",
                  "candidates", "items", "records", "documents",
                  "literature", "search_results", "results")
ID_KEYS = ("item_id", "patent_id", "paper_id", "doc_id", "id", "uid")
TITLE_KEYS = ("title", "name", "patent_title", "paper_title")
NUMBER_KEYS = ("publication_number", "patent_number", "grant_number",
               "application_number", "number", "pub_number")
PRIORITY_KEYS = ("priority_numbers", "priorities", "priority")
APP_KEYS = ("application_number", "application", "app_number")


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


def _first(entry, keys):
    if not isinstance(entry, dict):
        return None
    for k in keys:
        if entry.get(k):
            return entry[k]
    return None


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def extract_candidates(case):
    """从 case.json 常见键提取候选清单（id + 号码线索 + 标题线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，候选清单未提取"
    for key in CANDIDATE_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                entry = e if isinstance(e, dict) else {"title": str(e)}
                raw = _first(entry, NUMBER_KEYS)
                raw = str(raw) if raw is not None else None
                out.append({
                    "item_id": str(_first(entry, ID_KEYS) or "item-%02d" % (i + 1)),
                    "kind": str(entry.get("kind") or "unknown"),
                    "raw_number": raw,
                    "title": str(_first(entry, TITLE_KEYS) or "")[:120],
                    "priority_numbers": _as_list(_first(entry, PRIORITY_KEYS)),
                    "application_number": (lambda a: str(a) if a else None)(
                        _first(entry, APP_KEYS)),
                    "source_ref": "%s[%d]" % (key, i),
                })
            return out, ""
    return out, "case.json 未含候选条目键（%s），请人工核对后填入 result.items" % ",".join(CANDIDATE_KEYS)


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
            "sources": [],
            "items": [{"item_id": c["item_id"], "source_ref": c["source_ref"],
                       "kind": c["kind"], "raw_number": c["raw_number"],
                       "norm_number": None, "title": c["title"],
                       "priority_numbers": c["priority_numbers"],
                       "application_number": c["application_number"],
                       "relevance": None, "label": "pending",
                       "criteria_hit": [], "excluded_by": [],
                       "evidence_quote": None, "evidence_location": None,
                       "confidence": None, "rationale": None,
                       "family_id": None,
                       "legal_status": {"status": None, "effective_date": None,
                                        "source": None, "query_date": None,
                                        "lag_note": None},
                       "cross_refs": [], "tech_points": [],
                       "duplicate_of": None, "missing_metadata": [],
                       "pending_reason": None, "judged": False}
                      for c in cands],
            "family_groups": [],
            "legal_status_registry": [],
            "cross_registry": [],
            "screening": {"ordered_ids": [], "ties": [],
                          "rule": "relevance 层级(direct<indirect<irrelevant) → confidence 降序 → item_id 升序",
                          "note": "norm_family.py 回填"},
            "coverage": {"total_candidates": len(cands), "judged_items": 0,
                         "keep": 0, "pending": 0, "exclude": 0,
                         "families_merged": 0, "duplicates_merged": 0, "ratio": None},
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

    # 口径台账（事前声明：族归并口径、筛选破平规则、授权分级，声明后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        ledger_path = os.path.join(args.work_dir, "ledger.json")
        if not os.path.exists(ledger_path):
            with open(ledger_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何筛选之前必须声明族归并口径、筛选破平规则与授权分级策略；"
                                   "声明后禁止调整，须与 result 一致。",
                           "declared_at": None,
                           "family_scope_default": "simple",
                           "screening_tie_break": ["relevance 层级", "confidence 降序", "item_id 升序"],
                           "licensing_policy": "green=可展示原文/黄=仅登记元数据/红=仅登记存在性"},
                          f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("ledger 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 候选条目 %d 条"
          % (case_id, len(fields), len(all_files), len(cands)))
    for c in cands:
        print("  candidate: %s  [%s]  %s  %s" % (c["item_id"], c["kind"],
                                                 c["raw_number"] or "-", c["title"][:50]))
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
