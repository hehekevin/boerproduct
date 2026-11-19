#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（argchain-review 论文逻辑与论证审查）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭定位可回证 / 分类口径 / 强度匹配登记 / 链节点完备 / 待复核与抑制登记五组
检查），逐项对照可观测指标（全部实测，不臆造）：

  1. location_missed    定位失据漏检数（quote 不在原文/位置为空但未捕获）
  2. taxonomy_missed    分类口径违规漏检数（issue_type/严重度口径/交叉一致）
  3. strength_missed    强度登记缺失漏检数（未登记/字段违规/标尺映射违规）
  4. chain_missed       链节点完备违规漏检数
  5. pending_missed     待复核/抑制漏登记数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（污染为领域化注入：清空引文定位/篡改问题类型/清空强度登记/删除链结论节点/
清空待复核与证据链；正常模式须抓到污染项，退出码恒 0）。

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
    from verify_check import analyze, manuscript_text, norm  # noqa: E402
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


def objective_violations(res, case):
    """独立复算五类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    chains = [c for c in (inner.get("argument_chains") or []) if isinstance(c, dict)]
    matches = [m for m in (inner.get("strength_matches") or []) if isinstance(m, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rule_ids = {str(r.get("rule_id")) for r in (inner.get("suppression_rules") or [])
                if isinstance(r, dict)}
    src = manuscript_text(case)
    loc, taxo, stren, chainv, pend = [], [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    matched_fids = {str(m.get("finding_id")) for m in matches if m.get("finding_id")}
    for f in findings:
        fid = str(f.get("finding_id") or "")
        st = f.get("status")
        if st == "confirmed":
            q = norm(f.get("quote"))
            if not str(f.get("location") or "").strip() or not q or len(q) < 6 or (src and q not in src):
                loc.append(fid)
            cat, sv, it, fc = f.get("category"), f.get("severity"), f.get("issue_type"), f.get("facet")
            if (cat == "suggestion" and sv != "minor") or \
               (cat == "fact_error" and sv not in ("critical", "major")) or \
               (it == "strength_mismatch" and fc not in ("strength_match", "fact_check")):
                taxo.append(fid)
            if it == "strength_mismatch" and fid not in matched_fids:
                stren.append(fid)
            if fid not in claim_ids:
                pend.append(fid)
        if st == "pending":
            if not str(f.get("pending_reason") or "").strip():
                pend.append(fid)
            if not any(str(p.get("finding_id")) == fid for p in pending_reg):
                pend.append(fid)
        if st == "suppressed":
            rec = [s for s in suppressed_reg if str(s.get("finding_id")) == fid]
            if not rec or not all(str(s.get("rule_id")) in rule_ids for s in rec):
                pend.append(fid)
    # 口径声明真值
    taxo_decl = inner.get("issue_taxonomy") or {}
    ttypes = taxo_decl.get("types") or {}
    if not str(taxo_decl.get("declared_at") or "").strip() or \
       not all(str(ttypes.get(k) or "").strip() for k in
               ("broken_chain", "circular_reasoning", "correlation_causation",
                "over_extrapolation", "strength_mismatch", "missing_rebuttal")):
        taxo.append("issue_taxonomy.declared_at")
    rub = inner.get("severity_rubric") or {}
    levels = rub.get("levels") or {}
    if not str(rub.get("declared_at") or "").strip() or \
       not all(str(levels.get(k) or "").strip() for k in ("critical", "major", "minor")):
        taxo.append("severity_rubric.declared_at")
    scale = inner.get("strength_scale") or {}
    if not str(scale.get("declared_at") or "").strip() or \
       not str(scale.get("rule") or "").strip() or \
       not all(str((scale.get("evidence_levels") or {}).get(k) or "").strip() for k in ("E3", "E2", "E1", "E0")) or \
       not all(str((scale.get("claim_levels") or {}).get(k) or "").strip() for k in ("C3", "C2", "C1")):
        stren.append("strength_scale.declared_at")
    # 强度登记字段与标尺映射真值
    for i, m in enumerate(matches):
        mid = str(m.get("match_id") or i)
        if m.get("verdict") not in ("supported", "overstated", "understated", "pending") or \
           not str(m.get("basis") or "").strip() or \
           str(m.get("claim_strength") or "") not in ("C3", "C2", "C1") or \
           str(m.get("evidence_strength") or "") not in ("E3", "E2", "E1", "E0"):
            stren.append(mid)
        if str(m.get("claim_strength")) == "C3" and \
           str(m.get("evidence_strength")) in ("E2", "E1", "E0") and m.get("verdict") == "supported":
            stren.append(mid)
    # 链节点完备真值
    for ci, ch in enumerate(chains):
        cid = str(ch.get("chain_id") or ci)
        nodes = [n for n in (ch.get("nodes") or []) if isinstance(n, dict)]
        roles = [str(n.get("role") or "") for n in nodes]
        if len(nodes) < 2 or ("premise" not in roles and "hypothesis" not in roles) or "conclusion" not in roles:
            chainv.append(cid)
    return {"location": sorted(set(loc)), "taxonomy": sorted(set(taxo)),
            "strength": sorted(set(stren)), "chain": sorted(set(chainv)),
            "pending": sorted(set(pend))}


def count_caught(res, report, idx):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    chains = [c for c in (inner.get("argument_chains") or []) if isinstance(c, dict)]
    matches = [m for m in (inner.get("strength_matches") or []) if isinstance(m, dict)]
    loc = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].location_backed" % i))
    for ci, ch in enumerate(chains):
        for ni, _node in enumerate(ch.get("nodes") or []):
            if caught(idx, "chains[%d].nodes[%d].location_backed" % (ci, ni)):
                loc += 1
    taxo = sum(1 for i in range(len(findings))
               if caught(idx, "findings[%d].severity_rule" % i)
               or caught(idx, "findings[%d].taxonomy_cross" % i))
    if caught(idx, "issue_taxonomy.declared"):
        taxo += 1
    if caught(idx, "severity_rubric.declared"):
        taxo += 1
    stren = sum(1 for i in range(len(matches))
                if caught(idx, "strength_matches[%d].fields" % i)
                or caught(idx, "strength_matches[%d].mapping_rule" % i))
    stren += sum(1 for i in range(len(findings))
                 if caught(idx, "findings[%d].strength_registered" % i))
    if caught(idx, "strength_scale.declared"):
        stren += 1
    chainv = sum(1 for ci in range(len(chains)) if caught(idx, "chains[%d].node_complete" % ci))
    chainv += sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].chain_ref" % i))
    pend = sum(1 for i in range(len(findings))
               if caught(idx, "findings[%d].pending_registered" % i)
               or caught(idx, "findings[%d].suppression_registered" % i)
               or caught(idx, "findings[%d].claim_backed" % i))
    return loc, taxo, stren, chainv, pend


def mode_metrics(res, case, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    gt = objective_violations(res, case)
    loc_c, taxo_c, stren_c, chain_c, pend_c = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    loc_missed = max(len(gt["location"]) - loc_c, 0)
    taxo_missed = max(len(gt["taxonomy"]) - taxo_c, 0)
    stren_missed = len(gt["strength"]) if "strength" in disabled else \
        max(len(gt["strength"]) - stren_c, 0)
    chain_missed = len(gt["chain"]) if "chain" in disabled else \
        max(len(gt["chain"]) - chain_c, 0)
    pend_missed = max(len(gt["pending"]) - pend_c, 0)

    unjudged = sum(1 for f in findings if f.get("judged") is not True)
    no_suggest = sum(1 for f in findings
                     if f.get("status") == "confirmed" and not str(f.get("revision_suggestion") or "").strip())
    manual_items = unjudged + no_suggest + loc_missed + taxo_missed + stren_missed + chain_missed + pend_missed

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
            "location_violations_objective": len(gt["location"]),
            "location_caught": loc_c,
            "location_missed": loc_missed,
            "taxonomy_violations_objective": len(gt["taxonomy"]),
            "taxonomy_caught": taxo_c,
            "taxonomy_missed": taxo_missed,
            "strength_violations_objective": len(gt["strength"]),
            "strength_caught": stren_c,
            "strength_missed": stren_missed,
            "chain_violations_objective": len(gt["chain"]),
            "chain_caught": chain_c,
            "chain_missed": chain_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_caught": pend_c,
            "pending_missed": pend_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "no_revision_suggestion": no_suggest,
                                        "location_missed": loc_missed,
                                        "taxonomy_missed": taxo_missed,
                                        "strength_missed": stren_missed,
                                        "chain_missed": chain_missed,
                                        "pending_missed": pend_missed},
            "steps_count": checks_executed + steps_done,
            "steps_detail": {"checks_executed": checks_executed,
                             "checks_disabled": len(report.get("disabled_checks") or []),
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
        },
    }


def inject_pollution(res):
    """在副本上注入领域化污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    for f in findings:
        if f.get("status") == "confirmed":
            f["quote"] = None
            f["location"] = None
            plan.append("%s 清空 quote/location（定位失据）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and f.get("issue_type") == "strength_mismatch":
            f["issue_type"] = "unknown_type"
            plan.append("%s issue_type 篡改为非法值 unknown_type（枚举违规，基础层始终开启负责抓取）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and f.get("category") == "suggestion":
            f["severity"] = "major"
            plan.append("%s suggestion 但 severity 抬升为 major（分级口径违规）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and f.get("category") == "fact_error":
            f["evidence"] = None
            plan.append("%s fact_error 但清空对照依据 evidence" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "pending":
            f["pending_reason"] = None
            plan.append("%s 标 pending 但清空 pending_reason" % f.get("finding_id"))
            break
    chains = [c for c in (inner.get("argument_chains") or []) if isinstance(c, dict)]
    for ch in chains:
        nodes = ch.get("nodes") or []
        keep = [n for n in nodes if str(n.get("role")) != "conclusion"]
        if len(keep) < len(nodes) and len(keep) >= 1:
            ch["nodes"] = keep
            plan.append("链 %s 删除 conclusion 节点（链完备违规）" % ch.get("chain_id"))
            break
    if inner.get("strength_matches"):
        inner["strength_matches"] = []
        plan.append("清空 strength_matches（强度匹配判定登记丢失）")
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：findings 为空）")
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
        ap.add_argument("--ledger", default="/app/work/rubrics.json")
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
    led = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(led, dict) else "not_found"
    case_obj = case if isinstance(case, dict) else {}

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case_obj),
                         ablate="none", case_state=case_state, ledger_state=ledger_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case_obj),
                           ablate="all", case_state=case_state, ledger_state=ledger_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, case_obj, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, case_obj, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("location_missed", "taxonomy_missed", "strength_missed",
                  "chain_missed", "pending_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "location_missed", "mechanism": "定位可回证（findings 与链节点的 quote 空白归一化后须"
         "逐字出现在稿件原文中 + location 非空）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后引文张冠李戴、位置缺失不再被判 FAIL，清单不可回原文核对"},
        {"metric": "taxonomy_missed", "mechanism": "分类口径一致（issue_taxonomy 六类判定前声明 + "
         "issue_type 枚举 + severity 分级映射 + issue_type×facet 交叉一致）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后问题类型可随意填、严重度可随意抬升，分类口径失效"},
        {"metric": "strength_missed", "mechanism": "强度匹配判定登记（strength_scale 双侧标尺判定前声明 + "
         "strength_mismatch 发现须登记 + C3 须 E3 映射规则 + 字段完备）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后结论超证据等级不登记，强度不匹配漏检"},
        {"metric": "chain_missed", "mechanism": "论证链节点完备（每条链 ≥2 节点，含 premise/hypothesis "
         "与 conclusion；chain_ref 指向存在节点）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后断链/缺结论的链不再判 FAIL，论证链追踪退化为叙述"},
        {"metric": "pending_missed", "mechanism": "待复核与误报抑制登记（pending⇒pending_review"
         " 含 reason+needed_action；suppressed⇒suppressed[] 且 rule_id 须在事前规则表内）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后待定条目可静默漏登记、误报抑制可绕过规则表，人工复核入口丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定 + 缺修改建议合计",
         "formula": "unjudged + no_revision_suggestion + 五类漏检", "higher_is_better": False,
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
        "退化模式关闭五组检查（location/taxonomy/strength/chain/pending），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，定位回证退化为不可判（src 为空）。",
        "三口径（severity/issue_taxonomy/strength_scale）未事前声明时对应真值不可得，"
        "漏检数记违规而非『无违规』。",
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
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case_obj),
                           ablate="none", case_state=case_state, ledger_state=ledger_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case_obj),
                        ablate="all", case_state=case_state, ledger_state=ledger_state)
        pm_n = mode_metrics(polluted, case_obj, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, case_obj, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "location_missed": pm_n["metrics"]["location_missed"],
                            "taxonomy_missed": pm_n["metrics"]["taxonomy_missed"],
                            "strength_missed": pm_n["metrics"]["strength_missed"],
                            "chain_missed": pm_n["metrics"]["chain_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "location_missed": pm_d["metrics"]["location_missed"],
                              "taxonomy_missed": pm_d["metrics"]["taxonomy_missed"],
                              "strength_missed": pm_d["metrics"]["strength_missed"],
                              "chain_missed": pm_d["metrics"]["chain_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "location_missed": pm_d["metrics"]["location_missed"]
                                   - pm_n["metrics"]["location_missed"],
                "taxonomy_missed": pm_d["metrics"]["taxonomy_missed"]
                                   - pm_n["metrics"]["taxonomy_missed"],
                "strength_missed": pm_d["metrics"]["strength_missed"]
                                   - pm_n["metrics"]["strength_missed"],
                "chain_missed": pm_d["metrics"]["chain_missed"]
                                - pm_n["metrics"]["chain_missed"],
                "pending_missed": pm_d["metrics"]["pending_missed"]
                                  - pm_n["metrics"]["pending_missed"],
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
        "findings_total": len([f for f in ((res.get("result") or {}).get("findings") or [])
                               if isinstance(f, dict)]),
        "chains_total": len([c for c in ((res.get("result") or {}).get("argument_chains") or [])
                             if isinstance(c, dict)]),
        "strength_matches_total": len([m for m in ((res.get("result") or {}).get("strength_matches") or [])
                                       if isinstance(m, dict)]),
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
