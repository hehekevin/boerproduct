#!/usr/bin/env python3
"""verify_check.py — 多库联合检索业务校验器（merge-skill）。

机械复算 result.json：检索式合规（逐库适配、禁止机械复制）、raw_hits 来源链
（库—查询—原始响应）、去重划分完整性、事前去重策略声明一致性、相似度复算、
冲突登记完备性、覆盖矩阵一致性、数值逐字回证、结论分级约束。
--ablate 提供退化/基线模式（关闭归一/模糊匹配/冲突检测/全部），仅用于增益对照，
不得用于交付自检。任何异常均捕获降级，绝不崩溃。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|normalize|fuzzy|conflict|all]
退出码：恒为 0（PASS/FAIL 记录在报告 verdict 字段，失败不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dedup_core import (engine_partition, clamp_policy, norm_text, title_tokens,
                            jaccard, extract_hits_from_case, KEY_FIELDS)
except Exception as e:  # pragma: no cover
    print("[verify_check] 无法导入 dedup_core: %s" % e)
    def engine_partition(*a, **k):  # 兜底：引擎缺失时跳过复算
        return None

VERDICTS = {"merged", "partially_merged", "not_merged", "cannot_verify"}
ATTRIBUTION = {"db_unavailable", "syntax_mismatch", "dedup_ambiguity",
               "metadata_conflict", "coverage_gap"}
RUN_STATUS = {"success", "partial", "unable_to_determine", "refused"}
DB_STATUS = {"queried", "failed", "limited", "skipped"}
FAILURE_STAGES = {"connect", "auth", "rate_limit", "syntax", "parse"}
STATUS_ENUM = ("answered", "partial", "insufficient_evidence", "input_error")
ABLATE_MODES = {"none", "normalize", "fuzzy", "conflict", "all"}


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def num_variants(x):
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


def numeric_fields(res):
    """枚举可复算数值位：合并计数 / 相似度（computed，须 claim text 回证）、
    年份（paper，须 quote 回证）。供增益探针算"机器逐位判定占比"。"""
    out = []
    inner = res.get("result") if isinstance(res, dict) else {}
    if not isinstance(inner, dict):
        return out
    dm = inner.get("dedup_metrics") or {}
    for k in ("raw_hits_total", "merged_records_total", "duplicates_merged",
              "single_source_records"):
        if is_num(dm.get(k)):
            out.append({"path": "dedup_metrics.%s" % k, "value": dm.get(k),
                        "side": "computed", "check": "dedup_metrics.counts_backed"})
    for i, d in enumerate(inner.get("dedup_decisions") or []):
        if isinstance(d, dict) and d.get("method") == "title_fuzzy" and is_num(d.get("similarity")):
            out.append({"path": "dedup_decisions[%d].similarity" % i, "value": d.get("similarity"),
                        "side": "computed", "check": "dedup_decisions[%d].similarity_backed" % i})
    for i, m in enumerate(inner.get("merged_records") or []):
        if isinstance(m, dict) and is_num(m.get("year")):
            out.append({"path": "merged_records[%d].year" % i, "value": m.get("year"),
                        "side": "paper", "check": "merged_records[%d].year_backed" % i})
    return out


def _dump(report, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def analyze(res, case, ablate="none", case_state="enforced"):
    """核心校验逻辑（纯函数式）。绝不抛异常。"""
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
    inner = {}
    try:
        inner = res.get("result") if isinstance(res.get("result"), dict) else {}
        if not inner:
            problems.append("result 为空或非对象")
    except Exception:
        inner = {}
    off_conflict = ablate in ("conflict", "all")   # 冲突检测关闭 → 无法复算冲突登记
    off_backing = ablate == "all"                  # 全部关闭 → 回证检查跳过

    gates.append({"gate": "result_readable", "state": "enforced", "note": ""})
    if case_state == "enforced":
        gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
    else:
        gates.append({"gate": "case_contract", "state": case_state,
                      "note": "case.json 不可用，output_contract 校验跳过；下游不得宣称已核对"})
        warnings.append("case.json 不可用（%s），契约字段校验跳过" % case_state)

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

    def backed_by_quotes(x):
        return any(v in q for v in num_variants(x) for q in quotes)

    def backed_by_texts(x):
        return any(v in t for v in num_variants(x) for t in texts)

    # ---- 1. 事前去重策略声明（"容差事前声明"同构）----
    policy = {}
    try:
        policy = inner.get("dedup_policy") or {}
        add_check("dedup_policy.present", "须有跨库去重策略声明 dedup_policy", True, bool(policy))
        if policy:
            add_check("dedup_policy.threshold",
                      "title_similarity_threshold 须为 0-1 数值", True,
                      is_num(policy.get("title_similarity_threshold"))
                      and 0 <= float(policy["title_similarity_threshold"]) <= 1)
            add_check("dedup_policy.basis", "策略须写明依据 basis（事前声明，禁止事后调参）",
                      True, bool(str(policy.get("basis") or "").strip()))
            add_check("dedup_policy.declared_at", "策略须写明声明时点 declared_at", True,
                      bool(str(policy.get("declared_at") or "").strip()))
    except Exception as e:
        problems.append("去重策略校验异常: %s" % e)

    # ---- 2. 库注册表与检索式合规 ----
    dbs, query_ids_by_db = {}, {}
    try:
        dbs = {d.get("db_id"): d for d in (inner.get("databases") or [])
               if isinstance(d, dict) and d.get("db_id")}
        add_check("databases.present", "须有库注册表 databases[]", True, bool(dbs))
        for db_id, d in dbs.items():
            qary = d.get("queries") or []
            add_check("databases[%s].queries" % db_id, "每库须登记查询列表 queries[]",
                      True, bool(qary))
            qids = set()
            for qi, q in enumerate(qary):
                if not isinstance(q, dict):
                    continue
                qid = str(q.get("query_id") or "")
                qids.add(qid)
                add_check("databases[%s].queries[%d].adapted" % (db_id, qi),
                          "检索式须按该库语法适配（adapted_query 非空）", True,
                          bool(str(q.get("adapted_query") or "").strip()))
                if str(q.get("adapted_query") or "").strip() and str(q.get("original_query") or "").strip():
                    same = norm(q.get("adapted_query")) == norm(q.get("original_query"))
                    add_check("databases[%s].queries[%d].not_verbatim" % (db_id, qi),
                              "禁止把同一条查询机械复制到所有库（adapted≠original）",
                              True, not same)
                add_check("databases[%s].queries[%d].status_enum" % (db_id, qi),
                          "查询状态 ∈ queried/failed/limited/skipped", True,
                          q.get("status") in DB_STATUS)
                if q.get("status") == "failed":
                    add_check("databases[%s].queries[%d].failure_stage" % (db_id, qi),
                              "failed 须标 failure_stage", True, bool(q.get("failure_stage")))
                    add_check("databases[%s].queries[%d].failure_stage_enum" % (db_id, qi),
                              "failure_stage ∈ connect/auth/rate_limit/syntax/parse", True,
                              q.get("failure_stage") in FAILURE_STAGES)
                    add_check("databases[%s].queries[%d].failure_reason" % (db_id, qi),
                              "failed 须写明失败原因（失败降级：告知缺口而非静默）", True,
                              bool(str(q.get("failure_reason") or "").strip()))
            query_ids_by_db[db_id] = qids
    except Exception as e:
        problems.append("库注册表校验异常: %s" % e)

    # ---- 3. raw_hits 来源链（库—查询—原始响应）----
    try:
        hits = inner.get("raw_hits") or []
        add_check("raw_hits.present", "须有原始响应登记 raw_hits[]", True, bool(hits))
        ok_chain = 0
        for i, h in enumerate(hits):
            if not isinstance(h, dict):
                problems.append("raw_hits[%d] 非对象" % i)
                continue
            db_id, qid, ref = str(h.get("db_id") or ""), str(h.get("query_id") or ""), \
                str(h.get("raw_ref") or "")
            chain_ok = bool(db_id and qid and ref and db_id in dbs
                            and qid in query_ids_by_db.get(db_id, set()))
            if chain_ok:
                ok_chain += 1
            else:
                add_check("raw_hits[%d].trace" % i,
                          "每条原始命中须可追溯（db_id∈注册表 + query_id∈该库 queries + raw_ref）",
                          True, False)
        ratio = (ok_chain / len(hits)) if hits else None
    except Exception as e:
        problems.append("raw_hits 校验异常: %s" % e)
        hits, ratio = [], None

    # ---- 4. 划分完整性：每条 raw_hit 恰好归入一条合并记录 ----
    agent_groups = []
    try:
        mrecs = inner.get("merged_records") or []
        add_check("merged_records.present", "须有合并记录 merged_records[]", True, bool(mrecs))
        seen = {}
        for i, m in enumerate(mrecs):
            if not isinstance(m, dict):
                problems.append("merged_records[%d] 非对象" % i)
                continue
            srcs = [s.get("hit_id") for s in (m.get("sources") or [])
                    if isinstance(s, dict) and s.get("hit_id")]
            add_check("merged_records[%d].sources" % i, "每条合并记录须有非空 sources", True,
                      bool(srcs))
            for hid in srcs:
                if hid in seen:
                    problems.append("raw_hit %s 被重复归入多条记录（%s / %s）"
                                    % (hid, seen[hid], m.get("record_id")))
                seen[hid] = m.get("record_id")
            agent_groups.append((str(m.get("record_id")), set(srcs),
                                 bool(m.get("arbitration") == "manual")))
        hit_ids = {str(h.get("hit_id")) for h in hits if isinstance(h, dict)}
        orphans = [x for x in hit_ids if x not in seen]
        if orphans:
            problems.append("raw_hit 未归入任何合并记录: %s" % ", ".join(sorted(orphans)[:8]))
    except Exception as e:
        problems.append("合并记录校验异常: %s" % e)
        agent_groups = []

    # ---- 5. 引擎复算（任何模式都实跑，ablate 只改引擎参数 → 同一校验器双跑 FAIL 差）----
    eng = None
    partition_agree, partition_total = 0, 0
    try:
        if engine_partition is not None and hits:
            eng = engine_partition(hits, policy, ablate=ablate)
        if eng is None:
            skip_check("engine.recompute", "引擎复算（划分/相似度/冲突/覆盖）",
                       "引擎不可用或无 raw_hits，复算跳过；下游不得宣称已机械复核")
        else:
            eng_sets = [set(g) for g in eng["groups"]]
            for rid, s, manual in agent_groups:
                if manual:
                    warnings.append("记录 %s 标注人工仲裁 manual，机器不复算（保留仲裁入口）" % rid)
                    continue
                partition_total += 1
                if s in eng_sets:
                    partition_agree += 1
                else:
                    problems.append("合并记录 %s 的来源划分与引擎复算（ablate=%s）不一致（来源=%s）"
                                    % (rid, ablate, sorted(s)))
            if partition_total:
                add_check("engine.partition_match", "引擎划分须与合并记录一致", True,
                          partition_agree == partition_total)
            # 相似度复算（"容差复算"同构）
            rowmap = {r["hit_id"]: r for r in eng["rows"]}
            for i, d in enumerate(inner.get("dedup_decisions") or []):
                if not isinstance(d, dict) or d.get("method") != "title_fuzzy":
                    continue
                pair = d.get("pair") or []
                if len(pair) == 2 and all(p in rowmap for p in pair):
                    recomputed = jaccard(rowmap[pair[0]]["tokens"], rowmap[pair[1]]["tokens"])
                    claimed = d.get("similarity")
                    ok = is_num(claimed) and abs(float(claimed) - recomputed) <= 0.05
                    add_check("dedup_decisions[%d].similarity_recompute" % i,
                              "声称相似度 %s vs 复算 %.4f（±0.05）" % (claimed, recomputed),
                              True, ok)
            # 冲突登记完备性
            if off_conflict:
                skip_check("conflicts.registered", "引擎检出的字段冲突须全部登记",
                           "ablate=%s 已关闭冲突检测（仅用于增益对照）" % ablate)
            else:
                reg = {(str(c.get("record_id")), str(c.get("field")))
                       for c in (inner.get("conflicts") or []) if isinstance(c, dict)}
                missed = [c for c in eng["conflicts"]
                          if (c["record_id"], c["field"]) not in reg]
                add_check("conflicts.registered",
                          "引擎检出 %d 处字段冲突须全部登记（缺 %d）"
                          % (len(eng["conflicts"]), len(missed)), True, not missed)
                if missed:
                    warnings.append("未登记冲突样例: %s"
                                    % json.dumps(missed[0], ensure_ascii=False)[:120])
            # 覆盖矩阵一致性
            em = eng["coverage_matrix"]
            am = inner.get("coverage_matrix") or {}
            add_check("coverage_matrix.present", "须有覆盖矩阵 coverage_matrix", True, bool(am))
            mism = []
            for db, cells in em.items():
                acells = am.get(db) or {}
                for f, st in cells.items():
                    if str(acells.get(f) or "") != st:
                        mism.append("%s.%s 实际=%s 登记=%s" % (db, f, st, acells.get(f)))
            add_check("coverage_matrix.consistent",
                      "覆盖矩阵须与引擎复算一致（差异 %d 处）" % len(mism), True, not mism)
            if mism:
                warnings.append("矩阵差异样例: %s" % mism[0])
            # 合并计数一致性
            dm = inner.get("dedup_metrics") or {}
            em2 = eng["metrics"]
            for k in ("raw_hits_total", "merged_records_total", "duplicates_merged",
                      "single_source_records"):
                if k in dm and dm.get(k) != em2.get(k):
                    problems.append("dedup_metrics.%s=%r 与引擎复算 %r 不一致"
                                    % (k, dm.get(k), em2.get(k)))
    except Exception as e:
        problems.append("引擎复算异常: %s" % e)

    # ---- 6. 数值逐字回证 ----
    try:
        dm = inner.get("dedup_metrics") or {}
        counts = [dm.get(k) for k in ("raw_hits_total", "merged_records_total",
                                      "duplicates_merged", "single_source_records")
                  if is_num(dm.get(k))]
        if off_backing:
            skip_check("dedup_metrics.counts_backed", "合并计数须在 claim text 回证",
                       "ablate=all 已关闭回证（仅用于增益对照）")
        elif counts:
            ok = all(backed_by_texts(v) for v in counts)
            add_check("dedup_metrics.counts_backed", "合并计数须在 claim text 回证", True, ok,
                      fatal=False)
            if not ok:
                unbacked.append("dedup_metrics 计数 %s 无 claim text 回证" % counts)
        for i, d in enumerate(inner.get("dedup_decisions") or []):
            if isinstance(d, dict) and d.get("method") == "title_fuzzy" and is_num(d.get("similarity")):
                if off_backing:
                    skip_check("dedup_decisions[%d].similarity_backed" % i,
                               "相似度须在 claim text 回证", "ablate=all 已关闭回证")
                else:
                    ok = backed_by_texts(d.get("similarity"))
                    add_check("dedup_decisions[%d].similarity_backed" % i,
                              "相似度须在 claim text 回证", True, ok, fatal=False)
                    if not ok:
                        unbacked.append("dedup_decisions[%d].similarity=%r 无 claim text 回证"
                                        % (i, d.get("similarity")))
        for i, m in enumerate(inner.get("merged_records") or []):
            if isinstance(m, dict) and is_num(m.get("year")):
                if off_backing:
                    skip_check("merged_records[%d].year_backed" % i,
                               "年份须在来源响应 quote 回证", "ablate=all 已关闭回证")
                else:
                    ok = backed_by_quotes(m.get("year"))
                    add_check("merged_records[%d].year_backed" % i,
                              "年份须在来源响应 quote 回证", True, ok, fatal=False)
                    if not ok:
                        unbacked.append("merged_records[%d].year=%r 无 quote 回证"
                                        % (i, m.get("year")))
    except Exception as e:
        problems.append("数值回证检查异常: %s" % e)

    # ---- 7. 运行状态 / 结论分级 / 归因 ----
    try:
        attrs = inner.get("attributions") or []
        for i, a in enumerate(attrs):
            if isinstance(a, dict):
                add_check("attributions[%d].attribution" % i,
                          "∈ db_unavailable/syntax_mismatch/dedup_ambiguity/metadata_conflict/coverage_gap",
                          True, a.get("attribution") in ATTRIBUTION)
        verdict = inner.get("verdict")
        add_check("verdict_enum", "∈ merged/partially_merged/not_merged/cannot_verify",
                  True, verdict in VERDICTS)
        if verdict == "not_merged":
            add_check("verdict_attributions", "not_merged 须有 attributions", True, bool(attrs))
        if verdict == "cannot_verify":
            add_check("verdict_material_gaps", "cannot_verify 须有 material_gaps", True,
                      bool(inner.get("material_gaps") or []))
        rs = inner.get("run_status") or {}
        add_check("run_status.present", "须有运行状态 run_status{state,reason}", True, bool(rs))
        if rs:
            add_check("run_status.state", "state ∈ success/partial/unable_to_determine/refused",
                      True, rs.get("state") in RUN_STATUS)
            add_check("run_status.reason", "须写明状态原因", True,
                      bool(str(rs.get("reason") or "").strip()))
            if rs.get("state") in ("partial", "unable_to_determine", "refused"):
                add_check("run_status.takeover", "非成功状态须给出人工接管位置", True,
                          bool(rs.get("manual_takeover")))
    except Exception as e:
        problems.append("运行状态/结论校验异常: %s" % e)

    # ---- 8. 复现步骤 / 环境 / 增益证据 ----
    try:
        steps = inner.get("steps") or []
        add_check("steps.present", "须有可重跑步骤 steps[]", True, bool(steps))
        if steps:
            add_check("steps.has_command", "至少一条步骤给出可执行命令", True,
                      any(str(s.get("command") or "").strip() for s in steps
                          if isinstance(s, dict)))
        env = inner.get("environment") or {}
        add_check("environment.python_version", "environment 须有 python_version", True,
                  isinstance(env, dict) and bool(env.get("python_version") or env.get("python")))
        ge = inner.get("gain_evidence")
        add_check("gain_evidence.present", "须有 gain_evidence（正常 vs 退化对照）", True,
                  ge is not None)
        if isinstance(ge, dict):
            if ge.get("available") is False:
                add_check("gain_evidence.available_false_reason", "available=false 须写明原因",
                          True, bool(str(ge.get("reason") or "").strip()))
            else:
                modes = [str(r.get("mode")) for r in (ge.get("runs") or []) if isinstance(r, dict)]
                add_check("gain_evidence.runs", "runs 须含 normal 与 degraded 两遍实跑", True,
                          "normal" in modes and "degraded" in modes)
                add_check("gain_evidence.delta", "须有 delta_normal_minus_degraded", True,
                          isinstance(ge.get("delta_normal_minus_degraded"), dict)
                          and bool(ge.get("delta_normal_minus_degraded")))
                add_check("gain_evidence.mechanism_map", "须有机制→指标映射", True,
                          bool(ge.get("mechanism_to_metric_map")))
                add_check("gain_evidence.boundaries", "须写明边界", True,
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
                add_check("efficiency.reproduce", "efficiency 须写明复现方式", True,
                          bool(str(eff.get("reproduce") or "").strip()))
                add_check("efficiency.counters", "efficiency 须含自动采集计数", True,
                          eff.get("wall_clock_seconds_total") is not None
                          or eff.get("checker_runs") is not None)
    except Exception as e:
        problems.append("步骤/环境/增益校验异常: %s" % e)

    # ---- 9. claims 覆盖与 unbacked ----
    has_numbers = bool(numeric_fields(res))
    try:
        claims = res.get("claims") or []
        add_check("claims_coverage", "有可复算数字则 claims 非空", True,
                  not (has_numbers and not claims))
        if off_backing:
            add_check("numbers_backed", "全部可复算数字有逐字回证（本次已关闭回证）", False, True,
                      note="ablate=all 已关闭逐字回证（仅用于增益对照）")
        elif unbacked:
            add_check("numbers_backed", "全部可复算数字有逐字回证（unbacked=%d）" % len(unbacked),
                      True, False)
        else:
            add_check("numbers_backed", "全部可复算数字有逐字回证", bool(has_numbers), True,
                      fatal=False)
    except Exception as e:
        problems.append("claims 检查异常: %s" % e)

    counts = {"databases": len(dbs), "raw_hits": len(hits),
              "merged_records": len(agent_groups),
              "dedup_decisions": len(inner.get("dedup_decisions") or []),
              "conflicts_registered": len(inner.get("conflicts") or []),
              "claims": len(res.get("claims") or []),
              "steps": len(inner.get("steps") or []),
              "traceability_ratio": ratio,
              "partition_agree": partition_agree,
              "partition_total": partition_total,
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
                        help="退化/基线模式：关闭归一(normalize)/模糊匹配(fuzzy)/冲突检测(conflict)；"
                             "仅用于增益对照，不得用于交付自检")
        args = ap.parse_args()
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
