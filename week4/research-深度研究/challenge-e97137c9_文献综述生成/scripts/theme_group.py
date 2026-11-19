#!/usr/bin/env python3
"""theme_group.py — 主题覆盖机械核对（lit-review-bind）。

对 result.json 的主题分组做三项机械核对并**机械计算** result.coverage（键归属：
本脚本独占 coverage 键）：
  1. 归属完整：label=keep 的文献必须归属 ≥1 个主题（themes[].paper_ids），
     未归属的必须在 omissions[] 登记遗漏原因——主题既不重叠遗漏也不静默丢文献。
  2. 主题有效：每个主题 paper_ids 非空、标题非空、basis 非空（主题必须从文献
     里长出来，不是套通用框架）；重复出现在多个主题的文献登记 overlap 供人复核。
  3. 覆盖计算：total/included/cited_in_outline/uncited/omissions_registered/ratio
     全部由脚本按实际数据重算覆盖写入，不采信手填数字。

用法：
    python3 theme_group.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/theme_group.json] [--emit-into] [--ablate all|coverage,theme]
退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


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
        print("[theme_group] 写盘失败 %s: %s" % (path, e))
        return False


def analyze(res, ablate="none"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "disabled_checks": [],
              "ablate": ablate, "coverage_recomputed": None, "theme_overlap": []}
    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    if off("theme"):
        report["disabled_checks"].append("theme")
    if off("coverage"):
        report["disabled_checks"].append("coverage")

    inner = (res or {}).get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        return report

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    themes = [t for t in (inner.get("themes") or []) if isinstance(t, dict)]
    omissions = [o for o in (inner.get("omissions") or []) if isinstance(o, dict)]

    # ---- 文献身份索引 ----
    all_ids = {str(it.get("paper_id")) for it in items if it.get("paper_id")}
    keep_ids = {str(it.get("paper_id")) for it in items
                if it.get("paper_id") and it.get("label") == "keep"}
    theme_map = {}   # paper_id -> [theme_id]
    for t in themes:
        tid = str(t.get("theme_id") or "themes[?]")
        pids = [str(x) for x in (t.get("paper_ids") or [])]
        if not off("theme"):
            if not pids:
                report["problems"].append("主题 %s 无文献支撑（paper_ids 空）" % tid)
            if not str(t.get("title") or "").strip():
                report["problems"].append("主题 %s 缺 title" % tid)
            if not str(t.get("basis") or "").strip():
                report["problems"].append("主题 %s 缺 basis（主题归纳依据）" % tid)
            for pid in pids:
                if pid not in all_ids:
                    report["problems"].append("主题 %s 引用了不存在的文献 %s" % (tid, pid))
        for pid in pids:
            theme_map.setdefault(pid, []).append(tid)
    for pid, tids in sorted(theme_map.items()):
        if len(tids) > 1:
            report["theme_overlap"].append({"paper_id": pid, "theme_ids": tids})

    # ---- keep 归属完整 / 遗漏登记 ----
    for it in items:
        pid = str(it.get("paper_id") or "")
        if it.get("label") != "keep":
            continue
        assigned = theme_map.get(pid) or []
        registered = any(str(o.get("paper_id")) == pid for o in omissions)
        ok = bool(assigned) or registered
        report["self_check"].append({"item": "items[%s].theme_assigned" % pid,
                                     "template_value": "keep ⇒ 归属≥1主题或登记遗漏",
                                     "applied": not off("theme"), "match": ok})
        if not off("theme") and not ok:
            report["problems"].append("keep 文献 %s 未归属任何主题且未登记 omissions" % pid)

    # ---- coverage 机械重算 ----
    outline = inner.get("outline") or {}
    cited = set()
    for s in (outline.get("sections") or []):
        if not isinstance(s, dict):
            continue
        for p in (s.get("paragraphs") or []):
            if isinstance(p, dict):
                for sid in (p.get("source_ids") or []):
                    cited.add(str(sid))
    if not cited:
        # 兜底：大纲未写时用主题归属近似（并在 note 说明口径）
        cited = set(theme_map.keys())
    uncited = sorted(keep_ids - cited)
    omissions_registered = sum(1 for o in omissions
                               if str(o.get("paper_id")) in keep_ids
                               and str(o.get("reason") or "").strip())
    cov = {"total_papers": len(items), "included_papers": len(keep_ids),
           "cited_in_outline": len(cited & keep_ids),
           "uncited": len(uncited),
           "omissions_registered": omissions_registered,
           "uncited_ids": uncited,
           "ratio": round((len(cited & keep_ids) / len(keep_ids)), 4) if keep_ids else None,
           "note": "theme_group.py 机械重算覆盖（不入大纲的 keep 文献必须登记 omissions）"}
    report["coverage_recomputed"] = cov

    if not off("coverage"):
        for pid in uncited:
            registered = any(str(o.get("paper_id")) == pid for o in omissions)
            report["self_check"].append({"item": "uncited_registered[%s]" % pid,
                                         "template_value": "uncited ⇒ 登记 omissions",
                                         "applied": True, "match": registered})
            if not registered:
                report["problems"].append("keep 文献 %s 未进入大纲任何段落（uncited）"
                                          "且未登记 omissions" % pid)
        cov_mismatch = []
        stored = inner.get("coverage")
        if isinstance(stored, dict):
            cov_mismatch = [k for k in ("total_papers", "included_papers", "cited_in_outline",
                                        "uncited", "omissions_registered")
                            if isinstance(stored.get(k), int) and stored.get(k) != cov[k]]
            for k in cov_mismatch:
                report["problems"].append("coverage.%s 手填值 %s 与机械重算 %s 不符"
                                          % (k, stored.get(k), cov[k]))
        report["self_check"].append({"item": "coverage.consistency",
                                     "template_value": "coverage 手填值 = 机械重算值",
                                     "applied": True, "match": not cov_mismatch})

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把重算的 coverage 写回 result.result.coverage（键归属本脚本）")
        ap.add_argument("--ablate", default="none", help="none | all | theme,coverage 子集")
        args = ap.parse_args()
    except Exception as e:
        print("[theme_group] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[theme_group] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        save_json(args.out, {"verdict": "FAIL", "problems": ["result.json 不可解析"],
                              "self_check": [], "disabled_checks": [], "ablate": args.ablate})
        return 0

    report = analyze(res, ablate=args.ablate)
    if args.emit_into and not (args.ablate == "all" or "coverage" in str(args.ablate).split(",")):
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["coverage"] = report["coverage_recomputed"]
                save_json(args.result, cur)
        except Exception as e:
            print("[theme_group] 回写 coverage 失败: %s" % e)
    save_json(args.out, report)

    if report["verdict"] == "PASS":
        print("[theme_group] PASS（ablate=%s，检查项 %d 条；覆盖 %s）"
              % (args.ablate, len(report["self_check"]),
                 {k: v for k, v in (report["coverage_recomputed"] or {}).items()
                  if k not in ("uncited_ids", "note")}))
    else:
        print("[theme_group] FAIL（%d 处，不中断交付；ablate=%s）:" % (len(report["problems"]), args.ablate))
        for p in report["problems"][:20]:
            print("  - %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[theme_group] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
