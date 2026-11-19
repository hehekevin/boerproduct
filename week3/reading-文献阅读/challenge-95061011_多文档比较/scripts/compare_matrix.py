#!/usr/bin/env python3
"""compare_matrix.py — 规则化跨文档对照器（r5）。

把 Agent 抽取好的 matrix（逐格 + 逐字证据）转成可复算的 pairwise 判定与冲突登记，
并提供 --ablate 退化开关，用于「同输入跑两遍」的对照取证。

用法：
    python3 compare_matrix.py --result R.json --workorder WO.json --out pair_full.json
    python3 compare_matrix.py --result R.json --workorder WO.json --ablate no_pairwise --out base1.json
    python3 compare_matrix.py --result R.json --workorder WO.json --ablate no_attribution --out base2.json

--ablate 取值：
    no_pairwise      退化模式A：关闭两两跨文档比对（只留逐篇抽取，无跨文档结论）
    no_attribution   退化模式B：关闭冲突归因（冲突仍登记，但不落归因维度）

输出为独立 JSON（不修改 --result），便于与正常模式产物做同输入对照。
所有异常降级不崩溃，失败路径 exit 0，问题写入 problems 字段。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cli_guard import SafeParser, run_entry, safe_parse_args  # noqa: E402

# 维度 → 关键词（匹配 field_id / definition / group / unit_expectation）
DIM_KEYWORDS = {
    "task": ["research_object", "objective", "goal", "task", "研究对象", "研究目标", "体系", "对象"],
    "metric": ["metric", "evaluation", "indicator", "capacity", "performance", "efficiency",
               "removal", "指标", "评价", "性能", "吸附量", "去除率"],
    "units": ["unit", "单位"],
    "material": ["material", "adsorbent", "catalyst", "membrane", "材料", "吸附剂", "催化剂", "膜"],
    "pollutant": ["pollutant", "dye", "target", "contaminant", "污染物", "染料", "目标物"],
    "budget": ["budget", "cost", "price", "energy", "剂量", "成本", "能耗", "用量"],
}
# 维度 → 字段组（关键词未命中时兜底）
DIM_GROUP_FALLBACK = {
    "task": ["对象"], "metric": ["指标"], "units": ["指标"],
    "material": ["对象"], "pollutant": ["对象"], "budget": ["条件"],
}
# 归因维度推断规则（按顺序匹配，先命中先决定）
ATTRIBUTION_RULES = [
    ("sample", ["sample_size", "dataset", "data_source", "样本", "数据集", "数据来源"]),
    ("method", ["method", "baseline", "model", "方法", "模型", "基线"]),
    ("condition", ["temperature", "ph", "condition", "contact_time", "温度", "pH", "条件", "时间"]),
    ("object", ["material", "adsorbent", "catalyst", "pollutant", "dye", "材料", "吸附剂", "污染物"]),
    ("metric", ["metric", "capacity", "removal", "指标", "吸附量", "去除率"]),
]
UNIT_SYNONYMS = {
    "mg g-1": "mg/g", "mg g^-1": "mg/g", "mg·g-1": "mg/g", "mg·g⁻¹": "mg/g",
    "g g-1": "g/g", "mg/l": "mg/l", "μg l-1": "ug/l",
}
VERDICTS = ("same", "partial", "different")


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def norm_text(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def norm_unit(s):
    u = norm_text(s).replace(" ", "")
    for k, v in UNIT_SYNONYMS.items():
        u = u.replace(k.replace(" ", ""), v)
    return u


def to_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v or ""))
    if m:
        try:
            return float(m.group(0))
        except Exception:
            return None
    return None


def tokens(s):
    t = re.sub(r"[()（）\[\]【】,，。;；:：/\\|\-_]", " ", norm_text(s))
    return set(x for x in t.split() if x)


def jaccard(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(len(ta | tb))


def alias_norm(value, aliases):
    """用字段字典 aliases 把论文内叫法折叠到标准字段值。"""
    v = norm_text(value)
    if not v or not aliases:
        return v
    for alias in aliases:
        a = norm_text(alias)
        if a and (v == a or a in v):
            return norm_text(aliases.get(alias, v))
    return v


def field_index(res):
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    idx = {}
    for f in inner.get("field_dictionary") or []:
        if isinstance(f, dict):
            fid = str(f.get("field_id") or "")
            if fid:
                idx[fid] = f
    return idx


def cell_map(res):
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    out = {}
    for c in inner.get("matrix") or []:
        if isinstance(c, dict):
            out[(str(c.get("field_id")), str(c.get("source_document_id")))] = c
    return out


def all_field_ids(cm, fdict):
    ids = set(k[0] for k in cm.keys())
    ids |= set(fdict.keys())
    return sorted(ids)


def fields_for(dimension, fdict, field_ids):
    kws = DIM_KEYWORDS.get(dimension, [])
    groups = DIM_GROUP_FALLBACK.get(dimension, [])
    picked = []
    for fid in field_ids:
        f = fdict.get(fid, {})
        hay = " ".join([norm_text(fid), norm_text(f.get("definition")),
                        norm_text(f.get("group")), norm_text(f.get("unit_expectation"))])
        if any(k.lower() in hay for k in kws):
            picked.append(fid)
    if picked:
        return picked
    for fid in field_ids:
        if norm_text(fdict.get(fid, {}).get("group")) in groups:
            picked.append(fid)
    return picked


def compare_pair(doc_a, doc_b, dimension, fields, cm, fdict):
    note_parts = []
    evid = []
    verdicts = []
    for fid in fields:
        ca = cm.get((fid, doc_a))
        cb = cm.get((fid, doc_b))
        if not ca or not cb:
            continue
        sa, sb = ca.get("cell_status"), cb.get("cell_status")
        if sa != "reported" or sb != "reported":
            note_parts.append("%s: %s/%s 未报告" % (fid, sa, sb))
            continue
        aliases = fdict.get(fid, {}).get("aliases")
        va = alias_norm(ca.get("value"), aliases)
        vb = alias_norm(cb.get("value"), aliases)
        if dimension == "units":
            ua, ub = norm_unit(ca.get("units")), norm_unit(cb.get("units"))
            if not ua and not ub:
                note_parts.append("%s: 双方均无单位" % fid)
                continue
            verdicts.append("same" if ua == ub else "different")
        else:
            na, nb = to_number(va), to_number(vb)
            if na is not None and nb is not None:
                if abs(na - nb) < 1e-9:
                    verdicts.append("same")
                elif min(abs(na), abs(nb)) > 0 and max(abs(na), abs(nb)) / min(abs(na), abs(nb)) <= 1.15:
                    verdicts.append("partial")
                else:
                    verdicts.append("different")
            elif va == vb:
                verdicts.append("same")
            else:
                j = jaccard(va, vb)
                verdicts.append("same" if j >= 0.75 else ("partial" if j >= 0.3 else "different"))
        for c in (ca, cb):
            e = c.get("evidence") or {}
            if e.get("source_document_id") and e.get("paragraph_id") and (e.get("quote") or "").strip():
                evid.append({"source_document_id": str(e.get("source_document_id")),
                             "paragraph_id": str(e.get("paragraph_id")),
                             "quote": str(e.get("quote"))})
    if not verdicts:
        return {"pair": [doc_a, doc_b], "dimension": dimension, "verdict": "not_judged",
                "note": "；".join(note_parts) or "该维度无可比较字段值（未报告/缺单位）",
                "evidence": []}
    if all(v == "same" for v in verdicts):
        verdict = "same"
    elif all(v == "different" for v in verdicts):
        verdict = "different"
    else:
        verdict = "partial"
    seen, uniq = set(), []
    for e in evid:
        key = (e["source_document_id"], e["paragraph_id"], e["quote"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    if len({e["source_document_id"] for e in uniq}) < 2:
        return {"pair": [doc_a, doc_b], "dimension": dimension, "verdict": "not_judged",
                "note": "可比较字段有值但缺少双方逐字引文，无法双文档绑定",
                "evidence": uniq}
    return {"pair": [doc_a, doc_b], "dimension": dimension, "verdict": verdict,
            "note": "；".join(note_parts) or "按字段值/单位/别名归一后逐字段判定",
            "evidence": uniq}


def infer_attribution(field_id, ca, cb):
    hay = norm_text(field_id)
    for dim, kws in ATTRIBUTION_RULES:
        for k in kws:
            if norm_text(k) in hay:
                return dim
    ctx_a = norm_text((ca or {}).get("context"))
    ctx_b = norm_text((cb or {}).get("context"))
    if ctx_a and ctx_b and ctx_a != ctx_b:
        return "condition"
    return "unattributable"


def build_conflicts(docs, cm):
    conflicts = []
    fids = sorted(set(k[0] for k in cm.keys()))
    for a, b in combinations(docs, 2):
        for fid in fids:
            ca, cb = cm.get((fid, a)), cm.get((fid, b))
            if not ca or not cb:
                continue
            if ca.get("cell_status") != "reported" or cb.get("cell_status") != "reported":
                continue
            va, vb = norm_text(ca.get("value")), norm_text(cb.get("value"))
            if not va or not vb or va == vb:
                continue
            na, nb = to_number(va), to_number(vb)
            if na is not None and nb is not None and \
                    abs(na - nb) / max(abs(na), abs(nb), 1e-9) < 0.15:
                continue
            ua, ub = norm_unit(ca.get("units")), norm_unit(cb.get("units"))
            dim = "metric" if (ua and ub and ua != ub) else infer_attribution(fid, ca, cb)
            quotes = []
            for c in (ca, cb):
                e = c.get("evidence") or {}
                if e.get("source_document_id") and (e.get("quote") or "").strip():
                    quotes.append({"source_document_id": str(e.get("source_document_id")),
                                   "paragraph_id": str(e.get("paragraph_id") or ""),
                                   "quote": str(e.get("quote"))})
            if len(quotes) < 2:
                continue
            conflicts.append({
                "what": "%s 取值差异：%s(%s) vs %s(%s)" % (
                    fid, va, ua or "无单位", vb, ub or "无单位"),
                "docs": ["%s@%s" % (ca.get("source_document_id"),
                                    (ca.get("evidence") or {}).get("paragraph_id")),
                         "%s@%s" % (cb.get("source_document_id"),
                                    (cb.get("evidence") or {}).get("paragraph_id"))],
                "attribution": "" if dim == "unattributable" else (
                    "单位/口径差异" if dim == "metric" else "字段 %s 所属维度差异" % fid),
                "attribution_dimension": dim,
                "quotes": quotes,
            })
    return conflicts


def read_workorder(path):
    if not path or not os.path.exists(path):
        return None
    return load_json(path)


def run_comparison(res, wo, ablate=None):
    """同输入执行一次对照。返回 artifacts dict（含 pairwise/conflicts/docs/dims/problems）。"""
    problems = []
    cm = cell_map(res)
    fdict = field_index(res)
    field_ids = all_field_ids(cm, fdict)

    docs = []
    for d in (wo or {}).get("documents") or (wo or {}).get("corpus") or []:
        sid = str((d.get("source_document_id") or d.get("id")) if isinstance(d, dict) else d)
        if sid:
            docs.append(sid)
    if not docs:
        docs = sorted(set(k[1] for k in cm.keys()))
        if docs:
            problems.append("工单不可用：文档集合改由 matrix 反推")
    dims = [str(x) for x in ((wo or {}).get("comparison_dimensions")
                             or (wo or {}).get("dimensions") or [])]
    if not dims:
        dims = list(DIM_KEYWORDS.keys())
        problems.append("工单 comparison_dimensions 缺失：按默认六维处理")

    pairwise = []
    for a, b in combinations(docs, 2):
        for d in dims:
            fields = fields_for(d, fdict, field_ids)
            if not fields:
                pairwise.append({"pair": [a, b], "dimension": d, "verdict": "not_judged",
                                 "note": "该维度无对应字段（字段字典未覆盖）", "evidence": []})
                continue
            try:
                pairwise.append(compare_pair(a, b, d, fields, cm, fdict))
            except Exception as e:
                problems.append("pairwise %s/%s/%s 异常: %s" % (a, b, d, e))
                pairwise.append({"pair": [a, b], "dimension": d, "verdict": "not_judged",
                                 "note": "判定异常降级为 not_judged", "evidence": []})

    conflicts = []
    if ablate != "no_pairwise":
        try:
            conflicts = build_conflicts(docs, cm)
        except Exception as e:
            problems.append("冲突登记异常: %s" % e)
    if ablate == "no_attribution":
        for c in conflicts:
            c["attribution"] = ""
            c["attribution_dimension"] = "unattributable"

    if ablate == "no_pairwise":
        pairwise_out = []
        conflicts_out = []
    else:
        pairwise_out = pairwise
        conflicts_out = conflicts

    return {
        "ablate": ablate or "none",
        "source_document_ids": docs,
        "comparison_dimensions": dims,
        "pairwise": pairwise_out,
        "conflicts": conflicts_out,
        "pairwise_all": pairwise,
        "problems": problems,
    }


def main():
    ap = SafeParser(description="规则化跨文档对照器（退出码恒 0，判定看输出文件）")
    ap.add_argument("--result", required=True)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--ablate", default=None, choices=["no_pairwise", "no_attribution"])
    args = safe_parse_args(ap)
    if args is None:
        print("[compare_matrix] FAIL: 命令行参数有误，判定按失败处理")
        return 0

    res = load_json(args.result)
    if res is None:
        _write({"ok": False, "problems": ["result.json 不存在或不是合法 JSON"]}, args.out)
        print("[compare_matrix] FAIL: result.json 不存在或不是合法 JSON")
        return 0
    wo = read_workorder(args.workorder)
    art = run_comparison(res, wo, args.ablate)
    art["ok"] = True
    _write(art, args.out)
    n_j = sum(1 for p in art["pairwise"] if p.get("verdict") in VERDICTS)
    print("[compare_matrix] mode=%s pairwise=%d(judged=%d) conflicts=%d problems=%d" % (
        art["ablate"], len(art["pairwise"]), n_j, len(art["conflicts"]), len(art["problems"])))
    return 0


def _write(obj, path):
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


if __name__ == "__main__":
    run_entry(main, "compare_matrix")
