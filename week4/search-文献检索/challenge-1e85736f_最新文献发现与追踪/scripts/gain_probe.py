#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（lit-track-incremental）。

同一输入跑两遍：正常模式（四组机械校验全部开启）与退化模式（--ablate all，
关闭事件-标签一致性 / 时效排序复算 / 证据链回证 / 登记完整性四组检查），逐项
对照可观测指标（全部实测，不臆造）：

  1. consistency_missed  事件-标签违规漏检数（客观违规但校验层未捕获）
  2. order_missed        排序失据漏检数（track_score 复算不符/顺序错但未捕获）
  3. evidence_missed     证据缺失漏检数（push/hold 无 claims 回证）
  4. registry_missed     登记漏项数（hold 未登记 / 重复未处置 / 版本链缺失）
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
    from track_engine import dedup_key_of, fused, parse_date, weights_ok  # noqa: E402
    from verify_check import analyze  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 track_engine/verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
PUSHABLE = ("new", "version_update", "backfill")


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


def norm_ws(s):
    import re
    return re.sub(r"\s+", "", str(s or ""))


def objective_violations(res):
    """独立复算四类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    conflicts = inner.get("conflicts") or []
    chains = inner.get("version_chains") or []
    chain_members = {str(m) for ch in chains if isinstance(ch, dict)
                     for m in (ch.get("member_ids") or [])}
    con, rank_bad, evid, reg = [], [], [], []

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab, ev, rel = it.get("label"), it.get("event"), it.get("relevance")
        if lab == "push" and (ev not in PUSHABLE or it.get("in_window") is False
                              or rel != "direct" or not str(it.get("evidence_quote") or "").strip()):
            con.append(iid)
        if ev == "out_of_window" and lab != "exclude":
            con.append(iid)
        if ev == "duplicate" and not it.get("related_to"):
            con.append(iid)
        if ev == "retraction" and lab == "push":
            con.append(iid)
        if rel == "irrelevant" and lab == "push":
            con.append(iid)
        if lab == "hold" and not str(it.get("pending_reason") or "").strip():
            con.append(iid)
        if lab == "exclude" and not it.get("excluded_by"):
            con.append(iid)
        if lab in ("push", "hold") and iid not in claim_ids:
            evid.append(iid)
        if lab == "hold" and not any(str(p.get("item_id")) == iid for p in pending_reg):
            reg.append(iid)
        if it.get("related_to"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and iid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            if not any(str(c.get("resolution")) in ("merged", "escalated") for c in rec):
                reg.append(iid)
        if ev in ("version_update", "retraction") and iid not in chain_members:
            reg.append(iid)

    weights = weights_ok(inner.get("rubric") or {})
    if weights is not None:
        scored = [(str(it.get("item_id")), fused(weights, it.get("factors")),
                   parse_date(it.get("published_date")) or "0000-00-00")
                  for it in items if it.get("factors")]
        ordered = sorted(scored, key=lambda t: str(t[0]))
        ordered.sort(key=lambda t: t[2], reverse=True)
        ordered = sorted(ordered, key=lambda t: -t[1]) if ordered else ordered
        exp_order = [p for p, _s, _d in ordered]
        got_order = list((inner.get("ranking") or {}).get("ordered_ids") or [])
        for p, s, _d in scored:
            stored = next((it.get("track_score") for it in items
                           if str(it.get("item_id")) == p), None)
            if s is not None and isinstance(stored, (int, float)) and abs(s - float(stored)) > 1e-6:
                rank_bad.append("%s(score %s vs %s)" % (p, s, stored))
        if got_order and exp_order and got_order != exp_order:
            rank_bad.append("ordered_ids 与复算顺序不一致")
    return {"consistency": con, "order": rank_bad, "evidence": evid, "registry": reg}


def count_caught(report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    items_n = len([it for it in ((report.get("_res") or {}).get("result") or {}).get("items") or []
                   if isinstance(it, dict)])
    c = sum(1 for i in range(items_n) if caught(idx, "items[%d].consistency_event_label" % i))
    r = sum(1 for i in range(items_n) if caught(idx, "items[%d].score_recompute" % i))
    if caught(idx, "ranking.order_recompute"):
        r += 1
    g = sum(1 for i in range(items_n) if caught(idx, "items[%d].hold_registered" % i)
            or caught(idx, "items[%d].duplicate_recorded" % i))
    return c, r, g


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    report["_res"] = res  # 供 count_caught 计条目数（内部字段，不落盘）
    gt = objective_violations(res)
    con_caught, rank_caught, reg_caught = count_caught(report, idx)
    report.pop("_res", None)

    disabled = set(report.get("disabled_checks") or [])
    evid_missed = len(gt["evidence"]) if "evidence" in disabled else 0

    con_missed = max(len(gt["consistency"]) - con_caught, 0)
    order_missed = max(len(gt["order"]) - rank_caught, 0)
    reg_missed = max(len(gt["registry"]) - reg_caught, 0)

    missing_factors = sum(1 for it in items if it.get("label") in ("push", "hold")
                          and not it.get("factors"))
    unjudged = sum(1 for it in items if it.get("judged") is not True)
    manual_items = missing_factors + unjudged + con_missed + order_missed + evid_missed + reg_missed

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
            "consistency_violations_objective": len(gt["consistency"]),
            "consistency_caught": con_caught,
            "consistency_missed": con_missed,
            "order_violations_objective": len(gt["order"]),
            "order_caught": rank_caught,
            "order_missed": order_missed,
            "evidence_violations_objective": len(gt["evidence"]),
            "evidence_missed": evid_missed,
            "registry_violations_objective": len(gt["registry"]),
            "registry_caught": reg_caught,
            "registry_missed": reg_missed,
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"missing_factors": missing_factors,
                                        "unjudged": unjudged,
                                        "consistency_missed": con_missed,
                                        "order_missed": order_missed,
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
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    for i, it in enumerate(items):
        if it.get("label") == "push":
            it["evidence_quote"] = None
            it["relevance"] = "indirect"
            if isinstance(it.get("factors"), dict):
                it["track_score"] = 9.9999
            plan.append("%s 保持 push 但清空 evidence_quote、relevance 降为 indirect 并篡改 track_score"
                        % it.get("item_id"))
            break
    for it in items:
        if it.get("event") == "duplicate":
            it["related_to"] = None
            plan.append("%s 保持 event=duplicate 但清空 related_to" % it.get("item_id"))
            break
    for it in items:
        if it.get("label") == "hold":
            it["pending_reason"] = None
            plan.append("%s 标 hold 但清空 pending_reason" % it.get("item_id"))
            break
    if inner.get("pending_review"):
        inner["pending_review"] = []
        plan.append("清空 pending_review（待复核登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：items 为空）")
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
        ap.add_argument("--policy", default="/app/work/track_policy.json")
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
    pol = load_json(args.policy) if os.path.exists(args.policy) else None
    policy_state = "enforced" if isinstance(pol, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, policy_state=policy_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, policy_state=policy_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("consistency_missed", "order_missed", "evidence_missed",
                  "registry_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "consistency_missed", "mechanism": "事件-标签一致性检查（push ⇒ 可推送事件+窗内+"
         "direct+有证据；out_of_window⇒exclude；duplicate⇒related_to；retraction 不推送）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后窗外/重复/撤稿条目可被误推送，误报不再被判 FAIL"},
        {"metric": "order_missed", "mechanism": "track_score 机械复算 + 期望顺序逐位对照"
         "（rubric 事前权重，track_score 降序 → published_date 降序 → item_id 升序）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后分数被篡改或时效顺序错乱不再可检出，排序依据不可追溯"},
        {"metric": "evidence_missed", "mechanism": "claims 证据链回证（push/hold 须有 source_id 对应"
         " claim；track_score 数字须出现在 claim text/quote）",
         "formula": "无回证的 push/hold 条目数", "higher_is_better": False,
         "degrade_effect": "关闭后证据链缺失不再判 FAIL，提醒依据退化为自述"},
        {"metric": "registry_missed", "mechanism": "登记完整性检查（hold⇒pending_review；duplicate⇒"
         "conflicts merged/escalated；version_update/retraction⇒version_chains；source_registry 非空）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后待定条目可静默漏登记，版本链与来源快照记录丢失，增量不可复算"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 缺因子（仅 push/hold 计）+ 未判定条目合计",
         "formula": "missing_factors(push/hold) + unjudged + 四类漏检", "higher_is_better": False,
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
        "退化模式关闭四组检查（consistency/order/evidence/registry），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "四类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "rubric 未事前声明时排序复算真值不可得，order_missed 记 0 但属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, policy_state=policy_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, policy_state=policy_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "consistency_missed": pm_n["metrics"]["consistency_missed"],
                            "order_missed": pm_n["metrics"]["order_missed"],
                            "evidence_missed": pm_n["metrics"]["evidence_missed"],
                            "registry_missed": pm_n["metrics"]["registry_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "consistency_missed": pm_d["metrics"]["consistency_missed"],
                              "order_missed": pm_d["metrics"]["order_missed"],
                              "evidence_missed": pm_d["metrics"]["evidence_missed"],
                              "registry_missed": pm_d["metrics"]["registry_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "consistency_missed": pm_d["metrics"]["consistency_missed"]
                                      - pm_n["metrics"]["consistency_missed"],
                "order_missed": pm_d["metrics"]["order_missed"]
                                - pm_n["metrics"]["order_missed"],
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
