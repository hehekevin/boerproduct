#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（trend-frontier-analyst）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭主题归属一致性 / 趋势判定复算 / 证据回证 / 登记完整性四组检查），逐项
对照可观测指标（全部实测，不臆造）：

  1. consistency_missed  主题归属违规漏检数（topic_id 与机械重算不符等）
  2. trend_missed        趋势判定漏检数（年度计数/增速/分级复算不符）
  3. evidence_missed     证据缺失漏检数（主题无 claims 回证 / 数字无回证 /
                         空白无排除证据）
  4. registry_missed     登记漏项数（未归属未登记 / coverage 不符 / 外推边界缺失）
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（篡改增速数字 / 错标分级 / 清空证据 / 拆除空白排除证据 / 清空 claims；
正常模式须抓到污染项，原 result.json 不被改动，退出码恒 0）。

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
    from trend_engine import assign_topic, build_coverage, growth_of, norm_text, \
        stage_of, thresholds_of, yearly_counts  # noqa: E402
    from verify_check import analyze  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 trend_engine/verify_check: %s" % e)
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


def objective_violations(res):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    topics = [t for t in (inner.get("topics") or []) if isinstance(t, dict)]
    gaps = [g for g in (inner.get("gaps") or []) if isinstance(g, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    registry = inner.get("source_registry") or []
    cov = inner.get("coverage") or {}
    clustering = inner.get("clustering_policy") or {}
    trend_policy = inner.get("trend_policy") or {}
    clusters = clustering.get("clusters") or []
    window = trend_policy.get("window") or {}
    con, trend_bad, evid, reg = [], [], [], []

    claim_by_topic = {}
    for c in claims:
        claim_by_topic.setdefault(str(c.get("source_id") or ""), []).append(c)

    # --- consistency ---
    for it in items:
        iid = str(it.get("item_id") or "")
        if it.get("judged") is True:
            if it.get("topic_id"):
                exp_tid, _kw = assign_topic(it, clusters)
                if exp_tid != str(it.get("topic_id")):
                    con.append("%s(topic_mismatch)" % iid)
            elif not str(it.get("pending_reason") or "").strip():
                con.append("%s(unassigned_no_reason)" % iid)
            if it.get("relevance") == "irrelevant" and it.get("topic_id"):
                con.append("%s(irrelevant_assigned)" % iid)
        if it.get("relevance") in ("core", "related") and not (
                str(it.get("evidence_quote") or "").strip()
                and str(it.get("evidence_location") or "").strip()):
            evid.append("%s(no_quote)" % iid)

    for t in topics:
        tid = str(t.get("topic_id") or "")
        member_ids = set(str(x) for x in (t.get("item_ids") or []))
        for rid in (t.get("representative_ids") or []):
            rep = next((it for it in items if str(it.get("item_id")) == str(rid)), None)
            if not rep or str(rep.get("topic_id") or "") != tid \
                    or not str(rep.get("evidence_quote") or "").strip():
                con.append("topic:%s(rep_binding:%s)" % (tid, rid))

    # --- trend ---
    S, E = window.get("start_year"), window.get("end_year")
    window_ok = isinstance(S, int) and isinstance(E, int) and S <= E
    if not (str(clustering.get("declared_at") or "").strip() and clusters):
        trend_bad.append("clustering_policy_not_declared")
    if not str(trend_policy.get("declared_at") or "").strip():
        trend_bad.append("trend_policy_not_declared")
    em_th, de_th = thresholds_of(trend_policy)
    for t in topics:
        tid = str(t.get("topic_id") or "")
        if window_ok:
            counts = yearly_counts(items, tid, window)
            exp_counts = {str(y): int(counts.get(y, 0))
                          for y in range(int(S), int(E) + 1)}
            got_counts = {str(k): int(v) for k, v in (t.get("yearly_counts") or {}).items()}
            if got_counts != exp_counts:
                trend_bad.append("topic:%s(yearly_counts)" % tid)
            g = growth_of(counts, window)
            gr = t.get("growth_rate")
            if not (isinstance(gr, (int, float)) and abs(float(gr) - g["growth_rate"]) <= 1e-3):
                trend_bad.append("topic:%s(growth %s vs %s)" % (tid, gr, g["growth_rate"]))
            exp_stage = stage_of(g["growth_rate"], em_th, de_th) if t.get("total_count") else "no_evidence"
            if t.get("stage") != exp_stage:
                trend_bad.append("topic:%s(stage %s vs %s)" % (tid, t.get("stage"), exp_stage))

    # --- evidence ---
    for t in topics:
        tid = str(t.get("topic_id") or "")
        cl = claim_by_topic.get(tid) or []
        if not cl:
            evid.append("topic:%s(no_claim)" % tid)
            continue
        quotes = [norm_text_e(e.get("quote")) for c in cl for e in (c.get("evidence") or [])]
        texts = [norm_text_e(c.get("text")) for c in cl] + quotes
        for rid in (t.get("representative_ids") or []):
            rep = next((it for it in items if str(it.get("item_id")) == str(rid)), None)
            q = norm_text_e((rep or {}).get("evidence_quote"))
            if q and q not in quotes:
                evid.append("topic:%s(rep_quote:%s)" % (tid, rid))
        if isinstance(t.get("growth_rate"), (int, float)):
            gstr = str(round(float(t["growth_rate"]), 2))
            if not any(gstr in tx for tx in texts):
                evid.append("topic:%s(growth_unbacked)" % tid)
    for g in gaps:
        if g.get("status") == "identified":
            ex = [e for e in (g.get("exclusion_evidence") or []) if isinstance(e, dict)]
            if not (str(g.get("search_scope") or "").strip() and ex
                    and all(str(e.get("quote") or "").strip() for e in ex)):
                evid.append("gap:%s(no_exclusion)" % g.get("gap_id"))

    # --- registry ---
    for it in items:
        iid = str(it.get("item_id") or "")
        if it.get("judged") is True and not it.get("topic_id") \
                and not any(str(p.get("item_id")) == iid for p in pending_reg):
            reg.append("%s(unassigned_unregistered)" % iid)
        if not str(it.get("source_ref") or "").strip():
            reg.append("%s(no_source_ref)" % iid)
    if items and not registry:
        reg.append("source_registry_empty")
    if cov:
        exp = build_coverage(items, topics)
        for k, v in exp.items():
            if v is not None and isinstance(cov.get(k), int) and cov[k] != v:
                reg.append("coverage:%s" % k)
    extrap = inner.get("extrapolation") or {}
    if not (isinstance(extrap.get("allowed"), bool) and str(extrap.get("rule") or "").strip()):
        reg.append("extrapolation_missing")

    return {"consistency": con, "trend": trend_bad, "evidence": evid, "registry": reg}


def norm_text_e(s):
    import re
    return re.sub(r"\s+", "", str(s or ""))


def count_caught(report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    res = report.get("_res") or {}
    items = [it for it in ((res.get("result") or {}).get("items") or []) if isinstance(it, dict)]
    topics = [t for t in ((res.get("result") or {}).get("topics") or []) if isinstance(t, dict)]
    gaps = [g for g in ((res.get("result") or {}).get("gaps") or []) if isinstance(g, dict)]
    c = sum(1 for i in range(len(items))
            if caught(idx, "items[%d].topic_assignment_recompute" % i)
            or caught(idx, "items[%d].unassigned_reasoned" % i))
    r = sum(1 for i in range(len(topics))
            if caught(idx, "topics[%d].yearly_counts_recompute" % i)
            or caught(idx, "topics[%d].growth_recompute" % i)
            or caught(idx, "topics[%d].stage_recompute" % i))
    e = sum(1 for i in range(len(topics))
            if caught(idx, "topics[%d].claim_backed" % i)
            or caught(idx, "topics[%d].rep_quote_in_claim" % i))
    e += sum(1 for i in range(len(items))
             if caught(idx, "items[%d].quote_location" % i))
    e += sum(1 for i in range(len(gaps))
             if caught(idx, "gaps[%d].exclusion_evidence" % i))
    g = sum(1 for i in range(len(items))
            if caught(idx, "items[%d].unassigned_registered" % i))
    g += sum(1 for i in range(len(gaps))
             if caught(idx, "gaps[%d].not_verified_reason" % i))
    return c, r, e, g


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    report["_res"] = res  # 供 count_caught 计条目数（内部字段，不落盘）
    gt = objective_violations(res)
    con_caught, trend_caught, evid_caught, reg_caught = count_caught(report, idx)
    report.pop("_res", None)

    disabled = set(report.get("disabled_checks") or [])
    evid_missed = max(len(gt["evidence"]) - evid_caught, 0) if "evidence" not in disabled \
        else len(gt["evidence"])
    con_missed = max(len(gt["consistency"]) - con_caught, 0) if "consistency" not in disabled \
        else len(gt["consistency"])
    trend_missed = max(len(gt["trend"]) - trend_caught, 0) if "trend" not in disabled \
        else len(gt["trend"])
    reg_missed = max(len(gt["registry"]) - reg_caught, 0) if "registry" not in disabled \
        else len(gt["registry"])

    unjudged = sum(1 for it in items if it.get("judged") is not True)
    manual_items = unjudged + con_missed + trend_missed + evid_missed + reg_missed

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
            "consistency_violations_objective": len(gt["consistency"]),
            "consistency_caught": con_caught,
            "consistency_missed": con_missed,
            "trend_violations_objective": len(gt["trend"]),
            "trend_caught": trend_caught,
            "trend_missed": trend_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_caught": evid_caught,
            "evidence_missed": evid_missed,
            "registry_violations_objective": len(gt["registry"]),
            "registry_caught": reg_caught,
            "registry_missed": reg_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "consistency_missed": con_missed,
                                        "trend_missed": trend_missed,
                                        "evidence_missed": evid_missed,
                                        "registry_missed": reg_missed},
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
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    topics = [t for t in (inner.get("topics") or []) if isinstance(t, dict)]

    # 1. 篡改首个有增速主题的 growth_rate（+0.5）
    for t in topics:
        if isinstance(t.get("growth_rate"), (int, float)) and t.get("total_count"):
            old = t["growth_rate"]
            t["growth_rate"] = round(float(old) + 0.5, 4)
            plan.append("topic %s growth_rate %s → %s（篡改增速数字）"
                        % (t.get("topic_id"), old, t["growth_rate"]))
            break
    # 2. 错标一个主题的分级（合法枚举值但与阈值复算不符）
    for t in topics:
        if t.get("stage") and t.get("stage") != "no_evidence":
            wrong = "mature" if t.get("stage") != "mature" else "declining"
            plan.append("topic %s stage %s → %s（分级错标）"
                        % (t.get("topic_id"), t.get("stage"), wrong))
            t["stage"] = wrong
            break
    # 3. 清空一条 core 条目的逐字证据
    for it in items:
        if it.get("relevance") == "core" and it.get("evidence_quote"):
            plan.append("%s 清空 evidence_quote（证据丢失仍算已判定）" % it.get("item_id"))
            it["evidence_quote"] = None
            break
    # 4. 拆除一个 identified 空白的排除证据
    for g in (inner.get("gaps") or []):
        if isinstance(g, dict) and g.get("status") == "identified" and g.get("exclusion_evidence"):
            plan.append("gap %s 清空 exclusion_evidence（无排除证据仍标空白）" % g.get("gap_id"))
            g["exclusion_evidence"] = []
            break
    # 5. 清空 claims（趋势结论与证据解绑）
    if p.get("claims"):
        plan.append("清空 claims（主题-证据绑定全部丢失）")
        p["claims"] = []
    if not plan:
        plan.append("（无可注入位置：items/topics 为空）")
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
        ap.add_argument("--policy", default="/app/work/trend_policy.json")
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
    pol = load_json(args.policy) if os.path.exists(args.policy) else None
    policy_state = "enforced" if isinstance(pol, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, policy_state=policy_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, policy_state=policy_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("consistency_missed", "trend_missed", "evidence_missed",
                  "registry_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "consistency_missed", "mechanism": "主题归属一致性检查（topic_id 按事前关键词簇"
         "机械重算；matched_keyword 须在簇词表；irrelevant 不得归属；未归属须有理由）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后主题错挂、irrelevant 被聚类、未归属无理由不再被检出，"
         "主题占比与演化叙事失去可复算基础"},
        {"metric": "trend_missed", "mechanism": "趋势判定复算（年度发文量按 items+window 复算；"
         "growth_rate=(late_avg-early_avg)/early_avg；stage 按事前阈值机械复算）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后增速数字被篡改、新兴/成熟/衰退分级错标不再可检出，"
         "趋势结论退化为自述"},
        {"metric": "evidence_missed", "mechanism": "证据回证（每主题须有 claims 回证：代表作"
         " quote 逐字出现、growth_rate 数字与 stage 出现在 claim text/quote；空白主张须有排除证据）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，『没检索到』可被冒充为研究空白"},
        {"metric": "registry_missed", "mechanism": "登记完整性检查（未归属条目 ⇒ pending_review；"
         "source_registry 非空且条目有 source_ref；coverage 与实际一致；外推边界已登记）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后歧义项可静默漏登记，来源清单与外推边界丢失，趋势不可复算"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目合计",
         "formula": "unjudged + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（consistency/trend/evidence/registry），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
        "主题归属按关键词规则机械复算：簇词表是本技能的先验设定，不是文献库官方分类；"
        "术语漂移（同一主题换词）依赖簇词表覆盖度，覆盖不足时按未归属处理并登记待复核。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "trend_policy 未事前声明时分级复算真值不可得，trend_missed 记 0 但属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, policy_state=policy_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, policy_state=policy_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "consistency_missed": pm_n["metrics"]["consistency_missed"],
                            "trend_missed": pm_n["metrics"]["trend_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "registry_missed": pm_n["metrics"]["registry_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "consistency_missed": pm_d["metrics"]["consistency_missed"],
                              "trend_missed": pm_d["metrics"]["trend_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "registry_missed": pm_d["metrics"]["registry_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "consistency_missed": pm_d["metrics"]["consistency_missed"]
                                      - pm_n["metrics"]["consistency_missed"],
                "trend_missed": pm_d["metrics"]["trend_missed"]
                                - pm_n["metrics"]["trend_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "registry_missed": pm_d["metrics"]["registry_missed"]
                                   - pm_n["metrics"]["registry_missed"],
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
        "items_total": len([it for it in ((res.get("result") or {}).get("items") or [])
                            if isinstance(it, dict)]),
        "topics_total": len([t for t in ((res.get("result") or {}).get("topics") or [])
                             if isinstance(t, dict)]),
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
