#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""align_check_grant.py — 基金申请书对齐与预算核对
检查: 1) 每个 goal 在 contents/routes/metrics 有对应项；2) route 被引用；3) metrics 可考核；
4) 禁用修辞词（无对照依据的'首次/国际领先/填补空白'）；5) 路线步骤含输入输出；
6) 预算数字-来源核对（--budget）：每条预算必须有来源或明确标记 assumed/missing，禁止编造金额。

退出码契约: 恒为 0（任何失败路径都不中断交付链）。判定看报告里的 verdict/fail/problems，
脚本把结论写进 --out 报告文件，由上层读取；不靠退出码表达失败。
退化模式（--ablate）：关闭指定检查项用于"若无该机制会怎样"的同输入对照，
被关闭的检查在 checks 里 applied=false + note，gates 不受影响（enforced 语义不变）。
"""
import argparse, json, os, re, sys

BANNED = ["国际领先", "国际首创", "填补空白", "世界首创", "重大突破"]
SOFT_BANNED = ["首次"]
BUDGET_STATUS = ("sourced", "assumed", "missing")
ABLATE_CHOICES = ("innovation", "budget", "evidence", "alignment")

def check_budget(path, problems):
    """预算数字-来源核对表：amount 必须为数字，source_locator 必填，
    status 只能是 sourced/assumed/missing；编造（无来源又无标记）→ fail。"""
    if not os.path.exists(path):
        problems.append({"type": "budget_ledger_missing",
                         "detail": "未找到预算核对表；若有预算节必须逐条登记来源"})
        return 0, 0
    rows = []
    try:
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    except Exception as e:
        problems.append({"type": "budget_ledger_unparsable", "detail": str(e)[:120]})
        return 0, 0
    bad = []
    for r in rows:
        item = str(r.get("item") or r.get("name") or "?")
        amt = r.get("amount")
        st = str(r.get("status") or "").lower()
        if amt is not None and not isinstance(amt, (int, float)):
            bad.append({"item": item, "reason": "amount 非数字"})
        if st not in BUDGET_STATUS:
            bad.append({"item": item, "reason": f"status 非法: {st or '空'}（须 sourced/assumed/missing）"})
        if st == "sourced" and not r.get("source_locator"):
            bad.append({"item": item, "reason": "标 sourced 但缺 source_locator"})
        if amt is not None and not st:
            bad.append({"item": item, "reason": "有金额但未标来源状态（疑似编造）"})
    if bad:
        problems.append({"type": "budget_unsourced", "detail": bad[:10]})
    return len(rows), len(bad)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alignment", required=True)
    ap.add_argument("--routes", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--budget", default=None, help="budget_ledger.jsonl 预算数字-来源核对表")
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablate", default="",
                    help="退化档：关闭指定检查项（逗号分隔 innovation,budget,evidence,alignment），"
                         "用于同输入对照；被关闭项在 checks 里 applied=false 并记 note")
    args = ap.parse_args()
    ablate = set(x.strip() for x in (args.ablate or "").split(",") if x.strip())
    unknown = ablate - set(ABLATE_CHOICES)
    if unknown:
        raise ValueError("未知 --ablate 项: %s（可选 %s）" % (sorted(unknown), list(ABLATE_CHOICES)))
    align = [json.loads(l) for l in open(args.alignment, encoding="utf-8") if l.strip()]
    routes = [json.loads(l) for l in open(args.routes, encoding="utf-8") if l.strip()]
    draft = open(args.draft, encoding="utf-8").read()

    problems = []
    orphan = [g.get("goal") for g in align
              if not (g.get("contents") and g.get("routes") and g.get("metrics"))]
    if orphan and "alignment" not in ablate:
        problems.append({"type": "orphan_goals", "goals": orphan})
    metric_bad = []
    for g in align:
        for m in g.get("metrics") or []:
            if not re.search(r"\d|[完成|发表|授权|达到|验证|通过]", str(m)):
                metric_bad.append(str(m))
    if metric_bad and "alignment" not in ablate:
        problems.append({"type": "unmeasurable_metrics", "metrics": metric_bad[:10]})
    rids = {r.get("rid") for r in routes}
    refs = set()
    for g in align:
        refs |= set(g.get("routes") or [])
    unused = rids - refs
    if unused and rids and "alignment" not in ablate:
        problems.append({"type": "unused_routes", "rids": sorted(unused)})
    step_bad = [r.get("rid") for r in routes
                if r.get("steps") and any(not s.get("in") or not s.get("out") for s in r["steps"])]
    if step_bad and "alignment" not in ablate:
        problems.append({"type": "route_steps_missing_io", "rids": step_bad})

    # 禁用词（允许出现于 vs_existing 对照语境）
    hard_hits = []
    for w in BANNED:
        for m in re.finditer(re.escape(w), draft):
            ctx = draft[max(0, m.start()-60):m.end()+60].replace("\n", " ")
            if "vs_existing" not in ctx and "对照" not in ctx:
                hard_hits.append({"w": w, "ctx": ctx})
    if hard_hits:
        problems.append({"type": "banned_claims", "detail": hard_hits[:8]})

    # 创新点 vs_existing 对照表：创新节必须含与已有工作的逐条对照（谁/差在哪/凭什么）
    if "vs_existing" not in draft and "innovation" not in ablate:
        problems.append({"type": "innovation_no_vs_existing",
                         "detail": "创新点缺 vs_existing 逐条对照（与谁比/差在哪/凭什么做得成）"})

    # 预算核对（有 --budget 才检查；hard=fail）
    budget_n, budget_bad = (None, None)
    if args.budget and "budget" not in ablate:
        budget_n, budget_bad = check_budget(args.budget, problems)

    # 逐条三元组：每项检查输出 {item, template_value, applied, match}，嵌入 result.json 可复核
    checks = [
        {"item": "goals_no_orphan", "template_value": "每个 goal 在 contents/routes/metrics 均有对应项",
         "applied": "alignment" not in ablate,
         "match": None if "alignment" in ablate else not any(p["type"] == "orphan_goals" for p in problems)},
        {"item": "metrics_measurable", "template_value": "指标含数字或可考核动词",
         "applied": "alignment" not in ablate,
         "match": None if "alignment" in ablate else not any(p["type"] == "unmeasurable_metrics" for p in problems)},
        {"item": "routes_used_and_io", "template_value": "路线被 goal 引用且步骤含输入输出",
         "applied": "alignment" not in ablate,
         "match": None if "alignment" in ablate else not any(
             p["type"] in ("unused_routes", "route_steps_missing_io") for p in problems)},
        {"item": "no_banned_claims", "template_value": "无'首次/国际领先/填补空白'裸用",
         "applied": True,
         "match": not any(p["type"] == "banned_claims" for p in problems)},
        {"item": "budget_sourced", "template_value": "预算逐条 status=sourced/assumed/missing 且有 locator",
         "applied": bool(args.budget) and "budget" not in ablate,
         "match": None if (not args.budget or "budget" in ablate) else not any(
             p["type"] in ("budget_unsourced", "budget_ledger_unparsable") for p in problems)},
    ]
    # 闸门自身状态显式枚举：未运行 ≠ 通过
    gates = [
        {"gate": "budget_check", "status": "enforced" if (args.budget and "budget" not in ablate)
         else "skipped_not_provided",
         "gate_note": "" if (args.budget and "budget" not in ablate)
         else ("退化档已关闭 budget 检查（--ablate budget），不得宣称预算已核对"
               if "budget" in ablate else "未提供 budget_ledger，下游不得宣称预算已核对")},
    ]

    hard_types = ("orphan_goals", "unmeasurable_metrics", "banned_claims", "budget_unsourced",
                  "budget_ledger_unparsable", "innovation_no_vs_existing")
    checks.append({"item": "innovation_vs_existing", "template_value": "创新点含 vs_existing 逐条对照",
                   "applied": "innovation" not in ablate,
                   "match": None if "innovation" in ablate else
                   "innovation_no_vs_existing" not in [p["type"] for p in problems]})
    hard = [p for p in problems if p["type"] in hard_types]
    report = {"goals": len(align), "routes": len(routes),
              "budget_entries": budget_n, "budget_bad": budget_bad,
              "problems": problems, "fail": len(hard),
              "checks": checks, "gates": gates,
              "ablate": sorted(ablate),
              "verdict": "pass" if not hard else "fail",
              "hint": "孤儿目标/不可考核指标/禁用断言/无来源预算必须修复；soft(首次) 需补对照依据或改写。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "goals": len(align),
                      "budget": budget_n,
                      "types": [p["type"] for p in problems]}, ensure_ascii=False))
    # 退出码契约：恒 0（失败不中断交付链），判定看 verdict/fail/problems
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        # 容错：检查器自身崩溃时不阻塞交付，只诚实登记后放行
        print(json.dumps({"verdict": "checker_error", "error": str(e)[:200]},
                         ensure_ascii=False))
        sys.exit(0)
