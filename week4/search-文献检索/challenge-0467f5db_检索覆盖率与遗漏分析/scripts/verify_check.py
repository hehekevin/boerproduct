#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（cov-gap-audit）。

对 result.json 做四组机械校验（与题面四种失效方式逐项对应）：
  A. denominator 分母口径：覆盖率分子分母必须来自可核对的冻结参考集——
     reference_set.frozen=true、frozen_at 非空、denominator_basis 正确、
     total_reference/items/included/unavailable/hit/miss 逐项机械复算一致、
     coverage_rate=hit/included 复算相符；防"以结果定义分母"。
  B. attribution 遗漏登记完备：每条 miss 恰一条 miss_registry 登记，category
     枚举合法、attribution(query_id/field/source_db/reason) 完整且 query_id
     存在于查询清单；防"把没找到当作不相关"与"归因泛泛"。
  C. supplement 补检真实收益：new_hits 全为 miss、查询式不与原查询重复、
     effective 声称与实际一致（空转 FAIL）、post 覆盖率机械复算、残余遗漏
     有解释、stop_rule 非空；防"补检空转"。
  D. evidence 证据回证：每条 hit 有 rationale+evidence_quote+claims 逐字回证；
     coverage_rate/miss_rate/post_coverage_rate 数字须出现在 claim text/quote
     中（显式数字字符类定界，不用 \\b/isalpha——汉字 isalpha() 为 True 会误判
     边界；匹配前剥离 DOI 等标识符内嵌数字，年份区间端点保留）。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；coverage/hit_* 归 coverage_calc.py，miss_registry 归
miss_audit.py，supplementary 归 supp_check.py，gain_evidence/efficiency 归
gain_probe.py，其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--ledger /app/work/coverage_ledger.json] [--out /app/work/verify_check.json] \
        [--ablate all | denominator,attribution,supplement,evidence 子集] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REF_STATUS = ("included", "unavailable", "retracted", "pending")
HIT_STATUS = ("hit", "miss", None)
MATCHED_BY = ("identifier", "title", "manual", None)
CATEGORIES = ("synonym_gap", "field_narrow", "time_window", "source_gap",
              "identifier_anomaly", "other")
DOI_RE = re.compile(r"10\.\d{4,9}/\S+")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（空白全删后做子串匹配）。"""
    return re.sub(r"\s+", "", str(s or ""))


def num_variants(v):
    """覆盖率等数值的可回证字符串形态（0.6 / 0.6000 均可）。"""
    try:
        f = float(v)
    except Exception:
        return set()
    s4 = "%.4f" % f
    s = str(round(f, 4))
    return {s4, s, s.rstrip("0").rstrip(".") if "." in s else s}


def num_in_text(value, text):
    """显式字符类定界数字回证：不用 \\b（汉字 isalpha()=True，\\w 类边界会把
    '0.6学生' 判成无边界）；剥离 DOI 等标识符内嵌数字；年份区间端点保留。"""
    t = DOI_RE.sub(" ", str(text or ""))
    t = norm(t)
    for v in num_variants(value):
        if re.search(r"(?<![0-9.])" + re.escape(v) + r"(?![0-9])", t):
            return True
    return False


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
    for g in ("denominator", "attribution", "supplement", "evidence"):
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
    refset = inner.get("reference_set") if isinstance(inner.get("reference_set"), dict) else {}
    reg = [r for r in (inner.get("miss_registry") or []) if isinstance(r, dict)]
    supp = inner.get("supplementary") if isinstance(inner.get("supplementary"), dict) else {}
    cov = inner.get("coverage") if isinstance(inner.get("coverage"), dict) else {}
    queries = [q for q in (inner.get("queries") or []) if isinstance(q, dict)]
    qids = {str(q.get("query_id")) for q in queries if q.get("query_id")}
    qids |= {str(q.get("query_id")) for q in (case.get("queries") or []) if isinstance(q, dict) and q.get("query_id")}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "coverage_ledger", "state": ledger_state,
                            "note": "" if ledger_state == "enforced" else "coverage_ledger.json 台账缺失，下游不得宣称已核对"})
    cov_state = "enforced" if cov.get("coverage_rate") is not None else "not_found"
    report["gates"].append({"gate": "coverage_output", "state": cov_state,
                            "note": "" if cov_state == "enforced" else "coverage 未回填（coverage_calc.py 未跑），下游不得宣称已核对"})
    supp_state = "enforced" if supp.get("new_hits_total") is not None else "not_found"
    report["gates"].append({"gate": "supp_output", "state": supp_state,
                            "note": "" if supp_state == "enforced" else "supplementary 未回填（supp_check.py 未跑），下游不得宣称已核对"})

    # ---- 枚举合法性（始终开启） ----
    for i, it in enumerate(items):
        rid = it.get("ref_id") or "items[%d]" % i
        if it.get("ref_status") not in REF_STATUS:
            report["problems"].append("%s ref_status 枚举非法: %r（须 included/unavailable/retracted/pending）" % (rid, it.get("ref_status")))
        if it.get("hit_status") not in HIT_STATUS:
            report["problems"].append("%s hit_status 枚举非法: %r（须 hit/miss/null）" % (rid, it.get("hit_status")))
        if it.get("matched_by") not in MATCHED_BY:
            report["problems"].append("%s matched_by 枚举非法: %r" % (rid, it.get("matched_by")))

    included_n = sum(1 for it in items if it.get("ref_status") == "included")
    unavail_n = sum(1 for it in items if it.get("ref_status") in ("unavailable", "retracted"))
    hit_n = sum(1 for it in items if it.get("hit_status") == "hit")
    miss_n = sum(1 for it in items if it.get("hit_status") == "miss")
    judged_n = sum(1 for it in items if it.get("judged") is True)

    # ---- A. 分母口径（防以结果定义分母） ----
    if not off("denominator"):
        add("reference_set.frozen", "参考集冻结且 frozen_at 非空", True,
            refset.get("frozen") is True and bool(str(refset.get("frozen_at") or "").strip()))
        if refset.get("frozen") is not True:
            report["problems"].append("参考集未冻结（frozen≠true）：分母不可核对，不得宣称覆盖率")
        if not str(refset.get("frozen_at") or "").strip():
            report["problems"].append("reference_set.frozen_at 为空（冻结时间未记录）")
        add("coverage.basis", "denominator_basis=frozen_reference_set", True,
            cov.get("denominator_basis") == "frozen_reference_set")
        if cov.get("denominator_basis") not in ("frozen_reference_set", None):
            report["problems"].append("coverage.denominator_basis 非法: %r（分母必须来自冻结参考集）" % cov.get("denominator_basis"))
        add("coverage.total_reference", "total_reference == len(items)", True,
            cov.get("total_reference") == len(items))
        if cov.get("total_reference") != len(items):
            report["problems"].append("coverage.total_reference=%r 与实际条目数 %d 不符" % (cov.get("total_reference"), len(items)))
        add("coverage.included_unavailable", "included+unavailable == total", True,
            cov.get("included") == included_n and cov.get("unavailable") == unavail_n)
        if cov.get("included") != included_n or cov.get("unavailable") != unavail_n:
            report["problems"].append("coverage.included/unavailable 与实际条目不符（期望 %d/%d）" % (included_n, unavail_n))
        add("coverage.hit_miss", "hit+miss == included", True,
            cov.get("hit") == hit_n and cov.get("miss") == miss_n)
        if cov.get("hit") != hit_n or cov.get("miss") != miss_n:
            report["problems"].append("coverage.hit/miss 与实际条目不符（期望 %d/%d）" % (hit_n, miss_n))
        exp_rate = round(hit_n / included_n, 4) if included_n else None
        exp_miss = round(miss_n / included_n, 4) if included_n else None
        rate_ok = (cov.get("coverage_rate") == exp_rate) if exp_rate is not None \
            else (cov.get("coverage_rate") is None)
        add("coverage.rate_recompute", "coverage_rate = hit/included 机械复算", True, bool(rate_ok))
        if not rate_ok:
            report["problems"].append("coverage_rate 复算不符（期望 %s，实际 %s）" % (exp_rate, cov.get("coverage_rate")))
        if cov.get("miss_rate") != exp_miss:
            report["problems"].append("miss_rate 复算不符（期望 %s，实际 %s）" % (exp_miss, cov.get("miss_rate")))
        if exp_rate == 1.0 and miss_n > 0:
            report["problems"].append("coverage_rate=1.0 但存在 miss 条目（口径自相矛盾）")
        # 不可用记录：ref_status=unavailable/retracted 不得计入分母命中
        for it in items:
            if it.get("ref_status") in ("unavailable", "retracted") and it.get("hit_status") is not None:
                report["problems"].append("%s ref_status=%s 却有 hit_status=%r（不可用记录不入分母）"
                                          % (it.get("ref_id"), it.get("ref_status"), it.get("hit_status")))
            if it.get("ref_status") == "included" and it.get("hit_status") is None and it.get("judged") is True:
                report["problems"].append("%s included 但 hit_status 为空且声称已判定" % it.get("ref_id"))

    # ---- B. 遗漏登记完备（防"把没找到当作不相关"与归因泛泛） ----
    reg_by_id = {}
    for r in reg:
        reg_by_id.setdefault(str(r.get("ref_id")), []).append(r)
    for i, it in enumerate(items):
        rid = str(it.get("ref_id") or i)
        if it.get("hit_status") == "miss":
            entries = reg_by_id.get(rid) or []
            ok = len(entries) == 1
            if ok:
                e = entries[0]
                att = e.get("attribution") if isinstance(e.get("attribution"), dict) else {}
                ok = (e.get("category") in CATEGORIES
                      and all(str(att.get(k) or "").strip() for k in ("query_id", "field", "source_db", "reason"))
                      and str(att.get("query_id")) in qids
                      and bool(str(e.get("needed_action") or "").strip()))
            add("items[%d].miss_registered" % i, "miss ⇒ 恰一条登记且归因完整可回溯", not off("attribution"),
                (not off("attribution")) and ok)
            if not off("attribution"):
                if not entries:
                    report["problems"].append("%s hit_status=miss 但未登记进 miss_registry" % rid)
                elif len(entries) > 1:
                    report["problems"].append("%s 在 miss_registry 重复登记" % rid)
                elif not ok:
                    report["problems"].append("%s 遗漏登记不完整/归因泛泛（category、attribution.query_id/field/"
                                              "source_db/reason、query_id 存在性、needed_action 任一不满足）" % rid)
    for rid in reg_by_id:
        if not any(str(it.get("ref_id")) == rid and it.get("hit_status") == "miss" for it in items):
            report["problems"].append("%s 登记在 miss_registry 但并非 miss 条目（错登记）" % rid)

    # ---- C. 补检真实收益（防补检空转） ----
    if not off("supplement"):
        supp_q = [q for q in (supp.get("queries") or []) if isinstance(q, dict)]
        orig_norm = set()
        for q in queries:
            orig_norm.add(re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(q.get("query_string") or "").lower()))
        for q in (case.get("queries") or []) if isinstance(case, dict) else []:
            if isinstance(q, dict):
                orig_norm.add(re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(q.get("query_string") or "").lower()))
        miss_ids = {str(it.get("ref_id")) for it in items if it.get("hit_status") == "miss"}
        all_hits = []
        for q in supp_q:
            for h in (q.get("new_hits") or []):
                h = str(h)
                add("supplement.new_hits_valid", "new_hits ⊆ miss 条目", True, h in miss_ids)
                if h not in miss_ids:
                    report["problems"].append("补检 %s 的 new_hits 含非 miss 条目 %r" % (q.get("query_id"), h))
                all_hits.append(h)
            if re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(q.get("query_string") or "").lower()) in orig_norm:
                report["problems"].append("补检 %s query_string 与原查询实质相同（同义重跑空转）" % q.get("query_id"))
        distinct_new = len(set(all_hits))
        add("supplement.effective_consistency", "effective 声称与实际新增命中一致（空转 FAIL）", True,
            not (supp.get("effective") is True and distinct_new == 0))
        if supp.get("effective") is True and distinct_new == 0:
            report["problems"].append("补检空转：effective=true 但新增命中为 0，不得报告遗漏下降")
        if supp.get("new_hits_total") is not None and supp.get("new_hits_total") != distinct_new:
            report["problems"].append("supplementary.new_hits_total=%r 与复算 %d 不符" % (supp.get("new_hits_total"), distinct_new))
        included_n2 = included_n
        exp_post = round((hit_n + distinct_new) / included_n2, 4) if included_n2 else None
        add("supplement.post_rate", "post_coverage_rate = (hit+新增)/included 复算", True,
            supp.get("post_coverage_rate") == exp_post)
        if supp.get("post_coverage_rate") != exp_post:
            report["problems"].append("post_coverage_rate 复算不符（期望 %s，实际 %s）" % (exp_post, supp.get("post_coverage_rate")))
        for r in (supp.get("residual_misses") or []):
            if not isinstance(r, dict):
                continue
            rid = str(r.get("ref_id") or "")
            ok = rid in miss_ids and rid not in set(all_hits) and bool(str(r.get("explanation") or "").strip())
            add("supplement.residual_%s" % rid, "残余遗漏须是未补检命中的 miss 且有解释", True, ok)
            if not ok:
                report["problems"].append("残余遗漏 %r 非未补检命中的 miss 或缺 explanation" % rid)
        if supp.get("effective") is True and not str(supp.get("stop_rule") or "").strip():
            report["problems"].append("补检有效但 stop_rule 为空（何时停止补检未声明）")

    # ---- D. 证据回证 ----
    claim_idx = {}
    for c in claims:
        claim_idx.setdefault(str(c.get("source_id") or ""), []).append(c)
    for i, it in enumerate(items):
        rid = str(it.get("ref_id") or i)
        if it.get("hit_status") != "hit":
            continue
        if not off("evidence"):
            if not str(it.get("rationale") or "").strip():
                report["problems"].append("%s 命中但 rationale 为空（判定依据缺失）" % rid)
            if not str(it.get("evidence_quote") or "").strip():
                report["problems"].append("%s 命中但无证据（evidence_quote 空）" % rid)
            cl = claim_idx.get(rid) or []
            quote = norm(it.get("evidence_quote"))
            q_backed = any(quote and quote in norm(e.get("quote"))
                           for c in cl for e in (c.get("evidence") or [])) if quote else bool(cl)
            add("items[%d].evidence_backed" % i, "hit ⇒ claims 逐字回证", not off("evidence"),
                (not off("evidence")) and q_backed)
            if not q_backed:
                report["problems"].append("%s 的 evidence_quote 在 claims 证据链中无逐字回证" % rid)
        if it.get("hit_status") == "hit" and it.get("matched_by") == "manual":
            pass  # 人工裁决须在 rationale/evidence 中说明，enum 检查已放行

    # ---- 数字回证（防中文数值陷阱：显式字符类 + DOI 剥离 + 区间端点保留） ----
    if not off("evidence"):
        all_claim_text = " ".join(str(c.get("text") or "") for c in claims) + " " + \
                         " ".join(str(e.get("quote") or "") for c in claims for e in (c.get("evidence") or []))
        checks = [("coverage_rate", cov.get("coverage_rate")), ("miss_rate", cov.get("miss_rate")),
                  ("post_coverage_rate", supp.get("post_coverage_rate"))]
        for name, v in checks:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if not num_in_text(v, all_claim_text):
                    report["unbacked_numbers"].append(
                        {"item": "result.%s" % name, "value": str(round(float(v), 4)),
                         "reason": "数值未出现在任何 claim text/quote 中（显式字符类定界、DOI 内嵌数字已排除）"})

    # ---- 覆盖面汇总 + verdict 一致性（始终开启） ----
    if cov and cov.get("judged") is not None and cov.get("judged") != judged_n:
        report["problems"].append("coverage.judged=%r 与实际已判定条目 %d 不符" % (cov.get("judged"), judged_n))
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "covered_audited" and judged_n != len(items):
        report["problems"].append("verdict=covered_audited 但存在未判定条目（judged=false）")
    if verdict == "covered_audited" and miss_n > 0 and len(reg_by_id) < miss_n:
        report["problems"].append("verdict=covered_audited 但存在未登记遗漏")
    if verdict == "partially_audited" and judged_n == len(items) and items:
        report["problems"].append("verdict=partially_audited 但全部条目已判定（应为 covered_audited）")
    if verdict == "not_audited" and judged_n:
        report["problems"].append("verdict=not_audited 但存在已判定条目")
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
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）" % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--ledger", default="/app/work/coverage_ledger.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | denominator,attribution,supplement,evidence 子集")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_numbers/validator_verdict 回写 result.json")
        try:
            args = ap.parse_args()
        except SystemExit:
            print("[verify_check] 参数解析失败（argparse error，按契约退出码 0）")
            return 0
    except Exception as e:
        print("[verify_check] 参数初始化失败: %s" % e)
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
    ledger = load_json(args.ledger) if os.path.exists(args.ledger) else None
    ledger_state = "enforced" if isinstance(ledger, dict) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, ledger_state=ledger_state)
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
