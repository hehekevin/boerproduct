#!/usr/bin/env python3
"""verify_check.py — 主校验器（exp-result-anomaly）。

校验组：enum 枚举、anomaly 异常定位完备、detection 检测一致性、contract 契约、
structure 结构。退出码恒为 0，判据是报告里 verdict（PASS/FAIL）+ problems。
--emit-into 把 self_check / gates / validator_verdict 写回 result.json。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ANOMALY_TYPES = {"outlier", "jump", "plateau"}
RUN_STATES = {"success", "partial", "unable_to_determine", "refused"}
TOP_REQUIRED = ["case_id", "status", "result", "uncertainties", "changelog"]
RESULT_REQUIRED = ["material_gaps", "environment", "contract_fields", "dataset_ids",
                   "thresholds", "anomalies", "detection", "input_files",
                   "run_status", "verdict", "verdict_basis"]


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


def check(result, case):
    P = []
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        P.append("[structure] result 应为对象")
        return P

    th = inner.get("thresholds") or {}
    detection = inner.get("detection") or {}
    anomalies = inner.get("anomalies") or []

    # enum
    for a in anomalies:
        if not isinstance(a, dict):
            continue
        if a.get("anomaly_type") not in ANOMALY_TYPES:
            P.append("[enum] anomaly_type=%s 非法" % a.get("anomaly_type"))
    rs = inner.get("run_status") or {}
    if rs.get("state") is not None and rs.get("state") not in RUN_STATES:
        P.append("[enum] run_status.state=%s 非法" % rs.get("state"))

    # anomaly 定位完备：每个 anomaly 必须有维度+对象+阈值+偏离幅度
    for a in anomalies:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("anomaly_id") or "?")
        if not str(a.get("dimension") or "").strip():
            P.append("[%s][anomaly] 缺 dimension" % aid)
        if not str(a.get("object_ref") or "").strip():
            P.append("[%s][anomaly] 缺 object_ref（未定位到对象）" % aid)
        if not str(a.get("threshold_used") or "").strip():
            P.append("[%s][anomaly] 缺 threshold_used" % aid)
        if a.get("deviation") is None or str(a.get("deviation") or "").strip() == "":
            P.append("[%s][anomaly] 缺 deviation（偏离幅度）" % aid)
        if a.get("observed_value") is None:
            P.append("[%s][anomaly] 缺 observed_value" % aid)

    # detection 一致性：脚本声称的上报数应等于 anomalies 长度
    det_total = detection.get("anomalies_reported")
    if isinstance(det_total, int) and det_total != len(anomalies):
        P.append("[detection] anomalies_reported=%d 与 anomalies 实际 %d 不符"
                 % (det_total, len(anomalies)))

    # contract / structure
    if not result.get("case_id"):
        P.append("[contract] 缺 case_id")
    for f in TOP_REQUIRED:
        if f not in result:
            P.append("[contract] 缺顶层字段: %s" % f)
    for f in RESULT_REQUIRED:
        if f not in inner:
            P.append("[contract] 缺业务字段: result.%s" % f)
    for f in contract_fields(case):
        if f not in result:
            P.append("[contract] 缺 output_contract 字段: %s" % f)

    rs = inner.get("run_status") or {}
    if rs.get("state") not in (None, "success") and not rs.get("reason"):
        P.append("[structure] run_status 非 success 但缺 reason")
    v = inner.get("verdict")
    if v == "audited" and not anomalies:
        P.append("[structure] verdict=audited 但 anomalies 为空（要么有异常要么改 cannot_verify）")
    if v == "cannot_verify" and not inner.get("material_gaps"):
        P.append("[structure] verdict=cannot_verify 但 material_gaps 为空")
    return P


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    problems, result, case = [], {}, {}
    gates = []

    try:
        if os.path.exists(args.result):
            with open(args.result, "r", encoding="utf-8") as f:
                result = json.load(f)
        else:
            problems.append("[contract] result.json 不存在")
            gates.append({"gate": "result_exists", "state": "not_found", "note": args.result})
    except Exception as e:
        problems.append("[contract] result.json 读取失败: %s" % e)
        gates.append({"gate": "result_exists", "state": "invalid", "note": str(e)})
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
        else:
            gates.append({"gate": "case_contract", "state": "not_found", "note": args.case})
    except Exception as e:
        gates.append({"gate": "case_contract", "state": "invalid", "note": str(e)})
    gates.append({"gate": "skill_marker",
                  "state": "enforced" if marker_hit else "not_found", "note": ""})

    if result:
        try:
            problems = check(result, case)
        except Exception as e:
            problems.append("[structure] 校验器内部异常: %s" % e)

    verdict = "PASS" if not problems else "FAIL"
    report = {"ok": not problems, "verdict": verdict, "problems": problems,
              "counts": {"problems": len(problems)}}
    try:
        if args.out:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

    if args.emit_into and result:
        try:
            result["validator_verdict"] = verdict
            result["self_check"] = [{"item": "verify_check 校验", "template_value": "verdict=PASS",
                                     "applied": True, "match": verdict == "PASS"}]
            result["gates"] = gates
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[verify_check] 回写失败: %s" % e)

    print("[verify_check] verdict=%s（问题 %d 处，退出码恒 0）| marker_hit=%s"
          % (verdict, len(problems), marker_hit))
    for p in problems[:40]:
        print("  - %s" % p)
    if len(problems) > 40:
        print("  ... 共 %d 处" % len(problems))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)