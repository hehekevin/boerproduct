#!/usr/bin/env python3
"""verify_check.py — 学术文献检索结果机械校验器（lit-search-pro）。

校验 result.json 业务逻辑：查询计划与关键词扩展结构、来源可追溯
（source_db + matched_queries + rationale）、去重一致性与统计复算、覆盖统计
一致性、数字逐字回证（年份/分数/计数在 claims quote 或 claim text 中回证；
DOI/URL/ID 等标识符内嵌数字不参与回证防误报，区间端点逐端回证）、
遗漏登记完备性、结论分级约束、运行状态与枚举。
每条检查输出三元组 {item, template_value, applied, match}；闸门状态显式枚举
enforced / skipped_not_provided / not_found / unreadable；未回证数字列入
unbacked_numbers 并计入 fail。

--ablate 提供**退化/基线模式**（backing=关闭逐字回证 / dedup=关闭去重校验 /
trace=关闭追溯与覆盖校验 / all=全部关闭），仅用于增益对照实验，不得用于交付
自检。纯函数 analyze() 不写盘不读环境，供 gain_probe 复用。任何异常均捕获
降级，绝不崩溃。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|backing|dedup|trace|all]
退出码：恒为 0（PASS/FAIL 记录在报告 verdict 字段与 stdout，失败不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

VERDICTS = {"complete", "partial", "empty", "cannot_verify"}
RUN_STATUS = {"success", "partial", "unable_to_determine", "refused"}
STATUS_ENUM = ("answered", "partial", "insufficient_evidence", "input_error")
EXP_KINDS = {"variant", "abbreviation", "synonym", "related_term", "translation",
             "acronym_backform", "synonym_expansion"}
QUERY_STATUS = {"executed", "failed", "skipped"}
DB_STATUS = {"accessible", "rate_limited", "unavailable", "not_tried"}
GAP_KINDS = {"empty_result", "conflict", "missing_metadata", "access_denied",
             "rate_limited", "suspected_miss"}
ABLATE_MODES = {"none", "backing", "dedup", "trace", "all"}
# 标识符字段：内嵌数字不参与回证（防误报）；区间端点保留（逐端子串回证）
IDENTIFIER_KEYS = ("doi", "url", "paper_id", "query_id", "claim_id", "gap_id",
                   "isbn", "issn", "orcid", "material_id", "source_id")


def norm(s):
    """归一化：小写、去标点、空白折叠（不用 isalpha，避免汉字误判）。"""
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", str(s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def num_variants(x):
    """数字的多种字符串形态（归一化后），供逐字回证匹配。"""
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


def norm_title(t):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(t or "").lower())).strip()


def norm_doi(d):
    s = str(d or "").strip().lower()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    return s.strip()


def numeric_fields(res):
    """枚举 papers[] 中逐行回证的数值位（year / relevance_score）。

    返回 [{path, value, side, check}]：side=paper（来源侧，须在 quote）/
    computed（本方计算侧，须在 claim text）。dedup/coverage 计数由
    counts.numbers_backed 单独判定，不入本表。标识符字段内嵌数字不参与；
    区间端点保留（如 years:"2019-2024" 中的 2019/2024 仍逐端回证）。
    """
    out = []
    inner = res.get("result") if isinstance(res, dict) else {}
    if not isinstance(inner, dict):
        return out
    for i, p in enumerate(inner.get("papers") or []):
        if not isinstance(p, dict):
            continue
        for key, side in (("year", "paper"), ("relevance_score", "computed")):
            v = p.get(key)
            if is_num(v):
                out.append({"path": "papers[%d].%s" % (i, key), "value": v,
                            "side": side, "check": "papers[%d].numbers_backed" % i})
    # 过滤：数值落在标识符字段路径内的不参与（双保险；上文路径本身已排除标识符）
    return [f for f in out
            if not any(k in f["path"].lower() for k in IDENTIFIER_KEYS)]


def _dump(report, out_path):
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def analyze(res, case, ablate="none", case_state="enforced"):
    """核心校验逻辑（纯函数式，不写盘）。返回报告 dict，绝不抛异常。"""
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
    off_backing = ablate in ("backing", "all")
    off_dedup = ablate in ("dedup", "all")
    off_trace = ablate in ("trace", "all")

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

    # claims 证据库
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

    def backed_quotes(x):
        return any(v in q for v in num_variants(x) for q in quotes)

    def backed_texts(x):
        return any(v in t for v in num_variants(x) for t in texts)

    # 查询计划
    try:
        qp = inner.get("query_plan") or []
        add_check("query_plan.present", "须有多轮查询计划 query_plan", True, bool(qp))
        for i, q in enumerate(qp):
            if not isinstance(q, dict):
                problems.append("query_plan[%d] 非对象" % i)
                continue
            add_check("query_plan[%d].query" % i, "须写明查询串 query", True,
                      bool(str(q.get("query") or "").strip()))
            add_check("query_plan[%d].databases" % i, "须写明数据库组合 databases", True,
                      bool(q.get("databases")))
        if qp:
            add_check("query_plan.multi_round", "计划须 ≥2 轮（多轮规划）", True,
                      len({q.get("round") for q in qp if isinstance(q, dict)}) >= 2)
    except Exception as e:
        problems.append("查询计划校验异常: %s" % e)

    # 关键词扩展
    try:
        ke = inner.get("keyword_expansion") or []
        add_check("keyword_expansion.present", "须有关键词扩展 keyword_expansion", True,
                  bool(ke))
        for i, k in enumerate(ke):
            if not isinstance(k, dict):
                problems.append("keyword_expansion[%d] 非对象" % i)
                continue
            add_check("keyword_expansion[%d].kind" % i,
                      "kind ∈ variant/abbreviation/synonym/related_term/translation/"
                      "acronym_backform/synonym_expansion", True, k.get("kind") in EXP_KINDS)
            add_check("keyword_expansion[%d].basis" % i,
                      "扩展须带 source_basis（规则名或材料位置）", True,
                      bool(str(k.get("source_basis") or "").strip()))
    except Exception as e:
        problems.append("关键词扩展校验异常: %s" % e)

    # 查询执行记录
    try:
        qexec = inner.get("queries_executed") or []
        add_check("queries_executed.present", "须有查询执行记录 queries_executed", True,
                  bool(qexec))
        for i, q in enumerate(qexec):
            if not isinstance(q, dict):
                problems.append("queries_executed[%d] 非对象" % i)
                continue
            add_check("queries_executed[%d].status" % i,
                      "status ∈ executed/failed/skipped", True,
                      q.get("status") in QUERY_STATUS)
            if q.get("status") == "executed":
                add_check("queries_executed[%d].database" % i,
                          "executed 记录须写明 database", True,
                          bool(str(q.get("database") or "").strip()))
                if is_num(q.get("result_count")) and q.get("result_count") == 0:
                    gap_kinds = {str(g.get("kind")) for g in (inner.get("gaps") or [])
                                 if isinstance(g, dict)}
                    if not off_trace and "empty_result" not in gap_kinds:
                        add_check("queries_executed[%d].empty_gap" % i,
                                  "result_count=0 须登记 gaps(empty_result)", True, False,
                                  fatal=False)
                        warnings.append("queries_executed[%d] 空结果未登记 gaps" % i)
    except Exception as e:
        problems.append("查询执行校验异常: %s" % e)

    # 数据库使用状态
    try:
        for i, d in enumerate(inner.get("databases_used") or []):
            if isinstance(d, dict):
                add_check("databases_used[%d].status" % i,
                          "status ∈ accessible/rate_limited/unavailable/not_tried", True,
                          d.get("status") in DB_STATUS)
    except Exception as e:
        problems.append("数据库状态校验异常: %s" % e)

    # papers：追溯 + 去重 + 元数据
    papers = []
    try:
        papers = inner.get("papers") or []
        for i, p in enumerate(papers):
            if not isinstance(p, dict):
                problems.append("papers[%d] 非对象" % i)
                continue
            add_check("papers[%d].title" % i, "须有标题 title", True,
                      bool(str(p.get("title") or "").strip()))
            if off_trace:
                skip_check("papers[%d].trace" % i,
                           "来源可追溯：source_db + matched_queries + rationale 齐备",
                           "ablate=trace 已关闭追溯校验（仅用于增益对照）")
            else:
                ok = (bool(str(p.get("source_db") or "").strip())
                      and bool(p.get("matched_queries"))
                      and bool(str(p.get("rationale") or "").strip()))
                add_check("papers[%d].trace" % i,
                          "来源可追溯：source_db + matched_queries + rationale 齐备", True, ok)
            if is_num(p.get("year")) and off_backing:
                skip_check("papers[%d].numbers_backed" % i,
                           "year/relevance_score 须逐字回证（quote/text）",
                           "ablate=backing 已关闭逐字回证（仅用于增益对照）")
            elif is_num(p.get("year")):
                y_ok = backed_quotes(p.get("year"))
                s_ok = p.get("relevance_score") is None or backed_texts(p.get("relevance_score"))
                add_check("papers[%d].numbers_backed" % i,
                          "year 须在 quote / relevance_score 须在 claim text 回证", True,
                          y_ok and s_ok, fatal=False)
                if not y_ok:
                    unbacked.append("papers[%d].year=%r 无 quote 回证" % (i, p.get("year")))
                if p.get("relevance_score") is not None and not s_ok:
                    unbacked.append("papers[%d].relevance_score=%r 无 claim text 回证"
                                    % (i, p.get("relevance_score")))
            # 标题元数据回证（宽松：warning 级）
            if not off_backing and str(p.get("title") or "").strip():
                t_norm = norm(p.get("title"))
                if t_norm and not any(t_norm in q for q in quotes):
                    warnings.append("papers[%d].title 未出现在任何 quote 中（请补证据）" % i)
    except Exception as e:
        problems.append("文献登记校验异常: %s" % e)

    # 去重一致性
    try:
        dedup = inner.get("dedup") or {}
        add_check("dedup.present", "须有去重统计 dedup", True, bool(dedup))
        if not off_dedup:
            pid_index = {str(p.get("paper_id")): j for j, p in enumerate(papers)
                         if isinstance(p, dict) and p.get("paper_id")}
            marked = []
            for i, p in enumerate(papers):
                if not isinstance(p, dict):
                    continue
                dup = p.get("duplicate_of")
                if dup:
                    marked.append(i)
                    if str(dup) not in pid_index:
                        add_check("papers[%d].duplicate_of" % i,
                                  "duplicate_of 须指向存在的 paper_id", True, False)
                    elif str(dup) == str(p.get("paper_id")):
                        add_check("papers[%d].duplicate_of_self" % i,
                                  "duplicate_of 不得指向自身", True, False)
            # 正本不得也标重复
            for i, p in enumerate(papers):
                if isinstance(p, dict) and p.get("duplicate_of"):
                    can = pid_index.get(str(p.get("duplicate_of")))
                    if can is not None and papers[can].get("duplicate_of"):
                        add_check("papers[%d].canonical_chain" % i,
                                  "正本不得再标 duplicate_of（无链式重复）", True, False)
            if is_num(dedup.get("removed_duplicates")):
                add_check("dedup.removed_matches",
                          "removed_duplicates=%r 须等于实际标记数 %d"
                          % (dedup.get("removed_duplicates"), len(marked)), True,
                          dedup.get("removed_duplicates") == len(marked))
            total_raw = len(papers)
            if is_num(dedup.get("dedup_rate")) and total_raw:
                expect = round(dedup.get("removed_duplicates", 0) / total_raw, 6)
                add_check("dedup.rate_recompute", "dedup_rate 须复算成立（%s）" % expect, True,
                          abs(dedup.get("dedup_rate") - expect) < 1e-4)
        else:
            skip_check("dedup.consistency", "duplicate_of 指向有效性 + 统计复算",
                       "ablate=dedup 已关闭去重校验（仅用于增益对照）")
    except Exception as e:
        problems.append("去重校验异常: %s" % e)

    # 覆盖统计一致性
    try:
        cov = inner.get("coverage") or {}
        add_check("coverage.present", "须有覆盖统计 coverage", True, bool(cov))
        if not off_trace:
            traceable = sum(1 for p in papers if isinstance(p, dict)
                            and str(p.get("source_db") or "").strip()
                            and p.get("matched_queries")
                            and str(p.get("rationale") or "").strip())
            total_raw = len(papers)
            if is_num(cov.get("total_raw")):
                add_check("coverage.total_raw", "total_raw 须等于 papers 行数 %d" % total_raw,
                          True, cov.get("total_raw") == total_raw)
            if is_num(cov.get("traceable_items")):
                add_check("coverage.traceable", "traceable_items 须等于实际可追溯数 %d"
                          % traceable, True, cov.get("traceable_items") == traceable)
            if is_num(cov.get("traceability_ratio")) and total_raw:
                expect = round(traceable / total_raw, 6)
                add_check("coverage.ratio_recompute", "traceability_ratio 须复算成立（%s）"
                          % expect, True, abs(cov.get("traceability_ratio") - expect) < 1e-4)
            if not off_dedup and is_num(cov.get("total_unique")):
                uniq = sum(1 for p in papers if isinstance(p, dict) and not p.get("duplicate_of"))
                add_check("coverage.total_unique", "total_unique 须等于未标重复行数 %d" % uniq,
                          True, cov.get("total_unique") == uniq)
        else:
            skip_check("coverage.consistency", "覆盖统计与 papers 实际内容复算一致",
                       "ablate=trace 已关闭覆盖校验（仅用于增益对照）")
    except Exception as e:
        problems.append("覆盖统计校验异常: %s" % e)

    # 计数回证（dedup/coverage 统计数字须在 claim text 回证；本方计算侧）
    try:
        if off_backing:
            skip_check("counts.numbers_backed", "dedup/coverage 计数须在 claim text 回证",
                       "ablate=backing 已关闭逐字回证（仅用于增益对照）")
        else:
            miss = []
            for src, keys in ((inner.get("dedup") or {},
                               ("clusters_found", "removed_duplicates", "dedup_rate")),
                              (inner.get("coverage") or {},
                               ("total_raw", "total_unique", "traceable_items",
                                "traceability_ratio"))):
                for key in keys:
                    v = (src or {}).get(key)
                    if is_num(v) and not backed_texts(v):
                        miss.append("%s.%s=%r 无 claim text 回证" % (
                            "dedup" if src is inner.get("dedup") else "coverage", key, v))
                        unbacked.append("%s.%s=%r" % (
                            "dedup" if src is inner.get("dedup") else "coverage", key, v))
            add_check("counts.numbers_backed", "计数须回证（未回证 %d 处）" % len(miss),
                      True, not miss, fatal=False)
    except Exception as e:
        problems.append("计数回证校验异常: %s" % e)

    # 遗漏登记与结论分级
    try:
        gaps = inner.get("gaps") or []
        for i, g in enumerate(gaps):
            if isinstance(g, dict):
                add_check("gaps[%d].kind" % i,
                          "kind ∈ empty_result/conflict/missing_metadata/access_denied/"
                          "rate_limited/suspected_miss", True, g.get("kind") in GAP_KINDS)
                add_check("gaps[%d].description" % i, "须写明遗漏描述", True,
                          bool(str(g.get("description") or "").strip()))
        verdict = inner.get("verdict")
        add_check("verdict_enum", "∈ complete/partial/empty/cannot_verify", True,
                  verdict in VERDICTS)
        if verdict == "empty":
            add_check("verdict_empty", "verdict=empty 须 papers 为空且 gaps 非空", True,
                      not papers and bool(gaps))
        if verdict == "complete":
            ratio = (inner.get("coverage") or {}).get("traceability_ratio")
            add_check("verdict_complete", "verdict=complete 须 papers 非空且追溯率=1.0", True,
                      bool(papers) and ratio == 1.0)
        if verdict == "cannot_verify":
            add_check("verdict_cannot_verify", "cannot_verify 须有 material_gaps", True,
                      bool(inner.get("material_gaps") or []))
        if not papers and not gaps:
            problems.append("空检索必须登记遗漏（gaps 不得为空）")
    except Exception as e:
        problems.append("遗漏/结论校验异常: %s" % e)

    # 运行状态
    try:
        rs = inner.get("run_status") or {}
        add_check("run_status.present", "须有运行状态 run_status{state,reason}", True, bool(rs))
        if rs:
            add_check("run_status.state", "state ∈ success/partial/unable_to_determine/refused",
                      True, rs.get("state") in RUN_STATUS)
            add_check("run_status.reason", "须写明状态原因 reason", True,
                      bool(str(rs.get("reason") or "").strip()))
            if rs.get("state") in ("partial", "unable_to_determine", "refused"):
                add_check("run_status.takeover", "非成功状态须给出 manual_takeover", True,
                          bool(rs.get("manual_takeover")))
    except Exception as e:
        problems.append("运行状态校验异常: %s" % e)

    # 增益证据与效率计数
    try:
        ge = inner.get("gain_evidence")
        add_check("gain_evidence.present", "须有 gain_evidence（正常 vs 退化对照）", True,
                  ge is not None)
        if isinstance(ge, dict):
            if ge.get("available") is False:
                add_check("gain_evidence.available_false_reason",
                          "available=false 须写明原因 reason", True,
                          bool(str(ge.get("reason") or "").strip()))
            else:
                runs = ge.get("runs") or []
                modes = [str(r.get("mode")) for r in runs if isinstance(r, dict)]
                add_check("gain_evidence.runs", "runs 须含 normal 与至少一个退化臂", True,
                          "normal" in modes and len(modes) >= 2)
                add_check("gain_evidence.delta", "须有 delta_normal_minus_degraded", True,
                          isinstance(ge.get("delta_normal_minus_degraded"), dict)
                          and bool(ge.get("delta_normal_minus_degraded")))
                add_check("gain_evidence.mechanism_map", "须有机制→指标映射", True,
                          bool(ge.get("mechanism_to_metric_map")))
                add_check("gain_evidence.boundaries", "须写明边界 boundaries", True,
                          bool(ge.get("boundaries")))
                add_check("gain_evidence.failure_conditions", "须写明失效条件", True,
                          bool(ge.get("failure_conditions")))
        eff = inner.get("efficiency")
        add_check("efficiency.present", "须有 efficiency 效率计数", True, eff is not None)
        if isinstance(eff, dict):
            if eff.get("available") is False:
                add_check("efficiency.available_false_reason", "available=false 须写明原因",
                          True, bool(str(eff.get("reason") or "").strip()))
            else:
                add_check("efficiency.reproduce", "efficiency 须写明复现方式 reproduce", True,
                          bool(str(eff.get("reproduce") or "").strip()))
                add_check("efficiency.counters", "efficiency 须含自动采集计数", True,
                          eff.get("wall_clock_seconds_total") is not None
                          or eff.get("checker_runs") is not None)
    except Exception as e:
        problems.append("增益证据校验异常: %s" % e)

    # steps / claims 覆盖 / environment
    try:
        steps = inner.get("steps") or []
        add_check("steps.present", "须有步骤 steps[]", True, bool(steps))
        if steps:
            add_check("steps.has_command", "至少一条步骤给出可执行命令 command", True,
                      any(str(s.get("command") or "").strip() for s in steps
                          if isinstance(s, dict)))
    except Exception as e:
        problems.append("步骤校验异常: %s" % e)

    try:
        has_numbers = bool(numeric_fields(res))
        claims = res.get("claims") or []
        add_check("claims_coverage", "有可回证数字则 claims 非空", True,
                  not (has_numbers and not claims))
    except Exception as e:
        warnings.append("claims 检查异常: %s" % e)

    try:
        env = inner.get("environment") or {}
        add_check("environment.python_version",
                  "environment 须有 python_version（或 python）", True,
                  isinstance(env, dict) and bool(env.get("python_version") or env.get("python")))
    except Exception as e:
        problems.append("环境快照检查异常: %s" % e)

    # unbacked 汇总
    if off_backing:
        add_check("numbers_backed", "全部可回证数字有逐字回证（本次已关闭回证）", False, True,
                  note="ablate=backing 已关闭逐字回证（仅用于增益对照）")
    elif unbacked:
        add_check("numbers_backed",
                  "全部可回证数字有逐字回证（unbacked=%d）" % len(unbacked), True, False)
    else:
        add_check("numbers_backed", "全部可回证数字有逐字回证",
                  bool(numeric_fields(res)), True, fatal=False)

    counts = {"papers": len(papers),
              "query_plan": len(inner.get("query_plan") or []),
              "keyword_expansion": len(inner.get("keyword_expansion") or []),
              "queries_executed": len(inner.get("queries_executed") or []),
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
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/verify_check.json")
        ap.add_argument("--ablate", default="none", choices=sorted(ABLATE_MODES),
                        help="退化/基线模式；仅用于增益对照，不得用于交付自检")
        args = ap.parse_args()
    except SystemExit:  # argparse error 也退出码 0（题面硬约束）
        return 0
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

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
