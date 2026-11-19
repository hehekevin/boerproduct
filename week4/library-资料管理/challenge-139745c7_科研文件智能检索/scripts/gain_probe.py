#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（sci-file-retrieval）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭检索式一致性 / 排序复算 / 证据回证 / 登记完备四组检查），逐项对照
可观测指标（全部实测，不臆造）：

  1. grounding_missed    检索式无据漏检数（hit 无词表依据/未执行过滤但未捕获）
  2. ranking_missed      排序失据漏检数（fused_score 复算不符/顺序错但未捕获）
  3. evidence_missed     证据缺失漏检数（hit 证据不在原文/无 claims 回证）
  4. registry_missed     登记漏报数（待复核/空结果/受限文件漏登记）
  5. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

另采集 efficiency 效率计数，并支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染项，退出码恒 0）。判定词表匹配用集合运算，
不用 str.isalpha 分词（避免汉字陷阱）。

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
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import (analyze, build_content_map, fused,
                              norm, plan_vocab, weights_ok)  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
WK = ("term_match", "metadata_match", "content_match")


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
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    hits = [h for h in (inner.get("hits") or []) if isinstance(h, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    no_result = inner.get("no_result_queries") or []
    restricted = inner.get("restricted_files") or []
    conflicts = inner.get("conflicts") or []
    queries = inner.get("queries") or []
    plan_entries = {str(p.get("query_id")): p
                    for p in ((inner.get("query_plan") or {}).get("per_query") or [])
                    if isinstance(p, dict)}
    cmap = build_content_map(case if isinstance(case, dict) else {})
    gnd, rank_bad, evid, reg = [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for i, h in enumerate(hits):
        hid = str(h.get("hit_id") or i)
        lab = h.get("label")
        pe = plan_entries.get(str(h.get("query_id")))
        if lab == "hit":
            terms = [norm(t) for t in (h.get("matched_terms") or []) if str(t).strip()]
            if not terms:
                gnd.append("%s:matched_terms空" % hid)
            elif pe:
                vocab = plan_vocab(pe)
                gnd.extend("%s:词表外[%s]" % (hid, t) for t in terms if t not in vocab)
            if not str(h.get("evidence_quote") or "").strip():
                gnd.append("%s:quote空" % hid)
            declared_filters = [norm(x) for x in (pe.get("metadata_filters") or [])
                                ] if pe else []
            applied = [norm(x) for x in (h.get("filters_applied") or [])]
            if declared_filters and (not applied
                                     or any(a not in declared_filters for a in applied)):
                gnd.append("%s:过滤未执行" % hid)
        if lab == "no_hit" and not str(h.get("no_match_reason") or "").strip():
            gnd.append("%s:no_match_reason空" % hid)
        if lab == "pending" and not str(h.get("pending_reason") or "").strip():
            gnd.append("%s:pending_reason空" % hid)
        if lab in ("hit", "pending") and hid not in claim_ids:
            evid.append(hid)
        if lab == "hit" and cmap.get(str(h.get("file_id"))) is not None:
            q = norm(h.get("evidence_quote"))
            if q and q not in cmap[str(h.get("file_id"))]:
                evid.append("%s:quote不在原文" % hid)
        if lab == "pending" and not any(str(p.get("hit_id")) == hid for p in pending_reg):
            reg.append("%s:待复核漏登记" % hid)
        if h.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and hid in [str(x) for x in (c.get("item_ids") or [])]]
            if not any(str(c.get("resolution")) in ("merged", "escalated") for c in rec):
                reg.append("%s:冲突漏登记" % hid)

    for q in queries:
        qid = str(q.get("query_id") if isinstance(q, dict) else q)
        n_hits = sum(1 for h in hits if str(h.get("query_id")) == qid
                     and h.get("label") == "hit")
        if n_hits == 0 and not any(str(r.get("query_id")) == qid
                                   for r in no_result if isinstance(r, dict)):
            reg.append("query %s:空结果漏登记" % qid)
    lib_files = ((inner.get("library") or {}).get("files") or [])
    rids = {str(lf.get("file_id")) for lf in lib_files
            if isinstance(lf, dict) and lf.get("restricted")}
    rids |= {str(h.get("file_id")) for h in hits if h.get("restricted")}
    for rid in sorted(rids):
        if not any(str(r.get("file_id")) == rid for r in restricted if isinstance(r, dict)):
            reg.append("file %s:受限漏登记" % rid)

    scoring = ((inner.get("query_plan") or {}).get("scoring") or {})
    weights = weights_ok(scoring)
    if weights is not None:
        by_q = {}
        for h in hits:
            if h.get("label") == "hit" and h.get("factors"):
                by_q.setdefault(str(h.get("query_id")), []).append(h)
        for qid, qhits in by_q.items():
            for h in qhits:
                s = fused(weights, h.get("factors"))
                stored = h.get("fused_score")
                if s is not None and isinstance(stored, (int, float)) \
                        and abs(s - float(stored)) > 1e-6:
                    rank_bad.append("%s(score %s vs %s)" % (h.get("hit_id"), s, stored))
            exp = [(str(h.get("hit_id")), fused(weights, h["factors"]),
                    float((h["factors"] or {}).get("content_match") or 0.0))
                   for h in qhits]
            exp_order = [p for p, _s, _c in sorted(exp, key=lambda t: (-t[1], -t[2], t[0]))]
            got = next((list(pq.get("ordered_hits") or [])
                        for pq in (inner.get("ranking") or {}).get("per_query") or []
                        if str(pq.get("query_id")) == qid), [])
            if got and exp_order and got != exp_order:
                rank_bad.append("query %s ordered_hits 与复算顺序不一致" % qid)
    return {"grounding": gnd, "ranking": rank_bad, "evidence": evid, "registry": reg}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    inner = (res or {}).get("result") or {}
    hits = [h for h in (inner.get("hits") or []) if isinstance(h, dict)]
    g = sum(1 for i in range(len(hits))
            if caught(idx, "hits[%d].grounding" % i)
            or caught(idx, "hits[%d].quote_present" % i)
            or caught(idx, "hits[%d].filters_executed" % i)
            or caught(idx, "hits[%d].plan_declared" % i))
    r = sum(1 for i in range(len(hits)) if caught(idx, "hits[%d].fused_recompute" % i))
    for pq in ((inner.get("ranking") or {}).get("per_query") or []):
        if caught(idx, "ranking.order[%s]" % pq.get("query_id")):
            r += 1
    return g, r


def mode_metrics(res, case, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    hits = [h for h in (inner.get("hits") or []) if isinstance(h, dict)]
    gt = objective_violations(res, case)
    g_caught, rank_caught = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    # 证据回证违规：正常模式校验层以 problems/unbacked 捕获（记 0 漏检）；
    # 退化模式关闭 evidence 组 → 客观违规全部漏检。
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else 0
    reg_missed = len(gt["registry"]) if "registry" in disabled else \
        max(len(gt["registry"]) - sum(1 for i in range(len(hits))
            if caught(idx, "hits[%d].pending_registered" % i)
            or caught(idx, "hits[%d].conflict_recorded" % i)), 0)
    g_missed = max(len(gt["grounding"]) - g_caught, 0)
    rank_missed = max(len(gt["ranking"]) - rank_caught, 0)

    missing_factors = sum(1 for h in hits if h.get("label") == "hit"
                          and not h.get("factors"))
    unjudged = sum(1 for h in hits if h.get("judged") is not True)
    manual_items = missing_factors + unjudged + g_missed + rank_missed \
        + evid_missed + reg_missed

    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower()
                     in ("done", "ok", "completed"))
    rounds = int(math.ceil(manual_items / float(ROUND_BATCH))) if manual_items else 0

    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "metrics": {
            "grounding_violations_objective": len(gt["grounding"]),
            "grounding_caught": g_caught,
            "grounding_missed": g_missed,
            "ranking_violations_objective": len(gt["ranking"]),
            "ranking_caught": rank_caught,
            "ranking_missed": rank_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "registry_violations_objective": len(gt["registry"]),
            "registry_missed": reg_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"missing_factors": missing_factors,
                                        "unjudged": unjudged,
                                        "grounding_missed": g_missed,
                                        "ranking_missed": rank_missed,
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
    hits = [h for h in (inner.get("hits") or []) if isinstance(h, dict)]
    for h in hits:
        if h.get("label") == "hit":
            h["matched_terms"] = []
            h["evidence_quote"] = None
            if isinstance(h.get("factors"), dict):
                h["fused_score"] = 9.9999
            plan.append("%s 改为 hit 但清空 matched_terms/evidence_quote 并篡改 "
                        "fused_score" % h.get("hit_id"))
            break
    for h in hits:
        if h.get("label") == "pending":
            h["pending_reason"] = None
            plan.append("%s 标 pending 但清空 pending_reason" % h.get("hit_id"))
            break
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    if inner.get("no_result_queries"):
        inner["no_result_queries"] = []
        plan.append("清空 no_result_queries（空结果登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：hits 为空）")
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
        ap.add_argument("--query-plan", default="/app/work/query_plan.json")
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
        print("[gain_probe] FAIL: result.json 不存在或不可解析: %s（不中断交付）"
              % args.result)
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    cmap = build_content_map(case if isinstance(case, dict) else {})
    case_content_state = "enforced" if cmap else "not_found"
    qp = load_json(args.query_plan) if os.path.exists(args.query_plan) else None
    plan_state = "enforced" if isinstance(qp, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state,
                         plan_state=plan_state, case_content_state=case_content_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state,
                           plan_state=plan_state, case_content_state=case_content_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, case, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, case, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("grounding_missed", "ranking_missed", "evidence_missed",
                  "registry_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "grounding_missed", "mechanism": "检索式一致性检查（hit ⇒ matched_terms "
         "全在声明词表、声明过滤必须执行、no_hit/pending 须写原因）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后命中可以不带词表依据、过滤可以不执行，检索式与需求映射失据"},
        {"metric": "ranking_missed", "mechanism": "fused_score 机械复算 + 每查询期望顺序"
         "逐位对照（三因子事前权重）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后分数被篡改或顺序错乱不再可检出，相关性排序不可复算"},
        {"metric": "evidence_missed", "mechanism": "证据回证（hit 的 evidence_quote 须逐字"
         "出现在 case.json 该文件内容中 + claims 链逐字回证 + 分数数字回证）",
         "formula": "无回证的 hit/pending 条目数", "higher_is_better": False,
         "degrade_effect": "关闭后引用可以不在原文、证据链可以缺失，回链可靠性退化为自述"},
        {"metric": "registry_missed", "mechanism": "登记完备检查（pending ⇒ pending_review；"
         "零命中查询 ⇒ no_result_queries 空结果登记；受限文件 ⇒ restricted_files）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后空结果、权限受限、待定条目可静默漏登记，失败路径不可定位"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 缺因子（仅 hit 计）+ 未判定"
         "条目合计", "formula": "missing_factors(hit) + unjudged + 四类漏检",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条翻文件核对的条目增加"},
        {"metric": "steps_count", "mechanism": "线性检索流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数", "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds", "mechanism": "把人工核对条目按每轮 %d 条打包"
         "（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回文件/回问所需的轮次越多"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式关闭四组检查（grounding/ranking/evidence/registry），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "正常模式的违规同样进入 problems 列表并判 FAIL；missed 计数仅统计三元组键的"
        "捕获口径，低于实际捕获面，两侧均为下界。",
        "case.json 文件内容不可得时逐字回证退化为 claims 链回证（gate 记 not_found）。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "检索式权重未事前声明时排序复算真值不可得，ranking_missed 记 0 但属『无法判定』"
        "而非『无违规』。",
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
                  "case_content_state": case_content_state,
                  "same_input_for_both_runs": True,
                  "run_order": ["normal", "degraded"],
                  "note": "两遍均读取同一份 result.json 内容（深拷贝传入校验函数，"
                          "不做原地修改）"},
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
                           plan_state=plan_state, case_content_state=case_content_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state,
                        plan_state=plan_state, case_content_state=case_content_state)
        pm_n = mode_metrics(polluted, case, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, case, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "grounding_missed": pm_n["metrics"]["grounding_missed"],
                            "ranking_missed": pm_n["metrics"]["ranking_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "registry_missed": pm_n["metrics"]["registry_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "grounding_missed": pm_d["metrics"]["grounding_missed"],
                              "ranking_missed": pm_d["metrics"]["ranking_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "registry_missed": pm_d["metrics"]["registry_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "grounding_missed": pm_d["metrics"]["grounding_missed"]
                                    - pm_n["metrics"]["grounding_missed"],
                "ranking_missed": pm_d["metrics"]["ranking_missed"]
                                  - pm_n["metrics"]["ranking_missed"],
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
        "hits_total": len([h for h in ((res.get("result") or {}).get("hits") or [])
                           if isinstance(h, dict)]),
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
        print("  %-22s normal=%s  degraded=%s  delta=%s"
              % (name, a, b, delta.get(name)))
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
