#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架（cite-support-check 引用支持判定，极简单点）。

读取 case.json 提取 case_id、output_contract 全部字段名与稿件结构
（manuscript/paper/document 等常见键下的 sections/text/references），扫描输入
目录补齐材料清单，写入骨架 result.json 与 /app/work/skill_marker.json 标志文件。
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
                    sid, name = None, None
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
    ms = extract_manuscript(case)
    if ms["note"]:
        problems.append(ms["note"])
    all_files = scan_inputs(args.input_root)
    marker_hit, marker_path = check_skill_marker(__file__)
    if not marker_hit:
        problems.append("技能标志文件未命中（%s），脚本可能未挂载在 /skills/weekly-skill" % (marker_path or "SKILL.md"))

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": "stdlib-only",
                            "seed": None, "hardware_note": None,
                            "skill_marker": {"hit": marker_hit, "path": marker_path}},
            "manuscript_overview": {"title": ms["title"], "sections": ms["sections"],
                                    "reference_count": ms["reference_count"]},
            "citation_scan": {"note": "由 citation_scan.py 回填：带引用标号结论句候选清单与引用标记比对"},
            "citation_checks": [],
            "coverage": {"total_checks": 0, "judged": 0, "state_counts": {},
                         "over_inference_count": 0, "note": "手动或校验器回填"},
            "unchecked": [],
            "steps": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
            "gain_evidence": {"available": False,
                              "reason": "极简单点策略：单一引用支持判定方向，增益层在预算 50% 跳过"},
            "efficiency": {"checker_runs": 0, "reproduce": "",
                           "note": "由 verify_check.py 回填"},
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

    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        marker_file = os.path.join(args.work_dir, "skill_marker.json")
        with open(marker_file, "w", encoding="utf-8") as f:
            json.dump({"skill": "cite-support-check", "case_id": case_id,
                       "marker_hit": marker_hit, "marker_path": marker_path}, f,
                      ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("skill_marker.json 写出失败: %s" % e)

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