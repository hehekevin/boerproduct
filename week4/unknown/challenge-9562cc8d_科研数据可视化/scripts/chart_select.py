#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chart_select.py — 图型选择引擎：数据画像 → 意图识别 → 候选图型+推荐理由+不推荐理由。

用法:
  python3 chart_select.py --data data.csv --task task.md --out chart_selection.json
  （--no-rationale 为消融开关：剥离推荐/排除理由，供 gain_probe 对照实测）

规则库（分析目的 → 图型）:
  趋势/时间序列 → 折线；构成 → 堆叠柱(>5类或需精确读数时拒绝饼图)；
  分布 → 直方图；关系/相关 → 散点；分组比较 → 柱状。
编码原则：优先位置/长度编码，拒绝角度/面积夸大差异。
退出码恒 0，结论写进 JSON。
"""
import argparse, csv, json, os, re, sys

# CHARTVIZ-MARKER: chart_select

INTENT_PATTERNS = [
    ("trend", r"趋势|随.{0,6}变化|时间|序列|over\s+time|trend|time\s*series|变化率"),
    ("distribution", r"分布|频数|直方|histogram|distribution|离散|波动"),
    ("relation", r"关系|相关|散点|关联|scatter|correlat|relationship|vs\.?|versus"),
    ("composition", r"构成|占比|组成|比例|份额|composition|proportion|share|percent"),
    ("comparison", r"比较|对比|差异|组间|compare|comparison|between\s+groups|versus\s+groups"),
]
ASCII_NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
DATE_LIKE = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?([ T]\d{2}:\d{2})?$|^\d{1,2}[-/]\d{1,2}[-/]\d{4}$")

# 防汉字陷阱：禁止用 str.isalpha 判定文本列（'中文'.isalpha() 为 True，
# 会把中文列名/类别误判为纯字母文本）。统一用 ASCII 正则显式判定。


def is_number(s):
    return bool(ASCII_NUM.match(s.strip()))


def profile_column(values):
    vals = [v.strip() for v in values if v is not None and str(v).strip() != ""]
    missing = len(values) - len(vals)
    nums = [float(v) for v in vals if is_number(v)]
    uniq = sorted(set(vals))
    if nums and len(nums) >= 0.8 * max(1, len(vals)):
        return {"type": "numeric", "unique": len(uniq), "missing": missing,
                "min": min(nums), "max": max(nums)}
    if vals and all(DATE_LIKE.match(v) for v in vals):
        return {"type": "datetime", "unique": len(uniq), "missing": missing}
    if vals and 2 <= len(uniq) <= max(2, int(0.5 * len(vals))) and len(uniq) <= 20:
        return {"type": "categorical", "unique": len(uniq), "missing": missing,
                "categories": uniq}
    return {"type": "id_or_text", "unique": len(uniq), "missing": missing}


def detect_intent(task_text):
    t = task_text or ""
    hits = []
    for name, pat in INTENT_PATTERNS:
        m = re.search(pat, t, re.I)
        if m:
            hits.append((name, m.group(0)))
    return hits


def rule_candidates(profile, intent_hits, no_rationale=False):
    types = [c["type"] for c in profile]
    has_dt = "datetime" in types
    has_cat = "categorical" in types
    nums = [c for c in profile if c["type"] == "numeric"]
    cands, rejected = [], []

    def add(chart, score, why):
        cands.append({"chart": chart, "score": score,
                      "rationale": "" if no_rationale else why,
                      "encoding": "" if no_rationale else
                      "位置/长度编码优先，禁用角度与面积夸大差异"})

    if intent_hits:
        top = intent_hits[0][0]
        if top == "trend" and has_dt and nums:
            add("line", 0.95, "检测到时间/趋势意图且含 datetime 列：位置沿时间轴编码，最能保留连续趋势")
            add("scatter", 0.6, "次选：横轴为时间时散点可看离散程度，但丢失顺序连接性")
        elif top == "relation" and len(nums) >= 2:
            add("scatter", 0.95, "检测到关系/相关意图且有两个数值列：双位置编码最忠实于逐点数据")
        elif top == "distribution" and nums:
            add("histogram", 0.95, "检测到分布意图且有数值列：分箱+长度编码直方图展示频数分布")
            add("box", 0.5, "次选：箱线图概括分位数，但丢失分布形状细节")
        elif top == "composition" and has_cat and nums:
            add("stacked_bar", 0.9, "检测到构成意图且有分类+数值列：堆叠柱长度编码，类别数多时优于饼图")
        elif top == "comparison" and has_cat and nums:
            add("bar", 0.95, "检测到比较意图且有分类+数值列：柱长编码跨组比较最直观")
        if not intent_hits or not cands:
            add(*_structural_fallback(profile))
    else:
        add(*_structural_fallback(profile))

    # 不推荐理由（机械可查）
    def rej(chart, why):
        rejected.append({"chart": chart, "reason": "" if no_rationale else why})
    if "pie" not in [c["chart"] for c in cands]:
        ncat = next((c["unique"] for c in profile if c["type"] == "categorical"), 0)
        if ncat > 5:
            rej("pie", f"分类数 {ncat} > 5，饼图角度编码读数误差大且扇区过多")
        else:
            rej("pie", "角度/面积编码读数不精确；如需构成请用堆叠柱长度编码")
    if not has_dt and any(c["chart"] == "line" for c in cands) is False and has_cat:
        rej("line", "横轴为无序分类时折线会虚构顺序趋势")
    if not has_dt:
        rej("time_series_plot", "数据不含 datetime 列，无法构成时间序列图")
    if len(nums) < 2:
        rej("scatter", "数值列不足两列，散点图缺少第二维")
    if any(c["chart"] == "histogram" for c in cands) is False and nums:
        rej("histogram", "本任务非分布考察，直方图会掩盖组间比较信息" if not no_rationale else "")
    return cands, rejected


def _structural_fallback(profile):
    types = [c["type"] for c in profile]
    if "datetime" in types:
        return ("line", 0.7, "含 datetime 列：结构推断为时间序列，默认折线")
    if "categorical" in types:
        return ("bar", 0.7, "含分类+数值列：结构推断为跨组比较，默认柱状图")
    if sum(1 for c in profile if c["type"] == "numeric") >= 2:
        return ("scatter", 0.7, "两个及以上数值列：结构推断为关系考察，默认散点")
    return ("histogram", 0.6, "单数值列：结构推断为分布考察，默认直方图")


def build_selection(rows, header, task_text, no_rationale=False):
    profile = [dict(profile_column([r[h] for r in rows]), name=h) for h in header]
    intent = detect_intent(task_text)
    cands, rejected = rule_candidates(profile, intent, no_rationale)
    cands.sort(key=lambda c: -c["score"])
    return {"columns": profile, "intent_hits": intent,
            "recommended": cands[0]["chart"] if cands else "bar",
            "candidates": cands, "rejected": rejected,
            "rationale_coverage": round(
                sum(1 for c in cands if c["rationale"]) / max(1, len(cands)), 3),
            "mode": "ablated_no_rationale" if no_rationale else "full"}


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = list(csv.reader(f))
    header = rd[0]
    rows = [{h: r[i] if i < len(r) else "" for i, h in enumerate(header)}
            for r in rd[1:] if any(c.strip() for c in r)]
    return rows, header


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--out", default="chart_selection.json")
    ap.add_argument("--no-rationale", action="store_true", help="消融开关")
    args = ap.parse_args()
    out = {"ok": False, "data": os.path.basename(args.data)}
    try:
        rows, header = read_csv(args.data)
        task_text = ""
        if args.task and os.path.exists(args.task):
            task_text = open(args.task, encoding="utf-8", errors="ignore").read()
        sel = build_selection(rows, header, task_text, args.no_rationale)
        sel["n_rows"] = len(rows)
        out.update(sel)
        out["ok"] = True
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        out["written"] = args.out
    except Exception as e:
        out["error"] = str(e)
        out["status"] = "chart_select_failed"
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out.get(k) for k in ("ok", "recommended", "error",
                                              "rationale_coverage", "mode")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
