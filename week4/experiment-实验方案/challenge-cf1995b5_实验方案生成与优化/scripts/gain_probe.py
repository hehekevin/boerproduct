#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（exp-plan-design，实验方案设计）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭变量表完备 / 对照设置 / 功效依据 / 分析对齐 / 证据回证五组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. variables_missed    变量表违规漏检数（缺操作定义/测量/单位未捕获）
  2. controls_missed     对照设置违规漏检数（无对照/未写明排除混杂未捕获）
  3. power_missed        样本量功效依据漏登记数
  4. alignment_missed    分析计划-假设未对齐漏检数
  5. evidence_missed     依据/风险/数字回证缺失漏检数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入：清空对照设置、清空变量操作定义、清空功效登记、清空分析计划、清空
claims——正常模式须抓到，退出码恒 0）。

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
    from verify_check import analyze, fused, weights_ok  # noqa: E402
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


def _vars_list(variables):
    out = []
    for role in ("independent", "dependent", "control"):
        for j, v in enumerate((variables or {}).get(role) or []):
            if isinstance(v, dict):
                out.append((role, j, v))
    return out


def objective_violations(res):
    """独立复算五组客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    variables = inner.get("variables") or {}
    hyps = [h for h in (inner.get("hypotheses") or []) if isinstance(h, dict)]
    controls = [c for c in (inner.get("controls") or []) if isinstance(c, dict)]
    groups = [g for g in (inner.get("groups") or []) if isinstance(g, dict)]
    nreg = [r for r in ((inner.get("power_basis") or {}).get("n_registry") or [])
            if isinstance(r, dict)]
    protocol = [s for s in (inner.get("protocol") or []) if isinstance(s, dict)]
    measures = [m for m in (inner.get("measurements") or []) if isinstance(m, dict)]
    plans = [p for p in (inner.get("analysis_plan") or []) if isinstance(p, dict)]
    risks = [r for r in (inner.get("risks") or []) if isinstance(r, dict)]
    claims = res.get("claims") if isinstance(res.get("claims"), list) else []

    var, con, pow_, alg, evid = [], [], [], [], []

    ivs = [v for v in (variables.get("independent") or []) if isinstance(v, dict)]
    dvs = [v for v in (variables.get("dependent") or []) if isinstance(v, dict)]
    cvs = [v for v in (variables.get("control") or []) if isinstance(v, dict)]
    if not ivs or not dvs or not cvs:
        var.append("变量表不完备")
    for role, j, v in _vars_list(variables):
        if not all(str(v.get(k) or "").strip() for k in
                   ("name", "operational_definition", "measurement", "unit")):
            var.append("%s[%d].%s 缺要素" % (role, j, v.get("var_id")))
    for i, h in enumerate(hyps):
        if not str(h.get("text") or "").strip() or h.get("testable") is not True:
            var.append("%s 不可检验或缺 text" % (h.get("hypothesis_id") or i))

    group_ids = {str(g.get("group_id") or "") for g in groups}
    if len(groups) < 2 or not controls:
        con.append("组设计/对照设置缺失")
    for i, c in enumerate(controls):
        if str(c.get("group_id") or "") not in group_ids:
            con.append("controls[%d].group_id 无效" % i)
        if not str(c.get("excludes_confound") or "").strip():
            con.append("controls[%d] 未写明排除混杂" % i)

    reg_by_gid = {}
    for r in nreg:
        reg_by_gid[str(r.get("group_id") or "")] = r
    for i, g in enumerate(groups):
        r = reg_by_gid.get(str(g.get("group_id") or ""))
        if not (isinstance(r, dict) and r.get("n") == g.get("n")
                and str(r.get("method") or "").strip() and str(r.get("source") or "").strip()):
            pow_.append("%s n 未登记功效依据" % (g.get("group_id") or i))

    hyp_ids = [str(h.get("hypothesis_id") or "") for h in hyps]
    dv_ids = {str(v.get("var_id") or "") for v in dvs}
    covered = {str(p.get("hypothesis_id") or "") for p in plans}
    n_hyps = len(hyps)
    for i in range(n_hyps):
        hid = str(hyps[i].get("hypothesis_id") or i)
        if hid not in covered:
            alg.append("假设 %s 未被分析计划引用" % hid)
    for i, p in enumerate(plans):
        if str(p.get("hypothesis_id") or "") and str(p.get("hypothesis_id")) not in hyp_ids:
            alg.append("analysis_plan[%d] 引用无效假设" % i)
        if not str(p.get("test") or "").strip():
            alg.append("analysis_plan[%d] 缺检验方法" % i)
    for d in dv_ids:
        if not any(str(m.get("dv_ref") or "") == d for m in measures):
            alg.append("因变量 %s 缺测量条目" % d)

    if not protocol:
        evid.append("protocol 为空")
    for i, s in enumerate(protocol):
        for p in (s.get("params") or []) if isinstance(s.get("params"), list) else []:
            if isinstance(p, dict) and p.get("value") is not None \
                    and not str(p.get("basis") or "").strip():
                evid.append("protocol[%d] 参数 %r 缺 basis" % (i, p.get("name")))
    if not risks:
        evid.append("risks 为空")
    corpus = ""
    try:
        corpus = json.dumps(claims, ensure_ascii=False) if claims else ""
    except Exception:
        corpus = ""
    numeric_params = 0
    for i, s in enumerate(protocol):
        for p in (s.get("params") or []) if isinstance(s.get("params"), list) else []:
            if isinstance(p, dict) and isinstance(p.get("value"), (int, float)):
                numeric_params += 1
                if corpus and str(p["value"]) not in corpus:
                    evid.append("protocol[%d] 参数值 %s 未回证" % (i, p["value"]))
    if numeric_params and not claims:
        evid.append("claims 为空（%d 个数值参数失去回证）" % numeric_params)
    return {"variables": var, "controls": con, "power": pow_,
            "alignment": alg, "evidence": evid}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数（分组）。"""
    n = caught(idx, "variables.complete") + caught(idx, "variables.table_present")
    c = caught(idx, "controls.count")
    inner = (res or {}).get("result") or {}
    p = sum(1 for gi in range(len(inner.get("groups") or []))
            if caught(idx, "groups[%d].n_registered" % gi))
    a = caught(idx, "measurements.cover_dvs")
    hyps = inner.get("hypotheses") or []
    a += sum(1 for hi in range(len(hyps))
             if caught(idx, "hypotheses[%d].analysis_aligned" % hi))
    e = caught(idx, "protocol.params_basis")
    if caught(idx, "protocol.steps_present"):
        e += 1
    if caught(idx, "claims.backchain"):
        e += 1
    return {"variables": n, "controls": c, "power": p, "alignment": a, "evidence": e}


def mode_metrics(res, report, label):
    idx = check_index(report)
    gt = objective_violations(res)
    caught_d = count_caught(res, report, idx)
    disabled = set(report.get("disabled_checks") or [])

    missed = {}
    for g in ("variables", "controls", "power", "alignment", "evidence"):
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
            "variables_missed": missed["variables"],
            "controls_missed": missed["controls"],
            "power_missed": missed["power"],
            "alignment_missed": missed["alignment"],
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
    # 污染1：无对照设计
    if inner.get("controls"):
        inner["controls"] = []
        plan.append("清空 controls（无对照设计）")
    # 污染2：变量操作定义缺失
    variables = inner.get("variables") or {}
    for role in ("independent", "dependent", "control"):
        lst = variables.get(role) or []
        if lst and isinstance(lst[0], dict):
            lst[0]["operational_definition"] = ""
            plan.append("%s[0]（%s）清空 operational_definition" % (role, lst[0].get("var_id")))
            break
    # 污染3：功效依据缺失
    if (inner.get("power_basis") or {}).get("n_registry"):
        inner["power_basis"]["n_registry"] = []
        plan.append("清空 power_basis.n_registry（样本量无功效依据）")
    # 污染4：分析计划-假设不对齐
    if inner.get("analysis_plan"):
        inner["analysis_plan"] = []
        plan.append("清空 analysis_plan（假设失去分析对齐）")
    # 污染5：claims 证据链缺失
    p["claims"] = []
    plan.append("清空 claims（参数数值失去回证）")
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

    delta_keys = ("variables_missed", "controls_missed", "power_missed",
                  "alignment_missed", "evidence_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "variables_missed", "mechanism": "变量表完备性检查（独立/因/控制变量≥1，"
         "操作定义+测量方式+单位逐项齐全，假设 testable）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后缺操作定义/缺单位的变量不再判 FAIL，变量表退化成名词罗列"},
        {"metric": "controls_missed", "mechanism": "对照设置检查（groups≥2、controls≥1、"
         "group_id 有效、excludes_confound 非空）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后无对照设计、未写明排除混杂的对照不再判 FAIL"},
        {"metric": "power_missed", "mechanism": "样本量/功效依据登记（groups[].n 必须在"
         " n_registry 有 method+source 的条目且 n 一致）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后样本量拍脑袋不再被检出，功效依据台账失效"},
        {"metric": "alignment_missed", "mechanism": "分析计划-假设对齐（每个假设被 ≥1 条"
         " analysis_plan 引用；引用 id 有效；因变量有测量条目）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后分析计划与假设脱钩不再可检出，判读标准丢失"},
        {"metric": "evidence_missed", "mechanism": "依据/风险完备 + claims 数字回证"
         "（参数须标 basis；数值参数须出现在 claim text/quote）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后参数无来源、风险无止损、数字无回证不再判 FAIL"},
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
        "退化模式关闭五组检查（variables/controls/power/alignment/evidence），枚举、"
        "completeness 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五组违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序复算真值不可得，方案排序类漏检记 0 但属『无法判定』而非『无违规』。",
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
                            "variables_missed": pm_n["metrics"]["variables_missed"],
                            "controls_missed": pm_n["metrics"]["controls_missed"],
                            "power_missed": pm_n["metrics"]["power_missed"],
                            "alignment_missed": pm_n["metrics"]["alignment_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "variables_missed": pm_d["metrics"]["variables_missed"],
                              "controls_missed": pm_d["metrics"]["controls_missed"],
                              "power_missed": pm_d["metrics"]["power_missed"],
                              "alignment_missed": pm_d["metrics"]["alignment_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "variables_missed": pm_d["metrics"]["variables_missed"]
                                    - pm_n["metrics"]["variables_missed"],
                "controls_missed": pm_d["metrics"]["controls_missed"]
                                   - pm_n["metrics"]["controls_missed"],
                "power_missed": pm_d["metrics"]["power_missed"]
                                - pm_n["metrics"]["power_missed"],
                "alignment_missed": pm_d["metrics"]["alignment_missed"]
                                    - pm_n["metrics"]["alignment_missed"],
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
        "hypotheses_total": len((res.get("result") or {}).get("hypotheses") or []),
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
