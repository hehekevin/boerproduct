#!/usr/bin/env python3
"""gain_probe.py — 增益对照探针（paper-fact-citation-audit，可选步骤）。

同一份输入（result.json + case.json 副本）跑两遍校验：
  normal   = verify_check.analyze(ablate="none")        # 四组全开
  degraded = verify_check.analyze(ablate="all")         # 关闭定位/严重度/证据
把真实数字写进 result.gain_evidence（runs / delta_normal_minus_degraded /
mechanism_to_metric_map / boundaries / failure_conditions）与 result.efficiency。
三项对照指标：定位失据漏检 / 分级口径漏检 / 证据缺失漏检（另有 checker_runs
与 wall_clock）。数字全部来自实跑，不手填不臆造。

--inject-pollution 在**副本**上注入污染（清空 quote/location、把 fact_error
抬成 minor、清空 evidence）做反例自测：normal 须抓到（caught_by_normal_mode
=true），原 result.json 不被改动。
**预算保护**：--max-requests 默认 32（约 64 总预算的 50%）。传入已用请求数
（--used-requests）超过阈值时脚本直接跳过双跑，写 gain_evidence.available=false
（reason=budget_over_half）并 exit 0——不对 result 做任何改动。

用法：
    python3 gain_probe.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work --emit-into [--inject-pollution] [--used-requests N]
退出码恒为 0（结论记在 gain_evidence.available 与 stdout）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_check as vc  # noqa: E402


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _inject_pollution(copy_res):
    """在副本上注入三类污染（用于反例自测），返回注入清单。"""
    injected = []
    inner = (copy_res or {}).get("result")
    if not isinstance(inner, dict):
        return injected
    for i, f in enumerate(inner.get("findings") or []):
        if not isinstance(f, dict) or f.get("status") != "confirmed":
            continue
        if f.get("quote"):
            f["quote"] = "（污染注入：定位已清空）"
            f["location"] = ""
            injected.append("findings[%d].location_cleared" % i)
        if f.get("category") == "fact_error" and f.get("severity") in ("critical", "major"):
            f["severity"] = "minor"
            injected.append("findings[%d].severity_downgraded" % i)
        if f.get("category") in ("fact_error", "citation_mismatch"):
            f["evidence"] = ""
            injected.append("findings[%d].evidence_cleared" % i)
    return injected


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--emit-into", action="store_true")
        ap.add_argument("--inject-pollution", action="store_true")
        ap.add_argument("--used-requests", type=int, default=0)
        ap.add_argument("--max-requests", type=int, default=32)
        args = ap.parse_args()
    except Exception as e:
        print("[gain_probe] 参数解析失败: %s" % e)
        return 0

    res = load_json(args.result)
    case = load_json(args.case)
    case_obj = case if isinstance(case, dict) else {}

    # ---- 预算保护：请求已过半 -> 跳过双跑，gain_evidence.available=false ----
    if args.used_requests >= args.max_requests:
        ge = {"available": False, "reason": "budget_over_half",
              "used_requests": args.used_requests, "max_requests": args.max_requests,
              "runs": [], "delta_normal_minus_degraded": {},
              "mechanism_to_metric_map": [], "boundaries": [],
              "failure_conditions": ["双跑增益对照在累计请求达预算50%%起跳过"]}
        eff = {"available": False, "reason": "budget_over_half",
               "wall_clock_seconds_total": 0.0, "checker_runs": 0, "reproduce": None}
        _write_back(args, res, ge, eff)
        print("[gain_probe] 已跳过双跑（used_requests=%d >= max_requests=%d），"
              "gain_evidence.available=false" % (args.used_requests, args.max_requests))
        return 0

    if not isinstance(res, dict):
        ge = {"available": False, "reason": "result_not_readable", "runs": [],
              "delta_normal_minus_degraded": {}, "mechanism_to_metric_map": [],
              "boundaries": [], "failure_conditions": []}
        eff = {"available": False, "reason": "result_not_readable",
               "wall_clock_seconds_total": 0.0, "checker_runs": 0, "reproduce": None}
        _write_back(args, res, ge, eff)
        print("[gain_probe] result.json 不可读，gain_evidence.available=false（不编数字）")
        return 0

    base = copy.deepcopy(res)
    injected = []
    if args.inject_pollution:
        injected = _inject_pollution(base)

    runs = []
    t0 = time.time()
    r_normal = vc.analyze(base, case_obj, ablate="none",
                          case_state="enforced" if isinstance(case, dict) else "skipped_not_provided")
    t1 = time.time()
    r_degraded = vc.analyze(base, case_obj, ablate="all",
                            case_state="enforced" if isinstance(case, dict) else "skipped_not_provided")
    t2 = time.time()

    runs.append({"mode": "normal", "verdict": r_normal["verdict"],
                 "problems": len(r_normal["problems"]),
                 "wall_clock_seconds": round(t1 - t0, 4)})
    runs.append({"mode": "degraded", "verdict": r_degraded["verdict"],
                 "problems": len(r_degraded["problems"]),
                 "wall_clock_seconds": round(t2 - t1, 4)})

    p_n, p_d = set(r_normal["problems"]), set(r_degraded["problems"])
    missed = p_n - p_d  # 退化模式漏检 = 正常模式抓到而退化模式没抓到的
    loc_skipped = sum(1 for x in missed if "quote" in x or "location" in x)
    sev_skipped = sum(1 for x in missed if "严重度" in x or "severity" in x)
    evi_skipped = sum(1 for x in missed if "evidence" in x or "回证" in x or "revision_suggestion" in x)

    delta = {"problems": len(r_normal["problems"]) - len(r_degraded["problems"]),
             "location_missed_by_degraded": loc_skipped,
             "severity_missed_by_degraded": sev_skipped,
             "evidence_missed_by_degraded": evi_skipped}
    caught = bool(injected) and r_normal["verdict"] == "FAIL"

    ge = {
        "available": True,
        "used_requests": args.used_requests,
        "runs": runs,
        "delta_normal_minus_degraded": delta,
        "mechanism_to_metric_map": [
            {"mechanism": "定位回证(location)", "metric": "location_missed_by_degraded"},
            {"mechanism": "严重度口径(severity)", "metric": "severity_missed_by_degraded"},
            {"mechanism": "证据链回证(evidence)", "metric": "evidence_missed_by_degraded"},
        ],
        "boundaries": ["正常=ablate none 四组全开", "退化=ablate all 关闭定位/严重度/证据"],
        "failure_conditions": [],
        "pollution_injected": injected,
        "caught_by_normal_mode": caught,
    }
    eff = {"available": True,
           "wall_clock_seconds_total": round(t2 - t0, 4),
           "checker_runs": 2,
           "reproduce": "python3 gain_probe.py --result /app/output/result.json --case /input/case.json --work-dir /app/work --emit-into"}

    _write_back(args, res, ge, eff)
    print("[gain_probe] normal=%s(%d) degraded=%s(%d) delta=%s pollution_caught=%s"
          % (r_normal["verdict"], len(r_normal["problems"]),
             r_degraded["verdict"], len(r_degraded["problems"]),
             delta, caught))
    return 0


def _write_back(args, res, ge, eff):
    try:
        os.makedirs(args.work_dir or ".", exist_ok=True)
    except Exception:
        pass
    if args.emit_into and isinstance(res, dict):
        try:
            inner = res.setdefault("result", {})
            if isinstance(inner, dict):
                inner["gain_evidence"] = ge
                inner["efficiency"] = eff
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[gain_probe] 回写失败: %s" % e)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[gain_probe] 未预期异常（已降级）: %s" % e)
        sys.exit(0)