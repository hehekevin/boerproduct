#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_skeleton.py — 第0步：先写 result.json 骨架（契约全字段一个不缺）。

用法:
  python3 build_skeleton.py --case /input/case.json --out /app/output/result.json

行为:
  1. 读 case.json，抄 case_id 与 output_contract 全部键名（以实际声明为准）。
  2. 写骨架：契约键→"unknown"、status=partial、异常登记 exceptions=[]，
     并预留本包各脚本专属键（键归属唯一，防多脚本写同一键）：
       chart_selection  ← chart_select.py（agent 回填）
       verify_report    ← verify_check.py（agent 回填）
       render_evidence  ← render_export.py 输出（agent 回填）
       gain_evidence / efficiency ← gain_probe.py --write
       schema_report    ← schema_guard.py --write
  3. result.json 已存在时为合并模式：只填仍为 unknown/缺失的键，不覆盖已产出内容。
退出码恒 0；成败结论写进 stdout JSON。
"""
import argparse, json, os, sys

# CHARTVIZ-MARKER: build_skeleton

SCRIPT_OWNED_KEYS = ["chart_selection", "verify_report", "render_evidence",
                     "gain_evidence", "efficiency", "schema_report",
                     "compliance_checks", "exceptions", "pipeline_log"]


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:
        return None, str(e)


def build_skeleton(case_path, existing):
    case, err = load_json(case_path)
    contract, case_id = [], "unknown"
    if isinstance(case, dict):
        case_id = case.get("case_id", case_id)
        c = case.get("output_contract") or case.get("contract") or []
        if isinstance(c, dict):
            contract = sorted(c.keys())
        elif isinstance(c, list):
            contract = [x.get("key") if isinstance(x, dict) else str(x) for x in c]
    elif err:
        contract = []
    skeleton = {"case_id": case_id, "status": "partial"}
    for k in contract:
        if k not in SCRIPT_OWNED_KEYS and k not in ("status", "case_id"):
            skeleton[k] = "unknown"  # status/case_id 由骨架固定语义，契约同名键不覆盖
    for k in SCRIPT_OWNED_KEYS:
        if k in ("exceptions", "compliance_checks", "pipeline_log"):
            skeleton.setdefault(k, [])
        else:
            skeleton.setdefault(k, {})
    skeleton["exceptions"].append({
        "item": "skeleton_created",
        "detail": "契约键从 case.json 实际声明抄录；未能解析的输入字段如实留 unknown",
        "input_parse_error": err or ""})
    if isinstance(existing, dict):
        merged = dict(skeleton)
        merged.update({k: v for k, v in existing.items() if v not in (None, "unknown", [], {})})
        for k in contract:
            if merged.get(k) in (None, "unknown"):
                merged[k] = "unknown"
        merged["case_id"] = case_id
        return merged, case_id, contract
    return skeleton, case_id, contract


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    args = ap.parse_args()
    existing = None
    if os.path.exists(args.out):
        existing, _ = load_json(args.out)
    skeleton, case_id, contract = build_skeleton(args.case, existing)
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
        written, note = True, "ok"
    except Exception as e:
        written, note = False, str(e)
    print(json.dumps({"ok": written, "note": note, "case_id": case_id,
                      "contract_keys": contract, "status": skeleton["status"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
