#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_check.py — 业务校验器五组：mapping / recompute / boundary / log / conservation。
analyze() 纯函数不写盘，ablate 参数即机制开关（供 gain_probe 双跑复用）。
键归属：self_check / gates / unbacked_numbers / unbacked_evidence / validator_verdict 归本脚本。
退出码恒 0；判据是报告 verdict。
"""
import argparse, json, os, re, sys

MARKER = "sci-db-query-analyze-v1"
ABLATE_GROUPS = ["mapping", "recompute", "boundary", "log", "conservation"]
NUM_RE = re.compile(r"(?<![A-Za-z_])\d+(?:\.\d+)?")


def marker_hit():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md"), "r", encoding="utf-8") as f:
            return MARKER in f.read()
    except Exception:
        return False


def first_key(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def analyze(result, case, ablate=frozenset()):
    """返回 problems 列表；每条带 [组标签]。ablate 为关闭的检查组名集合。"""
    P = []
    off = set(ablate)
    r = result.get("result") or {}
    queries = r.get("queries") or []
    qrs = r.get("query_results") or []
    qs = r.get("query_scope") or {}
    questions = {q.get("question_id") for q in (qs.get("questions") or []) if isinstance(q, dict)}
    boundary = r.get("boundary_registry") or []
    logs = r.get("query_log") or []
    datasets = {}
    for ds in (first_key(case, ["datasets", "tables", "snapshots", "data", "sources"], []) if isinstance(case, dict) else []):
        if isinstance(ds, dict):
            datasets[first_key(ds, ["dataset_id", "id", "name", "table", "table_name"])] = ds

    def ds_columns(did):
        ds = datasets.get(did) or {}
        cols = first_key(ds, ["columns", "fields", "schema"]) or []
        rows = first_key(ds, ["rows", "records", "data", "samples"]) or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            cols = cols or list(rows[0].keys())
        return set(map(str, cols))

    # [mapping] 查询-问题映射与字段合法性
    if "mapping" not in off:
        seen_q = set()
        for q in queries:
            qid = q.get("query_id")
            if qid in seen_q:
                P.append("[mapping] 重复 query_id=%s" % qid)
            seen_q.add(qid)
            if not q.get("question_id"):
                P.append("[mapping] 查询 %s 缺 question_id，无法回溯到分析问题" % qid)
            elif questions and q.get("question_id") not in questions:
                P.append("[mapping] 查询 %s 的 question_id=%s 不在 query_scope.questions 中（悬空映射）" % (qid, q.get("question_id")))
            if not q.get("dataset_id"):
                P.append("[mapping] 查询 %s 缺 dataset_id" % qid)
            else:
                cols = ds_columns(q.get("dataset_id"))
                if cols:
                    for f in (q.get("filters") or []):
                        if str(f.get("column")) not in cols:
                            P.append("[mapping] 查询 %s 过滤列 %s 不在数据集 %s 实际字段中（张冠李戴）" % (qid, f.get("column"), q.get("dataset_id")))
                    for a_ in (q.get("aggregations") or []):
                        c = a_.get("column")
                        if c and c != "*" and str(c) not in cols:
                            P.append("[mapping] 查询 %s 聚合列 %s 不在数据集 %s 实际字段中" % (qid, c, q.get("dataset_id")))
                    for c in (q.get("group_by") or []):
                        if str(c) not in cols:
                            P.append("[mapping] 查询 %s 分组列 %s 不在数据集 %s 实际字段中" % (qid, c, q.get("dataset_id")))
        answered = set()
        for q in queries:
            if any(x.get("query_id") == q.get("query_id") and x.get("status") == "ok" for x in qrs):
                answered.add(q.get("question_id"))
        if questions and not answered:
            P.append("[mapping] 无任何查询成功映射到已登记问题（answered=0）")
        log_issued = {}
        for l in logs:
            if l.get("action") == "issued":
                log_issued[l.get("query_id")] = l.get("detail") or {}
        for q in queries:
            d0 = log_issued.get(q.get("query_id"))
            if d0 is not None:
                cur = {"dataset_id": q.get("dataset_id"), "filters": q.get("filters"),
                       "group_by": q.get("group_by"), "aggregations": q.get("aggregations")}
                if json.dumps(d0, sort_keys=True, ensure_ascii=False) != json.dumps(cur, sort_keys=True, ensure_ascii=False):
                    P.append("[mapping] 查询 %s 当前定义与 query_log.issued 记录不一致（执行后被改写/过滤条件遗漏）" % q.get("query_id"))
    # [recompute] 复算层存在且全过 + 独立抽查（不信任已有 checks，用 stat_recompute 的独立实现重算）
    if "recompute" not in off:
        rc = r.get("recompute") or {}
        if not rc.get("computed_by"):
            P.append("[recompute] recompute 段缺失或未由 stat_recompute.py 复算（无复算依据）")
        else:
            if rc.get("computed_by") != "stat_recompute.py":
                P.append("[recompute] recompute.computed_by=%s 非 stat_recompute.py" % rc.get("computed_by"))
            if queries and not (rc.get("checks") or []):
                P.append("[recompute] 存在 %d 条查询但 recompute.checks 为空：聚合数值无复算依据" % len(queries))
            for c in (rc.get("checks") or []):
                if not c.get("ok"):
                    P.append("[recompute] %s/%s 复算不一致: %s" % (c.get("query_id"), c.get("kind"), c.get("detail")))
        try:
            from stat_recompute import load_rows, refilter, recompute_agg, close as _close
        except ImportError:
            load_rows = None
        if load_rows is not None:
            qmap = {q.get("query_id"): q for q in queries}
            for x in qrs:
                if x.get("status") != "ok":
                    continue
                q = qmap.get(x.get("query_id")) or {}
                rows = load_rows(case, q.get("dataset_id"))
                if rows is None:
                    continue
                sel = refilter(rows, q.get("filters"))
                if len(sel) != x.get("row_count"):
                    P.append("[recompute] %s row_count 独立抽查不一致：重算=%d 报告=%s" % (x.get("query_id"), len(sel), x.get("row_count")))
                for alias, rep in (x.get("aggregates") or {}).items():
                    for a_ in (q.get("aggregations") or []):
                        if (a_.get("alias") or "%s(%s)" % (a_.get("fn"), a_.get("column"))) == alias:
                            v = recompute_agg(a_.get("fn"), a_.get("column"), sel)
                            if not _close(v, rep):
                                P.append("[recompute] %s 聚合 %s 独立抽查不一致：重算=%s 报告=%s" % (x.get("query_id"), alias, v, rep))
                            break
    # [boundary] 空结果与缺失值登记
    if "boundary" not in off:
        brefs = {b.get("ref") for b in boundary}
        for x in qrs:
            if x.get("empty") and x.get("query_id") not in brefs:
                P.append("[boundary] 空结果查询 %s 未登记 boundary_registry（静默丢弃）" % x.get("query_id"))
        if not boundary and qrs:
            P.append("[boundary] boundary_registry 为空：未见任何空结果/缺失值/边界条件登记记录")
        for q in queries:
            if not any(b.get("kind") == "missing_values" and str(b.get("ref", "")).startswith("%s#filter" % q.get("query_id")) for b in boundary):
                continue  # 无缺失不要求登记；缺失由 query_engine 自动登记
    # [log] 日志完整
    if "log" not in off:
        if not logs and queries:
            P.append("[log] query_log 为空：查询无留痕，不可复跑")
        seqs = [l.get("seq") for l in logs]
        if len(seqs) != len(set(seqs)):
            P.append("[log] query_log 存在重复 seq")
        for q in queries:
            acts = [l.get("action") for l in logs if l.get("query_id") == q.get("query_id")]
            if "issued" not in acts or "executed" not in acts:
                P.append("[log] 查询 %s 日志不完整（需 issued+executed，实得 %s）" % (q.get("query_id"), acts))
        for l in logs:
            if not l.get("ts"):
                P.append("[log] 日志 seq=%s 缺时间戳" % l.get("seq"))
    # [conservation] 分组守恒独立核对（与 stat_recompute 分开实现，抽查组计数和）
    if "conservation" not in off:
        for x in qrs:
            if x.get("groups"):
                gsum = sum(g.get("count", 0) for g in x["groups"])
                if gsum != x.get("row_count"):
                    P.append("[conservation] %s 组计数和=%d ≠ row_count=%s（行数膨胀/丢失）" % (x.get("query_id"), gsum, x.get("row_count")))
    # 结构检查（不受 ablate 影响）
    if not (r.get("steps") or []):
        P.append("[structure] steps 为空：无流程留痕")
    cov = r.get("coverage") or {}
    if qrs and cov.get("queries_total") != len(qrs):
        P.append("[structure] coverage.queries_total=%s 与 query_results 实际 %d 不符" % (cov.get("queries_total"), len(qrs)))
    verdict = result.get("verdict") if isinstance(result.get("verdict"), str) else (r.get("verdict"))
    n_ok = sum(1 for x in qrs if x.get("status") == "ok")
    if qrs and verdict == "not_appraised" and n_ok:
        P.append("[structure] verdict=not_appraised 但存在 %d 条成功查询，判定与进度矛盾" % n_ok)
    contract = first_key(case, ["output_contract"], []) if isinstance(case, dict) else []
    if isinstance(contract, dict):
        contract = list(contract.keys())
    for f in (contract or []):
        if f not in result:
            P.append("[contract] 缺 output_contract 字段: %s" % f)
    return P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--emit-into", action="store_true")
    a = ap.parse_args()
    report = {"script": "verify_check", "marker_hit": marker_hit(), "exit": 0, "verdict": "PASS", "problems": []}
    try:
        with open(a.result, "r", encoding="utf-8") as f:
            result = json.load(f)
        with open(a.case, "r", encoding="utf-8") as f:
            case = json.load(f)
        report["problems"] = analyze(result, case)
        report["verdict"] = "FAIL" if report["problems"] else "PASS"
        report["groups_checked"] = ABLATE_GROUPS
        if a.emit_into:
            r = result.setdefault("result", {})
            checks = [
                {"item": "query-question mapping backed", "template_value": "每条查询有 question_id 且列名在数据集中", "applied": True, "match": not any(p.startswith("[mapping]") for p in report["problems"])},
                {"item": "aggregate recompute consistent", "template_value": "recompute.checks 全 ok", "applied": True, "match": not any(p.startswith("[recompute]") for p in report["problems"])},
                {"item": "boundary registered", "template_value": "空结果必有登记", "applied": True, "match": not any(p.startswith("[boundary]") for p in report["problems"])},
                {"item": "query log complete", "template_value": "issued+executed+ts", "applied": True, "match": not any(p.startswith("[log]") for p in report["problems"])},
                {"item": "group conservation", "template_value": "组计数和=总行数", "applied": True, "match": not any(p.startswith("[conservation]") for p in report["problems"])},
            ]
            r["self_check"] = checks
            r["gates"] = [
                {"gate": "case_contract", "state": "enforced" if isinstance(case, dict) else "invalid", "note": "case.json loaded"},
                {"gate": "query_execution", "state": "enforced" if (r.get("query_results") or []) else "not_found", "note": "query_results written by query_engine.py"},
                {"gate": "recompute_output", "state": "enforced" if (r.get("recompute") or {}).get("computed_by") == "stat_recompute.py" else "not_found", "note": "recompute written by stat_recompute.py"},
            ]
            # unbacked_numbers：claims 中的数字无 recompute/守恒检查回证
            un = []
            all_checks = (r.get("recompute") or {}).get("checks") or []
            qids = {c.get("query_id") for c in all_checks}
            for c in (result.get("claims") or []):
                nums = NUM_RE.findall(str(c.get("text") or ""))
                if nums and c.get("source_id") not in qids:
                    un.append({"claim_id": c.get("claim_id"), "numbers": nums, "reason": "claim 含数值但该查询无复算检查回证"})
            result["unbacked_numbers"] = un
            # unbacked_evidence：claims 含 evidence 引文但逐字不在 case.json 文本中
            ue = []
            blob = json.dumps(case, ensure_ascii=False)
            for c in (result.get("claims") or []):
                for ev in (c.get("evidence") or []):
                    q = str(ev.get("quote") or "").strip()
                    if q and q not in blob:
                        ue.append({"claim_id": c.get("claim_id"), "quote": q[:60], "reason": "引文未在 case.json 逐字命中"})
            result["unbacked_evidence"] = ue
            result["validator_verdict"] = report["verdict"]
            with open(a.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        report["verdict"], report["error"] = "FAIL", str(e)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ("script", "exit", "verdict", "problems", "marker_hit")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
