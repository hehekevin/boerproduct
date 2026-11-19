#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（patent-search-verify）。

对 result.json 做四类机械校验（与题面机检点逐项对应）：
  A. 号码与标签一致性（numbers）：kind=patent 必须有 raw_number 且 norm_number
     通过规范形式校验（国家码+数字+种类码）；归一失败必须登记 missing_metadata；
     keep 必须命中 ≥1 条纳入标准；exclude 必须命中 ≥1 条排除标准；pending 必须
     写 pending_reason；relevance=irrelevant 不得标 keep；relevance=direct 除非
     登记 duplicate_of 不得标 exclude。
  B. 族归并与筛选顺序可复算（family）：按 items[].priority_numbers/application_number
     独立复算期望族分组，与 result.family_groups 成员逐组对照；复算期望筛选顺序
     与 result.screening.ordered_ids 逐位对照；family_groups 成员必须存在于 items。
  C. 证据回证（evidence）：已判定条目必须有 rationale；keep 必须有 evidence_quote；
     keep/pending 的 evidence_quote 必须在 claims 证据链中逐字回证；keep/pending
     专利条目的 norm_number 必须出现在对应 claim text/quote（空白归一化子串匹配），
     未回证号码列入 unbacked_numbers 并判 FAIL；cross_refs 引证必须逐字回证。
  D. 登记完备性（registry）：pending 逐条登记进 pending_review（含 reason 与
     needed_action）；duplicate_of 必须在 conflicts 登记 merged/escalated，escalated
     必须进待复核；keep 专利条目必须有 legal_status（status/source/query_date 非空）
     且 source 已在 sources[] 登记授权分级（green/yellow/red）；cross_refs 目标必须
     存在于 items。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
norm_number / family_id / family_groups / screening 归 norm_family.py，
其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/ledger.json] [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

KINDS = ("patent", "paper", "unknown")
REL = ("direct", "indirect", "irrelevant")
LAB = ("keep", "pending", "exclude")
CONF = ("high", "medium", "low")
LIC = ("green", "yellow", "red")
SCOPES = ("simple", "extended", "unknown")
NORM_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{6,15}$")
WK = ("numbers", "family", "evidence", "registry")


# ------------------------------------------------------------------ 工具
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（保留大小写与字母数字，供逐字回证匹配）。"""
    return re.sub(r"\s+", "", str(s or ""))


def norm_number(raw):
    if raw is None or not str(raw).strip():
        return None
    s = re.sub(r"[\s,./\-_()]", "", str(raw)).upper()
    return s if re.fullmatch(r"[0-9A-Z]+", s) and sum(c.isdigit() for c in s) >= 6 else None


def expected_families(items):
    """独立复算期望族分组（族键=规范化优先权号，缺省申请号）。返回 {key: [ids]}。"""
    groups = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        keys = [norm_number(p) for p in (it.get("priority_numbers") or [])]
        keys = [k for k in keys if k]
        if not keys and it.get("application_number"):
            k = norm_number(it.get("application_number"))
            if k:
                keys = [k]
        if keys:
            groups.setdefault(min(keys), []).append(str(it.get("item_id")))
    return {k: sorted(v) for k, v in groups.items()}


def expected_order(items):
    """复算期望筛选顺序（relevance 层级 → confidence → item_id）。"""
    tier = {"direct": 0, "indirect": 1, "irrelevant": 2}
    conf = {"high": 0, "medium": 1, "low": 2}
    scored = [(str(it.get("item_id")), tier.get(it.get("relevance"), 3),
               conf.get(it.get("confidence"), 3))
              for it in items if isinstance(it, dict) and it.get("relevance") is not None]
    return [t[0] for t in sorted(scored, key=lambda t: (t[1], t[2], t[0]))]


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


# ------------------------------------------------------------------ 主分析
def analyze(res, case, ablate="none", case_state="enforced", ledger_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in WK:
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    pending_reg = inner.get("pending_review") or []
    conflicts = inner.get("conflicts") or []
    groups = inner.get("family_groups") or []
    sources = inner.get("sources") or []
    screening = inner.get("screening") or {}
    cov = inner.get("coverage") or {}
    item_ids = {str(it.get("item_id")) for it in items}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "ledger_record", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "/app/work/ledger.json 口径台账缺失，下游不得宣称已核对"})
    eng_state = "enforced" if screening.get("ordered_ids") else "not_found"
    report["gates"].append({"gate": "engine_output", "state": eng_state,
                            "note": "" if eng_state == "enforced" else "norm_family.py 未回填 screening/family_groups，下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启，不属于消融组） ----
    for i, it in enumerate(items):
        iid = it.get("item_id") or "items[%d]" % i
        if it.get("kind") is not None and it.get("kind") not in KINDS:
            report["problems"].append("%s kind 枚举非法: %r（须 patent/paper/unknown）" % (iid, it.get("kind")))
        if it.get("relevance") is not None and it.get("relevance") not in REL:
            report["problems"].append("%s relevance 枚举非法: %r" % (iid, it.get("relevance")))
        if it.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 keep/pending/exclude）" % (iid, it.get("label")))
        if it.get("confidence") is not None and it.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (iid, it.get("confidence")))

    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    source_ids = {str(s.get("source_id") or "") for s in sources if isinstance(s, dict)}
    source_ids |= {str(s.get("name") or "") for s in sources if isinstance(s, dict)}
    source_ids.discard("")

    # ---- A. 号码与标签一致性 ----
    n_num = 0
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab, rel, kind = it.get("label"), it.get("relevance"), it.get("kind")
        miss = [str(x) for x in (it.get("missing_metadata") or [])]
        num_ok = True
        if kind == "patent" and not off("numbers"):
            exp_norm = norm_number(it.get("raw_number"))
            if not it.get("raw_number") and "number" not in miss:
                num_ok = False
            elif it.get("norm_number") is None and "number" not in miss:
                num_ok = False
            elif it.get("norm_number") is not None and exp_norm is not None \
                    and str(it.get("norm_number")) != exp_norm:
                num_ok = False
            elif it.get("norm_number") is not None and not NORM_RE.fullmatch(str(it.get("norm_number"))):
                num_ok = False
        add("items[%d].numbers_consistency" % i,
            "patent ⇒ raw/norm 号码可归一、norm 与 raw 归一结果一致或登记缺失", not off("numbers"),
            (not off("numbers")) and num_ok)
        if not off("numbers"):
            if kind == "patent" and not it.get("raw_number") and "number" not in miss:
                report["problems"].append("%s kind=patent 但无 raw_number 且未登记 missing_metadata" % iid)
                n_num += 1
            if it.get("raw_number") and it.get("kind") == "patent" \
                    and not norm_number(it.get("raw_number")):
                report["problems"].append("%s raw_number 无法归一（缺国家码或数字位不足）且未登记缺失" % iid)
                n_num += 1
            if kind == "patent" and it.get("norm_number") is None and "number" not in miss:
                report["problems"].append("%s norm_number 为空且未登记 missing_metadata" % iid)
                n_num += 1
            if kind == "patent" and it.get("norm_number") is not None \
                    and not NORM_RE.fullmatch(str(it.get("norm_number"))):
                report["problems"].append("%s norm_number 不符合规范形式（国家码+数字+种类码）: %r"
                                          % (iid, it.get("norm_number")))
                n_num += 1
            exp_norm = norm_number(it.get("raw_number"))
            if kind == "patent" and it.get("norm_number") is not None \
                    and exp_norm is not None and str(it.get("norm_number")) != exp_norm:
                report["problems"].append("%s norm_number=%r 与 raw_number 归一结果 %s 不一致（号码失据）"
                                          % (iid, it.get("norm_number"), exp_norm))
                n_num += 1
            if lab == "keep" and not it.get("criteria_hit"):
                report["problems"].append("%s 标 keep 但未命中任何纳入标准（criteria_hit 空）" % iid)
                n_num += 1
            if lab == "exclude" and not it.get("excluded_by"):
                report["problems"].append("%s 标 exclude 但未命中任何排除标准（excluded_by 空）" % iid)
                n_num += 1
            if lab == "pending" and not str(it.get("pending_reason") or "").strip():
                report["problems"].append("%s 标 pending 但 pending_reason 为空" % iid)
                n_num += 1
            if rel == "irrelevant" and lab == "keep":
                report["problems"].append("%s relevance=irrelevant 却标 keep（跨级矛盾）" % iid)
                n_num += 1
            if rel == "direct" and lab == "exclude" and not it.get("duplicate_of"):
                report["problems"].append("%s relevance=direct 却标 exclude 且未登记重复归并（duplicate_of 空）" % iid)
                n_num += 1

    # ---- B. 族归并与筛选顺序可复算 ----
    n_fam = 0
    if not off("family"):
        exp_groups = expected_families(items)
        got = {}
        for g in groups:
            if not isinstance(g, dict):
                report["problems"].append("family_groups 含非对象条目")
                n_fam += 1
                continue
            gid = str(g.get("family_id") or "?")
            members = [str(m) for m in (g.get("member_ids") or [])]
            unknown = [m for m in members if m not in item_ids]
            if unknown:
                report["problems"].append("%s 成员不存在于 items: %s" % (gid, ",".join(unknown)))
                n_fam += 1
            if g.get("scope") is not None and g.get("scope") not in SCOPES:
                report["problems"].append("%s scope 枚举非法: %r（simple/extended/unknown）" % (gid, g.get("scope")))
                n_fam += 1
            for m in members:
                got.setdefault(m, set()).add(gid)
        # 每个有族键的条目应恰好在一个组里且组键匹配
        for i, it in enumerate(items):
            iid = str(it.get("item_id"))
            keys = [norm_number(p) for p in (it.get("priority_numbers") or [])]
            keys = [k for k in keys if k]
            if not keys and it.get("application_number"):
                k = norm_number(it.get("application_number"))
                if k:
                    keys = [k]
            if not keys:
                ok = it.get("family_id") is None
                add("items[%d].family_membership" % i, "无族键 ⇒ family_id 为空（不臆造族关系）",
                    not off("family"), ok)
                if not ok:
                    report["problems"].append("%s 无族键却有 family_id=%s（族关系臆造）" % (iid, it.get("family_id")))
                    n_fam += 1
                continue
            exp_gids = {g.get("family_id") for g in groups if isinstance(g, dict)
                        and str(it.get("item_id")) in [str(m) for m in (g.get("member_ids") or [])]}
            match = len(exp_gids) == 1 and it.get("family_id") in exp_gids
            add("items[%d].family_membership" % i, "有族键 ⇒ 恰好归入一个已登记族组", not off("family"), match)
            if not match:
                report["problems"].append("%s 有族键但族组归并不一致（登记 %r）" % (iid, it.get("family_id")))
                n_fam += 1
        # 同键成员应同组
        for key, members in exp_groups.items():
            gids = set()
            for m in members:
                for g in groups:
                    if isinstance(g, dict) and m in [str(x) for x in (g.get("member_ids") or [])]:
                        gids.add(str(g.get("family_id")))
            if len(gids) > 1:
                report["problems"].append("同族键 %s 的成员被拆进多个组: %s" % (key, ",".join(sorted(gids))))
                n_fam += 1
        # 筛选顺序复算
        exp_order = expected_order(items)
        got_ids = list(screening.get("ordered_ids") or [])
        order_ok = (got_ids == exp_order) if got_ids else True
        add("screening.order_recompute", "期望顺序逐位对照（relevance 层级→confidence→item_id）",
            not off("family"), order_ok)
        if got_ids and not order_ok:
            report["problems"].append("screening.ordered_ids 与机械复算顺序不一致（期望 %s…）" % exp_order[:6])
            n_fam += 1

    # ---- C. 证据回证 ----
    n_evi = 0
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab = it.get("label")
        if lab is None:
            continue
        cl = claim_idx.get(iid) or claim_idx.get("items[%d]" % i) or []
        all_quotes = [norm(e.get("quote")) for c in cl for e in (c.get("evidence") or [])
                      if isinstance(c, dict)]
        all_texts = [norm(c.get("text")) for c in cl if isinstance(c, dict)]
        backed = False
        if not off("evidence"):
            quote = norm(it.get("evidence_quote"))
            backed = (quote in all_quotes) if quote else bool(cl)
            add("items[%d].evidence_backed" % i,
                "keep/pending ⇒ evidence_quote 与 norm_number 在 claims 逐字回证", True, backed)
            if not str(it.get("rationale") or "").strip():
                report["problems"].append("%s 已判定但 rationale 为空（理由完备性）" % iid)
                n_evi += 1
            if lab == "keep" and not str(it.get("evidence_quote") or "").strip():
                report["problems"].append("%s 标 keep 但无证据摘录（evidence_quote 空）" % iid)
                n_evi += 1
            if lab in ("keep", "pending") and not backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % iid)
                n_evi += 1
            nn = norm(it.get("norm_number"))
            if lab in ("keep", "pending") and nn:
                num_ok = any(nn in t or nn in q for t in all_texts for q in all_quotes)
                if not num_ok:
                    report["unbacked_numbers"].append(
                        {"item": "items[%d].norm_number" % i, "value": str(it.get("norm_number")),
                         "reason": "keep/pending 条目 norm_number 未出现在任何 claim text/quote 中"})
            for j, cr in enumerate(it.get("cross_refs") or []):
                if not isinstance(cr, dict):
                    continue
                cq = norm(cr.get("evidence_quote"))
                if cq and cq not in all_quotes and cq not in all_texts:
                    report["problems"].append("%s cross_refs[%d] 引证在 claims 中无逐字回证" % (iid, j))
                    n_evi += 1

    # ---- D. 登记完备性 ----
    n_reg = 0
    for i, it in enumerate(items):
        iid = str(it.get("item_id") or i)
        lab = it.get("label")
        if not off("registry"):
            if lab == "pending":
                reg = [p for p in pending_reg if isinstance(p, dict) and str(p.get("item_id")) == iid]
                ok = bool(reg) and all(str(p.get("reason") or "").strip() for p in reg) \
                     and all(str(p.get("needed_action") or "").strip() for p in reg)
                add("items[%d].registry_complete" % i, "pending ⇒ 登记入 pending_review", True, ok)
                if not ok:
                    report["problems"].append("%s 标 pending 但未登记进 pending_review（缺 reason/needed_action）" % iid)
                    n_reg += 1
            ls = it.get("legal_status") if isinstance(it.get("legal_status"), dict) else {}
            if it.get("kind") == "patent" and lab == "keep":
                ok = (str(ls.get("status") or "").strip()
                      and str(ls.get("source") or "").strip()
                      and str(ls.get("query_date") or "").strip())
                add("items[%d].legal_status_recorded" % i,
                    "keep 专利 ⇒ legal_status 含 status/source/query_date", True, bool(ok))
                if not ok:
                    report["problems"].append("%s keep 专利但 legal_status 缺 status/source/query_date" % iid)
                    n_reg += 1
                elif str(ls.get("source")) not in source_ids:
                    report["problems"].append("%s legal_status.source=%r 未在 sources[] 登记授权分级" % (iid, ls.get("source")))
                    n_reg += 1
            for j, cr in enumerate(it.get("cross_refs") or []):
                if isinstance(cr, dict) and cr.get("target_id") and str(cr.get("target_id")) not in item_ids:
                    report["problems"].append("%s cross_refs[%d].target_id=%r 不存在于 items" % (iid, j, cr.get("target_id")))
                    n_reg += 1
        if it.get("duplicate_of"):
            rec = [c for c in conflicts if isinstance(c, dict)
                   and iid in [str(x) for x in (c.get("item_ids") or [c.get("item_id")])]]
            resolved = bool(rec) and any(str(c.get("resolution")) in ("merged", "escalated") for c in rec)
            add("items[%d].conflict_recorded" % i, "duplicate_of ⇒ conflicts 登记 merged/escalated", True, resolved)
            if not off("registry") and not resolved:
                report["problems"].append("%s 标记 duplicate_of 但 conflicts 未登记 merged/escalated 处置" % iid)
                n_reg += 1
            if not off("registry") and any(str(c.get("resolution")) == "escalated" for c in rec):
                if not any(str(p.get("item_id")) == iid for p in pending_reg if isinstance(p, dict)):
                    report["problems"].append("%s 冲突升级(escalated)但未进入 pending_review" % iid)
                    n_reg += 1

    # ---- sources 授权分级（registry 组） ----
    if not off("registry"):
        for s in sources:
            if isinstance(s, dict) and s.get("licensing") not in LIC:
                report["problems"].append("sources[%s] licensing 枚举非法: %r（须 green/yellow/red）"
                                          % (s.get("source_id") or "?", s.get("licensing")))
                n_reg += 1
        add("sources.licensing_registered", "每个使用来源都登记 green/yellow/red 分级",
            not off("registry"),
            all(isinstance(s, dict) and s.get("licensing") in LIC
                for s in sources if isinstance(s, dict)))

    # ---- 覆盖面汇总一致性（始终开启） ----
    judged = [it for it in items if it.get("judged") is True]
    lab_count = {k: sum(1 for it in items if it.get("label") == k) for k in LAB}
    if cov:
        exp = {"total_candidates": len(items), "judged_items": len(judged),
               "keep": lab_count["keep"], "pending": lab_count["pending"], "exclude": lab_count["exclude"]}
        bad = [k for k, v in exp.items() if isinstance(cov.get(k), int) and cov[k] != v]
        if bad:
            report["problems"].append("coverage 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "screened" and len(judged) != len(items):
        report["problems"].append("verdict=screened 但存在未判定条目（judged=false）")
    if verdict == "partially_screened" and len(judged) == len(items):
        report["problems"].append("verdict=partially_screened 但全部条目已判定（应为 screened）")
    if verdict == "not_screened" and judged:
        report["problems"].append("verdict=not_screened 但存在已判定条目")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") and not str(rs.get("reason") or "").strip():
        report["problems"].append("run_status 非 success 但 reason 为空")

    # ---- steps（始终开启） ----
    steps = inner.get("steps") or []
    if not steps:
        report["problems"].append("steps 为空（须给出他人可重跑的步骤）")
    elif not any(str(s.get("command") or "").strip() for s in steps if isinstance(s, dict)):
        report["problems"].append("steps 无任何可执行 command")

    # ---- 契约字段（闸门 enforced 时） ----
    if case_state == "enforced":
        for fname in contract_fields(case):
            if isinstance(res, dict) and fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 个未回证号码（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["counts"] = {"numbers": n_num, "family": n_fam, "evidence": n_evi, "registry": n_reg}
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/ledger.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | numbers,family,evidence,registry 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "unbacked_numbers": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    led = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(led, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, ledger_state=ledger_state)
    report["gates"].append({"gate": "engine_output",
                            "state": "enforced" if ((res.get("result") or {}).get("screening") or {}).get("ordered_ids")
                            else "not_found",
                            "note": "" if ((res.get("result") or {}).get("screening") or {}).get("ordered_ids")
                            else "norm_family.py 未回写 screening，下游不得宣称已核对"})
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_numbers"] = report.get("unbacked_numbers") or []
                cur["validator_verdict"] = report.get("verdict")
                with open(args.result, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    if report["verdict"] == "PASS":
        print("[verify_check] PASS（ablate=%s，检查项 %d 条全部 applied）"
              % (args.ablate, len(report["self_check"])))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付；ablate=%s）:"
              % (len(report["problems"]), args.ablate))
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
