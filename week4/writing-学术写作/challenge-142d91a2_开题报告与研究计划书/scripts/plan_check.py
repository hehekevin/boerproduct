#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_check.py — 开题/研究计划对齐检查（容错版）
检查: 1) 问题-目标对齐（无孤儿目标/无空悬问题）；2) 里程碑周期合规；
3) 风险分类覆盖与字段完整（trigger/fallback/decision_point）；4) success_criteria 可考核。
容错: 缺文件/脏行/缺 constraints 一律降级登记，不崩溃；退出码恒为 0，结论看 verdict。
"""
import argparse, json, os, re, sys


def load_lines(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows, False
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows, True


def load_json(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--milestones", required=True)
    ap.add_argument("--risks", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    plan, ok_p = load_lines(args.plan)
    ms, ok_m = load_lines(args.milestones)
    risks, ok_r = load_lines(args.risks)
    con = load_json(args.constraints) or {}

    problems, notes = [], []
    if not ok_p:
        notes.append("plan 文件缺失: %s" % args.plan)
    if not ok_m:
        notes.append("milestones 文件缺失: %s" % args.milestones)
    if not ok_r:
        notes.append("risks 文件缺失: %s" % args.risks)
    if not con:
        notes.append("constraints 缺失或不可解析——周期检查跳过")

    # 1) 问题-目标对齐
    qids = {p.get("qid") for p in plan if isinstance(p, dict) and p.get("qid")}
    orphan = [g.get("gid") for g in plan
              if isinstance(g, dict) and g.get("objective") and g.get("qid") not in qids]
    if orphan:
        problems.append({"type": "orphan_objectives", "gids": orphan})
    crit_bad = [g.get("gid") for g in plan
                if isinstance(g, dict) and g.get("objective")
                and (len(str(g.get("success_criteria") or "")) < 8
                     or not re.search(r"\d|指标|完成|通过|发表|验证|验收|申请|专利",
                                      str(g.get("success_criteria") or "")))]
    if crit_bad:
        problems.append({"type": "criteria_unmeasurable", "gids": crit_bad})

    # 2) 周期
    span = con.get("total_months") or con.get("period_months")
    if span:
        try:
            span = int(span)
            max_m = 0
            for m in ms:
                if not isinstance(m, dict):
                    continue
                period = str(m.get("period", ""))
                for a, b in re.findall(r"(\d+)\s*[-~至到]\s*(\d+)\s*月", period):
                    max_m = max(max_m, int(b))
                qm = re.findall(r"(\d{4})Q([1-4])", period)
                if qm:
                    y, q = qm[-1]
                    base = int(con.get("start_year") or 0)
                    if base:
                        max_m = max(max_m, (int(y) - base) * 12 + int(q) * 3)
            if max_m > span:
                problems.append({"type": "period_exceeded", "max_month": max_m, "limit": span})
        except Exception as e:
            notes.append("周期解析异常: %s" % str(e)[:120])

    # 3) 风险字段与分类
    risk_missing = [r.get("rid") for r in risks
                    if isinstance(r, dict)
                    and not all(r.get(k) for k in ("trigger", "fallback", "decision_point"))]
    if risk_missing:
        problems.append({"type": "risk_fields_missing", "rids": risk_missing})
    cats = {r.get("category") for r in risks if isinstance(r, dict)}
    need = set(con.get("risk_categories") or ["数据", "方法", "进度", "伦理合规"])
    missing_cats = need - cats
    if missing_cats and risks:
        problems.append({"type": "risk_categories_incomplete", "missing": sorted(missing_cats)})

    hard = [p for p in problems
            if p["type"] in ("orphan_objectives", "criteria_unmeasurable", "period_exceeded")]
    report = {"goals": len(plan), "milestones": len(ms), "risks": len(risks),
              "problems": problems, "notes": notes, "fail": len(hard),
              "verdict": "pass" if (not hard and ok_p and ok_m and ok_r) else
                         ("fail" if hard else "incomplete"),
              "hint": "孤儿目标/不可考核标准/超期必须修复；风险字段与分类缺失补齐；"
                      "incomplete 表示输入文件缺失，需回补后重跑。"}
    if args.out:
        try:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass
    print(json.dumps({k: report[k] for k in ("verdict", "goals", "milestones", "risks", "fail")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
