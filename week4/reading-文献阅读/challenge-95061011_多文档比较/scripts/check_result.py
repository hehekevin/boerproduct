#!/usr/bin/env python3
"""check_result.py — 多文档比较结果校验器（r5）。

r5 相对 r4：①按题面「Skill 运行后的输出要求」表逐项对齐校验（输入标识/主结果/
证据与边界/运行状态/不确定性/变更记录）；②新增 gain_evidence 增益取证块机检
（同输入三遍、指纹一致、逐项 delta、机制→指标映射、边界与失效条件）；
③新增 efficiency 效率计数块机检；④保留 r4 全部校验（覆盖/引文/pairwise 双引文/
冲突归因/混池/数字回证/gates 四态/verification 三元组）；⑤**所有失败路径 exit 0**
（verdict 照实写入 report 与 result.verification，禁止中断交付）。

退出码约定：任何路径恒为 0 —— 校验不通过、输入缺失、JSON 非法、命令行参数有误、
顶层异常，一律 exit 0；判定结果照实写入 report 的 ok/problems/verdict。
**不提供 --strict**：退出码不再是门禁信号，门禁语义由 report.verdict 承担，
避免「校验失败」被上游误读成「交付中断」。

用法：
    python3 check_result.py --result R.json [--workorder WO.json] [--case C.json]
                           [--out report.json] [--embed]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cli_guard import SafeParser, peek_option, run_entry, safe_parse_args  # noqa: E402

CELL_STATUS = {"reported", "not_reported", "not_comparable"}
VERDICTS = {"same", "partial", "different", "not_judged"}
GATE_STATES = {"enforced", "skipped_not_provided", "not_found", "unreadable"}
STATUS_VALUES = {"answered", "partial", "insufficient_evidence", "input_error"}
# 题面「Skill 运行后的输出要求」表 → 必须存在的顶层契约键
TASK_ALIGNED_TOP_KEYS = ["case_id", "status", "result", "claims", "uncertainties",
                         "sources", "changelog"]
# 「证据与边界」要求：未报告与不确定项必须分区落地
UNCERTAINTY_KEYS = ["unreported", "unverifiable", "unbacked", "conflicts",
                     "human_review", "summary"]
GAIN_METRICS = ["dimension_coverage", "agreement_rate", "conflicts_found",
                "manual_review_items", "steps", "followup_rounds"]


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def num_str(v):
    """数字转逐字字符串：312.5 -> '312.5'，120 -> '120'。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return "%g" % v
    if isinstance(v, str):
        return v.strip() if re.fullmatch(r"-?\d+(\.\d+)?", v.strip()) else None
    return None


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def parse_docs(wo):
    docs = []
    try:
        for d in (wo.get("documents") or wo.get("corpus") or []):
            if isinstance(d, dict):
                docs.append(str(d.get("source_document_id") or d.get("id")))
            else:
                docs.append(str(d))
    except Exception:
        pass
    return docs


def parse_fields(wo):
    fields = []
    try:
        for fdef in (wo.get("fields") or wo.get("comparison_fields") or []):
            if isinstance(fdef, dict):
                fields.append(str(fdef.get("field_id") or fdef.get("name")))
            else:
                fields.append(str(fdef))
    except Exception:
        pass
    return fields


def distinct_doc_ids(entries):
    ids = set()
    for e in entries or []:
        if isinstance(e, dict):
            sid = str(e.get("source_document_id") or "")
            if sid:
                ids.add(sid)
    return ids


def check_gain_evidence(inner, problems):
    """增益取证块机检：同输入三遍 + 逐项对照 + 机制映射 + 边界与失效条件。"""
    ge = inner.get("gain_evidence")
    if not isinstance(ge, dict):
        problems.append("result.gain_evidence 缺失或不是对象（使用增益需同输入对照证据）")
        return {}
    for k in ("input_fingerprint", "runs", "deltas", "mechanism_map", "boundary",
              "failure_conditions", "verdict"):
        if k not in ge:
            problems.append("gain_evidence 缺键: %s" % k)
    runs = ge.get("runs")
    if not isinstance(runs, list) or len(runs) < 2:
        problems.append("gain_evidence.runs 少于 2 遍（须含正常模式 + 至少一遍退化模式）")
        runs = []
    modes = []
    for i, r in enumerate(runs):
        if not isinstance(r, dict):
            problems.append("gain_evidence.runs[%d] 不是对象" % i)
            continue
        mode = str(r.get("mode") or "")
        modes.append(mode)
        if not r.get("label"):
            problems.append("gain_evidence.runs[%d] 缺 label 说明" % i)
        mets = r.get("metrics")
        if not isinstance(mets, dict):
            problems.append("gain_evidence.runs[%d] 缺 metrics" % i)
            continue
        for mk in GAIN_METRICS:
            if mk not in mets:
                problems.append("gain_evidence.runs[%d]（%s）metrics 缺指标: %s" % (i, mode, mk))
    if not any(m == "full" for m in modes):
        problems.append("gain_evidence.runs 缺 full（正常模式）对照遍")
    if not any(m != "full" for m in modes):
        problems.append("gain_evidence.runs 缺退化模式对照遍")
    fp = ge.get("input_fingerprint")
    if not isinstance(fp, dict):
        problems.append("gain_evidence.input_fingerprint 缺失或不是对象")
    else:
        if fp.get("same_input_across_runs") is not True:
            problems.append("gain_evidence.input_fingerprint.same_input_across_runs 非 true"
                            "（对照必须是同输入）")
        if not fp.get("matrix_sha256"):
            problems.append("gain_evidence.input_fingerprint 缺 matrix_sha256（同输入凭据）")
        if not fp.get("unique_variable"):
            problems.append("gain_evidence.input_fingerprint 缺 unique_variable（须写明唯一变量）")
    deltas = ge.get("deltas")
    if not isinstance(deltas, dict) or not deltas:
        problems.append("gain_evidence.deltas 缺失或为空（须逐项对照指标差值）")
    else:
        for mode, d in deltas.items():
            if not isinstance(d, dict):
                problems.append("gain_evidence.deltas[%s] 不是对象" % mode)
                continue
            for mk in GAIN_METRICS:
                if mk not in d:
                    problems.append("gain_evidence.deltas[%s] 缺逐项指标: %s" % (mode, mk))
    mm = ge.get("mechanism_map")
    if not isinstance(mm, list) or not mm:
        problems.append("gain_evidence.mechanism_map 缺失或为空（须写明机制→指标映射）")
    else:
        for i, row in enumerate(mm):
            if not isinstance(row, dict):
                problems.append("mechanism_map[%d] 不是对象" % i)
                continue
            for k in ("mechanism", "metric", "mapping_rule", "full_value", "ablate_value"):
                if k not in row:
                    problems.append("mechanism_map[%d] 缺键: %s" % (i, k))
    for key, name in (("boundary", "边界"), ("failure_conditions", "失效条件")):
        v = ge.get(key)
        if not isinstance(v, list) or not v:
            problems.append("gain_evidence.%s 缺失或为空（须写明%s与失效条件）" % (key, name))
    if not ge.get("verdict"):
        problems.append("gain_evidence.verdict 缺失（须照实记录对照结论）")
    if not ge.get("reproduce"):
        problems.append("gain_evidence.reproduce 缺失（须写明复现方式）")
    return ge


def check_efficiency(inner, problems):
    eff = inner.get("efficiency")
    if not isinstance(eff, dict):
        problems.append("result.efficiency 缺失或不是对象（效率计数须落盘）")
        return {}
    for k in ("collection_method", "reproduce", "counts"):
        if k not in eff:
            problems.append("efficiency 缺键: %s" % k)
    counts = eff.get("counts")
    if not isinstance(counts, dict):
        problems.append("efficiency.counts 缺失或不是对象")
    else:
        for k in ("matrix_cells", "pairwise_records", "comparison_rounds",
                  "conflict_records", "manual_review_items", "human_review_items",
                  "followup_rounds"):
            if k not in counts:
                problems.append("efficiency.counts 缺计数: %s" % k)
    if not eff.get("collection_method"):
        problems.append("efficiency.collection_method 为空（须说明采集口径）")
    if not eff.get("reproduce"):
        problems.append("efficiency.reproduce 为空（须说明复现方式）")
    return eff


def main() -> int:
    ap = SafeParser(description="多文档比较结果校验器（退出码恒 0，判定看 report.verdict）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--out", default="/app/output/check_report.json")
    ap.add_argument("--embed", action="store_true", help="把校验结论回填进 result.verification")
    args = safe_parse_args(ap)
    if args is None:
        # 命令行参数有误：判定照实落盘（verdict=fail），退出码恒 0
        out = peek_option(sys.argv[1:], "--out", "/app/output/check_report.json")
        _write_report({"ok": False, "verdict": "fail",
                       "problems": ["命令行参数有误，校验未执行（缺 --result 或参数名拼错）"]}, out)
        print("[check_result] FAIL: 命令行参数有误，判定已写入 %s" % out)
        return 0

    problems = []
    unbacked = []
    res = load_json(args.result)
    if res is None:
        problems.append("result.json 不存在或不是合法 JSON")
        _write_report({"ok": False, "verdict": "fail", "problems": problems}, args.out)
        print("[check_result] FAIL: %s" % problems[0])
        return 0

    # 1) 题面对齐：顶层契约键一个不缺
    for k in TASK_ALIGNED_TOP_KEYS:
        if k not in res:
            problems.append("缺少顶层契约字段: %s" % k)
    for k in ("status", "result", "claims", "uncertainties", "changelog"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)
    if res.get("status") not in STATUS_VALUES:
        problems.append("status 非法: %r（须为 %s 之一，诚实四级）" % (
            res.get("status"), "/".join(sorted(STATUS_VALUES))))
    if not (res.get("status_reason") or "").strip():
        problems.append("缺 status_reason（运行状态须附原因说明）")

    # 2) 证据与边界：未报告与不确定项分区落地
    unc = res.get("uncertainties")
    if isinstance(unc, dict):
        for k in UNCERTAINTY_KEYS:
            if k not in unc:
                problems.append("uncertainties 缺分区: %s" % k)
    else:
        problems.append("uncertainties 不是对象（须分区记录未报告/不可核验/未回证/冲突/人工复核）")

    # 3) 来源定位：sources 至少登记每篇语料的读取状态
    src = res.get("sources")
    if not isinstance(src, list) or not src:
        problems.append("sources 缺失或为空（须登记语料来源与读取状态）")
    else:
        for i, s in enumerate(src):
            if not isinstance(s, dict):
                problems.append("sources[%d] 不是对象" % i)
                continue
            if not (s.get("source_document_id") or "").strip():
                problems.append("sources[%d] 缺 source_document_id" % i)
            if not (s.get("read_status") or "").strip():
                problems.append("sources[%d] 缺 read_status（读取成功/部分/失败）" % i)

    # 4) output_contract 全键
    case = load_json(args.case) if args.case and os.path.exists(args.case) else None
    if case:
        for f in contract_fields(case):
            if f not in res:
                problems.append("缺少 output_contract 字段: %s" % f)

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}

    # 5) 工单覆盖：matrix 文档 × 字段全格
    wo = load_json(args.workorder) if args.workorder and os.path.exists(args.workorder) else None
    docs = parse_docs(wo) if wo else []
    fields = parse_fields(wo) if wo else []

    matrix = inner.get("matrix")
    if not isinstance(matrix, list):
        problems.append("result.matrix 缺失或不是数组")
        matrix = []

    got_cells = set()
    n_reported = n_notrep = n_notcomp = 0
    for i, c in enumerate(matrix):
        if not isinstance(c, dict):
            problems.append("matrix[%d] 不是对象" % i)
            continue
        fid = str(c.get("field_id"))
        doc = str(c.get("source_document_id"))
        got_cells.add((fid, doc))
        st = c.get("cell_status")
        if st not in CELL_STATUS:
            problems.append("[%s@%s] cell_status 非法: %r" % (fid, doc, st))
            continue
        if st == "reported":
            n_reported += 1
            if c.get("value") is None and not (c.get("text") or "").strip():
                problems.append("[%s@%s] reported 但无值" % (fid, doc))
            ev = c.get("evidence") or {}
            if not ev.get("source_document_id") or not ev.get("paragraph_id") or not (ev.get("quote") or "").strip():
                problems.append("[%s@%s] reported 格缺完整 evidence" % (fid, doc))
            ns = num_str(c.get("value"))
            if ns is not None and (ev.get("quote") or "").strip():
                if norm(ns) not in norm(ev.get("quote")):
                    unbacked.append({"field_id": fid, "source_document_id": doc,
                                     "value": c.get("value"), "quote": ev.get("quote")})
                    problems.append("[%s@%s] 数字回证失败: value=%r 未出现在 quote 中（unbacked）" % (
                        fid, doc, c.get("value")))
        elif st == "not_reported":
            n_notrep += 1
        elif st == "not_comparable":
            n_notcomp += 1
            if not (c.get("incomparable_reason") or "").strip():
                problems.append("[%s@%s] not_comparable 缺 incomparable_reason" % (fid, doc))

    for d in docs:
        for f in fields:
            if (f, d) not in got_cells:
                problems.append("缺格: field=%s doc=%s" % (f, d))

    # 6) pairwise：verdict 非 not_judged 必须有双方（不同文档）引文
    pairwise = inner.get("pairwise")
    if not isinstance(pairwise, list):
        problems.append("result.pairwise 缺失或不是数组（两两比较矩阵为核心产出）")
        pairwise = []
    n_pair_valid = 0
    for i, p in enumerate(pairwise):
        if not isinstance(p, dict):
            problems.append("pairwise[%d] 不是对象" % i)
            continue
        vd = p.get("verdict")
        if vd not in VERDICTS:
            problems.append("pairwise[%d] verdict 非法: %r" % (i, vd))
            continue
        if vd == "not_judged":
            if not (p.get("note") or "").strip():
                problems.append("pairwise[%d] not_judged 缺 note 说明原因" % i)
            continue
        ev = p.get("evidence") or []
        ids = distinct_doc_ids(ev)
        if len(ev) < 2:
            problems.append("pairwise[%d]（%s）verdict=%s 但 evidence 少于 2 条（须双方引文）" % (
                i, p.get("dimension"), vd))
        elif len(ids) < 2:
            problems.append("pairwise[%d]（%s）evidence 两方来自同一文档: %s" % (
                i, p.get("dimension"), sorted(ids)))
        else:
            n_pair_valid += 1

    # 7) 可比性
    comp = inner.get("comparability") or {}
    if comp:
        subset = comp.get("comparable_subset") or []
        if comp.get("pooled") and len(subset) < 2:
            problems.append("pooled=true 但可比子集不足 2 篇（混池风险）")

    # 8) 冲突：引文 ≥2 且来自不同文档
    conflicts = ((inner.get("synthesis") or {}).get("conflicts")) or []
    for i, cf in enumerate(conflicts):
        q = cf.get("quotes") or []
        ids = distinct_doc_ids(q)
        if len(q) < 2:
            problems.append("conflicts[%d] 引文少于 2（冲突双方须并列）" % i)
        elif len(ids) < 2:
            problems.append("conflicts[%d] 引文全部来自同一文档: %s" % (i, sorted(ids)))
        if not (cf.get("attribution") or "").strip():
            problems.append("conflicts[%d] 缺 attribution" % i)

    # 9) claims：每条至少 1 条带定位引文
    claims = res.get("claims")
    if not isinstance(claims, list):
        problems.append("claims 缺失或不是数组")
        claims = []
    for i, cl in enumerate(claims):
        if not isinstance(cl, dict):
            problems.append("claims[%d] 不是对象" % i)
            continue
        ev = cl.get("evidence") or []
        if not ev:
            problems.append("claims[%d] 缺 evidence" % i)
            continue
        ok_ev = all(
            isinstance(e, dict) and (e.get("paragraph_id") or e.get("location"))
            and (e.get("quote") or "").strip()
            for e in ev
        )
        if not ok_ev:
            problems.append("claims[%d] evidence 缺 paragraph_id/location 或 quote" % i)
        ids = distinct_doc_ids(ev)
        if len(ids) > 1 and len(ev) < 2:
            problems.append("claims[%d] 声明跨文档但引文不足 2 条" % i)

    n_conflicts = len(conflicts)

    # 10) coverage 统计块一致性
    cov = inner.get("coverage")
    if isinstance(cov, dict):
        if int(cov.get("cells") or 0) != len(matrix):
            problems.append("coverage.cells=%r 与实际 matrix 格数 %d 不符" % (cov.get("cells"), len(matrix)))
        if int(cov.get("reported") or 0) != n_reported:
            problems.append("coverage.reported=%r 与实际 %d 不符" % (cov.get("reported"), n_reported))
        if int(cov.get("pairwise_records") or 0) != len(pairwise):
            problems.append("coverage.pairwise_records=%r 与实际 %d 不符" % (
                cov.get("pairwise_records"), len(pairwise)))
        if int(cov.get("conflicts") or 0) != n_conflicts:
            problems.append("coverage.conflicts=%r 与实际 %d 不符" % (cov.get("conflicts"), n_conflicts))
        if int(cov.get("claims") or 0) != len(claims):
            problems.append("coverage.claims=%r 与实际 %d 不符" % (cov.get("claims"), len(claims)))

    # 11) gates 闸门状态机检：没跑 ≠ 通过
    gates = inner.get("gates")
    if not isinstance(gates, list) or not gates:
        problems.append("result.gates 缺失或为空（闸门状态必须显式枚举）")
    else:
        for i, g in enumerate(gates):
            if not isinstance(g, dict):
                problems.append("gates[%d] 不是对象" % i)
                continue
            st_g = g.get("state")
            if st_g not in GATE_STATES:
                problems.append("gates[%d]（%s）state 非法: %r（须为 %s）" % (
                    i, g.get("gate"), st_g, "/".join(sorted(GATE_STATES))))
            if st_g in ("skipped_not_provided", "not_found", "unreadable"):
                if not (g.get("gate_note") or "").strip():
                    problems.append("gates[%d]（%s）未 enforced 但缺 gate_note（须写明下游不得宣称已核对）" % (
                        i, g.get("gate")))

    # 12) gain_evidence 增益取证块
    ge = check_gain_evidence(inner, problems)

    # 13) efficiency 效率计数块
    eff = check_efficiency(inner, problems)

    # 14) 增益取证与效率计数的交叉一致性
    if ge and eff:
        ge_followup = None
        for r in ge.get("runs") or []:
            if isinstance(r, dict) and r.get("mode") == "full":
                m = r.get("metrics") or {}
                if isinstance(m.get("followup_rounds"), int):
                    ge_followup = m["followup_rounds"]
        ef_followup = ((eff.get("counts") or {}).get("followup_rounds"))
        if ge_followup is not None and isinstance(ef_followup, int) and ge_followup != ef_followup:
            problems.append("gain_evidence(full).followup_rounds=%r 与 efficiency.counts.followup_rounds=%r 不一致"
                            "（同公式两处须一致）" % (ge_followup, ef_followup))
        ef_cells = ((eff.get("counts") or {}).get("matrix_cells"))
        if isinstance(ef_cells, int) and int(cov.get("cells") or 0) != ef_cells:
            problems.append("efficiency.counts.matrix_cells=%r 与 coverage.cells=%r 不符" % (
                ef_cells, cov.get("cells")))

    # 结构性结论（不含 verification 自检）——用于回填三元组
    structural_problems = list(problems)

    report = {
        "ok": not problems,
        "verdict": "pass" if not problems else "fail",
        "problems": problems,
        "unbacked_numbers": unbacked,
        "cells": len(matrix),
        "docs": len(docs),
        "fields": len(fields),
        "reported": n_reported,
        "not_reported": n_notrep,
        "not_comparable": n_notcomp,
        "pairwise_records": len(pairwise),
        "pairwise_dual_evidence": n_pair_valid,
        "conflicts": n_conflicts,
        "claims": len(claims),
        "gain_evidence_runs": len(ge.get("runs") or []) if ge else 0,
        "gain_evidence_verdict": ge.get("verdict") if ge else None,
        "efficiency_counts": eff.get("counts") if eff else None,
    }

    # 15) verification 逐条 {item, template_value, applied, match}
    #     顺序要点：--embed 模式下先按结构性结论回填三元组，再校验 verification，
    #     避免「读到上一轮遗留的 match=false → 误判 FAIL」的自指循环。
    if args.embed:
        _embed(res, report, args.result, structural_problems)
    verif = inner.get("verification")
    verif_problems = []
    if not isinstance(verif, list) or not verif:
        verif_problems.append("result.verification 缺失或为空（逐条机检三元组必须嵌入）")
    else:
        for i, v in enumerate(verif):
            if not isinstance(v, dict):
                verif_problems.append("verification[%d] 不是对象" % i)
                continue
            for k in ("item", "template_value", "applied", "match"):
                if k not in v:
                    verif_problems.append("verification[%d] 缺键: %s" % (i, k))
            if v.get("applied") is not True:
                verif_problems.append("verification[%d]（%s）applied=false：校验未实际运行" % (i, v.get("item")))
            if v.get("match") is not True:
                verif_problems.append("verification[%d]（%s）match=false：自检未通过仍交付" % (i, v.get("item")))
    problems.extend(verif_problems)
    report["ok"] = not problems
    report["verdict"] = "pass" if not problems else "fail"
    report["problems"] = problems
    _write_report(report, args.out)

    if problems:
        print("[check_result] FAIL（%d 处，其中数字回证失败 %d 处）——判定已写入 report，交付不中断" % (
            len(problems), len(unbacked)))
        for p in problems[:50]:
            print("  - %s" % p)
        return 0
    print("[check_result] PASS（%d 格 = %d 文档 × %d 字段；reported %d / not_reported %d / not_comparable %d；"
          "pairwise %d 条（双引文 %d）；冲突 %d；claims %d；数字回证 %d 处全通过；"
          "gates/verification 机检通过；gain_evidence %d 遍（verdict=%s）；efficiency 已落盘）" % (
              len(matrix), len(docs), len(fields), n_reported, n_notrep, n_notcomp,
              len(pairwise), n_pair_valid, n_conflicts, len(claims),
              sum(1 for c in matrix if isinstance(c, dict) and c.get("cell_status") == "reported"
                  and num_str(c.get("value")) is not None),
              report["gain_evidence_runs"], report["gain_evidence_verdict"]))
    return 0


def _write_report(report, out):
    try:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _embed(res, report, result_path, structural_problems):
    """把校验结论写回 result.verification（逐条三元组，match 照实不粉饰）。

    只用结构性 problems（不含 verification 自身失败）重算 match，
    避免「上次 match=false → 本次又判 false」的自指循环。
    """
    try:
        inner = res.get("result") if isinstance(res.get("result"), dict) else None
        if inner is None:
            res["result"] = inner = {}
        verif = inner.get("verification")
        verif = verif if isinstance(verif, list) else []

        def failed(*needles):
            for p in structural_problems:
                s = str(p)
                if any(n in s for n in needles):
                    return True
            return False

        items = [
            ("coverage_cells", report.get("cells"), failed("coverage.cells")),
            ("coverage_pairwise_records", report.get("pairwise_records"),
             failed("coverage.pairwise_records")),
            ("coverage_conflicts", report.get("conflicts"), failed("coverage.conflicts")),
            ("coverage_claims", report.get("claims"), failed("coverage.claims")),
            ("pairwise_dual_evidence", report.get("pairwise_dual_evidence"),
             failed("evidence 少于 2", "同一文档")),
            ("unbacked_numbers", len(report.get("unbacked_numbers") or []),
             failed("数字回证失败")),
            ("gain_evidence_runs", report.get("gain_evidence_runs"), failed("gain_evidence")),
            ("efficiency_matrix_cells", (report.get("efficiency_counts") or {}).get("matrix_cells"),
             failed("efficiency")),
        ]
        by_item = {str(v.get("item")): v for v in verif if isinstance(v, dict)}
        for item, tv, bad in items:
            rec = by_item.get(item)
            if rec is None:
                rec = {"item": item}
                verif.append(rec)
                by_item[item] = rec
            rec["template_value"] = tv
            rec["applied"] = True
            rec["match"] = not bad
        inner["verification"] = verif
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    def _entry():
        try:
            main()
        except Exception as e:
            print("[check_result] 异常降级: %s" % e)
            try:
                _write_report({"ok": False, "verdict": "fail",
                               "problems": ["校验器异常降级: %s" % e]}, "/app/output/check_report.json")
            except Exception:
                pass

    run_entry(_entry, "check_result")
