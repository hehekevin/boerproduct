#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与参考集清单（cov-gap-audit）。

读取 case.json 提取 output_contract 全部字段名、参考集（reference_set/known_set
等常见键）、检索查询（queries）与检索结果记录（retrieved_records），扫描输入
目录补齐材料清单，写入骨架 result.json（全部键，待回填）与 /app/work/
coverage_ledger.json 分母冻结台账（覆盖率分母必须来自冻结参考集，禁止以结果
定义分母）。三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺
result.json。

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

REF_KEYS = ("reference_set", "known_set", "golden_set", "known_items",
            "benchmark_references", "references")
QUERY_KEYS = ("queries", "search_queries", "searches")
RET_KEYS = ("retrieved_records", "retrieved", "search_results", "results",
            "hits", "found_records", "records")


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


def _first_list(case, keys):
    for k in keys:
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, list) and v:
            return v, k
        if isinstance(v, dict) and isinstance(v.get("items"), list) and v["items"]:
            return v["items"], k
    return [], None


def _rid(entry, idx):
    for k in ("ref_id", "paper_id", "id", "doc_id", "uid", "item_id"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "K%02d" % (idx + 1)


def _title(entry):
    if isinstance(entry, dict):
        for tk in ("title", "name", "paper_title"):
            if entry.get(tk):
                return str(entry[tk])[:160]
    elif isinstance(entry, str):
        return entry[:160]
    return ""


def extract_reference(case):
    refs, key = [], None
    for k in REF_KEYS:
        v = case.get(k) if isinstance(case, dict) else None
        if isinstance(v, list) and v:
            refs, key = v, k
            break
        if isinstance(v, dict) and isinstance(v.get("items"), list) and v["items"]:
            refs, key = v["items"], k
            break
    out = []
    for i, e in enumerate(refs):
        idents = {}
        if isinstance(e, dict) and isinstance(e.get("identifiers"), dict):
            for ik in ("doi", "pmid"):
                if e["identifiers"].get(ik):
                    idents[ik] = str(e["identifiers"][ik])
        out.append({"ref_id": _rid(e, i), "source_ref": "%s[%d]" % (key, i) if key else "manual-%02d" % (i + 1),
                    "title": _title(e), "year": e.get("year") if isinstance(e, dict) else None,
                    "identifiers": idents,
                    "ref_status": str(e.get("ref_status") or "pending") if isinstance(e, dict) else "pending",
                    "inclusion_reason": e.get("inclusion_reason") if isinstance(e, dict) else None})
    return out, key


def extract_queries(case):
    qs, key = _first_list(case, QUERY_KEYS)
    out = []
    for i, e in enumerate(qs):
        if isinstance(e, dict):
            out.append({"query_id": str(e.get("query_id") or "Q%d" % (i + 1)),
                        "query_string": str(e.get("query_string") or e.get("query") or ""),
                        "fields": str(e.get("fields") or ""),
                        "source_db": str(e.get("source_db") or e.get("source") or ""),
                        "time_window": str(e.get("time_window") or "")})
        elif isinstance(e, str):
            out.append({"query_id": "Q%d" % (i + 1), "query_string": e,
                        "fields": "", "source_db": "", "time_window": ""})
    return out, key


def extract_retrieved(case):
    rs, key = _first_list(case, RET_KEYS)
    out = []
    for i, e in enumerate(rs):
        idents = {}
        if isinstance(e, dict) and isinstance(e.get("identifiers"), dict):
            for ik in ("doi", "pmid"):
                if e["identifiers"].get(ik):
                    idents[ik] = str(e["identifiers"][ik])
        out.append({"record_id": str(e.get("record_id") or "R%02d" % (i + 1)) if isinstance(e, dict) else "R%02d" % (i + 1),
                    "title": _title(e), "year": e.get("year") if isinstance(e, dict) else None,
                    "identifiers": idents,
                    "source_db": str(e.get("source_db") or "") if isinstance(e, dict) else "",
                    "query_id": str(e.get("query_id") or "") if isinstance(e, dict) else "",
                    "source_ref": "%s[%d]" % (key, i) if key else ""})
    return out, key


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
        try:
            args = ap.parse_args()
        except SystemExit:
            print("[build_skeleton] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[build_skeleton] 参数初始化失败: %s" % e)
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
    refs, ref_key = extract_reference(case)
    queries, q_key = extract_queries(case)
    rets, r_key = extract_retrieved(case)
    if not refs:
        problems.append("case.json 未含参考集键（%s），请人工核对后填入 result.reference_set.items"
                        % ",".join(REF_KEYS))
    all_files = scan_inputs(args.input_root)

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None, "scope": None, "time_range": None},
            "reference_set": {"frozen": None, "frozen_at": None, "source": None,
                              "denominator_rule": "分母=参考集中 ref_status=included 的条目；"
                                                  "unavailable/retracted 登记但不入分母",
                              "items": [{"ref_id": r["ref_id"], "source_ref": r["source_ref"],
                                         "title": r["title"], "year": r["year"],
                                         "identifiers": r["identifiers"],
                                         "ref_status": r["ref_status"],
                                         "inclusion_reason": r["inclusion_reason"]}
                                        for r in refs]},
            "queries": queries,
            "items": [{"ref_id": r["ref_id"], "source_ref": r["source_ref"],
                       "title": r["title"], "ref_status": r["ref_status"],
                       "hit_status": None, "matched_by": None, "matched_query_id": None,
                       "matched_record_ref": None, "evidence_quote": None,
                       "evidence_location": None, "rationale": None, "judged": False}
                      for r in refs],
            "retrieved_summary": {"records_seen": len(rets), "source_key": r_key},
            "coverage": {"denominator_basis": "frozen_reference_set",
                         "match_rule": None, "total_reference": len(refs),
                         "included": 0, "unavailable": 0, "judged": 0,
                         "hit": 0, "miss": 0, "extra_records": None,
                         "coverage_rate": None, "miss_rate": None,
                         "note": "coverage_calc.py 回填"},
            "miss_registry": [],
            "supplementary": {"queries": [], "new_hits_total": None,
                              "marginal_gain": None, "effective": None,
                              "effective_actual": None, "post_coverage_rate": None,
                              "post_miss_rate": None, "stop_rule": None,
                              "residual_misses": [], "note": "supp_check.py 校验回填"},
            "review": {"sampled": [], "agreement_rate": None, "residual_explanation": []},
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待冻结参考集与逐条命中判定后回填"},
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

    # 分母冻结台账（覆盖率分母必须来自冻结参考集；/app/work 台账供闸门核对）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        ledger_path = os.path.join(args.work_dir, "coverage_ledger.json")
        with open(ledger_path, "w", encoding="utf-8") as f:
            json.dump({"note": "分母冻结台账：result.reference_set 须与本台账一致后才能宣称已核对；"
                               "frozen=true 且 frozen_at 非空之前不得计算覆盖率。",
                       "case_id": case_id, "frozen": None, "frozen_at": None,
                       "total_reference": len(refs),
                       "ref_ids": [r["ref_id"] for r in refs],
                       "ref_status_counts": {}}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("coverage_ledger 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 参考条目 %d 条 | 查询 %d 条 | 检索记录 %d 条"
          % (case_id, len(fields), len(all_files), len(refs), len(queries), len(rets)))
    for r in refs:
        print("  reference: %s  [%s]  %s" % (r["ref_id"], r["ref_status"], r["title"][:60]))
    for q in queries:
        print("  query: %s  [%s]  %s" % (q["query_id"], q["source_db"], q["query_string"][:60]))
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
