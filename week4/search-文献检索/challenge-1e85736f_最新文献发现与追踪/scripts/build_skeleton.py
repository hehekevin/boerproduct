#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与候选记录清单（lit-track-incremental）。

读取 case.json 提取 output_contract 全部字段名与本次窗口抓到的文献记录
（records/papers/candidates/items 等常见键），扫描输入目录补齐材料清单，
写入骨架 result.json（全部键，待回填）与 /app/work/track_policy.json
口径模板（时间窗 / 水位 / 去重键 / 权重须在任何判定与排序之前声明）。
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

CANDIDATE_KEYS = ("records", "papers", "candidates", "items", "documents",
                  "literature", "search_results", "results", "feed")


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
    for k in ("item_id", "record_id", "paper_id", "id", "doc_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "R%02d" % (idx + 1)


def extract_candidates(case):
    """从 case.json 常见键提取本次窗口抓到的记录清单（id + 标题线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，记录清单未提取"
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
    return out, "case.json 未含记录键（%s），请人工核对后填入 result.items" % ",".join(CANDIDATE_KEYS)


def extract_previous(case):
    """提取上一次快照的记录键清单（供增量比对；无则记空）。"""
    for key in ("previous_snapshot", "snapshot", "prior_snapshot", "watermark_items"):
        v = case.get(key) if isinstance(case, dict) else None
        if isinstance(v, list):
            keys = []
            for e in v:
                if isinstance(e, dict):
                    keys.append({"doi": e.get("doi"), "arxiv_id": e.get("arxiv_id"),
                                 "title": e.get("title")})
            return keys
    return []


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
    prev = extract_previous(case)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"topic": None, "scope": None, "sources": []},
            "window": {"start": None, "end": None, "timezone": None,
                       "boundary_rule": "start <= published_date <= end（ISO 8601，按声明时区）"},
            "watermark": {"previous_snapshot_ref": None, "watermark_date": None,
                          "window_index": None, "declared_at": None},
            "dedup_policy": {"title_normalization": "casefold + 去标点空白（\\w 含 CJK，不用 isalpha）",
                             "id_precedence": "doi > arxiv_id > title_norm",
                             "version_link_rule": "同 dedup_key 按发表日升序构成版本链",
                             "declared_at": None},
            "rubric": {"weights": {"relevance": None, "recency": None, "confidence": None},
                       "tie_break": ["track_score 降序", "published_date 降序", "item_id 升序"],
                       "normalization": None, "declared_at": None},
            "items": [{"item_id": c["item_id"], "source_ref": c["source_ref"],
                       "title": c["title"], "published_date": None,
                       "indexed_date": None, "venue_type": "unknown",
                       "version_tag": None, "doi": None, "arxiv_id": None,
                       "dedup_key": None, "in_window": None,
                       "event": None, "related_to": None,
                       "relevance": None, "label": "hold",
                       "excluded_by": [], "evidence_quote": None,
                       "evidence_location": None, "confidence": None,
                       "rationale": None,
                       "factors": {"relevance": None, "recency": None, "confidence": None},
                       "track_score": None, "rank": None,
                       "missing_metadata": [], "pending_reason": None,
                       "judged": False}
                      for c in cands],
            "ranking": {"ordered_ids": [], "ties": [], "top_k": None, "k_value": None,
                        "note": "track_engine.py 回填"},
            "coverage": {"total": len(cands), "in_window": 0, "judged": 0,
                         "push": 0, "hold": 0, "exclude": 0, "new": 0,
                         "version_update": 0, "duplicates_merged": 0,
                         "backfilled": 0, "retracted": 0, "out_of_window": 0,
                         "ratio": None},
            "version_chains": [],
            "source_registry": [],
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
        if prev:
            skeleton["previous_snapshot_keys"] = prev
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

    # 追踪口径模板（事前声明：判定与排序前必须填写，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        pol_path = os.path.join(args.work_dir, "track_policy.json")
        if not os.path.exists(pol_path):
            with open(pol_path, "w", encoding="utf-8") as f:
                json.dump({"note": "时间窗 / 水位 / 去重键规则 / 权重必须在任何判定与排序之前声明；"
                                   "声明后禁止调整，须与 result.window / result.dedup_policy /"
                                   " result.rubric 一致。",
                           "declared_at": None,
                           "window": {"start": None, "end": None, "timezone": None},
                           "watermark": {"previous_snapshot_ref": None,
                                         "watermark_date": None, "window_index": None},
                           "dedup_policy": {"title_normalization": "casefold + 去标点空白",
                                            "id_precedence": "doi > arxiv_id > title_norm",
                                            "version_link_rule": "同 dedup_key 按发表日升序"},
                           "rubric": {"weights": {"relevance": None, "recency": None,
                                                  "confidence": None},
                                      "tie_break": ["track_score 降序", "published_date 降序",
                                                    "item_id 升序"],
                                      "normalization": None}}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("track_policy 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 本次记录 %d 条 | 上次快照键 %d 个"
          % (case_id, len(fields), len(all_files), len(cands), len(prev)))
    for c in cands:
        print("  record: %s  %s" % (c["item_id"], c["title"][:60]))
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
