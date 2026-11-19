#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与数据集清单（stat-analysis-audit）。

读取 case.json 提取 output_contract 全部字段名与数据集/实验记录（datasets/
records/data/tables 等常见键），扫描输入目录补齐材料清单，写入骨架 result.json
（全部键，待回填）与 /app/work/claim_rules.json 解读口径模板（须在任何复算与
分级之前声明，之后禁止调整）。
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

DATA_KEYS = ("datasets", "records", "data", "tables", "studies", "materials")

DEFAULT_CHECKLIST = {
    "version": "stat-audit-checklist-v1",
    "domains": ["data_quality", "descriptive", "test_choice", "effect_ci",
                "interpretation", "causal_claim"],
    "items": [
        {"checklist_id": "DQ-01", "domain": "data_quality",
         "prompt": "缺失/重复/异常值的处理口径是否声明（删了多少、怎么判、单位口径）", "evidence_required": True},
        {"checklist_id": "DE-01", "domain": "descriptive",
         "prompt": "样本量、中心位置、离散程度与分位数是否给出且口径/单位明确", "evidence_required": True},
        {"checklist_id": "TC-01", "domain": "test_choice",
         "prompt": "检验方法是否与分布、样本量、设计结构匹配（正态性/方差齐性/组数/配对）", "evidence_required": True},
        {"checklist_id": "EC-01", "domain": "effect_ci",
         "prompt": "效应量与置信区间是否与检验匹配给出并解释方向", "evidence_required": True},
        {"checklist_id": "IR-01", "domain": "interpretation",
         "prompt": "结论强度是否与数据强度匹配（显著≠证明、统计显著≠实际意义）", "evidence_required": True},
        {"checklist_id": "CC-01", "domain": "causal_claim",
         "prompt": "观察性/相关性设计是否使用因果表述（相关≠因果）", "evidence_required": True},
    ],
}

DEFAULT_RULES = {
    "version": "claim-rules-v1",
    "declared_at": None,
    "grade_map": {"supported": "high", "concerns": "medium", "inadequate": "low",
                  "unreported": "uncertain", "unassessable": "uncertain", "not_applicable": None},
    "category_map": {"supported": "none", "concerns": "interpretation_risk",
                     "inadequate": "method_error", "unreported": "reporting_gap",
                     "unassessable": "none", "not_applicable": "none"},
    "penalty_map": {"supported": 0, "concerns": 1, "inadequate": 3, "unreported": 1,
                    "unassessable": 0, "not_applicable": 0},
    "thresholds": {"low": [0, 1], "some_concerns": [2, 4], "high": [5, 9999]},
    "strength_map": {"experimental": "causal", "quasi_experimental": "associative",
                     "observational": "associative", "correlational": "associative",
                     "unknown": "descriptive"},
    "causal_verbs": ["导致", "证明", "证明有效", "因果", "causes", "proves", "effect of",
                     "due to", "because of", "提高了", "提升了", "证明了"],
    "downgrade_rule": "claim_strength 超过 strength_map[design_type] 允许强度 ⇒ overclaim，"
                      "强度降级到允许值并登记；观察性设计 + 因果动词 ⇒ causal_ok=false",
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


def extract_datasets(case):
    out = []
    if not isinstance(case, dict):
        return out, "case.json 非对象，数据集清单未提取"
    for key in DATA_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                did, title, dtype = "", "", "unknown"
                if isinstance(e, dict):
                    for tk in ("dataset_id", "id", "name", "title"):
                        if e.get(tk):
                            did = str(e[tk])
                            break
                    title = str(e.get("title") or e.get("name") or e.get("description") or "")[:120]
                    dtype = str(e.get("design_type") or e.get("study_type") or "unknown")
                elif isinstance(e, str):
                    title = e[:120]
                out.append({"analysis_id": did or "ds-%02d" % (i + 1), "dataset_id": did,
                            "title": title, "design_type": dtype,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含数据集键（%s），请人工核对后填入 result.analyses" % ",".join(DATA_KEYS)


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
    datasets, ds_note = extract_datasets(case)
    if ds_note:
        problems.append(ds_note)
    all_files = scan_inputs(args.input_root)

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": None,
                            "seed": None, "hardware_note": None},
            "review_scope": {"question": None, "dataset_refs": None,
                             "unit_policy": None, "checklist_version": None},
            "checklist": dict(DEFAULT_CHECKLIST),
            "claim_rules": json.loads(json.dumps(DEFAULT_RULES)),
            "analyses": [{"analysis_id": d["analysis_id"], "dataset_id": d["dataset_id"],
                          "title": d["title"], "design_type": d["design_type"],
                          "source_ref": d["source_ref"],
                          "data_quality": {}, "descriptive": {}, "test_registration": {},
                          "claim": {}, "appraisals": [], "judged": False} for d in datasets],
            "stat_recompute": {"per_dataset": [], "all_match": None,
                               "note": "stat_recompute.py 回填"},
            "interpret_summary": {"per_analysis": [], "totals": {},
                                  "note": "interpret_rollup.py 回填"},
            "coverage": {"datasets_total": len(datasets), "domains_required": 6,
                         "items_total": 0, "judged_items": 0, "abstained": 0,
                         "method_errors": 0, "reporting_gaps": 0,
                         "interpretation_risks": 0, "not_applicable": 0, "ratio": None},
            "conflicts": [], "pending_review": [],
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

    # 解读口径模板（事前声明：任何复算/分级之前必须填写 declared_at，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rules_path = os.path.join(args.work_dir, "claim_rules.json")
        if not os.path.exists(rules_path):
            tpl = json.loads(json.dumps(DEFAULT_RULES))
            tpl["note"] = ("任何统计复算与解读分级之前必须声明本口径（declared_at 必填），"
                           "声明后禁止调整，须与 result.claim_rules 一致。")
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("claim_rules 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | marker_hit=%s | contract 字段 %d 个 | 文件 %d 个 | 数据集/记录 %d 组"
          % (case_id, marker_hit, len(fields), len(all_files), len(datasets)))
    for d in datasets:
        print("  dataset: %s  %s" % (d["analysis_id"], d["title"][:60]))
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
