#!/usr/bin/env python3
"""plan_audit.py — 研究计划事前声明审计（deep-research-loop Step 1）。

在**任何检索迭代之前**审计 result.plan：子问题编号唯一、证据需求非空、依赖
引用存在且无环、收敛判据已声明。审计通过后计算计划摘要指纹（sha256，稳定
序列化），写 /app/work/plan_ledger.json 台账并把审计结论回写 result.plan_audit。
计划一经声明锁定，之后禁止调整；verify_check 以 plan_audit 状态作为闸门。

**键归属**：本脚本只写 result.plan_audit 与 /app/work/plan_ledger.json；
其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 plan_audit.py --result /app/output/result.json [--work-dir /app/work]
退出码恒为 0（结论记在 plan_audit.state 与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import hashlib
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
        print("[plan_audit] 写盘失败 %s: %s" % (path, e))
        return False


def find_cycle(sqs):
    """依赖图找环（迭代染色）。返回构成环的 sq_id 列表（可能为空）。"""
    ids = [str(s.get("sq_id")) for s in sqs if s.get("sq_id")]
    graph = {}
    for s in sqs:
        sid = str(s.get("sq_id") or "")
        graph[sid] = [str(d) for d in (s.get("depends_on") or []) if str(d) in ids]
    state, cyc = {}, []

    def dfs(n):
        state[n] = 1
        for m in graph.get(n, []):
            if state.get(m) == 1:
                cyc.append(m)
                return True
            if state.get(m, 0) == 0 and dfs(m):
                return True
        state[n] = 2
        return False

    for n in graph:
        if state.get(n, 0) == 0 and dfs(n):
            break
    return cyc


def audit_plan(plan):
    """结构化审计计划。返回 (state, problems)。state ∈ declared|invalid|missing。"""
    problems = []
    if not isinstance(plan, dict):
        return "invalid", ["plan 缺失或不是对象（研究计划必须在迭代前声明）"]
    if not str(plan.get("declared_at") or "").strip():
        problems.append("plan.declared_at 为空（计划须在任何检索迭代之前声明）")
    sqs = [s for s in (plan.get("sub_questions") or []) if isinstance(s, dict)]
    if not sqs:
        problems.append("plan.sub_questions 为空（须拆出至少一个可独立检索的子问题）")
    seen = {}
    for i, s in enumerate(sqs):
        sid = str(s.get("sq_id") or "items[%d]" % i)
        if sid in seen:
            problems.append("子问题编号重复: %s" % sid)
        seen[sid] = True
        if not str(s.get("text") or "").strip():
            problems.append("%s text 为空（子问题须可独立检索）" % sid)
        if not str(s.get("evidence_needs") or "").strip():
            problems.append("%s evidence_needs 为空（须声明该子问题需要什么证据）" % sid)
        if not (s.get("search_queries") or []):
            problems.append("%s search_queries 为空（须声明检索式，便于留痕复跑）" % sid)
    for s in sqs:
        sid = str(s.get("sq_id") or "")
        for d in (s.get("depends_on") or []):
            if str(d) not in seen:
                problems.append("%s depends_on 引用不存在的子问题: %s" % (sid, d))
    cyc = find_cycle(sqs) if sqs else []
    if cyc:
        problems.append("依赖关系存在环: %s（子问题依赖必须是有向无环图）" % ",".join(sorted(set(cyc))))
    conv = plan.get("convergence") or {}
    if not str(conv.get("rule") or "").strip():
        problems.append("plan.convergence.rule 为空（须声明收敛判据/停止条件）")
    return ("invalid" if problems else "declared"), problems


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except Exception as e:
        print("[plan_audit] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[plan_audit] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）"
              % args.result)
        return 0

    plan = res["result"].get("plan") or {}
    state, problems = audit_plan(plan)
    digest = None
    try:
        digest = hashlib.sha256(
            json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    except Exception:
        digest = None
    audit = {"state": state, "declared_at": plan.get("declared_at"),
             "sq_count": len([s for s in (plan.get("sub_questions") or [])
                              if isinstance(s, dict)]),
             "digest": digest, "problems": problems,
             "audited_at_step": "step1",
             "note": "计划在任何检索迭代之前声明并锁定（sha256 前 16 位指纹）；声明后禁止调整。"}
    if state != "declared":
        audit["note"] = "计划未通过事前审计，下游不得宣称已按计划推进"

    save_json(os.path.join(args.work_dir or ".", "plan_ledger.json"),
              {"state": state, "declared_at": plan.get("declared_at"),
               "digest": digest, "problems": problems,
               "note": "计划台账：声明后禁止调整；verify_check 据此设置 plan_ledger 闸门。"})

    try:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["plan_audit"] = audit
            save_json(args.result, cur)
    except Exception as e:
        print("[plan_audit] 回写 result.plan_audit 失败: %s" % e)

    if state == "declared":
        print("[plan_audit] PASS: 计划事前声明审计通过（%d 个子问题，digest=%s）"
              % (audit["sq_count"], digest))
    else:
        print("[plan_audit] FAIL（%d 处，不中断交付）:" % len(problems))
        for p in problems[:20]:
            print("  - %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[plan_audit] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
