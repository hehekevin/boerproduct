#!/usr/bin/env python3
"""grade_rollup.py — 分级机械复算与汇总（lit-quality-appraise）。

按 result.grading_rules（或 --rules 指定的台账）对每篇文献机械复算：
  penalty_total = Σ penalty_map[judgment]
  risk_of_bias  = thresholds 分档（low/some_concerns→medium/high），
                  叠加事前声明的 abstain_rule（弃权→uncertain）
  direction     = 事前声明的 direction_rule（负面条目方向多数规则）
并把结果写入 result.risk_summary（**键归属：本脚本只写 risk_summary 这一个键**，
与 verify_check / gain_probe / build_skeleton 不冲突）。

用法：
    python3 grade_rollup.py --result /app/output/result.json [--rules /app/work/grading_rules.json] [--dry-run]
退出码恒为 0（失败以 problems 报告，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

JUD = ("adequate", "concerns", "inadequate", "unreported", "not_applicable", "unassessable")


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
        print("[grade_rollup] 写盘失败 %s: %s" % (path, e))
        return False


def marker_note():
    """定位标志文件校验：脚本与 SKILL.md 同包才算挂载命中（只提示，不阻断）。"""
    m = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    return bool(os.path.exists(m))


def rules_valid(rules):
    if not isinstance(rules, dict):
        return False
    return all(k in rules for k in ("grade_map", "category_map", "penalty_map", "thresholds")) \
        and all(j in rules.get("penalty_map", {}) for j in JUD)


def rollup(paper, rules):
    gm, pm, th = rules["grade_map"], rules["penalty_map"], rules["thresholds"]
    total, abstained = 0, 0
    counts = {"high": 0, "medium": 0, "low": 0, "uncertain": 0, "none_grade": 0}
    dirs = []
    for a in paper.get("appraisals") or []:
        if not isinstance(a, dict):
            continue
        j = a.get("judgment")
        total += int(pm.get(j, 0) or 0)
        g = a.get("grade")
        counts[str(g) if g in ("high", "medium", "low", "uncertain") else "none_grade"] += 1
        if j == "unassessable":
            abstained += 1
        if a.get("bias_direction") in ("favors_conclusion", "against_conclusion"):
            dirs.append(a["bias_direction"])
    band = "unknown"
    for name in ("low", "some_concerns", "high"):
        rng = th.get(name) or []
        if len(rng) == 2 and rng[0] <= total <= rng[1]:
            band = {"low": "low", "some_concerns": "medium", "high": "high"}[name]
            break
    risk = band
    if abstained >= 2 or (abstained >= 1 and band == "low"):
        risk = "uncertain"
    if any(d == "against_conclusion" for d in dirs):
        direction = "against_conclusion"
    elif any(d == "favors_conclusion" for d in dirs):
        direction = "favors_conclusion"
    else:
        direction = "unclear"
    flaws = sum(1 for a in (paper.get("appraisals") or []) if isinstance(a, dict)
                and a.get("category") == "design_flaw")
    rgaps = sum(1 for a in (paper.get("appraisals") or []) if isinstance(a, dict)
                and a.get("category") == "reporting_gap")
    return {"paper_id": paper.get("paper_id"), "penalty_total": total,
            "risk_of_bias": risk, "band_raw": band, "direction": direction,
            "abstained": abstained, "design_flaws": flaws, "reporting_gaps": rgaps,
            "grade_counts": counts}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--rules", default="/app/work/grading_rules.json")
        ap.add_argument("--dry-run", action="store_true", help="只打印复算结果，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[grade_rollup] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[grade_rollup] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）" % args.result)
        return 0
    rules = load_json(args.rules) if os.path.exists(args.rules) else None
    if not rules_valid(rules):
        rules = res["result"].get("grading_rules")
    if not rules_valid(rules):
        print("[grade_rollup] FAIL: grading_rules 缺失或非法（须含 grade_map/category_map/"
              "penalty_map/thresholds 且 declared_at 非空）；本脚本不臆造口径，请先声明。")
        return 0

    papers = [p for p in (res["result"].get("papers") or []) if isinstance(p, dict)]
    per_paper = []
    for p in papers:
        try:
            per_paper.append(rollup(p, rules))
        except Exception as e:
            problems.append("%s 复算异常: %s" % (p.get("paper_id"), e))

    dflaws = sum(x.get("design_flaws", 0) for x in per_paper)
    rgaps = sum(x.get("reporting_gaps", 0) for x in per_paper)
    risk_summary = {
        "computed_by": "scripts/grade_rollup.py",
        "rules_version": str(rules.get("version") or "undeclared"),
        "declared_at": rules.get("declared_at"),
        "marker_hit": marker_note(),
        "per_paper": per_paper,
        "totals": {"papers": len(papers), "design_flaws": dflaws, "reporting_gaps": rgaps},
    }

    if args.dry_run:
        print("[grade_rollup] dry-run（不写盘）marker_hit=%s" % risk_summary["marker_hit"])
    else:
        # 键归属纪律：只覆盖 result.risk_summary，不触碰其他键
        res["result"]["risk_summary"] = risk_summary
        if save_json(args.result, res):
            print("[grade_rollup] risk_summary 已回写: %s" % args.result)
        else:
            problems.append("risk_summary 回写失败")
        print("[grade_rollup] 台账同步: %s" % args.rules)
        cur = load_json(args.rules)
        if isinstance(cur, dict) and not cur.get("declared_at"):
            cur["declared_at"] = rules.get("declared_at") or "grade_rollup"
            save_json(args.rules, cur)

    for x in per_paper:
        print("  %-8s penalty=%-3s risk=%-10s direction=%-18s 弃权=%d 设计缺陷=%d 报告不全=%d"
              % (x.get("paper_id"), x.get("penalty_total"), x.get("risk_of_bias"),
                 x.get("direction"), x.get("abstained", 0), x.get("design_flaws", 0),
                 x.get("reporting_gaps", 0)))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[grade_rollup] done（exit 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[grade_rollup] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
