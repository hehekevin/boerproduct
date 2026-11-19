#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（lit-search-pro）。

同一输入跑多遍：正常模式（全部机械校验开启）与退化/基线模式（--ablate 分别
关闭逐字回证 backing / 去重校验 dedup / 追溯与覆盖校验 trace，或 all 全关），
逐项对照七类可观测指标：

  1. traceable_adjudicated 来源可追溯（被机器逐条判定的文献数）
  2. dup_missed          去重漏检数（客观重复但未被标记/未被判定的条数）
  3. numbers_adjudicated 数字回证覆盖（被机器逐位判定的数值位数）
  4. manual_review_items 需人工核对条目数
  5. steps_count         步骤数（校验层已执行检查项 + 流程已执行步骤）
  6. clarification_rounds 追问轮次（每轮 3 条打包折算，公式随记录落盘）
  7. 查询覆盖数 / 关键词扩展数 / 去重率 / 遗漏登记数（数据属性，两臂相同）

另采集 efficiency 效率计数，支持 --inject-pollution 生成污染副本做反例自测
（正常模式须抓到污染，且退出码恒 0）。
**本脚本只产出对照证据，不修改业务结论；退化模式仅用于增益对照，不得用于
交付自检。**
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
    from verify_check import analyze, numeric_fields, norm_title, norm_doi  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[gain_probe] 无法导入 verify_check: %s" % e)
    sys.exit(0)

ROUND_BATCH = 3  # 追问轮次折算：每轮最多消化 3 条人工条目
ARMS = [("normal", "none"), ("degraded_backing", "backing"),
        ("degraded_dedup", "dedup"), ("degraded_trace", "trace"),
        ("degraded_all", "all")]


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


def objective_dup_missed(res):
    """独立复算客观重复：按归一化标题聚类，多出的行未被标 duplicate_of 即漏检。"""
    inner = (res or {}).get("result") or {}
    papers = [p for p in (inner.get("papers") or []) if isinstance(p, dict)]
    seen_titles, objective = {}, 0
    for p in papers:
        nt = norm_title(p.get("title"))
        doi = norm_doi(p.get("doi"))
        key = ("doi:" + doi) if doi else ("t:" + nt if nt else None)
        if key and key in seen_titles:
            objective += 1
        elif key:
            seen_titles[key] = True
    marked = sum(1 for p in papers if p.get("duplicate_of"))
    return max(0, objective - marked), objective, marked


def mode_metrics(res, report, label):
    """从一次真实运行的 report 计算对照指标（全部来自实测，不臆造）。"""
    idx = check_index(report)
    fields = numeric_fields(res)
    inner = (res or {}).get("result") or {}
    papers = [p for p in (inner.get("papers") or []) if isinstance(p, dict)]

    # 1. 来源可追溯机器判定覆盖
    trace_ok = 0
    for i in range(len(papers)):
        e = idx.get("papers[%d].trace" % i)
        if e is not None and e.get("applied") and e.get("match"):
            trace_ok += 1
    trace_ratio_machine = (round(trace_ok / len(papers), 6) if papers else None)

    # 2. 去重漏检（客观真值由探针独立复算）
    dup_missed, obj_dups, marked = objective_dup_missed(res)

    # 3. 数字回证覆盖：papers 数值位对应检查项 applied=true + 计数回证检查 applied
    nums_ok = sum(1 for f in fields
                  if (idx.get(f["check"]) or {}).get("applied"))
    total_num = len(fields) + 1  # +1 为 counts.numbers_backed 计数回证检查
    if (idx.get("counts.numbers_backed") or {}).get("applied"):
        nums_ok += 1

    # 3b. 去重判定覆盖：dedup.* 检查项 applied=true 的数量
    dedup_adjudicated = sum(1 for item, e in idx.items()
                            if item.startswith("dedup.") and e.get("applied"))

    # 4. 需人工核对条目：未被机器判定的数值位 + 追溯未判定文献 + 去重漏检
    manual = ((len(papers) - trace_ok) + (total_num - nums_ok) + dup_missed)

    # 5. 步骤数
    checks_executed = sum(1 for s in (report.get("self_check") or [])
                          if isinstance(s, dict) and s.get("applied"))
    steps_field = inner.get("steps") or []
    steps_done = sum(1 for s in steps_field if isinstance(s, dict)
                     and str(s.get("status") or "done").lower() in ("done", "ok", "completed"))
    steps_count = checks_executed + steps_done

    # 6. 追问轮次
    rounds = int(math.ceil(manual / float(ROUND_BATCH))) if manual else 0

    # 数据属性（两臂相同，供参考）
    qexec = [q for q in (inner.get("queries_executed") or []) if isinstance(q, dict)]
    dedup = inner.get("dedup") or {}
    return {
        "mode": label,
        "ablate": report.get("ablate"),
        "verdict": report.get("verdict"),
        "problems": len(report.get("problems") or []),
        "unbacked_numbers": len(report.get("unbacked_numbers") or []),
        "metrics": {
            "traceable_adjudicated": trace_ok,
            "papers_total": len(papers),
            "traceability_ratio_machine": trace_ratio_machine,
            "traceability_ratio_declared": (inner.get("coverage") or {}).get("traceability_ratio"),
            "dup_missed": dup_missed,
            "dup_objective": obj_dups,
            "dup_marked": marked,
            "numbers_adjudicated": nums_ok,
            "numeric_fields_total": total_num,
            "dedup_adjudicated": dedup_adjudicated,
            "manual_review_items": manual,
            "manual_review_breakdown": {
                "trace_not_adjudicated": len(papers) - trace_ok,
                "numbers_not_adjudicated": len(fields) - nums_ok,
                "dup_missed": dup_missed,
            },
            "steps_count": steps_count,
            "steps_detail": {"checks_executed": checks_executed,
                             "flow_steps_total": len(steps_field),
                             "flow_steps_done": steps_done},
            "clarification_rounds": rounds,
            "query_coverage_count": len({q.get("query_id") for q in qexec if q.get("query_id")}),
            "keyword_expansion_count": len(inner.get("keyword_expansion") or []),
            "dedup_rate": dedup.get("dedup_rate"),
            "gap_registered_count": len(inner.get("gaps") or []),
        },
    }


def inject_pollution(res):
    """在副本上注入 4 类污染（不触碰交付文件本身）。返回 (polluted, plan)。"""
    p = copy.deepcopy(res or {})
    inner = p.setdefault("result", {})
    plan = []
    papers = inner.get("papers") or []

    if papers and isinstance(papers[0], dict):
        # 1) 注入未标记的重复文献（去重机制须抓到）
        dup = copy.deepcopy(papers[0])
        dup["paper_id"] = "pollution-dup"
        dup["duplicate_of"] = None
        if dup.get("doi"):
            dup["doi"] = None  # 仅靠标题相同判定重复
        papers.append(dup)
        plan.append("追加 papers[0] 的同题副本 pollution-dup 且不标 duplicate_of（去重漏检反例）")
        # 2) 清空来源追溯字段
        papers[0]["matched_queries"] = []
        plan.append("papers[0].matched_queries 清空（来源不可追溯反例）")
        # 3) 篡改年份（无 quote 回证反例）
        if isinstance(papers[0].get("year"), (int, float)):
            papers[0]["year"] = int(papers[0]["year"]) + 800
            plan.append("papers[0].year 加 800（无 quote 回证反例）")
    else:
        plan.append("（无 papers，跳过文献污染）")
    # 4) 破坏去重统计一致性
    dedup = inner.get("dedup") or {}
    if isinstance(dedup, dict):
        dedup["removed_duplicates"] = 0
        plan.append("dedup.removed_duplicates 置 0（与实际标记不一致反例）")
    return p, plan


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--input-root", default=None)
        ap.add_argument("--out", default=None, help="对照证据落盘路径")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 gain_evidence 写入 result.json 的 result.gain_evidence")
        ap.add_argument("--inject-pollution", action="store_true",
                        help="额外生成污染副本做反例自测")
        args = ap.parse_args()
    except SystemExit:  # argparse error 也退出码 0（题面硬约束）
        return 0
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

    # --- 多臂真实运行：同一输入、同一份文件内容 ---
    runs = []
    for label, ablate in ARMS:
        t1 = time.time()
        rep = analyze(copy.deepcopy(res), copy.deepcopy(case) if case else {},
                      ablate=ablate, case_state=case_state)
        m = mode_metrics(res, rep, label)
        m["wall_clock_seconds"] = round(time.time() - t1, 4)
        runs.append(m)

    # 指标差（normal − 各退化臂，正数表示机制带来的增益）
    by_mode = {m["mode"]: m for m in runs}
    delta = {}
    mkeys = ("traceable_adjudicated", "traceability_ratio_machine", "dup_missed",
             "numbers_adjudicated", "dedup_adjudicated", "manual_review_items",
             "steps_count", "clarification_rounds")
    for label, _ in ARMS[1:]:
        d = {}
        for k in mkeys:
            a = runs[0]["metrics"].get(k)
            b = by_mode[label]["metrics"].get(k)
            d[k] = (round(a - b, 6) if isinstance(a, (int, float))
                    and isinstance(b, (int, float)) else None)
        delta[label] = d

    mechanism_map = [
        {"metric": "traceable_adjudicated / traceability_ratio_machine",
         "mechanism": "来源可追溯三要素校验（source_db + matched_queries + rationale 逐条判定）"
                      "+ 覆盖统计复算",
         "formula": "trace 检查 applied=true 且 match=true 的文献数 / 文献总数",
         "higher_is_better": True,
         "degrade_effect": "关闭追溯校验后，文献不再被机器逐条判定可追溯性，"
                           "不可追溯条目只能靠人工发现"},
        {"metric": "dup_missed",
         "mechanism": "去重一致性与统计复算（duplicate_of 指向有效性 + removed_duplicates"
                      "与实际标记数核对 + dedup_rate 复算）",
         "formula": "客观重复数（探针按归一化标题/DOI 独立聚类）− 已标记重复数",
         "higher_is_better": False,
         "degrade_effect": "关闭去重校验后，未标记的重复文献不再被判 FAIL，漏检上升"},
        {"metric": "numbers_adjudicated",
         "mechanism": "数字逐字回证（年份须在来源 quote、分数/计数须在 claim text；"
                      "标识符内嵌数字排除、区间端点保留）",
         "formula": "对应回证检查 applied=true 的数值位数 / 全部数值位",
         "higher_is_better": True,
         "degrade_effect": "关闭回证后，年份/分数/计数不再被机器逐位判定，"
                           "无出处的数字无法被发现"},
        {"metric": "manual_review_items",
         "mechanism": "追溯判定覆盖 + 数字判定覆盖 + 去重漏检 三项合计",
         "formula": "追溯未判定文献数 + 数值位未判定数 + 去重漏检数",
         "higher_is_better": False,
         "degrade_effect": "机器判定面缩小后，需人工逐条核对的条目增加"},
        {"metric": "steps_count",
         "mechanism": "六步线性流程 + 机械校验三元组自检",
         "formula": "校验层已执行检查项数 + 流程层已完成步骤数",
         "higher_is_better": None,
         "degrade_effect": "关闭检查项会减少执行计数，但换来漏检——步骤少不等于质量高"},
        {"metric": "clarification_rounds",
         "mechanism": "把人工核对条目按每轮 %d 条打包（公式随记录落盘）" % ROUND_BATCH,
         "formula": "ceil(manual_review_items / %d)" % ROUND_BATCH,
         "higher_is_better": False,
         "degrade_effect": "人工条目越多，回来源材料/回问所需的轮次越多"},
        {"metric": "query_coverage_count / keyword_expansion_count / dedup_rate / "
                   "gap_registered_count",
         "mechanism": "多轮查询计划 + 规则关键词扩展 + 机械去重 + 遗漏登记（流程层机制，"
                      "指标为数据属性，两臂相同；其增益体现在流程覆盖广度）",
         "formula": "执行的查询 id 数 / 扩展词数 / removed_duplicates ÷ total_raw / gaps 行数",
         "higher_is_better": True,
         "degrade_effect": "不走规划/扩展/去重/登记流程时这些产出直接缺失或退化"},
    ]

    boundaries = [
        "对照对象是本校验层自身的正常模式与各退化模式，不是平台基础 Agent 与参赛 Agent 的"
        "平台白板对照；平台对照结论由平台生成，本探针不代替、不冒充。",
        "退化模式只关闭对应机制的检查（backing/dedup/trace 各一臂 + all 全关），结构枚举、"
        "契约字段等检查仍开启，因此退化侧漏检数是下界而非最坏情形。",
        "去重漏检的客观真值由探针按归一化标题/DOI 独立聚类得出，与校验层分开算；"
        "同名不同 DOI 不计入客观重复。",
        "数字回证覆盖的分母只统计 papers[].year、relevance_score、queries_executed[].result_count"
        "及 dedup/coverage 计数；DOI/URL/ID 等标识符内嵌数字不参与。",
        "追问轮次是按约定批量（每轮 3 条）折算的估计量，不是实测交互次数；"
        "原始计数 manual_review_items 一并落盘，可换批量重算。",
        "wall_clock_seconds 为本机各次 analyze 调用耗时，受机器负载影响，仅作同次对照参考。",
        "本探针是机制消融（同一校验层开关对照），不是对 Agent 大模型行为本身的消融。",
    ]

    failure_conditions = [
        "result.json 不存在或不可解析 → 探针输出 FAIL 并以退出码 0 结束，不改交付物。",
        "case.json 缺失 → case_contract 闸门记 skipped_not_provided，"
        "契约字段校验跳过，下游不得宣称已核对。",
        "退化模式报告只可用于增益对照；把 --ablate 的结果当作交付自检结论即为误用。",
        "污染反例自测只在副本上注入，原 result.json 不被修改。",
        "papers 为空时追溯/去重指标无区分度（分母为 0），增益以 all 臂的检查项计数差为准。",
    ]

    gain_evidence = {
        "probe_version": "1.0",
        "probe_tool": "scripts/gain_probe.py",
        "case_id": res.get("case_id"),
        "input": {"result_path": os.path.abspath(args.result),
                  "case_path": os.path.abspath(args.case),
                  "case_contract_state": case_state,
                  "same_input_for_all_runs": True,
                  "run_order": [label for label, _ in ARMS],
                  "note": "各臂均读取同一份 result.json 内容（深拷贝传入校验函数，"
                          "不做任何原地修改）"},
        "runs": runs,
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": mechanism_map,
        "boundaries": boundaries,
        "failure_conditions": failure_conditions,
        "interpretation_rule": "delta>0 且指标方向为 higher_is_better 时表示机制带来增益；"
                               "delta=0 表示该指标在本输入上无区分度；"
                               "dup_missed / manual_review_items / clarification_rounds "
                               "为 lower_is_better，读 delta 的相反符号。",
    }

    # 污染反例自测（副本）
    if args.inject_pollution:
        polluted, plan = inject_pollution(res)
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
            "injected": plan,
            "normal_mode": {"verdict": p_normal.get("verdict"),
                            "problems": len(p_normal.get("problems") or []),
                            "unbacked_numbers": len(p_normal.get("unbacked_numbers") or []),
                            "dup_missed": pm_n["metrics"]["dup_missed"],
                            "manual_review_items": pm_n["metrics"]["manual_review_items"],
                            "problem_sample": (p_normal.get("problems") or [])[:8]},
            "degraded_mode": {"verdict": p_deg.get("verdict"),
                              "problems": len(p_deg.get("problems") or []),
                              "unbacked_numbers": len(p_deg.get("unbacked_numbers") or []),
                              "dup_missed": pm_d["metrics"]["dup_missed"],
                              "manual_review_items": pm_d["metrics"]["manual_review_items"],
                              "problem_sample": (p_deg.get("problems") or [])[:8]},
            "missed_detection_delta": {
                "dup_missed": (pm_d["metrics"]["dup_missed"]
                               - pm_n["metrics"]["dup_missed"]),
                "unbacked_numbers": (len(p_deg.get("unbacked_numbers") or [])
                                     - len(p_normal.get("unbacked_numbers") or [])),
                "problems": (len(p_deg.get("problems") or [])
                             - len(p_normal.get("problems") or [])),
            },
            "caught_by_normal_mode": bool(p_normal.get("problems")),
            "note": "污染仅注入副本；正常模式须抓到污染项，退化模式漏检属预期。"
                    "missed_detection_delta > 0 表示退化模式漏掉的项数。",
        }

    # efficiency：自动可采集的效率计数
    elapsed = round(time.time() - t0, 4)
    try:
        size_bytes = os.path.getsize(args.result)
    except Exception:
        size_bytes = None
    efficiency = {
        "collected_by": "scripts/gain_probe.py（自动采集）",
        "wall_clock_seconds_total": elapsed,
        "result_bytes": size_bytes,
        "checker_runs": len(ARMS),
        "checker_checks_executed_normal": runs[0]["metrics"]["steps_detail"]["checks_executed"],
        "checker_checks_executed_degraded_all": runs[-1]["metrics"]["steps_detail"]["checks_executed"],
        "flow_steps_total": runs[0]["metrics"]["steps_detail"]["flow_steps_total"],
        "flow_steps_done": runs[0]["metrics"]["steps_detail"]["flow_steps_done"],
        "numeric_fields_total": runs[0]["metrics"]["numeric_fields_total"],
        "papers_total": runs[0]["metrics"]["papers_total"],
        "manual_review_items_normal": runs[0]["metrics"]["manual_review_items"],
        "manual_review_items_degraded_all": runs[-1]["metrics"]["manual_review_items"],
        "clarification_rounds_normal": runs[0]["metrics"]["clarification_rounds"],
        "clarification_rounds_degraded_all": runs[-1]["metrics"]["clarification_rounds"],
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

    print("[gain_probe] %d 臂实跑完成：" % len(runs))
    for m in runs:
        mt = m["metrics"]
        print("  %-18s verdict=%-4s problems=%d trace_ok=%d/%d dup_missed=%d "
              "nums_ok=%d/%d manual=%d checks=%d"
              % (m["mode"], m["verdict"], m["problems"],
                 mt["traceable_adjudicated"], mt["papers_total"], mt["dup_missed"],
                 mt["numbers_adjudicated"], mt["numeric_fields_total"],
                 mt["manual_review_items"], mt["steps_detail"]["checks_executed"]))
    if gain_evidence.get("pollution_selftest"):
        ps = gain_evidence["pollution_selftest"]
        print("[gain_probe] 污染反例: normal 抓到=%s (problems=%d) | 退化臂 problems=%d"
              % (ps["caught_by_normal_mode"], ps["normal_mode"]["problems"],
                 ps["degraded_mode"]["problems"]))
    print("[gain_probe] 证据落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
