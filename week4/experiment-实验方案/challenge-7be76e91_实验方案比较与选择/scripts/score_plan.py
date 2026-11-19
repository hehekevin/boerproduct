#!/usr/bin/env python3
"""score_plan.py — 候选实验方案五维机械打分、确定性排序与敏感性分析（exp-plan-compare）。

从 result.json 读取 result.rubric（事前声明的五维权重：scientific_value /
feasibility / cost / duration / risk_control，合计=1.0）与 result.plan_versions[]
（组织方给定的候选方案），机械复算每个方案的 fused_score（保留 4 位小数），
按平局规则（fused_score 降序 → risk_control 降序 → plan_id 升序）产出稳定可复现
的排序：写 result.plan_ranking（ordered_ids / ties / top_k / k_value）与
plan_versions[].fused_score / plan_versions[].rank。同分条目全部记入 ties，
不静默破坏平局。

同时做权重敏感性分析（--no-sensitivity 关闭）：对每个维度权重施加
±0.05/±0.10/±0.15/±0.20 扰动（其余四维按比例归一），逐个变体机械复算 winner，
写 result.sensitivity（variants / flip_conditions / overall_stable）。

**键归属**：本脚本只写 result.plan_ranking、result.sensitivity、
plan_versions[].fused_score、plan_versions[].rank；其余键一律不碰
（多脚本禁写同一键）。

用法：
    python3 score_plan.py --result /app/output/result.json [--k 1]
        [--no-sensitivity] [--dry-run]
    --dry-run 只打印对照不写盘。
退出码恒为 0（结论记在 stdout 与返回对象，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

WEIGHT_KEYS = ("scientific_value", "feasibility", "cost", "duration", "risk_control")
DELTAS = (0.05, 0.10, 0.15, 0.20)


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
        print("[score_plan] 写盘失败 %s: %s" % (path, e))
        return False


def weights_ok(rubric):
    """五维权重校验：均为非负数值且合计=1.0。返回权重 dict 或 None。"""
    w = (rubric or {}).get("weights") or {}
    vals = {}
    for k in WEIGHT_KEYS:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals[k] = float(v)
    if abs(sum(vals.values()) - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    """机械融合 fused = Σ w_i * f_i（保留 4 位小数）；任一因子缺失返回 None。"""
    if not isinstance(factors, dict):
        return None
    total = 0.0
    for k in WEIGHT_KEYS:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        total += weights[k] * float(v)
    return round(total, 4)


def scored_pairs(versions, weights):
    """返回 [(plan_id, fused_score, risk_control)]，只含 factors 完整的方案。"""
    out = []
    for v in versions:
        pid = str(v.get("plan_id") or "plan_versions[%d]" % len(out))
        s = fused(weights, v.get("factors"))
        if s is None:
            continue
        rc = (v.get("factors") or {}).get("risk_control")
        out.append((pid, s, float(rc) if isinstance(rc, (int, float))
                    and not isinstance(rc, bool) else 0.0))
    return out


def order_ids(scored):
    """平局规则：fused_score 降序 → risk_control 降序 → plan_id 升序。"""
    return [p for p, _s, _r in sorted(scored, key=lambda t: (-t[1], -t[2], t[0]))]


def compute_sensitivity(versions, weights):
    """机械敏感性分析：对每个维度权重施加 ±DELTAS 扰动（其余维度按比例归一），
    逐变体复算 winner。返回 dict（available / variants / flip_conditions /
    overall_stable）。可被 verify_check 导入复算，保证口径一致。"""
    base = scored_pairs(versions, weights)
    if len(base) < 2:
        return {"available": False,
                "reason": "可参与复算的候选方案 %d 个（<2），敏感性分析无意义" % len(base),
                "base_winner": order_ids(base)[0] if base else None,
                "variants": [], "flip_conditions": [], "overall_stable": None}
    base_winner = order_ids(base)[0]
    wkeys = list(WEIGHT_KEYS)
    wvals = [float(weights[k]) for k in wkeys]
    variants, flips = [], []
    for dim_idx, dim in enumerate(wkeys):
        min_flip = None
        for sign in ("+", "-"):
            for d in DELTAS:
                new = list(wvals)
                new[dim_idx] = max(0.0, new[dim_idx] + (d if sign == "+" else -d))
                s = sum(new)
                new = [round(x / s, 6) for x in new]
                nw = dict(zip(wkeys, new))
                ordered = order_ids(scored_pairs(versions, nw))
                winner = ordered[0] if ordered else None
                changed = bool(winner) and winner != base_winner
                variants.append({"variant": "%s%s%.2f" % (dim, sign, d),
                                 "weights": nw, "winner_id": winner,
                                 "winner_changed": changed})
                if changed and min_flip is None:
                    min_flip = {"dim": dim, "direction": sign,
                                "min_flip_delta": d, "winner_after": winner}
        if min_flip:
            flips.append(min_flip)
    return {"available": True,
            "method": "对每个维度权重施加 ±0.05/0.10/0.15/0.20 扰动（其余四维按比例归一），"
                      "按主排序同一平局规则复算 winner",
            "base_winner": base_winner, "variants": variants,
            "flip_conditions": flips,
            "overall_stable": all(not v["winner_changed"] for v in variants),
            "note": "winner_changed=true 的变体即选择结论翻转的权重条件；"
                    "overall_stable=false 时须在 final_choice.reasons 说明翻转条件"}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--k", type=int, default=None, help="top_k，默认取全部")
        ap.add_argument("--no-sensitivity", action="store_true")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[score_plan] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[score_plan] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）"
              % args.result)
        return 0
    inner = res["result"]
    versions = [v for v in (inner.get("plan_versions") or []) if isinstance(v, dict)]
    weights = weights_ok(inner.get("rubric") or {})
    if weights is None:
        print("[score_plan] FAIL: rubric 五维权重未事前声明或非法（非负数值且合计=1.0）"
              "——不排序、不写盘（不中断交付）")
        return 0

    problems = []
    scored = scored_pairs(versions, weights)
    for v in versions:
        pid = str(v.get("plan_id") or "")
        if not pid or fused(weights, v.get("factors")) is None:
            problems.append("%r factors 缺失或非法（五维 0-1 数值），不参与排序"
                            % (pid or v.get("plan_id")))
    ordered = order_ids(scored)
    rank_map = {p: i + 1 for i, p in enumerate(ordered)}
    for v in versions:
        pid = str(v.get("plan_id") or "")
        s = fused(weights, v.get("factors"))
        if s is not None:
            v["fused_score"] = s
            v["rank"] = rank_map.get(pid)
        print("  plan %s  fused_score=%s  rank=%s" % (pid, v.get("fused_score"), v.get("rank")))
    if len(scored) < 2:
        problems.append("可参与复算的候选方案 %d 个（<2），无法构成比较" % len(scored))

    ties = []
    by_score = {}
    for pid, s, _r in scored:
        by_score.setdefault(s, []).append(pid)
    for s, pids in sorted(by_score.items(), reverse=True):
        if len(pids) > 1:
            ties.append({"fused_score": s, "plan_ids": sorted(pids),
                         "rule": "risk_control 降序 → plan_id 升序"})

    k = args.k if args.k else len(ordered)
    inner["plan_ranking"] = {"ordered_ids": ordered, "ties": ties,
                             "top_k": ordered[:k], "k_value": k,
                             "tie_break_rule": "fused_score 降序 → risk_control 降序 → plan_id 升序"}

    if not args.no_sensitivity:
        inner["sensitivity"] = compute_sensitivity(versions, weights)
        sens = inner["sensitivity"]
        if sens.get("available"):
            print("  敏感性: base_winner=%s overall_stable=%s 变体 %d 个 翻转条件 %d 条"
                  % (sens.get("base_winner"), sens.get("overall_stable"),
                     len(sens.get("variants") or []), len(sens.get("flip_conditions") or [])))

    if not args.dry_run:
        save_json(args.result, res)
        print("[score_plan] 已回写 result.plan_ranking / sensitivity / fused_score / rank"
              "（%d 个方案）" % len(ordered))
    else:
        print("[score_plan] --dry-run 未写盘")
    for p in problems:
        print("  WARN: %s" % p)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[score_plan] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
