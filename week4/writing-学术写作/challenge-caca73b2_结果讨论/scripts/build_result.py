#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（结果与讨论章节写作 · 统一收尾）
把 case_id、output_contract 原字段、主产物（指针 + 全文嵌入）、证据映射、数字-来源核对表、
讨论结论溯源表、检查报告、状态与不确定性组装成 /app/output/result.json。
已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact results_discussion.docx --artifact-md results_discussion.md \
      --embed-md /app/output/results_discussion.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --trace-audit trace_audit.json --source-table number_source_table.json \
      --dclaims dclaims.jsonl --consistency check_report.json --render previews/render_log.json \
      --status complete --notes '[待核条目...]'
字段均可缺省；output_contract 中的字段若无法填写，保持 null 并在 uncertainty 说明。
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
            return {"raw_path": p}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--embed-md", default=None, help="主产物 md 全文嵌入 result.json（主产物完整随行）")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--trace-audit", default=None, help="trace_audit.json（核对表摘要+交叉引用+讨论溯源）")
    ap.add_argument("--source-table", default=None, help="number_source_table.json 数字-来源逐条核对表")
    ap.add_argument("--dclaims", default=None, help="dclaims.jsonl 讨论结论溯源表")
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    # 契约字段原样保留（值可为 null，后面 --set 或模型回填）
    for k in contract if isinstance(contract, list) else (contract.get("fields") or contract.get("required") or []):
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

    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md or None,
                                 "editable": True}
    # 主产物全文嵌入：即使预览/文件丢失，result.json 单文件即可复核完整章节文本
    if args.embed_md and os.path.exists(args.embed_md):
        try:
            text = open(args.embed_md, encoding="utf-8").read()
            if text.strip():
                result["main_text_markdown"] = text
        except Exception as e:
            result.setdefault("uncertainty", []).append(f"main_text embed failed: {e}")
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    ta = load_jsonish(args.trace_audit)
    if ta is not None:
        result["trace_audit"] = ta
    st = load_jsonish(args.source_table)
    if st is not None:
        result["number_source_table"] = st
    dc = load_jsonish(args.dclaims)
    if dc is not None:
        result["discussion_claims"] = dc
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd
    lg = load_jsonish(args.ledger)
    if lg is not None:
        result["fact_ledger_ref"] = args.ledger

    def as_list(s):
        if not s: return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]
    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    else:
        result.setdefault("uncertainty", [])
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        result.setdefault("changelog", [])
    result["status"] = args.status

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "embedded_main_text": bool(result.get("main_text_markdown")),
                      "number_source_rows": len(result["number_source_table"]) if isinstance(result.get("number_source_table"), list) else 0,
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
