#!/usr/bin/env python3
"""chain_audit.py — 论证链节点完备与覆盖机械审计（argchain-review）。

对 result.json 做确定性计数审计，回写三个键：
  result.chain_audit  每条论证链的节点完备性（缺 premise/hypothesis、缺
                      conclusion、节点数<2、节点引文过短）+ 汇总计数
  result.coverage     分面/问题类型/类别/严重度/章节计数 + 稿件规模统计
  result.unchecked    零发现分面/章节、不完备链且未登记豁免的机械缺口清单
Agent 声明的 clearances[]（已查无问题/材料不可读的显式豁免）会抑制对应缺口。

统计约定：英文词数用正则 [A-Za-z]+ 统计，不用 str.isalpha()——汉字
"字".isalpha()==True，会把中文全部误计为英文词（isalpha 汉字陷阱）。

**键归属**：本脚本只写 result.chain_audit / result.coverage / result.unchecked
三个键；self_check/gates/unbacked_numbers/validator_verdict 归 verify_check.py，
gain_evidence/efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 chain_audit.py --result /app/output/result.json --case /input/case.json \
        --input-root /input --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("argument_chain", "strength_match", "rebuttal_coverage", "cross_section",
          "fact_check", "integrity_norms")
ISSUE_TYPES = ("broken_chain", "circular_reasoning", "correlation_causation",
               "over_extrapolation", "strength_mismatch", "missing_rebuttal")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
ROLES = ("hypothesis", "premise", "reasoning", "conclusion")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[chain_audit] 写盘失败 %s: %s" % (path, e))
        return False


def en_words(s):
    """英文词数：正则统计，规避 isalpha 的汉字误计陷阱。"""
    return len(re.findall(r"[A-Za-z]+", str(s or "")))


def collect_text(o):
    buf = []
    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            buf.append(x)
    walk(o)
    return "".join(buf)


def audit_chains(res):
    """机械审计每条链的节点完备性。返回 (chain_audit, chain_unchecked)。"""
    inner = (res or {}).get("result") or {}
    chains = [c for c in (inner.get("argument_chains") or []) if isinstance(c, dict)]
    per_chain = []
    unchecked = []
    for ci, ch in enumerate(chains):
        cid = str(ch.get("chain_id") or ci)
        nodes = [n for n in (ch.get("nodes") or []) if isinstance(n, dict)]
        roles = [str(n.get("role") or "") for n in nodes]
        bad_roles = sorted({r for r in roles if r not in ROLES})
        has_premise = ("premise" in roles) or ("hypothesis" in roles)
        has_concl = "conclusion" in roles
        short_quotes = [str(n.get("node_id") or i) for i, n in enumerate(nodes)
                        if len(str(n.get("quote") or "").strip()) < 6]
        issues = []
        if len(nodes) < 2:
            issues.append("节点数<2，不足以构成论证链")
        if not has_premise:
            issues.append("缺 premise/hypothesis 节点")
        if not has_concl:
            issues.append("缺 conclusion 节点")
        if bad_roles:
            issues.append("非法节点角色: %s" % ",".join(bad_roles))
        if short_quotes:
            issues.append("节点引文过短或缺失: %s" % ",".join(short_quotes))
        per_chain.append({"chain_id": cid, "name": str(ch.get("name") or ""),
                          "node_count": len(nodes),
                          "role_counts": {r: roles.count(r) for r in ROLES if roles.count(r)},
                          "complete": not issues, "issues": issues})
        if issues:
            unchecked.append({"scope": "chain:%s" % cid,
                              "reason": "论证链节点完备性违规（%s），须补节点或登记豁免" % "；".join(issues)})
    summary = {"total_chains": len(chains), "complete_chains": sum(1 for c in per_chain if c["complete"]),
               "incomplete_chains": sum(1 for c in per_chain if not c["complete"]),
               "total_nodes": sum(c["node_count"] for c in per_chain), "per_chain": per_chain,
               "note": "由 chain_audit.py 机械审计；incomplete_chains>0 时对应链落 unchecked"}
    return summary, unchecked


def audit(res, case, input_root):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    overview = inner.get("manuscript_overview") or {}
    sections = [s for s in (overview.get("sections") or []) if isinstance(s, dict)]
    clearances = {str(c.get("scope")) for c in (inner.get("clearances") or [])
                  if isinstance(c, dict) and c.get("scope")}
    cleared = clearances

    chain_audit, chain_unchecked = audit_chains(res)

    facet_counts = {k: 0 for k in FACETS}
    issue_counts = {k: 0 for k in ISSUE_TYPES}
    cat_counts = {k: 0 for k in CATEGORIES}
    sev_counts = {k: 0 for k in SEVERITIES}
    status_counts = {k: 0 for k in STATUSES}
    per_section = {}
    judged = 0
    for f in findings:
        if f.get("facet") in facet_counts:
            facet_counts[f.get("facet")] += 1
        if f.get("issue_type") in issue_counts:
            issue_counts[f.get("issue_type")] += 1
        if f.get("category") in cat_counts:
            cat_counts[f.get("category")] += 1
        if f.get("severity") in sev_counts:
            sev_counts[f.get("severity")] += 1
        if f.get("status") in status_counts:
            status_counts[f.get("status")] += 1
        if f.get("judged") is True:
            judged += 1
        sid = str(f.get("section_id") or "")
        if sid:
            per_section[sid] = per_section.get(sid, 0) + 1

    sections_with = sum(1 for s in sections if per_section.get(str(s.get("section_id")), 0) > 0)

    unchecked = list(chain_unchecked)
    for k, v in facet_counts.items():
        if v == 0 and "facet:%s" % k not in cleared:
            unchecked.append({"scope": "facet:%s" % k,
                              "reason": "六分面之一零发现且未登记豁免（clearances），须复核是否漏查"})
    for s in sections:
        sid = str(s.get("section_id") or "")
        if sid and per_section.get(sid, 0) == 0 and "section:%s" % sid not in cleared:
            unchecked.append({"scope": "section:%s" % sid,
                              "reason": "该章节零发现且未登记豁免（clearances），须复核是否漏查或登记已查清"})

    stats = {"chars": len(collect_text(case)), "en_words": en_words(collect_text(case)),
             "note": "字符数按全部 case 文本计；英文词数用正则统计（规避 isalpha 汉字陷阱）"}
    n_files = 0
    try:
        for _dp, _dn, fn in os.walk(input_root):
            n_files += len(fn)
    except Exception:
        pass

    coverage = {
        "total_sections": len(sections),
        "sections_with_findings": sections_with,
        "total_findings": len(findings),
        "judged": judged,
        "confirmed": status_counts["confirmed"],
        "pending": status_counts["pending"],
        "suppressed": status_counts["suppressed"],
        "facet_counts": facet_counts,
        "issue_type_counts": issue_counts,
        "category_counts": cat_counts,
        "severity_counts": sev_counts,
        "per_section": dict(sorted(per_section.items())),
        "manuscript_stats": stats,
        "input_files": n_files,
        "note": "由 chain_audit.py 机械计数生成；unchecked 为机械缺口清单（含链完备违规），"
                "非空时 verdict 不得为 audited（verify_check 强制）。",
    }
    return coverage, unchecked, chain_audit


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 coverage/unchecked/chain_audit 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[chain_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[chain_audit] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    coverage, unchecked, chain_audit = audit(res, case if isinstance(case, dict) else {}, args.input_root)

    if args.out:
        save_json(args.out, {"coverage": coverage, "unchecked": unchecked, "chain_audit": chain_audit})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["coverage"] = coverage
            cur["result"]["unchecked"] = unchecked
            cur["result"]["chain_audit"] = chain_audit
            save_json(args.result, cur)

    zero_facets = [k for k, v in coverage["facet_counts"].items() if v == 0]
    print("[chain_audit] findings=%d（confirmed=%d pending=%d suppressed=%d）| 章节 %d/%d 有发现"
          % (coverage["total_findings"], coverage["confirmed"], coverage["pending"],
             coverage["suppressed"], coverage["sections_with_findings"], coverage["total_sections"]))
    print("  链审计: %d 条链，完备 %d 条，不完备 %d 条，节点 %d 个"
          % (chain_audit["total_chains"], chain_audit["complete_chains"],
             chain_audit["incomplete_chains"], chain_audit["total_nodes"]))
    print("  facet_counts=%s" % coverage["facet_counts"])
    print("  issue_type_counts=%s" % coverage["issue_type_counts"])
    if zero_facets:
        print("  WARN: 零发现分面: %s" % ",".join(zero_facets))
    print("  unchecked=%d 项" % len(unchecked))
    for u in unchecked[:10]:
        print("  - %s: %s" % (u["scope"], u["reason"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[chain_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
