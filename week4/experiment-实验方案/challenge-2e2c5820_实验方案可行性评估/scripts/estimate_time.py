#!/usr/bin/env python3
"""estimate_time.py — Step 3 机械时间成本汇总（feas-review）。

读取 result.json 的 result.time_estimate.rows（Agent 在 Step 2 按方案步骤拆解的
{plan_id, step_id, equipment_h, labor_h, wait_h}），机械复算每行 total_h 与
每方案合计 totals（保留 2 位小数），回写 result.time_estimate。键归属：本脚本
只写 result.time_estimate（rows[].total_h / totals / computed_by）；分级判定与
证据归 Agent，校验归 verify_check.py。

估算口径（可解释）：总时长 = 设备占用 + 人工操作 + 等待周期（等待不占设备但占
排期），由 rows 逐行累加，无任何隐含系数；口径在 SKILL.md Step 3 声明。

退出码恒为 0（结论记在 stdout 与 result.time_estimate.note，不中断交付）。
用法：
    python3 estimate_time.py --result /app/output/result.json [--check]
"""
from __future__ import annotations

import argparse
import json
import os
import sys


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
        print("[estimate_time] 写盘失败 %s: %s" % (path, e))
        return False


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def recompute(rows):
    """纯函数：机械复算每行 total 与每方案合计。返回 (rows_out, totals, problems)。"""
    problems = []
    rows_out = []
    totals = {}
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            problems.append("rows[%d] 不是对象，跳过" % i)
            continue
        vals = [_num(r.get(k)) for k in ("equipment_h", "labor_h", "wait_h")]
        if any(v is None for v in vals):
            problems.append("rows[%d]（%s/%s）缺少数值型 equipment_h/labor_h/wait_h，本行不计入合计"
                            % (i, r.get("plan_id"), r.get("step_id")))
            rows_out.append(dict(r, total_h=None))
            continue
        total = round(sum(vals), 2)
        pid = str(r.get("plan_id") or "unknown")
        rows_out.append(dict(r, total_h=total))
        totals[pid] = round(totals.get(pid, 0.0) + total, 2)
    return rows_out, totals, problems


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--check", action="store_true",
                        help="只复算对照不回写（用于自检与增益对照）")
        args = ap.parse_args()
    except Exception as e:
        print("[estimate_time] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[estimate_time] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）"
              % args.result)
        return 0

    inner = res["result"]
    est = inner.get("time_estimate") if isinstance(inner.get("time_estimate"), dict) else {}
    rows = est.get("rows") if isinstance(est, dict) else None
    rows_out, totals, problems = recompute(rows)
    n_rows = sum(1 for r in rows_out if r.get("total_h") is not None)

    if not problems and n_rows == 0:
        problems.append("time_estimate.rows 为空：请先在 Step 2 按方案步骤拆解时间行"
                        "（plan_id/step_id/equipment_h/labor_h/wait_h），再跑本脚本")

    if not args.check and rows is not None:
        est["rows"] = rows_out
        est["totals"] = totals
        est["computed_by"] = "scripts/estimate_time.py（机械累加：total_h=equipment_h+labor_h+wait_h）"
        est["note"] = ("可解释估算：等待周期不占设备但占排期；无隐含系数；"
                       if not problems else "存在未计入行（见 stdout problems）；") + \
                      "时间数字须在 claims 中回证（verify_check 复核）"
        save_json(args.result, res)

    if problems:
        print("[estimate_time] FAIL（%d 处，不中断交付）:" % len(problems))
        for p in problems[:20]:
            print("  - %s" % p)
        return 0

    print("[estimate_time] PASS: 复算 %d 行 / %d 个方案合计 %s"
          % (n_rows, len(totals), json.dumps(totals, ensure_ascii=False)))
    if not args.check:
        print("[estimate_time] 已回写 result.time_estimate（rows[].total_h + totals）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[estimate_time] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
