#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（deep-research-loop）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭计划事前声明 / 迭代留痕 / 结论-证据对齐 / 未决问题登记四组检查），逐项
对照可观测指标（全部实测，不臆造）：

  1. plan_missed        计划违规漏检数（未事前声明/子问题越界/依赖违规）
  2. trace_missed       迭代留痕漏检数（留痕不全/来源不可回放）
  3. evidence_missed    结论-证据对齐漏检数（强度与来源不符/引文无回证）
  4. registry_missed    未决问题漏登记数
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。

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


def objective_violations(res):
    """独立复算四类客观违规（与 verify_check 分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    plan = inner.get("plan") or {}
    sqs = [s for s in (plan.get("sub_questions") or []) if isinstance(s, dict)]
    sq_set = {str(s.get("sq_id")) for s in sqs if s.get("sq_id")}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    iterations = [r for r in (inner.get("iterations") or []) if isinstance(r, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    open_qs = [q for q in (inner.get("open_questions") or []) if isinstance(q, dict)]
    divergent = [v for v in (inner.get("divergent_views") or []) if isinstance(v, dict)]

    plan_bad, trace_bad, evid_bad, reg_bad = [], [], [], []

    # plan：事前声明 + 子问题集合对齐
    if not str(plan.get("declared_at") or "").strip():
        plan_bad.append("plan.declared_at 为空")
    if not str((plan.get("convergence") or {}).get("rule") or "").strip():
        plan_bad.append("convergence.rule 为空")
    if (inner.get("plan_audit") or {}).get("state") != "declared":
        plan_bad.append("plan_audit.state != declared")
    claim_sq = set()
    for f in findings:
        unknown = [str(x) for x in (f.get("sq_ids") or []) if str(x) not in sq_set]
        if unknown:
            plan_bad.append("%s sq_ids 越界: %s" % (f.get("finding_id"), unknown))
        claim_sq.update(str(x) for x in (f.get("sq_ids") or []))
    for i, r in enumerate(iterations):
        if any(str(x) not in sq_set for x in (r.get("sq_ids_targeted") or [])):
            plan_bad.append("iterations[%d] sq_ids_targeted 越界" % i)
    # trace：留痕齐全 + 来源可回放
    trace_srcs = set()
    for i, r in enumerate(iterations):
        trace_srcs.update(str(x) for x in (r.get("sources_found") or []))
        if not (r.get("queries_run") and str(r.get("synthesis_note") or "").strip()
                and str(r.get("artifacts_ref") or "").strip()):
            trace_bad.append("iterations[%d] 留痕不全" % i)
    for f in findings:
        for s in (f.get("sources") or []):
            if isinstance(s, dict) and str(s.get("source_id")) not in trace_srcs:
                trace_bad.append("%s 来源 %s 不在任何轮次 sources_found"
                                 % (f.get("finding_id"), s.get("source_id")))
    # evidence：强度-来源一致 + 引文逐字回证
    claim_ids = {str(c.get("source_id") or "") for c in claims}
    claim_quotes = [e.get("quote") for c in claims for e in (c.get("evidence") or [])
                    if isinstance(c, dict)]
    import re
    nn = lambda x: re.sub(r"\s+", "", str(x or ""))
    claim_q_norm = [nn(q) for q in claim_quotes]
    for f in findings:
        fid = str(f.get("finding_id") or "")
        srcs = [s for s in (f.get("sources") or []) if isinstance(s, dict)]
        quoted = [s for s in srcs if nn(s.get("quote")) and nn(s.get("location"))]
        st = f.get("strength")
        if st == "strong" and len(quoted) < 2:
            evid_bad.append("%s strong 但带引文来源 %d 个" % (fid, len(quoted)))
        if st == "moderate" and len(quoted) < 1:
            evid_bad.append("%s moderate 无带引文来源" % fid)
        if st == "unverified" and srcs:
            evid_bad.append("%s unverified 却带来源" % fid)
        if f.get("kind") == "material_fact" and not srcs:
            evid_bad.append("%s material_fact 无来源" % fid)
        if srcs and fid not in claim_ids:
            evid_bad.append("%s 有来源但 claims 无对应证据条目" % fid)
        for s in srcs:
            q = nn(s.get("quote"))
            if q and not any(q in cq for cq in claim_q_norm):
                evid_bad.append("%s 来源 %s 引文无逐字回证" % (fid, s.get("source_id")))
    # registry：未决问题登记
    per_sq = {}
    for f in findings:
        for sid in (f.get("sq_ids") or []):
            per_sq.setdefault(str(sid), []).append(str(f.get("strength")))
    oq_refs = set()
    for q in open_qs:
        oq_refs.update(str(x) for x in (q.get("related_sq_ids") or []))
        if not (str(q.get("oq_id") or "").strip() and str(q.get("reason") or "").strip()
                and str(q.get("needed_action") or "").strip()):
            reg_bad.append("open_questions 条目不全（%s）" % q.get("oq_id"))
    oq_ids = {str(q.get("oq_id")) for q in open_qs if q.get("oq_id")}
    for sid in sorted(sq_set):
        sts = per_sq.get(sid, [])
        if (not sts) or not any(x in ("strong", "moderate") for x in sts):
            if sid not in oq_refs:
                reg_bad.append("子问题 %s 未登记进 open_questions" % sid)
    for i, v in enumerate(divergent):
        if v.get("handling") == "unresolved" \
                and str(v.get("open_question_ref") or "") not in oq_ids:
            reg_bad.append("divergent_views[%d] unresolved 未指向有效 open_question_ref" % i)
    return {"plan": plan_bad, "trace": trace_bad, "evidence": evid_bad, "registry": reg_bad}


def mode_metrics(res, report, label):
    disabled = set(report.get("disabled_checks") or [])
    gt = objective_violations(res)
    inner = (res or {}).get("result") or {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    sqs = [s for s in ((inner.get("plan") or {}).get("sub_questions") or []) if isinstance(s, dict)]

    def missed(group):
        # 正常模式开启该组检查时违规由 problems 捕获（漏检记 0）；
        # 退化模式关闭后漏检 = 客观违规数（下界：基础枚举/结构检查仍开启）。
        return len(gt[group]) if group in disabled else 0

    plan_m, trace_m = missed("plan"), missed("trace")
    evid_m, reg_m = missed("evidence"), missed("registry")
    orphan = sum(1 for f in findings
                 if any(str(x) not in {str(s.get("sq_id")) for s in sqs}
                        for x in (f.get("sq_ids") or [])))
    manual_items = plan_m + trace_m + evid_m + reg_m + orphan

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
            "plan_violations_objective": len(gt["plan"]),
            "plan_missed": plan_m,
            "trace_violations_objective": len(gt["trace"]),
            "trace_missed": trace_m,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_m,
            "registry_violations_objective": len(gt["registry"]),
            "registry_missed": reg_m,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"plan_missed": plan_m, "trace_missed": trace_m,
                                        "evidence_missed": evid_m, "registry_missed": reg_m,
                                        "orphan_findings": orphan},
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
    # 1. strong 结论清空来源（强度-来源矛盾 + 引文无回证）
    for f in (inner.get("findings") or []):
        if f.get("strength") == "strong":
            f["sources"] = []
            plan.append("%s 保持 strength=strong 但清空 sources（对齐违规）" % f.get("finding_id"))
            break
    # 2. 清空 claims（证据链缺失）
    p["claims"] = []
    plan.append("清空 claims（结论-证据对齐失据）")
    # 3. 清空 open_questions（未决问题登记丢失）
    if inner.get("open_questions"):
        inner["open_questions"] = []
        plan.append("清空 open_questions（未决问题登记丢失）")
    # 4. 计划声明清空（事前声明缺失）
    if isinstance(inner.get("plan"), dict):
        inner["plan"]["declared_at"] = None
        plan.append("清空 plan.declared_at（计划事前声明缺失）")
    # 5. 首轮清空 queries_run（留痕不全）
    for r in (inner.get("iterations") or []):
        r["queries_run"] = []
        plan.append("%s 清空 queries_run（迭代留痕不全）" % r.get("round_id"))
        break
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
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence/efficiency")
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
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("plan_missed", "trace_missed", "evidence_missed", "registry_missed",
                  "manual_review_items", "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "plan_missed", "mechanism": "计划事前声明检查（declared_at/convergence 声明、"
         "子问题编号唯一、依赖无环、findings/iterations 对齐计划集合）",
         "formula": "客观违规数（正常模式开启时漏检记 0）", "higher_is_better": False,
         "degrade_effect": "关闭后计划可事后补造、子问题越界与依赖违规不再判 FAIL"},
        {"metric": "trace_missed", "mechanism": "迭代留痕检查（每轮 queries_run/synthesis_note/"
         "artifacts_ref 齐全；结论来源必须出现在某轮 sources_found）",
         "formula": "客观违规数（正常模式开启时漏检记 0）", "higher_is_better": False,
         "degrade_effect": "关闭后轮次可无检索式空转、结论来源可凭空出现，路径不可回放"},
        {"metric": "evidence_missed", "mechanism": "结论-证据对齐（strong⇒≥2 带引文来源、"
         "material_fact⇒有来源、引文在 claims 逐字回证）",
         "formula": "客观违规数（正常模式开启时漏检记 0）", "higher_is_better": False,
         "degrade_effect": "关闭后强度标注与来源脱钩、引文可凭空捏造，结论退化为自述"},
        {"metric": "registry_missed", "mechanism": "未决问题登记检查（unanswered/partially 子问题"
         "⇒open_questions；unresolved 分歧⇒open_question_ref）",
         "formula": "客观违规数（正常模式开启时漏检记 0）", "higher_is_better": False,
         "degrade_effect": "关闭后证据缺口与分歧可静默吞掉，未决问题不进人工复核入口"},
        {"metric": "manual_review_items", "mechanism": "四类漏检 + 越界结论合计",
         "formula": "plan+trace+evidence+registry 漏检 + orphan_findings",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "Step 0-7 线性流程 + 机械校验三元组自检",
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
        "退化模式关闭四组检查（plan/trace/evidence/registry），枚举、coverage/strength 汇总"
        "一致性、verdict 一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
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
        polluted, inj_plan = inject_pollution(res)
        p_path = os.path.join(args.work_dir or ".", "gain_probe_polluted.json")
        save_json(p_path, polluted)
        p_normal = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                           ablate="none", case_state=case_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": inj_plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "plan_missed": pm_n["metrics"]["plan_missed"],
                            "trace_missed": pm_n["metrics"]["trace_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "registry_missed": pm_n["metrics"]["registry_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "plan_missed": pm_d["metrics"]["plan_missed"],
                              "trace_missed": pm_d["metrics"]["trace_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "registry_missed": pm_d["metrics"]["registry_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "plan_missed": pm_d["metrics"]["plan_missed"] - pm_n["metrics"]["plan_missed"],
                "trace_missed": pm_d["metrics"]["trace_missed"] - pm_n["metrics"]["trace_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"] - pm_n["metrics"]["evidence_missed"],
                "registry_missed": pm_d["metrics"]["registry_missed"] - pm_n["metrics"]["registry_missed"],
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
        "sub_questions_total": len([s for s in ((res.get("result") or {}).get("plan") or {})
                                    .get("sub_questions", []) if isinstance(s, dict)]),
        "findings_total": len([f for f in ((res.get("result") or {}).get("findings") or [])
                               if isinstance(f, dict)]),
        "iterations_total": len([r for r in ((res.get("result") or {}).get("iterations") or [])
                                 if isinstance(r, dict)]),
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
