#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（cite-fact-verify 引用与事实核验）。

同一输入跑两遍：正常模式（六组机械校验全部开启）与退化模式（--ablate all，
关闭引用逐字回证 / 严重度口径 / 证据链 / 待复核与抑制登记 / 引用规则 / 数值
回证六组检查），逐项对照可观测指标（全部实测，不臆造）：

  1. location_missed    引用定位失据漏检数（quote 不在原文/位置为空但未捕获）
  2. severity_missed    分级口径违规漏检数
  3. evidence_missed    证据链缺失漏检数（confirmed 无 claims 回证）
  4. pending_missed     待复核/抑制漏登记数
  5. citation_missed    引用规则违规漏检数（编造引用/不可判定冒充已核对/标记不回证）
  6. numeric_missed     数值回证违规漏检数（数值不在稿件原文）
  7. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（领域化污染注入：篡改 cite_marker 为参考文献表不存在的标记、篡改数值为原文
不存在的值、清空引文定位/清空对照依据/清空待复核/清空证据链；正常模式须抓到，
退出码恒 0）。

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
    from verify_check import analyze, manuscript_text, norm, manuscript_body_raw  # noqa: E402
    from citation_audit import extract_ref_keys, extract_text_markers, refs_list  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check/citation_audit: %s" % e)
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
    """独立复算六类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rule_ids = {str(r.get("rule_id")) for r in (inner.get("suppression_rules") or [])
                if isinstance(r, dict)}
    src = manuscript_text(case)
    loc, sev, evid, pend, cite, num = [], [], [], [], [], []

    # 引用真值独立复算（不依赖 result.citation_audit 是否回填）
    try:
        ind_markers = set(extract_text_markers(manuscript_body_raw(case)))
        ind_refs = set(extract_ref_keys(refs_list(case)))
        ind_fab = ind_markers - ind_refs
    except Exception:
        ind_markers, ind_refs, ind_fab = set(), set(), set()

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for f in findings:
        fid = str(f.get("finding_id") or "")
        st = f.get("status")
        if st == "confirmed":
            q = norm(f.get("quote"))
            if not str(f.get("location") or "").strip() or not q or len(q) < 6 or (src and q not in src):
                loc.append(fid)
            cat, sv = f.get("category"), f.get("severity")
            if (cat == "suggestion" and sv != "minor") or \
               (cat == "fact_error" and sv not in ("critical", "major")):
                sev.append(fid)
            if fid not in claim_ids:
                evid.append(fid)
        if st == "pending":
            if not str(f.get("pending_reason") or "").strip():
                pend.append(fid)
            if not any(str(p.get("finding_id")) == fid for p in pending_reg):
                pend.append(fid)
        if st == "suppressed":
            rec = [s for s in suppressed_reg if str(s.get("finding_id")) == fid]
            if not rec or not all(str(s.get("rule_id")) in rule_ids for s in rec):
                pend.append(fid)
        # 引用规则真值（与 verify_check 口径一致）
        cs = f.get("citation_state")
        m = str(f.get("cite_marker") or "").strip()
        if cs == "cannot_determine" and st != "pending":
            cite.append(fid)
        if m and st == "confirmed":
            if f.get("facet") == "citation_fabrication":
                if m not in ind_fab:
                    cite.append(fid)
            elif ind_refs and m not in ind_refs:
                cite.append(fid)
        # 数值回证真值
        for c in (f.get("numeric_claims") or []):
            if isinstance(c, dict):
                v = norm(str(c.get("value") or "") + str(c.get("unit") or ""))
                if v and (not src or v not in src):
                    num.append(fid)
                    break
    rub = inner.get("severity_rubric") or {}
    levels = rub.get("levels") or {}
    if not str(rub.get("declared_at") or "").strip() or \
       not all(str(levels.get(k) or "").strip() for k in ("critical", "major", "minor")):
        sev.append("severity_rubric.declared_at")
    return {"location": loc, "severity": sev, "evidence": evid, "pending": pend,
            "citation": cite, "numeric": num}


def count_caught(res, report, idx):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    loc = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].location_backed" % i))
    sev = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].severity_rule" % i))
    if caught(idx, "severity_rubric.declared"):
        sev += 1
    evid = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].claim_backed" % i))
    pend = sum(1 for i in range(len(findings))
               if caught(idx, "findings[%d].pending_registered" % i)
               or caught(idx, "findings[%d].suppression_registered" % i))
    cite = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].citation_rules" % i))
    num = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].numeric_backed" % i))
    return loc, sev, evid, pend, cite, num


def mode_metrics(res, case, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    gt = objective_violations(res, case)
    loc_c, sev_c, evid_c, pend_c, cite_c, num_c = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    loc_missed = max(len(gt["location"]) - loc_c, 0)
    sev_missed = max(len(gt["severity"]) - sev_c, 0)
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else \
        max(len(gt["evidence"]) - evid_c, 0)
    pend_missed = max(len(gt["pending"]) - pend_c, 0)
    cite_missed = max(len(gt["citation"]) - cite_c, 0)
    num_missed = max(len(gt["numeric"]) - num_c, 0)

    unjudged = sum(1 for f in findings if f.get("judged") is not True)
    no_suggest = sum(1 for f in findings
                     if f.get("status") == "confirmed" and not str(f.get("revision_suggestion") or "").strip())
    manual_items = unjudged + no_suggest + loc_missed + sev_missed + evid_missed + \
        pend_missed + cite_missed + num_missed

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
            "severity_violations_objective": len(gt["severity"]),
            "severity_caught": sev_c,
            "severity_missed": sev_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_caught": pend_c,
            "pending_missed": pend_missed,
            "citation_violations_objective": len(gt["citation"]),
            "citation_caught": cite_c,
            "citation_missed": cite_missed,
            "numeric_violations_objective": len(gt["numeric"]),
            "numeric_caught": num_c,
            "numeric_missed": num_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "no_revision_suggestion": no_suggest,
                                        "location_missed": loc_missed,
                                        "severity_missed": sev_missed,
                                        "evidence_missed": evid_missed,
                                        "pending_missed": pend_missed,
                                        "citation_missed": cite_missed,
                                        "numeric_missed": num_missed},
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
            plan.append("%s 清空 quote/location（引用定位失据）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and str(f.get("cite_marker") or "").strip():
            f["cite_marker"] = "[99]"
            plan.append("%s 篡改 cite_marker 为 [99]（参考文献表不存在的编造引用）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and f.get("numeric_claims"):
            f["numeric_claims"][0]["value"] = "999"
            plan.append("%s 篡改 numeric_claims 数值为原文不存在的 999（数值漂移）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "pending":
            f["pending_reason"] = None
            plan.append("%s 标 pending 但清空 pending_reason" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "confirmed" and f.get("category") == "fact_error":
            f["evidence"] = None
            plan.append("%s fact_error 但清空对照依据 evidence" % f.get("finding_id"))
            break
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
        ap.add_argument("--ledger", default="/app/work/severity_rubric.json")
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

    delta_keys = ("location_missed", "severity_missed", "evidence_missed",
                  "pending_missed", "citation_missed", "numeric_missed",
                  "manual_review_items", "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "location_missed", "mechanism": "引用逐字回证（quote 空白归一化后须逐字出现在"
         "稿件原文中 + location 非空）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后引文张冠李戴、位置缺失不再被判 FAIL，清单不可回原文核对"},
        {"metric": "severity_missed", "mechanism": "严重度分级口径（suggestion⇒minor、"
         "fact_error⇒critical/major，口径判定前声明）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后严重度可随意抬升/压低，分级口径失效"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（confirmed 须有 source_id"
         " 对应条目且 quote 逐字回证；fact_error 须给对照依据）",
         "formula": "无回证的 confirmed 发现数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，判断退化为自述"},
        {"metric": "pending_missed", "mechanism": "待复核与误报抑制登记（pending⇒pending_review"
         " 含 reason+needed_action；suppressed⇒suppressed[] 且 rule_id 须在事前规则表内）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后待定条目可静默漏登记、误报抑制可绕过规则表，人工复核入口丢失"},
        {"metric": "citation_missed", "mechanism": "引用规则（四态枚举/不可判定⇒pending 不冒充"
         "已核对/cite_marker 回证参考文献表与编造引用候选清单）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后编造引用可冒充已核对、读不到被引文献可凭空补结论"},
        {"metric": "numeric_missed", "mechanism": "数值回证（numeric_claims 逐字回证于稿件原文，"
         "配合 numeric_audit 的标签冲突与 p 值复算底账）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后数值可凭空冒充证据，数值漂移不再被判 FAIL"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定 + 缺修改建议合计",
         "formula": "unjudged + no_revision_suggestion + 六类漏检", "higher_is_better": False,
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
        "退化模式关闭六组检查（location/severity/evidence/pending/citation/numeric），"
        "枚举、结构守卫、coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "六类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，引用/数值回证退化为不可判（src 为空）。",
        "citation_audit / numeric_audit 未回填时闸门记 not_found，编造引用识别退化为独立复算。",
        "severity_rubric 未事前声明时分级口径真值不可得，severity_missed 记违规而非『无违规』。",
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
                            "severity_missed": pm_n["metrics"]["severity_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "citation_missed": pm_n["metrics"]["citation_missed"],
                            "numeric_missed": pm_n["metrics"]["numeric_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "location_missed": pm_d["metrics"]["location_missed"],
                              "severity_missed": pm_d["metrics"]["severity_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "citation_missed": pm_d["metrics"]["citation_missed"],
                              "numeric_missed": pm_d["metrics"]["numeric_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "location_missed": pm_d["metrics"]["location_missed"]
                                   - pm_n["metrics"]["location_missed"],
                "severity_missed": pm_d["metrics"]["severity_missed"]
                                   - pm_n["metrics"]["severity_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "pending_missed": pm_d["metrics"]["pending_missed"]
                                  - pm_n["metrics"]["pending_missed"],
                "citation_missed": pm_d["metrics"]["citation_missed"]
                                   - pm_n["metrics"]["citation_missed"],
                "numeric_missed": pm_d["metrics"]["numeric_missed"]
                                  - pm_n["metrics"]["numeric_missed"],
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
