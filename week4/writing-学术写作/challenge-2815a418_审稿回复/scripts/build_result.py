#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — result.json 生命周期管理（骨架先行 · 主产物嵌入 · 写盘自检）

设计目的: result.json 的完整性由本脚本保证，不依赖提示词纪律。
任何一次运行即使中途崩溃，/app/output/result.json 也始终是合法 JSON，
包含 case_id、output_contract 全部字段和诚实 status。

子命令:
  init      立即落骨架（Stage 0 第一步执行）: case_id + 契约字段 + status=partial
  embed     主产物分批嵌入: --key letter_markdown|revised_markdown|... --file F [--part 标签]
            可多次调用追加（按审稿人/按章节分批，规避单次响应 token 限制）
  set       回填字段: --set key=value（value 为 JSON 或原文）
  finalize  收尾: --status complete|partial --notes --changelog；result.json 缺失时自愈重建
  verify    写盘自检: 契约字段齐全 / 嵌入非空 / 交付文件存在 / status 诚实

示例:
  python build_result.py init --case /input/case.json --out /app/output/result.json
  python build_result.py embed --key letter_markdown --file /app/work/letter_R1.md --part R1
  python build_result.py embed --key revised_markdown --file /app/work/revised_part1.md --part sec1-3
  python build_result.py finalize --out /app/output/result.json --status complete \
      --evidence /app/work/response_ledger.jsonl --audit /app/output/ledger_audit.json \
      --notes "C05 证据需作者确认" --changelog "Stage3 分批嵌入完成"
  python build_result.py verify --case /input/case.json --out /app/output/result.json
"""
import argparse, json, os, sys, time


def _load_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _contract_fields(case):
    c = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(c, list):
        return [k for k in c if isinstance(k, str)]
    if isinstance(c, dict):
        for key in ("fields", "required", "keys"):
            v = c.get(key)
            if isinstance(v, list):
                return [k for k in v if isinstance(k, str)]
        return list(c.keys())
    return []


def _write(result, out):
    """tmp 写入后替换，避免中途崩溃留下半截 JSON。"""
    d = os.path.dirname(out) or "."
    os.makedirs(d, exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out)


def _ensure_skeleton(result, case):
    """幂等补齐: case_id + 契约字段 + 基础结构。缺什么补什么，不覆盖已有值。"""
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    result.setdefault("case_id", case_id)
    result.setdefault("embedded", {})          # 主产物嵌入区
    result.setdefault("deliverable", {})       # 可编辑文件指针
    result.setdefault("uncertainty", [])
    result.setdefault("changelog", [])
    for k in _contract_fields(case):
        result.setdefault(k, None)
    return result


def cmd_init(args):
    case = _load_json(args.case) or {}
    result = _ensure_skeleton({}, case)
    result["status"] = "partial"
    result["changelog"].append({"event": "skeleton", "at": time.strftime("%H:%M:%S"),
                                "contract_fields": _contract_fields(case)})
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "init", "out": args.out,
                      "case_id": result["case_id"],
                      "contract_fields": _contract_fields(case)}, ensure_ascii=False))
    return 0


def cmd_embed(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        print(json.dumps({"ok": False, "cmd": "embed",
                          "error": "result.json 不存在或损坏，先跑 init 或 finalize 自愈"},
                         ensure_ascii=False))
        return 2
    if not os.path.exists(args.file):
        print(json.dumps({"ok": False, "cmd": "embed", "error": f"file 不存在: {args.file}"},
                         ensure_ascii=False))
        return 2
    with open(args.file, encoding="utf-8") as f:
        text = f.read()
    emb = result.setdefault("embedded", {})
    if args.mode == "replace" or key_empty(emb, args.key):
        emb[args.key] = text
    else:
        sep = "\n\n<!-- embed part: %s -->\n\n" % (args.part or "part")
        emb[args.key] = str(emb.get(args.key) or "") + sep + text
    meta = emb.setdefault("_parts", {})
    meta.setdefault(args.key, []).append({"part": args.part or "part", "file": args.file,
                                          "chars": len(text), "at": time.strftime("%H:%M:%S")})
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "embed", "key": args.key, "part": args.part,
                      "chars": len(text), "total_chars": len(str(emb.get(args.key) or ""))},
                     ensure_ascii=False))
    return 0


def key_empty(emb, key):
    return len(str(emb.get(key) or "")) < 10


def cmd_set(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        result = {}
    case = _load_json(args.case) or {}
    _ensure_skeleton(result, case)
    for kv in args.set:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        try:
            v = json.loads(v)
        except Exception:
            pass
        result[k] = v
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "set", "keys": list(result.keys())}, ensure_ascii=False))
    return 0


def cmd_finalize(args):
    result = _load_json(args.out)
    if not isinstance(result, dict):
        result = {}
    case = _load_json(args.case) or {}
    _ensure_skeleton(result, case)   # 自愈: init 未跑/损坏也能补出合法骨架

    def as_list(s):
        if not s:
            return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]

    if args.evidence:
        ev = _load_json(args.evidence)
        if ev is not None:
            result["response_ledger"] = ev
        result["ledger_ref"] = args.evidence
    if args.audit:
        au = _load_json(args.audit)
        if au is not None:
            result["consistency_check"] = au
    if args.render:
        rd = _load_json(args.render)
        if rd is not None:
            result["render"] = rd
    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md,
                                 "editable": True}
    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    if args.changelog:
        result["changelog"].extend([{"event": e, "at": time.strftime("%H:%M:%S")}
                                    for e in as_list(args.changelog)])
    result["status"] = args.status
    result["finalized_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write(result, args.out)
    print(json.dumps({"ok": True, "cmd": "finalize", "out": args.out, "status": args.status,
                      "embedded_keys": sorted(result.get("embedded", {}).keys()),
                      "contract_null_fields": [k for k, v in result.items() if v is None
                                               and k in _contract_fields(case)]},
                     ensure_ascii=False))
    return 0


def cmd_verify(args):
    """写盘自检。partial 状态: 只报 warning（诚实部分交付不应被误杀）；
    complete 状态: 严格机检（字段缺失/嵌入过短/文件不存在 → fail）。"""
    result = _load_json(args.out)
    hard, warns = [], []
    if not isinstance(result, dict):
        hard.append("result.json 不存在或不是合法 JSON")
        result = {}
    case = _load_json(args.case) or {}
    fields = _contract_fields(case)
    strict = result.get("status") == "complete"
    has_uncertainty = bool(result.get("uncertainty"))

    def add(msg):
        (hard if strict and not (has_uncertainty and msg.startswith("契约字段")) else warns).append(msg)

    missing = [k for k in fields if k not in result]
    if missing:
        add(f"契约字段缺失: {missing}")
    nulls = [k for k in fields if result.get(k) is None]
    if nulls:
        add(f"契约字段为 null{'（complete 且未在 uncertainty 说明则需修复）' if strict else '（partial 可接受，如实报告）'}: {nulls}")
    emb = result.get("embedded") or {}
    if strict:
        for key in ("letter_markdown", "revised_markdown"):
            if len(str(emb.get(key) or "")) < 200:
                hard.append(f"status=complete 但嵌入 {key} 缺失或过短(<200字)")
    dl = result.get("deliverable") or {}
    for k in ("docx", "markdown"):
        p = dl.get(k)
        if p and not os.path.exists(p):
            add(f"交付文件不存在: {p}")
    if result.get("status") not in ("complete", "partial", "failed"):
        hard.append(f"status 非法: {result.get('status')}")
    if not result.get("case_id") or result.get("case_id") == "unknown_case":
        hard.append("case_id 缺失或 unknown")
    report = {"verdict": "pass" if not hard else "fail", "problems": hard,
              "warnings": warns,
              "case_id": result.get("case_id"), "status": result.get("status"),
              "embedded_chars": {k: len(str(v)) for k, v in emb.items()
                                 if not k.startswith("_")}}
    if args.report:
        _write(report, args.report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not hard else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="Stage 0 立即落骨架")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("embed", help="主产物分批嵌入")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--key", required=True, help="letter_markdown / revised_markdown / ...")
    p.add_argument("--file", required=True)
    p.add_argument("--part", default=None, help="分批标签，如 R1 / sec1-3")
    p.add_argument("--mode", default="append", choices=["append", "replace"])
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("set", help="回填字段")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--set", action="append", default=[])
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("finalize", help="收尾（失败也交付的自愈路径）")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--artifact", default=None)
    p.add_argument("--artifact-md", default=None)
    p.add_argument("--evidence", default=None, help="response_ledger.jsonl")
    p.add_argument("--audit", default=None, help="ledger_audit.json")
    p.add_argument("--render", default=None, help="render_log.json")
    p.add_argument("--status", default="partial", choices=["complete", "partial", "failed"])
    p.add_argument("--notes", default=None, help="uncertainty: JSON 数组或 ; 分隔")
    p.add_argument("--changelog", default=None, help="追加事件: ; 分隔")
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("verify", help="写盘自检")
    p.add_argument("--case", default="/input/case.json")
    p.add_argument("--out", default="/app/output/result.json")
    p.add_argument("--report", default=None)
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
