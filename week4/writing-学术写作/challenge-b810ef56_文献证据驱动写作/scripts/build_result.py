#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（证据驱动写作收尾，v2：主产物完整嵌入）
把 case_id、output_contract 原字段、主产物（成文全文+论断-证据表）、双向映射矩阵、
检查报告、状态与不确定性组装进 /app/output/result.json，使其自包含可独立复核。
已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact draft.docx --artifact-md draft.md \
      --claims /app/work/claims_evidence.jsonl --draft-json /app/work/draft.json \
      --fact-check /app/output/fact_check.json --consistency /app/output/check_report.json \
      --audit /app/output/evidence_audit.json --status complete [--notes ...] [--changelog ...]
字段均可缺省；output_contract 字段无法填写时保持 null 并在 uncertainty 说明。
"""
import argparse, json, os, re, sys

def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p, "note": "unreadable, kept path only"}

def as_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v) else [str(v)]
    except Exception:
        return [x.strip() for x in s.split(";") if x.strip()]

def draft_to_text(draft):
    """draft.json → 纯文本全文（嵌入 result.json 用，保结构标题）。"""
    if not isinstance(draft, dict):
        return None
    L = [str(draft.get("title", ""))]
    for sec in draft.get("sections", []):
        L.append("")
        L.append("## " + str(sec.get("heading", "")))
        for para in sec.get("paragraphs", []):
            if isinstance(para, str):
                L.append(para)
            elif isinstance(para, dict):
                if para.get("type") == "table":
                    rows = para.get("rows", [])
                    for r in rows:
                        L.append(" | ".join(str(c) for c in r))
                elif para.get("caption"):
                    L.append("[%s]" % para["caption"])
    refs = draft.get("references") or []
    if refs:
        L.append("")
        L.append("## 参考文献")
        L.extend(str(r) for r in refs)
    return "\n".join(L)

def build_matrix(claims_rows):
    """claims_evidence.jsonl → 双向映射矩阵（含孤儿检测）。"""
    fwd, rev = {}, {}
    for r in claims_rows:
        if not isinstance(r, dict) or r.get("status") != "bound":
            continue
        cid = str(r.get("cid"))
        fwd[cid] = r.get("sources") or []
        for s in fwd[cid]:
            rev.setdefault(str(s), []).append(cid)
    return {"claim_to_source": fwd,
            "source_to_claims": {k: v for k, v in sorted(rev.items())},
            "claims_bound": len(fwd), "sources_used": len(rev)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--claims", default=None, help="claims_evidence.jsonl（嵌入+生成矩阵）")
    ap.add_argument("--draft-json", default=None, help="draft.json（全文嵌入）")
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--audit", default=None, help="evidence_audit.json")
    ap.add_argument("--render", default=None)
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None)
    ap.add_argument("--set", action="append", default=[], help="--set key=value 回填契约字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    old = load_jsonish(args.out) if os.path.exists(args.out) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
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

    # 主产物指针
    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md or None,
                                 "editable": True}

    # 主产物完整嵌入: 成文全文
    draft_json = load_jsonish(args.draft_json)
    if isinstance(draft_json, dict):
        text = draft_to_text(draft_json)
        if text:
            result["deliverable_text"] = text  # 成文全文自包含
    # 主产物完整嵌入: 论断-证据表 + 双向映射矩阵
    claims = load_jsonish(args.claims)
    if isinstance(claims, list) and claims:
        result["claims_evidence"] = claims
        result["claim_source_matrix"] = build_matrix(claims)

    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    au = load_jsonish(args.audit)
    if au is not None:
        result["evidence_audit"] = au
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd

    if args.notes:
        result["uncertainty"] = as_list(args.notes)
    else:
        result.setdefault("uncertainty", [])
    if args.changelog:
        result["changelog"] = as_list(args.changelog)
    else:
        result.setdefault("changelog", [])
    result["status"] = args.status

    d = os.path.dirname(args.out)
    if d:
        os.makedirs(d, exist_ok=True)
    json.dump(result, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": args.out, "status": args.status,
                      "embedded": {"deliverable_text": "deliverable_text" in result,
                                   "claims": len(claims) if isinstance(claims, list) else 0,
                                   "matrix": "claim_source_matrix" in result},
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
