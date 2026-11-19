#!/usr/bin/env python3
"""verify_check.py — 中间产物校验与结论-证据对齐校验器（multi-step-analysis）。

五组机械校验（问题串带组标签，供 gain_probe 按标签统计捕获数）：
  1. [contract]  case_id 一致、output_contract 全字段存在、case.json 可读。
  2. [plan]      result.plan 已声明且 declared_at 非空，与 /app/work 台账一致；步骤
                 图无环、依赖引用完备（与 pipeline_run 分开独立复算，双实现互核）。
  3. [middle]    每个完成步骤有中间校验条目（kind ∈ schema|recompute）；
                 result.middle_checks 的 total/passed/failed/pass_rate 可由
                 steps[].checks 独立复算复现。
  4. [evidence]  claims 证据链：每条 claim 的 quote 逐字存在于 case.json 来源文本
                 或对应步骤产物；claim 正文中的数字须能在证据/步骤产物中回证，
                 否则进 unbacked_numbers / unbacked_evidence 判 FAIL。
  5. [fallback]  failed/degraded 步骤必须登记 result.fallbacks；skipped 步骤必须
                 登记 result.pending_review——失败降级不静默、不丢登记。

键归属纪律：本脚本只写 self_check / gates / unbacked_numbers / unbacked_evidence /
validator_verdict / middle_checks（复算回填）六个键；gain_evidence / efficiency 归
gain_probe.py，dag / trace_audit 归 pipeline_run.py。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        --plan /app/work/analysis_plan.json --out /app/work/verify_check.json --emit-into
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pipeline_run import topo_check, trace_audit, valid_step_id  # noqa: E402
except Exception as e:  # pragma: no cover
    print("[verify_check] 无法导入 pipeline_run: %s" % e)
    sys.exit(0)

NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])\d+(?:\.\d+)?(?![A-Za-z0-9_.])")
STATUS_VALUES = ("answered", "partial", "insufficient_evidence", "input_error")
RUN_STATES = ("success", "partial", "unable_to_determine", "refused")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[verify_check] 写盘失败 %s: %s" % (path, e))
        return False


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
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


def case_text_blob(case):
    """把 case.json 的文本内容压成规范化串，供引文存在性比对。"""
    try:
        return norm(json.dumps(case, ensure_ascii=False))
    except Exception:
        return ""


def recompute_middle(steps):
    total = passed = 0
    kinds_bad = []
    for s in steps:
        for c in (s.get("checks") or []):
            if not isinstance(c, dict):
                kinds_bad.append("%s 校验条目非对象" % s.get("step_id"))
                continue
            total += 1
            if c.get("passed") is True:
                passed += 1
            if str(c.get("kind") or "") not in ("schema", "recompute"):
                kinds_bad.append("%s/%s kind 非法: %r" % (s.get("step_id"), c.get("check_id"), c.get("kind")))
    failed = total - passed
    rate = round(passed / total, 4) if total else None
    return {"total": total, "passed": passed, "failed": failed, "pass_rate": rate,
            "kinds_bad": kinds_bad}


def claims_audit(res, case_blob):
    """结论-证据对齐：引文回证 + 数字回证。"""
    unbacked_ev, unbacked_num, problems = [], [], []
    inner = (res or {}).get("result") or {}
    steps_idx = {}
    for s in (inner.get("steps") or []):
        if isinstance(s, dict):
            steps_idx[str(s.get("step_id") or "")] = s
    claims = [c for c in ((res or {}).get("claims") or []) if isinstance(c, dict)]
    if not claims:
        problems.append("[evidence] claims 为空：最终结论无证据链")
        return unbacked_ev, unbacked_num, problems
    for c in claims:
        cid = str(c.get("claim_id") or "?")
        src = str(c.get("source_id") or "")
        quotes = [norm(e.get("quote")) for e in (c.get("evidence") or []) if isinstance(e, dict)]
        quotes = [q for q in quotes if q]
        if not quotes:
            unbacked_ev.append("%s 无证据引文" % cid)
        for q in quotes:
            step = steps_idx.get(src) or {}
            step_blob = norm(json.dumps(step, ensure_ascii=False)) if step else ""
            if q not in case_blob and q not in step_blob:
                unbacked_ev.append("%s 引文在 case.json 与步骤 %s 产物中均不存在（逐字比对）" % (cid, src or "?"))
        # 数字回证：claim 正文的每个数字须出现在引文或对应步骤产物中
        pool = " ".join(quotes) + " " + (norm(json.dumps(steps_idx.get(src) or {}, ensure_ascii=False)) if src else "")
        for num in NUM_RE.findall(str(c.get("text") or "")):
            if norm(num) not in pool:
                unbacked_num.append("%s 数字 %s 无回证" % (cid, num))
    return unbacked_ev, unbacked_num, problems


def fallback_audit(res):
    problems = []
    inner = (res or {}).get("result") or {}
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    fb_ids = {str(f.get("step_id")) for f in (inner.get("fallbacks") or []) if isinstance(f, dict)}
    pend_ids = {str(p.get("step_id")) for p in (inner.get("pending_review") or []) if isinstance(p, dict)}
    for s in steps:
        sid = str(s.get("step_id") or "")
        st = str(s.get("status") or "").lower()
        if st == "failed" and sid not in fb_ids:
            problems.append("[fallback] 步骤 %s status=failed 未登记 fallbacks" % sid)
        if st == "degraded" and sid not in fb_ids:
            problems.append("[fallback] 步骤 %s status=degraded 未登记降级处置" % sid)
        if st == "skipped" and sid not in pend_ids:
            problems.append("[pending] 步骤 %s status=skipped 未登记 pending_review" % sid)
        if st in ("failed", "degraded"):
            fb = next((f for f in (inner.get("fallbacks") or [])
                       if isinstance(f, dict) and str(f.get("step_id")) == sid), None)
            if fb is not None and not (fb.get("degraded_action") or fb.get("failure_mode")):
                problems.append("[fallback] 步骤 %s 登记缺 degraded_action/failure_mode" % sid)
    return problems


def analyze(result, case, ablate="none", case_state="not_found", rules_state="not_found",
            plan_path=None):
    """供 gain_probe 导入的主校验入口（纯函数，不改 result）。"""
    problems = []
    inner = (result or {}).get("result") or {}
    steps = [s for s in (inner.get("steps") or []) if isinstance(s, dict)]
    plan_steps = ((inner.get("plan") or {}).get("steps")) or []
    case_blob = case_text_blob(case if isinstance(case, dict) else {})

    # [contract]
    fields = contract_fields(case if isinstance(case, dict) else {})
    missing_fields = [f for f in fields if f not in (result or {})]
    if missing_fields:
        problems.append("[contract] 缺 output_contract 字段: %s" % ",".join(missing_fields))
    case_id = str((case or {}).get("case_id") or "unknown") if isinstance(case, dict) else "unknown"
    if isinstance(case, dict) and str(result.get("case_id")) != case_id:
        problems.append("[contract] case_id 与 case.json 不一致: %s != %s" % (result.get("case_id"), case_id))
    if str(result.get("status") or "") not in STATUS_VALUES:
        problems.append("[enum] status 非法: %r" % (result.get("status"),))

    # [plan]（独立复算，与 pipeline_run 分开实现）
    if not plan_steps:
        problems.append("[structure] result.plan.steps 为空（步骤图未声明）")
    elif str((inner.get("plan") or {}).get("declared_at") or "") in ("", "None"):
        problems.append("[plan] plan.declared_at 为空（口径未事前声明）")
    acyclic, order = None, []
    if plan_steps:
        acyclic, gp, order = topo_check(plan_steps)
        if ablate != "all":
            problems.extend(gp)
    # [trace]
    if ablate != "all":
        tp, _stats = trace_audit(steps, plan_steps, bool(acyclic), order)
        problems.extend(tp)

    # [middle]
    mc = recompute_middle(steps)
    if ablate != "all":
        for kb in mc["kinds_bad"]:
            problems.append("[middle] %s" % kb)
        stored = inner.get("middle_checks") or {}
        if mc["total"] == 0 and steps:
            problems.append("[middle] 有留痕步骤但零中间校验条目")
        for key in ("total", "passed", "failed"):
            sv = stored.get(key)
            if sv is not None and int(sv) != mc[key]:
                problems.append("[middle] middle_checks.%s=%s 与复算 %d 不符" % (key, sv, mc[key]))
        sv_rate = stored.get("pass_rate")
        if sv_rate is not None and mc["pass_rate"] is not None and abs(float(sv_rate) - mc["pass_rate"]) > 1e-6:
            problems.append("[middle] pass_rate=%s 与复算 %s 不符" % (sv_rate, mc["pass_rate"]))

    # [evidence] / 数字回证
    if ablate != "all":
        uev, unum, _ = claims_audit(result or {}, case_blob)
        for x in uev:
            problems.append("[evidence] %s" % x)
        for x in unum:
            problems.append("[evidence] %s" % x)

    # [fallback] / [pending]
    if ablate != "all":
        problems.extend(fallback_audit(result or {}))

    # verdict / run_status 枚举
    if str((inner.get("run_status") or {}).get("state") or "") not in RUN_STATES:
        problems.append("[enum] run_status.state 非法: %r" % ((inner.get("run_status") or {}).get("state"),))
    if str(inner.get("verdict") or "") not in ("answered", "partially_answered",
                                               "not_answered", "cannot_verify"):
        problems.append("[enum] verdict 非法: %r" % (inner.get("verdict"),))

    disabled = [] if ablate != "all" else ["graph", "trace", "middle", "evidence", "fallback"]
    gates = [
        {"gate": "case_contract", "state": "enforced" if isinstance(case, dict) else case_state,
         "note": "" if isinstance(case, dict) else "case.json 缺失，来源比对跳过"},
        {"gate": "plan_ledger", "state": "enforced" if plan_steps else "not_found",
         "note": "" if plan_steps else "步骤图未声明，下游不得宣称步骤图完备"},
        {"gate": "dag_acyclic", "state": "enforced" if acyclic else "not_found",
         "note": "" if acyclic else "无环性未确证"},
        {"gate": "middle_checks", "state": "enforced" if mc["total"] else "not_found",
         "note": "" if mc["total"] else "无中间校验条目"},
    ]
    verdict = "PASS" if not problems else "FAIL"
    self_check = [
        {"item": "步骤图依赖无环", "template_value": "topo_check 双实现复算", "applied": ablate != "all", "match": bool(acyclic)},
        {"item": "逐步留痕可回放", "template_value": "trace_audit 要素齐全", "applied": ablate != "all", "match": not any("[trace]" in p for p in problems)},
        {"item": "中间校验通过率可复算", "template_value": "steps[].checks 复算对照", "applied": ablate != "all", "match": not any("[middle]" in p for p in problems)},
        {"item": "结论-证据对齐（引文+数字回证）", "template_value": "claims_audit", "applied": ablate != "all", "match": not any("[evidence]" in p for p in problems)},
        {"item": "失败降级登记不静默", "template_value": "fallback_audit", "applied": ablate != "all", "match": not any("[fallback]" in p or "[pending]" in p for p in problems)},
    ]
    return {"verdict": verdict, "problems": problems, "gates": gates,
            "self_check": self_check, "ablate": ablate, "disabled_checks": disabled,
            "middle_recompute": {k: mc[k] for k in ("total", "passed", "failed", "pass_rate")},
            "unbacked_numbers": [p for p in problems if "无回证" in p],
            "unbacked_evidence": [p for p in problems if "不存在" in p or "无证据引文" in p]}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--plan", default="/app/work/analysis_plan.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[verify_check] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    ledger = load_json(args.plan) or {}
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    plan_state = "enforced" if ledger.get("steps") else "not_found"

    rep = analyze(res, case if isinstance(case, dict) else {}, ablate="none",
                  case_state=case_state, rules_state=plan_state, plan_path=args.plan)
    # 台账一致性：result.plan 与 work 台账
    inner = res.get("result") or {}
    if ledger.get("steps") and (inner.get("plan") or {}).get("steps"):
        if norm(json.dumps(ledger["steps"])) != norm(json.dumps((inner["plan"]).get("steps"))):
            rep["problems"].append("[plan] result.plan 与 /app/work/analysis_plan.json 台账不一致")
            rep["verdict"] = "PASS" if not rep["problems"] else "FAIL"

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = rep.get("self_check")
                cur["gates"] = rep.get("gates")
                cur["unbacked_numbers"] = rep.get("unbacked_numbers")
                cur["unbacked_evidence"] = rep.get("unbacked_evidence")
                cur["validator_verdict"] = rep.get("verdict")
                if isinstance(cur.get("result"), dict):
                    cur["result"]["middle_checks"] = dict(rep["middle_recompute"],
                                                          computed_by="verify_check.py")
                save_json(args.result, cur)
        except Exception as e:
            print("[verify_check] 回写 result.json 失败: %s" % e)

    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)),
                                        "..", "work", "verify_check.json")
    save_json(out_path, rep)
    print("[verify_check] verdict=%s | problems=%d | 中间校验 total=%d passed=%d pass_rate=%s"
          % (rep["verdict"], len(rep["problems"]), rep["middle_recompute"]["total"],
             rep["middle_recompute"]["passed"], rep["middle_recompute"]["pass_rate"]))
    for pr in rep["problems"][:20]:
        print("  PROBLEM: %s" % pr)
    print("[verify_check] 报告落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
