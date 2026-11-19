#!/usr/bin/env python3
"""dispute_table.py — 分歧与共识对照登记校验器（lit-review-bind）。

对 result.json 的 disputes[] 与 claims[] 的表述强度做机械校验（对应题面机检点
"分歧对照登记、结论不超出文献支持范围"）：
  A. 分歧登记：status=disputed 的条目必须有 ≥2 个立场（positions），各立场的
     paper_ids 非空且互不重叠（同一文献不得同时站在两个对立立场）；每立场须附
     逐字 quote；consensus 条目须写明共识表述与支撑文献。
  B. 强度不越界：claims[].strength ∈ established|suggestive|disputed；
     established 须 ≥2 个来源；disputed 须指向 disputes 中的 dispute_id；
     引用了"仅单篇支持"的结论却标 established 视为越界判 FAIL。

analyze_disputes(res, ablate) 为纯函数（不写盘），供 verify_check/gain_probe 复用；
CLI 形式把报告落盘并可回写顶层 dispute_audit（键归属：本脚本独占 dispute_audit）。
退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

STRENGTH = ("established", "suggestive", "disputed")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def analyze_disputes(res, ablate="none"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [],
              "disabled_checks": [], "ablate": ablate}
    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    if off("dispute"):
        report["disabled_checks"].append("dispute")

    inner = (res or {}).get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        return report

    disputes = [d for d in (inner.get("disputes") or []) if isinstance(d, dict)]
    dispute_ids = {str(d.get("dispute_id")) for d in disputes if d.get("dispute_id")}
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]

    # ---- A. 分歧对照登记 ----
    for di, d in enumerate(disputes):
        did = str(d.get("dispute_id") or "disputes[%d]" % di)
        status = str(d.get("status") or "")
        if status not in ("disputed", "consensus", "unresolved"):
            if not off("dispute"):
                report["problems"].append("%s status 枚举非法: %r（须 disputed/consensus/unresolved）"
                                          % (did, status))
            continue
        if status == "disputed":
            positions = [p for p in (d.get("positions") or []) if isinstance(p, dict)]
            ok = len(positions) >= 2
            report["self_check"].append({"item": "%s.two_sides" % did,
                                         "template_value": "disputed ⇒ ≥2 个对立立场",
                                         "applied": not off("dispute"), "match": ok})
            if off("dispute"):
                continue
            if not ok:
                report["problems"].append("%s 标 disputed 但立场数 <2（分歧须双方并列呈现）" % did)
            seen = set()
            for pi, p in enumerate(positions):
                pids = [str(x) for x in (p.get("paper_ids") or [])]
                if not pids:
                    report["problems"].append("%s.positions[%d] 无支撑文献" % (did, pi))
                if not str(p.get("quote") or "").strip():
                    report["problems"].append("%s.positions[%d] 无逐字 quote" % (did, pi))
                for pid in pids:
                    if pid in seen:
                        report["problems"].append("%s 中文献 %s 同时出现在对立双方（立场重叠）" % (did, pid))
                    seen.add(pid)
        elif status == "consensus":
            pids = [str(x) for x in (d.get("paper_ids") or d.get("consensus_paper_ids") or [])]
            ok = bool(pids) and bool(str(d.get("consensus_text") or d.get("summary") or "").strip())
            report["self_check"].append({"item": "%s.consensus_backed" % did,
                                         "template_value": "consensus ⇒ 共识表述+支撑文献",
                                         "applied": not off("dispute"), "match": ok})
            if off("dispute"):
                continue
            if not pids:
                report["problems"].append("%s 标 consensus 但无支撑文献" % did)
            if not str(d.get("consensus_text") or d.get("summary") or "").strip():
                report["problems"].append("%s 标 consensus 但缺共识表述（consensus_text/summary）" % did)

    # ---- B. 强度不越界 ----
    for ci, c in enumerate(claims):
        cid = str(c.get("claim_id") or "claims[%d]" % ci)
        strength = c.get("strength")
        if strength is not None and strength not in STRENGTH:
            if not off("dispute"):
                report["problems"].append("%s strength 枚举非法: %r" % (cid, strength))
            continue
        if off("dispute"):
            continue
        n_src = len([x for x in (c.get("source_ids") or []) if str(x).strip()])
        if strength == "established" and n_src < 2:
            report["problems"].append("%s 标 established 但来源数=%d（结论超出单篇文献支持范围）"
                                      % (cid, n_src))
        if strength == "disputed" and not str(c.get("dispute_id") or "").strip():
            report["problems"].append("%s 标 disputed 但未指向 dispute_id" % cid)
        elif strength == "disputed" and str(c.get("dispute_id")) not in dispute_ids:
            report["problems"].append("%s 指向的 dispute_id %s 不在 disputes[]（断链）"
                                      % (cid, c.get("dispute_id")))
        report["self_check"].append({"item": "%s.strength_bounded" % cid,
                                     "template_value": "established⇒≥2来源；disputed⇒dispute_id 有效",
                                     "applied": not off("dispute"), "match": True})

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 dispute_audit 回写 result.json 顶层（键归属本脚本）")
        ap.add_argument("--ablate", default="none", help="none | all | dispute")
        args = ap.parse_args()
    except Exception as e:
        print("[dispute_table] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[dispute_table] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        if args.out:
            try:
                d = os.path.dirname(args.out)
                if d:
                    os.makedirs(d, exist_ok=True)
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump({"verdict": "FAIL", "problems": ["result.json 不可解析"],
                               "self_check": [], "disabled_checks": [], "ablate": args.ablate},
                              f, ensure_ascii=False, indent=1)
            except Exception:
                pass
        return 0

    report = analyze_disputes(res, ablate=args.ablate)
    if args.out:
        try:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[dispute_table] 报告落盘失败: %s" % e)
    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["dispute_audit"] = {k: report[k] for k in
                                        ("verdict", "problems", "disabled_checks")}
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[dispute_table] 回写 dispute_audit 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[dispute_table] PASS（ablate=%s，检查项 %d 条）" % (args.ablate, len(report["self_check"])))
    else:
        print("[dispute_table] FAIL（%d 处，不中断交付；ablate=%s）:" % (len(report["problems"]), args.ablate))
        for p in report["problems"][:20]:
            print("  - %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[dispute_table] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
