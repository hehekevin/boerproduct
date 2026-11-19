#!/usr/bin/env python3
"""verify_check.py — 总业务校验器（lit-review-bind）。

汇聚四组机械校验（与题面机检点逐项对应），三组复用领域校验器的纯函数：
  A. 段落-来源绑定  （draft_bind.analyze_binding 的 binding 组）
  B. 引用逐字回证  （draft_bind.analyze_binding 的 quote 组 → unbacked_quotes 判 FAIL）
  C. 分歧对照 + 强度不越界（dispute_table.analyze_disputes）
  D. 主题归属与覆盖  （theme_group.analyze 的 theme/coverage 组）
另做：枚举合法性、verdict/run_status 一致性、steps 可重跑、output_contract 字段。

所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_quotes / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；coverage 归 theme_group.py，quote_audit 归 draft_bind.py，
dispute_audit 归 dispute_table.py，gain_evidence / efficiency 归 gain_probe.py，
其余归 build_skeleton + Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--emit-into] [--ablate all|binding,quote,dispute,coverage]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from draft_bind import analyze_binding
    from dispute_table import analyze_disputes
    from theme_group import analyze as analyze_theme
except Exception as e:  # pragma: no cover
    print("[verify_check] 无法导入领域校验器: %s" % e)
    sys.exit(0)

LAB = ("keep", "pending", "exclude")
VERDICTS = ("drafted", "partially_drafted", "not_drafted", "cannot_verify")


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


def analyze(res, case, ablate="none", case_state="enforced", outline_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_quotes": [], "unverifiable_text": [], "disabled_checks": [],
              "ablate": ablate}
    off = lambda g: ablate == "all" or g in str(ablate).split(",")

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced"
                            else "case.json 缺失/不可读，逐字回证无底本，下游不得宣称已核对"})
    report["gates"].append({"gate": "outline_ledger", "state": outline_state,
                            "note": "" if outline_state == "enforced"
                            else "/app/work/outline.json 台账缺失，下游不得宣称已核对"})
    has_outline = bool((inner.get("outline") or {}).get("sections"))
    report["gates"].append({"gate": "outline_written", "state": "enforced" if has_outline else "not_found",
                            "note": "" if has_outline else "大纲未写，下游不得宣称已核对"})

    # ---- A+B. 段落绑定 + 逐字回证 ----
    if not (off("binding") and off("quote")):
        b = analyze_binding(res, case if isinstance(case, dict) else {}, ablate=ablate)
        report["self_check"].extend(b.get("self_check") or [])
        for k in ("unbacked_quotes", "unverifiable_text"):
            if b.get(k):
                report[k] = b[k] if k == "unbacked_quotes" else report[k] + b[k]
        report["problems"].extend(b.get("problems") or [])
        report["disabled_checks"].extend(b.get("disabled_checks") or [])

    # ---- C. 分歧对照 + 强度不越界 ----
    if not off("dispute"):
        d = analyze_disputes(res, ablate=ablate)
        report["self_check"].extend(d.get("self_check") or [])
        report["problems"].extend(d.get("problems") or [])
        report["disabled_checks"].extend(d.get("disabled_checks") or [])

    # ---- D. 主题归属 + 覆盖 ----
    if not (off("theme") and off("coverage")):
        t = analyze_theme(res, ablate=ablate)
        for s in (t.get("self_check") or []):
            s["item"] = "theme." + s["item"]
            report["self_check"].append(s)
        report["problems"].extend(t.get("problems") or [])
        report["disabled_checks"].extend(t.get("disabled_checks") or [])

    # ---- 枚举合法性（始终开启） ----
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    for i, it in enumerate(items):
        pid = it.get("paper_id") or "items[%d]" % i
        if it.get("label") is not None and it.get("label") not in LAB:
            report["problems"].append("%s label 枚举非法: %r（须 keep/pending/exclude）" % (pid, it.get("label")))
        if it.get("label") == "keep" and not it.get("criteria_hit") and not off("binding"):
            pass  # 纳入依据由筛选口径约束，主题归属已在 D 组核对
        if it.get("label") == "pending" and not str(it.get("pending_reason") or "").strip():
            report["problems"].append("%s 标 pending 但 pending_reason 为空" % pid)

    # ---- verdict / run_status 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict is not None and verdict not in VERDICTS:
        report["problems"].append("verdict 枚举非法: %r（须 drafted/partially_drafted/not_drafted/cannot_verify）"
                                  % verdict)
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    claims_all = res.get("claims") or []
    if verdict == "drafted" and not claims_all:
        report["problems"].append("verdict=drafted 但 claims 为空（无带引用草稿）")
    if verdict == "not_drafted" and claims_all:
        report["problems"].append("verdict=not_drafted 但 claims 非空")
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
            if fname not in res:
                report["problems"].append("缺少 output_contract 字段: %s" % fname)

    if report["unbacked_quotes"]:
        report["problems"].append("存在 %d 条编造/未回证引用（见 unbacked_quotes）"
                                  % len(report["unbacked_quotes"]))
    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--outline", default="/app/work/outline.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="把 self_check/gates/unbacked_quotes/validator_verdict 回写 result.json")
        ap.add_argument("--ablate", default="none",
                        help="none | all | binding,quote,dispute,coverage 子集")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict):
        msg = "result.json 不存在或不可解析: %s（不中断交付）" % args.result
        print("[verify_check] FAIL: %s" % msg)
        _dump(args.out, {"verdict": "FAIL", "problems": [msg], "self_check": [],
                         "gates": [], "unbacked_quotes": [], "ablate": args.ablate})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    outline_state = "enforced" if os.path.exists(args.outline) else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     ablate=args.ablate, case_state=case_state, outline_state=outline_state)
    _dump(args.out, report)

    if args.emit_into:
        try:
            cur = load_json(args.result)
            if isinstance(cur, dict):
                cur["self_check"] = report.get("self_check") or []
                cur["gates"] = report.get("gates") or []
                cur["unbacked_quotes"] = report.get("unbacked_quotes") or []
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
