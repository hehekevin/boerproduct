#!/usr/bin/env python3
"""trend_engine.py — 机械趋势引擎（trend-frontier-analyst，challenge-073af7d3）。

把三件不能靠"关键词热度自述"的事机械落定：
  1. 主题归属：按事前声明的关键词簇（clustering_policy.clusters）逐条机械分配，
     标题归一化 casefold + 非字母数字折叠为空格（\\w 含 CJK，禁用 isalpha 判字），
     按簇声明顺序首个命中即归属；未命中 → topic_id=null（unassigned，须登记待复核）。
  2. 年度计数与增速：按 trend_policy.window（start_year/end_year）统计每主题
     yearly_counts；mid=(S+E)//2，early=[S..mid]，late=[mid+1..E]；
     growth_rate=(late_avg-early_avg)/early_avg（early_avg=0 且 late_avg>0 记 1.0，
     两者皆 0 记 0.0），四舍五入 4 位。
  3. 阶段分级：growth_rate >= emerging_min_growth → emerging；
     growth_rate <= declining_max_growth → declining；否则 mature；主题无条目 →
     no_evidence（不得参与分级叙事）。阈值为事前声明口径，分级机械可复算。
另落定：extrapolation 外推边界（默认禁止外推，须登记 rule）与 coverage 计数。

被 verify_check.py / gain_probe.py 复用同一函数实现（口径一致才可信）。
退出码恒为 0（问题以 WARN 打印，不中断交付）。
用法：
    python3 trend_engine.py --result /app/output/result.json [--case /input/case.json] [--out 报告路径]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

STAGES = ("emerging", "mature", "declining", "no_evidence")

DEFAULT_THRESHOLDS = {"emerging_min_growth": 0.5, "declining_max_growth": -0.34}


def norm_text(s):
    """标题归一化：casefold + 非 \\w 字符折叠为空格（\\w 含 CJK，不用 isalpha）。"""
    return re.sub(r"\s+", " ", re.sub(r"[^\w]+", " ", str(s or "").casefold())).strip()


def item_text(it):
    """参与关键词匹配的条目文本：标题 + 摘要摘录（如有）。"""
    parts = [str(it.get("title") or ""), str(it.get("abstract") or "")]
    return " ".join(p for p in parts if p.strip())


def year_of(it):
    """取年份：优先显式 year 字段，否则取 published_date 前 4 位数字。"""
    y = it.get("year")
    if isinstance(y, int) and 1500 < y < 2200:
        return y
    m = re.match(r"(\d{4})", str(it.get("published_date") or ""))
    return int(m.group(1)) if m else None


def assign_topic(it, clusters):
    """按簇声明顺序首个关键词命中即归属。返回 (topic_id, matched_keyword)。"""
    text = norm_text(item_text(it))
    for cl in clusters or []:
        if not isinstance(cl, dict):
            continue
        for kw in cl.get("keywords") or []:
            nkw = norm_text(kw)
            if nkw and nkw in text:
                return str(cl.get("topic_id") or ""), str(kw)
    return None, None


def cluster_of(topic_id, clusters):
    for cl in clusters or []:
        if isinstance(cl, dict) and str(cl.get("topic_id")) == str(topic_id):
            return cl
    return None


def split_window(S, E):
    """mid=(S+E)//2；early=[S..mid]，late=[mid+1..E]。"""
    S, E = int(S), int(E)
    mid = (S + E) // 2
    return list(range(S, mid + 1)), list(range(mid + 1, E + 1))


def growth_of(counts, window):
    """counts: {year(int): n}。返回 dict(early_years, late_years, early_avg, late_avg, growth_rate)。"""
    S, E = int(window.get("start_year")), int(window.get("end_year"))
    early_years, late_years = split_window(S, E)
    ec = sum(int(counts.get(y, 0)) for y in early_years)
    lc = sum(int(counts.get(y, 0)) for y in late_years)
    early_avg = ec / float(len(early_years)) if early_years else 0.0
    late_avg = lc / float(len(late_years)) if late_years else 0.0
    if early_avg > 0:
        growth = (late_avg - early_avg) / early_avg
    elif late_avg > 0:
        growth = 1.0
    else:
        growth = 0.0
    return {"early_years": early_years, "late_years": late_years,
            "early_avg": round(early_avg, 4), "late_avg": round(late_avg, 4),
            "growth_rate": round(growth, 4)}


def thresholds_of(trend_policy):
    th = (trend_policy or {}).get("thresholds") or {}
    try:
        em = float(th.get("emerging_min_growth", DEFAULT_THRESHOLDS["emerging_min_growth"]))
        de = float(th.get("declining_max_growth", DEFAULT_THRESHOLDS["declining_max_growth"]))
    except Exception:
        em, de = DEFAULT_THRESHOLDS["emerging_min_growth"], DEFAULT_THRESHOLDS["declining_max_growth"]
    return em, de


def stage_of(growth, em_th, de_th):
    if growth >= em_th:
        return "emerging"
    if growth <= de_th:
        return "declining"
    return "mature"


def yearly_counts(items, topic_id, window):
    S, E = int(window.get("start_year")), int(window.get("end_year"))
    counts = {}
    for it in items:
        if str(it.get("topic_id") or "") != str(topic_id):
            continue
        y = year_of(it)
        if y is not None and S <= y <= E:
            counts[y] = counts.get(y, 0) + 1
    return counts


def build_topics(items, clustering, trend_policy):
    """机械构建 topics[]（与 verify_check 复算同一实现，口径一致）。"""
    clusters = (clustering or {}).get("clusters") or []
    window = (trend_policy or {}).get("window") or {}
    em_th, de_th = thresholds_of(trend_policy)
    topics = []
    if not (isinstance(window.get("start_year"), int) and isinstance(window.get("end_year"), int)
            and window["start_year"] <= window["end_year"]):
        return topics, "trend_policy.window 非法或缺失，趋势计数未计算"
    for cl in clusters:
        tid = str(cl.get("topic_id") or "")
        members = [it for it in items if str(it.get("topic_id") or "") == tid]
        counts = yearly_counts(items, tid, window)
        g = growth_of(counts, window)
        if members:
            stage = stage_of(g["growth_rate"], em_th, de_th)
        else:
            stage = "no_evidence"
        reps = [str(r) for r in (cl.get("representative_seed") or [])]
        topics.append({
            "topic_id": tid, "label": cl.get("label"),
            "keywords": list(cl.get("keywords") or []),
            "item_ids": [str(it.get("item_id")) for it in members],
            "total_count": len(members),
            "yearly_counts": {str(y): int(counts.get(y, 0))
                              for y in range(int(window["start_year"]), int(window["end_year"]) + 1)},
            "early_avg": g["early_avg"], "late_avg": g["late_avg"],
            "growth_rate": g["growth_rate"], "stage": stage,
            "stage_basis": "growth_rate=%.4f；emerging>= %s / declining<= %s（事前阈值）"
                           % (g["growth_rate"], em_th, de_th),
            "representative_ids": reps,
        })
    return topics, ""


def extrapolation_default():
    return {"allowed": False,
            "rule": "仅报告观测窗口内趋势，不做趋势外推；如需外推须登记人工确认与边界条件",
            "registered_at": "step3"}


def build_coverage(items, topics):
    cov = {
        "total": len(items),
        "judged": sum(1 for it in items if it.get("judged") is True),
        "core": sum(1 for it in items if it.get("relevance") == "core"),
        "related": sum(1 for it in items if it.get("relevance") == "related"),
        "irrelevant": sum(1 for it in items if it.get("relevance") == "irrelevant"),
        "unassigned": sum(1 for it in items if it.get("judged") is True and not it.get("topic_id")),
        "topics_count": sum(1 for t in topics if t.get("total_count", 0) > 0),
        "ratio": None,
    }
    cov["ratio"] = round(cov["judged"] / cov["total"], 4) if cov["total"] else None
    return cov


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        args = ap.parse_args()
    except Exception as e:
        print("[trend_engine] 参数解析失败（已降级）: %s" % e)
        return 0

    warns = []
    res = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[trend_engine] FAIL: result.json 不可解析: %s（不中断交付）" % e)
        return 0

    inner = res.get("result") if isinstance(res, dict) else None
    if not isinstance(inner, dict):
        print("[trend_engine] FAIL: result 非对象（不中断交付）")
        return 0
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    clustering = inner.get("clustering_policy") or {}
    trend_policy = inner.get("trend_policy") or {}
    if not (clustering.get("clusters") or []):
        warns.append("clustering_policy.clusters 为空：请先在 Step 1 事前声明关键词簇")
    if not (trend_policy.get("window") or {}).get("start_year"):
        warns.append("trend_policy.window 缺失：请先声明观测窗口 start_year/end_year")

    topics, note = build_topics(items, clustering, trend_policy)
    if note:
        warns.append(note)
    inner["topics"] = topics
    if not inner.get("extrapolation"):
        inner["extrapolation"] = extrapolation_default()
    inner["coverage"] = build_coverage(items, topics)

    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[trend_engine] 回写失败: %s（不中断交付）" % e)
        return 0

    for t in topics:
        print("  topic %s %-14s count=%-3s growth=%-8s stage=%s reps=%s"
              % (t["topic_id"], str(t.get("label"))[:14], t["total_count"],
                 t["growth_rate"], t["stage"], ",".join(t["representative_ids"])))
    for w in warns:
        print("  WARN: %s" % w)
    print("[trend_engine] topics=%d coverage=%s 已回写: %s"
          % (len(topics), json.dumps(inner.get("coverage"), ensure_ascii=False), args.result))
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"ok": True, "warns": warns, "topics": len(topics)}, f,
                          ensure_ascii=False, indent=1)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[trend_engine] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
