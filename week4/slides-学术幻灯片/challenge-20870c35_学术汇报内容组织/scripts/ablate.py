#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ablate.py — 增益层：同输入消融两臂 + 污染反例灵敏度检验（全部机器判定）。

三臂同输入、同一校验器（verify_gate.evaluate）各跑一遍：
  A skill     —— 本次完整计划（证据映射+问答准备+页级主张）。
  B ablated   —— 模拟基础 Agent「逐段搬运」：删证据映射、删问答预判、删页级主张。
  P polluted  —— A 的副本注入一条捏造主张+捏造数字+捏造引文（污染反例）；
                校验器必须报 FAIL，否则判定校验器灵敏度不足。
FAIL 数差与逐项指标差是机器判定，写入 result.json 的 gain_evidence 与
efficiency（仅本脚本写这两个键，避免与其他脚本冲突）。退出码恒 0。
"""
import argparse, copy, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_gate  # 同一校验器，保证双臂判定一致


def strip_arm(plan):
    """B 臂：模拟基础 Agent 的搬运式产出（无证据映射/无问答准备/无页级主张）。"""
    b = copy.deepcopy(plan)
    for s in b.get("slides", []):
        if not isinstance(s, dict):
            continue
        s["evidence"] = []
        s["claim"] = None
        n = str(s.get("notes") or "")
        s["notes"] = re.sub(r"Q:.*?(?=Q:|$)", "", n, flags=re.S).strip() or \
            "本页对应论文对应章节内容。"  # 基础路径备注常与页面重复
    b.setdefault("meta", {})["arm"] = "ablated_baseline_copy_paragraphs"
    return b


def pollute(plan):
    """P 臂：注入捏造反例（不在源文本中的数字与引文），检验校验器灵敏度。"""
    p = copy.deepcopy(plan)
    target = None
    for s in p.get("slides", []):
        if isinstance(s, dict) and str(s.get("role") or "") == "result":
            target = s
            break
    if target is None:
        for s in p.get("slides", []):
            if isinstance(s, dict):
                target = s
                break
    if target is None:
        p["slides"] = [{"no": 1, "role": "result", "title": "注入反例",
                        "claim": "准确率提升37.2%", "bullets": ["准确率提升37.2%"],
                        "evidence": [{"type": "section", "locator": "§4",
                                      "quote": "准确率提升了37.2个百分点，显著优于全部基线"}],
                        "notes": "注入的污染反例，用于检验校验器灵敏度。" * 3}]
    else:
        target["claim"] = "准确率提升37.2%"
        target.setdefault("bullets", []).append("准确率提升37.2%（超出源材料记录）")
        target.setdefault("evidence", []).append(
            {"type": "quote", "locator": "§4",
             "quote": "准确率提升了37.2个百分点，显著优于全部基线"})
    p.setdefault("meta", {})["arm"] = "polluted_counterexample_copy"
    p["meta"]["pollution_injected"] = True
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="/app/work/deck.json")
    ap.add_argument("--source", default="/app/work/source_text.txt")
    ap.add_argument("--constraints", default="/app/work/constraints.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default="/app/work/ablation_report.json")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    rep = {"ok": False, "note": ""}
    try:
        plan = json.load(open(args.plan, encoding="utf-8"))
        src = ""
        if os.path.exists(args.source):
            src = open(args.source, encoding="utf-8", errors="ignore").read()
        cons = None
        if os.path.exists(args.constraints):
            try:
                cons = json.load(open(args.constraints, encoding="utf-8"))
            except Exception:
                cons = None
        if not src:
            rep["note"] = "源文本为空：quote 闸门四态为 skipped_not_provided，增益差不可机器判定，如实登记"
        arm_a = copy.deepcopy(plan)
        arm_a.setdefault("meta", {})["arm"] = "skill_full"
        arm_b = strip_arm(plan)
        arm_p = pollute(plan)
        r_a = verify_gate.evaluate(arm_a, src, cons)
        r_b = verify_gate.evaluate(arm_b, src, cons)
        r_p = verify_gate.evaluate(arm_p, src, cons)
        m_a, m_b = r_a.get("metrics") or {}, r_b.get("metrics") or {}
        diff = {}
        for k in ("quote_verifiable_rate", "numeric_backed_rate",
                  "evidence_coverage_rate", "notes_qa_rate", "claim_single_rate",
                  "narrative_ok", "fails_total"):
            va, vb = m_a.get(k), m_b.get(k)
            diff[k] = (round(va - vb, 3) if isinstance(va, (int, float))
                       and isinstance(vb, (int, float)) else None)
        # ---- 机制→指标映射（含边界与失效条件） ----
        mapping = [
            {"mechanism": "证据映射+quote逐字回证闸门",
             "metric": "quote_verifiable_rate",
             "skill": m_a.get("quote_verifiable_rate"), "ablated": m_b.get("quote_verifiable_rate"),
             "boundary": "仅在源文本可提取（文本型PDF/文本文件）时可判；扫描件未OCR则回退为locator-only、该指标不计入增益",
             "failure_condition": "源文本为空或PDF文本层损坏→闸门 skipped_not_provided，增益差不可机器判定"},
            {"mechanism": "数字回证闸门（页级数字须在该页quote中）",
             "metric": "numeric_backed_rate",
             "skill": m_a.get("numeric_backed_rate"), "ablated": m_b.get("numeric_backed_rate"),
             "boundary": "只对出现在 claim/bullets 的数字生效；纯图内数字须走 figure+quote 另证",
             "failure_condition": "页面无数字→指标为 None，不构成增益证据"},
            {"mechanism": "问答准备（notes 强制含 Q: 预判追问）",
             "metric": "notes_qa_rate",
             "skill": m_a.get("notes_qa_rate"), "ablated": m_b.get("notes_qa_rate"),
             "boundary": "机械检查只验存在性与长度，问题质量需评审人工判读",
             "failure_condition": "听众约束缺失时预判问题由模型自拟，可能偏题"},
            {"mechanism": "页级唯一主张（每内容页恰一 claim ≤40字）",
             "metric": "claim_single_rate",
             "skill": m_a.get("claim_single_rate"), "ablated": m_b.get("claim_single_rate"),
             "boundary": "只验唯一性与长度，主张是否成立由 quote/numeric 闸门联动",
             "failure_condition": "整册无内容页→None"},
            {"mechanism": "叙事顺序闸门（title开头/结论收尾/结论不先于结果）",
             "metric": "narrative_ok",
             "skill": m_a.get("narrative_ok"), "ablated": m_b.get("narrative_ok"),
             "boundary": "只约束骨架顺序与取舍登记，不评判起承转合的文学质量",
             "failure_condition": "空 slides→fatal fail"},
        ]
        sens = (r_p.get("metrics") or {}).get("fails_total", 0)
        base_fail = (r_p.get("gates") or {}).get("quote_gate", {}).get("fail", 0) + \
                    (r_p.get("gates") or {}).get("numeric_gate", {}).get("fail", 0)
        skill_fail = m_a.get("fails_total", 0)
        rep = {
            "ok": True,
            "arms": {
                "skill_full": {"verdict": r_a.get("verdict"), "metrics": m_a},
                "ablated_baseline": {"verdict": r_b.get("verdict"), "metrics": m_b},
                "polluted_counterexample": {"verdict": r_p.get("verdict"),
                                            "fails_total": sens,
                                            "quote_numeric_fail": base_fail},
            },
            "diff_skill_minus_ablated": diff,
            "validator_sensitivity": {
                "polluted_fails": sens, "skill_fails": skill_fail,
                "machine_verdict": bool(base_fail >= 1),
                "note": "污染反例被 quote/numeric 闸门捕获=校验器具备灵敏度；未捕获则如实记 false"},
            "mechanism_metric_map": mapping,
            "boundaries": [
                "消融对照基于同一计划的结构化改写，代表『有/无证据映射机制』的机制差，非基础Agent的端到端复跑",
                "三臂均由同一校验器判定；校验器对结构敏感、对排版美观不敏感",
                "quote 回证率受源文本提取质量影响；源文本缺失时本报告只登记不宣称"],
            "failure_conditions": [
                "plan 不可解析→本报告 ok:false，result.json 不写入增益键",
                "源文本为空→quote/numeric 闸门 skipped，diff 不可机器判定并如实登记"],
        }
        # ---- 效率计数 ----
        pages = len([s for s in plan.get("slides", []) if isinstance(s, dict)])
        manual_a = sum(1 for f in (r_a.get("fails") or []) for _ in
                       (f.get("items") if isinstance(f.get("items"), list) else [f]))
        manual_b = sum(1 for f in (r_b.get("fails") or []) for _ in
                       (f.get("items") if isinstance(f.get("items"), list) else [f]))
        rep["efficiency"] = {
            "pages_built": pages,
            "mechanical_checks_run": (m_a.get("checks_total", 0) * 3),
            "arms_validated": 3,
            "manual_review_items_skill": manual_a,
            "manual_review_items_ablated": manual_b,
            "reduction": max(0, manual_b - manual_a),
            "note": "可自动采集计数；模型请求数与工具调用数由平台 Harness 记录，本脚本不虚构",
        }
    except Exception as e:
        rep = {"ok": False, "error": str(e)}
    if args.write and rep.get("ok"):
        try:
            result = {}
            if os.path.exists(args.result):
                result = json.load(open(args.result, encoding="utf-8"))
            result["gain_evidence"] = {k: v for k, v in rep.items() if k != "efficiency"}
            result["efficiency"] = rep["efficiency"]
            os.makedirs(os.path.dirname(args.result), exist_ok=True)
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
            rep["written"] = True
        except Exception as e:
            rep["written"] = False
            rep["write_error"] = str(e)
    try:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(rep, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    print(json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        sys.exit(0)  # 所有失败路径（含 argparse error）一律退出码 0

