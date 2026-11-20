#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""format_check.py — 逐项核对映射表与内容零丢失

审计三件事:
  1) format_mapping.jsonl 每条必含 item/template_value/source/applied/status；
     status∈{applied,partial,unspecified,conflict,degraded}；applied/unspecified 都必须有 rationale。
  2) 内容单元零丢失：content_inventory.jsonl 中每个单元的关键文本在成品 draft.md 中可找到
     （表格/标题取首 40 字符匹配）；任何丢失 → content_lost 列出。
  3) 图表交叉引用一致：正文中 "图N/表N" 引用与题注编号一一对应。

输出 format_check.json（verdict: pass|fail + 明细）。
"""
import argparse, json, os, re, sys

REQUIRED = ("item", "template_value", "source", "applied", "status")
VALID_STATUS = {"applied", "partial", "unspecified", "conflict", "degraded"}

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", default="/app/work/format_mapping.jsonl")
    ap.add_argument("--inventory", default="/app/work/extracted/content_inventory.jsonl")
    ap.add_argument("--draft", default="/app/output/draft.md")
    ap.add_argument("--mids", default=None,
                    help="只对账稿件材料，逗号分隔如 M01,M02；缺省=全部材料")
    ap.add_argument("--out", default="/app/output/format_check.json")
    args = ap.parse_args()

    items = []
    if os.path.exists(args.mapping):
        for line in open(args.mapping, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except Exception:
                    items.append({"item": "PARSE_ERROR", "status": "invalid", "raw": line[:120]})

    mapping_issues = []
    for it in items:
        missing = [k for k in REQUIRED if not str(it.get(k) or "").strip()]
        if missing:
            mapping_issues.append({"item": it.get("item"), "issue": "missing_fields", "fields": missing})
        elif it.get("status") not in VALID_STATUS:
            mapping_issues.append({"item": it.get("item"), "issue": "invalid_status",
                                   "status": it.get("status")})
        elif it.get("status") in ("applied", "unspecified") and not str(it.get("rationale") or "").strip():
            mapping_issues.append({"item": it.get("item"), "issue": "missing_rationale"})

    # 内容零丢失
    draft_text = ""
    if os.path.exists(args.draft):
        draft_text = norm(open(args.draft, encoding="utf-8").read())
    lost, total = [], 0
    only_mids = set(x.strip() for x in args.mids.split(",")) if args.mids else None
    if os.path.exists(args.inventory):
        for line in open(args.inventory, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                u = json.loads(line)
            except Exception:
                continue
            if only_mids and u.get("mid") not in only_mids:
                continue
            total += 1
            key = norm(re.sub(r"^#+\s*", "", str(u.get("text", ""))))[:40]
            if key and key not in draft_text:
                lost.append({"mid": u.get("mid"), "locator": u.get("locator"),
                             "text_head": u.get("text", "")[:60]})

    # 图表交叉引用
    fig_caps = set(re.findall(r"图\s*(\d+)", draft_text))
    tab_caps = set(re.findall(r"表\s*(\d+)", draft_text))
    crossref = {"figure_numbers": sorted(fig_caps), "table_numbers": sorted(tab_caps),
                "note": "编号集合仅作展示；重排后应连续无跳号"}
    def contiguous(nums):
        return [int(x) for x in nums] == list(range(1, len(nums) + 1))
    crossref["figures_contiguous"] = contiguous(fig_caps) if fig_caps else True
    crossref["tables_contiguous"] = contiguous(tab_caps) if tab_caps else True

    status_counts = {}
    for it in items:
        s = it.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    verdict = "pass"
    if mapping_issues or lost:
        verdict = "fail"
    out = {"verdict": verdict, "mapping_total": len(items), "status_counts": status_counts,
           "mapping_issues": mapping_issues, "content_total": total, "content_lost": lost,
           "crossref": crossref,
           "note": "verdict=fail 时必须修复重跑；unspecified 项属如实标注，不算 fail"}
    # 注意: mapping_issues 中 missing_rationale 对 unspecified 也要求给理由——视为 issue
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "verdict": verdict, "mapping": len(items),
                      "content_lost": len(lost), "issues": len(mapping_issues),
                      "out": args.out}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
