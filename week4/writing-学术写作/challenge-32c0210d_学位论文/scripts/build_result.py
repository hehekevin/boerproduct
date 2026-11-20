#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学位论文赛道收尾）
把 case_id、output_contract 原字段、主产物指针、证据映射、检查报告、修订记录、
状态与不确定性组装成 /app/output/result.json。已有骨架时只回填不覆盖。
支持 --embed-file/--embed-key 把主产物全文真正嵌入 result.json（可多次调用，每次刷新嵌入内容）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact thesis.docx --artifact-md thesis.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency cross_check.json --revision-log revision_log.jsonl \
      --embed-file thesis.md --embed-key deliverable_content \
      --status complete --notes '待核条目'
"""
import argparse, json, os, sys

def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        try:
            with open(p, encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        except Exception:
            return {"raw_path": p}

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
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--revision-log", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--embed-file", default=None, help="主产物全文文件路径，嵌入 result.json")
    ap.add_argument("--embed-key", default=None, help="嵌入字段名（默认 deliverable_content）")
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
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
    if args.embed_file and os.path.exists(args.embed_file):
        key = args.embed_key or "deliverable_content"
        try:
            with open(args.embed_file, encoding="utf-8") as f:
                content = f.read()
            if content.strip():
                result[key] = content
                result.setdefault("embed_info", {})["source"] = args.embed_file
                result["embed_info"]["chars"] = len(content)
        except Exception as e:
            result.setdefault("uncertainty", []).append("embed失败:%s" % e)
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    rl = load_jsonish(args.revision_log)
    if rl is not None:
        result["revision_log"] = rl
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd
    lg = load_jsonish(args.ledger)
    if lg is not None:
        result["fact_ledger_ref"] = args.ledger

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
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
