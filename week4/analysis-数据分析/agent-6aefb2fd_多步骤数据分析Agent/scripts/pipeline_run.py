#!/usr/bin/env python3
"""pipeline_run.py — 步骤图完备性审计与逐步留痕回放（multi-step-analysis）。

机械审计两层：
  1. 步骤图完备（依赖无环）：对 plan.steps 做拓扑排序 + 环检测，检查每个
     depends_on 引用的 step_id 都存在、step_id 本身合法（显式 ASCII 白名单，
     不用 str.isalpha——该函数对汉字返回 True，会把「步骤一」误判成合法 id）。
  2. 逐步留痕可回放：对 result.steps 留痕逐条回放——每个计划步骤都有留痕条目、
     status ∈ done|failed|degraded|skipped、依赖步骤已先完成、每步有可回放要素
     （command/inputs/outputs/artifacts）。

键归属纪律：本脚本只写 result.dag 与 result.trace_audit 两个键，多脚本禁写
同一键；其余键归 build_skeleton / verify_check / gain_probe / Agent。

用法：
    python3 pipeline_run.py --result /app/output/result.json \
        --plan /app/work/analysis_plan.json --out /app/work/pipeline_run.json
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STEP_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")
STATUS_OK = ("done", "failed", "degraded", "skipped")
TRACE_FIELDS = ("step_id", "status", "command", "inputs", "outputs")


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
        print("[pipeline_run] 写盘失败 %s: %s" % (path, e))
        return False


def valid_step_id(sid):
    return bool(isinstance(sid, str) and STEP_ID_RE.match(sid))


def topo_check(plan_steps):
    """拓扑排序 + 环检测 + 引用完备性。返回 (acyclic, problems, order)。"""
    problems = []
    ids = []
    for s in plan_steps:
        sid = s.get("step_id")
        if not valid_step_id(sid):
            problems.append("[structure] step_id 非法（须为 ASCII 大写字母+数字）: %r" % (sid,))
        ids.append(str(sid))
    if len(set(ids)) != len(ids):
        problems.append("[structure] step_id 重复")
    idset = set(ids)
    edges = []
    for s in plan_steps:
        sid = str(s.get("step_id"))
        for dep in (s.get("depends_on") or []):
            d = str(dep)
            edges.append([d, sid])
            if d not in idset:
                problems.append("[graph] 依赖引用不存在: %s -> %s" % (d, sid))
    # Kahn 拓扑
    indeg = {i: 0 for i in idset}
    adj = {i: [] for i in idset}
    for a, b in edges:
        if a in idset and b in idset:
            adj[a].append(b)
            indeg[b] += 1
    queue = sorted([i for i in idset if indeg[i] == 0])
    order = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
        queue.sort()
    acyclic = len(order) == len(idset)
    if not acyclic and not problems:
        cyc = sorted(set(idset) - set(order))
        problems.append("[graph] 步骤图存在环，涉及节点: %s" % ",".join(cyc))
    return acyclic, problems, order


def trace_audit(steps, plan_steps, acyclic, order):
    """逐步留痕回放。返回 (problems, stats)。"""
    problems = []
    plan_ids = [str(s.get("step_id")) for s in plan_steps]
    traces = {}
    appearance = {}
    for idx, t in enumerate(steps):
        if not isinstance(t, dict):
            problems.append("[trace] 留痕条目非对象")
            continue
        sid = str(t.get("step_id") or "")
        if sid in traces:
            problems.append("[trace] 步骤 %s 重复留痕" % sid)
        traces[sid] = t
        appearance[sid] = idx
    done = set()
    for s in plan_steps:
        sid = str(s.get("step_id"))
        t = traces.get(sid)
        if t is None:
            problems.append("[trace] 计划步骤 %s 无留痕条目（不可回放）" % sid)
            continue
        st = str(t.get("status") or "").lower()
        if st not in STATUS_OK:
            problems.append("[enum] 步骤 %s status 非法: %r" % (sid, t.get("status")))
        missing = [f for f in TRACE_FIELDS if t.get(f) in (None, "", [])]
        if missing:
            problems.append("[trace] 步骤 %s 留痕缺要素: %s" % (sid, ",".join(missing)))
        for dep in (s.get("depends_on") or []):
            d = str(dep)
            dt = traces.get(d)
            dst = str((dt or {}).get("status") or "").lower()
            if dst not in ("done", "degraded"):
                problems.append("[graph] 步骤 %s 依赖 %s 未完成（status=%s）即执行" % (sid, d, dst or "无"))
            if appearance.get(d) is not None and appearance.get(sid) is not None \
                    and appearance[d] >= appearance[sid]:
                problems.append("[graph] 步骤 %s 的留痕先于其依赖 %s（留痕顺序违背拓扑序）" % (sid, d))
        if st in ("done", "degraded"):
            done.add(sid)
    stats = {
        "plan_steps": len(plan_ids),
        "traced_steps": len(traces),
        "done_or_degraded": len(done),
        "failed": sum(1 for t in traces.values() if str(t.get("status")).lower() == "failed"),
        "skipped": sum(1 for t in traces.values() if str(t.get("status")).lower() == "skipped"),
    }
    return problems, stats


def analyze(result, plan_source="result", plan_path=None):
    """供 gain_probe 导入的纯函数审计入口。返回报告 dict（不改 result）。"""
    import copy
    r = copy.deepcopy(result or {})
    inner = (r.get("result") or {}) if isinstance(r, dict) else {}
    problems = []
    plan = inner.get("plan") or {}
    plan_steps = plan.get("steps") or []
    if not plan_steps:
        problems.append("[structure] result.plan.steps 为空（步骤图未声明）")
    acyclic, order = None, []
    if plan_steps:
        acyclic, gp, order = topo_check(plan_steps)
        problems.extend(gp)
    steps = inner.get("steps") or []
    tp, stats = trace_audit(steps, plan_steps, bool(acyclic), order)
    problems.extend(tp)
    gates = [
        {"gate": "plan_ledger", "state": "enforced" if plan_steps else "not_found",
         "note": "" if plan_steps else "步骤图台账缺失，下游不得宣称步骤图完备"},
        {"gate": "dag_acyclic", "state": "enforced" if acyclic else "not_found",
         "note": "" if acyclic else "无环性未确证"},
    ]
    verdict = "PASS" if not problems else "FAIL"
    return {"verdict": verdict, "problems": problems, "dag": {"acyclic": acyclic,
            "order": order}, "trace_stats": stats, "gates": gates,
            "ablate": "none", "disabled_checks": []}


def ablated_analyze(result, plan_path=None):
    """退化模式：关闭 graph 与 trace 两组检查（仅用于增益对照）。"""
    import copy
    r = copy.deepcopy(result or {})
    inner = (r.get("result") or {}) if isinstance(r, dict) else {}
    plan_steps = ((inner.get("plan") or {}).get("steps")) or []
    problems = []
    for s in plan_steps:
        if not valid_step_id(s.get("step_id")):
            problems.append("[structure] step_id 非法: %r" % (s.get("step_id"),))
    return {"verdict": "PASS" if not problems else "FAIL", "problems": problems,
            "dag": {"acyclic": None, "order": []}, "trace_stats": {},
            "gates": [{"gate": "plan_ledger", "state": "not_found", "note": "退化模式"}],
            "ablate": "all", "disabled_checks": ["graph", "trace", "enum", "structure"]}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--plan", default="/app/work/analysis_plan.json")
        ap.add_argument("--out", default=None)
        args = ap.parse_args()
    except Exception as e:
        print("[pipeline_run] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[pipeline_run] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    ledger = load_json(args.plan) or {}
    inner = res.get("result") or {}
    plan_steps = (inner.get("plan") or {}).get("steps") or ledger.get("steps") or []
    acyclic, problems, order = topo_check(plan_steps)
    steps = inner.get("steps") or []
    tp, stats = trace_audit(steps, plan_steps, acyclic, order)
    problems.extend(tp)
    verdict = "PASS" if not problems else "FAIL"

    # 只写 result.dag（键归属纪律）
    try:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            cur["result"]["dag"] = {"nodes": [str(s.get("step_id")) for s in plan_steps],
                                    "edges": [[str(d), str(s.get("step_id"))]
                                              for s in plan_steps for d in (s.get("depends_on") or [])],
                                    "acyclic": acyclic, "order": order,
                                    "computed_by": "pipeline_run.py",
                                    "trace_stats": stats}
            cur["result"]["trace_audit"] = {"computed_by": "pipeline_run.py",
                                            "problems": problems,
                                            "stats": stats}
            save_json(args.result, cur)
    except Exception as e:
        print("[pipeline_run] 回写 result.dag 失败: %s" % e)

    report = {"verdict": verdict, "problems": problems, "dag": {"acyclic": acyclic, "order": order},
              "trace_stats": stats, "ablate": "none", "disabled_checks": [],
              "self_check": [{"item": "步骤图依赖无环且引用完备", "applied": bool(plan_steps),
                              "match": acyclic},
                             {"item": "每个计划步骤有留痕且要素齐全", "applied": bool(plan_steps),
                              "match": not tp}]}
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)),
                                        "..", "work", "pipeline_run.json")
    save_json(out_path, report)

    print("[pipeline_run] verdict=%s | acyclic=%s | 计划步骤=%d 留痕=%d 完成=%d 失败=%d 跳过=%d"
          % (verdict, acyclic, stats.get("plan_steps", 0), stats.get("traced_steps", 0),
             stats.get("done_or_degraded", 0), stats.get("failed", 0), stats.get("skipped", 0)))
    for pr in problems:
        print("  PROBLEM: %s" % pr)
    print("[pipeline_run] 报告落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[pipeline_run] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
