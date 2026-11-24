#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（开题报告赛道统一收尾）
把 case_id、output_contract 原字段、主产物全文（内嵌）、证据映射、检查报告、状态与
不确定性组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact proposal.docx --artifact-md proposal.md \
      --embed-file /app/output/proposal.md --embed-key deliverable_content \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency plan_check.json --render previews/render_log.json \
      --status complete --notes '[待核条目...]' --changelog '取舍记录'

容错: case.json/各报告缺失或损坏时降级组装，绝不崩溃；status 仅接受
complete/partial/failed/blocked 四级，越界值降级为 partial 并登记。
末尾输出自检 JSON（contract 缺键、embed 字符数），供协议第 5 条核验。
"""
import argparse, json, os, sys

STATUSES = ("complete", "partial", "failed", "blocked")


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
    """从 output_contract 提取字段名列表；兼容 list[str]/list[dict]/dict 多种形态。"""
    keys = []
    try:
        if isinstance(contract, list):
            for k in contract:
                if isinstance(k, str):
                    keys.append(k)
                elif isinstance(k, dict):
                    for f in ("name", "key", "field", "id"):
                        if k.get(f):
                            keys.append(k[f])
                            break
        elif isinstance(contract, dict):
            hit = False
            for f in ("fields", "required", "keys", "properties"):
                v = contract.get(f)
                if isinstance(v, list) and v:
                    for k in v:
                        if isinstance(k, str):
                            keys.append(k)
                        elif isinstance(k, dict):
                            for ff in ("name", "key", "field", "id"):
                                if k.get(ff):
                                    keys.append(k[ff])
                                    break
                    hit = bool(keys)
                    break
                if isinstance(v, dict) and v:
                    keys.extend(list(v.keys()))
                    hit = True
                    break
            if not hit:
                keys = [k for k in contract.keys()
                        if k not in ("description", "note", "notes", "contract_version")]
    except Exception:
        pass
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


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
    ap.add_argument("--embed-file", default=None,
                    help="主产物全文文件（md/txt），内容作为字符串写入 --embed-key 字段")
    ap.add_argument("--embed-key", default="deliverable_content")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[],
                    help="--set key=value 直接回填 output_contract 字段")
    args = ap.parse_args()

    notes = list(as_list(args.notes) or [])
    status = args.status if args.status in STATUSES else "partial"
    if status != args.status:
        notes.append("status '%s' 不在四级诚实状态内，已降级为 partial" % args.status)

    case = load_jsonish(args.case) or {}
    if not isinstance(case, dict):
        case = {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), (dict, list)) else {}
    key_list = contract_keys(contract)

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    for k in key_list:
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
        result["deliverable"] = {"docx": args.artifact,
                                 "markdown": args.artifact_md or None,
                                 "editable": True}

    # 主产物全文内嵌（协议第 3 条）：字符串整读整写，绕开模型响应 token 截断
    embed_chars = 0
    if args.embed_file:
        try:
            text = open(args.embed_file, encoding="utf-8").read()
            if text.strip():
                result[args.embed_key] = text
                embed_chars = len(text)
            else:
                notes.append("embed 文件为空: %s" % args.embed_file)
        except Exception as e:
            notes.append("embed 读取失败 %s: %s" % (args.embed_file, str(e)[:120]))
        result.setdefault(args.embed_key, None)

    for flag, key in ((args.evidence, "evidence_map"), (args.fact_check, "fact_check"),
                      (args.consistency, "consistency_check"), (args.render, "render")):
        v = load_jsonish(flag) if flag else None
        if v is not None:
            result[key] = v
    if args.ledger:
        result["fact_ledger_ref"] = args.ledger

    prev_notes = result.get("uncertainty")
    merged = [x for x in (prev_notes if isinstance(prev_notes, list) else []) if x not in notes]
    result["uncertainty"] = merged + notes
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        result.setdefault("changelog", [])
    result["status"] = status

    try:
        os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
        json.dump(result, open(result_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        written = True
    except Exception as e:
        written = False
        sys.stderr.write("result.json 写盘失败: %s\n" % e)

    # 自检输出（协议第 5 条依据）
    empty_keys = [k for k in key_list if result.get(k) in (None, "", [], {})]
    check = {"ok": written, "result": result_path, "status": status,
             "case_id": result.get("case_id"), "contract_keys": key_list,
             "contract_keys_total": len(key_list),
             "contract_keys_empty": empty_keys,
             "embed_key": args.embed_key if args.embed_file else None,
             "embed_chars": embed_chars,
             "uncertainty_count": len(result["uncertainty"])}
    print(json.dumps(check, ensure_ascii=False))
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
