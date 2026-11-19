#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（lit-quality-appraise）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭清单覆盖 / 分级一致 / 证据回证 / 缺陷区分 / 弃权登记五组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. coverage_missed  清单 domain 漏覆盖漏检数（客观违规但校验层未捕获）
  2. grading_missed   分级口径漂移/汇总失据漏检数
  3. evidence_missed  证据缺失/不可回证漏检数
  4. defect_missed    设计缺陷与报告不全混淆漏检数
  5. pending_missed   弃权漏登记数
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

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
    from verify_check import analyze, rollup, rules_ok  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3
TAGS = ("coverage", "grading", "evidence", "defect", "pending")


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


def objective_violations(res, case):
    """独立复算五类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    papers = [p for p in (inner.get("papers") or []) if isinstance(p, dict)]
    claims = [c for c in ((res or {}).get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
    rules = rules_ok(inner.get("grading_rules") or {})
    domains_req = set(str(d) for d in ((inner.get("checklist") or {}).get("domains") or []))
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    ntext = {pid: norm(" ".join([norm(c.get("text"))] +
                                [norm(e.get("quote")) for c in cl for e in (c.get("evidence") or [])]))
             for pid, cl in claim_idx.items()}

    out = {t: [] for t in TAGS}
    if not isinstance(inner, dict):
        out["coverage"].append("result 非对象")
        return out
    rules = rules_ok(inner.get("grading_rules") or {})
    for p in papers:
        pid = str(p.get("paper_id") or "")
        aps = [a for a in (p.get("appraisals") or []) if isinstance(a, dict)]
        doms = set()
        for a in aps:
            jd = a.get("judgment")
            doms.add(str(a.get("domain") or ""))
            if rules and rules["grade_map"].get(jd) != a.get("grade"):
                out["grading"].append("%s/%s grade 漂移" % (pid, a.get("checklist_id")))
            if rules and rules["category_map"].get(jd) != a.get("category"):
                out["defect"].append("%s/%s category 混淆" % (pid, a.get("checklist_id")))
            if jd in ("adequate", "concerns", "inadequate"):
                q = norm(a.get("evidence_quote"))
                if not q or (q not in ntext.get(pid, "") and q not in ntext.get("*", "")):
                    out["evidence"].append("%s/%s 证据缺失或无回证" % (pid, a.get("checklist_id")))
            if jd == "unassessable" and not any(
                    str(x.get("paper_id")) == pid and str(x.get("checklist_id")) == str(a.get("checklist_id"))
                    for x in pending_reg if isinstance(x, dict)):
                out["pending"].append("%s/%s 弃权未登记" % (pid, a.get("checklist_id")))
        miss = domains_req - doms
        if domains_req and miss:
            out["coverage"].append("%s 缺 domain: %s" % (pid, ",".join(sorted(miss))))
        if rules:
            r = rollup(p, rules)
            stored = next((s for s in ((inner.get("risk_summary") or {}).get("per_paper") or [])
                           if isinstance(s, dict) and str(s.get("paper_id")) == pid), None)
            if stored is None:
                out["grading"].append("%s risk_summary 缺失" % pid)
            elif r is not None and (stored.get("penalty_total") != r["penalty_total"]
                                    or stored.get("risk_of_bias") != r["risk_of_bias"]
                                    or stored.get("direction") != r["direction"]):
                out["grading"].append("%s 汇总复算不符" % pid)
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
    papers = [p for p in (inner.get("papers") or []) if isinstance(p, dict)]
    missed = {t: max(len(obj_truth[t]) - idx[t], 0) for t in TAGS}
    unjudged_items = sum(1 for p in papers for a in (p.get("appraisals") or [])
                         if not isinstance(a, dict) or a.get("judged") is not True)
    empty_papers = sum(1 for p in papers if not (p.get("appraisals") or []))
    manual_items = sum(missed.values()) + unjudged_items + empty_papers
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
            "grading_missed": missed["grading"],
            "evidence_missed": missed["evidence"],
            "defect_missed": missed["defect"],
            "pending_missed": missed["pending"],
            "violations_objective": {t: len(obj_truth[t]) for t in TAGS},
            "violations_caught": idx,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged_items": unjudged_items,
                                        "empty_papers": empty_papers,
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
    papers = [x for x in (inner.get("papers") or []) if isinstance(x, dict)]
    # 1) 混淆缺陷/报告不全 + 2) 分级漂移 + 3) 编造证据
    for paper in papers:
        for a in (paper.get("appraisals") or []):
            if a.get("judgment") == "unreported":
                a["category"] = "design_flaw"
                plan.append("%s/%s unreported 改归 design_flaw（缺陷混淆）"
                            % (paper.get("paper_id"), a.get("checklist_id")))
                break
        for a in (paper.get("appraisals") or []):
            if a.get("judgment") == "inadequate":
                a["grade"] = "high"
                plan.append("%s/%s inadequate 改 grade=high（分级漂移）"
                            % (paper.get("paper_id"), a.get("checklist_id")))
                break
        for a in (paper.get("appraisals") or []):
            if a.get("judgment") == "adequate":
                a["evidence_quote"] = "本句为污染注入的虚构引文，任何来源文本均不含此句"
                plan.append("%s/%s adequate 换为编造引文（证据失据）"
                            % (paper.get("paper_id"), a.get("checklist_id")))
                break
        if paper.get("appraisals"):
            paper["appraisals"] = paper["appraisals"][:-1]
            plan.append("%s 删除一条 appraisal（清单漏覆盖）" % paper.get("paper_id"))
        break
    # 4) 汇总失据
    pp = (inner.get("risk_summary") or {}).get("per_paper") or []
    if pp:
        pp[0]["risk_of_bias"] = "low"
        pp[0]["penalty_total"] = 0
        plan.append("risk_summary[%s] 篡改为 penalty=0/risk=low（汇总失据）" % pp[0].get("paper_id"))
    # 5) 弃权漏登记
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（弃权登记丢失）")
    # 6) 证据链缺失
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：papers 为空）")
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
        ap.add_argument("--rubric", default="/app/work/grading_rules.json")
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
    rub = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rules_state = "enforced" if isinstance(rub, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    obj_truth = objective_violations(res, case if isinstance(case, dict) else {})
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, rules_state=rules_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, rules_state=rules_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal", obj_truth)
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded", obj_truth)
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("coverage_missed", "grading_missed", "evidence_missed",
                  "defect_missed", "pending_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "coverage_missed", "mechanism": "清单 domain 覆盖检查（每篇 appraisals "
         "必须覆盖量表声明的全部维度）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后整维度漏评不再判 FAIL，评价表看似完整实则缺维度"},
        {"metric": "grading_missed", "mechanism": "分级口径一致（grade==grade_map[judgment]）"
         " + penalty/risk/direction 机械复算对照 risk_summary", "formula": "客观违规数 − 被捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后分级口径可漂移、汇总可被篡改，等级失去可解释性"},
        {"metric": "evidence_missed", "mechanism": "证据回证双闸（claims 链逐字回证 + "
         "case.json 来源文本存在性）", "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后转述/编造引文不再判 FAIL，评价退化为复述摘要"},
        {"metric": "defect_missed", "mechanism": "缺陷与报告不全区分（category==category_map"
         "[judgment]，inadequate⇒design_flaw、unreported⇒reporting_gap）",
         "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后两类混淆不再可检出，改进建议失去指向"},
        {"metric": "pending_missed", "mechanism": "弃权登记检查（unassessable⇒pending_review "
         "含 reason+needed_action）", "formula": "客观违规数 − 被捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后证据不足可被静默补判，弃权入口丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定条目 + 空评篇目合计",
         "formula": "五类漏检 + unjudged + empty_papers", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "七步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         % ROUND_BATCH, "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回原文/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭五组检查（coverage/grading/evidence/defect/pending），枚举、结构守卫、"
        "coverage 汇总等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，来源文本存在性检查跳过。",
        "grading_rules 未事前声明时汇总真值不可得，grading_missed 属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, rules_state=rules_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, rules_state=rules_state)
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
        "papers_total": len([p for p in ((res.get("result") or {}).get("papers") or [])
                             if isinstance(p, dict)]),
        "appraisals_total": sum(len((p.get("appraisals") or []) or 0) for p in
                                ((res.get("result") or {}).get("papers") or [])
                                if isinstance(p, dict)),
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
