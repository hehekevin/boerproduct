#!/usr/bin/env python3
"""gain_probe.py — Step 5 增益对照与效率计数（exp-result-explain）。

同一份输入跑两遍内部校验核（compact core）：正常模式（对齐一致性/配对/回证/
可执行复核四组全开）与退化模式（--ablate all 全关或按组关闭），把真实问题数
差写进 result.gain_evidence。--inject-pollution 在副本上注入 9 类污染反例
（异常删原因 / 解释删证据 / 对齐越级判 supported / 复核改空话 / 篡改数字 /
原因类别非法 / 清空 pending_review / 异常删对象绑定 / 编造引文），正常模式须
抓到；原 result.json 不被改动。同时写 result.efficiency（墙钟/字节/检查数/
reproduce）。全捕获容错，退出码恒为 0。

用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work [--ablate alignment,pairing,evidence,recheck|all] \
        [--emit-into] [--inject-pollution]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time

ALL_GROUPS = ["alignment", "pairing", "evidence", "recheck"]
JUDGMENTS = {"supported", "concerns", "inadequate", "unreported", "not_applicable", "unassessable"}
NUM_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w])")


def core_check(result, case, enabled):
    """紧凑校验核：返回 {group: [problems]}；enabled 为开启组集合。"""
    out = {g: [] for g in ALL_GROUPS}
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        out["enum"] = ["result 非对象"]
        return out
    rules = inner.get("judge_rules") or {}
    verdicts = set(rules.get("alignment_verdicts") or ["supported", "partially_supported", "not_supported", "unassessable"])
    anomaly_types = set(rules.get("anomaly_types") or ["outlier", "jump", "plateau"])
    cause_cats = set(rules.get("cause_categories") or ["instrument", "operation", "sample", "environment", "unknown"])
    vague = [str(w).lower() for w in (rules.get("vague_recheck_words") or ["检查数据质量", "check data quality"])]
    try:
        case_text = json.dumps(case, ensure_ascii=False)
    except Exception:
        case_text = ""
    pending_ids = {str(x.get("analysis_id")) for x in (inner.get("pending_review") or []) if isinstance(x, dict)}
    enum_p = out.setdefault("enum", [])
    for a in inner.get("analyses") or []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "?")
        align = a.get("alignment") or {}
        v = align.get("verdict")
        if v is not None and v not in verdicts:
            enum_p.append("%s alignment.verdict=%s 非法" % (aid, v))
        for x in a.get("anomalies") or []:
            if isinstance(x, dict) and x.get("anomaly_type") not in anomaly_types:
                enum_p.append("%s anomaly_type=%s 非法" % (aid, x.get("anomaly_type")))
        for x in a.get("causes") or []:
            if isinstance(x, dict) and x.get("category") not in cause_cats:
                enum_p.append("%s cause.category=%s 非法" % (aid, x.get("category")))
        neg = unass = False
        for x in a.get("appraisals") or []:
            if isinstance(x, dict):
                if x.get("judgment") not in JUDGMENTS:
                    enum_p.append("%s judgment=%s 非法" % (aid, x.get("judgment")))
                neg = neg or x.get("judgment") in {"inadequate", "unreported"}
                unass = unass or x.get("judgment") == "unassessable"
        if enabled.get("alignment"):
            g = out["alignment"]
            if not str(align.get("basis") or "").strip():
                g.append("%s verdict 缺 basis" % aid)
            if v == "supported" and (neg or unass):
                g.append("%s verdict=supported 但存在负面/弃权条目" % aid)
            if v == "unassessable" and aid not in pending_ids:
                g.append("%s verdict=unassessable 未登记 pending_review" % aid)
        anom_ids, has_quote_miss = set(), 0
        if enabled.get("pairing"):
            g = out["pairing"]
            for x in a.get("anomalies") or []:
                if isinstance(x, dict) and x.get("anomaly_id"):
                    anom_ids.add(str(x.get("anomaly_id")))
                    if not str(x.get("object_ref") or "").strip():
                        g.append("%s 异常 %s 缺对象绑定 object_ref" % (aid, x.get("anomaly_id")))
            bound = {}
            for c in a.get("causes") or []:
                if isinstance(c, dict) and c.get("anomaly_id"):
                    bound[str(c.get("anomaly_id"))] = bound.get(str(c.get("anomaly_id")), 0) + 1
            for i in anom_ids:
                if bound.get(i, 0) < 1:
                    g.append("%s 异常 %s 无绑定 cause" % (aid, i))
            for c in a.get("causes") or []:
                if isinstance(c, dict) and c.get("anomaly_id") and str(c.get("anomaly_id")) not in anom_ids:
                    g.append("%s cause %s 回指不存在的 anomaly" % (aid, c.get("cause_id")))
        if enabled.get("evidence"):
            g = out["evidence"]
            items = [("trend", a.get("trend") or {}), ("alignment", align)] + \
                    [("anomaly", x) for x in a.get("anomalies") or []] + \
                    [("cause", x) for x in a.get("causes") or []] + \
                    [("recheck", x) for x in a.get("rechecks") or []] + \
                    [("followup", x) for x in a.get("followups") or []]
            for kind, x in items:
                if not isinstance(x, dict):
                    continue
                q = str(x.get("evidence_quote") or "").strip()
                if not q:
                    g.append("%s %s 缺 evidence_quote" % (aid, kind))
                elif q not in case_text:
                    g.append("%s %s 引文无逐字回证" % (aid, kind))
                    has_quote_miss += 1
        if enabled.get("recheck"):
            g = out["recheck"]
            for r in a.get("rechecks") or []:
                if not isinstance(r, dict):
                    continue
                action = str(r.get("action") or "").strip()
                four = bool(action) and bool(str(r.get("target_file") or "").strip()) \
                    and (bool(str(r.get("target_field") or "").strip()) or bool(str(r.get("method") or "").strip())) \
                    and bool(str(r.get("expected_outcome") or "").strip())
                if r.get("executable") is True and (not four or any(w in action.lower() for w in vague)):
                    g.append("%s recheck %s 标可执行但四要素缺失或空话" % (aid, r.get("recheck_id")))
                if not four:
                    g.append("%s recheck %s 四要素不齐" % (aid, r.get("recheck_id")))
    if enabled.get("evidence"):
        rec_json = json.dumps(inner.get("trend_anomaly_check") or {}, ensure_ascii=False)
        rec_nums = [float(m) for m in re.findall(r"-?\d+\.\d+|-?\d+", rec_json)]
        for c in result.get("claims") or []:
            if isinstance(c, dict):
                for m in NUM_RE.finditer(str(c.get("text") or "")):
                    tok = m.group(1)
                    if tok in case_text:
                        continue
                    fval = float(tok)
                    backed = any(abs(fval - r) <= max(0.005 * abs(r), 0.005 * max(abs(fval), 1.0))
                                 for r in rec_nums)
                    if not backed:
                        out["evidence"].append("claim %s 数字 %s 未回证" % (c.get("claim_id"), tok))
    return out


def make_polluted(result):
    """构造 9 类污染副本（不改动原对象）。"""
    p = copy.deepcopy(result)
    inner = p.get("result") or {}
    analyses = inner.get("analyses") or []
    notes = []
    if analyses:
        a0 = analyses[0]
        # 1 异常删原因
        if a0.get("anomalies") and a0.get("causes"):
            tgt = a0["anomalies"][0].get("anomaly_id")
            a0["causes"] = [c for c in a0["causes"] if c.get("anomaly_id") != tgt]
            notes.append("anomaly_without_cause")
        # 2 解释删证据
        if a0.get("trend"):
            a0["trend"].pop("evidence_quote", None)
            notes.append("explanation_without_evidence")
        # 3 对齐越级
        a0["alignment"] = dict(a0.get("alignment") or {})
        a0["alignment"]["verdict"] = "supported"
        notes.append("alignment_overupgrade")
        # 4 复核改空话
        if a0.get("rechecks"):
            a0["rechecks"][0]["action"] = "检查数据质量"
            a0["rechecks"][0]["target_file"] = ""
            notes.append("recheck_vague_wording")
        # 8 异常删对象绑定
        if a0.get("anomalies"):
            a0["anomalies"][0].pop("object_ref", None)
            notes.append("anomaly_without_object_ref")
        # 9 编造引文
        if a0.get("anomalies"):
            a0["anomalies"][0]["evidence_quote"] = "本句为编造的引文，来源文本中不存在"
            notes.append("fabricated_quote")
    if len(analyses) > 1:
        a1 = analyses[1]
        # 6 原因类别非法
        if a1.get("causes"):
            a1["causes"][0]["category"] = "magic"
            notes.append("illegal_cause_category")
        # 3 对齐越级（第二组：负面/弃权条目存在时判 supported 即被抓）
        a1["alignment"] = dict(a1.get("alignment") or {})
        a1["alignment"]["verdict"] = "supported"
    # 7 清空 pending_review
    if inner.get("pending_review"):
        inner["pending_review"] = []
        notes.append("clear_pending_review")
    # 5 篡改数字
    claims = p.get("claims") or []
    if claims:
        claims[0]["text"] = str(claims[0].get("text") or "") + " 均值 999.99。"
        notes.append("fabricated_number_in_claim")
    return p, notes


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--ablate", default="all", help="关闭的组：alignment,pairing,evidence,recheck 或 all")
        ap.add_argument("--emit-into", action="store_true")
        ap.add_argument("--inject-pollution", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    problems = []
    t0 = time.perf_counter()

    result, case = {}, {}
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[gain_probe] FAIL: result.json 读取失败：%s（不中断交付）" % e)
        return 0
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
        else:
            problems.append("case.json 不存在: %s" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败: %s" % e)

    ablated = set(ALL_GROUPS) if args.ablate == "all" else \
        {g.strip() for g in args.ablate.split(",") if g.strip() in ALL_GROUPS}
    enabled_normal = {g: True for g in ALL_GROUPS}
    enabled_degraded = {g: g not in ablated for g in ALL_GROUPS}

    runs = []
    t1 = time.perf_counter()
    normal = core_check(result, case, enabled_normal)
    t2 = time.perf_counter()
    degraded = core_check(result, case, enabled_degraded)
    t3 = time.perf_counter()
    n_normal = sum(len(v) for v in normal.values())
    n_degraded = sum(len(v) for v in degraded.values())
    runs.append({"mode": "normal", "enabled_groups": [g for g, v in enabled_normal.items() if v],
                 "problems_found": n_normal, "by_group": {g: len(v) for g, v in normal.items() if len(v)},
                 "seconds": round(t2 - t1, 4)})
    runs.append({"mode": "degraded(--ablate %s)" % args.ablate,
                 "enabled_groups": [g for g, v in enabled_degraded.items() if v],
                 "problems_found": n_degraded, "by_group": {g: len(v) for g, v in degraded.items() if len(v)},
                 "seconds": round(t3 - t2, 4)})
    delta = {"total": n_normal - n_degraded}
    for g in ALL_GROUPS:
        delta[g] = len(normal.get(g) or []) - len(degraded.get(g) or [])

    # 污染反例注入副本（同输入双跑：污染副本也做正常 vs 退化两遍）
    pollution = {"available": False, "injected": [], "caught_by_normal_mode": None, "note": None}
    delta_polluted = None
    if args.inject_pollution:
        try:
            polluted, notes = make_polluted(result)
            t4 = time.perf_counter()
            pnorm = core_check(polluted, case, enabled_normal)
            t5 = time.perf_counter()
            pdeg = core_check(polluted, case, enabled_degraded)
            t6 = time.perf_counter()
            n_pnorm, n_pdeg = sum(len(v) for v in pnorm.values()), sum(len(v) for v in pdeg.values())
            runs.append({"mode": "normal@polluted-copy", "enabled_groups": [g for g, v in enabled_normal.items() if v],
                         "problems_found": n_pnorm, "by_group": {g: len(v) for g, v in pnorm.items() if len(v)},
                         "seconds": round(t5 - t4, 4)})
            runs.append({"mode": "degraded@polluted-copy", "enabled_groups": [g for g, v in enabled_degraded.items() if v],
                         "problems_found": n_pdeg, "by_group": {g: len(v) for g, v in pdeg.items() if len(v)},
                         "seconds": round(t6 - t5, 4)})
            delta_polluted = {"total": n_pnorm - n_pdeg}
            for g in ALL_GROUPS:
                delta_polluted[g] = len(pnorm.get(g) or []) - len(pdeg.get(g) or [])
            caught = {}
            pmap = {"anomaly_without_cause": "pairing", "explanation_without_evidence": "evidence",
                    "alignment_overupgrade": "alignment", "recheck_vague_wording": "recheck",
                    "fabricated_number_in_claim": "evidence", "illegal_cause_category": "enum",
                    "clear_pending_review": "alignment", "anomaly_without_object_ref": "pairing",
                    "fabricated_quote": "evidence"}
            for note in notes:
                grp = pmap.get(note)
                # 正常模式在污染副本上该组问题数 > 原结果该组问题数 ⇒ 抓到
                hit = bool(grp) and len(pnorm.get(grp) or []) > len(normal.get(grp) or [])
                caught[note] = bool(hit)
            pollution = {"available": True, "injected": notes, "caught_by_normal_mode": caught,
                         "caught_count": sum(1 for v in caught.values() if v),
                         "copy_path": None, "note": "污染只发生在内存副本，原 result.json 未被改动"}
            try:
                os.makedirs(args.work_dir or ".", exist_ok=True)
                ppath = os.path.join(args.work_dir, "polluted_result.json")
                with open(ppath, "w", encoding="utf-8") as f:
                    json.dump(polluted, f, ensure_ascii=False, indent=1)
                pollution["copy_path"] = ppath
            except Exception as e:
                pollution["note"] = "污染副本落盘失败（内存对照仍有效）: %s" % e
        except Exception as e:
            pollution = {"available": False, "injected": [], "caught_by_normal_mode": None,
                         "note": "注入异常: %s" % e}
            problems.append("污染注入异常: %s" % e)

    t_end = time.perf_counter()
    gain_evidence = {
        "available": True,
        "runs": runs,
        "delta_normal_minus_degraded": delta,
        "delta_polluted_copy": delta_polluted,
        "pollution_injection": pollution,
        "mechanism_to_metric_map": [
            {"mechanism": "对齐口径一致校验（supported 不得与负面/弃权条目并存）", "metric": "delta.alignment"},
            {"mechanism": "异常-原因配对校验（无 cause/孤儿 cause/缺对象绑定即报）", "metric": "delta.pairing"},
            {"mechanism": "解释回证校验（引文逐字+数字回证）", "metric": "delta.evidence"},
            {"mechanism": "复核可执行性校验（四要素+空话词表）", "metric": "delta.recheck"},
        ],
        "boundaries": ["本对照是本校验层正常 vs 退化两模式，不等于平台基础 Agent 对照；平台白板对照由平台生成"],
        "failure_conditions": ["case.json 缺失或不可解析时增益对照退化", "result.analyses 为空时两组问题数均为 0"],
    }
    try:
        bytes_size = os.path.getsize(args.result)
    except Exception:
        bytes_size = None
    efficiency = {
        "wall_clock_seconds_total": round(t_end - t0, 4),
        "checker_runs": len(runs),
        "checks_per_run": "enum+alignment+pairing+evidence+recheck 五组，按 analyses 逐组展开",
        "result_bytes": bytes_size,
        "model_requests": None,
        "reproduce": "python3 %s --result %s --case %s --work-dir %s --ablate %s --emit-into --inject-pollution"
                     % ("scripts/gain_probe.py", args.result, args.case, args.work_dir, args.ablate),
    }

    ok = False
    try:
        inner = result.get("result")
        if isinstance(inner, dict):
            inner["gain_evidence"] = gain_evidence   # 仅此两键归 gain_probe.py
            inner["efficiency"] = efficiency
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            ok = True
    except Exception as e:
        problems.append("回写失败: %s" % e)

    print("[gain_probe] case_id=%s | normal=%d 退化=%d delta=%s | 污染注入=%s 抓到=%s | marker_hit=%s"
          % (result.get("case_id"), n_normal, n_degraded, json.dumps(delta, ensure_ascii=False),
             pollution.get("available"), pollution.get("caught_count"), marker_hit))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[gain_probe] 回写%s" % ("成功" if ok else "失败"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
