#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（结构诊断赛道收尾；增益键归 gain_evidence.py）

职责：case_id + output_contract 全字段（一个不缺，无值先 null）、主产物全量嵌入
（findings / edit_actions / report.md 全文 / claim_evidence_map）、题面三桶语义、
contract_coverage、uncertainty/changelog。已有文件只回填不覆盖；gain_evidence 与
efficiency 两个键由 gain_evidence.py 独占写入，本脚本不碰（防多脚本写同一键）。
退出码恒 0：校验/组装失败不阻断交付，状态如实记录在 result.json 内。
"""
import argparse, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog

BUCKETS = ("target_artifact", "fact_source_mapping", "version_and_boundary")
CONTRACT_SEMANTICS = [
    ("finding", "target_artifact"), ("action", "target_artifact"), ("edit", "target_artifact"),
    ("report", "target_artifact"), ("diagnosis", "target_artifact"), ("plan", "target_artifact"),
    ("target", "target_artifact"), ("content", "target_artifact"), ("main", "target_artifact"),
    ("claim", "fact_source_mapping"), ("evidence", "fact_source_mapping"),
    ("source", "fact_source_mapping"), ("citation", "fact_source_mapping"),
    ("map", "fact_source_mapping"), ("quote", "fact_source_mapping"),
    ("uncertainty", "version_and_boundary"), ("status", "version_and_boundary"),
    ("changelog", "version_and_boundary"), ("note", "version_and_boundary"),
    ("gap", "version_and_boundary"), ("limit", "version_and_boundary"),
    ("version", "version_and_boundary"), ("boundary", "version_and_boundary"),
    ("diff", "version_and_boundary"), ("pending", "version_and_boundary"),
]


def bucket_of(name):
    n = str(name or "").lower()
    for k, b in CONTRACT_SEMANTICS:
        if k in n:
            return b
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
            return None


def load_jsonl(p):
    if not p or not os.path.exists(p):
        return None
    rows = []
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    except Exception:
        return None


def contract_fields(contract):
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


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--findings", default="/app/output/findings.json")
    ap.add_argument("--actions", default="/app/work/edit_actions.jsonl")
    ap.add_argument("--report", default="/app/output/report.md")
    ap.add_argument("--claim-map", default="/app/work/claim_evidence_map.jsonl")
    ap.add_argument("--manuscript", default="/app/work/manuscript.json")
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填契约字段")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误，退出码 0"}))
        return 0

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    fields = contract_fields(case.get("output_contract") or {})

    result = load_jsonish(args.out) if os.path.exists(args.out) else None
    result = result if isinstance(result, dict) else {}
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

    findings_obj = load_jsonish(args.findings)
    if findings_obj is not None:
        result["findings_merged"] = findings_obj
    acts = load_jsonl(args.actions)
    if acts is not None:
        result["edit_actions"] = acts
    rep = None
    if args.report and os.path.exists(args.report):
        try:
            rep = open(args.report, encoding="utf-8").read()
        except Exception:
            rep = None
    if rep is not None:
        result["report_text"] = rep
        result["report_path"] = args.report
    cm = load_jsonl(args.claim_map)
    if cm is not None:
        result["claim_evidence_map"] = cm
        result["claim_stats"] = {
            "claims_total": len(cm),
            "unsupported": sum(1 for r in cm if r.get("support") == "none"),
            "note": "论点—论据映射；support=none 的条目对应论证链 findings",
        }
    ms = load_jsonish(args.manuscript)
    if isinstance(ms, dict):
        result["manuscript_stats"] = ms.get("stats")
        result["manuscript_notes"] = ms.get("notes")

    def as_list(s):
        if not s:
            return []
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

    result["target_artifact"] = {
        "findings": result.get("findings_merged"),
        "edit_actions": result.get("edit_actions"),
        "report_text": result.get("report_text"),
        "editable": bool(rep is not None or acts),
    }
    result["fact_source_mapping"] = {
        "claim_evidence_map": result.get("claim_evidence_map"),
        "claim_stats": result.get("claim_stats"),
        "note": "每条 finding 带 location+quote 可回原文核对；机检口径见 basis 字段",
    }
    result["version_and_boundary"] = {
        "changelog": result.get("changelog"),
        "uncertainty": result.get("uncertainty"),
        "manuscript_notes": result.get("manuscript_notes"),
        "status": args.status,
        "status_scale": ["complete", "partial", "failed", "blocked"],
    }
    coverage = {}
    src_map = {"target_artifact": ("findings_merged", ["edit_actions", "report_text"]),
               "fact_source_mapping": ("claim_evidence_map", ["claim_stats"]),
               "version_and_boundary": ("uncertainty", ["changelog", "status"])}
    for f in fields:
        b = bucket_of(f)
        primary, alts = src_map[b]
        filled, source = False, None
        for cand in [primary] + alts:
            v = result.get(cand)
            if v not in (None, [], {}, ""):
                if result.get(f) in (None, "", [], {}):
                    result[f] = v
                filled, source = True, cand
                break
        coverage[f] = {"bucket": b, "filled": filled, "source": source,
                       "value_present": result.get(f) not in (None, "", [], {})}
    result["contract_coverage"] = {
        "output_contract_fields": fields, "field_count": len(fields),
        "coverage": coverage, "buckets": list(BUCKETS),
        "note": "契约键一律保留不删；未回填字段保持 null 并在 uncertainty 说明。",
    }
    result["reproduction"] = {
        "commands": [
            "python3 scripts/extract_input.py --input /input --outdir /app/work",
            "python3 scripts/claim_extractor.py --manuscript /app/work/manuscript.json --out /app/work/claim_evidence_map.jsonl",
            "python3 scripts/structure_check.py --manuscript /app/work/manuscript.json --out /app/work/findings_machine.json",
            "python3 scripts/edit_plan.py --machine /app/work/findings_machine.json --model /app/work/model_findings.json --manuscript /app/work/manuscript.json",
            "python3 scripts/gain_evidence.py --manuscript /app/work/manuscript.json --result /app/output/result.json",
            "python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status complete",
        ],
        "ablation": "python3 scripts/structure_check.py --ablate（消融臂）；gain_evidence.py 内部同输入双跑",
        "environment": "Python 3.8+ 标准库即可运行；PyMuPDF/python-docx 为可选增强，缺失自动降级",
        "determinism": "同一 manuscript.json 输入下 structure_check 两臂与 gain_evidence 结果一致（时间戳除外）",
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": args.out, "status": args.status,
                      "contract_fields": len(fields),
                      "contract_filled": sum(1 for c in coverage.values() if c["filled"]),
                      "keys": sorted(result.keys())}, ensure_ascii=False))
    _rlog.log_call("build_result", argv=sys.argv[1:], seconds=time.time() - t0,
                   extra={"status": args.status})
    return 0


if __name__ == "__main__":
    sys.exit(main())
