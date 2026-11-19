#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与稿件结构清单（argchain-review）。

读取 case.json 提取 output_contract 全部字段名与稿件结构（manuscript/paper/
document 等常见键下的 sections/text），扫描输入目录补齐材料清单，写入骨架
result.json（全部键，待回填）与 /app/work/rubrics.json 口径三合一模板
（severity_rubric 三级判据 + issue_taxonomy 六类问题 + strength_scale 双侧
强度标尺；须在任何判定之前声明，之后禁止调整）。
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

MANUSCRIPT_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
SECTION_KEYS = ("sections", "chapters", "parts")

# 六分面（覆盖审计维度）
FACETS = (
    ("argument_chain", "论证链：假设→前提→推理→结论逐环是否断裂或循环"),
    ("strength_match", "强度匹配：结论强度与证据等级是否相称"),
    ("rebuttal_coverage", "反驳与局限：替代解释、反例、局限性是否覆盖"),
    ("cross_section", "章节衔接：引言承诺/方法结果口径/摘要与结论一致"),
    ("fact_check", "事实核验：数据/表述在摘要、正文、图表间是否一致"),
    ("integrity_norms", "学术规范：声明齐备性、术语一致、格式与可发表性"),
)

# 六类逻辑问题（issue_taxonomy，判定前须声明）
TAXONOMY = (
    ("broken_chain", "断链：前提与结论之间缺必要推理环节或隐含假设未交代"),
    ("circular_reasoning", "循环论证：结论（或其等价改写）被用作前提"),
    ("correlation_causation", "因果相关混淆：仅相关/观察证据却做因果表述"),
    ("over_extrapolation", "外推超界：超出样本、场景或时限的推广"),
    ("strength_mismatch", "强度不匹配：结论强度超出证据等级"),
    ("missing_rebuttal", "反驳缺失：对明显替代解释或已知反例无讨论且未声明局限"),
)

# 强度标尺（strength_scale，判定前须声明）
EVIDENCE_LEVELS = (
    ("E3", "对照/实验/定量复现证据"),
    ("E2", "观察性相关或单点定量证据"),
    ("E1", "个案、转述或权威断言"),
    ("E0", "无实证"),
)
CLAIM_LEVELS = (
    ("C3", "因果断言或普遍推广"),
    ("C2", "限定条件下的相关结论"),
    ("C1", "假说性表述"),
)


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


def extract_manuscript(case):
    """从 case.json 常见键提取稿件结构与统计线索（只记结构，不复制全文）。"""
    info = {"found": False, "title": None, "sections": [], "reference_count": None, "note": ""}
    if not isinstance(case, dict):
        info["note"] = "case.json 非对象，稿件结构未提取"
        return info
    root = None
    for k in MANUSCRIPT_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            root = case[k]
            break
    if root is None:
        info["note"] = "case.json 未含稿件键（%s），请人工核对稿件实际位置" % ",".join(MANUSCRIPT_KEYS)
        return info
    info["found"] = True
    if isinstance(root, dict):
        info["title"] = root.get("title") or None
        for sk in SECTION_KEYS:
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    sid = None
                    name = None
                    if isinstance(s, dict):
                        sid = s.get("section_id") or s.get("id") or ("S%d" % (i + 1))
                        name = s.get("name") or s.get("title") or None
                    elif isinstance(s, str):
                        sid, name = "S%d" % (i + 1), s[:40]
                    info["sections"].append({"section_id": str(sid), "name": str(name or ""),
                                             "source_ref": "manuscript.%s[%d]" % (sk, i)})
                break
        refs = root.get("references")
        if isinstance(refs, list):
            info["reference_count"] = len(refs)
    elif isinstance(root, list):
        for i, s in enumerate(root):
            sid = s.get("section_id", "S%d" % (i + 1)) if isinstance(s, dict) else "S%d" % (i + 1)
            info["sections"].append({"section_id": str(sid), "name": "", "source_ref": "manuscript[%d]" % i})
    if not info["sections"]:
        info["note"] = "稿件未分段（连续文本），sections 留空，按全文通读审查"
    return info


def scan_inputs(root):
    all_files = []
    try:
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                all_files.append(os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/"))
    except Exception:
        pass
    return all_files


def check_skill_marker(script_file):
    """定位标志文件校验式命中：以脚本所在目录上两级（技能根）的 SKILL.md 为标志。"""
    try:
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(script_file)))
        marker = os.path.join(skill_root, "SKILL.md")
        return os.path.exists(marker), marker
    except Exception:
        return False, ""


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
    ms = extract_manuscript(case)
    if ms["note"]:
        problems.append(ms["note"])
    all_files = scan_inputs(args.input_root)
    marker_hit, marker_path = check_skill_marker(__file__)
    if not marker_hit:
        problems.append("技能标志文件未命中（%s），脚本可能未挂载在 /skills/weekly-skill" % (marker_path or "SKILL.md"))

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": "stdlib-only",
                            "seed": None, "hardware_note": None,
                            "skill_marker": {"hit": marker_hit, "path": marker_path}},
            "manuscript_overview": {"title": ms["title"], "sections": ms["sections"],
                                    "reference_count": ms["reference_count"]},
            "severity_rubric": {"levels": {"critical": None, "major": None, "minor": None},
                                "declared_at": None,
                                "note": "任何逐条判定之前必须声明三级口径，之后禁止调整"},
            "issue_taxonomy": {"types": {k: None for k, _v in TAXONOMY},
                               "declared_at": None,
                               "note": "六类问题口径判定前声明；issue_type 必居其一"},
            "strength_scale": {"evidence_levels": {k: None for k, _v in EVIDENCE_LEVELS},
                               "claim_levels": {k: None for k, _v in CLAIM_LEVELS},
                               "rule": None, "declared_at": None,
                               "note": "双侧强度标尺判定前声明；C3须E3，C2须≥E2，E0不得支撑confirmed结论"},
            "suppression_rules": [
                {"rule_id": "FP-01", "text": "作者有意设置的对照组/明确标注的假设情形不是自相矛盾"},
                {"rule_id": "FP-02", "text": "转述他人观点（他人主张）不算作者自身缺陷"},
                {"rule_id": "FP-03", "text": "学科写作惯例与期刊格式差异（篇幅内省略、惯用转承语）不算缺陷"},
            ],
            "facets": {k: v for k, v in FACETS},
            "argument_chains": [],
            "findings": [],
            "strength_matches": [],
            "suppressed": [],
            "pending_review": [],
            "clearances": [],
            "coverage": {"total_sections": len(ms["sections"]), "sections_with_findings": 0,
                         "total_findings": 0, "judged": 0, "confirmed": 0, "pending": 0,
                         "suppressed": 0, "facet_counts": {}, "issue_type_counts": {},
                         "category_counts": {}, "severity_counts": {}, "per_section": {},
                         "note": "chain_audit.py 回填"},
            "unchecked": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待逐条审查后回填"},
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

    # 口径三合一模板（事前声明：判定前必须填写，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rub_path = os.path.join(args.work_dir, "rubrics.json")
        if not os.path.exists(rub_path):
            with open(rub_path, "w", encoding="utf-8") as f:
                json.dump({"note": "任何逐条判定之前必须声明三口径；声明后禁止调整，"
                                   "须与 result.severity_rubric / issue_taxonomy / "
                                   "strength_scale 一致。",
                           "severity_rubric": {"declared_at": None,
                                               "levels": {"critical": None, "major": None, "minor": None}},
                           "issue_taxonomy": {"declared_at": None,
                                              "types": {k: None for k, _v in TAXONOMY}},
                           "strength_scale": {"declared_at": None,
                                              "evidence_levels": {k: None for k, _v in EVIDENCE_LEVELS},
                                              "claim_levels": {k: None for k, _v in CLAIM_LEVELS},
                                              "rule": None}}, f,
                          ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("rubrics.json 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract 字段 %d 个 | 输入文件 %d 个 | 章节 %d 个 | 参考文献 %s"
          % (case_id, len(fields), len(all_files), len(ms["sections"]),
             ms["reference_count"] if ms["reference_count"] is not None else "未知"))
    for s in ms["sections"]:
        print("  section: %s  %s" % (s["section_id"], s["name"]))
    for p in problems:
        print("  WARN: %s" % p)
    print("[build_skeleton] 骨架已写: %s（标志文件命中=%s）" % (out_path, marker_hit))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（已降级，请手工落骨架）: %s" % e)
        sys.exit(0)
