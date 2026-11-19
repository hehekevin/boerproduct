#!/usr/bin/env python3
"""selftest.py — 本地自测：正例 → 增益双跑 → 污染反例 → 消融对照（恒 exit 0）。

用法：
    python3 scripts/selftest.py [--out /tmp/selftest.json]

跑四件事，输出真实数字：
  T1 正例：examples/ 三件套过 claim_check（--require-gain）与 schema_guard。
  T2 增益双跑：同输入跑 full / ablated 两臂，逐项指标 + 差值（脚本实测）。
  T3 污染反例：注入 5 类脏数据（改写摘录 / 漏判且未登记 uncovered /
     verdict_summary 错账 / 非法 type / modifiers 缺字段），确认校验器逐条抓到，
     且退出码为 0（失败不中断交付）。
  T4 消融对照：同一份输入真跑两遍（full / --ablate），确认消融开关**真实生效**
     （闸门状态由 enforced 变为 ablated_off，内容级问题由 FAIL 降级为 WARNING），
     且两臂退出码均为 0。

退出码恒 0；结论看输出 JSON 的 ok/all_passed。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return {"cmd": " ".join(cmd), "exit_code": p.returncode,
            "stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]}


def contaminate(res):
    """注入 5 类脏数据（每类一处）。"""
    r = copy.deepcopy(res)
    v = r["result"]["verdicts"]
    # 1) 改写摘录：fatigue life -> fatigue lifetime
    v[0]["subclaims"][0]["evidence"][0]["quote"] = "a 12.4% higher fatigue lifetime than the control"
    # 2) 漏判 cl-2 且不登记 uncovered
    v = [x for x in v if x.get("claim_id") != "cl-2"]
    r["result"]["verdicts"] = v
    r["result"]["verdict_summary"] = {"supported": 99, "partially_supported": 1,
                                      "contradicted": 0, "insufficient_evidence": 0}
    # 3) verdict_summary 错账（上面已改）
    # 4) 非法 type
    v[0]["subclaims"][0]["type"] = "correlation"
    # 5) modifiers 缺字段（保留 modifiers 但删掉 significance）
    v[0]["subclaims"][1].get("modifiers", {}).pop("significance", None)
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    py = sys.executable
    case = os.path.join(BASE, "examples", "example-input.json")
    claims = os.path.join(BASE, "examples", "example-claims.json")
    good = os.path.join(BASE, "examples", "example-result.json")
    work = os.path.join(os.path.expanduser("~"), ".cache", "claim_audit_selftest")
    os.makedirs(work, exist_ok=True)
    bad = os.path.join(work, "contaminated-result.json")
    with open(good, "r", encoding="utf-8") as f:
        base_res = json.load(f)
    with open(bad, "w", encoding="utf-8") as f:
        json.dump(contaminate(base_res), f, ensure_ascii=False, indent=1)

    out = {"ok": True, "all_passed": False, "tests": {}}

    # ---- T1 正例 ----
    cc = run([py, os.path.join(HERE, "claim_check.py"), "--result", good, "--case", case,
              "--claims", claims, "--out", os.path.join(work, "claim_check_ok.json"), "--require-gain"])
    sg = run([py, os.path.join(HERE, "schema_guard.py"), "--result", good, "--case", case])
    cc_ok = False
    try:
        with open(os.path.join(work, "claim_check_ok.json"), "r", encoding="utf-8") as f:
            cc_ok = bool(json.load(f).get("ok"))
    except Exception:
        cc_ok = False
    sg_ok = "[schema_guard] PASS" in sg["stdout"]
    out["tests"]["T1_positive"] = {"claim_check_ok": cc_ok, "claim_check_exit": cc["exit_code"],
                                   "schema_guard_pass": sg_ok, "schema_guard_exit": sg["exit_code"],
                                   "passed": bool(cc_ok and sg_ok and cc["exit_code"] == 0
                                                  and sg["exit_code"] == 0),
                                   "stdout": cc["stdout"]}

    # ---- T2 增益双跑（同输入两遍）----
    cmp_path = os.path.join(work, "gain_compare.json")
    gp = run([py, os.path.join(HERE, "gain_probe.py"), "compare", "--result", good,
              "--case", case, "--claims", claims, "--out", cmp_path])
    rule_path = os.path.join(work, "gain_rule.json")
    gr = run([py, os.path.join(HERE, "gain_probe.py"), "rule", "--case", case,
              "--claims", claims, "--out", rule_path])
    pair = {}
    try:
        with open(rule_path, "r", encoding="utf-8") as f:
            rr = json.load(f)
        pair = {"rule_arms": rr.get("arms"), "rule_delta": rr.get("delta_full_minus_ablated")}
    except Exception as e:
        pair = {"error": str(e)}
    try:
        with open(cmp_path, "r", encoding="utf-8") as f:
            cmp_out = json.load(f)
        pair["gate_arms_on_clean"] = cmp_out.get("arms")
        pair["gate_delta_on_clean"] = cmp_out.get("delta_full_minus_ablated")
    except Exception as e:
        pair["error"] = str(e)
    # 污染件上的闸门双跑（展示闸门对真实缺陷的处置差异）
    cmp_bad_path = os.path.join(work, "gain_compare_contaminated.json")
    run([py, os.path.join(HERE, "gain_probe.py"), "compare", "--result", bad,
         "--case", case, "--claims", claims, "--out", cmp_bad_path])
    try:
        with open(cmp_bad_path, "r", encoding="utf-8") as f:
            cb = json.load(f)
        pair["gate_arms_on_contaminated"] = cb.get("arms")
        pair["gate_delta_on_contaminated"] = cb.get("delta_full_minus_ablated")
    except Exception as e:
        pair["error"] = str(e)
    out["tests"]["T2_gain_ab"] = {"exit_codes": {"compare": gp["exit_code"], "rule": gr["exit_code"]},
                                  "data": pair,
                                  "passed": bool(gp["exit_code"] == 0 and gr["exit_code"] == 0 and pair)}

    # ---- T3 污染反例 ----
    ccb = run([py, os.path.join(HERE, "claim_check.py"), "--result", bad, "--case", case,
               "--claims", claims, "--out", os.path.join(work, "claim_check_bad.json"),
               "--require-gain"])
    sgb = run([py, os.path.join(HERE, "schema_guard.py"), "--result", bad, "--case", case])
    rep = {}
    try:
        with open(os.path.join(work, "claim_check_bad.json"), "r", encoding="utf-8") as f:
            rep = json.load(f)
    except Exception as e:
        rep = {"error": str(e)}
    caught = len(rep.get("problems") or [])
    expect_kinds = ["quote 改写", "漏核验且未登记 uncovered", "verdict_summary 与实际不符",
                    "type 非法", "modifiers 缺字段"]
    hit = {k: any(k in p for p in (rep.get("problems") or [])) for k in expect_kinds}
    out["tests"]["T3_contamination"] = {
        "exit_codes": {"claim_check": ccb["exit_code"], "schema_guard": sgb["exit_code"]},
        "problems_caught": caught,
        "caught_kinds": hit,
        "all_kinds_caught": all(hit.values()),
        "problems": rep.get("problems"),
        "passed": bool(caught >= 4 and all(hit.values()) and ccb["exit_code"] == 0
                       and sgb["exit_code"] == 0),
        "stdout": ccb["stdout"]}

    # ---- T4 消融对照：同一份输入真跑两遍（full / --ablate）----
    abl_path = os.path.join(work, "gain_ablate.json")
    ga = run([py, os.path.join(HERE, "gain_probe.py"), "ablate", "--result", bad,
              "--case", case, "--claims", claims, "--out", abl_path])
    abl = {}
    try:
        with open(abl_path, "r", encoding="utf-8") as f:
            abl = json.load(f)
    except Exception as e:
        abl = {"error": str(e)}
    gl = abl.get("gate_layer") or {}
    fr, ar = gl.get("full_run") or {}, gl.get("ablated_run") or {}
    # 消融必须真实生效：闸门状态由 enforced 变为 ablated_off，且内容级问题由 FAIL 降级为 WARNING
    switch_on = (fr.get("gates") or {}).get("coverage_audit") == "enforced" \
        and (fr.get("gates") or {}).get("quote_verification") == "enforced"
    switch_off = (ar.get("gates") or {}).get("coverage_audit") == "ablated_off" \
        and (ar.get("gates") or {}).get("quote_verification") == "ablated_off"
    ablated_flag = (ar.get("ablation") or {}).get("active") is True
    # 污染件上：闸门开应多拦住内容级问题（改写摘录 + 漏判未登记）
    caught = gl.get("problems_caught_only_by_gates")
    caught_ok = isinstance(caught, int) and caught >= 1
    out["tests"]["T4_ablation"] = {
        "exit_code": ga["exit_code"],
        "gates_full": fr.get("gates"),
        "gates_ablated": ar.get("gates"),
        "problems_full": fr.get("problems_count"),
        "problems_ablated": ar.get("problems_count"),
        "warnings_ablated": ar.get("warnings_count"),
        "problems_caught_only_by_gates": caught,
        "headline": abl.get("headline"),
        "switch_effective": bool(switch_on and switch_off and ablated_flag),
        "passed": bool(ga["exit_code"] == 0 and switch_on and switch_off
                       and ablated_flag and caught_ok
                       and fr.get("exit_code") == 0 and ar.get("exit_code") == 0),
        "stdout": ga["stdout"]}

    out["all_passed"] = all(t.get("passed") for t in out["tests"].values())
    out["ok"] = True
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[selftest] WARNING 结果写出失败: %s" % e)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
