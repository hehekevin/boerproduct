#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与资料库/需求清单（sci-file-retrieval）。

读取 case.json 提取 output_contract 全部字段名、资料库文件清单（files/documents/
library 等常见键，含内容摘要与元数据）与自然语言检索需求（queries/questions 等），
写入骨架 result.json（全部键，待回填）与 /app/work/query_plan.json 检索式台账模板
（关键词/同义词/元数据过滤/内容词 + 权重须在任何排序前声明）。
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

LIB_KEYS = ("files", "documents", "library", "inventory", "materials",
            "records", "resources", "file_list")
QUERY_KEYS = ("queries", "questions", "requirements", "retrieval_tasks",
              "search_tasks", "tasks")
FID_KEYS = ("file_id", "doc_id", "id", "uid", "name", "filename", "path")
TITLE_KEYS = ("title", "name", "filename", "path", "doc_title")
CONTENT_KEYS = ("content", "content_summary", "summary", "abstract", "text",
                "excerpt", "snippet", "description", "ocr_text", "body", "preview")
META_KEYS = ("metadata", "meta", "attrs", "properties", "fields")
RESTRICT_KEYS = ("restricted", "permission", "access", "access_level",
                 "permission_restricted")
PAIR_LIMIT = 400  # 预填 (query,file) 判定条目的上限，超过则留空待人工补


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
    for k in keys:
        if isinstance(entry, dict) and entry.get(k):
            return entry[k]
    return None


def _extract(case, keys, note_kind):
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，%s 未提取" % note_kind
    for key in keys:
        v = case.get(key)
        candidates = []
        if isinstance(v, list) and v:
            candidates.append((key, v))
        elif isinstance(v, dict):
            # 兼容嵌套包装（如 library.files / retrieval.queries）
            for k2, v2 in v.items():
                if isinstance(v2, list) and v2:
                    candidates.append(("%s.%s" % (key, k2), v2))
        if candidates:
            base, arr = candidates[0]
            for i, e in enumerate(arr):
                out.append((base, i, e if isinstance(e, dict) else
                            {"_text": str(e)[:200]}))
            return out, ""
    return out, "case.json 未含 %s 键（%s），请人工核对后填入" % (note_kind, ",".join(keys))


def extract_library(case):
    """提取资料库文件清单：file_id + 标题 + 内容线索 + 元数据 + 受限标记。"""
    raw, note = _extract(case, LIB_KEYS, "资料库")
    files = []
    for key, i, e in raw:
        fid = _first(e, FID_KEYS) or "file-%02d" % (i + 1)
        title = _first(e, TITLE_KEYS) or ""
        content = _first(e, CONTENT_KEYS)
        meta = _first(e, META_KEYS)
        restricted = False
        rreason = None
        for rk in RESTRICT_KEYS:
            rv = e.get(rk)
            if isinstance(rv, bool) and rv:
                restricted, rreason = True, "case.json 标记 %s=true" % rk
            elif isinstance(rv, str) and rv.strip().lower() in (
                    "restricted", "no_access", "denied", "none", "false"):
                restricted, rreason = True, "case.json %s=%s" % (rk, rv)
        files.append({
            "file_id": str(fid), "source_ref": "%s[%d]" % (key, i),
            "title": str(title)[:120] if title else "",
            "content_available": bool(content and str(content).strip()),
            "content_preview": (str(content)[:160] if content else None),
            "metadata": meta if isinstance(meta, dict) else None,
            "restricted": restricted, "restricted_reason": rreason,
        })
    return files, note


def extract_queries(case):
    """提取自然语言检索需求清单。"""
    raw, note = _extract(case, QUERY_KEYS, "检索需求")
    qkeys = ("question", "query", "text", "requirement", "description",
             "task", "_text", "prompt")
    out = []
    for key, i, e in raw:
        qid = _first(e, ("query_id", "question_id", "id", "qid")) or "Q%02d" % (i + 1)
        qtext = _first(e, qkeys) or ""
        out.append({"query_id": str(qid), "question": str(qtext)[:300],
                    "source_ref": "%s[%d]" % (key, i)})
    return out, note


def scan_inputs(root):
    all_files = []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                all_files.append(os.path.relpath(
                    os.path.join(dirpath, fn), root).replace("\\", "/"))
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
    case, case_id = {}, "unknown"
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
    files, f_note = extract_library(case)
    queries, q_note = extract_queries(case)
    for n in (f_note, q_note):
        if n:
            problems.append(n)
    all_files = scan_inputs(args.input_root)

    # 预填 (query, file) 判定条目（label 默认 pending，强制逐条判定）
    pairs = len(queries) * len(files)
    prefilled = pairs <= PAIR_LIMIT
    hits = []
    if prefilled:
        n = 0
        for q in queries:
            for fl in files:
                n += 1
                hits.append({
                    "hit_id": "H%03d" % n, "query_id": q["query_id"],
                    "file_id": fl["file_id"], "file_ref": fl["source_ref"],
                    "label": "pending", "relevance": None,
                    "matched_terms": [], "filters_applied": [],
                    "evidence_quote": None, "evidence_location": None,
                    "confidence": None, "rationale": None,
                    "factors": {"term_match": None, "metadata_match": None,
                                "content_match": None},
                    "fused_score": None, "rank": None, "duplicate_of": None,
                    "restricted": fl["restricted"], "pending_reason": "待判定",
                    "no_match_reason": None, "judged": False})
    elif pairs:
        problems.append("判定对数 %d 超预填上限 %d，hits 留空待按流程逐条补"
                        % (pairs, PAIR_LIMIT))

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "library": {"root": args.input_root, "total_files": len(files),
                        "files": files},
            "queries": queries,
            "query_plan": {"scoring": {
                "weights": {"term_match": None, "metadata_match": None,
                            "content_match": None},
                "tie_break": ["fused_score 降序", "content_match 降序", "hit_id 升序"],
                "normalization": None, "declared_at": None},
                "declared_at": None, "per_query": []},
            "hits": hits,
            "ranking": {"per_query": [], "weights": None, "tie_break": None,
                        "declared_at": None,
                        "note": "score_rank.py 回填"},
            "coverage": {"total_pairs": len(hits) if prefilled else pairs,
                         "judged_pairs": 0, "hit": 0, "pending": 0, "no_hit": 0,
                         "ratio": None, "per_query": {}},
            "restricted_files": [], "no_result_queries": [],
            "pending_review": [], "conflicts": [], "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None, "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [],
                    "unverifiable": [], "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待检索判定后回填"},
                    "changelog": [{"step": "step0",
                                   "change": "build_skeleton 落骨架"}]}
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

    # 检索式台账模板（事前声明：排序前必须填写权重与词表，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        qp_path = os.path.join(args.work_dir, "query_plan.json")
        if not os.path.exists(qp_path):
            with open(qp_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何排序之前必须声明三因子权重（合计=1.0）与"
                                   "每个需求的检索式（keywords/synonyms/"
                                   "metadata_filters/content_terms + "
                                   "requirement_mapping）；声明后禁止调整，"
                                   "须与 result.query_plan 一致。",
                           "declared_at": None,
                           "scoring": {"weights": {"term_match": None,
                                                   "metadata_match": None,
                                                   "content_match": None},
                                       "tie_break": ["fused_score 降序",
                                                     "content_match 降序",
                                                     "hit_id 升序"],
                                       "normalization": None,
                                       "declared_at": None},
                           "per_query": []}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("query_plan 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 输入文件 %d 个 | "
          "资料库文件 %d 份 | 检索需求 %d 条 | 预填判定对 %d"
          % (case_id, len(fields), len(all_files), len(files), len(queries),
             len(hits)))
    for fl in files:
        print("  file: %s  %s%s" % (fl["file_id"], fl["title"][:50],
              " [受限]" if fl["restricted"] else ""))
    for q in queries:
        print("  query: %s  %s" % (q["query_id"], q["question"][:60]))
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
