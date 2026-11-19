#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（exp-param-optimize，实验参数优化建议）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭当前值依据审计 / 优化建议完备 / 耦合约束登记 / 寻优方法 / 证据回证五组
检查），逐项对照可观测指标（全部实测，不臆造）：

  1. audit_missed        当前值依据登记违规漏检数（缺 basis/域声明未捕获）
  2. suggestions_missed  优化建议违规漏检数（建议无据/收益不量化未捕获）
  3. coupling_missed     耦合约束违规漏检数（约束缺失/引用无效未捕获）
  4. search_missed       寻优方法违规漏检数（缺停止判据/预算口径未捕获）
  5. evidence_missed     依据/风险/数字回证缺失漏检数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入：清空参数 basis 登记、清空建议依据、清空预期收益量化、清空耦合约束、
清空 claims——正常模式须抓到，退出码恒 0）。

**本脚本只产出对照证据；退化模式仅用于增益对照，不得用于交付自检。**
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
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目


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


def check_index(report):
    out = {}
    for s in report.get("self_check") or []:
        if isinstance(s, dict) and s.get("item"):
            out[s["item"]] = s
    return out


def caught(idx, key):
    e = idx.get(key)
    return bool(e and e.get("applied") and e.get("match") is False)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def objective_violations(res):
    """独立复算五组客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    params = [p for p in (inner.get("parameters") or []) if isinstance(p, dict)]
    suggs = [s for s in (inner.get("optimization_suggestions") or []) if isinstance(s, dict)]
    cons = [c for c in (inner.get("coupling_constraints") or []) if isinstance(c, dict)]
    pmap = [m for m in (inner.get("parameter_response_map") or []) if isinstance(m, dict)]
    metrics = [m for m in (inner.get("response_metrics") or []) if isinstance(m, dict)]
    search = inner.get("search_strategy") or {}
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    claims = res.get("claims") if isinstance(res.get("claims"), list) else []
    param_ids = {str(p.get("param_id") or "") for p in params}
    metric_ids = {str(m.get("metric_id") or "") for m in metrics}

    aud, sug, coup, sea, evid = [], [], [], [], []

    if not params:
        aud.append("参数表为空")
    for i, p in enumerate(params):
        dom = p.get("domain") if isinstance(p.get("domain"), dict) else {}
        if not (all(str(p.get(k) or "").strip() for k in ("name", "unit", "basis", "source_ref"))
                and p.get("basis") in ("manual", "pilot", "literature", "vendor")
                and is_num(dom.get("min")) and is_num(dom.get("max"))
                and is_num(p.get("current_value"))):
            aud.append("parameters[%d].%s 审计要素缺失" % (i, p.get("param_id")))

    if not suggs:
        sug.append("优化建议为空")
    for i, s in enumerate(suggs):
        g = s.get("expected_gain") if isinstance(s.get("expected_gain"), dict) else {}
        ok = (str(s.get("param_id") or "") in param_ids
              and bool(str(s.get("basis") or "").strip())
              and bool(str(s.get("rationale") or "").strip())
              and str(g.get("metric_ref") or "") in metric_ids
              and is_num(g.get("baseline")) and is_num(g.get("projected"))
              and is_num(g.get("delta"))
              and abs(float(g["projected"]) - float(g["baseline"]) - float(g["delta"])) <= 1e-6)
        if not ok:
            sug.append("suggestions[%d].%s 建议无据或收益未量化" % (i, s.get("sugg_id")))

    if not cons:
        coup.append("耦合约束未登记")
    for i, c in enumerate(cons):
        if c.get("kind") == "none_declared":
            if not str(c.get("source") or "").strip():
                coup.append("constraints[%d] 无耦合声明缺 source" % i)
            continue
        refs = [str(x) for x in (c.get("params") or []) if str(x).strip()]
        if not (refs and all(x in param_ids for x in refs)
                and str(c.get("expression") or "").strip()
                and str(c.get("source") or "").strip()):
            coup.append("constraints[%d] 约束不完备" % i)

    if search.get("method") not in ("ofat", "grid", "rsm", "bayesian", "sequential",
                                    "staged_screening"):
        sea.append("寻优方法缺失或非法")
    for k in ("rationale", "stop_criteria", "budget_note", "initial_points"):
        if not str(search.get(k) or "").strip():
            sea.append("search_strategy.%s 缺失" % k)

    if not pmap:
        evid.append("参数-响应关系图为空")
    for i, m in enumerate(pmap):
        if not (str(m.get("param_id") or "") in param_ids
                and str(m.get("metric_id") or "") in metric_ids
                and str(m.get("relation") or "").strip()
                and str(m.get("evidence") or "").strip()):
            evid.append("response_map[%d] 关系不完备" % i)
    if not metrics or not all(str(m.get("measurement") or "").strip() for m in metrics):
        evid.append("响应指标缺测量口径")
    if not risks:
        evid.append("risks 为空")
    corpus = ""
    try:
        corpus = json.dumps(claims, ensure_ascii=False) if claims else ""
    except Exception:
        corpus = ""
    numeric_vals = 0
    for p in params:
        if is_num(p.get("current_value")):
            numeric_vals += 1
            if corpus and str(p["current_value"]) not in corpus:
                evid.append("current_value %s 未回证" % p["current_value"])
    for s in suggs:
        g = s.get("expected_gain") if isinstance(s.get("expected_gain"), dict) else {}
        for v in (s.get("suggested_value"), g.get("projected")):
            if is_num(v):
                numeric_vals += 1
                if corpus and str(v) not in corpus:
                    evid.append("建议数值 %s 未回证" % v)
    if numeric_vals and not claims:
        evid.append("claims 为空（%d 个业务数值失去回证）" % numeric_vals)
    return {"audit": aud, "suggestions": sug, "coupling": coup,
            "search": sea, "evidence": evid}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数（分组，逐条计数）。"""
    inner = (res or {}).get("result") or {}
    a = caught(idx, "audit.complete")
    for i in range(len(inner.get("parameters") or [])):
        if caught(idx, "parameters[%d].audited" % i):
            a += 1
    s = caught(idx, "suggestions.complete")
    for i in range(len(inner.get("optimization_suggestions") or [])):
        if caught(idx, "suggestions[%d].complete" % i):
            s += 1
    c = caught(idx, "coupling.registered")
    for i in range(len(inner.get("coupling_constraints") or [])):
        if caught(idx, "constraints[%d].valid" % i) or caught(idx, "constraints[%d].declared" % i):
            c += 1
    q = caught(idx, "search.strategy_complete")
    e = caught(idx, "response_map.present") + caught(idx, "claims.backchain") \
        + caught(idx, "metrics.measurable")
    for i in range(len(inner.get("parameter_response_map") or [])):
        if caught(idx, "response_map[%d].complete" % i):
            e += 1
    return {"audit": a, "suggestions": s, "coupling": c, "search": q, "evidence": e}


def mode_metrics(res, report, label):
    idx = check_index(report)
    gt = objective_violations(res)
    caught_d = count_caught(res, report, idx)
    disabled = set(report.get("disabled_checks") or [])

    missed = {}
    for g in ("audit", "suggestions", "coupling", "search", "evidence"):
        if g in disabled:
            missed[g] = len(gt[g])  # 关闭后全部漏检
        else:
            missed[g] = max(len(gt[g]) - caught_d.get(g, 0), 0)

    manual_items = sum(missed.values())
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = (res.get("result") or {}).get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "audit_missed": missed["audit"],
            "suggestions_missed": missed["suggestions"],
            "coupling_missed": missed["coupling"],
            "search_missed": missed["search"],
            "evidence_missed": missed["evidence"],
            "violations_objective": {g: len(gt[g]) for g in gt},
            "manual_review_items": manual_items,
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
    # 污染1：当前值依据登记缺失
    for p_ in inner.get("parameters") or []:
        if isinstance(p_, dict) and p_.get("basis"):
            p_["basis"] = ""
    plan.append("清空 parameters[].basis（当前值依据登记缺失）")
    # 污染2：建议无据
    for s in inner.get("optimization_suggestions") or []:
        if isinstance(s, dict) and s.get("basis"):
            s["basis"] = ""
    plan.append("清空 optimization_suggestions[].basis（建议无据）")
    # 污染3：收益虚标/不量化
    for s in inner.get("optimization_suggestions") or []:
        if isinstance(s, dict) and isinstance(s.get("expected_gain"), dict):
            s["expected_gain"] = {"metric_ref": s["expected_gain"].get("metric_ref"),
                                  "baseline": None, "projected": None, "delta": None,
                                  "claim": "预计显著提升（虚标示意）"}
    plan.append("把 expected_gain 改为无数字的虚标声明（收益不量化）")
    # 污染4：耦合约束缺失
    if inner.get("coupling_constraints"):
        inner["coupling_constraints"] = []
        plan.append("清空 coupling_constraints（参数间耦合约束缺失）")
    # 污染5：claims 证据链缺失
    p["claims"] = []
    plan.append("清空 claims（业务数值失去回证）")
    if not plan:
        plan.append("（无可注入位置：方案要素为空）")
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
        ap.add_argument("--marker", default="/app/work/skill_marker.json")
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
    rub_path = os.path.join(args.work_dir or ".", "rubric.json")
    rub = load_json(rub_path) if os.path.exists(rub_path) else None
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"
    marker = load_json(args.marker)
    marker_state = "enforced" if isinstance(marker, dict) and marker.get("all_present") else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state,
                         rubric_state=rubric_state, marker_state=marker_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state,
                           rubric_state=rubric_state, marker_state=marker_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("audit_missed", "suggestions_missed", "coupling_missed",
                  "search_missed", "evidence_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "audit_missed", "mechanism": "当前参数取值依据审计（name/unit/domain/"
         "basis∈manual|pilot|literature|vendor/source_ref/当前值逐项齐全）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后当前值无出处、域声明缺失不再判 FAIL，参数表退化成拍脑袋取值"},
        {"metric": "suggestions_missed", "mechanism": "优化建议完备检查（param_ref 有效、"
         "basis/rationale 非空、expected_gain 量化且 delta=projected−baseline）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后建议无据、收益虚标（只有形容词没有数字）不再判 FAIL"},
        {"metric": "coupling_missed", "mechanism": "参数间耦合约束登记（params 引用有效、"
         "expression/source 齐备，确无耦合须显式声明）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后约束缺失或引用无效参数不再判 FAIL，可行域感知失效"},
        {"metric": "search_missed", "mechanism": "寻优方法检查（method 枚举、初始点、"
         "停止判据、预算口径齐备；grid 须给分辨率）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后搜索策略没有收敛依据与停止判据不再判 FAIL"},
        {"metric": "evidence_missed", "mechanism": "参数-响应关系/风险/claims 数字回证"
         "（关系条目引用有效、数值须出现在 claim text/quote）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后关系无依据、风险无止损、数字无回证不再判 FAIL"},
        {"metric": "manual_review_items", "mechanism": "五组漏检合计需人工核对条目",
         "formula": "五组 missed 之和", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐项核对的条目增加"},
        {"metric": "steps_count", "mechanism": "八步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回问/返工所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭五组检查（audit/suggestions/coupling/search/evidence），枚举、"
        "completeness 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五组违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序复算真值不可得，策略排序类漏检记 0 但属『无法判定』而非『无违规』。",
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
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state,
                           rubric_state=rubric_state, marker_state=marker_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state,
                        rubric_state=rubric_state, marker_state=marker_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "audit_missed": pm_n["metrics"]["audit_missed"],
                            "suggestions_missed": pm_n["metrics"]["suggestions_missed"],
                            "coupling_missed": pm_n["metrics"]["coupling_missed"],
                            "search_missed": pm_n["metrics"]["search_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "audit_missed": pm_d["metrics"]["audit_missed"],
                              "suggestions_missed": pm_d["metrics"]["suggestions_missed"],
                              "coupling_missed": pm_d["metrics"]["coupling_missed"],
                              "search_missed": pm_d["metrics"]["search_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "audit_missed": pm_d["metrics"]["audit_missed"]
                                - pm_n["metrics"]["audit_missed"],
                "suggestions_missed": pm_d["metrics"]["suggestions_missed"]
                                      - pm_n["metrics"]["suggestions_missed"],
                "coupling_missed": pm_d["metrics"]["coupling_missed"]
                                   - pm_n["metrics"]["coupling_missed"],
                "search_missed": pm_d["metrics"]["search_missed"]
                                 - pm_n["metrics"]["search_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
            },
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
        "parameters_total": len((res.get("result") or {}).get("parameters") or []),
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
