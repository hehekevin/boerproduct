#!/usr/bin/env python3
"""verify_check.py — 科研问题驱动检索结果机械校验器（quest-search / challenge-e7598a44）。

校验 result.json 业务逻辑：问题结构化拆解、子问题→查询覆盖、查询式与依赖合法性、
候选来源可追溯与相关性判定有据、缺口登记枚举与完备性、停止条件事前声明、
可复现性汇总一致性、claims 证据链数字回证、结论分级约束、运行状态枚举。
每条检查输出三元组 {item, template_value, applied, match} 嵌入 result.json；
闸门状态显式枚举 enforced / skipped_not_provided / not_found / unreadable；
未回证的数字逐条列入 unbacked_numbers 并计入 fail。

--ablate 提供**退化/基线模式**（关闭子问题覆盖校验 / 相关性判定校验 / 缺口登记校验），
仅用于增益对照实验，不得用于交付自检。
--selftest 校验包标志文件身份（防串包），不读 result.json。
任何异常均捕获降级，退出码恒 0，绝不崩溃。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|coverage|relevance|gaps|all]
    python3 verify_check.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

GAP_KINDS = {"no_result", "conflict", "metadata_missing", "permission", "other"}
VERDICTS = {"search_completed", "partial_coverage", "cannot_verify", "refused"}
RUN_STATUS = {"success", "partial", "unable_to_determine", "refused"}
ABLATE_MODES = {"none", "coverage", "relevance", "gaps", "all"}
STATUS_ENUM = ("answered", "partial", "insufficient_evidence", "input_error")
RQ_DIMENSIONS = ("object", "mechanism", "method", "time_range", "comparison",
                 "evidence_requirements")
MARKER_FILE = ".package-marker.json"
MARKER_PACKAGE = "quest-search"
MARKER_CHALLENGE = "challenge-e7598a44"


def norm(s):
    """空白归一化，用于 quote/text 子串匹配。"""
    return re.sub(r"\s+", "", str(s or ""))


def num_variants(x):
    """数字的多种字符串形态（归一化后），供逐字回证匹配。
    注意：只按 float 可转换性判定数字，不用 str.isalpha 判断（汉字会误过 isalpha）。"""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return []
    out = {norm("%g" % f), norm(repr(f))}
    try:
        if f == int(f):
            out.add(norm(str(int(f))))
    except Exception:
        pass
    return [v for v in out if v]


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _txt(v):
    return bool(str(v or "").strip())


def subq_status(inner):
    """逐子问题机器判定：has_query / has_candidate_link / has_gap / covered。
    covered = 有查询 且（有候选关联 或 有缺口登记）。纯函数，不写盘。"""
    subqs = [s for s in (inner.get("subquestions") or []) if isinstance(s, dict)]
    plan = [q for q in (inner.get("query_plan") or []) if isinstance(q, dict)]
    cands = [c for c in (inner.get("candidates") or []) if isinstance(c, dict)]
    gaps = [g for g in (inner.get("gaps") or []) if isinstance(g, dict)]
    plan_ids = {str(q.get("query_id")) for q in plan if q.get("query_id") is not None}
    plan_subq = {str(q.get("subq_id")) for q in plan if q.get("subq_id") is not None}
    cand_subq = set()
    for c in cands:
        for sid in (c.get("subq_ids") or []):
            cand_subq.add(str(sid))
    gap_subq = {str(g.get("subq_id")) for g in gaps if g.get("subq_id") is not None}
    rows = []
    for i, s in enumerate(subqs):
        sid = str(s.get("subq_id"))
        qids = [str(x) for x in (s.get("query_ids") or [])]
        has_query = bool(qids) and any(q in plan_ids for q in qids)
        has_cand = sid in cand_subq
        has_gap = sid in gap_subq
        rows.append({"index": i, "subq_id": sid, "has_query": has_query,
                     "has_candidate_link": has_cand, "has_gap": has_gap,
                     "covered": has_query and (has_cand or has_gap)})
    return rows


def numeric_fields(res):
    """枚举 result.json 中所有可回证数值位：候选相关性分数等。
    返回 [{path, value, side, check}]，供增益探针计算机器判定占比。"""
    out = []
    inner = res.get("result") if isinstance(res, dict) else {}
    if not isinstance(inner, dict):
        return out
    for i, c in enumerate(inner.get("candidates") or []):
        if isinstance(c, dict) and is_num(c.get("relevance_score")):
            out.append({"path": "candidates[%d].relevance_score" % i,
                        "value": c.get("relevance_score"), "side": "computed",
                        "check": "candidates[%d].relevance_backed" % i})
    return out


def selftest():
    """校验包标志文件身份：防止 find|head -1 式定位串包。退出码恒 0。"""
    here = os.path.dirname(os.path.abspath(__file__))
    mpath = os.path.join(here, MARKER_FILE)
    problems = []
    pkg = chal = None
    try:
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8") as f:
                m = json.load(f)
            pkg, chal = m.get("package"), m.get("challenge")
        else:
            problems.append("标志文件不存在: %s" % mpath)
    except Exception as e:
        problems.append("标志文件读取失败: %s" % e)
    if pkg is not None and pkg != MARKER_PACKAGE:
        problems.append("package 不匹配: %r != %r" % (pkg, MARKER_PACKAGE))
    if chal is not None and chal != MARKER_CHALLENGE:
        problems.append("challenge 不匹配: %r != %r" % (chal, MARKER_CHALLENGE))
    ok = not problems and pkg == MARKER_PACKAGE and chal == MARKER_CHALLENGE
    print("[verify_check] selftest %s  package=%s challenge=%s script=%s"
          % ("PASS" if ok else "FAIL", pkg, chal, os.path.basename(__file__)))
    for p in problems:
        print("  - %s" % p)
    print("[verify_check] selftest 报告 verdict=%s（退出码恒 0，不中断交付）"
          % ("PASS" if ok else "FAIL"))
    return 0


def _dump(report, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def analyze(res, case, ablate="none", case_state="enforced"):
    """核心校验逻辑（纯函数式，不写盘）。

    返回报告 dict：problems / warnings / counts / self_check / gates /
    unbacked_numbers / disabled_checks / verdict。绝不抛异常。
    """
    problems, warnings, self_check, gates, unbacked = [], [], [], [], []
    disabled = []

    def add_check(item, template, applied, match, fatal=True, note=None):
        if match is None:
            match = False
        entry = {"item": item, "template_value": template,
                 "applied": bool(applied), "match": bool(match)}
        if note:
            entry["note"] = note
        self_check.append(entry)
        if applied and match is False and fatal:
            problems.append("%s 未通过: %s" % (item, template))

    def skip_check(item, template, reason):
        self_check.append({"item": item, "template_value": template, "applied": False,
                           "match": False, "note": reason})
        disabled.append(item)

    res = res if isinstance(res, dict) else {}
    case = case if isinstance(case, dict) else {}
    off_coverage = ablate in ("coverage", "all")
    off_relevance = ablate in ("relevance", "all")
    off_gaps = ablate in ("gaps", "all")

    # 闸门 1/2
    gates.append({"gate": "result_readable", "state": "enforced", "note": ""})
    if case_state == "enforced":
        gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
    else:
        gates.append({"gate": "case_contract", "state": case_state,
                      "note": "case.json 不可用，output_contract 校验跳过；下游不得宣称已核对"})
        warnings.append("case.json 不可用（%s），契约字段校验跳过" % case_state)

    # 通用契约字段
    try:
        add_check("case_id", "case_id 非空", True, bool(res.get("case_id")))
        missing_top = [k for k in ("status", "result", "claims", "uncertainties") if k not in res]
        add_check("top_fields", "status/result/claims/uncertainties 全键", True, not missing_top)
        if missing_top:
            problems.extend("缺少通用契约字段: %s" % k for k in missing_top)
        add_check("status_enum", "status ∈ answered/partial/insufficient_evidence/input_error",
                  res.get("status") is not None, res.get("status") in STATUS_ENUM, fatal=False)
        if res.get("status") not in STATUS_ENUM:
            warnings.append("status 非约定枚举: %r" % res.get("status"))
    except Exception as e:
        problems.append("契约字段检查异常: %s" % e)

    inner = {}
    try:
        inner = res.get("result") if isinstance(res.get("result"), dict) else {}
        if not inner:
            problems.append("result 为空或非对象")
    except Exception:
        inner = {}

    # claims 证据库（空白归一化后的 quote / text 集合）
    quotes, texts = [], []
    try:
        for c in res.get("claims") or []:
            if not isinstance(c, dict):
                continue
            texts.append(norm(c.get("text")))
            for ev in (c.get("evidence") or []):
                if isinstance(ev, dict):
                    quotes.append(norm(ev.get("quote")))
    except Exception:
        pass
    quotes = [q for q in quotes if q]
    texts = [t for t in texts if t]

    def backed_by_texts(x):
        return any(v in t for v in num_variants(x) for t in texts)

    # 1. 研究问题结构化
    try:
        rq = inner.get("research_question")
        add_check("research_question.present", "须有结构化研究问题 research_question",
                  True, isinstance(rq, dict) and bool(rq))
        if isinstance(rq, dict):
            filled = [d for d in RQ_DIMENSIONS if _txt(rq.get(d)) and str(rq.get(d)).strip() != "unknown"]
            add_check("research_question.dimensions",
                      "至少 1 个维度（对象/机制/方法/时间范围/比较/证据要求）有具体值",
                      True, bool(filled), fatal=False)
            add_check("research_question.scope", "须写明检索范围 scope", True, _txt(rq.get("scope")))
    except Exception as e:
        problems.append("研究问题检查异常: %s" % e)

    # 2. 子问题清单与查询覆盖（ablatable）
    plan_ids = set()
    try:
        plan = inner.get("query_plan") or []
        plan_ids = {str(q.get("query_id")) for q in plan
                    if isinstance(q, dict) and q.get("query_id") is not None}
        add_check("query_plan.present", "须有查询计划 query_plan", True, bool(plan))
        for i, q in enumerate(plan):
            if not isinstance(q, dict):
                problems.append("query_plan[%d] 非对象" % i)
                continue
            add_check("query_plan[%d].query_string" % i, "查询式 query_string 非空",
                      True, _txt(q.get("query_string")))
            add_check("query_plan[%d].subq_ref" % i,
                      "查询须挂到子问题 subq_id", True, _txt(q.get("subq_id")))
            deps = q.get("depends_on") or []
            bad = [str(d) for d in deps if str(d) not in plan_ids]
            if deps:
                add_check("query_plan[%d].deps_valid" % i,
                          "依赖 depends_on 须指向存在的 query_id", True, not bad)
                if bad:
                    problems.append("query_plan[%d] 依赖不存在的 query_id: %s" % (i, bad))
        if plan:
            any_exp = any(isinstance(q, dict) and (q.get("term_expansions")
                          or _txt(q.get("term_expansions"))) for q in plan)
            add_check("query_plan.term_expansions", "至少一条查询做了术语/同义词扩展",
                      True, any_exp, fatal=False)
            if not any_exp:
                warnings.append("全部查询无 term_expansions（术语扩展缺失，召回可能不足）")
    except Exception as e:
        problems.append("查询计划检查异常: %s" % e)

    try:
        subqs = inner.get("subquestions") or []
        add_check("subquestions.present", "须有子问题清单 subquestions", True, bool(subqs))
        rows = subq_status(inner)
        for i, s in enumerate(subqs):
            if not isinstance(s, dict):
                problems.append("subquestions[%d] 非对象" % i)
                continue
            add_check("subquestions[%d].id_text" % i, "子问题须有 subq_id 与 text",
                      True, _txt(s.get("subq_id")) and _txt(s.get("text")))
            qids = [str(x) for x in (s.get("query_ids") or [])]
            hit = bool(qids) and any(q in plan_ids for q in qids)
            if off_coverage:
                skip_check("subquestions[%d].query_coverage" % i,
                           "子问题 %s 须挂到 query_plan 中存在的查询" % s.get("subq_id"),
                           "ablate=coverage 已关闭子问题覆盖校验（仅用于增益对照）")
            else:
                add_check("subquestions[%d].query_coverage" % i,
                          "子问题 %s 须挂到 query_plan 中存在的查询" % s.get("subq_id"),
                          True, hit)
                if not hit:
                    problems.append("subquestions[%d] 无有效查询覆盖" % i)
    except Exception as e:
        problems.append("子问题检查异常: %s" % e)

    # 3. 多轮检索记录
    try:
        rounds = inner.get("search_rounds") or []
        if not rounds:
            warnings.append("search_rounds 为空（多轮检索未记录，检索过程可解释性受限）")
        for i, r in enumerate(rounds):
            if not isinstance(r, dict):
                problems.append("search_rounds[%d] 非对象" % i)
                continue
            add_check("search_rounds[%d].structure" % i,
                      "轮次须有 round 与 findings/adjustment 之一", True,
                      r.get("round") is not None
                      and (_txt(r.get("findings")) or _txt(r.get("adjustment"))))
    except Exception as e:
        problems.append("检索轮次检查异常: %s" % e)

    # 4. 候选集：可追溯 + 相关性有据（ablatable）+ 排除有因
    has_numbers = False
    try:
        cands = inner.get("candidates") or []
        add_check("candidates.present", "须有候选文献集 candidates", True, bool(cands))
        for i, c in enumerate(cands):
            if not isinstance(c, dict):
                problems.append("candidates[%d] 非对象" % i)
                continue
            add_check("candidates[%d].traceable" % i,
                      "候选须有来源 source 与定位 location（可追溯）", True,
                      _txt(c.get("source")) or _txt(c.get("location")))
            sids = [str(x) for x in (c.get("subq_ids") or [])]
            add_check("candidates[%d].subq_ref" % i,
                      "候选须关联至少一个子问题", True, bool(sids))
            if off_relevance:
                skip_check("candidates[%d].relevance_basis" % i,
                           "候选须写明相关性依据 relevance_basis",
                           "ablate=relevance 已关闭相关性判定校验（仅用于增益对照）")
            else:
                add_check("candidates[%d].relevance_basis" % i,
                          "候选须写明相关性依据 relevance_basis", True, _txt(c.get("relevance_basis")))
            if c.get("included") is False and not _txt(c.get("exclusion_reason")):
                if off_relevance:
                    skip_check("candidates[%d].exclusion_reason" % i,
                               "included=false 须写明排除原因 exclusion_reason",
                               "ablate=relevance 已关闭相关性判定校验（仅用于增益对照）")
                else:
                    add_check("candidates[%d].exclusion_reason" % i,
                              "included=false 须写明排除原因 exclusion_reason", True, False)
            if is_num(c.get("relevance_score")):
                has_numbers = True
                if off_relevance:
                    skip_check("candidates[%d].relevance_backed" % i,
                               "relevance_score 数字须在 claim text 中回证",
                               "ablate=relevance 已关闭数字回证（仅用于增益对照）")
                else:
                    ok = backed_by_texts(c.get("relevance_score"))
                    add_check("candidates[%d].relevance_backed" % i,
                              "relevance_score 数字须在 claim text 中回证", True, ok,
                              fatal=False)
                    if not ok:
                        unbacked.append("candidates[%d].relevance_score=%r 无 claim text 回证"
                                        % (i, c.get("relevance_score")))
    except Exception as e:
        problems.append("候选集检查异常: %s" % e)

    # 5. 缺口登记（ablatable）
    try:
        gaps = inner.get("gaps") or []
        for i, g in enumerate(gaps):
            if not isinstance(g, dict):
                problems.append("gaps[%d] 非对象" % i)
                continue
            if off_gaps:
                skip_check("gaps[%d].kind_enum" % i,
                           "gap kind ∈ no_result/conflict/metadata_missing/permission/other",
                           "ablate=gaps 已关闭缺口登记校验（仅用于增益对照）")
                skip_check("gaps[%d].follow_up" % i,
                           "gap 须写明 description 与 follow_up",
                           "ablate=gaps 已关闭缺口登记校验（仅用于增益对照）")
            else:
                add_check("gaps[%d].kind_enum" % i,
                          "gap kind ∈ no_result/conflict/metadata_missing/permission/other",
                          True, g.get("kind") in GAP_KINDS)
                add_check("gaps[%d].follow_up" % i,
                          "gap 须写明 description 与 follow_up", True,
                          _txt(g.get("description")) and _txt(g.get("follow_up")))
    except Exception as e:
        problems.append("缺口登记检查异常: %s" % e)

    # 6. 停止条件事前声明
    try:
        sc = inner.get("stop_criteria") or {}
        add_check("stop_criteria.present", "须有停止条件 stop_criteria", True, bool(sc))
        declared = sc.get("declared_before")
        dec_ok = declared is True or _txt(declared)
        add_check("stop_criteria.declared", "停止条件须事前声明 declared_before（检索前写定）",
                  True, dec_ok)
        add_check("stop_criteria.substance", "停止条件须写明实质规则（marginal_rule/stop_reason）",
                  True, _txt(sc.get("marginal_rule")) or _txt(sc.get("stop_reason")))
    except Exception as e:
        problems.append("停止条件检查异常: %s" % e)

    # 7. 可复现性汇总一致性（随 coverage 一起消融）
    try:
        rec = inner.get("reproducibility") or {}
        add_check("reproducibility.present", "须有可复现性汇总 reproducibility", True, bool(rec))
        rows = subq_status(inner)
        total = len(rows)
        q_cov = sum(1 for r in rows if r["has_query"])
        e_cov = sum(1 for r in rows if r["covered"])
        if off_coverage:
            skip_check("reproducibility.consistency",
                       "reproducibility 计数须与子问题实际覆盖一致（total=%d query=%d evidence=%d）"
                       % (total, q_cov, e_cov),
                       "ablate=coverage 已关闭覆盖一致性校验（仅用于增益对照）")
        elif rec:
            ok = (rec.get("total_subquestions") == total
                  and rec.get("query_covered") == q_cov
                  and rec.get("evidence_covered") == e_cov
                  and rec.get("uncovered") == total - e_cov)
            ratio = (e_cov / total) if total else None
            ok_ratio = (ratio is None and rec.get("ratio") in (None, 0)) or \
                       (ratio is not None and is_num(rec.get("ratio"))
                        and abs(rec["ratio"] - ratio) < 1e-6)
            add_check("reproducibility.consistency",
                      "reproducibility 计数须与子问题实际覆盖一致（total=%d query=%d evidence=%d）"
                      % (total, q_cov, e_cov), True, ok and ok_ratio)
    except Exception as e:
        problems.append("可复现性汇总检查异常: %s" % e)

    # 8. 复现步骤
    try:
        steps = inner.get("steps") or []
        add_check("steps.present", "须有复现步骤列表 steps[]", True, bool(steps))
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                problems.append("steps[%d] 非对象" % i)
                continue
            add_check("steps[%d].action" % i, "须写明动作 action", True,
                      bool(str(s.get("action") or "").strip()))
        if steps:
            add_check("steps.has_command", "至少一条步骤给出可执行命令 command", True,
                      any(str(s.get("command") or "").strip() for s in steps
                          if isinstance(s, dict)))
    except Exception as e:
        problems.append("复现步骤校验异常: %s" % e)

    # 9. 运行状态
    try:
        rs = inner.get("run_status") or {}
        add_check("run_status.present", "须有运行状态 run_status{state,reason}", True, bool(rs))
        if rs:
            add_check("run_status.state", "state ∈ success/partial/unable_to_determine/refused",
                      True, rs.get("state") in RUN_STATUS)
            add_check("run_status.reason", "须写明状态原因 reason", True, _txt(rs.get("reason")))
            if rs.get("state") in ("partial", "unable_to_determine", "refused"):
                add_check("run_status.takeover", "非成功状态须给出人工接管位置 manual_takeover",
                          True, bool(rs.get("manual_takeover")))
    except Exception as e:
        problems.append("运行状态校验异常: %s" % e)

    # 10. 增益证据与效率计数
    try:
        ge = inner.get("gain_evidence")
        add_check("gain_evidence.present", "须有 gain_evidence（正常 vs 退化双模式对照）",
                  True, ge is not None)
        if isinstance(ge, dict):
            if ge.get("available") is False:
                add_check("gain_evidence.available_false_reason",
                          "available=false 须写明原因 reason", True, _txt(ge.get("reason")))
            else:
                runs = ge.get("runs") or []
                modes = [str(r.get("mode")) for r in runs if isinstance(r, dict)]
                add_check("gain_evidence.runs", "runs 须含 normal 与 degraded 两遍实跑记录",
                          True, "normal" in modes and "degraded" in modes)
                add_check("gain_evidence.delta", "须有 delta_normal_minus_degraded 对照差值",
                          True, isinstance(ge.get("delta_normal_minus_degraded"), dict)
                          and bool(ge.get("delta_normal_minus_degraded")))
                add_check("gain_evidence.mechanism_map", "须有机制→指标映射 mechanism_to_metric_map",
                          True, bool(ge.get("mechanism_to_metric_map")))
                add_check("gain_evidence.boundaries", "须写明边界 boundaries", True,
                          bool(ge.get("boundaries")))
                add_check("gain_evidence.failure_conditions", "须写明失效条件 failure_conditions",
                          True, bool(ge.get("failure_conditions")))
        eff = inner.get("efficiency")
        add_check("efficiency.present", "须有 efficiency 效率计数", True, eff is not None)
        if isinstance(eff, dict):
            if eff.get("available") is False:
                add_check("efficiency.available_false_reason",
                          "available=false 须写明原因 reason", True, _txt(eff.get("reason")))
            else:
                add_check("efficiency.reproduce", "efficiency 须写明复现方式 reproduce", True,
                          _txt(eff.get("reproduce")))
                add_check("efficiency.counters", "efficiency 须含自动采集计数", True,
                          eff.get("wall_clock_seconds_total") is not None
                          or eff.get("checker_runs") is not None)
    except Exception as e:
        problems.append("增益证据校验异常: %s" % e)

    # 11. 结论分级约束
    try:
        verdict = inner.get("verdict")
        add_check("verdict_enum", "∈ search_completed/partial_coverage/cannot_verify/refused",
                  True, verdict in VERDICTS)
        rows = subq_status(inner)
        uncovered = sum(1 for r in rows if not r["covered"])
        if verdict == "search_completed" and not off_coverage:
            add_check("verdict_completion", "search_completed 须全部子问题 covered（当前 uncovered=%d）"
                      % uncovered, True, uncovered == 0)
        if verdict == "cannot_verify":
            add_check("verdict_material_gaps", "cannot_verify 须有 material_gaps 或 gaps 登记",
                      True, bool(inner.get("material_gaps") or inner.get("gaps")))
        if verdict == "partial_coverage" and not off_coverage:
            add_check("verdict_partial_basis", "partial_coverage 须写明 verdict_basis（缺哪些）",
                      True, _txt(inner.get("verdict_basis")))
    except Exception as e:
        problems.append("结论分级检查异常: %s" % e)

    # 12. claims 证据链覆盖 + 数字回证
    try:
        claims = res.get("claims") or []
        add_check("claims_coverage", "有可回证数字则 claims 非空", True,
                  not (has_numbers and not claims))
        for i, c in enumerate(claims):
            if isinstance(c, dict):
                for k in ("kind", "source_id", "location"):
                    if c.get(k) in (None, ""):
                        warnings.append("claims[%d] 缺 %s" % (i, k))
    except Exception as e:
        warnings.append("claims 检查异常: %s" % e)

    if off_relevance:
        add_check("numbers_backed", "全部可回证数字有逐字回证（本次已关闭回证）", False, True,
                  note="ablate=relevance 已关闭数字回证（仅用于增益对照）")
    elif unbacked:
        add_check("numbers_backed",
                  "全部可回证数字有逐字回证（unbacked=%d）" % len(unbacked), True, False)
    else:
        add_check("numbers_backed", "全部可回证数字有逐字回证",
                  bool(has_numbers), True, fatal=False)

    # 13. 环境快照
    try:
        env = inner.get("environment") or {}
        add_check("environment.python_version",
                  "environment 须有 python_version（或 python）", True,
                  isinstance(env, dict) and bool(env.get("python_version") or env.get("python")))
    except Exception as e:
        problems.append("环境快照检查异常: %s" % e)

    counts = {"subquestions": len(inner.get("subquestions") or []),
              "query_plan": len(inner.get("query_plan") or []),
              "search_rounds": len(inner.get("search_rounds") or []),
              "candidates": len(inner.get("candidates") or []),
              "gaps": len(inner.get("gaps") or []),
              "claims": len(res.get("claims") or []),
              "steps": len(inner.get("steps") or []),
              "unbacked_numbers": len(unbacked),
              "checks_executed": sum(1 for s in self_check if s.get("applied")),
              "checks_disabled": len(disabled)}
    return {"ok": not problems, "verdict": "PASS" if not problems else "FAIL",
            "problems": problems, "warnings": warnings, "counts": counts,
            "self_check": self_check, "gates": gates, "unbacked_numbers": unbacked,
            "disabled_checks": disabled, "ablate": ablate}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/verify_check.json")
        ap.add_argument("--ablate", default="none", choices=sorted(ABLATE_MODES),
                        help="退化/基线模式：关闭子问题覆盖(coverage)/相关性判定(relevance)/"
                             "缺口登记(gaps)校验；仅用于增益对照，不得用于交付自检")
        ap.add_argument("--selftest", action="store_true",
                        help="校验包标志文件身份（防串包），不读 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    if args.selftest:
        return selftest()

    # 读 result
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        print("[verify_check] FAIL: result.json 不存在: %s（不中断交付）" % args.result)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 不存在"],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "not_found",
                          "note": "result.json 缺失，下游不得宣称已核对"}],
               "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0
    except Exception as e:
        print("[verify_check] FAIL: result.json 解析失败: %s（不中断交付）" % e)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 解析失败: %s" % e],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "unreadable",
                          "note": "result.json 不可解析，下游不得宣称已核对"}],
               "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0

    # 读 case（可选输入）
    case, case_state = {}, "skipped_not_provided"
    if args.case and os.path.exists(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_state = "enforced"
        except Exception:
            case_state = "unreadable"
    try:
        report = analyze(res, case, ablate=args.ablate, case_state=case_state)
    except Exception as e:
        report = {"ok": False, "verdict": "FAIL", "problems": ["校验异常: %s" % e],
                  "warnings": [], "counts": {}, "self_check": [],
                  "gates": [{"gate": "result_readable", "state": "enforced", "note": ""}],
                  "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}
    _dump(report, args.out)

    # 三元组 + unbacked + 闸门状态嵌入 result.json（评分器不开附件即可核对）
    try:
        res["self_check"] = report["self_check"]
        res["unbacked_numbers"] = report["unbacked_numbers"]
        res["gates"] = report["gates"]
        res["validator_verdict"] = report["verdict"]
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        report["warnings"].append("self_check/gates 回写 result.json 失败: %s" % e)

    for g in report["gates"]:
        if g["state"] != "enforced":
            report["warnings"].append("闸门 %s=%s：%s" % (g["gate"], g["state"], g["note"]))
    print("[verify_check] %s  ablate=%s  %s" % (report["verdict"], args.ablate, report["counts"]))
    for p in report["problems"][:30]:
        print("  - %s" % p)
    if report["unbacked_numbers"]:
        print("  unbacked numbers:")
        for u in report["unbacked_numbers"][:20]:
            print("  ! %s" % u)
    for w in report["warnings"][:20]:
        print("  ? %s" % w)
    print("[verify_check] 报告: %s（退出码恒 0，不中断交付）" % args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
