#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（read-note-harvest）。

同一输入跑两遍：正常模式（五组机械校验全部开启）与退化模式（--ablate all，
关闭位置回证 / 类型口径 / 卡片三要素 / 归纳依据 / 待查证登记五组检查），逐项
对照可观测指标（全部实测，不臆造）：

  1. location_missed   位置回证漏检数（锚点缺失/quote 无逐字回证但未捕获）
  2. type_missed       类型口径漂移漏检数（ann_type 越出口径但未捕获）
  3. card_missed       卡片三要素缺失漏检数
  4. theme_missed      归纳无依据漏检数
  5. toverify_missed   待查证漏登记数
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
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from verify_check import analyze, vocab_types  # noqa: E402
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
    """独立复算五类客观违规（与校验层分开实现，作为漏检真值）。"""
    inner = (res or {}).get("result") or {}
    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    cards = [c for c in (inner.get("cards") or []) if isinstance(c, dict)]
    themes = [t for t in (inner.get("themes") or []) if isinstance(t, dict)]
    to_verify = [p for p in (inner.get("to_verify") or []) if isinstance(p, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    conflicts = inner.get("conflicts") or []
    legal = vocab_types(inner.get("annotation_vocab") or {})

    loc, typ, card, theme, tov = [], [], [], [], []
    import re as _re

    def norm(s):
        return _re.sub(r"\s+", "", str(s or ""))

    claim_ids = {str(c.get("source_id") or "") for c in claims}
    claim_quotes = {str(c.get("source_id") or ""):
                    [norm(e.get("quote")) for e in (c.get("evidence") or [])]
                    for c in claims}
    ann_quotes = {str(a.get("ann_id") or i): norm(a.get("quote"))
                  for i, a in enumerate(anns)}
    tv_anns = set()
    for p in to_verify:
        for r in (p.get("related_anns") or []):
            tv_anns.add(str(r))
        if str(p.get("question") or "").strip() and str(p.get("needed_action") or "").strip():
            for r in (p.get("related_anns") or []):
                tv_anns.add(str(r))

    for i, a in enumerate(anns):
        aid = str(a.get("ann_id") or i)
        if a.get("judged") is not True:
            continue
        if not str(a.get("locator") or "").strip():
            loc.append(aid)
        q = ann_quotes.get(aid)
        backed = q and any(q in cq for cq in claim_quotes.get(aid, []))
        if not backed:
            loc.append(aid)
        if a.get("needs_verify") is True and aid not in tv_anns:
            tov.append(aid)
        if a.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and aid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            if not any(str(c.get("resolution")) in ("merged", "escalated") for c in rec):
                tov.append(aid)
        if legal is not None and a.get("ann_type") is not None and a.get("ann_type") not in legal:
            typ.append(aid)

    for i, c in enumerate(cards):
        cid = str(c.get("card_id") or i)
        if not str(c.get("point") or "").strip() or not c.get("evidence") \
                or not str(c.get("source") or "").strip():
            card.append(cid)
        for j, ev in enumerate(c.get("evidence") or []):
            if not isinstance(ev, dict):
                continue
            ref = str(ev.get("ann_id") or "")
            if ref not in ann_quotes:
                card.append("%s.ev%d" % (cid, j))
            else:
                q = norm(ev.get("quote"))
                if q and q not in ann_quotes[ref]:
                    card.append("%s.ev%d" % (cid, j))

    ann_ids = {str(a.get("ann_id") or i) for i, a in enumerate(anns)}
    for i, t in enumerate(themes):
        members = [str(x) for x in (t.get("member_anns") or [])]
        if len(members) < 2 or not str(t.get("basis") or "").strip() \
                or any(m not in ann_ids for m in members):
            theme.append(str(t.get("theme_id") or i))
    return {"location": loc, "type": typ, "card": card, "theme": theme, "toverify": tov}


def count_caught(res, report, idx):
    """按 self_check 三元组统计被校验层捕获的违规数。"""
    inner = (res or {}).get("result") or {}
    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    c = {}
    for i in range(len(anns)):
        for g, key in (("location", "annotations[%d].locator_present"),
                       ("location", "annotations[%d].quote_backed"),
                       ("type", "annotations[%d].type_in_vocab"),
                       ("toverify", "annotations[%d].toverify_registered"),
                       ("toverify", "annotations[%d].conflict_recorded")):
            if caught(idx, key % i):
                c[g] = c.get(g, 0) + 1
    for i in range(100):
        if caught(idx, "cards[%d].three_elements" % i):
            c["card"] = c.get("card", 0) + 1
        if caught(idx, "themes[%d].basis_grounded" % i):
            c["theme"] = c.get("theme", 0) + 1
    return c


def mode_metrics(res, report, label):
    idx = check_index(report)
    inner = (res or {}).get("result") or {}
    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    gt = objective_violations(res)
    caught_map = count_caught(res, report, idx)

    disabled = set(report.get("disabled_checks") or [])
    missed = {}
    for g in ("location", "type", "card", "theme", "toverify"):
        if g in disabled:
            missed[g] = len(gt[g])
        else:
            missed[g] = max(len(gt[g]) - caught_map.get(g, 0), 0)

    unjudged = sum(1 for a in anns if a.get("judged") is not True)
    manual_items = unjudged + sum(missed.values())
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
            "location_missed": missed["location"],
            "type_violations_objective": len(gt["type"]),
            "type_missed": missed["type"],
            "card_violations_objective": len(gt["card"]),
            "card_missed": missed["card"],
            "theme_violations_objective": len(gt["theme"]),
            "theme_missed": missed["theme"],
            "toverify_violations_objective": len(gt["toverify"]),
            "toverify_missed": missed["toverify"],
            "manual_review_items": manual_items,
            "manual_review_breakdown": {"unjudged": unjudged,
                                        "location_missed": missed["location"],
                                        "type_missed": missed["type"],
                                        "card_missed": missed["card"],
                                        "theme_missed": missed["theme"],
                                        "toverify_missed": missed["toverify"]},
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
    anns = [a for a in (inner.get("annotations") or []) if isinstance(a, dict)]
    for a in anns:
        if a.get("judged") is True:
            a["locator"] = None
            a["quote"] = None
            a["ann_type"] = "rumor-type"  # 未声明口径的越界类型
            a["needs_verify"] = True
            plan.append("%s 清空 locator/quote、注入越界类型 rumor-type 并置 needs_verify"
                        % a.get("ann_id"))
            break
    cards = [c for c in (inner.get("cards") or []) if isinstance(c, dict)]
    for c in cards:
        c["source"] = None
        for ev in (c.get("evidence") or []):
            if isinstance(ev, dict):
                ev["ann_id"] = "ghost-ann"
        plan.append("%s 清空 source 并把 evidence 指向不存在的批注 ghost-ann"
                    % c.get("card_id"))
        break
    themes = [t for t in (inner.get("themes") or []) if isinstance(t, dict)]
    if themes:
        themes[0]["member_anns"] = []
        themes[0]["basis"] = None
        plan.append("%s 清空 member_anns 与 basis（归纳无依据）" % themes[0].get("theme_id"))
    if inner.get("to_verify"):
        inner["to_verify"] = []
        plan.append("清空 to_verify（待查证登记丢失）")
    p["claims"] = []
    plan.append("清空 claims（证据链缺失）")
    if not plan:
        plan.append("（无可注入位置：annotations/cards 为空）")
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
        ap.add_argument("--vocab", default="/app/work/type_vocab.json")
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
    vb = load_json(args.vocab) if os.path.exists(args.vocab) else None
    vocab_state = "enforced" if isinstance(vb, dict) else "not_found"

    # --- 两遍真实运行：同一输入、同一份文件内容 ---
    t1 = time.time()
    rep_normal = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                         ablate="none", case_state=case_state, vocab_state=vocab_state)
    t_normal = time.time() - t1
    t2 = time.time()
    rep_degraded = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                           ablate="all", case_state=case_state, vocab_state=vocab_state)
    t_degraded = time.time() - t2

    m_normal = mode_metrics(res, rep_normal, "normal")
    m_normal["wall_clock_seconds"] = round(t_normal, 4)
    m_degraded = mode_metrics(res, rep_degraded, "degraded")
    m_degraded["wall_clock_seconds"] = round(t_degraded, 4)

    delta_keys = ("location_missed", "type_missed", "card_missed", "theme_missed",
                  "toverify_missed", "manual_review_items", "steps_count",
                  "clarification_rounds")
    delta = {}
    for k in delta_keys:
        a, b = m_normal["metrics"].get(k), m_degraded["metrics"].get(k)
        delta[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)

    mechanism_map = [
        {"metric": "location_missed", "mechanism": "批注位置回证检查（locator 非空 + quote 在 "
         "claims 证据链逐字回证）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后锚点错位、quote 无回证不再判 FAIL，批注退化为不可回溯的句子"},
        {"metric": "type_missed", "mechanism": "类型口径一致性检查（ann_type 必须命中事前"
         "声明的四类型口径）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后越界类型不再可检出，高亮/划线/页边批注被混成一类"},
        {"metric": "card_missed", "mechanism": "卡片三要素检查（point/evidence/source 一个不缺，"
         "卡片摘录逐字来自所引批注）", "formula": "客观违规数 − 被校验层捕获数",
         "higher_is_better": False,
         "degrade_effect": "关闭后笔记退化为无来源摘抄，写完即沉底"},
        {"metric": "theme_missed", "mechanism": "归纳依据检查（member_anns≥2 且全部存在 + "
         "basis 非空）", "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后关键词重合式过度连接不再可检出"},
        {"metric": "toverify_missed", "mechanism": "待查证登记检查（needs_verify ⇒ to_verify "
         "含 question+needed_action；duplicate_of ⇒ conflicts 处置）",
         "formula": "客观违规数 − 被校验层捕获数", "higher_is_better": False,
         "degrade_effect": "关闭后疑点可静默丢失，人工核查入口断链"},
        {"metric": "manual_review_items", "mechanism": "漏检 + 未判定批注合计",
         "formula": "unjudged + 五类漏检", "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count", "mechanism": "线性流程 + 机械校验三元组自检",
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
        "退化模式关闭五组检查（location/type/card/theme/toverify），枚举、结构守卫、"
        "coverage 汇总一致性等基础检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "五类违规的客观真值由探针独立复算（与 verify_check 分开实现），口径一致时漏检数才可信。",
        "wall_clock_seconds 为本机两次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，契约字段校验跳过。",
        "type_vocab 未事前声明时类型口径真值不可得，type_missed 记 0 但属『无法判定』而非『无违规』。",
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
                           ablate="none", case_state=case_state, vocab_state=vocab_state)
        p_deg = analyze(copy.deepcopy(polluted), copy.deepcopy(case) if case else {},
                        ablate="all", case_state=case_state, vocab_state=vocab_state)
        pm_n = mode_metrics(polluted, p_normal, "polluted_normal")
        pm_d = mode_metrics(polluted, p_deg, "polluted_degraded")
        gain_evidence["pollution_selftest"] = {
            "polluted_copy": os.path.abspath(p_path),
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "location_missed": pm_n["metrics"]["location_missed"],
                            "type_missed": pm_n["metrics"]["type_missed"],
                            "card_missed": pm_n["metrics"]["card_missed"],
                            "theme_missed": pm_n["metrics"]["theme_missed"],
                            "toverify_missed": pm_n["metrics"]["toverify_missed"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "location_missed": pm_d["metrics"]["location_missed"],
                              "type_missed": pm_d["metrics"]["type_missed"],
                              "card_missed": pm_d["metrics"]["card_missed"],
                              "theme_missed": pm_d["metrics"]["theme_missed"],
                              "toverify_missed": pm_d["metrics"]["toverify_missed"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "location_missed": pm_d["metrics"]["location_missed"]
                                   - pm_n["metrics"]["location_missed"],
                "type_missed": pm_d["metrics"]["type_missed"]
                               - pm_n["metrics"]["type_missed"],
                "card_missed": pm_d["metrics"]["card_missed"]
                               - pm_n["metrics"]["card_missed"],
                "theme_missed": pm_d["metrics"]["theme_missed"]
                                - pm_n["metrics"]["theme_missed"],
                "toverify_missed": pm_d["metrics"]["toverify_missed"]
                                   - pm_n["metrics"]["toverify_missed"],
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
        "annotations_total": len([a for a in ((res.get("result") or {}).get("annotations") or [])
                                  if isinstance(a, dict)]),
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
