#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（模板适配赛道统一收尾）

把 case_id、output_contract 原字段、主产物指针、规格来源映射、机检报告、保真报告、
效率计数、状态与不确定性组装成 /app/output/result.json。已有骨架时只回填不覆盖。
（gain_evidence 键由 gain_evidence.py --write 单独写入，本脚本不写该键，避免多脚本同键互踩。）

题面「Skill 运行后的输出要求」三桶语义（在 result.json 内显式给出）：
  target_artifact       目标产物：可编辑适配稿件（adapted_text/sections/deliverable）
  spec_source_mapping   规格与来源映射：每条模板规格带 source 锚点，每条机检带 applied/match
  version_and_boundary  版本与边界：changelog/uncertainty/人工确认项/冲突/fidelity/status
另附 contract_coverage：把 output_contract 每个字段归类到三桶并标注填充状态；契约键一律保留。

退出码恒 0：校验/组装失败不阻断交付，状态如实记录在 result.json 内。
"""
import argparse, json, os, sys, time

try:
    import _rlog
except Exception:
    _rlog = None

BUCKETS = ("target_artifact", "spec_source_mapping", "version_and_boundary")

CONTRACT_SEMANTICS = [
    ("deliverable", "target_artifact"), ("adapted", "target_artifact"),
    ("manuscript", "target_artifact"), ("artifact", "target_artifact"),
    ("main_text", "target_artifact"), ("draft", "target_artifact"),
    ("target", "target_artifact"), ("content", "target_artifact"), ("text", "target_artifact"),
    ("spec", "spec_source_mapping"), ("checklist", "spec_source_mapping"),
    ("format", "spec_source_mapping"), ("template", "spec_source_mapping"),
    ("evidence", "spec_source_mapping"), ("source", "spec_source_mapping"),
    ("citation", "spec_source_mapping"), ("reference", "spec_source_mapping"),
    ("check", "spec_source_mapping"), ("match", "spec_source_mapping"),
    ("fidelity", "spec_source_mapping"), ("trace", "spec_source_mapping"),
    ("uncertainty", "version_and_boundary"), ("status", "version_and_boundary"),
    ("changelog", "version_and_boundary"), ("change", "version_and_boundary"),
    ("note", "version_and_boundary"), ("gap", "version_and_boundary"),
    ("limit", "version_and_boundary"), ("version", "version_and_boundary"),
    ("boundary", "version_and_boundary"), ("conflict", "version_and_boundary"),
    ("review", "version_and_boundary"), ("pending", "version_and_boundary"),
]


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
        raw = open(p, encoding="utf-8", errors="ignore").read()
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except Exception:
            rows = []
            for l in raw.splitlines():
                if not l.strip():
                    continue
                try:
                    rows.append(json.loads(l))
                except Exception:
                    return {"raw_path": p, "unparsed_lines": True}
            return rows or None
    except Exception:
        return None


def load_sections(sections_dir):
    import glob as _g
    sections, skipped, md_lines = [], [], []
    for fp in sorted(_g.glob(os.path.join(sections_dir, "S*.json"))):
        try:
            obj = json.load(open(fp, encoding="utf-8"))
            if isinstance(obj, dict):
                sections.append(obj)
                md_lines.append("# " + obj.get("heading", os.path.basename(fp)))
                for p in obj.get("paragraphs", []):
                    md_lines.append(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False))
        except Exception as e:
            skipped.append({"file": os.path.basename(fp), "error": str(e)})
    return sections, skipped, "\n\n".join(md_lines)


def derive_claims(checklist):
    """由 checklist 推导 spec_claims：每条规格 kind/template_value/evidence(≤40字逐字)/location。"""
    claims = []
    items = []
    if isinstance(checklist, dict):
        items = (checklist.get("items") or []) + (checklist.get("defaulted") or [])
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        src = it.get("source") or {}
        claims.append({
            "claim_id": "F%02d" % i,
            "kind": it.get("category"),
            "text": it.get("name"),
            "template_value": it.get("template_value"),
            "evidence": str(src.get("quote") or "")[:40],
            "source_id": src.get("file"),
            "location": "%s:%s" % (src.get("file"), src.get("line")),
        })
    return claims


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


def auto_fill_contract(result, fields):
    src = {
        "target_artifact": ("adapted_text", ["sections", "deliverable"]),
        "spec_source_mapping": ("spec_claims", ["format_check", "checklist_ref"]),
        "version_and_boundary": ("uncertainty", ["changelog", "status"]),
    }
    coverage = {}
    for f in fields:
        bucket = bucket_of(f)
        primary, alts = src[bucket]
        filled, source = False, None
        for cand in [primary] + alts:
            v = result.get(cand)
            if v not in (None, [], {}, ""):
                if result.get(f) in (None, "", [], {}):
                    result[f] = v
                filled, source = True, cand
                break
        coverage[f] = {"bucket": bucket, "filled": filled, "source": source,
                       "value_present": result.get(f) not in (None, "", [], {})}
    return coverage


def efficiency_counters(run_log_path, model_requests, followup_rounds, manual_items):
    rows = _rlog.read_log(run_log_path) if _rlog is not None else []
    by_tool = {}
    for r in rows:
        t = r.get("tool") or "unknown"
        by_tool[t] = by_tool.get(t, 0) + 1
    machine_checks = sum(1 for r in rows if (r.get("tool") or "").startswith("format_check"))
    return {
        "tool_calls": len(rows),
        "tool_calls_by_script": by_tool,
        "tool_calls_source": "auto: run_log.jsonl 逐次调用记录（scripts 内 _rlog.log_call 写入）",
        "model_requests": model_requests,
        "model_requests_source": ("auto: run_log 中 build_result 调用次数（每次回填=1 次模型响应）"
                                  if model_requests is None else "explicit: 由运行方显式传入 --model-requests"),
        "model_requests_proxy_build_result_calls": by_tool.get("build_result", 0),
        "mechanical_check_runs": machine_checks,
        "manual_review_items": manual_items,
        "manual_review_items_source": ("explicit: --manual-items（机检 fail/skipped + conflicts 等需人工核对条数）"
                                       if manual_items is not None else "auto: 未显式传入，由 gain_evidence 层统计"),
        "followup_rounds": followup_rounds,
        "followup_rounds_source": ("explicit: --followup-rounds" if followup_rounds is not None
                                   else "auto_proxy: 未显式传入，不冒充真实追问轮次"),
        "note": "仅统计脚本可自动采集项；模型请求数与追问轮次若无显式值则标注来源并留空。",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None, help="adapted.docx 路径")
    ap.add_argument("--artifact-md", default=None, help="adapted.md 路径")
    ap.add_argument("--checklist", default=None)
    ap.add_argument("--format-report", default=None)
    ap.add_argument("--fidelity", default=None)
    ap.add_argument("--adapt-log", default=None)
    ap.add_argument("--run-log", default=None)
    ap.add_argument("--model-requests", type=int, default=None)
    ap.add_argument("--followup-rounds", type=int, default=None)
    ap.add_argument("--manual-items", type=int, default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    ap.add_argument("--sections-dir", default=None)
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    fields = contract_fields(case.get("output_contract") or {})

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
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

    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md or None,
                                 "editable": True, "kind": "template_adapted_manuscript"}
    if args.checklist:
        cl = load_jsonish(args.checklist)
        if isinstance(cl, dict):
            result["checklist_ref"] = args.checklist
            result["spec_claims"] = derive_claims(cl)
            result["checklist_gates"] = cl.get("gates")
            result["spec_conflicts"] = cl.get("conflicts")
        elif cl is not None:
            result["checklist_ref"] = args.checklist
            result["checklist_gates"] = {"checklist_readable": "malformed"}
    fc = load_jsonish(args.format_report)
    if isinstance(fc, dict):
        result["format_check"] = fc
        result["section_check"] = next(
            (r for r in (fc.get("results") or []) if isinstance(r, dict) and r.get("item") == "sections_complete"), None)
    fd = load_jsonish(args.fidelity)
    if isinstance(fd, dict):
        result["fidelity_check"] = fd
    al = load_jsonish(args.adapt_log)
    if isinstance(al, dict):
        result["adapt_log"] = al
    notes_for_human = []
    if args.sections_dir:
        secs, skipped, adapted_text = load_sections(args.sections_dir)
        result["sections"] = secs
        result["adapted_text"] = adapted_text
        result["sections_skipped"] = skipped
        for s in secs:
            for n in (s.get("notes_for_human") or []):
                notes_for_human.append(n)

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

    # ---- 题面三桶语义（显式给出） ----
    result["target_artifact"] = {
        "adapted_text": result.get("adapted_text"),
        "sections": result.get("sections"),
        "deliverable": result.get("deliverable"),
        "editable": bool(result.get("deliverable") or result.get("adapted_text")),
    }
    result["spec_source_mapping"] = {
        "spec_claims": result.get("spec_claims"),
        "checklist_ref": result.get("checklist_ref"),
        "format_check": result.get("format_check"),
        "fidelity_check": result.get("fidelity_check"),
        "adapt_log": result.get("adapt_log"),
    }
    result["version_and_boundary"] = {
        "changelog": result.get("changelog"),
        "uncertainty": result.get("uncertainty"),
        "notes_for_human": notes_for_human,
        "spec_conflicts": result.get("spec_conflicts"),
        "status": args.status,
        "status_scale": ["complete", "partial", "failed", "blocked"],
    }
    coverage = auto_fill_contract(result, fields)
    result["contract_coverage"] = {
        "output_contract_fields": fields,
        "field_count": len(fields),
        "coverage": coverage,
        "buckets": list(BUCKETS),
        "note": "契约键一律保留；能由已产出内容回填的字段已回填，其余保持 null 并在 uncertainty 说明。",
    }

    result["efficiency"] = efficiency_counters(
        args.run_log, args.model_requests, args.followup_rounds, args.manual_items)
    result["reproduction"] = {
        "commands": [
            "python3 scripts/extract_template.py --input /input --out /app/work/checklist.json",
            "python3 scripts/adapt_build.py --sections-dir /app/work/sections --checklist /app/work/checklist.json --out-docx /app/output/adapted.docx --out-md /app/output/adapted.md",
            "python3 scripts/inventory.py scan --doc /input/原稿.md --out /app/work/inv_src.json",
            "python3 scripts/inventory.py scan --doc /app/output/adapted.md --out /app/work/inv_adp.json",
            "python3 scripts/inventory.py compare --a /app/work/inv_src.json --b /app/work/inv_adp.json --out /app/output/fidelity_report.json",
            "python3 scripts/format_check.py --draft /app/output/adapted.md --checklist /app/work/checklist.json --docx /app/output/adapted.docx --out /app/output/format_report.json",
            "python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status complete",
            "python3 scripts/gain_evidence.py --result /app/output/result.json --draft /app/output/adapted.md --checklist /app/work/checklist.json --docx /app/output/adapted.docx --write",
        ],
        "ablation_command": "python3 scripts/format_check.py --draft ... --checklist ... --ablate（gain_evidence.py 已内置双臂对照 + 污染反例注入）",
        "environment": "Python 3.8+，零外部依赖；失败路径一律 exit 0",
        "determinism": "同一 draft/checklist/docx 输入下 format_check 与 gain_evidence 结果一致",
    }

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "contract_fields": len(fields),
                      "contract_filled": sum(1 for c in coverage.values() if c["filled"]),
                      "keys": list(result.keys())}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("build_result", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"status": args.status})
    return 0


if __name__ == "__main__":
    sys.exit(main())
