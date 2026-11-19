#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（sci-code-exec / 科研代码生成与执行）。

对 result.json 做四组机械校验（与题面机检点逐项对应，问题串带标签前缀供
gain_probe 按组计数）：
  A. [coverage] 需求-代码覆盖映射：每条 requirement 必须有 coverage_map 条目且
     artifact_id 落在 code_artifacts 内；uncovered/partial 须登记 pending_review；
     partial 须写 note；code_artifacts 为空判 FAIL。
  B. [trace] 执行留痕完整：命令必须以 python3 开头；有命令的 step 必须有
     exit_code 与 log_ref；environment.python_version 非空；有命令步骤但
     execution_traces 为空（执行未留痕）判 FAIL。
  C. [anomaly] 异常登记与口径一致：handling∈dropped/imputed/clipped/filtered
     的 anomaly 其 rule_ref 必须在已声明 cleaning_rules 内；stats.rule_refs
     引用不存在的规则判 FAIL（防静默处理）。
  D. [recompute] 数值可复算：每条 stat 必须出现在 recompute.per_stat 且
     declared_value 与 stats 值一致；recompute.verdict≠PASS 判 FAIL；
     stat 数值在 claims 无回证 → unbacked_numbers 判 FAIL。

键归属（多脚本禁写同一键）：本脚本只写顶层 self_check / gates / unbacked_numbers /
unbacked_evidence / validator_verdict；execution_traces 归 run_trace.py；
recompute 归 recompute.py；gain_evidence / efficiency 归 gain_probe.py；
其余归 build_skeleton.py + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
防汉字陷阱：全程不做 .isalpha()/.isalnum() 判定，ID 校验一律用显式正则。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--rubric /app/work/cleaning_rules.json] [--out 报告路径] [--ablate none|all|组列表]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STATUS = ("answered", "partial", "insufficient_evidence", "input_error")
RUN_STATE = ("success", "partial", "unable_to_determine", "refused")
VERDICTS = ("completed", "partial_completed", "not_completed", "cannot_verify")
ANOM_KIND = ("missing", "outlier", "duplicate", "type_mismatch", "empty_query",
             "overflow", "other")
ANOM_HANDLING = ("dropped", "imputed", "clipped", "filtered", "flagged",
                 "passthrough", "failed", "not_present")
ACTIVES = ("dropped", "imputed", "clipped", "filtered")
COV_STATUS = ("covered", "partial", "uncovered")
STAT_TYPES = ("count", "count_missing", "mean", "sum", "min", "max",
              "group_mean", "group_count")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做 isalpha/isalnum——对汉字串不可靠；只折叠空白）。"""
    return re.sub(r"\s+", "", str(s or ""))


def id_ok(s):
    # 显式正则（\w 含 CJK），兼容 R1/CR-01/S01/AN-01 等编号；不用 isalpha
    return bool(re.match(r"^[\w]{1,8}(-?\d{1,3})?$", str(s or ""), re.UNICODE))


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


def rules_ok(rules):
    """校验 cleaning_rules 可机械执行：declared_at 已声明且 rules 非空、编号合法。"""
    if not isinstance(rules, dict):
        return None
    if not str(rules.get("declared_at") or "").strip():
        return None
    rs = rules.get("rules")
    if not isinstance(rs, list) or not rs:
        return None
    for r in rs:
        if not isinstance(r, dict) or not id_ok(r.get("rule_id")):
            return None
        if str(r.get("action") or "") not in ("dropna", "dedup", "filter", "clip", "impute"):
            return None
    return rules


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", rules_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "unbacked_evidence": [], "disabled_checks": [],
              "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match) if match is not None else True})
        return match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("coverage", "trace", "recompute", "anomaly"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("[structure] result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    reqs = [r for r in (inner.get("requirements") or []) if isinstance(r, dict)]
    cov_map = [c for c in (inner.get("coverage_map") or []) if isinstance(c, dict)]
    artifacts = [a for a in (inner.get("code_artifacts") or []) if isinstance(a, dict)]
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    traces = [t for t in (inner.get("execution_traces") or []) if isinstance(t, dict)]
    stats = [s for s in (inner.get("stats") or []) if isinstance(s, dict)]
    anomalies = [a for a in (inner.get("anomalies") or []) if isinstance(a, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = [p for p in (inner.get("pending_review") or []) if isinstance(p, dict)]
    crules = rules_ok(inner.get("cleaning_rules") or {})
    rule_ids = set()
    if crules:
        rule_ids = {str(r.get("rule_id")) for r in crules["rules"]}
    recompute = inner.get("recompute") if isinstance(inner.get("recompute"), dict) else {}
    per_stat = {str(p.get("stat_id")): p for p in (recompute.get("per_stat") or [])
                if isinstance(p, dict)}
    env = inner.get("environment") if isinstance(inner.get("environment"), dict) else {}
    cov = inner.get("coverage") if isinstance(inner.get("coverage"), dict) else {}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "rules_ledger", "state": rules_state if crules else "invalid",
                            "note": "" if crules else "/app/work/cleaning_rules.json 台账缺失或未声明 declared_at，下游不得宣称已核对"})
    rec_state = "enforced" if str(recompute.get("verdict") or "") in ("PASS", "FAIL", "UNABLE") and recompute.get("per_stat") is not None else "not_found"
    report["gates"].append({"gate": "recompute", "state": rec_state,
                            "note": "" if rec_state == "enforced" else "recompute.py 未回填（数值未独立复算），下游不得宣称已核对"})
    tr_state = "enforced" if traces else "not_found"
    report["gates"].append({"gate": "execution_traces", "state": tr_state,
                            "note": "" if tr_state == "enforced" else "execution_traces 为空（run_trace.py 未跑或未留痕），下游不得宣称已核对"})

    claim_norm = norm(" ".join([norm(c.get("text")) for c in claims] +
                               [norm(e.get("quote")) for c in claims
                                for e in (c.get("evidence") or [])]))

    def number_backed(v):
        s = str(v)
        return bool(s) and s in claim_norm

    # ---- 枚举合法性（始终开启） ----
    if res.get("status") is not None and res.get("status") not in STATUS:
        report["problems"].append("[enum] status 枚举非法: %r" % res.get("status"))
    rs = inner.get("run_status") or {}
    if rs.get("state") not in RUN_STATE:
        report["problems"].append("[enum] run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and \
            not str(rs.get("reason") or "").strip():
        report["problems"].append("[enum] run_status 非 success 但 reason 为空")
    verdict = inner.get("verdict")
    if verdict is not None and verdict not in VERDICTS:
        report["problems"].append("[enum] verdict 枚举非法: %r" % verdict)

    # ---- A. 需求-代码覆盖映射 ----
    art_ids = {str(a.get("artifact_id")) for a in artifacts}
    cov_by_req = {}
    for c in cov_map:
        cov_by_req.setdefault(str(c.get("req_id")), []).append(c)
    for i, r in enumerate(reqs):
        rid = str(r.get("req_id") or "R%d" % (i + 1))
        entries = cov_by_req.get(rid, [])
        ok = add("requirements[%s].mapped" % rid, "有 coverage_map 条目", not off("coverage"), bool(entries))
        if not off("coverage") and not ok:
            report["problems"].append("[coverage] 需求 %s 无 coverage_map 条目（需求-代码映射缺失）" % rid)
        for j, c in enumerate(entries):
            aid = str(c.get("artifact_id") or "")
            st_ = str(c.get("status") or "")
            if st_ not in COV_STATUS:
                report["problems"].append("[enum] coverage_map[%s].status 枚举非法: %r" % (rid, c.get("status")))
            if not off("coverage") and aid not in art_ids:
                report["problems"].append("[coverage] 需求 %s 映射的 artifact_id=%r 不在 code_artifacts（映射到不存在的代码）"
                                          % (rid, aid))
                add("requirements[%s].artifact_exists" % rid, "artifact_id 存在", not off("coverage"), False)
            if not off("coverage") and st_ == "partial" and not str(c.get("note") or "").strip():
                report["problems"].append("[coverage] 需求 %s 映射 status=partial 但 note 为空" % rid)
            if not off("coverage") and st_ in ("partial", "uncovered"):
                reg = [p for p in pending_reg if str(p.get("req_id")) == rid]
                if not reg or not all(str(p.get("reason") or "").strip() and
                                      str(p.get("needed_action") or "").strip() for p in reg):
                    report["problems"].append("[coverage] 需求 %s 状态=%s 但未登记 pending_review（缺 reason/needed_action）"
                                              % (rid, st_))
    if not off("coverage") and reqs and not artifacts:
        report["problems"].append("[coverage] code_artifacts 为空（没有任何代码产物，无法支撑覆盖映射）")

    # ---- B. 执行留痕完整 ----
    cmd_steps = [s for s in steps if str(s.get("command") or "").strip()]
    for i, s in enumerate(steps):
        cmd = str(s.get("command") or "").strip()
        if not cmd:
            continue
        if not cmd.startswith("python3"):
            report["problems"].append("[trace] steps[%d].command 未以 python3 开头: %r（命令一律 python3）" % (i, cmd))
        if not off("trace"):
            if s.get("exit_code") is None:
                report["problems"].append("[trace] steps[%d] 有命令但缺 exit_code（执行结果未记录）" % i)
            if not str(s.get("log_ref") or "").strip():
                report["problems"].append("[trace] steps[%d] 有命令但缺 log_ref（日志未留痕）" % i)
            add("steps[%d].trace_complete" % i, "exit_code + log_ref 齐备", not off("trace"),
                s.get("exit_code") is not None and bool(str(s.get("log_ref") or "").strip()))
    if not off("trace") and not env.get("python_version"):
        report["problems"].append("[trace] environment.python_version 为空（运行环境未记录）")
    if not off("trace") and cmd_steps and not traces:
        report["problems"].append("[trace] 有命令步骤但 execution_traces 为空（执行未留痕）")
    if not steps:
        report["problems"].append("[structure] steps 为空（须给出他人可重跑的步骤）")

    # ---- C. 异常登记与口径一致 ----
    for i, a in enumerate(anomalies):
        kind = str(a.get("kind") or "")
        handling = str(a.get("handling") or "")
        if kind not in ANOM_KIND:
            report["problems"].append("[enum] anomalies[%d].kind 枚举非法: %r" % (i, a.get("kind")))
        if handling not in ANOM_HANDLING:
            report["problems"].append("[enum] anomalies[%d].handling 枚举非法: %r" % (i, a.get("handling")))
        if not off("anomaly") and handling in ACTIVES:
            rr = str(a.get("rule_ref") or "")
            ok = bool(rr) and rr in rule_ids
            add("anomalies[%d].rule_backed" % i, "rule_ref 在已声明 cleaning_rules", not off("anomaly"), ok)
            if not ok:
                report["problems"].append("[anomaly] anomalies[%d] 处理方式=%s 但 rule_ref=%r 不在已声明 cleaning_rules（静默处理/口径漂移）"
                                          % (i, handling, rr))
    if not off("anomaly") and stats:
        for i, s in enumerate(stats):
            refs = [str(rr) for rr in (s.get("rule_refs") or [])]
            ok = all(rr in rule_ids for rr in refs)
            add("stats[%d].rules_declared" % i, "rule_refs 全部已声明", not off("anomaly"), ok)
            for rr in refs:
                if rr not in rule_ids:
                    report["problems"].append("[anomaly] stats[%d].rule_refs 引用不存在的规则: %r（口径漂移）" % (i, rr))
    if not off("anomaly") and crules is None:
        report["gates"][-1]["note"] = "cleaning_rules 未声明，异常处理与统计口径无从核对"

    # ---- D. 数值可复算 ----
    for i, s in enumerate(stats):
        sid = str(s.get("stat_id") or "stats[%d]" % i)
        if str(s.get("type") or "") not in STAT_TYPES:
            report["problems"].append("[enum] stats[%d].type 枚举非法: %r" % (i, s.get("type")))
        if not off("recompute"):
            p = per_stat.get(sid)
            ok = add("stats[%s].recomputed" % sid, "在 recompute.per_stat 且 declared 一致",
                     not off("recompute"), bool(p))
            if p is None:
                report["problems"].append("[recompute] stat %s 未被独立复算（recompute.per_stat 缺条目）" % sid)
            else:
                dv, rv = p.get("declared_value"), s.get("value")
                same = (dv == rv) or (isinstance(dv, (int, float)) and isinstance(rv, (int, float))
                                      and abs(float(dv) - float(rv)) <= 1e-9)
                if not same:
                    report["problems"].append("[recompute] stat %s declared_value=%r 与 stats.value=%r 不符"
                                              % (sid, dv, rv))
                if str(p.get("verdict")) == "MISMATCH":
                    report["problems"].append("[recompute] stat %s 独立复算不符（recompute.verdict=MISMATCH，须修代码重跑，不得改数凑数）" % sid)
        if not off("recompute") and s.get("value") is not None and not number_backed(s.get("value")):
            report["unbacked_numbers"].append({"item": "stats[%s].value" % sid,
                                               "value": str(s.get("value")),
                                               "reason": "stat 数值未出现在任何 claim text/evidence quote 中"})
    if not off("recompute") and stats and str(recompute.get("verdict")) == "FAIL":
        report["problems"].append("[recompute] recompute.verdict=FAIL（%d 条 mismatch）"
                                  % len(recompute.get("mismatches") or []))
    if not off("recompute") and not claims and stats:
        report["problems"].append("[evidence] claims 为空（每条 stat 数值须有可复核的回证条目）")

    # ---- verdict 一致性（始终开启） ----
    n_unc = sum(1 for c in cov_map if str(c.get("status")) in ("partial", "uncovered"))
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("[structure] verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "completed" and reqs and n_unc:
        report["problems"].append("[structure] verdict=completed 但存在 %d 条 partial/uncovered 需求" % n_unc)
    if verdict == "completed" and stats and str(recompute.get("verdict")) not in ("PASS",):
        report["problems"].append("[structure] verdict=completed 但 recompute.verdict=%r（数值未全部复算通过）"
                                  % recompute.get("verdict"))
    if verdict == "not_completed" and reqs and not n_unc:
        report["problems"].append("[structure] verdict=not_completed 但需求全部 covered")

    # ---- 覆盖面汇总（始终开启） ----
    if cov:
        exp = {"requirements_total": len(reqs),
               "covered": sum(1 for c in cov_map if str(c.get("status")) == "covered"),
               "stats_total": len(stats), "anomalies_registered": len(anomalies)}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("[structure] coverage 汇总与实际不符: %s" % bad)

    # ---- 契约字段 ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if fname not in res:
                report["problems"].append("[contract] 缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("[recompute] 存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    if report["unbacked_evidence"]:
        report["problems"].append("[recompute] 存在 %d 条不可回证证据（见 unbacked_evidence）" % len(report["unbacked_evidence"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--rubric", default="/app/work/cleaning_rules.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | coverage,trace,recompute,anomaly 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_*/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [], "gates": [],
                         "unbacked_numbers": [], "unbacked_evidence": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    rules = load_json(args.rubric) if os.path.exists(args.rubric) else None
    rules_state = "enforced" if (isinstance(rules, dict) and rules_ok(rules)) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, rules_state=rules_state)
    report["gates"].append({"gate": "recompute_output",
                            "state": "enforced" if (res.get("result") or {}).get("recompute", {}).get("verdict")
                            else "not_found",
                            "note": "" if (res.get("result") or {}).get("recompute", {}).get("verdict")
                            else "recompute.py 未回写 recompute，下游不得宣称已核对"})
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["unbacked_evidence"] = report.get("unbacked_evidence") or []
                cur["validator_verdict"] = report.get("verdict")
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（ablate=%s，检查项 %d 条）" % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:" % (len(report["problems"]), args.ablate))
        for p in report["problems"][:30]:
            print("  - %s" % p)
        if len(report["problems"]) > 30:
            print("  ... 共 %d 处" % len(report["problems"]))
    return 0


def _dump(out_path, report):
    if not out_path:
        return
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
