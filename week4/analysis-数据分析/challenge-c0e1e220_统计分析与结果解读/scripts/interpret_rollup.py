#!/usr/bin/env python3
"""interpret_rollup.py — 解读强度机械汇总（stat-analysis-audit）。

按 result.claim_rules（或 --rules 指定的台账）对每组分析机械复算：
  strength_allowed = strength_map[design_type]（设计类型允许的最高结论强度）
  causal_verbs_found = 因果动词词表在 claim.text 中的命中（子串匹配，不依赖 isalpha）
  overclaim = 强度序（descriptive < associative < causal）超过允许值
  causal_ok = 非（观察性/相关性设计 且 命中因果动词）
  strength_final = overclaim 时降级到允许值（过强结论降级）
并把结果写入 result.interpret_summary（**键归属：本脚本只写 interpret_summary
这一个键**，与 verify_check / gain_probe / build_skeleton / stat_recompute 不冲突）。

用法：
    python3 interpret_rollup.py --result /app/output/result.json \
        [--rules /app/work/claim_rules.json] [--dry-run]
退出码恒为 0（失败以 problems 报告，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

JUD = ("supported", "concerns", "inadequate", "unreported", "not_applicable", "unassessable")
STRENGTH_ORDER = {"descriptive": 0, "insufficient": 0, "associative": 1, "causal": 2}


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
        print("[interpret_rollup] 写盘失败 %s: %s" % (path, e))
        return False


def marker_note():
    m = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    return bool(os.path.exists(m))


def rules_valid(rules):
    if not isinstance(rules, dict):
        return False
    need = ("strength_map", "causal_verbs", "penalty_map", "thresholds")
    if not all(k in rules for k in need):
        return False
    return all(j in rules.get("penalty_map", {}) for j in JUD)


def rollup(analysis, rules):
    """机械复算单组分析：罚分、结论强度、因果约束、降级。"""
    text = str((analysis.get("claim") or {}).get("text") or "")
    text_low = text.lower()
    design = str(analysis.get("design_type") or "unknown")
    sm = rules["strength_map"]
    allowed = sm.get(design) or sm.get("unknown") or "descriptive"
    claimed = str((analysis.get("claim") or {}).get("claim_strength") or "").strip().lower()
    verbs = [str(v) for v in (rules.get("causal_verbs") or [])]
    found = [v for v in verbs if (v.lower() in text_low)]
    overclaim = bool(claimed and claimed in STRENGTH_ORDER and allowed in STRENGTH_ORDER
                     and STRENGTH_ORDER[claimed] > STRENGTH_ORDER[allowed])
    observational = design in ("observational", "correlational", "quasi_experimental")
    causal_ok = not (observational and found)
    strength_final = allowed if overclaim else (claimed or allowed)
    # 罚分与弃权
    total, abstained = 0, 0
    counts = {"high": 0, "medium": 0, "low": 0, "uncertain": 0, "none_grade": 0}
    dirs = []
    for ap in analysis.get("appraisals") or []:
        if not isinstance(ap, dict):
            continue
        j = ap.get("judgment")
        total += int(rules["penalty_map"].get(j, 0) or 0)
        g = ap.get("grade")
        counts[str(g) if g in ("high", "medium", "low", "uncertain") else "none_grade"] += 1
        if j == "unassessable":
            abstained += 1
        if ap.get("bias_direction") in ("favors_conclusion", "against_conclusion"):
            dirs.append(ap["bias_direction"])
    th = rules["thresholds"]
    band = "unknown"
    for name in ("low", "some_concerns", "high"):
        rng = th.get(name) or []
        if len(rng) == 2 and rng[0] <= total <= rng[1]:
            band = {"low": "low", "some_concerns": "medium", "high": "high"}[name]
            break
    overall = band
    if abstained >= 2 or (abstained >= 1 and band == "low"):
        overall = "uncertain"
    if not causal_ok:
        overall = "high" if band == "high" else overall
    if any(d == "against_conclusion" for d in dirs):
        direction = "against_conclusion"
    elif any(d == "favors_conclusion" for d in dirs):
        direction = "favors_conclusion"
    else:
        direction = "unclear"
    flaws = sum(1 for ap in (analysis.get("appraisals") or []) if isinstance(ap, dict)
                and ap.get("category") == "method_error")
    rgaps = sum(1 for ap in (analysis.get("appraisals") or []) if isinstance(ap, dict)
                and ap.get("category") == "reporting_gap")
    return {"analysis_id": analysis.get("analysis_id"), "design_type": design,
            "strength_allowed": allowed, "strength_claimed": claimed or None,
            "strength_final": strength_final, "overclaim": overclaim,
            "causal_verbs_found": found, "causal_ok": causal_ok,
            "penalty_total": total, "band": band, "overall": overall,
            "direction": direction, "abstained": abstained,
            "method_errors": flaws, "reporting_gaps": rgaps, "grade_counts": counts}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--rules", default="/app/work/claim_rules.json")
        ap.add_argument("--dry-run", action="store_true", help="只打印复算结果，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[interpret_rollup] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[interpret_rollup] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）" % args.result)
        return 0
    rules = load_json(args.rules) if os.path.exists(args.rules) else None
    if not rules_valid(rules):
        rules = res["result"].get("claim_rules")
    if not rules_valid(rules):
        print("[interpret_rollup] FAIL: claim_rules 缺失或非法（须含 strength_map/causal_verbs/"
              "penalty_map/thresholds 且 declared_at 非空）；本脚本不臆造口径，请先声明。")
        return 0

    analyses = [a for a in (res["result"].get("analyses") or []) if isinstance(a, dict)]
    per_analysis = []
    for a in analyses:
        try:
            per_analysis.append(rollup(a, rules))
        except Exception as e:
            problems.append("%s 复算异常: %s" % (a.get("analysis_id"), e))

    interpret_summary = {
        "computed_by": "scripts/interpret_rollup.py",
        "rules_version": str(rules.get("version") or "undeclared"),
        "declared_at": rules.get("declared_at"),
        "marker_hit": marker_note(),
        "per_analysis": per_analysis,
        "totals": {"analyses": len(analyses),
                   "overclaims": sum(1 for x in per_analysis if x.get("overclaim")),
                   "causal_violations": sum(1 for x in per_analysis if not x.get("causal_ok")),
                   "downgrades": sum(1 for x in per_analysis if x.get("overclaim"))},
    }

    if args.dry_run:
        print("[interpret_rollup] dry-run（不写盘）marker_hit=%s" % interpret_summary["marker_hit"])
    else:
        # 键归属纪律：只覆盖 result.interpret_summary，不触碰其他键
        res["result"]["interpret_summary"] = interpret_summary
        if save_json(args.result, res):
            print("[interpret_rollup] interpret_summary 已回写: %s" % args.result)
        else:
            problems.append("interpret_summary 回写失败")

    for x in per_analysis:
        print("  %-10s design=%-14s allowed=%-11s claimed=%-11s final=%-11s overclaim=%-5s "
              "causal_ok=%-5s penalty=%-3s overall=%-8s verbs=%s"
              % (x.get("analysis_id"), x.get("design_type"), x.get("strength_allowed"),
                 x.get("strength_claimed"), x.get("strength_final"), x.get("overclaim"),
                 x.get("causal_ok"), x.get("penalty_total"), x.get("overall"),
                 x.get("causal_verbs_found") or "-"))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[interpret_rollup] done（exit 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[interpret_rollup] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
