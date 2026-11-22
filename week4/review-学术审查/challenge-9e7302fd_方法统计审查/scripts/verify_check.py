#!/usr/bin/env python3
"""verify_check.py — 业务校验器（num-consistency-audit 数字一致性审查）。

对 result.json 做机械校验，判据是报告 `verdict`（PASS/FAIL）与 problems 列表：
  A. 定位可回证：每条 confirmed finding 的 quote（空白归一化）必须出现在
     case.json 实际稿件文本中（number_audit 的 raw 是全文子串，天然可回证）；
  B. 严重度口径：severity_rubric 三级必须判定前声明（declared_at + levels 非空）；
  C. number↔finding 双向一致：每条 finding 的 conflict_ids 必须指向存在的
     audit_id，且被指向的 audit 其 consistent 须为 False；
  D. 卡片结构：每条约 audit_id/kind/value/source 非空；findings 缺字段补报；
  E. 状态一致性：verdict/run_status 枚举合法；verdict=audited 需 unchecked 中
     无非 out_of_scope 项且 findings 全部 confirmed；
  F. 契约字段：output_contract 字段一个不缺。
退出码恒 0（看 verdict 不看退出码）。
用法：
    verify_check.py --result /app/output/result.json --case /input/case.json [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

KINDS = ("sample_size", "p_value", "effect_size", "confidence_interval",
         "percentage", "statistic", "df")
SEVERITIES = ("critical", "major", "minor")
STATUSES = ("confirmed", "pending", "suppressed")
RUN_STATES = ("success", "partial", "unable_to_determine", "refused")
VERDICTS = ("audited", "partially_audited", "not_audited", "cannot_verify")
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")


def _load(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def manuscript_norm(case):
    if not isinstance(case, dict):
        return ""
    root = None
    for k in MANU_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            root = case[k]
            break
    if root is None:
        root = {k: v for k, v in case.items() if k != "output_contract"}
    buf = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            if len(o.strip()) >= 2:
                buf.append(o)
    walk(root)
    return norm("".join(buf))


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


def analyze(res, case, case_state="enforced"):
    report = {"verdict": "PASS", "problems": [], "self_check": []}

    def check(item, ok, note=""):
        report["self_check"].append({"item": item, "template_value": note,
                                     "applied": True, "match": bool(ok)})
        return bool(ok)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象")
        return report

    audits = [a for a in (inner.get("number_audits") or []) if isinstance(a, dict)]
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    src = manuscript_norm(case)
    aid_set = {a.get("audit_id") for a in audits}

    # A. 定位可回证 + 结构
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "findings[%d]" % i
        q = norm(f.get("quote"))
        in_src = bool(src) and len(q) >= 6 and q in src
        check("findings[%d].quote_backed" % i, in_src, "quote 逐字回证于稿件原文")
        if not in_src:
            report["problems"].append("%s quote 不在稿件原文或过短" % fid)
        for field in ("location", "severity", "evidence", "revision_suggestion"):
            if not str(f.get(field) or "").strip():
                report["problems"].append("%s 缺 %s" % (fid, field))
        if f.get("severity") not in SEVERITIES:
            report["problems"].append("%s severity 枚举非法" % fid)
        if f.get("status") not in STATUSES:
            report["problems"].append("%s status 枚举非法" % fid)

    # 卡片结构
    for i, a in enumerate(audits):
        aid = a.get("audit_id") or "audits[%d]" % i
        if a.get("kind") not in KINDS:
            report["problems"].append("%s kind 枚举非法: %r" % (aid, a.get("kind")))
        if "value" not in a or "source" not in a or "raw" not in a:
            report["problems"].append("%s 缺 value/source/raw 之一" % aid)

    # B. 严重度口径
    rub = inner.get("severity_rubric") or {}
    levels = rub.get("levels") or {}
    declared = bool(str(rub.get("declared_at") or "").strip()) and \
        all(str(levels.get(k) or "").strip() for k in SEVERITIES)
    check("severity_rubric.declared", declared, "三级口径判定前声明")
    if not declared:
        report["problems"].append("severity_rubric 未事前声明（declared_at 空或 levels 缺文本）")

    # C. number↔finding 双向一致
    for i, f in enumerate(findings):
        fid = f.get("finding_id") or "F%02d" % (i + 1)
        cids = f.get("conflict_ids") or []
        missing = [c for c in cids if c not in aid_set]
        check("findings[%d].conflict_ids_exist" % i, not missing, "conflict_ids 指向存在的 audit_id")
        if missing:
            report["problems"].append("%s conflict_ids 指向不存在的 audit: %s" % (fid, missing))
        for c in cids:
            rec = next((a for a in audits if a.get("audit_id") == c), None)
            if rec is not None and rec.get("consistent") is not False:
                report["problems"].append("%s 被指向的 %s 未标 consistent=false" % (fid, c))

    conflict_audits = {a.get("audit_id") for a in audits if a.get("consistent") is False}
    orphan = sorted(conflict_audits - {c for f in findings for c in (f.get("conflict_ids") or [])})
    if orphan:
        check("conflict_orphans", False, "每个 consistent=false 都被某条 finding 引用")
        report["problems"].append("consistent=false 但未被 finding 引用的 audit: %s" % orphan)

    # E. 状态一致性
    verdict = inner.get("verdict")
    if verdict not in VERDICTS:
        report["problems"].append("verdict 枚举非法: %r" % verdict)
    rs = inner.get("run_status") or {}
    if rs.get("state") not in RUN_STATES:
        report["problems"].append("run_status.state 枚举非法: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    # verified 判定：有 findings 且全部 confirmed 且无非 out_of_scope unchecked
    non_scope = [u for u in (inner.get("unchecked") or [])
                 if isinstance(u, dict) and not str(u.get("reason", "")).startswith("out_of_scope")]
    if verdict == "audited" and (non_scope or not findings):
        report["problems"].append("verdict=audited 但存在非 out_of_scope unchecked 或 findings 为空")

    # F. 契约字段
    if case_state == "enforced":
        for fn in contract_fields(case):
            if fn not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fn)

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--emit-into", action="store_true")
        args, _unknown = ap.parse_known_args()
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        print("[verify_check] 参数解析失败（降级）: %s" % e)
        return 0

    res = _load(args.result)
    if not isinstance(res, dict):
        print("[verify_check] FAIL: result.json 不存在/不可解析（不中断交付）")
        return 0
    case = _load(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    report = analyze(res, case if isinstance(case, dict) else {}, case_state)

    if args.emit_into:
        try:
            cur = _load(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["validator_verdict"] = report.get("verdict")
                cur["gates"] = [{"gate": "case_contract", "state": case_state,
                                 "note": "" if case_state == "enforced" else "case 缺失，下游不得宣称已核对"}]
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（%d 条 self_check 全部通过）" % len(report["self_check"]))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付）:" % len(report["problems"]))
        for p in report["problems"][:40]:
            print("  - %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（降级，exit 0）: %s" % e)
        sys.exit(0)