#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（multi-step-analysis）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭步骤图完备 / 留痕回放 / 中间校验复算 / 证据对齐 / 降级登记五组检查），
逐项对照可观测指标（全部实测，不臆造）：

  1. graph_missed    步骤图违规（环/依赖悬空）漏检数
  2. trace_missed    留痕缺失/不可回放漏检数
  3. middle_missed   中间校验通过率失真漏检数
  4. evidence_missed 结论-证据失据漏检数（引文+数字回证）
  5. fallback_missed 失败降级漏登记数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。违规客观真值由本探针独立复算（与
verify_check 分开实现，拓扑排序为第二套实现）。**退化模式仅用于增益对照，
不得用于交付自检。**

用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution]
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze, case_text_blob, recompute_middle, contract_fields  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3
TAGS = ("graph", "trace", "middle", "evidence", "fallback")


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
        print("[gain_probe] 写盘失败 %s: %s" % (path, e))
        return False


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def indep_dag(plan_steps):
    """独立第二套环检测（DFS 三色标记），与 verify_check 的 Kahn 实现分开。"""
    problems = []
    graph = {}
    ids = []
    for s in plan_steps:
        sid = str(s.get("step_id") or "")
        ids.append(sid)
        graph.setdefault(sid, [])
    for s in plan_steps:
        for dep in (s.get("depends_on") or []):
            d = str(dep)
            if d not in graph:
                problems.append("依赖引用不存在: %s -> %s" % (d, s.get("step_id")))
            else:
                graph[str(s.get("step_id"))].append(d)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in graph}
    def dfs(u, stack):
        color[u] = GRAY
        for v in graph.get(u, []):
            if color.get(v) == GRAY:
                problems.append("步骤图存在环: %s -> %s" % (u, v))
            elif color.get(v) == WHITE:
                dfs(v, stack + [u])
        color[u] = BLACK
    for n in graph:
        if color[n] == WHITE:
            dfs(n, [])
    return problems


def objective_violations(res, case):
    """独立复算五类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    out = {t: [] for t in TAGS}
    plan_steps = ((inner.get("plan") or {}).get("steps")) or []
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    # graph：独立 DFS 环检测
    if plan_steps:
        out["graph"].extend(indep_dag(plan_steps))
    else:
        out["graph"].append("plan.steps 为空（步骤图未声明）")
    # trace
    traces = {}
    for t in steps:
        sid = str(t.get("step_id") or "")
        if sid in traces:
            out["trace"].append("步骤 %s 重复留痕" % sid)
        traces[sid] = t
    for s in plan_steps:
        sid = str(s.get("step_id"))
        t = traces.get(sid)
        if t is None:
            out["trace"].append("计划步骤 %s 无留痕" % sid)
            continue
        if str(t.get("status") or "").lower() not in ("done", "failed", "degraded", "skipped"):
            out["trace"].append("步骤 %s status 非法" % sid)
        for f in ("command", "inputs", "outputs"):
            if t.get(f) in (None, "", []):
                out["trace"].append("步骤 %s 留痕缺 %s" % (sid, f))
    # middle
    mc = recompute_middle(steps)
    stored = inner.get("middle_checks") or {}
    for key in ("total", "passed", "failed"):
        sv = stored.get(key)
        if sv is not None and int(sv) != mc[key]:
            out["middle"].append("middle_checks.%s=%s 复算=%d 不符" % (key, sv, mc[key]))
    if mc["total"] == 0 and steps:
        out["middle"].append("有留痕步骤但零中间校验")
    # evidence（引文 + 数字回证，独立实现）
    case_blob = case_text_blob(case if isinstance(case, dict) else {})
    steps_idx = {str(s.get("step_id") or ""): s for s in steps}
    claims = [c for c in ((res or {}).get("claims") or []) if isinstance(c, dict)]
    if not claims:
        out["evidence"].append("claims 为空（结论无证据链）")
    for c in claims:
        cid = str(c.get("claim_id") or "?")
        src = str(c.get("source_id") or "")
        quotes = [norm(e.get("quote")) for e in (c.get("evidence") or []) if isinstance(e, dict)]
        quotes = [q for q in quotes if q]
        if not quotes:
            out["evidence"].append("%s 无证据引文" % cid)
        pool = " ".join(quotes) + norm(json.dumps(steps_idx.get(src) or {}, ensure_ascii=False))
        for q in quotes:
            if q not in case_blob and q not in pool:
                out["evidence"].append("%s 引文无回证" % cid)
        for num in re.findall(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?![A-Za-z0-9_.])", str(c.get("text") or "")):
            if norm(num) not in pool:
                out["evidence"].append("%s 数字 %s 无回证" % (cid, num))
    # fallback
    fb_ids = {str(f.get("step_id")) for f in (inner.get("fallbacks") or []) if isinstance(f, dict)}
    pend_ids = {str(p.get("step_id")) for p in (inner.get("pending_review") or []) if isinstance(p, dict)}
    for s in steps:
        sid = str(s.get("step_id") or "")
        st = str(s.get("status") or "").lower()
        if st in ("failed", "degraded") and sid not in fb_ids:
            out["fallback"].append("步骤 %s %s 未登记 fallbacks" % (sid, st))
        if st == "skipped" and sid not in pend_ids:
            out["fallback"].append("步骤 %s skipped 未登记 pending_review" % sid)
    return out


def count_caught(report):
    cnt = {t: 0 for t in TAGS}
    for pr in report.get("problems") or []:
        m = re.match(r"^\[(\w+)\]", str(pr))
        if m and m.group(1) in cnt:
            cnt[m.group(1)] += 1
    return cnt


def mode_metrics(res, report, label, obj_truth):
    idx = count_caught(report)
    inner = (res or {}).get("result") or {}
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    missed = {t: max(len(obj_truth[t]) - idx[t], 0) for t in TAGS}
    untraced = sum(1 for s in (((inner.get("plan") or {}).get("steps")) or [])
                   if str(s.get("step_id")) not in {str(t.get("step_id")) for t in steps})
    manual_items = sum(missed.values()) + untraced
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_done = sum(1 for s in steps
                     if str(s.get("status") or "").lower() in ("done", "degraded"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0
    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "graph_missed": missed["graph"],
            "trace_missed": missed["trace"],
            "middle_missed": missed["middle"],
            "evidence_missed": missed["evidence"],
            "fallback_missed": missed["fallback"],
            "violations_objective": {t: len(obj_truth[t]) for t in TAGS},
            "violations_caught": idx,
            "manual_review_items": manual_items,
            "untraced_plan_steps": untraced,
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "traced_steps_total": len(steps),
                             "steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    plan_steps = ((inner.get("plan") or {}).get("steps")) or []
    # 1) 步骤图注入环：首步骤反向依赖末步骤（S1→…→S5→S1 回路）
    if plan_steps:
        first = plan_steps[0]
        last_id = plan_steps[-1].get("step_id")
        first.setdefault("depends_on", [])
        if last_id not in first["depends_on"] and len(plan_steps) >= 2:
            first["depends_on"].append(last_id)
            plan.append("plan: %s 反向依赖 %s（注入环）" % (first.get("step_id"), last_id))
    # 2) 删除一条留痕
    if inner.get("steps"):
        dropped = inner["steps"].pop()
        plan.append("steps: 删除步骤 %s 的留痕（不可回放）" % dropped.get("step_id"))
    # 3) 篡改 middle_checks
    inner["middle_checks"] = {"total": 999, "passed": 999, "failed": 0,
                              "pass_rate": 1.0, "computed_by": "pollution"}
    plan.append("middle_checks: 篡改为 999/999（通过率失真）")
    # 4) 编造引文 + 数字
    if p.get("claims"):
        c0 = p["claims"][0]
        c0["text"] = str(c0.get("text") or "") + " 置信区间 [98.7, 99.9]"
        if c0.get("evidence"):
            c0["evidence"][0]["quote"] = "本句为污染注入的虚构引文，任何来源文本均不含此句"
        else:
            c0["evidence"] = [{"paragraph_id": "pollution", "quote": "污染虚构引文"}]
        plan.append("claims[0]: 注入编造引文与无回证数字 98.7/99.9")
    # 5) 清空降级登记
    inner["fallbacks"] = []
    plan.append("fallbacks: 清空（失败降级登记丢失）")
    if not plan:
        plan.append("（无可注入位置）")
    return p, plan


def count_files(root):
    n = 0
    try:
        for _dirpath, _dirnames, filenames in os.walk(root):
            n += len(filenames)
    except Exception:
        pass
    return n


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败（已降级）: %s" % e)
        return 0

    t0 = time.time()
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"

    obj_truth = objective_violations(res, case if isinstance(case, dict) else {})
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal", obj_truth)
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded", obj_truth)
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("graph_missed", "trace_missed", "middle_missed", "evidence_missed",
                  "fallback_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "graph_missed", "mechanism": "步骤图完备检查（Kahn 拓扑 + 依赖引用完备，"
         "与探针 DFS 第二实现互核）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后环/依赖悬空不再判 FAIL，带环步骤图可静默通过"},
        {"metric": "trace_missed", "mechanism": "逐步留痕回放（每步 status/command/inputs/"
         "outputs 要素齐全、依赖先完成、顺序合拓扑）", "formula": "客观违规数 − 被捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后留痕缺失/乱序不再判 FAIL，过程退化为不可回放"},
        {"metric": "middle_missed", "mechanism": "中间校验通过率复算（steps[].checks 独立"
         "复算对照 middle_checks）", "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后通过率可被篡改，质量门槛失去数字依据"},
        {"metric": "evidence_missed", "mechanism": "结论-证据对齐双闸（引文逐字回证 + 数字"
         "回证到证据/步骤产物）", "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后编造结论与数字不再判 FAIL"},
        {"metric": "fallback_missed", "mechanism": "失败降级登记（failed/degraded⇒fallbacks，"
         "skipped⇒pending_review）", "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后失败步骤可被静默跳过，异常不可追溯"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 无留痕计划步骤合计",
         "formula": "五类漏检 + untraced_plan_steps", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工回放核对的步骤增加"},
        {"metric": "steps_count", "mechanism": "五段流程 + 机械校验自检",
         "formula": "校验层已执行检查项数 + 已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         % ROUND_BATCH, "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回放/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭五组检查（graph/trace/middle/evidence/fallback），枚举与 contract 等"
        "基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（环检测为 DFS 第二实现，与 verify_check 的 "
        "Kahn 实现分开），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，来源比对跳过。",
        "plan 未事前声明（declared_at 空）时步骤图真值不可得，graph_missed 属『无法判定』而非『无违规』。",
        "把 --ablate 的退化结果当作交付自检结论即为误用。",
        "污染反例自试只在副本上注入，原 result.json 不被修改。",
    ]

    gain_evidence = {
        "collected_by": "scripts/gain_probe.py",
        "probe_version": "1.0",
        "probe_tool": "scripts/gain_probe.py",
        "case_id": res.get("case_id"),
        "input": {"result_path": os.path.abspath(args.result),
                  "case_path": os.path.abspath(args.case),
                  "case_contract_state": case_state,
                  "same_input_for_both_runs": True,
                  "run_order": ["normal", "degraded"],
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，不做原地修改）"},
        "runs": [m_normal, m_degraded],
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标为 lower_is_better 时表示机制带来增益"
                               "（漏检减少）；delta=0 表示该指标在本输入上无区分度。",
    }

    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_truth = objective_violations(polluted, case if isinstance(case, dict) else {})
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal", p_truth)
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded", p_truth)
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "missed": {t: pm_n["metrics"][t + "_missed"] for t in TAGS},
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "missed": {t: pm_d["metrics"][t + "_missed"] for t in TAGS},
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                t: pm_d["metrics"][t + "_missed"] - pm_n["metrics"][t + "_missed"] for t in TAGS},
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。",
        }

    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "input_files_scanned": count_files(os.path.dirname(os.path.abspath(args.case))),
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "plan_steps_total": len(((res.get("result") or {}).get("plan") or {}).get("steps") or []),
        "traced_steps_total": len((res.get("result") or {}).get("steps") or []),
        "claims_total": len(res.get("claims") or []),
        "manual_review_items_normal": m_normal["metrics"]["manual_review_items"],
        "manual_review_items_degraded": m_degraded["metrics"]["manual_review_items"],
        "clarification_rounds_normal": m_normal["metrics"]["clarification_rounds"],
        "clarification_rounds_degraded": m_degraded["metrics"]["clarification_rounds"],
        "model_requests": None,
        "model_requests_note": "模型请求数由 Agent 侧记录（不可由本脚本采集），"
                               "交付前按实际请求次数回填；缺失时保持 null，不得臆造。",
        "reproduce": "python3 /skills/weekly-skill/scripts/gain_probe.py "
                     "--result /app/output/result.json --case /input/case.json "
                     "--work-dir /app/work --emit-into --inject-pollution",
    }

    out_path = args.out or os.path.join(args.work_dir or ".", "gain_evidence.json")
    save_json(out_path, {"gain_evidence": gain_evidence, "efficiency": efficiency})

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
                cur["result"]["gain_evidence"] = gain_evidence
                cur["result"]["efficiency"] = efficiency
                save_json(args.result, cur)
        except Exception as e:
            print("[gain_probe] 回写 result.json 失败: %s" % e)

    print("[gain_probe] 正常模式 verdict=%s ｜ 退化模式 verdict=%s"
          % (m_normal["verdict"], m_degraded["verdict"]))
    for name in delta_keys:
        a, b = m_normal["metrics"].get(name), m_degraded["metrics"].get(name)
        print("  %-22s normal=%s  degraded=%s  delta=%s" % (name, a, b, delta.get(name)))
    if "pollution_selftest" in gain_evidence:
        ps = gain_evidence["pollution_selftest"]
        print("  污染反例: caught_by_normal_mode=%s（注入 %d 项）"
              % (ps["caught_by_normal_mode"], len(ps["injected"])))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
