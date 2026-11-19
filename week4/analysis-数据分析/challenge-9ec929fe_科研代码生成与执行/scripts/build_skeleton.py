#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与数据清单（sci-code-exec）。

读取 case.json 提取 output_contract 全部字段名、数据集（csv_inline / file /
sqlite 三种形态）与任务要求（requirements），扫描输入目录补齐材料清单，写入
骨架 result.json（全部键，待回填）与 /app/work/cleaning_rules.json 清洗口径
模板（须在任何计算之前声明 declared_at，之后禁止调整）。
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

DATASET_KEYS = ("datasets", "data", "tables", "data_files", "sources")
REQ_KEYS = ("requirements", "tasks", "questions", "requirements_list")

DEFAULT_RULES = {
    "version": "cleaning-rules-v1",
    "declared_at": None,
    "rules": [
        {"rule_id": "CR-01", "action": "dropna", "target_field": None,
         "params": {}, "rationale": "缺失值剔除并在 anomalies 登记，不按 0 参与统计"},
        {"rule_id": "CR-02", "action": "dedup", "target_field": None,
         "params": {"keep": "first"}, "rationale": "按主键去重，保留首条"},
    ],
    "note": ("任何计算之前必须声明本口径（declared_at 必填），声明后禁止调整；"
             "每条 stats 的 rule_refs 须指向本表规则。"),
}

DEFAULT_FIELDS = {
    "material_gaps": [],
    "environment": {"python_version": None, "packages": "stdlib-only",
                    "seed": None, "hardware_note": None},
    "task_scope": {"question": None, "dataset_names": [], "analysis_kind": None},
    "data_dictionary": {"version": None, "fields": []},
    "cleaning_rules": {"version": "cleaning-rules-v1", "declared_at": None, "rules": []},
    "requirements": [],
    "code_artifacts": [],
    "coverage_map": [],
    "steps": [],
    "execution_traces": [],
    "stats": [],
    "recompute": {"computed_by": "recompute.py", "data_sources": [], "per_stat": [],
                  "mismatches": [], "verdict": None, "note": "recompute.py 回填"},
    "anomalies": [],
    "coverage": {"requirements_total": 0, "covered": 0, "partial": 0, "uncovered": 0,
                 "stats_total": 0, "stats_recomputed": 0, "recompute_pass": False,
                 "anomalies_registered": 0, "ratio": None},
    "conflicts": [],
    "pending_review": [],
    "run_status": {"state": None, "reason": None, "manual_takeover": []},
    "verdict": None,
    "verdict_basis": None,
    "gain_evidence": {},
    "efficiency": {},
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
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，数据集未提取"
    for key in DATASET_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                name, fmt, path, table, ncols = "ds-%02d" % (i + 1), "unknown", None, None, None
                if isinstance(e, dict):
                    name = str(e.get("name") or e.get("id") or name)
                    fmt = str(e.get("format") or ("sqlite" if e.get("table") else "unknown"))
                    path = e.get("path") or e.get("file")
                    table = e.get("table")
                    content = e.get("content")
                    if fmt == "csv_inline" and isinstance(content, str):
                        head = content.splitlines()
                        ncols = len(head[0].split(",")) if head else None
                elif isinstance(e, str):
                    fmt, path = "file", e
                out.append({"dataset_id": name, "format": fmt, "path": path,
                            "table": table, "columns_hint": ncols,
                            "source_ref": "%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含数据集键（%s），请人工核对后填入 task_scope" % ",".join(DATASET_KEYS)


def extract_requirements(case):
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，要求清单未提取"
    for key in REQ_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                rid, text = "R%d" % (i + 1), ""
                if isinstance(e, dict):
                    rid = str(e.get("req_id") or e.get("id") or rid)
                    text = str(e.get("text") or e.get("description") or "")[:200]
                elif isinstance(e, str):
                    text = e[:200]
                out.append({"req_id": rid, "text": text, "source": "case.json#%s[%d]" % (key, i)})
            return out, ""
    return out, "case.json 未含要求键（%s），请从题面 task.md 抄录 requirements" % ",".join(REQ_KEYS)


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
    datasets, ds_note = extract_datasets(case)
    if ds_note:
        problems.append(ds_note)
    reqs, req_note = extract_requirements(case)
    if req_note:
        problems.append(req_note)
    all_files = scan_inputs(args.input_root)

    # 二级：组装骨架（output_contract 键 + 本题业务键，一个不缺）
    try:
        inner = json.loads(json.dumps(DEFAULT_FIELDS))
        inner["requirements"] = reqs
        inner["coverage"]["requirements_total"] = len(reqs)
        inner["task_scope"]["dataset_names"] = [d["dataset_id"] for d in datasets]
        q = case.get("task") or case.get("question") if isinstance(case, dict) else None
        if isinstance(q, str):
            inner["task_scope"]["question"] = q[:300]
        if isinstance(case, dict) and isinstance(case.get("data_dictionary"), dict):
            inner["data_dictionary"] = case["data_dictionary"]
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待声明口径、生成代码并回填"},
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

    # 清洗口径模板（事前声明：任何计算之前必须填写 declared_at，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        rules_path = os.path.join(args.work_dir, "cleaning_rules.json")
        if not os.path.exists(rules_path):
            tpl = json.loads(json.dumps(DEFAULT_RULES))
            with open(rules_path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("cleaning_rules 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | marker_hit=%s | contract 字段 %d 个 | 文件 %d 个 | 数据集 %d 个 | 要求 %d 条"
          % (case_id, marker_hit, len(fields), len(all_files), len(datasets), len(reqs)))
    for d in datasets:
        print("  dataset: %s (%s%s)" % (d["dataset_id"], d["format"],
              ", table=%s" % d["table"] if d["table"] else ""))
    for r in reqs:
        print("  req: %s  %s" % (r["req_id"], r["text"][:60]))
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
