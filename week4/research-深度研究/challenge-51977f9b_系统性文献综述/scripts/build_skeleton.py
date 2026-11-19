#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与题录清单（sysrev-review-synthesis）。

读取 case.json 提取 output_contract 全部字段名与题录记录（records/papers/
candidates/items 等常见键），扫描输入目录补齐材料清单，写入骨架 result.json
（全部键，待回填）与 /app/work/protocol_ledger.json 综述协议注册台账模板
（检索协议+纳排标准须在任何判定之前注册版本，之后禁止口头修改）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 WARN 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RECORD_KEYS = ("records", "papers", "candidates", "items", "documents",
               "literature", "search_results", "results", "exports")


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


def _record_id(entry, idx):
    for k in ("record_id", "item_id", "paper_id", "id", "doc_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "R%02d" % (idx + 1)


def extract_records(case):
    """从 case.json 常见键提取题录记录清单（id + 标题线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，题录清单未提取"
    for key in RECORD_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                doi = None
                year = None
                if isinstance(e, dict):
                    for tk in ("title", "name", "paper_title"):
                        if e.get(tk):
                            title = str(e[tk])[:160]
                            break
                    doi = e.get("doi") or e.get("DOI")
                    year = e.get("year") or e.get("pub_year")
                elif isinstance(e, str):
                    title = e[:160]
                out.append({"record_id": _record_id(e, i), "title": title,
                            "doi": str(doi) if doi else None,
                            "year": year if isinstance(year, int) else None,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含题录键（%s），请人工核对后填入 result.records" % ",".join(RECORD_KEYS)


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
    recs, rec_note = extract_records(case)
    if rec_note:
        problems.append(rec_note)
    all_files = scan_inputs(args.input_root)

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None,
                                  "pico": {"population": None, "intervention": None,
                                           "comparison": None, "outcome": None,
                                           "study_design": None},
                                  "scope": None, "time_range": None},
            "review_registration": {"review_id": None, "registered_at": None,
                                    "question_final": None, "protocol_version": None},
            "search_protocol": {"databases": [], "query_string": None, "fields": [],
                                "time_range": None, "language_limits": None,
                                "search_date": None, "criteria_mapping": None},
            "criteria": {"version": None, "declared_at": None,
                         "inclusion": [], "exclusion": []},
            "records": [{"record_id": r["record_id"], "source_ref": r["source_ref"],
                         "title": r["title"], "year": r["year"], "doi": r["doi"],
                         "source_db": None, "venue_type": "unknown",
                         "decision": "pending_review", "reason_code": None,
                         "criteria_ref": [], "evidence_quote": None,
                         "evidence_location": None, "confidence": None,
                         "rationale": None, "duplicate_of": None,
                         "merge_basis": None, "missing_metadata": [],
                         "annotation": {"annotator_a": None, "annotator_b": None},
                         "pending_reason": None, "judged": False}
                        for r in recs],
            "funnel": {"identified": len(recs), "duplicates_removed": 0, "screened": len(recs),
                       "excluded": 0, "included": 0, "pending_review": len(recs),
                       "excluded_by_reason": {}, "closure": None, "closure_note": "flow_audit.py 回填"},
            "conflicts": [],
            "pending_review": [],
            "quality_appraisal": {"scale": {"id": None, "version": None, "dimensions": []},
                                  "assessments": [], "coverage_note": None},
            "extraction": {"schema_note": None, "items": []},
            "synthesis": {"conclusions": [], "conflict_matrix": [], "gaps": [],
                          "bias_registry": [], "gaps_note": None, "bias_note": None},
            "coverage": {"total_records": len(recs), "judged_records": 0,
                         "included": 0, "excluded": 0, "pending_review": len(recs),
                         "duplicates_merged": 0, "ratio": None},
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐条纳排判定后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}]}
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

    # 综述协议注册台账模板（事前声明：检索协议+纳排标准须在任何判定之前注册
    # 版本号与 registered_at，之后禁止口头修改；确需修改必须新增版本并回溯重判）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        led_path = os.path.join(args.work_dir, "protocol_ledger.json")
        if not os.path.exists(led_path):
            with open(led_path, "w", encoding="utf-8") as f:
                json.dump({"note": "综述协议（研究问题/检索式/纳排标准）须在任何判定之前"
                                   "注册版本号与 registered_at；中途禁止口头修改，确需修改"
                                   "必须新增版本并逐条回溯重判受影响记录（防协议漂移）。",
                           "versions": [], "final_version": None}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("protocol_ledger 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 题录 %d 条"
          % (case_id, len(fields), len(all_files), len(recs)))
    for r in recs:
        print("  record: %s  %s" % (r["record_id"], r["title"][:60]))
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
