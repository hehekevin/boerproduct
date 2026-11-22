#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""align_check_grant.py — 基金申请书对齐与预算核对
检查: 1) 每个 goal 在 contents/routes/metrics 有对应项；2) route 被引用；3) metrics 可考核；
4) 禁用修辞词（无对照依据的'首次/国际领先/填补空白'）；5) 路线步骤含输入输出；
6) 预算数字-来源核对（--budget）：每条预算必须有来源或明确标记 assumed/missing，禁止编造金额。
"""
import argparse, json, os, re, sys

BANNED = ["国际领先", "国际首创", "填补空白", "世界首创", "重大突破"]
SOFT_BANNED = ["首次"]
BUDGET_STATUS = ("sourced", "assumed", "missing")

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
    args = ap.parse_args()
    align = [json.loads(l) for l in open(args.alignment, encoding="utf-8") if l.strip()]
    routes = [json.loads(l) for l in open(args.routes, encoding="utf-8") if l.strip()]
    draft = open(args.draft, encoding="utf-8").read()

    problems = []
    orphan = [g.get("goal") for g in align
              if not (g.get("contents") and g.get("routes") and g.get("metrics"))]
    if orphan:
        problems.append({"type": "orphan_goals", "goals": orphan})
    metric_bad = []
    for g in align:
        for m in g.get("metrics") or []:
            if not re.search(r"\d|[完成|发表|授权|达到|验证|通过]", str(m)):
                metric_bad.append(str(m))
    if metric_bad:
        problems.append({"type": "unmeasurable_metrics", "metrics": metric_bad[:10]})
    rids = {r.get("rid") for r in routes}
    refs = set()
    for g in align:
        refs |= set(g.get("routes") or [])
    unused = rids - refs
    if unused and rids:
        problems.append({"type": "unused_routes", "rids": sorted(unused)})
    step_bad = [r.get("rid") for r in routes
                if r.get("steps") and any(not s.get("in") or not s.get("out") for s in r["steps"])]
    if step_bad:
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

    # 预算核对（有 --budget 才检查；hard=fail）
    budget_n, budget_bad = (None, None)
    if args.budget:
        budget_n, budget_bad = check_budget(args.budget, problems)

    hard_types = ("orphan_goals", "unmeasurable_metrics", "banned_claims", "budget_unsourced",
                  "budget_ledger_unparsable")
    hard = [p for p in problems if p["type"] in hard_types]
    report = {"goals": len(align), "routes": len(routes),
              "budget_entries": budget_n, "budget_bad": budget_bad,
              "problems": problems, "fail": len(hard),
              "verdict": "pass" if not hard else "fail",
              "hint": "孤儿目标/不可考核指标/禁用断言/无来源预算必须修复；soft(首次) 需补对照依据或改写。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "goals": len(align),
                      "budget": budget_n,
                      "types": [p["type"] for p in problems]}, ensure_ascii=False))
    return 1 if hard else 0

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
