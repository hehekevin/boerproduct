#!/usr/bin/env python3
"""decl_audit.py — 必备声明存在性机检 + 八分面覆盖审计（paper-compliance-audit）。

对 result.json 做两类确定性输出，回写三个键：
  result.declaration_audit  必备声明存在性机检：按关键词表（中英双语、大小写
                            不敏感）扫描稿件全文，逐项记录 detected/matched_
                            keywords/sections——这是机检证据，不是判定；声明
                            在正文之外（单独文件/投稿系统）时由 Agent 登记豁免。
  result.coverage           八分面/三类/严重度/章节计数 + 稿件规模统计
  result.unchecked          八分面之一或某章节零发现且未登记豁免的机械缺口清单
Agent 声明的 clearances[]（已查无问题/材料不可读的显式豁免）会抑制对应缺口。
机检只单向对账（verify_check 强制）：detected=false 的声明必须有一条
norm_missing 发现或豁免登记；detected=true 不强制有发现（关键词可能误命中，
由 Agent 语义判断）。

统计约定：英文词数用正则 [A-Za-z]+ 统计，不用 str.isalpha()——汉字
"字".isalpha()==True，会把中文全部误计为英文词（isalpha 汉字陷阱）。

**键归属**：本脚本只写 result.declaration_audit / result.coverage /
result.unchecked 三个键；self_check/gates/unbacked_numbers/validator_verdict
归 verify_check.py，gain_evidence/efficiency 归 gain_probe.py，其余归
build_skeleton + Agent。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 decl_audit.py --result /app/output/result.json --case /input/case.json \
        --input-root /input --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

FACETS = ("data_availability", "ethics", "conflict_of_interest", "author_contributions",
          "funding", "copyright_license", "reference_format", "duplicate_publication")
CATEGORIES = ("norm_missing", "norm_violation", "substantive_issue")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")

# 必备声明存在性机检关键词表（中英双语；匹配时全文小写化）
DECL_KEYWORDS = {
    "data_availability": ["数据可用性", "数据可用", "数据可获取", "数据共享", "原始数据",
                          "data availability", "data sharing", "available online"],
    "ethics": ["伦理", "知情同意", "irb", "ethics", "informed consent"],
    "conflict_of_interest": ["利益冲突", "conflict of interest", "competing interest",
                             "无利益冲突"],
    "author_contributions": ["作者贡献", "author contribution", "authors contributed", "credit taxonomy"],
    "funding": ["基金", "资助", "funding", "funded", "grant no", "grant number"],
    "copyright_license": ["版权", "许可", "授权", "copyright", "license", "permission", "cc by"],
}


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
        print("[decl_audit] 写盘失败 %s: %s" % (path, e))
        return False


def en_words(s):
    """英文词数：正则统计，规避 isalpha 的汉字误计陷阱。"""
    return len(re.findall(r"[A-Za-z]+", str(s or "")))


def section_strings(case):
    """提取 [(source_ref, text)]：优先稿件键下的 sections，每段一条；降级取全部长文本。"""
    items = []
    if not isinstance(case, dict):
        return items
    root = None
    for k in ("manuscript", "paper", "document", "full_text", "text", "body", "content"):
        if k in case and isinstance(case[k], (dict, list, str)):
            root = case[k]
            break
    if isinstance(root, dict):
        for sk in ("sections", "chapters", "parts"):
            v = root.get(sk)
            if isinstance(v, list) and v:
                for i, s in enumerate(v):
                    if isinstance(s, dict):
                        sid = s.get("section_id") or s.get("id") or ("S%d" % (i + 1))
                        items.append((str(sid), str(s.get("text") or s.get("content") or "")))
                    elif isinstance(s, str):
                        items.append(("S%d" % (i + 1), s))
                break
    if not items:
        buf = []

        def walk(o, ref):
            if isinstance(o, dict):
                for k2, v2 in o.items():
                    walk(v2, "%s.%s" % (ref, k2))
            elif isinstance(o, list):
                for i2, v2 in enumerate(o):
                    walk(v2, "%s[%d]" % (ref, i2))
            elif isinstance(o, str) and len(o.strip()) >= 4:
                buf.append((ref, o))
        walk({k2: v2 for k2, v2 in case.items() if k2 != "output_contract"}, "case")
        items = buf
    return items


def declaration_audit(case):
    """必备声明存在性机检（机械证据，非判定）。"""
    secs = section_strings(case)
    items = []
    for decl_id, kws in DECL_KEYWORDS.items():
        matched = []
        hit_sections = []
        for sid, text in secs:
            low = str(text or "").lower()
            for kw in kws:
                if kw.lower() in low:
                    matched.append(kw)
                    if sid not in hit_sections:
                        hit_sections.append(sid)
        items.append({
            "decl_id": decl_id,
            "name": {"data_availability": "数据可用性声明", "ethics": "伦理与知情同意声明",
                     "conflict_of_interest": "利益冲突声明", "author_contributions": "作者贡献声明",
                     "funding": "基金资助声明", "copyright_license": "版权与许可标注"}[decl_id],
            "detected": bool(matched),
            "matched_keywords": sorted(set(matched)),
            "sections": hit_sections,
        })
    return {
        "items": items,
        "run_by": "scripts/decl_audit.py（关键词机检，中英双语、大小写不敏感）",
        "note": "机检证据非判定：detected=false 的声明必须有一条 norm_missing 发现或"
                " clearances/material_gaps 豁免登记；detected=true 不强制有发现"
                "（关键词可能误命中，由 Agent 语义判断）。声明在投稿系统或单独文件中"
                "时按材料实际情况登记，不凭空判缺。",
    }


def audit(res, case, input_root):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    overview = inner.get("manuscript_overview") or {}
    sections = [s for s in (overview.get("sections") or []) if isinstance(s, dict)]
    cleared = {str(c.get("scope")) for c in (inner.get("clearances") or [])
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
                              "reason": "八分面之一零发现且未登记豁免（clearances），须复核是否漏查"})
    for s in sections:
        sid = str(s.get("section_id") or "")
        if sid and per_section.get(sid, 0) == 0 and "section:%s" % sid not in cleared:
            unchecked.append({"scope": "section:%s" % sid,
                              "reason": "该章节零发现且未登记豁免（clearances），须复核是否漏查或登记已查清"})

    all_text = "".join(t for _r, t in section_strings(case))
    stats = {"chars": len(all_text), "en_words": en_words(all_text),
             "note": "字符数按稿件正文计；英文词数用正则统计（规避 isalpha 汉字陷阱）"}
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
        "note": "由 decl_audit.py 机械计数生成；unchecked 为机械缺口清单，"
                "非空时 verdict 不得为 audited（verify_check 强制）。",
    }
    return declaration_audit(case), coverage, unchecked


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--input-root", default="/input")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 declaration_audit/coverage/unchecked 回写 result.json")
        args = ap.parse_args()
    except SystemExit as e:
        print("[decl_audit] 参数解析失败（argparse 退出码 %s，已降级为 exit 0）" % e)
        return 0
    except Exception as e:
        print("[decl_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[decl_audit] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    decl, coverage, unchecked = audit(res, case if isinstance(case, dict) else {}, args.input_root)

    if args.out:
        save_json(args.out, {"declaration_audit": decl, "coverage": coverage, "unchecked": unchecked})
    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["declaration_audit"] = decl
            cur["result"]["coverage"] = coverage
            cur["result"]["unchecked"] = unchecked
            save_json(args.result, cur)

    missing = [d["decl_id"] for d in decl["items"] if not d["detected"]]
    print("[decl_audit] 声明机检: %d/%d 项检出（未检出: %s）"
          % (len(decl["items"]) - len(missing), len(decl["items"]), ",".join(missing) or "无"))
    print("[decl_audit] findings=%d（confirmed=%d pending=%d suppressed=%d）| 章节 %d/%d 有发现"
          % (coverage["total_findings"], coverage["confirmed"], coverage["pending"],
             coverage["suppressed"], coverage["sections_with_findings"], coverage["total_sections"]))
    print("  facet_counts=%s" % coverage["facet_counts"])
    zero_facets = [k for k, v in coverage["facet_counts"].items() if v == 0]
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
        print("[decl_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
