#!/usr/bin/env python3
"""run_pipeline.py — 一键执行 r5 全流程（自测与复用入口）。

顺序（与 SKILL.md 五步流程一致）：
  1. compare_matrix.py   正常模式 + 两个退化模式，同输入跑三遍
  2. gain_probe.py       三遍对照 → gain_evidence（同输入指纹 + 逐项 delta + 机制映射）
  3. efficiency_probe.py 效率计数 → result.efficiency
  4. check_result.py     校验 → check_report.json（失败路径恒 exit 0）

用法：
    python3 run_pipeline.py --result R.json [--workorder WO.json] [--case C.json] [--work DIR]
    --work 指定中间产物目录（默认 /app/work/r5）；--embed 会把 gain_evidence 与
    efficiency 写回 result.json（由子脚本各自负责，不覆盖其他键）。

退出码恒为 0：判定结果看 check_report.json 的 ok/verdict/problems。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cli_guard import SafeParser, run_entry, safe_parse_args  # noqa: E402


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as e:
        return 0, "[子脚本执行异常] %s" % e, ""


def main():
    ap = SafeParser(description="一键执行 r5 全流程（退出码恒 0，判定看 check_report.verdict）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work/r5")
    ap.add_argument("--embed", action="store_true")
    args = safe_parse_args(ap)
    if args is None:
        print("[run_pipeline] FAIL: 命令行参数有误，判定按失败处理")
        return 0

    problems = []
    try:
        os.makedirs(args.work, exist_ok=True)
    except Exception as e:
        problems.append("中间目录不可创建: %s" % e)
        args.work = "."

    py = sys.executable or "python"
    steps = []

    # 1) 对照器三遍
    cm_base = [py, os.path.join(HERE, "compare_matrix.py"),
               "--result", args.result]
    if args.workorder:
        cm_base += ["--workorder", args.workorder]
    for mode, fname in (("none", "pairwise_full.json"),
                        ("no_pairwise", "pairwise_ablate_no_pairwise.json"),
                        ("no_attribution", "pairwise_ablate_no_attribution.json")):
        out = os.path.join(args.work, fname)
        cmd = cm_base + ["--out", out]
        if mode != "none":
            cmd += ["--ablate", mode]
        rc, so, se = run(cmd)
        steps.append({"step": "compare_matrix:%s" % mode, "exit_code": rc,
                      "stdout": so, "stderr": se, "out": out})
        if rc != 0:
            problems.append("compare_matrix(%s) 退出码非 0: %s" % (mode, rc))

    # 2) 增益取证（写回 result.json）
    gp_cmd = [py, os.path.join(HERE, "gain_probe.py"),
              "--result", args.result,
              "--out", os.path.join(args.work, "gain_evidence.json")]
    if args.workorder:
        gp_cmd += ["--workorder", args.workorder]
    if args.embed:
        gp_cmd += ["--embed"]
    rc, so, se = run(gp_cmd)
    steps.append({"step": "gain_probe", "exit_code": rc, "stdout": so, "stderr": se})
    if rc != 0:
        problems.append("gain_probe 退出码非 0: %s" % rc)

    # 3) 效率计数（写回 result.json）
    ep_cmd = [py, os.path.join(HERE, "efficiency_probe.py"),
              "--result", args.result,
              "--out", os.path.join(args.work, "efficiency.json")]
    if args.workorder:
        ep_cmd += ["--workorder", args.workorder]
    if args.embed:
        ep_cmd += ["--embed"]
    rc, so, se = run(ep_cmd)
    steps.append({"step": "efficiency_probe", "exit_code": rc, "stdout": so, "stderr": se})
    if rc != 0:
        problems.append("efficiency_probe 退出码非 0: %s" % rc)

    # 4) 校验（--embed 先按结构性结论回填三元组，再校验 verification，单遍自洽）
    report_path = os.path.join(args.work, "check_report.json")
    ck_cmd = [py, os.path.join(HERE, "check_result.py"),
              "--result", args.result, "--out", report_path,
              "--case", args.case]
    if args.workorder:
        ck_cmd += ["--workorder", args.workorder]
    if args.embed:
        ck_cmd += ["--embed"]
    rc, so, se = run(ck_cmd)
    steps.append({"step": "check_result", "exit_code": rc, "stdout": so, "stderr": se})
    if rc != 0:
        problems.append("check_result 退出码非 0: %s" % rc)

    verdict = "unknown"
    problems_count = 0
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            rep = json.load(f)
        verdict = rep.get("verdict")
        problems_count = len(rep.get("problems") or [])
    except Exception as e:
        problems.append("校验报告不可读: %s" % e)

    print("[run_pipeline] verdict=%s problems=%d work=%s" % (
        verdict, problems_count, args.work))
    for s in steps:
        print("  %-38s exit=%d" % (s["step"], s["exit_code"]))
        for line in (s["stdout"] or "").splitlines()[:12]:
            print("    %s" % line)
        if s["stderr"]:
            print("    stderr: %s" % s["stderr"][:300])
    for p in problems:
        print("  ! %s" % p)
    return 0


if __name__ == "__main__":
    run_entry(main, "run_pipeline")
