#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与子问题/来源清单（deep-research-loop）。

读取 case.json 提取 output_contract 全部字段名、建议子问题（sub_questions /
research_plan / questions 等常见键）与研究来源（sources / records / documents /
papers / evidence / materials / corpus 等常见键），扫描输入目录补齐材料清单，
写入骨架 result.json（全部键，待回填）与 /app/work/plan.json 计划声明模板
（研究计划必须在任何检索迭代之前声明）。
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

SQ_KEYS = ("sub_questions", "research_plan", "questions", "research_questions", "plan")
SOURCE_KEYS = ("sources", "records", "documents", "papers", "evidence",
               "materials", "corpus", "search_results", "results", "candidates")


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


def _entry_id(entry, idx, prefix):
    for k in ("sq_id", "source_id", "id", "doc_id", "uid"):
        if isinstance(entry, dict) and entry.get(k):
            return str(entry[k])
    return "%s-%02d" % (prefix, idx + 1)


def extract_sqs(case):
    """从 case.json 常见键提取建议子问题清单（可能为空：计划由 Agent 事前声明）。"""
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，子问题未提取"
    for key in SQ_KEYS:
        v = case.get(key)
        if isinstance(v, dict) and isinstance(v.get("sub_questions"), list):
            v = v["sub_questions"]
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                text = ""
                if isinstance(e, dict):
                    for tk in ("text", "question", "title", "name"):
                        if e.get(tk):
                            text = str(e[tk])[:200]
                            break
                elif isinstance(e, str):
                    text = e[:200]
                out.append({"sq_id": _entry_id(e, i, "SQ"), "text": text,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含建议子问题键（%s），请由 Agent 事前声明研究计划" % ",".join(SQ_KEYS)


def extract_sources(case):
    """从 case.json 常见键提取研究来源清单（id + 内容线索）。"""
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，来源未提取"
    for key in SOURCE_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title = ""
                if isinstance(e, dict):
                    for tk in ("title", "name", "content", "text", "abstract"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"source_id": _entry_id(e, i, "S"), "title": title,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含研究来源键（%s），请人工核对材料后登记" % ",".join(SOURCE_KEYS)


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
    sqs, sq_note = extract_sqs(case)
    if sq_note:
        problems.append(sq_note)
    sources, src_note = extract_sources(case)
    if src_note:
        problems.append(src_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "research_question": {"question": None, "scope": None, "time_range": None},
            "plan": {"declared_at": None,
                     "sub_questions": [{"sq_id": s["sq_id"], "text": s["text"],
                                        "depends_on": [], "evidence_needs": None,
                                        "search_queries": [], "stop_rule": None,
                                        "source_ref": s["source_ref"]}
                                       for s in sqs],
                     "convergence": {"rule": None, "criteria": []}},
            "iterations": [],
            "findings": [],
            "divergent_views": [],
            "open_questions": [],
            "coverage": {"sub_questions_total": len(sqs), "answered": 0,
                         "partially_answered": 0, "unanswered": 0,
                         "findings_total": 0, "iterations_count": 0,
                         "sources_total": 0, "answered_ratio": None,
                         "note": "coverage_calc.py 回填"},
            "strength_summary": {"strong": 0, "moderate": 0, "weak": 0,
                                 "unverified": 0, "total": 0,
                                 "note": "coverage_calc.py 回填"},
            "plan_audit": {"state": "missing", "declared_at": None, "sq_count": len(sqs),
                           "digest": None, "problems": ["plan_audit.py 未运行"],
                           "note": "plan_audit.py 回填"},
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待研究计划声明与逐轮迭代后回填"},
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

    # 计划声明模板（事前声明：任何检索迭代之前必须写定，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        plan_path = os.path.join(args.work_dir, "plan.json")
        if not os.path.exists(plan_path):
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump({"note": "研究计划必须在任何检索迭代之前声明并锁定：子问题、依赖、"
                                   "证据需求、检索式、停止规则与收敛判据；声明后禁止调整，"
                                   "须与 result.plan 一致，由 plan_audit.py 审计。",
                           "declared_at": None, "sub_questions": [], "convergence": None},
                          f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("plan 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 文件 %d 个 | 子问题 %d 条 | 来源 %d 条"
          % (case_id, len(fields), len(all_files), len(sqs), len(sources)))
    for s in sqs:
        print("  sub-question: %s  %s" % (s["sq_id"], s["text"][:60]))
    for s in sources:
        print("  source: %s  %s" % (s["source_id"], s["title"][:60]))
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
