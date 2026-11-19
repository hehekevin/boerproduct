#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（kbqa-cite 科研知识库问答）。

对 result.json 做四组机械校验（与题面机检点逐项对应）：
  A. 答案句-来源对齐（含无来源句识别）：answered/partial 的每个答案句必须有
     source_entry 且该条目真实存在；必须有非空 quote 且（条目正文在台账中时）
     quote 逐字出现在条目正文里（空白归一化后子串匹配）；answered/partial
     不得零句子；miss 状态句子的引用同样须对得上来源。
  B. 问题拆解覆盖：case.json 的每个问题都要出现在 result.questions 并完成拆解
     （≥1 个子问题）；每个子问题必须有对应 answers 条目；coverage 各计数与
     实际一致，ratio = answered/total_subquestions。
  C. 检索未命中登记：status=miss ⇒ miss_reason 非空且登记进 gaps（含
     missing_topic/needed_action）；status=partial ⇒ 至少 1 个带来源句子且
     显式声明缺口（gaps 或 miss_reason），不把未完成写成完成。
  D. claims 证据链回证：每个 answered/partial 答案句必须有 claim（source_id=
     句子来源条目、claim.text 含句子原文、claim.evidence.quote 含句子引文）；
     句子中的数字（≥2 位或含小数点）必须出现在来源条目正文中，否则记入
     unbacked_numbers 并判 FAIL。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；gain_evidence / efficiency 归 gain_probe.py，
knowledge_base / questions / answers / gaps 等业务键归 build_skeleton + Agent，
retrieval.json 只由 kb_index.py 写。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work [--out /app/work/verify_check.json] [--ablate all]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STATUS = ("answered", "partial", "miss")
CONF = ("high", "medium", "low")
VERDICTS = ("answered", "partially_answered", "not_answered", "cannot_verify")
GAP_KINDS = ("no_hit", "insufficient_evidence", "unreadable", "conflict",
             "permission", "empty_kb", "other")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（引用逐字回证的匹配口径；不折叠大小写，避免英文条目误配）。"""
    return re.sub(r"\s+", "", str(s or ""))


def extract_questions(case):
    """从 case.json 常见键提取问题清单（与 build_skeleton 同口径）。"""
    out = []
    if not isinstance(case, dict):
        return out
    for key in ("questions", "queries", "qa", "question_list", "tasks"):
        v = case.get(key)
        if isinstance(v, list) and v:
            for i, e in enumerate(v):
                if isinstance(e, dict):
                    qid = str(e.get("question_id") or e.get("qid") or e.get("id")
                              or "Q%d" % (i + 1))
                    q = str(e.get("question") or "")
                else:
                    qid, q = "Q%d" % (i + 1), str(e)
                out.append({"question_id": qid, "question": q})
            break
    return out


def manifest_contents(work_dir):
    """读条目内容台账 → {entry_id: content}；仅收录有正文条目。"""
    m = load_json(os.path.join(work_dir or ".", "entries.json")) or {}
    out = {}
    for e in (m.get("entries") or []):
        if isinstance(e, dict) and e.get("entry_id") and e.get("content"):
            out[str(e["entry_id"])] = str(e["content"])
    return out


def known_entry_ids(res):
    inner = (res or {}).get("result") or {}
    kb = inner.get("knowledge_base") or {}
    return {str(e.get("entry_id")) for e in (kb.get("entries") or [])
            if isinstance(e, dict) and e.get("entry_id")}


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


def sentence_violations(sent, entry_ids, contents):
    """单句对齐违规（独立实现，gain_probe 用作客观真值）。返回违规描述列表。"""
    bad = []
    src = str(sent.get("source_entry") or "").strip()
    if not src:
        bad.append("无来源句（source_entry 空）")
        return bad
    if src not in entry_ids:
        bad.append("来源条目不存在: %s" % src)
    quote = str(sent.get("quote") or "").strip()
    if not quote:
        bad.append("引文为空")
    elif src in contents and norm(quote) not in norm(contents[src]):
        bad.append("引文未回证到条目正文: %s" % src)
    return bad


def analyze(res, case, ablate="none", case_state="enforced",
            manifest_state="not_found", retrieval_state="not_found", contents=None):
    """纯函数式分析（不写盘）。contents = {entry_id: 正文}（由调用方从台账读入）。
    返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": [], "disabled_checks": [], "ablate": ablate}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    off = lambda g: ablate == "all" or g in str(ablate).split(",")
    for g in ("alignment", "coverage", "miss", "evidence"):
        if off(g):
            report["disabled_checks"].append(g)

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    answers = [a for a in (inner.get("answers") or []) if isinstance(a, dict)]
    questions = [q for q in (inner.get("questions") or []) if isinstance(q, dict)]
    gaps = [g for g in (inner.get("gaps") or []) if isinstance(g, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    cov = inner.get("coverage") or {}
    contents = contents or {}
    entry_ids = known_entry_ids(res) | set(contents.keys())

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "entries_manifest", "state": manifest_state,
                            "note": "" if manifest_state == "enforced" else "条目正文台账缺失，引用回证降级为 claims 链内回证"})
    report["gates"].append({"gate": "retrieval_index", "state": retrieval_state,
                            "note": "" if retrieval_state == "enforced" else "kb_index.py 检索报告缺失，下游不得宣称已跑检索"})

    # ---- 枚举合法性（始终开启） ----
    for i, a in enumerate(answers):
        aid = a.get("sub_id") or "answers[%d]" % i
        if a.get("status") not in STATUS:
            report["problems"].append("%s status 枚举非法: %r（须 answered/partial/miss）"
                                      % (aid, a.get("status")))
        if a.get("confidence") is not None and a.get("confidence") not in CONF:
            report["problems"].append("%s confidence 枚举非法: %r" % (aid, a.get("confidence")))
        for j, s in enumerate(a.get("sentences") or []):
            if isinstance(s, dict) and s.get("confidence") is not None \
                    and s.get("confidence") not in CONF:
                report["problems"].append("%s.sentences[%d] confidence 枚举非法: %r"
                                          % (aid, j, s.get("confidence")))

    # ---- A. 答案句-来源对齐 + 无来源句识别 ----
    n_align_bad = 0
    for i, a in enumerate(answers):
        aid = a.get("sub_id") or "answers[%d]" % i
        st = a.get("status")
        sents = [s for s in (a.get("sentences") or []) if isinstance(s, dict)]
        applied = not off("alignment")
        bad = []
        if applied and st in ("answered", "partial") and not sents:
            bad.append("status=%s 但答案句为空" % st)
        for j, s in enumerate(sents):
            bad.extend("sentences[%d]: %s" % (j, v)
                       for v in sentence_violations(s, entry_ids, contents))
        add("answers[%d].alignment" % i, "答案句-来源对齐（条目存在+引文回证正文）",
            applied, not bad)
        if applied:
            n_align_bad += len(bad)
            for b in bad:
                report["problems"].append("%s %s" % (aid, b))

    # ---- B. 问题拆解覆盖 ----
    case_qs = extract_questions(case)
    q_by_id = {str(q.get("question_id")): q for q in questions}
    n_cov_bad = 0
    for k, cq in enumerate(case_qs):
        q = q_by_id.get(str(cq["question_id"]))
        ok = q is not None and bool(q.get("subquestions"))
        add("questions[%d].decomposition" % k, "case 问题已拆解（≥1 子问题）",
            not off("coverage"), ok)
        if not off("coverage") and not ok:
            n_cov_bad += 1
            if q is None:
                report["problems"].append("case 问题 %s 未出现在 result.questions（拆解缺失）"
                                          % cq["question_id"])
            else:
                report["problems"].append("case 问题 %s 未拆解出任何子问题" % cq["question_id"])
    answered_ids = {str(a.get("sub_id")) for a in answers}
    uncovered = []
    for q in questions:
        for sq in (q.get("subquestions") or []):
            sid = str(sq.get("sub_id")) if isinstance(sq, dict) else str(sq)
            if sid and sid not in answered_ids:
                uncovered.append(sid)
    if not off("coverage") and uncovered:
        n_cov_bad += len(uncovered)
        report["problems"].append("%d 个子问题无 answers 条目（覆盖缺口）: %s"
                                  % (len(uncovered), uncovered[:8]))
    if cov and not off("coverage"):
        n_sub = sum(len(q.get("subquestions") or []) for q in questions)
        cnt = {"answered": sum(1 for a in answers if a.get("status") == "answered"),
               "partial": sum(1 for a in answers if a.get("status") == "partial"),
               "miss": sum(1 for a in answers if a.get("status") == "miss")}
        bad = []
        if isinstance(cov.get("total_questions"), int) and cov["total_questions"] != len(case_qs):
            bad.append("total_questions=%s 应为 %s" % (cov["total_questions"], len(case_qs)))
        if isinstance(cov.get("total_subquestions"), int) and cov["total_subquestions"] != n_sub:
            bad.append("total_subquestions=%s 应为 %s" % (cov["total_subquestions"], n_sub))
        if isinstance(cov.get("uncovered_subquestions"), int) \
                and cov["uncovered_subquestions"] != len(uncovered):
            bad.append("uncovered_subquestions=%s 应为 %s"
                       % (cov["uncovered_subquestions"], len(uncovered)))
        for st, v in cnt.items():
            if isinstance(cov.get(st), int) and cov[st] != v:
                bad.append("%s=%s 应为 %s" % (st, cov[st], v))
        if isinstance(cov.get("ratio"), (int, float)) and n_sub:
            exp = cnt["answered"] / float(n_sub)
            if abs(float(cov["ratio"]) - exp) > 0.01:
                bad.append("ratio=%s 应为 %.2f" % (cov["ratio"], exp))
        if bad:
            n_cov_bad += len(bad)
            report["problems"].append("coverage 汇总不一致: %s" % "; ".join(bad))
    add("coverage.consistency", "coverage 各计数与实际一致", not off("coverage"),
        not off("coverage") and n_cov_bad == 0)

    # ---- C. 检索未命中登记 ----
    n_miss_bad = 0
    for i, a in enumerate(answers):
        aid = a.get("sub_id") or "answers[%d]" % i
        st = a.get("status")
        if st == "miss":
            reg = [g for g in gaps if str(g.get("sub_id")) == aid]
            ok = bool(str(a.get("miss_reason") or "").strip()) and bool(reg) \
                and all(str(g.get("missing_topic") or "").strip()
                        and str(g.get("needed_action") or "").strip() for g in reg)
            add("answers[%d].miss_registered" % i,
                "miss ⇒ miss_reason + gaps 登记", not off("miss"), ok)
            if not off("miss") and not ok:
                n_miss_bad += 1
                report["problems"].append("%s 标 miss 但缺 miss_reason 或未登记 gaps"
                                          "（须含 missing_topic 与 needed_action）" % aid)
        if st == "partial":
            sents = [s for s in (a.get("sentences") or []) if isinstance(s, dict)]
            declared = bool(str(a.get("miss_reason") or "").strip()) or \
                any(str(g.get("sub_id")) == aid for g in gaps)
            ok = bool(sents) and declared
            add("answers[%d].partial_declared" % i,
                "partial ⇒ 有句子且显式声明缺口", not off("miss"), ok)
            if not off("miss") and not ok:
                n_miss_bad += 1
                report["problems"].append("%s 标 partial 但无句子或未声明缺口"
                                          "（不把未完成写成完成）" % aid)

    # ---- D. claims 证据链回证 ----
    n_evid_bad = 0
    for i, a in enumerate(answers):
        aid = a.get("sub_id") or "answers[%d]" % i
        st = a.get("status")
        if st not in ("answered", "partial"):
            continue
        bad = []
        for j, s in enumerate([s for s in (a.get("sentences") or [])
                               if isinstance(s, dict)]):
            text_n, quote_n = norm(s.get("text")), norm(s.get("quote"))
            src = str(s.get("source_entry") or "")
            hit = any(str(c.get("source_id")) == src
                      and (not text_n or text_n in norm(c.get("text")))
                      and any(quote_n and quote_n in norm(e.get("quote"))
                              for e in (c.get("evidence") or []) if isinstance(e, dict))
                      for c in claims)
            if not hit:
                bad.append("sentences[%d] 在 claims 证据链中无逐字回证" % j)
            content = contents.get(src)
            if content is not None:
                for tok in NUM_RE.findall(str(s.get("text") or "")):
                    if (len(tok) >= 2 or "." in tok) and norm(tok) not in norm(content):
                        report["unbacked_numbers"].append(
                            {"sentence": "%s.sentences[%d]" % (aid, j), "value": tok,
                             "reason": "数字未出现在来源条目正文（%s）" % src})
        add("answers[%d].claim_backed" % i, "答案句经 claims 逐字回证",
            not off("evidence"), not bad)
        if not off("evidence"):
            n_evid_bad += len(bad)
            for b in bad:
                report["problems"].append("%s %s" % (aid, b))

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps_field = inner.get("material_gaps") or []
    total_sub = sum(len(q.get("subquestions") or []) for q in questions)
    n_answered = sum(1 for a in answers if a.get("status") == "answered")
    n_miss = sum(1 for a in answers if a.get("status") == "miss")
    n_partial = sum(1 for a in answers if a.get("status") == "partial")
    if verdict == "cannot_verify" and not gaps_field:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "answered" and (n_answered != total_sub or n_miss or n_partial or uncovered):
        report["problems"].append("verdict=answered 但存在 miss/partial/未覆盖子问题")
    if verdict == "not_answered" and (n_answered or n_partial):
        report["problems"].append("verdict=not_answered 但存在 answered/partial 子问题")
    if verdict == "partially_answered" and n_answered == 0:
        report["problems"].append("verdict=partially_answered 但没有任何 answered 子问题")
    rs = inner.get("run_status") or {}
    if rs.get("state") not in ("success", "partial", "unable_to_determine", "refused"):
        report["problems"].append("run_status.state 枚举非法或缺失: %r" % rs.get("state"))
    if rs.get("state") in ("partial", "unable_to_determine", "refused") \
            and not str(rs.get("reason") or "").strip():
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
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）"
                                  % len(report["unbacked_numbers"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    report["violation_counts"] = {"alignment": n_align_bad, "coverage": n_cov_bad,
                                  "miss": n_miss_bad, "evidence": n_evid_bad}
    return report


def objective_violations(res, case, contents):
    """独立复算四类客观违规（与校验层检查分开实现，作为漏检真值）。
    返回 {alignment: [...], coverage: [...], miss: [...], evidence: [...]}。"""
    inner = (res or {}).get("result") or {}
    answers = [a for a in (inner.get("answers") or []) if isinstance(a, dict)]
    questions = [q for q in (inner.get("questions") or []) if isinstance(q, dict)]
    gaps = [g for g in (inner.get("gaps") or []) if isinstance(g, dict)]
    claims = [c for c in ((res or {}).get("claims") or []) if isinstance(c, dict)]
    entry_ids = known_entry_ids(res) | set((contents or {}).keys())
    cov = inner.get("coverage") or {}
    align, covv, miss, evid = [], [], [], []

    for i, a in enumerate(answers):
        aid = str(a.get("sub_id") or i)
        st = a.get("status")
        sents = [s for s in (a.get("sentences") or []) if isinstance(s, dict)]
        if st in ("answered", "partial") and not sents:
            align.append("%s 零句子" % aid)
        for j, s in enumerate(sents):
            for v in sentence_violations(s, entry_ids, contents or {}):
                align.append("%s.sentences[%d]: %s" % (aid, j, v))
        if st == "miss":
            reg = [g for g in gaps if str(g.get("sub_id")) == aid]
            if not str(a.get("miss_reason") or "").strip() or not reg \
                    or any(not str(g.get("missing_topic") or "").strip()
                           or not str(g.get("needed_action") or "").strip()
                           for g in reg):
                miss.append("%s 未登记" % aid)
        if st == "partial":
            declared = bool(str(a.get("miss_reason") or "").strip()) or \
                any(str(g.get("sub_id")) == aid for g in gaps)
            if not sents or not declared:
                miss.append("%s partial 未声明缺口" % aid)
        if st in ("answered", "partial"):
            for j, s in enumerate(sents):
                text_n, quote_n = norm(s.get("text")), norm(s.get("quote"))
                src = str(s.get("source_entry") or "")
                hit = any(str(c.get("source_id")) == src
                          and (not text_n or text_n in norm(c.get("text")))
                          and any(quote_n and quote_n in norm(e.get("quote"))
                                  for e in (c.get("evidence") or [])
                                  if isinstance(e, dict))
                          for c in claims)
                if not hit:
                    evid.append("%s.sentences[%d] 无 claims 回证" % (aid, j))

    case_qs = extract_questions(case)
    q_ids = {str(q.get("question_id")) for q in questions}
    for cq in case_qs:
        if str(cq["question_id"]) not in q_ids:
            covv.append("case 问题 %s 未拆解" % cq["question_id"])
    for q in questions:
        if not (q.get("subquestions") or []):
            covv.append("问题 %s 无子问题" % q.get("question_id"))
    answered_ids = {str(a.get("sub_id")) for a in answers}
    for q in questions:
        for sq in (q.get("subquestions") or []):
            sid = str(sq.get("sub_id")) if isinstance(sq, dict) else str(sq)
            if sid and sid not in answered_ids:
                covv.append("子问题 %s 无 answers" % sid)
    n_sub = sum(len(q.get("subquestions") or []) for q in questions)
    cnt = {"answered": sum(1 for a in answers if a.get("status") == "answered"),
           "partial": sum(1 for a in answers if a.get("status") == "partial"),
           "miss": sum(1 for a in answers if a.get("status") == "miss")}
    if isinstance(cov.get("answered"), int) and cov["answered"] != cnt["answered"]:
        covv.append("coverage.answered 不符")
    if isinstance(cov.get("miss"), int) and cov["miss"] != cnt["miss"]:
        covv.append("coverage.miss 不符")
    if n_sub and isinstance(cov.get("total_subquestions"), int) \
            and cov["total_subquestions"] != n_sub:
        covv.append("coverage.total_subquestions 不符")
    return {"alignment": align, "coverage": covv, "miss": miss, "evidence": evid}


def self_check_index(report):
    return {s["item"]: s for s in (report.get("self_check") or [])
            if isinstance(s, dict) and s.get("item")}


def caught(idx, key):
    e = idx.get(key)
    return bool(e and e.get("applied") and e.get("match") is False)


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ablate", default="none",
                        help="none | all | alignment,coverage,miss,evidence 子集")
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
    contents = manifest_contents(args.work_dir)
    manifest_state = "enforced" if contents else "not_found"
    retrieval_state = "enforced" if os.path.exists(
        os.path.join(args.work_dir or ".", "retrieval.json")) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state,
                     manifest_state=manifest_state, retrieval_state=retrieval_state,
                     contents=contents)
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
