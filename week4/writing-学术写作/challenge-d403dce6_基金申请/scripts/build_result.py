#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（基金申请书赛道统一收尾）
把 case_id、output_contract 原字段、主产物指针、证据映射、检查报告、状态与不确定性
组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact grant.docx --artifact-md grant.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency align_check.json --render previews/render_log.json \
      --status complete \
      --embed-file /app/output/grant.md --embed-key deliverable_content
逐章回填: 每写完一章即可
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --embed-file /app/work/chapters/ch01.md --embed-key deliverable_content --append
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
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--status", default=None, help="缺省时保留已有 status（骨架早期状态不被覆盖）")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填字段")
    ap.add_argument("--embed-file", default=None, help="把该文件全文嵌入指定键（主产物内嵌）")
    ap.add_argument("--embed-key", default="deliverable_content")
    ap.add_argument("--append", action="store_true", help="嵌入内容追加到已有键值之后（逐章回填）")
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
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd
    lg = load_jsonish(args.ledger)
    if lg is not None:
        result["fact_ledger_ref"] = args.ledger

    # 主产物内嵌（支持逐章追加，防 16384 截断：一章一调）
    if args.embed_file:
        if os.path.exists(args.embed_file):
            try:
                content = open(args.embed_file, encoding="utf-8").read()
                old_v = result.get(args.embed_key)
                if args.append and isinstance(old_v, str) and old_v:
                    result[args.embed_key] = old_v.rstrip() + "\n\n" + content
                else:
                    result[args.embed_key] = content
                result.setdefault("embedded_files", []).append(args.embed_file)
            except Exception as e:
                result.setdefault("uncertainty", []).append(
                    f"embed_failed: {args.embed_file}: {str(e)[:120]}")
        else:
            result.setdefault("uncertainty", []).append(
                f"embed_missing: {args.embed_file}")

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
    if args.status:  # 未显式给 status 时保留已有值（诚实状态不被无意覆盖）
        result["status"] = args.status
    elif "status" not in result:
        result["status"] = "partial"

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": result.get("status"),
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 三级容错：即使自身崩溃也不让输出目录失去 result.json
        try:
            os.makedirs("/app/output", exist_ok=True)
            json.dump({"case_id": "unknown_case", "status": "failed",
                       "uncertainty": [f"build_result crashed: {str(e)[:200]}"]},
                      open("/app/output/result.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass
        print(json.dumps({"ok": False, "error": str(e)[:300]}, ensure_ascii=False))
        sys.exit(1)
