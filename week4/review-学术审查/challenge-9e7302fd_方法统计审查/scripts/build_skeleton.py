#!/usr/bin/env python3
"""build_skeleton.py — Step 0 落骨架（num-consistency-audit 数字一致性审查）。

读取 case.json 提取 output_contract 全部字段名 + 稿件全文/章节结构，写入
result.json 骨架（全部业务键一个不缺），并生成 /app/work/skill_marker.json
（挂载标志，脚本定位校验用）。
三级容错：任何一级失败都降级产出可用骨架，退出码恒 0，绝不缺 result.json。

本题只做「结果报告审查——数字一致性」单方向；四方向（研究设计/变量定义/
统计方法匹配/样本量估算）记 out_of_scope 到 unchecked，不逐句读全文。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

MANUSCRIPT_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
SECTION_KEYS = ("sections", "chapters", "parts")
TABLE_KEYS = ("tables", "figure_captions", "captions", "figures")

OUT_OF_SCOPE = (
    ("facet:research_design", "out_of_scope：本题只做数字一致性，研究设计不审"),
    ("facet:variable_definition", "out_of_scope：本题只做数字一致性，变量定义不审"),
    ("facet:stat_method", "out_of_scope：本题只做数字一致性，统计方法选择不审"),
    ("facet:sample_power", "out_of_scope：本题只做数字一致性，样本量估算不审"),
)


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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


def _walk_strs(o, buf):
    """递归收集所有长度>=2 的字符串（正文全文/表格/图注都在手）。"""
    if isinstance(o, dict):
        for v in o.values():
            _walk_strs(v, buf)
    elif isinstance(o, list):
        for v in o:
            _walk_strs(v, buf)
    elif isinstance(o, str):
        if len(o.strip()) >= 2:
            buf.append(o)


def extract_manuscript(case):
    info = {"found": False, "title": None, "sections": [], "full_text": "",
            "full_text_chars": 0, "reference_count": None, "note": ""}
    if not isinstance(case, dict):
        info["note"] = "case.json 非对象"
        return info
    root = None
    for k in MANUSCRIPT_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            root = case[k]
            break
    if root is None:
        # 降级：取 output_contract 之外的整棵树
        root = {k: v for k, v in case.items() if k != "output_contract"}
    info["found"] = True
    if isinstance(root, dict):
        info["title"] = root.get("title")
        for sk in SECTION_KEYS:
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    if isinstance(s, dict):
                        sid = str(s.get("section_id") or s.get("id") or ("S%d" % (i + 1)))
                        name = str(s.get("name") or s.get("title") or "")
                        txt = s.get("text") or s.get("content") or ""
                    elif isinstance(s, str):
                        sid, name, txt = "S%d" % (i + 1), "", s
                    else:
                        continue
                    info["sections"].append({"section_id": sid, "name": name,
                                             "chars": len(str(txt))})
                break
        refs = root.get("references")
        if isinstance(refs, list):
            info["reference_count"] = len(refs)
    elif isinstance(root, list):
        for i, s in enumerate(root):
            txt = ""
            if isinstance(s, dict):
                sid = str(s.get("section_id", "S%d" % (i + 1)))
                name = str(s.get("name", ""))
                txt = s.get("text") or s.get("content") or ""
            else:
                sid, name, txt = "S%d" % (i + 1), "", str(s)
            info["sections"].append({"section_id": sid, "name": name, "chars": len(txt)})
    # 全文聚合（供 number_audit 复用，也写进骨架便于回证）
    buf = []
    _walk_strs(root, buf)
    info["full_text"] = "\n".join(buf)
    info["full_text_chars"] = len(info["full_text"])
    if not info["sections"]:
        info["note"] = "稿件未分段，sections 留空，全文通篇比对"
    return info


def scan_inputs(root):
    files = []
    try:
        for dirpath, _dn, filenames in os.walk(root):
            for fn in sorted(filenames):
                files.append(os.path.relpath(os.path.join(dirpath, fn), root).replace("\\", "/"))
    except Exception:
        pass
    return files


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args, _unknown = ap.parse_known_args()
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print("[build_skeleton] 参数解析失败（降级）: %s" % e)
        return 0

    problems = []
    case = {}
    case_id = "unknown"

    try:
        if os.path.exists(args.case):
            case = _load(args.case) or {}
        else:
            problems.append("case.json 不存在: %s" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败: %s" % e)
    if isinstance(case, dict):
        case_id = str(case.get("case_id") or "unknown")

    fields = contract_fields(case)
    ms = extract_manuscript(case)
    if ms.get("note"):
        problems.append(ms["note"])
    all_files = scan_inputs(args.input_root)

    # 挂载标志：脚本所在目录上两级（技能根）应有 SKILL.md
    marker_hit = False
    marker_path = ""
    try:
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        marker_path = os.path.join(skill_root, "SKILL.md")
        marker_hit = os.path.exists(marker_path)
    except Exception:
        pass

    skeleton = {}
    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": sys.version.split()[0], "packages": "stdlib-only",
                            "seed": None, "hardware_note": None,
                            "skill_marker": {"hit": marker_hit, "path": marker_path}},
            "manuscript_overview": {"title": ms.get("title"), "sections": ms.get("sections") or [],
                                    "full_text_chars": ms.get("full_text_chars") or 0,
                                    "reference_count": ms.get("reference_count")},
            "severity_rubric": {"levels": {"critical": None, "major": None, "minor": None},
                                "declared_at": None,
                                "note": "判定前必须声明，之后禁止调整"},
            "number_audits": [],
            "findings": [],
            "conflict_summary": {"conflicts_total": 0, "by_kind": {}, "by_severity": {},
                                 "note": "number_audit.py 回填"},
            "unchecked": [{"scope": s, "reason": r} for s, r in OUT_OF_SCOPE],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
            "gain_evidence": {"available": False, "reason": "增益层预算过半降级；built after Step 4"},
            "efficiency": {"wall_clock_seconds_total": 0.0, "checker_runs": 0,
                           "reproduce": "python3 scripts/number_audit.py --result /app/output/result.json --case /input/case.json --input-root /input --emit-into"},
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待数字提取与交叉比对后回填"},
                    "changelog": [{"step": "step0", "change": "build_skeleton 落骨架",
                                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")}]}
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
    written = False
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
        written = True
    except Exception as e:
        problems.append("骨架写出失败 %s: %s，转备用路径" % (out_path, e))
        try:
            os.makedirs(args.work_dir or ".", exist_ok=True)
            fallback = os.path.join(args.work_dir or ".", "result.skeleton.json")
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(skeleton, f, ensure_ascii=False, indent=1)
            problems.append("骨架已写备用路径: %s" % fallback)
        except Exception as e2:
            problems.append("备用写盘也失败: %s" % e2)

    # 标志文件 work/skill_marker.json（number_audit/verify 的定位校验 + 严重度台账）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        marker = {"skill_root": marker_path, "skill_hit": marker_hit,
                  "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "case_id": case_id}
        with open(os.path.join(args.work_dir or ".", "skill_marker.json"), "w",
                  encoding="utf-8") as f:
            json.dump(marker, f, ensure_ascii=False, indent=1)
        with open(os.path.join(args.work_dir or ".", "severity_rubric.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"declared_at": None,
                       "levels": {"critical": None, "major": None, "minor": None},
                       "note": "判定前声明，之后禁止调整"}, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("work 目录标志/台账写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | contract %d | files %d | sections %d | chars %d"
          % (case_id, len(fields), len(all_files), len(ms.get("sections") or []),
             ms.get("full_text_chars") or 0))
    for p in problems:
        print("  WARN: %s" % p)
    print("[build_skeleton] 骨架已写: %s (marker_hit=%s, written=%s)" % (out_path, marker_hit, written))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[build_skeleton] 未预期异常（降级，exit 0）: %s" % e)
        sys.exit(0)