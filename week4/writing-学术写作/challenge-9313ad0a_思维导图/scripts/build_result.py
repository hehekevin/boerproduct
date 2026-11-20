#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — result.json 统一收口（骨架 / 回填 / 嵌入 / 自检）
四种用法：
  1) 落骨架:   python build_result.py init --case /input/case.json --out /app/output/result.json
               读取 case.json 的 case_id 与 output_contract，立即写出全键骨架（缺值填 "unknown"，status=partial）。
  2) 嵌入回填: python build_result.py embed --out /app/output/result.json \
                 --embed-file /app/work/tree.json:mindmap_tree \
                 --embed-file /app/output/outline.md:deliverable_content \
                 --embed-file /app/work/relations.jsonl:mindmap_relations \
                 --embed-file /app/work/node_evidence.jsonl:node_evidence \
                 --set status=complete --set notes='xxx'
               --embed-file 路径:键名，可重复；.jsonl 自动解析为列表；文本读为字符串。
  3) 附加信息:  同 embed，--artifact / --artifact-md / --evidence / --consistency / --render / --changelog。
  4) 自检:     python build_result.py verify --case /input/case.json --out /app/output/result.json
               检查 JSON 可解析、契约键一个不缺、case_id 一致、status 如实（complete 时主内容键非 unknown/空）。
输出均为 JSON 一行日志。失败 exit 1，绝不静默。
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

def contract_keys(contract):
    if isinstance(contract, list):
        return [k for k in contract if isinstance(k, str)]
    if isinstance(contract, dict):
        for key in ("fields", "required", "keys"):
            v = contract.get(key)
            if isinstance(v, list):
                return [k for k in v if isinstance(k, str)]
        # dict 形式 {"字段名": 描述}
        return [k for k in contract.keys() if k not in ("case_id", "id")]
    return []

def cmd_init(args):
    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}
    keys = contract_keys(contract)
    skel = {"case_id": case_id, "status": "partial"}
    for k in keys:
        skel[k] = [] if k in ("uncertainty", "changelog") else "unknown"
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(skel, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "mode": "init", "out": args.out, "case_id": case_id,
                      "contract_keys": keys}, ensure_ascii=False))
    return 0

def cmd_embed(args):
    result_path = args.out
    result = load_jsonish(result_path)
    if not isinstance(result, dict):
        result = {"status": "partial"}
    if args.case:
        case = load_jsonish(args.case) or {}
        result.setdefault("case_id", case.get("case_id") or case.get("id") or "unknown_case")
        for k in contract_keys(case.get("output_contract") or {}):
            result.setdefault(k, None)
    for spec in (args.embed_file or []):
        if ":" not in spec:
            print(json.dumps({"ok": False, "error": f"--embed-file 需 路径:键名，收到 {spec}"}, ensure_ascii=False))
            return 1
        path, key = spec.rsplit(":", 1)
        if not os.path.exists(path):
            print(json.dumps({"ok": False, "error": f"embed 源不存在: {path}"}, ensure_ascii=False))
            return 1
        content = load_jsonish(path)
        if content is None:
            content = open(path, encoding="utf-8").read()
        if isinstance(content, str) and len(content) < 20:
            print(json.dumps({"ok": False, "error": f"embed 源过小疑似空文件: {path}"}, ensure_ascii=False))
            return 1
        result[key] = content
    if args.artifact:
        result["deliverable"] = {"file": args.artifact, "markdown": args.artifact_md or None, "editable": True}
    for flag, key in (("--evidence", "evidence_map"), ("--consistency", "consistency_check"),
                      ("--render", "render"), ("--fact-check", "fact_check")):
        val = getattr(args, flag[2:].replace("-", "_"))
        if val:
            data = load_jsonish(val)
            if data is not None:
                result[key] = data
    def as_list(s):
        if not s: return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    for kv in (args.set or []):
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            result[k] = v
    if "status" not in result:
        result["status"] = "partial"
    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "mode": "embed", "out": result_path, "status": result.get("status"),
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

def cmd_verify(args):
    problems = []
    result = load_jsonish(args.out)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "verdict": "fail", "problems": ["result.json 不存在或不可解析"]}, ensure_ascii=False))
        return 1
    case = load_jsonish(args.case) or {}
    cid = case.get("case_id") or case.get("id")
    if cid and result.get("case_id") != cid:
        problems.append(f"case_id 不一致: result={result.get('case_id')} case={cid}")
    missing = [k for k in contract_keys(case.get("output_contract") or {}) if k not in result]
    if missing:
        problems.append(f"契约键缺失: {missing}")
    st = result.get("status")
    if st == "complete":
        unknown = [k for k, v in result.items() if v in ("unknown", None, "", [])
                   and k not in ("uncertainty", "changelog")]
        if unknown:
            problems.append(f"status=complete 但这些键仍为空/unknown: {unknown[:10]}")
    if not result.get("render") and os.path.exists("/app/output/previews/render_log.json"):
        result["render"] = load_jsonish("/app/output/previews/render_log.json")
        json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": not problems, "verdict": "pass" if not problems else "fail",
                      "status": st, "problems": problems}, ensure_ascii=False))
    return 1 if problems else 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode")
    p1 = sub.add_parser("init"); p1.add_argument("--case", default="/input/case.json"); p1.add_argument("--out", default="/app/output/result.json")
    p2 = sub.add_parser("embed")
    p2.add_argument("--out", default="/app/output/result.json")
    p2.add_argument("--case", default=None)
    p2.add_argument("--embed-file", action="append", default=[], help="路径:键名，可重复")
    p2.add_argument("--artifact", default=None); p2.add_argument("--artifact-md", default=None)
    p2.add_argument("--evidence", default=None); p2.add_argument("--fact-check", default=None)
    p2.add_argument("--consistency", default=None); p2.add_argument("--render", default=None)
    p2.add_argument("--changelog", default=None)
    p2.add_argument("--set", action="append", default=[], help="key=value（JSON 值优先）")
    p3 = sub.add_parser("verify"); p3.add_argument("--case", default="/input/case.json"); p3.add_argument("--out", default="/app/output/result.json")
    args = ap.parse_args()
    if args.mode == "init":
        return cmd_init(args)
    if args.mode == "embed":
        return cmd_embed(args)
    if args.mode == "verify":
        return cmd_verify(args)
    ap.print_help()
    return 2

if __name__ == "__main__":
    sys.exit(main())
