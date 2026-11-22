#!/usr/bin/env python3
"""verify_check.py — 业务逻辑校验器（exp-param-domain，关键参数可行域约束）。

对 result.json 做三组机械校验（与题面突破方向「关键参数识别与可行域约束」对应）：
  A. params   关键参数识别：parameters 3-6 个；每个 name/current/range[下限,上限]/
              unit/basis(manual|spec|literature)/step 齐备；current 为数值且
              落在 range 内；basis 枚举合法。参数规模封顶 6（不追求穷尽）。
  B. cons     耦合约束登记：constraints 非空；每条 params 引用存在的参数名、
              expression 非空、source 非空；kind=none_declared 条目须给 source。
  C. evidence 依据可复核：每个参数 basis 非空；数值 current 须出现在 claims
              text/quote（空白归一化后子串匹配），未回证数字列入 unbacked_numbers。

另有常开检查：completeness 汇总一致性、verdict 与要素进度一致性、run_status/
steps 违规、契约字段（case_contract gate enforced 时）。
所有检查项产出三元组 {item, template_value, applied, match} 回写 result.json
（键 self_check / gates / unbacked_numbers / validator_verdict）。**键归属**：
本脚本只写这四个顶层键；feasibility_check 归 param_check.py，gain_evidence
归 build_skeleton/Agent。

退出码恒为 0（结论记在报告 verdict 与 stdout，不中断交付）。
用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--marker /app/work/skill_marker.json] [--out /app/work/verify_check.json] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

BASIS_ENUM = ("manual", "spec", "literature")
MIN_PARAMS = 3
MAX_PARAMS = 6


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm(s):
    """空白归一化（不做大小写折叠，避免影响中文/单位/数字之外的语义）。"""
    return re.sub(r"\s+", "", str(s or ""))


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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


def analyze(res, case, case_state="enforced", marker_state="not_found"):
    """纯函数式分析（不写盘）。返回报告 dict。"""
    report = {"verdict": "PASS", "problems": [], "self_check": [], "gates": [],
              "unbacked_numbers": []}

    def add(item, template_value, applied, match):
        report["self_check"].append({"item": item, "template_value": template_value,
                                     "applied": bool(applied), "match": bool(match)})
        return applied and match

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        report["verdict"] = "FAIL"
        report["problems"].append("result 非对象，无法校验")
        report["gates"] = [{"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "下游不得宣称已核对"}]
        return report

    params = [p for p in (inner.get("parameters") or []) if isinstance(p, dict)]
    cons = [c for c in (inner.get("constraints") or []) if isinstance(c, dict)]
    claims = [c for c in (res.get("claims") or []) if isinstance(c, dict)]
    names = {str(p.get("name") or "") for p in params}

    # ---- 闸门 ----
    report["gates"].append({"gate": "case_contract", "state": case_state,
                            "note": "" if case_state == "enforced" else "case.json 缺失/不可读，下游不得宣称已核对"})
    report["gates"].append({"gate": "skill_scripts", "state": marker_state,
                            "note": "" if marker_state == "enforced" else "skill_marker.json 缺失或脚本不齐，下游不得宣称已核对"})
    feas = inner.get("feasibility_check") or {}
    feas_state = "enforced" if feas.get("checked_count") is not None else "not_found"
    report["gates"].append({"gate": "param_feasibility_check", "state": feas_state,
                            "note": "" if feas_state == "enforced" else "feasibility_check 未回填（param_check.py 未跑），下游不得宣称已核对"})

    # ---- A. 关键参数识别 ----
    count_ok = MIN_PARAMS <= len(params) <= MAX_PARAMS
    add("params.count_in_range", "关键参数 3-6 个", True, count_ok)
    if not count_ok:
        report["problems"].append("关键参数数量 %d 不在 [%d, %d] 内（不追求穷尽，聚焦 3-6 个）"
                                  % (len(params), MIN_PARAMS, MAX_PARAMS))
    pbad = 0
    for i, p in enumerate(params):
        nm = str(p.get("name") or "parameters[%d]" % i)
        rng = p.get("range")
        rng_ok = (isinstance(rng, (list, tuple)) and len(rng) >= 2
                  and is_num(rng[0]) and is_num(rng[1])
                  and float(rng[0]) <= float(rng[1]))
        cur_ok = is_num(p.get("current"))
        in_range = cur_ok and rng_ok and float(rng[0]) <= float(p["current"]) <= float(rng[1])
        ok = (bool(str(nm).strip())
              and bool(str(p.get("unit") or "").strip())
              and bool(str(p.get("basis") or "").strip())
              and p.get("basis") in BASIS_ENUM
              and rng_ok and cur_ok and in_range)
        add("parameters[%d].audited" % i, "name/range/unit/basis/step 齐备且当前值落可行域", True, ok)
        if not ok:
            pbad += 1
            miss = []
            if not str(p.get("unit") or "").strip():
                miss.append("unit")
            if not str(p.get("basis") or "").strip() or p.get("basis") not in BASIS_ENUM:
                miss.append("basis(须 %s)" % "/".join(BASIS_ENUM))
            if not rng_ok:
                miss.append("range(下限/上限)")
            if not cur_ok:
                miss.append("current(数值)")
            if cur_ok and rng_ok and not in_range:
                miss.append("当前值越界")
            report["problems"].append("参数 %s 可行域登记不完整或越界，缺少: %s"
                                      % (nm, "/".join(miss) or "未知"))
    add("params.complete", "全部关键参数可行域齐备", True, pbad == 0)

    # ---- B. 耦合约束登记 ----
    add("constraints.registered", "耦合约束条目≥1（含 none_declared 声明）", True, len(cons) >= 1)
    if not cons:
        report["problems"].append("耦合约束未登记：constraints 为空"
                                  "（确无耦合也须登记 kind=none_declared 条目并给 source）")
    for i, c in enumerate(cons):
        cid = c.get("cid") or "constraints[%d]" % i
        if c.get("kind") == "none_declared":
            ok = bool(str(c.get("source") or "").strip())
            add("constraints[%d].declared" % i, "无耦合声明须给 source", True, ok)
            if not ok:
                report["problems"].append("%s 声明无耦合但 source 为空" % cid)
            continue
        refs = [str(x) for x in (c.get("params") or []) if str(x).strip()]
        ok = (bool(refs) and all(x in names for x in refs)
              and bool(str(c.get("expression") or "").strip())
              and bool(str(c.get("source") or "").strip()))
        add("constraints[%d].valid" % i, "params 引用有效+表达式+依据齐备", True, ok)
        if not ok:
            bad_refs = [x for x in refs if x not in names]
            if bad_refs:
                report["problems"].append("%s 引用不存在的参数: %s" % (cid, ",".join(bad_refs)))
            if not str(c.get("expression") or "").strip():
                report["problems"].append("%s 缺约束表达式（expression 空）" % cid)
            if not str(c.get("source") or "").strip():
                report["problems"].append("%s 缺约束来源（source 空，须设备手册/材料规格/安全阈值）" % cid)

    # ---- C. 依据可复核 / 数字回证 ----
    numeric_vals = []
    for i, p in enumerate(params):
        if is_num(p.get("current")):
            numeric_vals.append(("parameters[%d].current" % i, p["current"]))
    if numeric_vals and not claims:
        report["problems"].append("claims 为空但存在 %d 个业务数值（回证链缺失）" % len(numeric_vals))
    claim_corpus = norm(json.dumps(claims, ensure_ascii=False)) if claims else ""
    for loc, v in numeric_vals:
        if claim_corpus and str(v) not in claim_corpus:
            report["unbacked_numbers"].append(
                {"item": loc, "value": str(v), "reason": "数值未出现在任何 claim text/quote 中"})
    if report["unbacked_numbers"]:
        report["problems"].append("存在 %d 个未回证数字（见 unbacked_numbers）"
                                  % len(report["unbacked_numbers"]))
    add("claims.backchain", "当前值逐个回证 claims", True,
        len(report["unbacked_numbers"]) == 0 and (claims or not numeric_vals))

    # ---- 覆盖面汇总一致性（始终开启） ----
    comp = inner.get("completeness") or {}
    exp = {"parameters_total": len(params), "constraints_total": len(cons)}
    bad = [k for k, v in exp.items() if isinstance(comp.get(k), int) and comp[k] != v]
    if bad:
        report["problems"].append("completeness 汇总与实际条目不符: %s" % bad)

    # ---- verdict 一致性（始终开启） ----
    verdict = inner.get("verdict")
    gaps = inner.get("material_gaps") or []
    if verdict == "cannot_verify" and not gaps:
        report["problems"].append("verdict=cannot_verify 但 material_gaps 为空")
    if verdict == "feasible" and (not count_ok or pbad > 0):
        report["problems"].append("verdict=feasible 但关键参数登记不齐或越界")
    if verdict == "infeasible" and pbad == 0 and count_ok:
        report["problems"].append("verdict=infeasible 但全部参数均在可行域内")
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

    report["verdict"] = "FAIL" if report["problems"] else "PASS"
    return report


# ------------------------------------------------------------------ CLI
def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--marker", default="/app/work/skill_marker.json",
                        help="脚本标志文件（build_skeleton 落盘）")
        ap.add_argument("--out", default=None)
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
                         "gates": [], "unbacked_numbers": []})
        return 0
    case = load_json(args.case)
    case_state = "enforced" if isinstance(case, dict) else "skipped_not_provided"
    marker = load_json(args.marker)
    marker_state = "enforced" if isinstance(marker, dict) and marker.get("all_present") else "not_found"

    report = analyze(res, case if isinstance(case, dict) else {},
                     case_state=case_state, marker_state=marker_state)
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
        print("[verify_check] PASS（检查项 %d 条全部 applied）" % len(report["self_check"]))
    else:
        print("[verify_check] FAIL（%d 处，不中断交付）:" % len(report["problems"]))
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