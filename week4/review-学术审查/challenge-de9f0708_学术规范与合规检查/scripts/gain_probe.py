#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（paper-compliance-audit 学术规范与合规检查）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭定位回证 / 三类与严重度口径 / 规则绑定与声明机检 / 证据链 / 待复核与抑制
登记五组检查），逐项对照可观测指标（全部实测，不臆造）：

  1. location_missed    定位失据漏检数（quote 不在原文/位置为空但未捕获）
  2. rubric_missed      三类区分口径违规漏检数
  3. rules_missed       依据绑定/声明机检漏检数（norm 发现无 rule_id、声明缺失无发现）
  4. evidence_missed    证据链缺失漏检数（confirmed 无 claims 回证）
  5. pending_missed     待复核/抑制漏登记数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（污染为领域化注入：清空引文定位/抬升三类口径违规 severity/清空规则绑定/清空
待复核登记/清空证据链；正常模式须抓到污染项，退出码恒 0）。

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
    from verify_check import analyze, manuscript_text, norm, category_mapping_bad  # noqa: E402
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
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    suppressed_reg = [s for s in (inner.get("suppressed") or []) if isinstance(s, dict)]
    rule_ids = {str(r.get("rule_id")) for r in (inner.get("format_rules") or [])
                if isinstance(r, dict)}
    fp_ids = {str(r.get("rule_id")) for r in (inner.get("suppression_rules") or [])
              if isinstance(r, dict)}
    decl_items = [d for d in ((inner.get("declaration_audit") or {}).get("items") or [])
                  if isinstance(d, dict)]
    src = manuscript_text(case)
    loc, rub, rul, evid, pend = [], [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for f in findings:
        fid = str(f.get("finding_id") or "")
        st = f.get("status")
        if st == "confirmed":
            q = norm(f.get("quote"))
            if not str(f.get("location") or "").strip() or not q or len(q) < 6 or (src and q not in src):
                loc.append(fid)
            if category_mapping_bad(f.get("category"), f.get("severity")):
                rub.append(fid)
            if f.get("category") in ("norm_missing", "norm_violation") \
                    and str(f.get("rule_id") or "") not in rule_ids:
                rul.append(fid)
            if f.get("category") == "substantive_issue" and not str(f.get("evidence") or "").strip():
                rul.append(fid)
            if fid not in claim_ids:
                evid.append(fid)
        if st == "pending":
            if not str(f.get("pending_reason") or "").strip():
                pend.append(fid)
            if not any(str(p.get("finding_id")) == fid for p in pending_reg):
                pend.append(fid)
        if st == "suppressed":
            rec = [s for s in suppressed_reg if str(s.get("finding_id")) == fid]
            if not rec or not all(str(s.get("rule_id")) in fp_ids for s in rec):
                pend.append(fid)
    rub_obj = inner.get("compliance_rubric") or {}
    cats = rub_obj.get("categories") or {}
    levels = rub_obj.get("severity_levels") or {}
    if not str(rub_obj.get("declared_at") or "").strip() \
       or not all(str(cats.get(k) or "").strip() for k in ("norm_missing", "norm_violation", "substantive_issue")) \
       or not all(str(levels.get(k) or "").strip() for k in ("critical", "major", "minor")):
        rub.append("compliance_rubric.declared_at")
    for d in decl_items:
        did = str(d.get("decl_id") or "")
        if d.get("detected") is False:
            covered = any(f.get("facet") == did and f.get("category") == "norm_missing" for f in findings) \
                or ("decl:%s" % did in {str(c.get("scope")) for c in (inner.get("clearances") or [])
                                        if isinstance(c, dict)}) \
                or any(did in str(g) for g in (inner.get("material_gaps") or []))
            if not covered:
                rul.append("decl:%s" % did)
    return {"location": loc, "rubric": rub, "rules": rul, "evidence": evid, "pending": pend}


def count_caught(res, report, idx):
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    loc = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].location_backed" % i))
    rub = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].category_mapping" % i))
    if caught(idx, "compliance_rubric.declared"):
        rub += 1
    rul = sum(1 for i in range(len(findings))
              if caught(idx, "findings[%d].rule_bound" % i)
              or caught(idx, "findings[%d].substantive_evidence" % i))
    if caught(idx, "declaration_audit.consistency"):
        rul += 1
    evid = sum(1 for i in range(len(findings)) if caught(idx, "findings[%d].claim_backed" % i))
    pend = sum(1 for i in range(len(findings))
               if caught(idx, "findings[%d].pending_registered" % i)
               or caught(idx, "findings[%d].suppression_registered" % i))
    return loc, rub, rul, evid, pend


def mode_metrics(res, case, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    gt = objective_violations(res, case)
    loc_c, rub_c, rul_c, evid_c, pend_c = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    loc_missed = max(len(gt["location"]) - loc_c, 0)
    rub_missed = max(len(gt["rubric"]) - rub_c, 0)
    rul_missed = max(len(gt["rules"]) - rul_c, 0)
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else \
        max(len(gt["evidence"]) - evid_c, 0)
    pend_missed = max(len(gt["pending"]) - pend_c, 0)

    unjudged = sum(1 for f in findings if f.get("judged") is not True)
    no_suggest = sum(1 for f in findings
                     if f.get("status") == "confirmed" and not str(f.get("revision_suggestion") or "").strip())
    manual_items = unjudged + no_suggest + loc_missed + rub_missed + rul_missed + evid_missed + pend_missed

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
            "rubric_violations_objective": len(gt["rubric"]),
            "rubric_caught": rub_c,
            "rubric_missed": rub_missed,
            "rules_violations_objective": len(gt["rules"]),
            "rules_caught": rul_c,
            "rules_missed": rul_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_caught": pend_c,
            "pending_missed": pend_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "no_revision_suggestion": no_suggest,
                                        "location_missed": loc_missed,
                                        "rubric_missed": rub_missed,
                                        "rules_missed": rul_missed,
                                        "evidence_missed": evid_missed,
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
        if f.get("category") == "norm_missing":
            f["severity"] = "critical"
            plan.append("%s（norm_missing）把 severity 抬升为 critical（三类口径违规）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("category") in ("norm_missing", "norm_violation"):
            f["rule_id"] = None
            plan.append("%s 清空 rule_id（依据绑定丢失）" % f.get("finding_id"))
            break
    for f in findings:
        if f.get("status") == "pending":
            f["pending_reason"] = None
            plan.append("%s 标 pending 但清空 pending_reason" % f.get("finding_id"))
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
        ap.add_argument("--ledger", default="/app/work/compliance_rubric.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except SystemExit as e:
        print("[gain_probe] 参数解析失败（argparse 退出码 %s，已降级为 exit 0）" % e)
        return 0
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

    delta_keys = ("location_missed", "rubric_missed", "rules_missed",
                  "evidence_missed", "pending_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "location_missed", "mechanism": "定位可回证（quote 空白归一化后须逐字出现在"
         "稿件原文中 + location 非空）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后引文张冠李戴、位置缺失不再被判 FAIL，清单不可回原文核对"},
        {"metric": "rubric_missed", "mechanism": "三类区分与严重度口径（substantive_issue⇒critical/"
         "major；norm_missing/norm_violation⇒major/minor，口径判定前声明）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后规范缺失可随意抬成 critical，三类区分口径失效"},
        {"metric": "rules_missed", "mechanism": "格式规则依据绑定 + 声明机检一致性（norm 发现须引用"
         "事前声明 format_rules 的 rule_id；机检 detected=false 的声明须有 norm_missing 发现或豁免）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后判『不合规』可不引依据条款，声明机检与审查结论脱钩"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（confirmed 须有 source_id"
         " 对应条目且 quote 逐字回证）", "formula": "无回证的 confirmed 发现数",
         "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，判断退化为自述"},
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
        "退化模式关闭五组检查（location/rubric/rules/evidence/pending），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "声明存在性机检基于关键词表，只能证明『稿件文本中未出现相关表述』，不能证明声明不在"
        "投稿系统或单独文件中——机检证据与语义判定分层，判定由 Agent 给出。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，定位回证退化为不可判（src 为空）。",
        "compliance_rubric 未事前声明时三类口径真值不可得，rubric_missed 记违规而非『无违规』。",
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
                            "rubric_missed": pm_n["metrics"]["rubric_missed"],
                            "rules_missed": pm_n["metrics"]["rules_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "location_missed": pm_d["metrics"]["location_missed"],
                              "rubric_missed": pm_d["metrics"]["rubric_missed"],
                              "rules_missed": pm_d["metrics"]["rules_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "location_missed": pm_d["metrics"]["location_missed"]
                                   - pm_n["metrics"]["location_missed"],
                "rubric_missed": pm_d["metrics"]["rubric_missed"]
                                 - pm_n["metrics"]["rubric_missed"],
                "rules_missed": pm_d["metrics"]["rules_missed"]
                                - pm_n["metrics"]["rules_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
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
