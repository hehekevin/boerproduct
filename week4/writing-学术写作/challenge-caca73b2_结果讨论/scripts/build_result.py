#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_result.py — 组装/更新 result.json（结果与讨论章节写作 · 统一收尾）
把 case_id、output_contract 原字段、主产物（指针 + 全文嵌入）、证据映射、数字-来源核对表、
讨论结论溯源表、检查报告、增益证据(gain_evidence)、效率(efficiency)、状态与不确定性
组装成 /app/output/result.json。已有骨架时只回填不覆盖（保留早期诚实状态）。

用法:
  python3 build_result.py --case /input/case.json --out /app/output/result.json \
      --artifact results_discussion.docx --artifact-md results_discussion.md \
      --embed-md /app/output/results_discussion.md \
      --evidence evidence_map.jsonl --fact-check fact_check.json \
      --trace-audit trace_audit.json --source-table number_source_table.json \
      --dclaims dclaims.jsonl --consistency check_report.json --render previews/render_log.json \
      --gain-baseline gain_baseline.json --efficiency efficiency.json \
      --status complete --notes '[待核条目...]'
字段均可缺省；output_contract 中的字段若无法填写，保持 null 并在 uncertainty 说明。

增益证据（--gain-baseline）: 传入退化/基线模式跑出的 trace_audit 报告，
与本次 --trace-audit 逐项对照，合成 gain_evidence 字段（真实数字来自两次真实运行）。
"""
import argparse, json, os, sys


def load_jsonish(p):
    if not p or not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        try:
            return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        except Exception:
            return {"raw_path": p}


def _ensure_list(result, key):
    """保证 result[key] 是 list。

    契约字段回填时可能把 uncertainty/changelog 置为 None（表示「尚未填写」），
    此处必须就地修复为 list，否则后续 append 会抛 AttributeError 导致收尾中断。
    已有字符串内容转为单元素列表，不丢信息。
    """
    v = result.get(key)
    if isinstance(v, list):
        return v
    result[key] = [] if v is None else [str(v)]
    return result[key]


def _add_note(result, key, msg):
    _ensure_list(result, key).append(str(msg))


# ---- 增益证据合成：逐项对照 full vs baseline 两遍真实运行 ----
MECHANISM_TO_METRIC = [
    {"mechanism": "stat_verify", "name": "统计量逐条回证（数字-来源核对表）",
     "metric": "统计表述有据率 / 未回证数值数",
     "direction": "关闭后未回证数值不被发现，有据率统计失去意义（基线无核对表）",
     "ablate_key": "stat_verify"},
    {"mechanism": "strength_audit", "name": "限定强度机检（强断言↔本研究数据）",
     "metric": "强断言违规数",
     "direction": "关闭后强断言无独立检出，违规数归零（不等于不存在）",
     "ablate_key": "strength_audit"},
    {"mechanism": "separation", "name": "描述/解释分离检测",
     "metric": "推断-实测混淆数",
     "direction": "关闭后结果段混入解释不再被抓出，混淆数归零",
     "ablate_key": "separation"},
    {"mechanism": "claim_evidence", "name": "讨论结论【依据：…】标注与溯源",
     "metric": "需人工核对条目数（缺依据结论）",
     "direction": "关闭后缺依据结论数归零，待核负担被隐藏而非减少",
     "ablate_key": "claim_evidence"},
    {"mechanism": "crossref", "name": "图表交叉引用双向完整性核对",
     "metric": "交叉引用缺口数",
     "direction": "关闭后登记图/表漏引与未登记引用不再被抓出",
     "ablate_key": "crossref"},
]


def build_gain_evidence(full_ta, base_ta):
    """两遍真实运行的逐项对照。full_ta=本次完整模式报告；base_ta=退化/基线模式报告。"""
    if not isinstance(full_ta, dict) or not isinstance(base_ta, dict):
        return None
    fg = full_ta.get("gain_metrics") or {}
    bg = base_ta.get("gain_metrics") or {}
    ff = fg.get("fixed_evaluator") or {}
    bf = bg.get("fixed_evaluator") or {}
    fp = fg.get("input_fingerprint") or {}
    bp = bg.get("input_fingerprint") or {}

    def g(d, k, default=None):
        return d.get(k) if d.get(k) is not None else default

    rows = []

    def row(item, label, full_v, base_v, unit, better, note, mech="", caliber="fixed_evaluator"):
        rows.append({"item": item, "metric": label, "full_mode": full_v, "baseline_mode": base_v,
                     "unit": unit, "direction": better, "mechanism": mech, "note": note,
                     "caliber": caliber})

    # ---- 第一层：固定评估器口径（同一输入恒定，证明两遍跑输入一致）----
    row("stat_evidence_rate", "统计表述有据率", g(ff, "stat_evidence_rate"), g(bf, "stat_evidence_rate"),
        "ratio", "越高越好",
        "固定评估器口径：同一草稿下恒定，两遍相等即证明对照输入一致；真实差异见 delivered_* 同名指标。", "stat_verify")
    row("stat_statements_total", "统计表述总数（分母）", g(ff, "stat_statements_total"),
        g(bf, "stat_statements_total"), "count", "同输入应相等",
        "两遍跑同一草稿，分母一致才说明对照公平。", "stat_verify")
    row("stat_statements_backed", "有逐字来源的统计表述数", g(ff, "stat_statements_backed"),
        g(bf, "stat_statements_backed"), "count", "越高越好", "有据数值条数。", "stat_verify")
    row("stat_unverified", "未回证数值数（需人工核对）", g(ff, "defects", {}).get("stat_unverified"),
        g(bf, "defects", {}).get("stat_unverified"), "count", "越低越好",
        "固定评估器口径：两遍相同，证明污染数值必然出现在同一位置。", "stat_verify")
    row("strong_claim_violations", "强断言违规数", g(ff, "strong_claim_violations"),
        g(bf, "strong_claim_violations"), "count", "越低越好",
        "固定评估器口径；基线运行不检出，真实违规数不变。", "strength_audit")
    row("inference_measurement_confusion", "推断-实测混淆数", g(ff, "inference_measurement_confusion"),
        g(bf, "inference_measurement_confusion"), "count", "越低越好",
        "结果段把观察与解释混写的句数。", "separation")
    row("manual_review_items", "需人工核对条目数", g(ff, "manual_review_items"),
        g(bf, "manual_review_items"), "count", "越低越好",
        "真实待核负担；基线因不检出而显示为 0，属统计假象，不代表人工核对需求下降。", "claim_evidence")
    row("detected_total", "本模式检出缺陷数", g(fg, "detected_total"), g(bg, "detected_total"),
        "count", "完整模式应 ≥ 基线", "本模式护栏实际抓到的缺陷数。", "", "delivered")
    row("detection_coverage", "缺陷检出覆盖率", g(fg, "detection_coverage"), g(bg, "detection_coverage"),
        "ratio", "越高越好", "检出数 ÷ 固定评估器算出的真实缺陷总数。", "", "delivered")
    fd = fg.get("delivered") or {}
    bd = bg.get("delivered") or {}
    row("auto_verified_statements", "自动完成逐字回证的统计表述数", g(fd, "auto_verified_statements"),
        g(bd, "auto_verified_statements"), "count", "越高越好",
        "自动回证条数 = 免去作者逐条手工核对的工作量。", "stat_verify", "delivered")
    row("statements_requiring_manual_source_check", "仍需人工回材料核对的统计表述数",
        g(fd, "statements_requiring_manual_source_check"),
        g(bd, "statements_requiring_manual_source_check"), "count", "越低越好",
        "统计表述总数 − 自动回证数；这是真实的人工核对工作量。", "stat_verify", "delivered")
    row("defects_visible_to_reviewer", "对复核者可见的缺陷数", g(fd, "defects_visible_to_reviewer"),
        g(bd, "defects_visible_to_reviewer"), "count", "越高越好",
        "本模式报出的缺陷条数；退化模式显示为 0 属「缺陷不可见」的统计假象。", "", "delivered")
    row("defects_hidden_from_reviewer", "对复核者不可见的缺陷数", g(fd, "defects_hidden_from_reviewer"),
        g(bd, "defects_hidden_from_reviewer"), "count", "越低越好",
        "真实缺陷总数 − 本模式检出数；退化模式此值升高即「返工/漏发风险」。", "", "delivered")
    row("reviewer_manual_burden", "复核者总人工核对负担", g(fd, "reviewer_manual_burden"),
        g(bd, "reviewer_manual_burden"), "count", "越低越好",
        "需人工回材料核对的统计表述数 + 未暴露缺陷数；越低说明自动化覆盖越高。", "", "delivered")
    row("steps_executed", "流程步骤数", g(fg, "steps_executed"), g(bg, "steps_executed"),
        "count", "越少越省（但检出能力同步下降）", "退化模式少跑的步骤即被省掉的护栏动作。", "", "delivered")
    row("steps_total", "流程总步骤数（设计基线）", g(fg, "steps_total"), g(bg, "steps_total"),
        "count", "恒定", "完整流程的动作总数，两遍相同。", "", "delivered")

    # ---- 第二层：交付口径（本模式实际交付给下游的可核验量，随护栏开关变化）----
    # 固定评估器口径对同一输入恒定，故 5 项核心指标的「真实差异」体现在这一层。
    row("delivered_stat_evidence_rate", "统计表述有据率（交付口径）",
        g(fd, "delivered_evidence_rate"), g(bd, "delivered_evidence_rate"),
        "ratio", "越高越好",
        "本模式实际完成逐字回证的统计表述占比；关闭 stat_verify 后无人回证 → 0，是护栏的直接效果。",
        "stat_verify", "delivered")
    row("delivered_strong_claim_violations", "强断言违规数（交付口径·已检出）",
        (fg.get("detected_defects") or {}).get("strong_claim_without_data_basis"),
        (bg.get("detected_defects") or {}).get("strong_claim_without_data_basis"),
        "count", "越低越好",
        "本模式实际报给复核者的强断言违规条数；基线为 0 属「缺陷不可见」，不是稿件更干净。",
        "strength_audit", "delivered")
    row("delivered_inference_measurement_confusion", "推断-实测混淆数（交付口径·已检出）",
        (fg.get("detected_defects") or {}).get("inference_measurement_confusion"),
        (bg.get("detected_defects") or {}).get("inference_measurement_confusion"),
        "count", "越低越好",
        "本模式实际报出的结果段推断-实测混写条数；关闭 separation 后不再被识别。",
        "separation", "delivered")
    row("delivered_manual_review_items", "需人工核对条目数（交付口径·复核者实际承担）",
        g(fd, "reviewer_manual_burden"), g(bd, "reviewer_manual_burden"),
        "count", "越低越好",
        "复核者实际要处理的条目数 = 仍需人工回材料核对的统计表述数 + 未暴露缺陷数；"
        "固定评估器的 manual_review_items 两遍恒定，此处才是随模式变化的真实负担。",
        "claim_evidence", "delivered")
    row("delivered_residual_defect_rate", "残留缺陷率（交付口径·带进交付的缺陷占比）",
        g(fd, "residual_defect_rate"), g(bd, "residual_defect_rate"),
        "ratio", "越低越好",
        "本模式未暴露因而会随稿交付的缺陷占真实缺陷总数的比例；基线 1.0 = 全部缺陷静默通过。",
        "", "delivered")

    same_input = all(
        fp.get(k) is not None and fp.get(k) == bp.get(k)
        for k in ("draft", "readings") if fp.get(k) is not None
    )
    return {
        "method": "同一输入两遍真实运行：同一草稿/同一 readings/同一 ledger/同一 dclaims，"
                  "分别以「完整模式（全部护栏生效）」与「退化基线模式（--ablate 关闭全部护栏）」跑 trace_audit.py，"
                  "逐项对照。两层口径：fixed_evaluator（同一输入恒定，证明对照公平）与 delivered（随护栏开关变化，证明增益）。",
        "calibers": {
            "fixed_evaluator": "对同一草稿恒定计算，与护栏开关无关；两遍相等即证明输入一致（对照公平性证据）。",
            "delivered": "本模式实际交付给复核者的可核验量与人工负担；随护栏开关变化，是增益的真实落点。",
        },
        "how_to_reproduce": [
            "python3 scripts/trace_audit.py --draft <md> --readings <readings.jsonl> --ledger <ledger.jsonl> "
            "--dclaims <dclaims.jsonl> --out-table number_source_table.json --out trace_audit.json",
            "python3 scripts/trace_audit.py --draft <md> --readings <readings.jsonl> --ledger <ledger.jsonl> "
            "--dclaims <dclaims.jsonl> --ablate stat_verify,strength_audit,claim_evidence,crossref,separation "
            "--out trace_audit_baseline.json",
            "python3 scripts/build_result.py --case /input/case.json --out result.json --trace-audit trace_audit.json "
            "--gain-baseline trace_audit_baseline.json --source-table number_source_table.json --embed-md <md>",
        ],
        "same_input_verified": same_input,
        "input_fingerprint": {"full": fp, "baseline": bp,
                              "note": "sha1 前 16 位；draft/readings 一致即两遍跑输入相同。"},
        "full_mode": {"verdict": full_ta.get("verdict"), "fail_count": full_ta.get("fail_count"),
                      "gates": full_ta.get("gates"), "detected_total": fg.get("detected_total"),
                      "detection_coverage": fg.get("detection_coverage"),
                      "steps_executed": fg.get("steps_executed"),
                      "delivered": fd},
        "baseline_mode": {"mode": bg.get("mode"), "ablate_requested": bg.get("ablate_requested"),
                          "verdict": base_ta.get("verdict"), "fail_count": base_ta.get("fail_count"),
                          "gates": base_ta.get("gates"), "detected_total": bg.get("detected_total"),
                          "detection_coverage": bg.get("detection_coverage"),
                          "steps_executed": bg.get("steps_executed"),
                          "delivered": bd,
                          "note": "退化模式 verdict=pass 不等于稿件合格：护栏未生效，只代表该模式未检出。"},
        "metrics": rows,
        "mechanism_to_metric": MECHANISM_TO_METRIC,
        "boundaries": [
            "对照是同一草稿的「机制开关」对照，证明护栏的检出能力；不等于「不加载 Skill 的基础 Agent」对照，"
            "后者由平台在固定案例上运行并比较，本包不预置其结果。",
            "退化基线关闭护栏后计数归零属统计假象（未检出不等于不存在）；真实缺陷数以 fixed_evaluator 口径为准，"
            "该口径两遍恒定正是对照公平性的证据。",
            "增益读 delivered 口径：统计表述有据率、强断言违规数（已检出）、推断-实测混淆数（已检出）、"
            "复核者人工负担、残留缺陷率、流程步骤数；这些指标随护栏开关真实变化。",
            "质量增益以检出缺陷数与覆盖率为代理指标，最终章节质量分由平台评分表给出，本包不臆造评分。",
            "效率以步骤数与人工负担为代理指标；实际耗时/请求数由平台记录，本包不虚构平台数据。",
            "以上数字来自本包在合成夹具上的真实运行（标注为示意），非正式案例结果。",
        ],
    }


def build_efficiency(full_ta, gain_evidence, notes=None):
    """效率字段：步骤数 / 自动回证条目 / 人工待核条目（真实计数，来源可回溯）。"""
    if not isinstance(full_ta, dict):
        return None
    g = full_ta.get("gain_metrics") or {}
    f = g.get("fixed_evaluator") or {}
    d = g.get("delivered") or {}
    ns = full_ta.get("number_source_summary") or {}
    eff = {
        "workflow_steps_total": g.get("steps_total"),
        "workflow_steps_executed": g.get("steps_executed"),
        "workflow_step_list": g.get("step_list"),
        "auto_verified_statements": d.get("auto_verified_statements"),
        "auto_verified_ratio": f.get("stat_evidence_rate"),
        "delivered_evidence_rate": d.get("delivered_evidence_rate"),
        "residual_defect_rate": d.get("residual_defect_rate"),
        "statements_requiring_manual_source_check": d.get("statements_requiring_manual_source_check"),
        "manual_review_items": f.get("manual_review_items"),
        "manual_review_breakdown": f.get("defects"),
        "reviewer_manual_burden": d.get("reviewer_manual_burden"),
        "checks_run": {"numbers_checked": ns.get("checked"), "numbers_matched": ns.get("matched"),
                       "numbers_ledger": ns.get("ledger"), "numbers_unmatched": ns.get("unmatched")},
        "measures": [
            {"metric": "workflow_steps_executed", "meaning": "完整流程实际执行的动作数（可由 step_list 逐条核对）"},
            {"metric": "auto_verified_statements", "meaning": "自动完成逐字回证的统计表述条数（免去人工逐条核对）"},
            {"metric": "delivered_evidence_rate", "meaning": "交付口径的统计表述有据率 = 自动回证条数 ÷ 统计表述总数"},
            {"metric": "statements_requiring_manual_source_check", "meaning": "仍需人工回材料核对的统计表述条数"},
            {"metric": "manual_review_items", "meaning": "固定评估器口径的真实缺陷条目数（同一输入恒定）"},
            {"metric": "reviewer_manual_burden", "meaning": "复核者总人工负担 = 待核表述数 + 未暴露缺陷数"},
            {"metric": "residual_defect_rate", "meaning": "未暴露、因而随稿交付的缺陷占真实缺陷总数的比例"},
        ],
        "boundary": "步骤数为工作流动作计数，不等于模型请求数；真实请求数与耗时由平台记录，本包不臆造。"
                    "效率对照见 gain_evidence.metrics（完整模式 vs 退化基线，同输入两遍真实运行）；"
                    "其中 fixed_evaluator 口径恒定（证明输入一致），delivered 口径随护栏开关变化（真实增益）。",
    }
    if gain_evidence:
        rows = {r["item"]: r for r in gain_evidence.get("metrics", [])}
        eff["baseline_comparison"] = {
            "baseline_steps_executed": rows.get("steps_executed", {}).get("baseline_mode"),
            "steps_saved_by_baseline": (rows.get("steps_executed", {}).get("full_mode", 0) or 0)
                                       - (rows.get("steps_executed", {}).get("baseline_mode", 0) or 0),
            "note": "基线少跑的步骤即被省掉的护栏动作；省步骤与保检出不可兼得，取舍由本字段明示。",
        }
    if notes:
        eff["notes"] = notes
    return eff


def build_semantics(ta, result):
    """题面输出要求表 → result.json 字段语义映射。
    题面要求三类内容：目标产物 / 事实与来源映射 / 版本与边界。
    本函数把「结果表述、统计量、交叉引用、限定强度、解释与推断分离」五项可核验语义
    显式落到 result.json 的字段上，并给出每项的来源字段与判定状态。"""
    if not isinstance(ta, dict):
        return None
    rs = ta.get("result_statements") or []
    dc = ta.get("discussion_claims") or {}
    xr = ta.get("crossref") or {}
    sep = ta.get("separation") or {}
    nss = ta.get("number_source_summary") or {}
    sc = dc.get("strength_check") or {}

    def item(name, requirement, source_field, status, detail):
        return {"item": name, "requirement": requirement, "source_field": source_field,
                "status": status, "detail": detail}

    semantics = {
        "target_artifact": {
            "requirement": "可编辑的稿件/结构化写作产物（目标产物）",
            "fields": ["deliverable", "main_text_markdown"],
            "present": bool(result.get("main_text_markdown")) or bool(result.get("deliverable")),
            "status": "pass" if (result.get("main_text_markdown") or result.get("deliverable")) else "missing",
        },
        "checks": [
            item("结果表述", "结果段只陈述观察到的现象，且数值与图表一致",
                 "trace_audit.result_statements",
                 "pass" if rs and all(s.get("observation_only") for s in rs) else ("fail" if rs else "missing"),
                 {"total_statements": len(rs),
                  "observation_only": sum(1 for s in rs if s.get("observation_only")),
                  "numeric_without_figure_ref": sum(1 for s in rs if "numeric_without_figure_ref" in (s.get("issues") or [])),
                  "ref_not_registered": sum(1 for s in rs if any(i.startswith("ref_not_registered") for i in (s.get("issues") or [])))}),
            item("统计量", "统计量/误差棒/单位与图注原文一致，数值逐条可回溯",
                 "trace_audit.number_source_summary + number_source_table",
                 "pass" if nss.get("checked", 0) and not nss.get("unmatched") else ("fail" if nss.get("unmatched") else "missing"),
                 {"checked": nss.get("checked"), "matched": nss.get("matched"),
                  "ledger": nss.get("ledger"), "unmatched": nss.get("unmatched"),
                  "note": "统计量逐字回证表见 result.json.number_source_table"}),
            item("交叉引用", "登记的图/表全被结果段引用，引用编号全已登记（双向）",
                 "trace_audit.crossref",
                 xr.get("verdict", "missing") if xr.get("verdict") != "skipped" else "skipped",
                 {"registered": xr.get("registered"), "cited_in_results": xr.get("cited_in_results"),
                  "missing_in_text": xr.get("missing_in_text"), "unknown_in_text": xr.get("unknown_in_text")}),
            item("限定强度", "讨论结论语气强度与证据强度匹配（强断言须本研究数据）",
                 "trace_audit.discussion_claims.strength_check",
                 "pass" if not sc.get("fail") else "fail",
                 {"checked": sc.get("checked"), "fail": sc.get("fail"),
                  "strength_fail": sc.get("strength_fail"), "annotation_fail": sc.get("annotation_fail"),
                  "fail_detail": sc.get("fail_detail")}),
            item("解释与推断分离", "结果段不混入解释/推断，讨论段承担解释与局限",
                 "trace_audit.separation",
                 sep.get("verdict", "missing") if sep.get("verdict") != "skipped" else "skipped",
                 {"inference_measurement_confusion": sep.get("inference_measurement_confusion"),
                  "pure_observation_sentences": sep.get("pure_observation_sentences"),
                  "confusions": sep.get("confusions")}),
        ],
        "fact_source_mapping": {
            "requirement": "事实与来源映射：数字/术语/引用/图表/关键论断的来源或修改记录，可逐条回溯",
            "fields": ["evidence_map", "number_source_table", "readings", "discussion_claims"],
            "present": any(result.get(k) for k in ("evidence_map", "number_source_table", "readings", "discussion_claims")),
            "status": "pass" if any(result.get(k) for k in ("evidence_map", "number_source_table", "readings", "discussion_claims")) else "missing",
        },
        "version_and_boundary": {
            "requirement": "版本与边界：修改差异、人工确认项、材料缺口与异常分别说明",
            "fields": ["status", "uncertainty", "changelog"],
            "present": bool(result.get("status")),
            "status": "pass" if result.get("status") else "missing",
            "status_level": result.get("status"),
            "note": "status 为诚实四级之一（complete/partial/failed/blocked）；"
                    "uncertainty 载明读数缺口/估读项/冲突/推测句/待核条目。",
        },
        "honesty_note": "每个 status=missing 表示该项在本案例中无对应数据或检查未运行，"
                        "不得据此宣称已核对；闸门状态见 trace_audit.gates。",
    }
    return semantics


def main():
    """顶层安全网：任何异常都不中断交付链；如实记录后返回 0。"""
    try:
        return _run()
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:400],
                          "note": "组装脚本内部异常，已如实记录；交付链不中断。"},
                         ensure_ascii=False))
        return 0


def _run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--artifact-md", default=None)
    ap.add_argument("--embed-md", default=None, help="主产物 md 全文嵌入 result.json（主产物完整随行）")
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--fact-check", default=None)
    ap.add_argument("--trace-audit", default=None, help="trace_audit.json（核对表摘要+交叉引用+讨论溯源）")
    ap.add_argument("--source-table", default=None, help="number_source_table.json 数字-来源逐条核对表")
    ap.add_argument("--dclaims", default=None, help="dclaims.jsonl 讨论结论溯源表")
    ap.add_argument("--readings", default=None, help="readings.jsonl 图表读数登记（全量嵌入，供独立复核）")
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--render", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--boundary-check", default=None, help="boundary_check.json（结果/讨论边界报告）")
    ap.add_argument("--gain-baseline", default=None,
                    help="退化/基线模式跑出的 trace_audit.json；与 --trace-audit 对照合成 gain_evidence")
    ap.add_argument("--efficiency-notes", default=None, help="efficiency 附加说明（JSON 数组或 ; 分隔）")
    ap.add_argument("--status", default="partial")
    ap.add_argument("--notes", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--changelog", default=None, help="JSON 数组字符串或 ; 分隔文本")
    ap.add_argument("--set", action="append", default=[], help="--set key=value 直接回填 output_contract 字段")
    args = ap.parse_args()

    case = load_jsonish(args.case) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown_case"
    contract = case.get("output_contract") or {}

    result_path = args.out
    old = load_jsonish(result_path) if os.path.exists(result_path) else None
    result = old if isinstance(old, dict) else {}

    result.setdefault("case_id", case_id)
    # 契约字段原样保留（值可为 null，后面 --set 或模型回填）
    for k in contract if isinstance(contract, list) else (contract.get("fields") or contract.get("required") or []):
        if isinstance(k, str):
            result.setdefault(k, None)
    # uncertainty / changelog 是累积列表型字段：契约回填留下的 None 就地修正为 []
    for k in ("uncertainty", "changelog"):
        if k in result:
            _ensure_list(result, k)
    for kv in args.set:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                v = json.loads(v)
            except Exception:
                pass
            result[k] = v
            if k in ("uncertainty", "changelog"):
                _ensure_list(result, k)

    if args.artifact:
        result["deliverable"] = {"docx": args.artifact, "markdown": args.artifact_md or None,
                                 "editable": True}
    # 主产物全文嵌入：即使预览/文件丢失，result.json 单文件即可复核完整章节文本
    if args.embed_md and os.path.exists(args.embed_md):
        try:
            text = open(args.embed_md, encoding="utf-8").read()
            if text.strip():
                result["main_text_markdown"] = text
        except Exception as e:
            _add_note(result, "uncertainty", f"main_text embed failed: {e}")
    ev = load_jsonish(args.evidence)
    if ev is not None:
        result["evidence_map"] = ev
    fc = load_jsonish(args.fact_check)
    if fc is not None:
        result["fact_check"] = fc
    ta = load_jsonish(args.trace_audit)
    if ta is not None:
        result["trace_audit"] = ta
    st = load_jsonish(args.source_table)
    if st is not None:
        result["number_source_table"] = st
    dc = load_jsonish(args.dclaims)
    if dc is not None:
        result["discussion_claims"] = dc
    rdgs = load_jsonish(args.readings)
    if rdgs is not None:
        result["readings"] = rdgs  # 图表读数登记全量嵌入：核数表之外的原始读数证据链
    cc = load_jsonish(args.consistency)
    if cc is not None:
        result["consistency_check"] = cc
    rd = load_jsonish(args.render)
    if rd is not None:
        result["render"] = rd
    lg = load_jsonish(args.ledger)
    if lg is not None:
        result["fact_ledger_ref"] = args.ledger
    bc = load_jsonish(args.boundary_check)
    if bc is not None:
        result["boundary_check"] = bc

    def as_list(s):
        if not s: return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [str(v)]
        except Exception:
            return [x.strip() for x in s.split(";") if x.strip()]

    # ---- 增益证据：完整模式 vs 退化基线，两遍真实运行逐项对照 ----
    base_ta = load_jsonish(args.gain_baseline)
    gain_evidence = build_gain_evidence(ta, base_ta)
    if gain_evidence is not None:
        result["gain_evidence"] = gain_evidence
    else:
        _add_note(result, "uncertainty",
                  "gain_evidence 未生成：缺少退化基线运行的 trace_audit 报告（--gain-baseline），"
                  "本次交付未提供同输入对照的增益证据。")

    # ---- 效率字段 ----
    eff = build_efficiency(ta, gain_evidence, notes=as_list(args.efficiency_notes) if args.efficiency_notes else None)
    if eff is not None:
        result["efficiency"] = eff

    # ---- 题面输出要求表字段语义映射（结果表述/统计量/交叉引用/限定强度/解释与推断分离）----
    # --notes/--changelog 追加而非覆盖：保住上面已写入的缺口说明
    if args.notes:
        for n in as_list(args.notes):
            _add_note(result, "uncertainty", n)
    _ensure_list(result, "uncertainty")
    if args.changelog:
        for c in as_list(args.changelog):
            _add_note(result, "changelog", c)
    _ensure_list(result, "changelog")
    result["status"] = args.status

    semantics = build_semantics(ta, result)
    if semantics is not None:
        result["output_semantics"] = semantics

    os.makedirs(os.path.dirname(result_path) or ".", exist_ok=True)
    json.dump(result, open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "result": result_path, "status": args.status,
                      "embedded_main_text": bool(result.get("main_text_markdown")),
                      "number_source_rows": len(result["number_source_table"]) if isinstance(result.get("number_source_table"), list) else 0,
                      "readings_rows": len(result["readings"]) if isinstance(result.get("readings"), list) else 0,
                      "gain_evidence": bool(result.get("gain_evidence")),
                      "efficiency": bool(result.get("efficiency")),
                      "output_semantics": bool(result.get("output_semantics")),
                      "keys": list(result.keys())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
