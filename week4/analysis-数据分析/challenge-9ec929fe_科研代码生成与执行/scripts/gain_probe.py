#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（sci-code-exec）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭需求覆盖映射 / 执行留痕 / 数值复算核验 / 异常口径登记四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. coverage_missed  需求-代码覆盖映射漏检数（客观违规但校验层未捕获）
  2. trace_missed     执行留痕缺失（无退出码/无日志/无环境版本）漏检数
  3. recompute_missed 数值未复算/复算不符/数字无回证漏检数
  4. anomaly_missed   异常静默处理/口径漂移漏检数
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。违规客观真值由本探针独立复算（与
verify_check 分开实现）。**退化模式仅用于增益对照，不得用于交付自检。**

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
    from verify_check import analyze, rules_ok  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3
TAGS = ("coverage", "trace", "recompute", "anomaly")


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


def objective_violations(res, case):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    out = {t: [] for t in TAGS}
    inner = (res or {}).get("result") or {}
    if not isinstance(inner, dict):
        out["coverage"].append("result 非对象")
        return out
    reqs = [r for r in (inner.get("requirements") or []) if isinstance(r, dict)]
    cov_map = [c for c in (inner.get("coverage_map") or []) if isinstance(c, dict)]
    art_ids = {str(a.get("artifact_id")) for a in (inner.get("code_artifacts") or [])
               if isinstance(a, dict)}
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    traces = [t for t in (inner.get("execution_traces") or []) if isinstance(t, dict)]
    stats = [s for s in (inner.get("stats") or []) if isinstance(s, dict)]
    anomalies = [a for a in (inner.get("anomalies") or []) if isinstance(a, dict)]
    claims = [c for c in ((res or {}).get("claims") or []) if isinstance(c, dict)]
    pending = inner.get("pending_review") or []
    crules = rules_ok(inner.get("cleaning_rules") or {})
    rule_ids = {str(r.get("rule_id")) for r in (crules["rules"] if crules else [])}
    recompute = inner.get("recompute") if isinstance(inner.get("recompute"), dict) else {}
    per_stat = {str(p.get("stat_id")): p for p in (recompute.get("per_stat") or [])
                if isinstance(p, dict)}
    env = inner.get("environment") if isinstance(inner.get("environment"), dict) else {}

    # coverage：每条需求须有映射且 artifact 存在；partial/uncovered 须登记
    cov_by_req = {}
    for c in cov_map:
        cov_by_req.setdefault(str(c.get("req_id")), []).append(c)
    for i, r in enumerate(reqs):
        rid = str(r.get("req_id") or "R%d" % (i + 1))
        entries = cov_by_req.get(rid, [])
        if not entries:
            out["coverage"].append("需求 %s 无映射" % rid)
        for c in entries:
            if str(c.get("artifact_id") or "") not in art_ids:
                out["coverage"].append("需求 %s artifact 不存在" % rid)
            if str(c.get("status")) in ("partial", "uncovered"):
                reg = [p for p in pending if str(p.get("req_id")) == rid]
                if not reg:
                    out["coverage"].append("需求 %s 未登记 pending" % rid)
    # trace：命令须 python3 且有 exit_code/log_ref；环境版本；留痕非空
    cmd_steps = [s for s in steps if str(s.get("command") or "").strip()]
    if cmd_steps and not traces:
        out["trace"].append("有命令步骤但 execution_traces 为空")
    if not env.get("python_version"):
        out["trace"].append("environment.python_version 为空")
    for i, s in enumerate(steps):
        cmd = str(s.get("command") or "").strip()
        if not cmd:
            continue
        if not cmd.startswith("python3"):
            out["trace"].append("steps[%d] 命令非 python3" % i)
        if s.get("exit_code") is None:
            out["trace"].append("steps[%d] 缺 exit_code" % i)
        if not str(s.get("log_ref") or "").strip():
            out["trace"].append("steps[%d] 缺 log_ref" % i)
    # recompute：每条 stat 须复算一致且数字回证
    claim_norm = re.sub(r"\s+", "", " ".join([str(c.get("text") or "") for c in claims] +
                       [str(e.get("quote") or "") for c in claims
                        for e in (c.get("evidence") or [])]))
    for i, s in enumerate(stats):
        sid = str(s.get("stat_id") or "stats[%d]" % i)
        p = per_stat.get(sid)
        if p is None:
            out["recompute"].append("stat %s 未复算" % sid)
        else:
            dv, rv = p.get("declared_value"), s.get("value")
            same = (dv == rv) or (isinstance(dv, (int, float)) and isinstance(rv, (int, float))
                                  and abs(float(dv) - float(rv)) <= 1e-9)
            if not same:
                out["recompute"].append("stat %s declared 与 stats 不符" % sid)
            if str(p.get("verdict")) == "MISMATCH":
                out["recompute"].append("stat %s 复算 MISMATCH" % sid)
        if s.get("value") is not None and str(s.get("value")) not in claim_norm:
            out["recompute"].append("stat %s 数值无 claims 回证" % sid)
    if str(recompute.get("verdict")) == "FAIL":
        out["recompute"].append("recompute.verdict=FAIL")
    # anomaly：主动处理须有已声明规则；stats 口径须已声明
    for i, a in enumerate(anomalies):
        if str(a.get("handling")) in ("dropped", "imputed", "clipped", "filtered"):
            rr = str(a.get("rule_ref") or "")
            if rr not in rule_ids:
                out["anomaly"].append("anomalies[%d] rule_ref 未声明" % i)
    for i, s in enumerate(stats):
        for rr in (s.get("rule_refs") or []):
            if str(rr) not in rule_ids:
                out["anomaly"].append("stats[%d] rule_ref 未声明" % i)
    return out


def count_caught(report):
    """按问题串标签前缀统计被校验层捕获的违规数。"""
    cnt = {t: 0 for t in TAGS}
    for pr in report.get("problems") or []:
        m = re.match(r"^\[(\w+)\]", str(pr))
        if m and m.group(1) in cnt:
            cnt[m.group(1)] += 1
    return cnt


def mode_metrics(res, report, label, obj_truth):
    idx = count_caught(report)
    inner = (res or {}).get("result") or {}
    reqs = [r for r in (inner.get("requirements") or []) if isinstance(r, dict)]
    cov_map = [c for c in (inner.get("coverage_map") or []) if isinstance(c, dict)]
    stats = [s for s in (inner.get("stats") or []) if isinstance(s, dict)]
    missed = {t: max(len(obj_truth[t]) - idx[t], 0) for t in TAGS}
    unmapped = sum(1 for i, r in enumerate(reqs)
                   if not any(str(c.get("req_id")) == str(r.get("req_id") or "R%d" % (i + 1))
                              for c in cov_map))
    unbacked = len(report.get("unbacked_numbers") or [])
    manual_items = sum(missed.values()) + unmapped + unbacked
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0
    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "coverage_missed": missed["coverage"],
            "trace_missed": missed["trace"],
            "recompute_missed": missed["recompute"],
            "anomaly_missed": missed["anomaly"],
            "violations_objective": {t: len(obj_truth[t]) for t in TAGS},
            "violations_caught": idx,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unmapped_requirements": unmapped,
                                        "unbacked_numbers": unbacked,
                                        "missed_total": sum(missed.values())},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    cov_map = [c for c in (inner.get("coverage_map") or []) if isinstance(c, dict)]
    if cov_map:
        gone = cov_map.pop(0)
        inner["coverage_map"] = cov_map
        plan.append("删除需求 %s 的 coverage_map 条目（映射丢失）" % gone.get("req_id"))
    if cov_map:
        cov_map[0]["artifact_id"] = "ghost-artifact"
        plan.append("coverage_map[%s] artifact_id 改为不存在的 ghost-artifact（映射失据）"
                    % cov_map[0].get("req_id"))
    stats = [s for s in (inner.get("stats") or []) if isinstance(s, dict)]
    if stats:
        old = stats[0].get("value")
        try:
            stats[0]["value"] = (old + 1) if isinstance(old, (int, float)) else "tampered"
        except Exception:
            stats[0]["value"] = "tampered"
        plan.append("stats[%s] 数值篡改 %r→%r（复算必不符）"
                    % (stats[0].get("stat_id"), old, stats[0]["value"]))
        stats[0]["rule_refs"] = ["GHOST-RULE"]
        plan.append("stats[%s] rule_refs 改为 GHOST-RULE（口径漂移）" % stats[0].get("stat_id"))
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    if steps:
        if "exit_code" in steps[0]:
            del steps[0]["exit_code"]
            plan.append("steps[%s] 删除 exit_code（执行结果未记录）" % steps[0].get("step"))
        if len(steps) > 1:
            steps[-1]["log_ref"] = ""
            plan.append("steps[%s] 清空 log_ref（日志未留痕）" % steps[-1].get("step"))
    env = inner.get("environment")
    if isinstance(env, dict):
        env["python_version"] = None
        plan.append("environment.python_version 置空（运行环境未记录）")
    anomalies = [a for a in (inner.get("anomalies") or []) if isinstance(a, dict)]
    if anomalies:
        anomalies[0]["rule_ref"] = "GHOST-RULE"
        plan.append("anomalies[%s] rule_ref 改为 GHOST-RULE（静默处理）" % anomalies[0].get("anomaly_id"))
    if not plan:
        plan.append("（无可注入位置：覆盖映射/统计/步骤均为空）")
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

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
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

    delta_keys = ("coverage_missed", "trace_missed", "recompute_missed",
                  "anomaly_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "coverage_missed", "mechanism": "需求-代码覆盖映射检查（每条 requirement "
         "必须有 coverage_map 条目且 artifact_id 存在；uncovered/partial 须登记）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后需求漏实现不再判 FAIL，代码看似完成实则缺功能"},
        {"metric": "trace_missed", "mechanism": "执行留痕检查（命令 python3 前缀 + exit_code + "
         "log_ref + environment.python_version + execution_traces 非空）",
         "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后运行不留痕，他人无法独立重跑，失败现场丢失"},
        {"metric": "recompute_missed", "mechanism": "数值独立复算核验（每条 stat 必须出现在 "
         "recompute.per_stat、declared 与 stats 一致、verdict=PASS、数字在 claims 回证）",
         "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后『跑通了但算错了』的静默错误不再可检出"},
        {"metric": "anomaly_missed", "mechanism": "异常登记与口径一致（dropped/imputed/clipped/"
         "filtered 的 rule_ref 必须在事前声明的 cleaning_rules 内）",
         "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后缺失值/异常值可被静默处理，口径漂移不可检出"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未映射需求 + 无回证数字合计",
         "formula": "四类漏检 + unmapped + unbacked", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "六步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         % ROUND_BATCH, "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回数据/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（coverage/trace/recompute/anomaly），枚举、结构守卫、steps/"
        "coverage 汇总等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided。",
        "cleaning_rules 未事前声明时规则真值不可得，anomaly_missed 属『无法判定』而非『无违规』。",
        "把 --ablate 的退化结果当作交付自检结论即为误用。",
        "污染反例自测只在副本上注入，原 result.json 不被修改。",
    ]

    gain_evidence = {
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
        "requirements_total": len([r for r in ((res.get("result") or {}).get("requirements") or [])
                                   if isinstance(r, dict)]),
        "stats_total": len([s for s in ((res.get("result") or {}).get("stats") or [])
                            if isinstance(s, dict)]),
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
