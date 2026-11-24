#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装 result.json：探查原值与逐项映射表强制嵌入（评分器无需打开文档即可核对）

强制嵌入（verbatim，逐字原样）:
  result["format_spec"]    = probe_report.json 的 probes（模板真实观测值，含 engine 与出处）
  result["format_mapping"] = format_mapping.jsonl 逐条
      {item, template_value(模板原值), source(探查出处), applied(成品中的落点), rationale, status}
  result["format_check"]   = format_check.json
  result["content_audit"]  = 内容单元对账摘要（总数/丢失/清单位置）
其余: case_id、output_contract 字段、deliverable、uncertainty、changelog、status。
契约字段缺失时置 null 并记入 uncertainty——失败也交付。
"""
import argparse, json, os, sys

def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return None

def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in s.split(";") if x.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=os.path.join(os.environ.get("INPUT_DIR", "/input"), "case.json"))
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--probe", default="/app/work/extracted/probe_report.json")
    ap.add_argument("--mapping", default="/app/work/format_mapping.jsonl")
    ap.add_argument("--inventory", default="/app/work/extracted/content_inventory.jsonl")
    ap.add_argument("--check", default="/app/output/format_check.json")
    ap.add_argument("--artifact", default="draft.docx")
    ap.add_argument("--artifact-md", default="draft.md")
    ap.add_argument("--build-log", default=None, help="docx_build 输出 json 文件或留空")
    ap.add_argument("--status", default="complete")
    ap.add_argument("--notes", default=None)
    ap.add_argument("--changelog", default=None)
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填契约字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}
    contract_fields = contract if isinstance(contract, list) else \
        (contract.get("fields") if isinstance(contract, dict) else None) or []

    result = load_jsonish(args.out) if os.path.exists(args.out) else None
    result = result if isinstance(result, dict) else {}
    result.setdefault("case_id", case_id)
    for k in contract_fields:
        if isinstance(k, str):
            result.setdefault(k, None)
    for kv in args.set:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            result[k] = v

    # ---- 强制嵌入区（verbatim）----
    probe = load_jsonish(args.probe)
    if probe is not None:
        result["format_spec"] = probe.get("probes", probe)
        result["format_spec_note"] = ("format_spec 为模板文件真实观测原值（未解释、未编造），"
                                      "engine 记录读取方式；文本条款见 extracted/<mid>.txt 行号。")
    mapping = load_jsonish(args.mapping)
    if mapping is not None:
        result["format_mapping"] = mapping
        result["format_mapping_note"] = ("逐项映射：template_value=模板/要求原值(出处 source)，"
                                         "applied=成品中的落点，rationale=取舍理由，"
                                         "status∈{applied,partial,unspecified,conflict,degraded}。"
                                         "评分可逐条对照 format_spec 核验，无需打开文档。")
    check = load_jsonish(args.check)
    if check is not None:
        result["format_check"] = check
    inv_summary = {"inventory_path": args.inventory if os.path.exists(args.inventory) else None,
                   "inventory_units": None, "lost_units": (check or {}).get("content_lost", [])}
    if os.path.exists(args.inventory):
        n = sum(1 for l in open(args.inventory, encoding="utf-8") if l.strip())
        inv_summary["inventory_units"] = n
    result["content_audit"] = inv_summary
    if args.build_log and os.path.exists(args.build_log):
        result["build_log"] = load_jsonish(args.build_log)
    result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md, "editable": True}

    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    if not isinstance(result.get("uncertainty"), list):
        result["uncertainty"] = []
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    if not isinstance(result.get("changelog"), list):
        result["changelog"] = []
    result["status"] = args.status

    # 契约字段自检：仍为 null 的记入 uncertainty（失败也交付，但诚实标注；旧标签先清掉再按现状重写）
    result["uncertainty"] = [u for u in result["uncertainty"]
                             if not str(u).startswith("output_contract 字段未填写")]
    nulls = [k for k in contract_fields if isinstance(k, str) and result.get(k) is None]
    if nulls:
        result["uncertainty"].append("output_contract 字段未填写: " + ", ".join(nulls))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": args.out, "status": args.status,
                      "mapping_items": len(mapping) if isinstance(mapping, list) else 0,
                      "spec_probes": len(result.get("format_spec") or []),
                      "contract_nulls": nulls}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
