#!/usr/bin/env python3
"""coverage_audit.py — 六项覆盖与章节覆盖机械审计（paper-review-audit）。

对 result.json 的 findings[] 做确定性计数审计，回写两个键：
  result.coverage   分面/类别/严重度/章节计数 + 稿件规模统计
  result.unchecked  六项之一或某章节零发现且未登记豁免的机械缺口清单
Agent 声明的 clearances[]（已查无问题/材料不可读的显式豁免）会抑制对应缺口。

统计约定：英文词数用正则 [A-Za-z]+ 统计，不用 str.isalpha()——汉字
"字".isalpha()==True，会把中文全部误计为英文词（isalpha 汉字陷阱）。

**键归属**：本脚本只写 result.coverage 与 result.unchecked 两个键；
self_check/gates/unbacked_numbers/validator_verdict 归 verify_check.py，
gain_evidence/efficiency 归 gain_probe.py，其余归 build_skeleton + Agent。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 coverage_audit.py --result /app/output/result.json --case /input/case.json \
        --input-root /input --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("fact_check", "citation_support", "method_design", "stat_reporting",
          "argument_chain", "integrity_norms")
CATEGORIES = ("fact_error", "insufficient_evidence", "norm_issue", "suggestion")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")


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
        print("[coverage_audit] 写盘失败 %s: %s" % (path, e))
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


def audit(res, case, input_root):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    overview = inner.get("manuscript_overview") or {}
    sections = [s for s in (overview.get("sections") or []) if isinstance(s, dict)]
    clearances = {str(c.get("scope")) for c in (inner.get("clearances") or [])
                  if isinstance(c, dict) and c.get("scope")}

    facet_counts = {k: 0 for k in FACETS}
    cat_counts = {k: 0 for k in CATEGORIES}
    sev_counts = {k: 0 for k in SEVERITIES}
    status_counts = {k: 0 for k in STATUSES}
    per_section = {}
    judged = 0
    for f in findings:
        if f.get("facet") in facet_counts:
            facet_counts[f.get("facet")] += 1
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

    unchecked = []
    for k, v in facet_counts.items():
        if v == 0 and "facet:%s" % k not in cleared:
            unchecked.append({"scope": "facet:%s" % k,
                              "reason": "六项之一零发现且未登记豁免（clearances），须复核是否漏查"})
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
        "category_counts": cat_counts,
        "severity_counts": sev_counts,
        "per_section": dict(sorted(per_section.items())),
        "manuscript_stats": stats,
        "input_files": n_files,
        "note": "由 coverage_audit.py 机械计数生成；unchecked 为机械缺口清单，"
                "非空时 verdict 不得为 audited（verify_check 强制）。",
    }
    return coverage, unchecked


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 coverage/unchecked 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[coverage_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[coverage_audit] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    coverage, unchecked = audit(res, case if isinstance(case, dict) else {}, args.input_root)

    if args.out:
        save_json(args.out, {"coverage": coverage, "unchecked": unchecked})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["coverage"] = coverage
            cur["result"]["unchecked"] = unchecked
            save_json(args.result, cur)

    zero_facets = [k for k, v in coverage["facet_counts"].items() if v == 0]
    print("[coverage_audit] findings=%d（confirmed=%d pending=%d suppressed=%d）| 章节 %d/%d 有发现"
          % (coverage["total_findings"], coverage["confirmed"], coverage["pending"],
             coverage["suppressed"], coverage["sections_with_findings"], coverage["total_sections"]))
    print("  facet_counts=%s" % coverage["facet_counts"])
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
        print("[coverage_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
