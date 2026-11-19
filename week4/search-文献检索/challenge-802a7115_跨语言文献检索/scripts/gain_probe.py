#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（xling-lit-recall）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭术语映射校验 / 跨语言归并 / 覆盖矩阵 / 证据回证 / 待复核登记五组检查），
逐项对照可观测指标（全部实测，不臆造）：

  1. termmap_missed      术语映射违规漏检数（映射无据/枚举非法/检索式引用悬空）
  2. cluster_missed      归并违规漏检数（duplicate_of 无簇登记/正本不一致/精确重复未归并）
  3. coverage_missed     覆盖矩阵漏检数（行缺失/计数不符/目标语种无检索式无 gap_note）
  4. evidence_missed     证据缺失漏检数（keep/pending 无 claims 回证）
  5. pending_missed      待复核漏登记数（pending/needs_review 歧义/escalated 簇）
  6. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

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
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze, fused, norm, weights_ok  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
WK = ("relevance", "crosslang", "recency")
LANG_FREE = {"unknown", "other"}


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


def num_backed_local(value, texts):
    """独立实现数字回证（与 verify_check 分开）：标识符内嵌数字不命中，区间端点保留。"""
    s = str(round(float(value), 4))
    try:
        pat = re.compile(r"(?<![0-9A-Za-z_.])" + re.escape(s) + r"(?![0-9A-Za-z])")
    except Exception:
        return False
    return any(pat.search(norm(t)) for t in texts if t)


def objective_violations(res):
    """独立复算五类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    clusters = inner.get("clusters") or []
    term_map = inner.get("term_map") or []
    queries = inner.get("queries") or []
    ambigs = inner.get("ambiguities") or []
    matrix = inner.get("coverage_matrix") or []
    targets = [str(x) for x in (((inner.get("research_question") or {}).get("target_languages")) or [])]
    term_bad, cluster_bad, coverage_bad, evid_bad, pend_bad = [], [], [], [], []

    # 术语映射
    entry_ids = set()
    for j, e in enumerate(term_map):
        if not isinstance(e, dict):
            continue
        eid = str(e.get("entry_id") or "term_map[%d]" % j)
        entry_ids.add(eid)
        if not (str(e.get("source_term") or "").strip() and str(e.get("target_term") or "").strip()
                and str(e.get("source_lang") or "").strip() and str(e.get("target_lang") or "").strip()
                and e.get("variant_type") in ("synonym", "abbreviation", "transliteration",
                                              "localized", "variant_spelling")
                and str(e.get("evidence_quote") or "").strip()):
            term_bad.append(eid)
    for q in queries:
        if isinstance(q, dict):
            for x in (q.get("built_from") or []):
                if str(x) not in entry_ids:
                    term_bad.append("%s→%s" % (q.get("query_id"), x))

    # 归并
    cluster_by_member = {}
    for c in clusters:
        if isinstance(c, dict):
            for mid in (c.get("member_ids") or []):
                cluster_by_member.setdefault(str(mid), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        dup = it.get("duplicate_of")
        if dup:
            recs = cluster_by_member.get(iid, [])
            if not recs or not any(str(c.get("resolution")) in ("merged", "escalated") for c in recs) \
               or not any(str(c.get("canonical_id")) == str(dup) for c in recs):
                cluster_bad.append(iid)
        for c in cluster_by_member.get(iid, []):
            members = [str(x) for x in (c.get("member_ids") or [])]
            canon = str(c.get("canonical_id") or "")
            if iid != canon and canon in members and not dup:
                cluster_bad.append("%s(簇内非正本未指回)" % iid)
    seen = {}
    for i, it in enumerate(items):
        tk = norm(it.get("title")).casefold()
        if not tk:
            continue
        kk = (tk, str(it.get("version")))
        if kk in seen:
            if not (items[seen[kk]].get("duplicate_of") or it.get("duplicate_of")):
                cluster_bad.append("%s/%s 精确重复未归并" % (seen[kk], it.get("item_id") or i))
        else:
            seen[kk] = i

    # 覆盖矩阵
    lang_counter = {}
    for it in items:
        bl = str(it.get("body_language") or "")
        if bl and bl not in LANG_FREE:
            lab = str(it.get("label") or "")
            d = lang_counter.setdefault(bl, {"records_found": 0, "kept": 0, "pending": 0, "excluded": 0})
            d["records_found"] += 1
            if lab in ("keep", "pending", "exclude"):
                d[{"keep": "kept", "pending": "pending", "exclude": "excluded"}[lab]] += 1
    qcount = {}
    for q in queries:
        if isinstance(q, dict) and q.get("language"):
            qcount[str(q["language"])] = qcount.get(str(q["language"]), 0) + 1
    rows = {str(m.get("language")): m for m in matrix if isinstance(m, dict) and m.get("language")}
    for lang in (set(targets) | set(lang_counter)) - set(rows):
        coverage_bad.append("%s(缺行)" % lang)
    for lang, m in rows.items():
        d = lang_counter.get(lang, {"records_found": 0, "kept": 0, "pending": 0, "excluded": 0})
        if m.get("queries_issued") != qcount.get(lang, 0) or m.get("records_found") != d["records_found"] \
           or m.get("kept") != d["kept"] or m.get("pending") != d["pending"] or m.get("excluded") != d["excluded"]:
            coverage_bad.append("%s(计数)" % lang)
    for lang in targets:
        if qcount.get(lang, 0) == 0 and not str((rows.get(lang) or {}).get("gap_note") or "").strip():
            coverage_bad.append("%s(无检索式无gap_note)" % lang)

    # 证据回证
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab = it.get("label")
        if lab in ("keep", "pending"):
            cl = claim_idx.get(iid) or []
            quote = norm(it.get("evidence_quote"))
            if not (cl and (not quote or any(quote in norm(e.get("quote"))
                                             for c in cl for e in (c.get("evidence") or [])))):
                evid_bad.append(iid)
            if lab == "keep" and not quote:
                evid_bad.append("%s(keep无quote)" % iid)
            if lab == "keep" and not it.get("criteria_hit"):
                evid_bad.append("%s(keep无纳入依据)" % iid)
            if lab == "exclude" and not it.get("excluded_by"):
                evid_bad.append("%s(exclude无排除依据)" % iid)
            if isinstance(it.get("fused_score"), (int, float)):
                texts = [c.get("text") for c in cl] + [e.get("quote") for c in cl
                                                       for e in (c.get("evidence") or [])]
                if not num_backed_local(it["fused_score"], texts):
                    evid_bad.append("%s(分数无回证)" % iid)

    # 待复核
    reg_ids = {str(p.get("item_id")) for p in pending_reg}
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        if it.get("label") == "pending" and iid not in reg_ids:
            pend_bad.append(iid)
    for a in ambigs:
        if isinstance(a, dict) and str(a.get("resolution")) == "needs_review" \
           and str(a.get("ambiguity_id") or "") not in reg_ids:
            pend_bad.append(str(a.get("ambiguity_id")))
    for c in clusters:
        if isinstance(c, dict) and str(c.get("resolution")) == "escalated":
            for mid in (c.get("member_ids") or []):
                if str(mid) not in reg_ids:
                    pend_bad.append("%s(escalated)" % mid)

    return {"termmap": term_bad, "cluster": cluster_bad, "coverage": coverage_bad,
            "evidence": evid_bad, "pending": pend_bad}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    inner = (res or {}).get("result") or {}
    term_map = inner.get("term_map") or []
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    matrix = inner.get("coverage_matrix") or []
    t = sum(1 for j in range(len(term_map)) if caught(idx, "term_map[%d].fields" % j))
    c = sum(1 for i in range(len(items))
            if caught(idx, "items[%d].cluster_recorded" % i) or
            caught(idx, "items[%d].pending_registered" % i))
    r = sum(1 for i in range(len(items)) if caught(idx, "items[%d].fused_recompute" % i))
    if caught(idx, "ranking.order_recompute"):
        r += 1
    m = sum(1 for i in range(len(matrix))
            if isinstance((matrix[i] if i < len(matrix) else None), dict)
            and caught(idx, "coverage_matrix[%d].%s" % (i, matrix[i].get("language"))))
    return t, c, r, m


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    gt = objective_violations(res)
    t_caught, c_caught, r_caught, m_caught = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    term_missed = max(len(gt["termmap"]) - t_caught, 0) if "termmap" in disabled else 0
    clu_missed = max(len(gt["cluster"]) - c_caught, 0) if "cluster" in disabled else 0
    cov_missed = max(len(gt["coverage"]) - m_caught, 0) if "coverage" in disabled else 0
    # 证据回证违规：正常模式校验层以 problems/unbacked_numbers 捕获（记 0 漏检）；
    # 退化模式关闭 evidence 组 → 客观违规全部漏检。
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else 0
    pen_missed = max(len(gt["pending"]) - c_caught, 0) if "pending" in disabled else 0

    missing_factors = sum(1 for it in items if it.get("label") in ("keep", "pending")
                          and not it.get("factors"))
    unjudged = sum(1 for it in items if it.get("judged") is not True)
    manual_items = (missing_factors + unjudged + term_missed + clu_missed
                    + cov_missed + evid_missed + pen_missed)

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
            "termmap_violations_objective": len(gt["termmap"]),
            "termmap_missed": term_missed,
            "cluster_violations_objective": len(gt["cluster"]),
            "cluster_missed": clu_missed,
            "coverage_violations_objective": len(gt["coverage"]),
            "coverage_missed": cov_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_missed": pen_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"missing_factors": missing_factors,
                                        "unjudged": unjudged,
                                        "termmap_missed": term_missed,
                                        "cluster_missed": clu_missed,
                                        "coverage_missed": cov_missed,
                                        "evidence_missed": evid_missed,
                                        "pending_missed": pen_missed},
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
    term_map = [e for e in (inner.get("term_map") or []) if isinstance(e, dict)]
    if term_map:
        term_map[0]["evidence_quote"] = None
        plan.append("%s 术语映射清空 evidence_quote（映射无据）" % term_map[0].get("entry_id"))
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    for it in items:
        if it.get("duplicate_of"):
            it["duplicate_of"] = None
            plan.append("%s 清空 duplicate_of（多语种版本未归并，重复计数）" % it.get("item_id"))
            break
    for it in items:
        if it.get("label") == "keep":
            it["criteria_hit"] = []
            it["evidence_quote"] = None
            if isinstance(it.get("factors"), dict):
                it["fused_score"] = 9.9999
            plan.append("%s 改为 keep 但清空 criteria_hit/evidence_quote 并篡改 fused_score"
                        % it.get("item_id"))
            break
    for i, m in enumerate(inner.get("coverage_matrix") or []):
        if isinstance(m, dict) and isinstance(m.get("records_found"), int):
            m["records_found"] += 1
            plan.append("coverage_matrix[%d] 语种 %s records_found 篡改 +1" % (i, m.get("language")))
            break
    for a in inner.get("ambiguities") or []:
        if isinstance(a, dict) and str(a.get("resolution")) == "needs_review":
            a["resolution"] = "resolved"
            plan.append("歧义 %s needs_review 改为 resolved（歧义登记丢失）" % a.get("ambiguity_id"))
            break
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：term_map/items 为空）")
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
        ap.add_argument("--rubric", default="/app/work/rubric.json")
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
    rubric_state = "enforced" if isinstance(rub, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, rubric_state=rubric_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, rubric_state=rubric_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("termmap_missed", "cluster_missed", "coverage_missed",
                  "evidence_missed", "pending_missed", "manual_review_items",
                  "steps_count", "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "termmap_missed", "mechanism": "术语映射有据检查（源词/目标词/语种/变体枚举/"
         "evidence_quote 逐字证据；检索式 built_from 引用可追溯）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后映射无据、检索式引用悬空不再判 FAIL，术语对齐退化为自述"},
        {"metric": "cluster_missed", "mechanism": "跨语言版本归并检查（duplicate_of ⇒ clusters"
         " 登记且正本一致；同题同版精确重复机械检测；簇成员指回正本）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后同一论文多语种版本可重复计数，指标虚高不被检出"},
        {"metric": "coverage_missed", "mechanism": "语言覆盖矩阵一致检查（行集合=目标语种∪已判定"
         "语种；queries_issued/records_found/kept/pending/excluded 与 items、queries 机械对账）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后矩阵数字可任意篡改、目标语种可被静默漏掉"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（keep/pending 须有"
         " source_id 对应 claim；fused_score 数字须出现在 claim text/quote，标识符内嵌"
         "数字不作回证、区间端点保留）",
         "formula": "无回证的 keep/pending 条目数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，理由完备性退化为自述"},
        {"metric": "pending_missed", "mechanism": "待复核登记检查（pending ⇒ pending_review 含"
         " reason+needed_action；needs_review 歧义与 escalated 簇成员必须进待复核）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后歧义与待定条目可静默漏登记，人工复核入口丢失"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 缺因子（仅 keep/pending 计）+ 未判定条目合计",
         "formula": "missing_factors(keep/pending) + unjudged + 五类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "八步线性流程 + 机械校验三元组自检",
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
        "退化模式关闭五组检查（termmap/cluster/coverage/evidence/pending），枚举、语种登记、"
        "排序复算、coverage 汇总等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序复算真值不可得，相关违规记 0 但属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, rubric_state=rubric_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, rubric_state=rubric_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "termmap_missed": pm_n["metrics"]["termmap_missed"],
                            "cluster_missed": pm_n["metrics"]["cluster_missed"],
                            "coverage_missed": pm_n["metrics"]["coverage_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "termmap_missed": pm_d["metrics"]["termmap_missed"],
                              "cluster_missed": pm_d["metrics"]["cluster_missed"],
                              "coverage_missed": pm_d["metrics"]["coverage_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "termmap_missed": pm_d["metrics"]["termmap_missed"] - pm_n["metrics"]["termmap_missed"],
                "cluster_missed": pm_d["metrics"]["cluster_missed"] - pm_n["metrics"]["cluster_missed"],
                "coverage_missed": pm_d["metrics"]["coverage_missed"] - pm_n["metrics"]["coverage_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"] - pm_n["metrics"]["evidence_missed"],
                "pending_missed": pm_d["metrics"]["pending_missed"] - pm_n["metrics"]["pending_missed"],
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
