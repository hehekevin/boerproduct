#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与文献清单（lit-review-bind）。

读取 case.json 提取 output_contract 全部字段名与研究文献（papers/candidates/
literature 等常见键），扫描输入目录补齐材料清单，写入骨架 result.json（全部键，
待回填）与 /app/work/outline.json 大纲工作模板。三级容错：任何一级失败都降级
产出可用骨架，绝不崩溃、绝不缺 result.json。

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

PAPER_KEYS = ("papers", "candidates", "items", "records", "documents",
              "literature", "references", "sources", "search_results", "results")


def contract_fields(case):
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


def _paper_id(entry, idx):
    for k in ("paper_id", "item_id", "id", "doc_id", "ref_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "R%02d" % (idx + 1)


def _paper_text(entry):
    """提取可用于逐字回证的正文/摘要字段。"""
    if not isinstance(entry, dict):
        return ""
    for k in ("abstract", "text", "content", "excerpt", "fulltext", "summary"):
        if entry.get(k) and str(entry.get(k)).strip():
            return str(entry[k])
    return ""


def extract_papers(case):
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，文献清单未提取"
    for key in PAPER_KEYS:
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
                out.append({"paper_id": _paper_id(e, i), "title": title,
                            "source_ref": "%s[%d]" % (key, i),
                            "has_text": bool(_paper_text(e))})
            return out, ""
    return out, "case.json 未含文献键（%s），请人工核对后填入 result.items" % ",".join(PAPER_KEYS)


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
    papers, paper_note = extract_papers(case)
    if paper_note:
        problems.append(paper_note)
    all_files = scan_inputs(args.input_root)

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None, "scope": None, "time_range": None},
            "criteria": {"inclusion": [], "exclusion": []},
            "items": [{"paper_id": p["paper_id"], "source_ref": p["source_ref"],
                       "title": p["title"], "label": "pending", "criteria_hit": [],
                       "excluded_by": [], "theme_ids": [], "duplicate_of": None,
                       "missing_metadata": [], "pending_reason": None, "judged": False}
                      for p in papers],
            "themes": [],
            "outline": {"order": [], "sections": []},
            "evidence_table": [],
            "disputes": [],
            "omissions": [],
            "coverage": {"total_papers": len(papers), "included_papers": 0,
                         "cited_in_outline": 0, "uncited": 0,
                         "omissions_registered": 0, "ratio": None},
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待筛选/归纳/组织/写作四步后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架"}]}
        for f in fields:
            if f not in skeleton:
                skeleton[f] = "unknown"
    except Exception as e:
        problems.append("骨架组装异常: %s" % e)
        skeleton = {"case_id": case_id, "status": "partial", "result": {},
                    "claims": [], "uncertainties": {"summary": "骨架降级"}, "changelog": []}

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

    # 大纲工作模板（主题分组须先于草稿写作声明，之后只允许补充不允许推翻已绑定证据）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        op = os.path.join(args.work_dir, "outline.json")
        if not os.path.exists(op):
            with open(op, "w", encoding="utf-8") as f:
                json.dump({"note": "综述大纲台账：主题分组/时间脉络/方法论脉络须先于草稿写作声明；"
                                   "每个主题须给 paper_ids 与边界；与 result.themes/outline 保持一致。",
                           "declared_at": None, "themes": [], "order": [], "sections": []},
                          f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("outline 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 文献 %d 条（含正文 %d 条）"
          % (case_id, len(fields), len(all_files), len(papers),
             sum(1 for p in papers if p["has_text"])))
    for p in papers:
        print("  paper: %s  %s" % (p["paper_id"], p["title"][:60]))
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
