#!/usr/bin/env python3
"""schema_guard.py — 结构守卫（multi-step-analysis）。

只查结构与硬约束，不做业务校验（业务校验归 verify_check / pipeline_run）：
  1. result.json 可解析、顶层键齐备（含 output_contract 全字段）。
  2. 键归属纪律：多脚本禁写同一键——检查 computed_by 标记与键归属矩阵一致
     （dag/trace_audit 只能是 pipeline_run.py；middle_checks 只能是 verify_check.py；
     gain_evidence/efficiency 只能是 gain_probe.py）。
  3. 步骤图基本形：plan.steps 非空时每步 step_id 合法（显式 ASCII 白名单，
     不用 str.isalpha——该函数对汉字返回 True，会把「步骤一」误判成合法 id）、
     depends_on 为列表。
  4. 包完整性：SKILL.md 与 scripts/ 同在（定位标志）。

用法：
    python3 schema_guard.py --result /app/output/result.json --case /input/case.json \
        --out /app/work/schema_guard.json
退出码：恒为 0（结论记在 verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TOP_KEYS = ("case_id", "status", "result", "claims", "uncertainties", "changelog",
            "self_check", "unbacked_numbers", "unbacked_evidence", "validator_verdict", "gates")
OWNER_MAP = {
    "dag": "pipeline_run.py",
    "trace_audit": "pipeline_run.py",
    "middle_checks": "verify_check.py",
    "gain_evidence": "gain_probe.py",
    "efficiency": "gain_probe.py",
}
STEP_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


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


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        args = ap.parse_args()
    except Exception as e:
        print("[schema_guard] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    res = load_json(args.result)
    if not isinstance(res, dict):
        print("[schema_guard] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case) if os.path.exists(args.case) else None

    for k in TOP_KEYS:
        if k not in res:
            problems.append("[structure] 顶层缺键: %s" % k)
    for f in contract_fields(case if isinstance(case, dict) else {}):
        if f not in res:
            problems.append("[contract] 缺 output_contract 字段: %s" % f)

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    for key, owner in OWNER_MAP.items():
        v = inner.get(key)
        if isinstance(v, dict):
            cb = str(v.get("computed_by") or v.get("collected_by") or "")
            if cb and owner not in cb:
                problems.append("[owner] 键 %s 的 computed_by=%s，应为 %s（多脚本禁写同一键）" % (key, cb, owner))
            if not cb:
                problems.append("[owner] 键 %s 缺 computed_by/collected_by 标记（应 %s）" % (key, owner))

    plan_steps = ((inner.get("plan") or {}).get("steps")) or []
    for s in plan_steps:
        sid = s.get("step_id") if isinstance(s, dict) else None
        if not (isinstance(sid, str) and STEP_ID_RE.match(sid)):
            problems.append("[structure] step_id 非法（须 ASCII 大写字母+数字，禁用 isalpha 判断）: %r" % (sid,))
        dep = s.get("depends_on") if isinstance(s, dict) else None
        if not isinstance(dep, list):
            problems.append("[structure] 步骤 %r depends_on 非列表" % (sid,))

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    if not os.path.exists(marker):
        problems.append("[package] 定位标志未命中（脚本未与 SKILL.md 同包）")

    verdict = "PASS" if not problems else "FAIL"
    report = {"verdict": verdict, "problems": problems, "ablate": "none",
              "disabled_checks": [], "top_keys": len(TOP_KEYS),
              "plan_steps": len(plan_steps),
              "self_check": [{"item": "顶层键与 contract 字段齐备", "applied": True,
                              "match": not any("[structure]" in p or "[contract]" in p for p in problems)},
                             {"item": "键归属纪律（computed_by 一致）", "applied": True,
                              "match": not any("[owner]" in p for p in problems)}]}
    out_path = args.out or os.path.join(os.path.dirname(os.path.abspath(args.result)),
                                        "..", "work", "schema_guard.json")
    try:
        d = os.path.dirname(out_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[schema_guard] 报告写盘失败: %s" % e)

    print("[schema_guard] verdict=%s | problems=%d" % (verdict, len(problems)))
    for pr in problems[:20]:
        print("  PROBLEM: %s" % pr)
    print("[schema_guard] 报告落盘: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[schema_guard] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
