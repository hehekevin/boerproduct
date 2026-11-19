#!/usr/bin/env python3
"""score_strategy.py — 候选寻优策略多因子打分与确定性排序引擎（exp-param-optimize）。

从 result.json 读取 result.rubric（事前声明的四因子权重）与
result.strategy_versions[].factors，机械复算 fused_score =
w_i*information_gain + w_c*cost_efficiency + w_r*robustness +
w_k*risk_coverage（保留4位小数），按平局规则（fused_score 降序 →
cost_efficiency 降序 → version_id 升序）产出稳定可复现的排序：写
result.strategy_ranking（ordered_ids / ties / top_k / k_value）与
strategy_versions[].fused_score、strategy_versions[].rank。同名分条目全部
记入 ties，不静默破坏平局。

**键归属**：本脚本只写 result.strategy_ranking、strategy_versions[].fused_score、
strategy_versions[].rank；其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 score_strategy.py --result /app/output/result.json [--k 1] [--dry-run]
    --dry-run 只打印对照不写盘。
退出码恒为 0（结论记在 report verdict 字段与 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

WEIGHT_KEYS = ("information_gain", "cost_efficiency", "robustness", "risk_coverage")


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
        print("[score_strategy] 写盘失败 %s: %s" % (path, e))
        return False


def weights_ok(rubric):
    w = (rubric or {}).get("weights") or {}
    vals = []
    for k in WEIGHT_KEYS:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals.append(float(v))
    total = sum(vals)
    if abs(total - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    """机械融合：返回 round(w·f, 4)；任一因子缺失返回 None。"""
    if not isinstance(factors, dict):
        return None
    vals = []
    for k in WEIGHT_KEYS:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        vals.append(float(v))
    return round(sum(wi * vi for wi, vi in zip(weights, vals)), 4)


def rank_versions(versions, weights):
    """复算分数 + 确定性排序。返回 (report, updates)。"""
    problems, updates, scores = [], {}, []
    for v in versions:
        vid = str(v.get("version_id") or "versions[%d]" % len(scores))
        s = fused(weights, v.get("factors"))
        if s is None:
            problems.append("%s factors 缺失或非法（四因子 0-1 数值），不参与排序" % vid)
            continue
        scores.append((vid, s, float(v["factors"].get("cost_efficiency") or 0.0)))
        updates.setdefault(vid, {})["fused_score"] = s
    # 平局规则：fused_score 降序 → cost_efficiency 降序 → version_id 升序
    ordered = [p for p, _s, _f in sorted(scores, key=lambda t: (-t[1], -t[2], t[0]))]
    rank_map = {p: i + 1 for i, p in enumerate(ordered)}
    for vid, s, _f in scores:
        updates[vid]["rank"] = rank_map[vid]
    ties = []
    by_score = {}
    for vid, s, _f in scores:
        by_score.setdefault(s, []).append(vid)
    for s, gids in sorted(by_score.items(), reverse=True):
        if len(gids) > 1:
            ties.append({"fused_score": s, "version_ids": sorted(gids),
                         "rule": "cost_efficiency 降序 → version_id 升序"})
    return {"verdict": "PASS" if ordered else "FAIL", "problems": problems,
            "ordered_ids": ordered, "ties": ties}, updates


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--k", type=int, default=None, help="top_k，默认取全部已排序版本")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[score_strategy] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[score_strategy] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）"
              % args.result)
        return 0
    inner = res["result"]
    versions = [v for v in (inner.get("strategy_versions") or []) if isinstance(v, dict)]
    weights = weights_ok(inner.get("rubric") or {})
    if weights is None:
        print("[score_strategy] FAIL: rubric 权重未事前声明或非法（四因子 0-1 且合计=1.0）"
              "——不排序、不写盘（不中断交付）")
        return 0

    report, updates = rank_versions(versions, weights)
    for v in versions:
        vid = str(v.get("version_id") or "")
        if vid in updates:
            v["fused_score"] = updates[vid]["fused_score"]
            v["rank"] = updates[vid]["rank"]
        print("  strategy %s  fused_score=%s  rank=%s"
              % (vid, v.get("fused_score"), v.get("rank")))

    ordered = report["ordered_ids"]
    k = args.k if args.k else len(ordered)
    inner["strategy_ranking"] = {
        "ordered_ids": ordered,
        "ties": report["ties"],
        "top_k": ordered[:k],
        "k_value": k,
    }
    if not args.dry_run:
        save_json(args.result, res)
        print("[score_strategy] %s：已回写 result.strategy_ranking / fused_score / rank（%d 个策略）"
              % (report["verdict"], len(ordered)))
    else:
        print("[score_strategy] %s：--dry-run 未写盘" % report["verdict"])
    for p in report["problems"]:
        print("  WARN: %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[score_strategy] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
