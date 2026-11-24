#!/usr/bin/env python3
"""build_skeleton.py — Step 0 自动落骨架与步骤图模板（multi-step-analysis）。

读取 case.json 提取 output_contract 全部字段名与待分析数据表，扫描输入目录
补齐材料清单，写入骨架 result.json（全部键，待回填）与 /app/work/analysis_plan.json
步骤图台账（须在任何执行之前声明，之后禁止调整）。三级容错：任何一级失败都
降级产出可用骨架，绝不崩溃、绝不缺 result.json。

定位标志：脚本校验自身与 SKILL.md 同包（../SKILL.md 存在）才视为挂载命中，
未命中时照常落盘但打印 WARN，不中断。
防 isalpha 陷阱：step_id 用显式 ASCII 白名单校验，不用 str.isalpha()
（该函数对汉字返回 True，会把「步骤一」误判成合法标识符）。

用法：
    python3 build_skeleton.py --case /input/case.json --input-root /input \
        --out /app/output/result.json --work-dir /app/work
退出码恒为 0（失败以 problems 报告，骨架仍写出）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TABLE_KEYS = ("tables", "datasets", "data", "records", "samples", "observations")

DEFAULT_PLAN = {
    "version": "analysis-plan-v1",
    "declared_at": None,
    "steps": [
        {"step_id": "S1", "name": "导入与字段核对", "depends_on": [],
         "inputs": ["raw_table"], "outputs": ["schema_report"],
         "checkpoint": "字段名/类型/单位核对，产出字段映射"},
        {"step_id": "S2", "name": "清洗（缺失/异常/重复）", "depends_on": ["S1"],
         "inputs": ["raw_table", "schema_report"], "outputs": ["clean_table", "clean_log"],
         "checkpoint": "行数守恒：原始行数=保留+填补+剔除，规则逐条登记"},
        {"step_id": "S3", "name": "统计检验", "depends_on": ["S2"],
         "inputs": ["clean_table"], "outputs": ["stats_result"],
         "checkpoint": "检验前提（分布/样本量）+ 关键数值复算"},
        {"step_id": "S4", "name": "可视化", "depends_on": ["S3"],
         "inputs": ["stats_result"], "outputs": ["figure_spec"],
         "checkpoint": "图型选择与坐标轴/聚合层级和底层数据一致"},
        {"step_id": "S5", "name": "报告生成", "depends_on": ["S3", "S4"],
         "inputs": ["stats_result", "figure_spec"], "outputs": ["report"],
         "checkpoint": "正文数字与 stats_result 同源，可回算"},
    ],
}

# step_id 只允许大写字母+数字（ASCII），杜绝 isalpha 汉字陷阱
STEP_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")


def valid_step_id(sid):
    return bool(isinstance(sid, str) and STEP_ID_RE.match(sid))


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


def extract_tables(case):
    out, note = [], ""
    if not isinstance(case, dict):
        return out, "case.json 非对象，数据表清单未提取"
    for key in TABLE_KEYS:
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                tid, nrows, cols = "table-%02d" % (i + 1), None, []
                if isinstance(e, dict):
                    tid = str(e.get("table_id") or e.get("id") or tid)
                    rows = e.get("rows") or e.get("records") or []
                    if isinstance(rows, list):
                        nrows = len(rows)
                        if rows and isinstance(rows[0], dict):
                            cols = sorted(rows[0].keys())
                out.append({"table_id": tid, "source_ref": "%s[%d]" % (key, i),
                            "n_rows": nrows, "columns": cols})
            return out, ""
    return out, "case.json 未含数据表键（%s），请人工核对后登记 material_gaps" % ",".join(TABLE_KEYS)


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
    tables, table_note = extract_tables(case)
    if table_note:
        problems.append(table_note)
    all_files = scan_inputs(args.input_root)

    try:
        inner = {
            "material_gaps": [],
            "environment": {"python_version": None, "packages": "stdlib-only",
                            "seed": None, "hardware_note": None},
            "task_scope": {"question": None, "table_ids": [t["table_id"] for t in tables],
                           "plan_version": DEFAULT_PLAN["version"]},
            "plan": json.loads(json.dumps(DEFAULT_PLAN)),
            "dag": {"nodes": [], "edges": [], "acyclic": None, "computed_by": "pipeline_run.py"},
            "steps": [],
            "fallbacks": [],
            "middle_checks": {"total": 0, "passed": 0, "failed": 0, "pass_rate": None,
                              "computed_by": "verify_check.py"},
            "artifacts": {"clean_summary": None, "stats_result": None,
                          "figure_spec": None, "report_markdown": None},
            "conflicts": [],
            "pending_review": [],
            "run_status": {"state": None, "reason": None, "manual_takeover": []},
            "verdict": None,
            "verdict_basis": None,
        }
        skeleton = {"case_id": case_id, "status": "partial", "result": inner,
                    "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                    "conflicts": [], "human_review": [],
                    "summary": "骨架已落盘，待按步骤图执行后回填"},
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

    # 步骤图台账（事前声明：任何执行前必须填写 declared_at，之后禁止调整）
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
        plan_path = os.path.join(args.work_dir, "analysis_plan.json")
        if not os.path.exists(plan_path):
            tpl = json.loads(json.dumps(DEFAULT_PLAN))
            tpl["note"] = ("步骤图须在任何执行之前声明本台账（declared_at 必填），"
                           "声明后禁止调整，须与 result.plan 一致。")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(tpl, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("analysis_plan 模板写出失败: %s" % e)

    print("[build_skeleton] case_id=%s | marker_hit=%s | contract 字段 %d 个 | 文件 %d 个 | 表 %d 张"
          % (case_id, marker_hit, len(fields), len(all_files), len(tables)))
    for t in tables:
        print("  table: %s rows=%s cols=%s" % (t["table_id"], t["n_rows"], ",".join(t["columns"])[:60]))
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
