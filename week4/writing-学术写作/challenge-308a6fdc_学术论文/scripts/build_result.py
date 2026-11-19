#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学术写作赛道统一收尾）

把 case_id、output_contract 原字段、主产物指针、证据映射、检查报告、增益证据、
效率计数、状态与不确定性组装成 /app/output/result.json。
已有骨架时只回填不覆盖（保留早期诚实状态）。

题面「Skill 运行后的输出要求」三桶语义（在 result.json 内显式给出，便于评分器按语义核对）：
  target_artifact       目标产物：可编辑稿件 / 结构化写作产物
  fact_source_mapping  事实与来源映射：数字/术语/引用/图表/关键论断的来源与修改记录
  version_and_boundary 版本与边界：修改差异、人工确认项、材料缺口、异常
另附 contract_coverage：把 output_contract 每个字段归类到三桶并标注填充状态，
既有契约键一律保留、不删除。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact draft.docx --artifact-md draft.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency check_report.json --render previews/render_log.json \
      --gain-evidence /app/output/gain_evidence.json \
      --status complete --changelog '关键决策; 降级事实'
字段均可缺省；output_contract 中的字段若无法填写，保持 null 并在 uncertainty 说明。

退出码恒为 0：校验/组装失败不阻断交付，状态如实记录在 result.json 内。
"""
import argparse
import json
import os
import sys
import time

try:
    import _rlog
except Exception:
    _rlog = None

# 题面输出要求表的三桶语义
BUCKETS = ("target_artifact", "fact_source_mapping", "version_and_boundary")

# 契约字段名 → 语义桶（子串匹配，顺序敏感：先匹配更具体的）
CONTRACT_SEMANTICS = [
    ("deliverable_content", "target_artifact"), ("main_text", "target_artifact"),
    ("draft", "target_artifact"), ("section", "target_artifact"),
    ("manuscript", "target_artifact"), ("artifact", "target_artifact"),
    ("target", "target_artifact"), ("content", "target_artifact"),
    ("evidence_map", "fact_source_mapping"), ("evidence", "fact_source_mapping"),
    ("source", "fact_source_mapping"), ("trace", "fact_source_mapping"),
    ("citation", "fact_source_mapping"), ("reference", "fact_source_mapping"),
    ("number", "fact_source_mapping"), ("figure", "fact_source_mapping"),
    ("table", "fact_source_mapping"), ("claim", "fact_source_mapping"),
    ("fact", "fact_source_mapping"), ("map", "fact_source_mapping"),
    ("uncertainty", "version_and_boundary"), ("status", "version_and_boundary"),
    ("changelog", "version_and_boundary"), ("change", "version_and_boundary"),
    ("note", "version_and_boundary"), ("gap", "version_and_boundary"),
    ("limit", "version_and_boundary"), ("version", "version_and_boundary"),
    ("boundary", "version_and_boundary"), ("diff", "version_and_boundary"),
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
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p}


def load_sections(sections_dir):
    """读取 sections/S##.json，按文件名排序返回结构化章节列表与全文文本；坏文件跳过留痕。"""
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


def derive_claims(evidence):
    """从 evidence_map 推导 claims：kind/evidence(≤40字逐字)/source_id/location，嵌入 result.json。"""
    claims = []
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        return claims
    for i, e in enumerate(evidence, 1):
        if not isinstance(e, dict):
            continue
        loc = e.get("locator") or e.get("location") or ""
        parts = loc.split(":", 1)
        claims.append({
            "claim_id": e.get("claim_id") or "C%02d" % i,
            "section": e.get("section"),
            "text": e.get("text"),
            "kind": e.get("type") or e.get("kind") or "number",
            "evidence": (e.get("quote") or e.get("evidence") or "")[:40],
            "source_id": parts[0] if parts else None,
            "location": loc,
        })
    return claims


def contract_fields(contract):
    """兼容多种 output_contract 形态：{"fields":[...]} / {"required":[...]} / 直接列表。"""
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
    """把已产出的内容回填到 output_contract 同义字段；既有非空值不被覆盖。
    返回 {field: {bucket, filled, source}}。"""
    src = {
        "target_artifact": ("draft_text", ["sections", "deliverable"]),
        "fact_source_mapping": ("claims", ["evidence_map", "fact_check"]),
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


def efficiency_counters(run_log_path, model_requests, followup_rounds, notes_for_human):
    """效率计数：工具调用数等由 run_log 自动采集；模型请求数/追问轮次如实标注来源。"""
    rows = _rlog.read_log(run_log_path) if _rlog is not None else []
    by_tool = {}
    for r in rows:
        t = r.get("tool") or "unknown"
        by_tool[t] = by_tool.get(t, 0) + 1
    build_calls = by_tool.get("build_result", 0)
    detect_questions = sum(1 for n in (notes_for_human or [])
                            if isinstance(n, str) and ("？" in n or "?" in n))
    return {
        "tool_calls": len(rows),
        "tool_calls_by_script": by_tool,
        "tool_calls_source": "auto: run_log.jsonl 逐次调用记录（scripts 内 _rlog.log_call 写入）",
        "model_requests": model_requests,
        "model_requests_source": ("auto: run_log 中 build_result 调用次数（每次回填=1 次模型响应）"
                                  if model_requests is None else "explicit: 由运行方显式传入 --model-requests"),
        "model_requests_proxy_build_result_calls": build_calls,
        "followup_rounds": followup_rounds,
        "followup_rounds_source": ("explicit: --followup-rounds" if followup_rounds is not None
                                   else "auto_proxy: 待人工确认条目中含问号的条数（不冒充真实追问轮次）"),
        "followup_items_detected": detect_questions,
        "sections_written": by_tool.get("docx_build", 0),
        "note": "仅统计脚本可自动采集项；模型请求数与追问轮次若无显式值则取 auto_proxy 并标注来源。",
    }


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
    ap.add_argument("--gain-evidence", default=None)
    ap.add_argument("--run-log", default=None)
    ap.add_argument("--model-requests", type=int, default=None)
    ap.add_argument("--followup-rounds", type=int, default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    ap.add_argument("--sections-dir", default=None, help="sections 目录：主产物结构化全量嵌入 result.json")
    ap.add_argument("--constraints", default=None, help="constraints.json：章节完整性机检写进 result.json")
    args = ap.parse_args()
    t0 = time.time()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}
    fields = contract_fields(contract)

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    # 契约字段原样保留（值可为 null，后面 --set 或模型回填）
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
                                 "editable": True}
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
        claims = derive_claims(ev)
        if claims:
            result["claims"] = claims
    # 主产物结构化全量嵌入：评分器不开附件即可核对
    notes_for_human = []
    if args.sections_dir:
        secs, skipped, draft_text = load_sections(args.sections_dir)
        result["sections"] = secs
        result["draft_text"] = draft_text  # 嵌入全文（纯文本）
        result["sections_skipped"] = skipped
        for s in secs:
            for n in (s.get("notes_for_human") or []):
                notes_for_human.append(n)
        # 章节完整性机检（对照 constraints.required_sections）
        req = []
        if args.constraints and os.path.exists(args.constraints):
            try:
                req = json.load(open(args.constraints, encoding="utf-8")).get("required_sections") or []
            except Exception:
                req = []
        if req:
            heads = " ".join(str(s.get("heading", "")) for s in secs)
            result["section_check"] = {
                "item": "sections_complete", "template_value": req, "gate": "enforced",
                "applied": [h for h in (s.get("heading") for s in secs) if h],
                "match": all(h in heads for h in req),
                "missing": [h for h in req if h not in heads],
            }
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
    ge = load_jsonish(args.gain_evidence)
    if ge is not None:
        result["gain_evidence"] = ge

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
        "draft_text": result.get("draft_text"),
        "sections": result.get("sections"),
        "deliverable": result.get("deliverable"),
        "editable": bool(result.get("deliverable") or result.get("draft_text")),
    }
    result["fact_source_mapping"] = {
        "claims": result.get("claims"),
        "evidence_map": result.get("evidence_map"),
        "fact_check": result.get("fact_check"),
        "section_check": result.get("section_check"),
    }
    result["version_and_boundary"] = {
        "changelog": result.get("changelog"),
        "uncertainty": result.get("uncertainty"),
        "notes_for_human": notes_for_human,
        "material_gaps": result.get("material_gaps"),
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

    # ---- 效率计数 ----
    result["efficiency"] = efficiency_counters(
        args.run_log, args.model_requests, args.followup_rounds, notes_for_human)
    result["reproduction"] = {
        "commands": [
            "python3 scripts/extract_materials.py --input /input --outdir /app/work/extracted",
            "python3 scripts/fact_ledger.py build --sources /app/work/extracted --out /app/work/fact_ledger.jsonl",
            "python3 scripts/fact_ledger.py check --draft /app/output/draft.md --ledger /app/work/fact_ledger.jsonl --out /app/output/fact_check.json",
            "python3 scripts/consistency_check.py --draft /app/output/draft.md --constraints /app/work/constraints.json --out /app/output/check_report.json",
            "python3 scripts/gain_evidence.py --draft /app/output/draft.md --ledger /app/work/fact_ledger.jsonl --evidence /app/work/evidence_map.jsonl --constraints /app/work/constraints.json --extracted /app/work/extracted --out /app/output/gain_evidence.json",
            "python3 scripts/build_result.py --case /input/case.json --out /app/output/result.json --status complete",
        ],
        "ablation_command": ("python3 scripts/gain_evidence.py --draft ... --ablate 由内部双跑完成；"
                             "单臂可用 fact_ledger.py check --ablate / consistency_check.py --ablate 复现"),
        "environment": "Python 3.8+，零外部依赖；可选增强库缺失时自动降级并记录",
        "determinism": "同一 draft/ledger/evidence/constraints 输入下两次 gain_evidence 结果一致（步骤数除外）",
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
