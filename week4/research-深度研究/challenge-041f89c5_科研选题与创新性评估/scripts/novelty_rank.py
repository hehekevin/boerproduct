#!/usr/bin/env python3
"""novelty_rank.py — 创新性三因子打分与确定性排序引擎（topic-novelty-audit）。

从 result.json 读取 result.rubric（事前声明的权重与分级口径）与
result.proposals[].factors，机械复算 fused_score = w_n*novelty + w_f*feasibility
+ w_e*evidence（保留4位小数），按平局规则（fused_score 降序 → novelty 因子降序
→ proposal_id 升序）产出稳定可复现的排序：写 result.ranking（ordered_ids /
ties / top_k / k_value）与 proposals[].fused_score、proposals[].rank。
同名分条目全部记入 ties，不静默破坏平局。

**键归属**：本脚本只写 result.ranking、proposals[].fused_score、proposals[].rank；
其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 novelty_rank.py --result /app/output/result.json [--k 5] [--dry-run]
    --dry-run 只打印对照不写盘。
退出码恒为 0（结论记在 stdout，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

WEIGHT_KEYS = ("novelty", "feasibility", "evidence")


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
        print("[novelty_rank] 写盘失败 %s: %s" % (path, e))
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


def rank_items(proposals, weights):
    """复算分数 + 确定性排序。返回 (problems, updates, ranking)。"""
    problems, updates, scores = [], {}, []
    for it in proposals:
        if not isinstance(it, dict):
            continue
        s = fused(weights, it.get("factors"))
        if s is None:
            problems.append("%s 因子缺失或非法（novelty/feasibility/evidence 须为 0-1 数值）"
                            % it.get("proposal_id"))
            continue
        updates[it.get("proposal_id")] = {"fused_score": s,
                                          "novelty": it.get("factors", {}).get("novelty")}
        scores.append((it.get("proposal_id"), s,
                       float(it.get("factors", {}).get("novelty") or 0.0)))

    # 平局规则：fused_score 降序 → novelty 因子降序 → proposal_id 升序
    # （proposal_id 字符串序比较，不用 isalpha 判断汉字）
    ordered = sorted(scores, key=lambda t: (-t[1], -t[2], str(t[0])))
    ties = {}
    for pid, s, _n in ordered:
        ties.setdefault(s, []).append(str(pid))
    tie_groups = [{"fused_score": s, "proposal_ids": ids,
                   "rule": "novelty 因子降序 → proposal_id 升序"}
                  for s, ids in sorted(ties.items(), reverse=True) if len(ids) > 1]

    ranked, rank_no, prev = [], 0, None
    for i, (pid, s, _n) in enumerate(ordered, 1):
        # 同分并列同名次（competition ranking）；分数不同则顺位连续
        rank_no = rank_no if prev is not None and s == prev else i
        ranked.append({"proposal_id": str(pid), "fused_score": s, "rank": rank_no})
        prev = s
    return problems, updates, {"ordered_ids": [r["proposal_id"] for r in ranked],
                               "ties": tie_groups, "ranked": ranked}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--k", type=int, default=None, help="top-k（缺省取已评估条目数）")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[novelty_rank] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[novelty_rank] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）" % args.result)
        return 0

    inner = res["result"]
    rubric = inner.get("rubric") or {}
    weights = weights_ok(rubric)
    if weights is None:
        print("[novelty_rank] FAIL: rubric 权重未声明/非法（三项 0-1 数值且合计=1.0）。"
              "分级/排序前必须先在 result.rubric 与 /app/work/rubric.json 事前声明。")
        return 0

    proposals = inner.get("proposals") or []
    problems, updates, ranking = rank_items(proposals, weights)
    k_value = args.k if args.k is not None else sum(
        1 for it in proposals if isinstance(it, dict) and it.get("judged") is True)
    ranking_out = {"ordered_ids": ranking["ordered_ids"], "ties": ranking["ties"],
                   "top_k": ranking["ordered_ids"][:max(k_value, 0)], "k_value": k_value,
                   "rubric_weights": dict(zip(WEIGHT_KEYS, weights)),
                   "tie_break": (rubric.get("tie_break")
                                 or ["fused_score 降序", "novelty 因子降序", "proposal_id 升序"])}

    print("[novelty_rank] 权重 novelty=%.2f feasibility=%.2f evidence=%.2f | 已复算 %d/%d 条"
          % (weights[0], weights[1], weights[2], len(updates), len(proposals)))
    for r in ranking["ranked"]:
        print("  #%02d  %s  fused=%s" % (r["rank"], r["proposal_id"], r["fused_score"]))
    if ranking["ties"]:
        print("  平局组 %d 组（同分按 novelty 因子降序、proposal_id 升序破平）" % len(ranking["ties"]))
    for p in problems:
        print("  WARN: %s" % p)

    if args.dry_run:
        print("[novelty_rank] dry-run：不写盘。")
        return 0
    if problems and not updates:
        print("[novelty_rank] FAIL: 无任何条目可复算（见 WARN），不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for it in ch_inner.get("proposals") or []:
        u = updates.get(it.get("proposal_id") if isinstance(it, dict) else None)
        if isinstance(it, dict) and u:
            it["fused_score"] = u["fused_score"]
    ch_inner["ranking"] = ranking_out
    if save_json(args.result, changed):
        print("[novelty_rank] 已回写 ranking / fused_score / rank → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[novelty_rank] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
