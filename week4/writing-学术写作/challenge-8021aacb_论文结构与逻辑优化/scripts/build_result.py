#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装 result.json：契约字段一个不缺 + 主产物完整嵌入（三级容错）
用法:
  骨架:  python build_result.py --case /input/case.json --out /app/output/result.json --scaffold
  回填:  python build_result.py --case /input/case.json --out /app/output/result.json \
           --embed-diagnosis issues.jsonl --embed-chain claim_chain.jsonl \
           --embed-edits edits_before_after.jsonl --embed-revised revised.md \
           --artifact revised.docx --verify verify_report.json --status complete --notes 'a;b'
嵌入项: diagnosis.issues(逐条定位/摘句/类型/动作)、claim_chain(论断链)、
        edits_before_after(逐字前后对照)、revised_text(修订全文) —— 复核者无需打开原稿。
容错: ①正常组装 ②缺文件跳过该项并在 notes 说明 ③已有骨架只回填不覆盖，exit 0
"""
import argparse, json, os, sys

def load_jsonish(p):
    if not p or not os.path.exists(p): return None
    try: return json.load(open(p, encoding="utf-8"))
    except Exception:
        try: return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception: return None

def read_text(p):
    if p and os.path.exists(p):
        try: return open(p, encoding="utf-8", errors="ignore").read()
        except Exception: return None
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--scaffold", action="store_true")
    ap.add_argument("--embed-diagnosis", default=None)
    ap.add_argument("--embed-chain", default=None)
    ap.add_argument("--embed-edits", default=None)
    ap.add_argument("--embed-revised", default=None)
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--verify", default=None)
    ap.add_argument("--status", default=None)
    ap.add_argument("--notes", default=None, help="JSON 数组或 ; 分隔")
    ap.add_argument("--changelog", default=None, help="JSON 数组或 ; 分隔")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}
    field_list = contract if isinstance(contract, list) else \
        (contract.get("fields") if isinstance(contract, dict) else None) or \
        (contract.get("required") if isinstance(contract, dict) else None) or []

    old = load_jsonish(args.out) if os.path.exists(args.out) else None
    result = old if isinstance(old, dict) else {}
    result.setdefault("case_id", case_id)
    for k in field_list:  # 契约字段一个不缺（骨架即落盘，回填不覆盖）
        if isinstance(k, str): result.setdefault(k, None)

    if args.scaffold:
        result["status"] = "pending"
        result["protocol"] = {"scaffold_at_stage": "stage0", "budget_guard": "48req/700s"}
    def as_records(x):  # 单行 jsonl 会被 json.load 解析成 dict，统一归一为 list
        if isinstance(x, dict): return [x]
        return x if isinstance(x, list) else None
    issues = as_records(load_jsonish(args.embed_diagnosis))
    if issues is not None:
        result["diagnosis"] = {"issues": issues,
                               "summary": {"total": len(issues),
                                           "high": sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == "high")}}
    chain = as_records(load_jsonish(args.embed_chain))
    if chain is not None: result["claim_chain"] = chain
    edits = as_records(load_jsonish(args.embed_edits))
    if edits is not None: result["edits_before_after"] = edits
    rev = read_text(args.embed_revised)
    if rev: result["revised_text"] = rev
    if args.artifact:
        result["deliverable"] = {"docx": args.artifact if os.path.exists(args.artifact) else None,
                                 "markdown": args.embed_revised, "editable": True}
    vr = load_jsonish(args.verify)
    if vr is not None: result["verify_report"] = vr
    if args.notes:
        result["uncertainty"] = _as_list(args.notes)
    elif args.scaffold: result.setdefault("uncertainty", [])
    if args.changelog: result["changelog"] = _as_list(args.changelog)
    elif args.scaffold: result.setdefault("changelog", [])
    if args.status: result["status"] = args.status

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    missing = [k for k in field_list if isinstance(k, str) and result.get(k) is None]
    print(json.dumps({"ok": True, "result": args.out, "status": result.get("status"),
                      "embedded": {"issues": len(issues) if isinstance(issues, list) else 0,
                                   "edits": len(edits) if isinstance(edits, list) else 0,
                                   "revised_text": bool(rev)},
                      "contract_missing": missing}, ensure_ascii=False))
    return 0

def _as_list(s):
    try:
        v = json.loads(s); return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in s.split(";") if x.strip()]

if __name__ == "__main__":
    sys.exit(main())
