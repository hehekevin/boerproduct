#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（kbqa-cite 科研知识库问答）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭答案句-来源对齐 / 问题拆解覆盖 / 检索未命中登记 / claims 证据链回证四组
检查），逐项对照可观测指标（全部实测，不臆造）：

  1. alignment_missed   对齐违规漏检数（无来源句/条目不存在/引文未回证但未捕获）
  2. coverage_missed    覆盖违规漏检数（case 问题未拆解/子问题无答案/计数不符）
  3. miss_missed        未命中漏登记数（miss 无理由或未进 gaps 但未捕获）
  4. evidence_missed    claims 回证缺失漏检数
  5. manual_review_items 需人工核对子问题数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（注入无来源句/编造答案/清空 gaps/清空 claims；正常模式须抓到，退出码恒 0）。

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
    from verify_check import analyze, objective_violations, self_check_index, \
        caught, manifest_contents  # noqa: E402
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


def mode_metrics(res, report, label, contents, case=None):
    """按 self_check 三元组 + 客观真值统计一种模式的指标。"""
    idx = self_check_index(report)
    inner = (res or {}).get("result") or {}
    answers = [a for a in (inner.get("answers") or []) if isinstance(a, dict)]
    questions = [q for q in (inner.get("questions") or []) if isinstance(q, dict)]
    gt = objective_violations(res, case or {}, contents or {})
    disabled = set(report.get("disabled_checks") or [])

    align_caught = sum(1 for i in range(len(answers))
                       if caught(idx, "answers[%d].alignment" % i))
    evid_caught = sum(1 for i in range(len(answers))
                      if caught(idx, "answers[%d].claim_backed" % i))
    miss_caught = sum(1 for i in range(len(answers))
                      if caught(idx, "answers[%d].miss_registered" % i)
                      or caught(idx, "answers[%d].partial_declared" % i))
    cov_caught = sum(1 for q in range(len(questions))
                     if caught(idx, "questions[%d].decomposition" % q)) \
        + (1 if caught(idx, "coverage.consistency") else 0)

    align_missed = max(len(gt["alignment"]) - align_caught, 0)
    cov_missed = max(len(gt["coverage"]) - cov_caught, 0)
    miss_missed = max(len(gt["miss"]) - miss_caught, 0)
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else \
        max(len(gt["evidence"]) - evid_caught, 0)

    uncovered = sum(1 for q in questions
                    for sq in (q.get("subquestions") or [])
                    if str((sq or {}).get("sub_id")) not in
                    {str(a.get("sub_id")) for a in answers})
    manual_items = uncovered + align_missed + cov_missed + miss_missed + evid_missed

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
            "alignment_violations_objective": len(gt["alignment"]),
            "alignment_caught": align_caught,
            "alignment_missed": align_missed,
            "coverage_violations_objective": len(gt["coverage"]),
            "coverage_caught": cov_caught,
            "coverage_missed": cov_missed,
            "miss_violations_objective": len(gt["miss"]),
            "miss_caught": miss_caught,
            "miss_missed": miss_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "uncovered_subquestions": uncovered,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"uncovered": uncovered,
                                        "alignment_missed": align_missed,
                                        "coverage_missed": cov_missed,
                                        "miss_missed": miss_missed,
                                        "evidence_missed": evid_missed},
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
    answers = [a for a in (inner.get("answers") or []) if isinstance(a, dict)]
    for a in answers:
        sents = [s for s in (a.get("sentences") or []) if isinstance(s, dict)]
        if sents:
            sents[0]["source_entry"] = None
            sents[0]["quote"] = None
            sents[0]["text"] = "（编造：知识库未记载的结论，用于反例自测）"
            plan.append("%s 首句改为无来源句 + 编造文本" % a.get("sub_id"))
            break
    for a in answers:
        if a.get("status") == "miss":
            a["miss_reason"] = None
            plan.append("%s 标 miss 但清空 miss_reason" % a.get("sub_id"))
            break
    if inner.get("gaps"):
        inner["gaps"] = []
        plan.append("清空 gaps（缺口清单丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：answers 为空）")
    return p, plan


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
    contents = manifest_contents(args.work_dir)
    manifest_state = "enforced" if contents else "not_found"
    retrieval_state = "enforced" if os.path.exists(
        os.path.join(args.work_dir or ".", "retrieval.json")) else "not_found"

    def run(res_obj, ablate):
        return analyze(copy.deepcopy(res_obj), copy.deepcopy(case) if case else {},
                       ablate=ablate, case_state=case_state,
                       manifest_state=manifest_state, retrieval_state=retrieval_state,
                       contents=contents)

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = run(res, "none")
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = run(res, "all")
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal", contents, case)
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded", contents, case)
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("alignment_missed", "coverage_missed", "miss_missed",
                  "evidence_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "alignment_missed", "mechanism": "答案句-来源对齐检查（来源条目须存在、"
         "引文须逐字回证条目正文台账、无来源句识别）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后无来源句与编造引文不再判 FAIL，答案句与证据脱钩"},
        {"metric": "coverage_missed", "mechanism": "问题拆解覆盖检查（case 每问须拆解、"
         "每子问题须有答案、coverage 计数机械复算）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后漏拆解/漏答子问题不再可检出，多问回答可静默缺问"},
        {"metric": "miss_missed", "mechanism": "检索未命中登记检查（miss ⇒ miss_reason + "
         "gaps 含 missing_topic/needed_action；partial 须显式声明缺口）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后知识不足可被通顺回答掩盖，缺口清单丢失"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（答案句原文与引文须"
         "在对应 claim 中逐字出现；数字须回证条目正文）",
         "formula": "无回证的答案句数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，引用真实性退化为自述"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未覆盖子问题合计",
         "formula": "uncovered + 四类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工回原文核对的条目增加"},
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
        "退化模式关闭四组检查（alignment/coverage/miss/evidence），枚举、结构守卫、"
        "verdict 一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针经 objective_violations 独立复算（与 verify_check 的"
        "self_check 分开计数），口径一致时漏检数才可信。",
        "引文回证真值依赖 build_skeleton 产出的 entries.json 台账；台账缺失时回证降级为 "
        "claims 链内回证，alignment 真值口径相应放宽（闸门 entries_manifest 可见）。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "entries.json 台账缺失时引文回证无法对正文核验，alignment 真值只含结构性违规。",
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
                  "entries_manifest_state": manifest_state,
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
        p_normal = run(polluted, "none")
        p_deg = run(polluted, "all")
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal", contents, case)
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded", contents, case)
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "alignment_missed": pm_n["metrics"]["alignment_missed"],
                            "coverage_missed": pm_n["metrics"]["coverage_missed"],
                            "miss_missed": pm_n["metrics"]["miss_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "alignment_missed": pm_d["metrics"]["alignment_missed"],
                              "coverage_missed": pm_d["metrics"]["coverage_missed"],
                              "miss_missed": pm_d["metrics"]["miss_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "alignment_missed": pm_d["metrics"]["alignment_missed"]
                                    - pm_n["metrics"]["alignment_missed"],
                "coverage_missed": pm_d["metrics"]["coverage_missed"]
                                   - pm_n["metrics"]["coverage_missed"],
                "miss_missed": pm_d["metrics"]["miss_missed"]
                               - pm_n["metrics"]["miss_missed"],
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
        "entries_with_content": len(contents),
        "checker_runs": 2,
        "checker_checks_executed_normal": m_normal["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded": m_degraded["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_disabled_degraded": m_degraded["metrics"]["steps_detail"]["checks_disabled"],
        "subquestions_total": sum(len((q or {}).get("subquestions") or [])
                                  for q in ((res.get("result") or {}).get("questions") or [])
                                  if isinstance(q, dict)),
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
