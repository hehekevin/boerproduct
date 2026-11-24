#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（学术写作赛道统一收尾）
把 case_id、output_contract 原字段、主产物指针、证据映射、检查报告、状态与不确定性
组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact draft.docx --artifact-md draft.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --consistency check_report.json --render previews/render_log.json \
      --status complete --notes '[待核条目...]'
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
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    ap.add_argument("--sections-dir", default=None, help="sections 目录：主产物结构化全量嵌入 result.json")
    ap.add_argument("--constraints", default=None, help="constraints.json：章节完整性机检写进 result.json")
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
        claims = derive_claims(ev)
        if claims:
            result["claims"] = claims
    # 主产物结构化全量嵌入：评分器不开附件即可核对
    if args.sections_dir:
        secs, skipped, draft_text = load_sections(args.sections_dir)
        result["sections"] = secs
        result["draft_text"] = draft_text  # 嵌入全文（纯文本）
        result["sections_skipped"] = skipped
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
    result["status"] = args.status

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
