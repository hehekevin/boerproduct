#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与文献清单（lit-quality-appraise）。

读取 case.json 提取 output_contract 全部字段名与文献（papers/documents/articles
等常见键），扫描输入目录补齐材料清单，写入骨架 result.json（全部键，待回填）
与 /app/work/grading_rules.json 分级口径模板（须在任何复算之前声明，之后禁止调整）。
三级容错：任何一级失败都降级产出可用骨架，绝不崩溃、绝不缺 result.json。

定位标志：脚本校验自身与 SKILL.md 同包（../SKILL.md 存在）才视为挂载命中，
未命中时照常落盘但打印 WARN，不中断。

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

PAPER_KEYS = ("papers", "documents", "articles", "materials", "studies", "records")

DEFAULT_CHECKLIST = {
    "version": "methodology-checklist-v1",
    "domains": ["design", "sample", "control", "blinding", "statistics", "other"],
    "items": [
        {"checklist_id": "DS-01", "domain": "design", "prompt": "研究设计类型是否支持所述结论（随机化/分组来源明确）", "evidence_required": True},
        {"checklist_id": "SP-01", "domain": "sample", "prompt": "样本量与抽样方式是否合理（有无计算依据、代表性）", "evidence_required": True},
        {"checklist_id": "CO-01", "domain": "control", "prompt": "对照设置是否恰当（对照来源、可比性）", "evidence_required": True},
        {"checklist_id": "BL-01", "domain": "blinding", "prompt": "盲法是否实施与报告（对象、方式）", "evidence_required": True},
        {"checklist_id": "ST-01", "domain": "statistics", "prompt": "统计方法是否恰当（模型、效应量、CI、多重性）", "evidence_required": True},
        {"checklist_id": "OT-01", "domain": "other", "prompt": "伦理审批、利益冲突、资助来源是否报告", "evidence_required": True},
    ],
}

DEFAULT_RULES = {
    "version": "grading-rules-v1",
    "declared_at": None,
    "grade_map": {"adequate": "high", "concerns": "medium", "inadequate": "low",
                  "unreported": "uncertain", "unassessable": "uncertain", "not_applicable": None},
    "category_map": {"adequate": "none", "concerns": "design_flaw", "inadequate": "design_flaw",
                     "unreported": "reporting_gap", "unassessable": "none", "not_applicable": "none"},
    "penalty_map": {"adequate": 0, "concerns": 1, "inadequate": 3, "unreported": 1,
                    "unassessable": 0, "not_applicable": 0},
    "thresholds": {"low": [0, 1], "some_concerns": [2, 4], "high": [5, 9999]},
    "abstain_rule": "任一 unassessable 且 penalty 处于 low 档 → overall=uncertain；abstain≥2 → uncertain",
    "direction_rule": "负面条目存在 against_conclusion → against_conclusion；否则存在 favors_conclusion → favors_conclusion；否则 unclear",
}


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


def extract_papers(case):
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，文献清单未提取"
    for key in PAPER_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                title, did, ptype = "", "", "unknown"
                if isinstance(e, dict):
                    for tk in ("title", "name", "paper_title"):
                        if e.get(tk):
                            title = str(e[tk])[:120]
                            break
                    for ik in ("paper_id", "id", "doc_id"):
                        if e.get(ik):
                            did = str(e[ik])
                            break
                    ptype = str(e.get("paper_type") or e.get("study_type") or "unknown")
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"paper_id": did or "paper-%02d" % (i + 1), "doc_id": did,
                            "title": title, "paper_type": ptype,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含文献键（%s），请人工核对后填入 result.papers" % ",".join(PAPER_KEYS)


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
    case, case_id = {}, "unknown"

    # 定位标志：与 SKILL.md 同包才算挂载命中
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        problems.append("定位标志未命中（脚本未与 SKILL.md 同包），仍继续落盘")

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
    papers, paper_note = extract_papers(case)
    if paper_note:
        problems.append(paper_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "review_scope": {"question": None, "paper_types": None, "checklist_version": None},
            "checklist": dict(DEFAULT_CHECKLIST),
            "grading_rules": json.loads(json.dumps(DEFAULT_RULES)),
            "papers": [{"paper_id": p["paper_id"], "doc_id": p["doc_id"], "title": p["title"],
                        "paper_type": p["paper_type"], "source_ref": p["source_ref"],
                        "appraisals": [], "judged": False} for p in papers],
            "risk_summary": {"per_paper": [], "totals": {"papers": len(papers)},
                             "note": "grade_rollup.py 回填"},
            "coverage": {"papers_total": len(papers), "domains_required": 6, "items_total": 0,
                         "judged_items": 0, "abstained": 0, "design_flaws": 0,
                         "reporting_gaps": 0, "not_applicable": 0, "ratio": None},
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
                    "summary": "骨架已落盘，待逐条评价后回填"},
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

    # 分级口径模板（事前声明：任何复算前必须填写 declared_at，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rules_path = os.path.join(args.work_dir, "grading_rules.json")
        if not os.path.exists(rules_path):
            tpl = json.loads(json.dumps(DEFAULT_RULES))
            tpl["note"] = ("任何分级复算之前必须声明本口径（declared_at 必填），声明后禁止调整，"
                           "须与 result.grading_rules 一致。")
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("grading_rules 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | marker_hit=%s | contract 字段 %d 个 | 文件 %d 个 | 文献 %d 篇"
          % (case_id, marker_hit, len(fields), len(all_files), len(papers)))
    for p in papers:
        print("  paper: %s  %s" % (p["paper_id"], p["title"][:60]))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[build_skeleton] 骨架已写: %s" % out_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（已降级，请手工落骨架）: %s" % e)
        sys.exit(0)
