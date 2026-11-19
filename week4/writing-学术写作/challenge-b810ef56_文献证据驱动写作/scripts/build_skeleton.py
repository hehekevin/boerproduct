#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_skeleton.py — result.json 骨架落盘与最终组装（文献证据驱动写作赛道）

两阶段：
  1) 骨架：读 /input/case.json，逐字抄下 case_id 与 output_contract 全部字段，
     写出可解析的骨架 result.json（status=in_progress，契约字段置 null，一个不缺）。
  2) 组装（--assemble）：把论断清单、证据表、强度审计、校验报告、成稿全文等
     回填进 result.json；既有契约键一律保留，只回填不删除。

键归属约定（多脚本禁写同一键）：本脚本独占 case_id/契约字段/draft_text/claims/
evidence_table/strength_report/verify_report/contract_coverage/uncertainty/changelog/
status/reproduction；gain_probe.py 只写 gain_evidence 与 efficiency；互不覆盖。

退出码恒为 0：任何失败照实写 JSON、打印说明后正常退出，不以退出码表达成败。
"""
import argparse
import json
import os
import sys
import time

BUCKETS = ("target_artifact", "fact_source_mapping", "version_and_boundary")

# 契约字段名 → 题面三桶语义（子串匹配，先具体后泛化）
CONTRACT_SEMANTICS = [
    ("deliverable", "target_artifact"), ("draft", "target_artifact"),
    ("manuscript", "target_artifact"), ("main_text", "target_artifact"),
    ("section", "target_artifact"), ("content", "target_artifact"),
    ("artifact", "target_artifact"), ("text", "target_artifact"),
    ("claim", "fact_source_mapping"), ("evidence", "fact_source_mapping"),
    ("quote", "fact_source_mapping"), ("citation", "fact_source_mapping"),
    ("reference", "fact_source_mapping"), ("source", "fact_source_mapping"),
    ("strength", "fact_source_mapping"), ("locator", "fact_source_mapping"),
    ("number", "fact_source_mapping"), ("figure", "fact_source_mapping"),
    ("term", "fact_source_mapping"), ("map", "fact_source_mapping"),
    ("uncertainty", "version_and_boundary"), ("status", "version_and_boundary"),
    ("changelog", "version_and_boundary"), ("change", "version_and_boundary"),
    ("note", "version_and_boundary"), ("gap", "version_and_boundary"),
    ("limit", "version_and_boundary"), ("version", "version_and_boundary"),
    ("boundary", "version_and_boundary"), ("pending", "version_and_boundary"),
]



class _ArgParser(argparse.ArgumentParser):
    """参数错误也退出码 0：结论写 JSON，不以退出码表达成败（硬约束）。"""
    def error(self, message):
        print(json.dumps({"ok": False, "error": "argparse: %s" % message,
                          "note": "参数错误照实记录，退出码 0"}, ensure_ascii=False))
        self.exit(0)

def bucket_of(field_name):
    n = str(field_name or "").lower()
    for key, bucket in CONTRACT_SEMANTICS:
        if key in n:
            return bucket
    return "version_and_boundary"


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


def contract_fields(contract):
    """兼容 {"fields":[...]} / {"required":[...]} / 直接列表 三种形态。"""
    if isinstance(contract, list):
        return [k for k in contract if isinstance(k, str)]
    if isinstance(contract, dict):
        for key in ("fields", "required", "required_fields", "output_contract"):
            v = contract.get(key)
            if isinstance(v, list):
                return [k for k in v if isinstance(k, str)]
            if isinstance(v, dict):
                return list(v.keys())
    return []


def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else [str(v)]
    except Exception:
        return [x.strip() for x in s.split(";") if x.strip()]


def main():
    ap = _ArgParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--status", default="in_progress")
    ap.add_argument("--assemble", action="store_true", help="最终组装模式：回填工作产物")
    ap.add_argument("--draft", default=None, help="成稿 markdown/txt，全文嵌入 draft_text")
    ap.add_argument("--claims", default=None, help="/app/work/claims.jsonl")
    ap.add_argument("--evidence-table", default=None, help="/app/work/evidence_table.jsonl")
    ap.add_argument("--strength", default=None, help="/app/output/strength_report.json")
    ap.add_argument("--verify", default=None, help="/app/output/verify_report.json")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填契约字段")
    ap.add_argument("--notes", default=None, help="uncertainty：JSON 数组或 ; 分隔")
    ap.add_argument("--changelog", default=None, help="changelog：JSON 数组或 ; 分隔")
    args = ap.parse_args()
    t0 = time.time()

    try:
        case = load_jsonish(args.case) or {}
        if not isinstance(case, dict):
            case = {}
        case_id = case.get("case_id") or case.get("id") or "unknown_case"
        fields = contract_fields(case.get("output_contract") or {})

        old = load_jsonish(args.out) if os.path.exists(args.out) else None
        result = old if isinstance(old, dict) else {}
        result.setdefault("case_id", case_id)
        for k in fields:
            result.setdefault(k, None)
        for kv in args.set:
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    v = json.loads(v)
                except Exception:
                    pass
                result[k] = v
        result["status"] = args.status
        if args.notes is not None:
            result["uncertainty"] = as_list(args.notes)
        elif result.get("uncertainty") is None:
            # 注意：uncertainty 可能同时是契约字段（已被置 None），须判 None 而非 setdefault
            result["uncertainty"] = []
        if args.changelog is not None:
            result["changelog"] = as_list(args.changelog)
        elif result.get("changelog") is None:
            result["changelog"] = []

        coverage = {}
        if args.assemble:
            if args.draft and os.path.exists(args.draft):
                try:
                    result["draft_text"] = open(args.draft, encoding="utf-8",
                                                errors="ignore").read()
                except Exception as e:
                    result.setdefault("uncertainty", []).append(
                        "draft 读取失败: %s" % e)
            for argname, key in ((args.claims, "claims"),
                                 (args.evidence_table, "evidence_table"),
                                 (args.strength, "strength_report"),
                                 (args.verify, "verify_report")):
                v = load_jsonish(argname)
                if v is not None:
                    result[key] = v
            src = {"target_artifact": ["draft_text"],
                   "fact_source_mapping": ["evidence_table", "claims", "strength_report"],
                   "version_and_boundary": ["uncertainty", "changelog"]}
            for f in fields:
                b = bucket_of(f)
                filled, source = False, None
                for cand in src[b]:
                    if result.get(cand) not in (None, [], {}, ""):
                        if result.get(f) in (None, "", [], {}):
                            result[f] = result[cand]
                        filled, source = True, cand
                        break
                coverage[f] = {"bucket": b, "filled": filled, "source": source}
            result["contract_coverage"] = {
                "output_contract_fields": fields, "field_count": len(fields),
                "coverage": coverage, "buckets": list(BUCKETS),
                "note": "契约键一律保留；无法回填的字段保持 null 并在 uncertainty 说明。",
            }
            result["target_artifact"] = {
                "draft_text": result.get("draft_text"), "editable": True,
                "note": "成稿可编辑；论断清单与证据表见 claims/evidence_table",
            }
            result["fact_source_mapping"] = {
                "claims": result.get("claims"),
                "evidence_table": result.get("evidence_table"),
                "strength_report": result.get("strength_report"),
            }
            result["version_and_boundary"] = {
                "uncertainty": result.get("uncertainty"),
                "changelog": result.get("changelog"), "status": args.status,
                "status_scale": ["complete", "partial", "failed", "blocked"],
            }
            result["reproduction"] = {
                "commands": [
                    "python3 scripts/build_skeleton.py --case /input/case.json --out /app/output/result.json --status in_progress",
                    "python3 scripts/claim_split.py --draft /app/output/draft.md --out /app/work/claims.jsonl",
                    "python3 scripts/evidence_bind.py --claims /app/work/claims.jsonl --sources /app/work/sources --out /app/work/evidence_table.jsonl",
                    "python3 scripts/strength_gate.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --out /app/output/strength_report.json",
                    "python3 scripts/verify_check.py --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --out /app/output/verify_report.json",
                    "python3 scripts/schema_guard.py --result /app/output/result.json --case /input/case.json --out /app/output/guard_report.json",
                    "python3 scripts/gain_probe.py --result /app/output/result.json --claims /app/work/claims.jsonl --evidence-table /app/work/evidence_table.jsonl --sources /app/work/sources --draft /app/output/draft.md --ablate --write",
                ],
                "environment": "Python 3.8+，仅标准库，零外部依赖",
                "determinism": "同一输入下除时间戳外结果一致",
            }

        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(result, open(args.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"ok": True, "result": args.out, "mode":
                          "assemble" if args.assemble else "skeleton",
                          "status": args.status, "contract_fields": len(fields),
                          "contract_filled": sum(1 for c in coverage.values()
                                                 if c.get("filled")),
                          "seconds": round(time.time() - t0, 3)},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e),
                          "note": "组装失败不阻断交付，退出码 0"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
