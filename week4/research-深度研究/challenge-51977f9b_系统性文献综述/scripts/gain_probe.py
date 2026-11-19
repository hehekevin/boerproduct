#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（sysrev-review-synthesis）。

同一输入跑两遍：正常模式（七组机械校验全部开启）与退化模式（--ablate all，
关闭协议事前声明 / 筛选判定有据 / 漏斗闭合 / 提取项回证 / 质量评价一致 /
强度分级一致等全部分组检查），逐项对照可观测指标（全部实测，不臆造）：

  1. criteria_missed   纳排违规漏检数（判定无标准依据/理由码越界但未捕获）
  2. funnel_missed     计数失据漏检数（漏斗不闭合/存值与复算不符但未捕获）
  3. evidence_missed   理由/证据缺失漏检数（判定无 claims 逐字回证）
  4. pending_missed    待复核漏登记数
  5. extraction_missed 提取项漏检数（结构化缺块/证据无逐字回证）
  6. quality_missed    质量评价漏检数（缺评/维度非法/等级与推导不一致）
  7. synthesis_missed  强度分级漏检数（声明等级 != 机械推导级别）
  8. manual_review_items 需人工核对条目数；clarification_rounds 按每轮 3 条折算

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
    from verify_check import analyze, recompute_funnel, reason_codes  # noqa: E402
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


def objective_violations(res):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    conflicts = inner.get("conflicts") or []
    funnel = inner.get("funnel") or {}
    ex_codes, pd_codes = reason_codes()
    crit, fun, evid, pend = [], [], [], []
    ext_v, qua_v, syn_v = [], [], []

    import re as _re

    def norm(s):
        return _re.sub(r"\s+", "", str(s or ""))

    in_ids = {str(c.get("criterion_id")) for c in ((inner.get("criteria") or {}).get("inclusion") or []) if isinstance(c, dict)}
    ex_ids = {str(c.get("criterion_id")) for c in ((inner.get("criteria") or {}).get("exclusion") or []) if isinstance(c, dict)}
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)

    for r in records:
        rid = str(r.get("record_id") or "")
        if r.get("judged") is not True:
            continue
        dec, rc = r.get("decision"), r.get("reason_code")
        refs = {str(x) for x in (r.get("criteria_ref") or [])}
        if dec == "included":
            if not refs or not refs.issubset(in_ids):
                crit.append(rid)
        elif dec == "excluded":
            if rc not in ex_codes or (rc != "RC-EX-DUPLICATE" and (not refs or not refs.issubset(ex_ids))):
                crit.append(rid)
        elif dec == "pending_review":
            if rc not in pd_codes or not str(r.get("pending_reason") or "").strip():
                crit.append(rid)
        if dec in ("included", "excluded", "pending_review"):
            quote = norm(r.get("evidence_quote"))
            cl = claim_idx.get(rid) or []
            backed = any(quote and quote in norm(e.get("quote"))
                         for c in cl for e in (c.get("evidence") or [])) if quote else False
            # 与 verify_check 同口径：quote 为空（如 pending 无摘要）不算证据违规
            if quote and not backed:
                evid.append(rid)
        if dec == "pending_review" and not any(str(p.get("record_id")) == rid for p in pending_reg):
            pend.append(rid)
        if r.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and rid in [str(x) for x in (c.get("record_ids") or [])]]
            if not any(str(c.get("resolution")) in ("merged", "escalated") for c in rec):
                pend.append(rid)

    # --- 提取项客观真值（独立实现，不调用校验器）---
    ext = inner.get("extraction") or {}
    items = {str(it.get("record_id")): it for it in (ext.get("items") or []) if isinstance(it, dict)}
    included_ids = [str(r.get("record_id")) for r in records
                    if r.get("decision") == "included" and not r.get("duplicate_of")]
    for rid in included_ids:
        it = items.get(rid)
        if not isinstance(it, dict):
            ext_v.append(rid + ":缺提取项")
            continue
        for blk in ("study_design", "sample", "effect"):
            b = it.get(blk) if isinstance(it.get(blk), dict) else {}
            ev = b.get("evidence") if isinstance(b.get("evidence"), dict) else {}
            if not str(ev.get("quote") or "").strip() or not str(ev.get("location") or "").strip():
                ext_v.append("%s:%s无据" % (rid, blk))
    # --- 质量评价客观真值（独立实现）---
    qa = inner.get("quality_appraisal") or {}
    amap = {str(a.get("record_id")): a for a in (qa.get("assessments") or []) if isinstance(a, dict)}
    for rid in included_ids:
        a = amap.get(rid)
        if not isinstance(a, dict):
            qua_v.append(rid + ":缺评价")
            continue
        grades = {"yes": 1.0, "partly": 0.5, "no": 0.0, "unclear": 0.0}
        vals = [grades.get(str(d.get("judgment")), 0.0) for d in (a.get("dimensions") or [])
                if isinstance(d, dict)]
        mean = sum(vals) / len(vals) if vals else 0.0
        rec_g = "high" if mean >= 0.8 else ("moderate" if mean >= 0.5 else "low")
        if str(a.get("overall_grade")) != rec_g:
            qua_v.append("%s:等级不符(%s≠%s)" % (rid, a.get("overall_grade"), rec_g))
    # --- 强度分级客观真值（独立实现）---
    syn = inner.get("synthesis") or {}
    for c in (syn.get("conclusions") or []):
        if not isinstance(c, dict):
            continue
        n_s = len(c.get("supporting_records") or [])
        n_c = len(c.get("conflicting_records") or [])
        gs = [str((amap.get(str(x)) or {}).get("overall_grade") or "unknown")
              for x in (c.get("supporting_records") or [])]
        if n_s >= 3 and n_c == 0 and all(g in ("high", "moderate") for g in gs):
            rec_s = "strong"
        elif n_s >= 2 and n_c <= 1 and all(g in ("high", "moderate") for g in gs):
            rec_s = "moderate"
        elif n_s >= 1:
            rec_s = "weak"
        else:
            rec_s = "insufficient"
        if str(c.get("strength")) != rec_s:
            syn_v.append("%s:强度不符(%s≠%s)" % (c.get("conclusion_id"), c.get("strength"), rec_s))
    if not isinstance(syn.get("gaps"), list) or (not syn.get("gaps") and not str(syn.get("gaps_note") or "").strip()):
        syn_v.append("gaps 缺登记")
    if not isinstance(syn.get("bias_registry"), list) or (not syn.get("bias_registry") and not str(syn.get("bias_note") or "").strip()):
        syn_v.append("bias 缺登记")

    rec = recompute_funnel(records)
    if rec["identified"] != rec["duplicates_removed"] + rec["screened"]:
        fun.append("identified 链不闭合")
    if rec["screened"] != rec["included"] + rec["excluded"] + rec["pending_review"]:
        fun.append("screened 链不闭合")
    if sum(rec["excluded_by_reason"].values()) != rec["excluded"]:
        fun.append("excluded_by_reason 合计不符")
    for k in ("identified", "duplicates_removed", "screened", "excluded", "included", "pending_review"):
        stored = funnel.get(k)
        if isinstance(stored, int) and stored != rec[k]:
            fun.append("funnel.%s 存值不符" % k)

    esc_ids = set()
    for c in conflicts:
        if isinstance(c, dict) and str(c.get("resolution")) == "escalated":
            esc_ids.update(str(x) for x in (c.get("record_ids") or []))
    for rid in sorted(esc_ids):
        if not any(str(p.get("record_id")) == rid for p in pending_reg):
            pend.append(rid)
    return {"criteria": crit, "funnel": fun, "evidence": evid, "pending": pend,
            "extraction": ext_v, "quality": qua_v, "synthesis": syn_v}


def count_caught(idx, n_records):
    c = sum(1 for i in range(n_records)
            if caught(idx, "records[%d].criteria_consistency" % i))
    f = sum(1 for k in ("funnel.counts_recompute", "funnel.excluded_by_reason_sum",
                        "funnel.closure_closed") if caught(idx, k))
    e = sum(1 for i in range(n_records)
            if caught(idx, "records[%d].evidence_backed" % i)
            or caught(idx, "records[%d].evidence_present" % i))
    p = sum(1 for i in range(n_records)
            if caught(idx, "records[%d].pending_registered" % i)
            or caught(idx, "records[%d].duplicate_recorded" % i))
    if caught(idx, "conflicts.escalated_registered"):
        p += 1
    x = sum(1 for k, v in idx.items()
            if k.startswith("extraction[") and v.get("applied") and v.get("match") is False)
    q = sum(1 for k, v in idx.items()
            if k.startswith("quality[") and v.get("applied") and v.get("match") is False)
    y = sum(1 for k, v in idx.items()
            if (k.startswith("synthesis[") or k.startswith("synthesis."))
            and v.get("applied") and v.get("match") is False)
    return c, f, e, p, x, q, y


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    gt = objective_violations(res)
    con_caught, fun_caught, evid_caught, pend_caught, ext_caught, qua_caught, syn_caught = count_caught(idx, len(records))

    disabled = set(report.get("disabled_checks") or [])
    con_missed = max(len(gt["criteria"]) - con_caught, 0) if "screening" not in disabled else len(gt["criteria"])
    fun_missed = (len(gt["funnel"]) if "funnel" in disabled
                  else max(len(gt["funnel"]) - fun_caught, 0))
    evid_missed = len(gt["evidence"]) if "screening" in disabled else max(len(gt["evidence"]) - evid_caught, 0)
    pend_missed = (len(gt["pending"]) if "screening" in disabled
                   else max(len(gt["pending"]) - pend_caught, 0))
    ext_missed = (len(gt["extraction"]) if "extraction" in disabled
                  else max(len(gt["extraction"]) - ext_caught, 0))
    qua_missed = (len(gt["quality"]) if "quality" in disabled
                  else max(len(gt["quality"]) - qua_caught, 0))
    syn_missed = (len(gt["synthesis"]) if "synthesis" in disabled
                  else max(len(gt["synthesis"]) - syn_caught, 0))

    unjudged = sum(1 for r in records if r.get("judged") is not True)
    no_reason = sum(1 for r in records
                    if r.get("judged") is True and not str(r.get("rationale") or "").strip())
    manual_items = (unjudged + no_reason + con_missed + fun_missed + evid_missed
                    + pend_missed + ext_missed + qua_missed + syn_missed)

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
            "criteria_violations_objective": len(gt["criteria"]),
            "criteria_caught": con_caught,
            "criteria_missed": con_missed,
            "funnel_violations_objective": len(gt["funnel"]),
            "funnel_caught": fun_caught,
            "funnel_missed": fun_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_caught": evid_caught,
            "evidence_missed": evid_missed,
            "pending_violations_objective": len(gt["pending"]),
            "pending_missed": pend_missed,
            "extraction_violations_objective": len(gt["extraction"]),
            "extraction_caught": ext_caught,
            "extraction_missed": ext_missed,
            "quality_violations_objective": len(gt["quality"]),
            "quality_caught": qua_caught,
            "quality_missed": qua_missed,
            "synthesis_violations_objective": len(gt["synthesis"]),
            "synthesis_caught": syn_caught,
            "synthesis_missed": syn_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "no_rationale": no_reason,
                                        "criteria_missed": con_missed,
                                        "funnel_missed": fun_missed,
                                        "evidence_missed": evid_missed,
                                        "pending_missed": pend_missed,
                                        "extraction_missed": ext_missed,
                                        "quality_missed": qua_missed,
                                        "synthesis_missed": syn_missed},
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
    records = [r for r in (inner.get("records") or []) if isinstance(r, dict)]
    for r in records:
        if r.get("decision") == "included":
            r["criteria_ref"] = []
            r["evidence_quote"] = None
            plan.append("%s 判 included 但清空 criteria_ref/evidence_quote（纳排无依据）"
                        % r.get("record_id"))
            break
    for r in records:
        if r.get("decision") == "excluded" and not r.get("duplicate_of"):
            r["reason_code"] = None
            r["criteria_ref"] = []
            plan.append("%s 判 excluded 但清空 reason_code/criteria_ref（排除原因缺失）"
                        % r.get("record_id"))
            break
    funnel = inner.get("funnel")
    if isinstance(funnel, dict):
        for k in ("included", "excluded"):
            if isinstance(funnel.get(k), int):
                funnel[k] = funnel[k] + 1
                plan.append("funnel.%s 篡改 +1（流程计数不闭合）" % k)
                break
    for r in records:
        if r.get("decision") == "pending_review":
            r["pending_reason"] = None
            plan.append("%s 判 pending_review 但清空 pending_reason" % r.get("record_id"))
            break
    inner["pending_review"] = []
    plan.append("清空 pending_review（待复核登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    # 提取项无据
    ext = inner.get("extraction") or {}
    for it in (ext.get("items") or []):
        if isinstance(it, dict):
            for blk in ("study_design", "sample", "effect"):
                b = it.get(blk)
                if isinstance(b, dict) and isinstance(b.get("evidence"), dict):
                    b["evidence"]["quote"] = None
                    b["evidence"]["location"] = None
                    plan.append("%s 提取块 %s 清空 evidence（提取项无据）" % (it.get("record_id"), blk))
            break
    # 质量等级篡改
    qa2 = inner.get("quality_appraisal") or {}
    for a in (qa2.get("assessments") or []):
        if isinstance(a, dict) and a.get("overall_grade"):
            flip = {"high": "low", "moderate": "high", "low": "high"}.get(str(a.get("overall_grade")), "high")
            a["overall_grade"] = flip
            plan.append("%s overall_grade 篡改（质量评价与量表推导不一致）" % a.get("record_id"))
            break
    # 强度分级篡改
    syn = inner.get("synthesis") or {}
    for c in (syn.get("conclusions") or []):
        if isinstance(c, dict) and c.get("strength"):
            c["strength"] = "strong" if c.get("strength") != "strong" else "weak"
            plan.append("%s strength 篡改（结论强度分级不一致）" % c.get("conclusion_id"))
            break
    syn["gaps"] = []
    syn["gaps_note"] = None
    plan.append("清空 gaps/gaps_note（研究空白登记丢失）")
    # 协议事前声明缺失
    rr = inner.get("review_registration") or {}
    if isinstance(rr, dict):
        rr["registered_at"] = None
        plan.append("清空 review_registration.registered_at（协议事前声明缺失）")
    crit2 = inner.get("criteria") or {}
    if isinstance(crit2, dict):
        crit2["version"] = None
        plan.append("清空 criteria.version（协议版本声明缺失）")
    if not plan:
        plan.append("（无可注入位置：records 为空）")
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
        ap.add_argument("--ledger", default="/app/work/protocol_ledger.json")
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

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, ledger_state=ledger_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, ledger_state=ledger_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("criteria_missed", "funnel_missed", "evidence_missed",
                  "pending_missed", "extraction_missed", "quality_missed",
                  "synthesis_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "criteria_missed", "mechanism": "标准事前声明核对（decision ⇔ 理由码"
         "字典 + criteria_ref 引用存在的纳排标准 id；版本与台账一致防标准漂移）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后 included 无纳入依据、excluded 理由码越界不再判 FAIL，"
         "标准漂移与事后改标准不可检出"},
        {"metric": "funnel_missed", "mechanism": "漏斗五级计数机械复算 + excluded_by_reason"
         " 合计核对 + closure 闭合判据", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后计数篡改或漏斗不闭合不再可检出，1832→47 式断链无法防范"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（included/excluded/"
         "pending 的 evidence_quote 须在 claims 中逐字回证）",
         "formula": "无回证的已判定条目数", "higher_is_better": False,
         "degrade_effect": "关闭后理由退化为自述，『排除理由只写不相关』无法机械拦截"},
        {"metric": "pending_missed", "mechanism": "待复核登记检查（pending_review⇒登记含"
         " reason+needed_action；escalated 冲突须进入待复核）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后边界条目可静默漏登记，人工最终确认入口丢失"},
        {"metric": "extraction_missed", "mechanism": "提取项回证（结构化提取 study_design/"
         "sample/effect 逐块 evidence.quote 在来源语料或 claims 逐字回证）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后提取项可无据留空、指向非纳入研究也不可检出，"
         "效应量/样本/设计字段退化成无出处自述"},
        {"metric": "quality_missed", "mechanism": "质量评价一致性（纳入研究逐条评价 + "
         "维度判定合法 + overall_grade 等于量表机械推导）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后『质量较高』式一句评价不可检出，等级与维度判定脱钩"},
        {"metric": "synthesis_missed", "mechanism": "结论强度分级一致（declared strength "
         "等于按支持数/冲突数/支持质量机械推导级别；gaps/偏倚登记齐备）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后强度可口头指定、与证据基础脱钩，结论越界不可机械拦截"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定 + 无理由条目合计",
         "formula": "unjudged + no_rationale + 四类漏检", "higher_is_better": False,
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
        "退化模式关闭全部分组检查（protocol/screening/funnel/extraction/quality/"
        "synthesis），枚举、coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "协议台账缺失 → protocol_ledger 闸门记 not_found，事前声明不可独立证实（仍属"
        "『无法证实』而非『无违规』）。",
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
                           ablate="none", case_state=case_state, ledger_state=ledger_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, ledger_state=ledger_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "criteria_missed": pm_n["metrics"]["criteria_missed"],
                            "funnel_missed": pm_n["metrics"]["funnel_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "pending_missed": pm_n["metrics"]["pending_missed"],
                            "extraction_missed": pm_n["metrics"]["extraction_missed"],
                            "quality_missed": pm_n["metrics"]["quality_missed"],
                            "synthesis_missed": pm_n["metrics"]["synthesis_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "criteria_missed": pm_d["metrics"]["criteria_missed"],
                              "funnel_missed": pm_d["metrics"]["funnel_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "pending_missed": pm_d["metrics"]["pending_missed"],
                              "extraction_missed": pm_d["metrics"]["extraction_missed"],
                              "quality_missed": pm_d["metrics"]["quality_missed"],
                              "synthesis_missed": pm_d["metrics"]["synthesis_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "criteria_missed": pm_d["metrics"]["criteria_missed"]
                                   - pm_n["metrics"]["criteria_missed"],
                "funnel_missed": pm_d["metrics"]["funnel_missed"]
                                 - pm_n["metrics"]["funnel_missed"],
                "evidence_missed": pm_d["metrics"]["evidence_missed"]
                                   - pm_n["metrics"]["evidence_missed"],
                "pending_missed": pm_d["metrics"]["pending_missed"]
                                  - pm_n["metrics"]["pending_missed"],
                "extraction_missed": pm_d["metrics"]["extraction_missed"]
                                     - pm_n["metrics"]["extraction_missed"],
                "quality_missed": pm_d["metrics"]["quality_missed"]
                                  - pm_n["metrics"]["quality_missed"],
                "synthesis_missed": pm_d["metrics"]["synthesis_missed"]
                                    - pm_n["metrics"]["synthesis_missed"],
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
        "records_total": len([r for r in ((res.get("result") or {}).get("records") or [])
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
