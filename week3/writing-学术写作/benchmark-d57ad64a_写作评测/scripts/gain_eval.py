#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_eval.py — 使用增益 / 创新增益的同输入对照评测器（可独立复用）。

用途
----
对**同一批作答**（同一份 items.json + run_results.json + adjudication.json + 语料）
分别跑两个评分配置，产出可核对的增益证据：

  A 基础判分（basic_points_only）
      只对照必需要点（must_points）覆盖率判分 —— 相当于"人工手写一张要点对照
      评分表"能被机械化的那一部分。不查 reject、不做逐字回证、不做分歧裁定。
  B 完整评分器（full）
      必需要点覆盖率 + reject 语义红线 + 证据逐字回证 + 双评分分歧裁定。

两边的输入、语料、判定顺序、题目集合完全一致，唯一差异是"启用了哪些机制"，
因此逐项分数差可以归因到具体机制。脚本另外跑三组**机制消融**（去掉 reject /
去掉回证 / 去掉裁定）给出"机制 → 指标"的定量映射。

用法
----
    python3 gain_eval.py --outdir <dir> [--case <case.json>] [--input-dir <dir>]
                         [--degrade] [--json-out <file>]

    --outdir    acbench.py 产出的评测包目录（需含 items.json / run_results.json）
    --case      case.json，用于构建"逐字回证"语料（可选；缺则仅用输入目录文本）
    --input-dir 材料目录，扫描 .txt/.md/.csv/.json 文本并入回证语料（可选）
    --degrade   退化模式：只跑"全机制关闭"的基准档，并把消融结果作为对照
    --json-out  额外写出结果的 JSON 路径（默认写 <outdir>/gain_evidence.json）

设计约束
--------
- 零外部依赖，仅 Python 3.7+ 标准库；同一输入重复运行结果完全一致（确定性）。
- 任何异常都降级为"如实记录"，绝不抛裸异常、绝不中断上游流程；退出码恒为 0。
- 只做**对照评测**，不替代平台白板的人工对照，不生成正式答案，不改写来源数据。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time

RULE_ONLY = "仅规则评分"
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
QUOTE_RE = re.compile(r"[『「\"'“”‘’]([^』」\"'“”‘’]{1,40})[』」\"'“”‘’]")
TEXT_EXT = (".txt", ".md", ".csv", ".json", ".tsv", ".tex", ".html")


# ---------------------------------------------------------------- 基础工具

def log(outdir, msg):
    print("[gain_eval] %s" % msg)
    try:
        with open(os.path.join(outdir, "warn.log"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def norm_ws(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def sha16(obj):
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def cjk_bigrams(text):
    out = set()
    for seg in CJK_RE.findall(str(text or "")):
        if len(seg) == 1:
            out.add(seg)
            continue
        for i in range(len(seg) - 1):
            out.add(seg[i:i + 2])
    return out


def cjk_cover(point, draft):
    pb = cjk_bigrams(point)
    if not pb:
        return None
    db = cjk_bigrams(draft)
    return round(len(pb & db) / float(len(pb)), 3)


def token_cover(needle, hay):
    n = set(re.findall(r"\w+", str(needle).lower()))
    h = set(re.findall(r"\w+", str(hay).lower()))
    if not n:
        return 1   # 无实义词 needle：视为天然覆盖（原语义保留）
    return round(len(n & h) / float(len(n)), 3)


NEG_TABLE_RE = re.compile(r"(表外数值|材料外|未提供|无依据|没有依据|来源不明|额外数值|杜撰)")
OVERCLAIM_TERMS = ("证明", "证实", "彻底", "必然", "一定", "显著", "因果", "导致", "预测", "完全")
SPLIT_RE = re.compile(r"[，,；;]")
NEG_START_RE = re.compile(r"^(不|未|无|不得|禁止|避免|不含|不删|不能|不可|别|勿|严禁|不应)")
NEG_INFIX_RE = re.compile(r"(不得出现|不得写|不含|不引入|未出现|不出现|不包括|避免出现|"
                           r"禁止出现|不能出现|不应出现|无依据|表外数值|材料外)")


def material_list(item):
    """题卡的材料列表（兼容 list / 字符串 / JSON 字符串化列表三种形态）。"""
    mats = item.get("materials") or []
    if isinstance(mats, str):
        s = mats.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(m) for m in parsed]
            except Exception:
                pass
        return [mats]
    return [str(m) for m in mats]


def materials_text(item):
    """题卡的材料文本（用于数值来源核对）。"""
    return " ".join(material_list(item))


def point_scopes(point):
    return [s.strip() for s in SPLIT_RE.split(str(point or "")) if s.strip()]


def scope_met(scope, draft, item):
    s = str(scope or "").strip()
    if not s:
        return True, "empty"
    negated = bool(NEG_START_RE.match(s)) or bool(NEG_INFIX_RE.search(s))
    quoted = QUOTE_RE.findall(s)
    if negated:
        if quoted:
            return all(q not in draft for q in quoted), "negated_term_absent"
        if NEG_TABLE_RE.search(s):
            src = materials_text(item)
            if not src:
                return False, "negated_table_unverifiable"
            nums = [n for n in re.findall(r"\d+(?:\.\d+)?", draft)]
            missing = [n for n in nums if n not in src]
            return (not missing), ("negated_table_ok" if not missing else "negated_table_hit")
        hits = [w for w in OVERCLAIM_TERMS if w in draft]
        if hits:
            return False, "negated_overclaim_hit"
        return True, "negated_no_term_found"
    if s in draft:
        return True, "literal"
    if quoted:
        return all(q in draft for q in quoted), "quoted_term"
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if nums:
        return all(n in draft for n in nums), "numeric"
    cc = cjk_cover(s, draft)
    if cc is not None:
        return cc >= 0.6, "cjk_bigram"
    return token_cover(s, draft) >= 0.6, "token_cover"


def point_met(point, draft, item=None):
    """必需要点是否满足（确定性）：多子句全部满足才算满足；否定子句走缺席判定；
    正向子句走子串 → 引号术语 → 数字 → 中文二元组覆盖 → token 覆盖。"""
    scopes = point_scopes(point)
    if not scopes:
        return True
    for s in scopes:
        met, _kind = scope_met(s, draft, item or {})
        if not met:
            return False
    return True


# ---------------------------------------------------------------- 语料构建

def strings_of(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings_of(v, out)
    elif isinstance(obj, list):
        for v in obj:
            strings_of(v, out)


def build_corpus(case_path, input_dir):
    """回证语料 = case.json 全部字符串 + 材料目录下文本文件内容（空白归一化）。"""
    parts, sources = [], []
    if case_path:
        try:
            case = load_json(case_path)
            tmp = []
            strings_of(case, tmp)
            parts.extend(tmp)
            sources.append({"file": os.path.basename(case_path), "strings": len(tmp)})
        except Exception as e:
            log(input_dir or ".", "case.json 语料读取失败（%s），仅用材料目录" % e)
    if input_dir and os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            p = os.path.join(input_dir, name)
            if not os.path.isfile(p):
                continue
            if not name.lower().endswith(TEXT_EXT):
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                parts.append(txt)
                sources.append({"file": name, "chars": len(txt)})
            except Exception:
                continue
    corpus = norm_ws(" ".join(parts))
    return corpus, sources


def quote_backed(quote, corpus, limit=40):
    q = norm_ws(quote)[:limit]
    return bool(q) and q in corpus


def materials_in_corpus(item, corpus):
    """本条材料文本是否已被回证语料覆盖 —— 决定"回证未命中"是真编造还是语料不全。
    语料覆盖不到材料时（PDF 未抽文本等），未命中的引文只能算存疑，不能直接判编造。"""
    if not corpus:
        return False
    for m in material_list(item):
        s = norm_ws(m)[:60]
        if s and s in corpus:
            return True
    return False


def reject_terms(reject_list):
    """reject 条目 → 可检测关键词。引号内为关键触发词，否则整串按字面子串匹配。"""
    out = []
    for r in reject_list or []:
        s = str(r or "").strip()
        if not s:
            continue
        quoted = QUOTE_RE.findall(s)
        if quoted:
            for q in quoted:
                out.append({"reject": s, "term": q, "mode": "quoted"})
        else:
            out.append({"reject": s, "term": s, "mode": "literal"})
    return out


# ---------------------------------------------------------------- 评分器

def analyse_item(item, draft, evidence, corpus, use_reject=True, use_backcheck=True):
    """单题确定性分析：要点覆盖 + reject 命中 + 回证结果。返回分析字典。"""
    must = [str(m) for m in (item.get("must_points") or [])]
    met, missing = [], []
    for m in must:
        ok = bool(point_met(m, draft, item))
        (met if ok else missing).append(m[:120])
    ratio = (len(met) / float(len(must))) if must else 1.0
    hits = []
    if use_reject:
        for t in reject_terms(item.get("reject")):
            if t["term"] in draft:
                hits.append(t)
    unbacked = []
    corpus_verifiable = materials_in_corpus(item, corpus)
    if use_backcheck and corpus:
        for ev in (evidence or []):
            q = str((ev or {}).get("quote") or "")
            if q and not quote_backed(q, corpus):
                unbacked.append({"quote": q[:60], "location": str((ev or {}).get("location") or "")})
    return {"must_total": len(must), "must_met": met, "must_missing": missing,
            "must_ratio": round(ratio, 4), "reject_hits": hits, "unbacked_evidence": unbacked,
            "corpus_verifiable": corpus_verifiable,
            "steps": len(must) + len(hits) + len(unbacked or [])}


def score_from_analysis(a, adjudicated=None):
    """分数规则（两档共享同一规则，只因启用机制不同而输入不同）：
       reject 命中 → 0；引文回证未命中 → 材料已被语料覆盖时判 0（真编造），
       语料未覆盖材料时判 1（存疑，不误伤）；要点全覆盖 → 2；部分覆盖 → 1；完全未覆盖 → 0。
       裁定值（adjudicated ∈ {0,1,2}）存在时为最终分（人工裁定高于机械判定）。"""
    if adjudicated in (0, 1, 2):
        return int(adjudicated), "adjudicated"
    if a["reject_hits"]:
        return 0, "reject_hit"
    if a["unbacked_evidence"]:
        if a.get("corpus_verifiable"):
            return 0, "evidence_fabricated"      # 语料已覆盖材料却回证失败 = 真编造
        return 1, "evidence_unverifiable"         # 语料未覆盖材料 = 存疑不误伤（原语义保留）
    if not a["must_total"]:
        return 0, "no_must_points"
    if a["must_ratio"] >= 1.0:
        return 2, "must_all_met"                 # 要点全覆盖 = 2（原语义保留）
    if a["must_ratio"] > 0:
        return 1, "must_partially_met"           # 部分覆盖 = 1（原语义保留）
    return 0, "must_none_met"


def run_scorer(items, drafts, adj_map, corpus, use_reject, use_backcheck, use_adj):
    """跑一个评分配置，返回 {scores, detail, elapsed_ms, steps}。"""
    t0 = time.perf_counter()
    scores, detail, steps = {}, {}, 0
    for it in items:
        iid = str(it.get("item_id"))
        rec = drafts.get(iid) or {}
        draft = str(rec.get("draft_md") or "")
        ev = rec.get("evidence") or []
        a = analyse_item(it, draft, ev, corpus, use_reject=use_reject, use_backcheck=use_backcheck)
        adj = adj_map.get(iid) if use_adj else None
        adj_val = adj.get("adjudicated") if isinstance(adj, dict) else None
        if adj_val not in (0, 1, 2):
            adj_val = None
        sc, why = score_from_analysis(a, adj_val)
        scores[iid] = sc
        steps += a["steps"] + (1 if (use_adj and adj is not None) else 0)
        detail[iid] = {
            "score": sc, "reason": why, "must_ratio": a["must_ratio"],
            "must_total": a["must_total"], "must_missing": a["must_missing"],
            "reject_hits": [h["term"] for h in a["reject_hits"]],
            "unbacked_evidence": a["unbacked_evidence"],
            "adjudicated": adj_val,
            "judge_a": (adj or {}).get("judge_a") if isinstance(adj, dict) else None,
            "judge_b": (adj or {}).get("judge_b") if isinstance(adj, dict) else None,
            "judge_delta": (adj or {}).get("delta") if isinstance(adj, dict) else None,
            "draft_len": len(draft), "evidence_count": len(ev),
        }
    elapsed = round((time.perf_counter() - t0) * 1000, 3)
    return {"scores": scores, "detail": detail, "elapsed_ms": elapsed, "steps": steps}


def metrics_between(base, full):
    """两边逐项对照 → 一致率 / 漏检数 / 误判数 / 差异明细。"""
    ids = sorted(set(base) | set(full))
    same = miss = over = 0
    rows = []
    for iid in ids:
        b = base.get(iid)
        f = full.get(iid)
        if b is None or f is None:
            continue
        if b == f:
            same += 1
            kind = "same"
        elif f < b:
            miss += 1
            kind = "basic_missed_defect"   # 基础判分放行、完整评分器判不合格 → 漏检
        else:
            over += 1
            kind = "basic_over_penalized"  # 基础判分判过严、完整评分器放宽
        rows.append({"item_id": iid, "basic_score": b, "full_score": f,
                     "delta": f - b, "kind": kind})
    n = same + miss + over
    return {"items_compared": n,
            "agreement_rate": round(same / float(n), 4) if n else None,
            "missed_detections": miss,
            "false_downgrades": over,
            "same_scores": same,
            "per_item": rows}


def agreement_with_ref(scores, ref):
    """与人工语义判分（scores.csv）的一致率 —— 衡量"机器判分能否复现人工判分"。"""
    ids = [i for i in scores if i in ref]
    if not ids:
        return {"items_compared": 0, "agreement_rate": None, "per_item": []}
    same = sum(1 for i in ids if scores[i] == ref[i])
    rows = [{"item_id": i, "scorer": scores[i], "human": ref[i],
             "match": scores[i] == ref[i], "diff": scores[i] - ref[i]} for i in sorted(ids)]
    return {"items_compared": len(ids),
            "agreement_rate": round(same / float(len(ids)), 4),
            "mismatched_items": [r["item_id"] for r in rows if not r["match"]],
            "per_item": rows}


# ---------------------------------------------------------------- 主流程

def collect(outdir):
    """读取评测包（缺文件时降级为空，不抛异常）。"""
    items, run, adj = [], {}, {}
    try:
        items = (load_json(os.path.join(outdir, "items.json")) or {}).get("items") or []
    except Exception as e:
        log(outdir, "items.json 读取失败（%s），按空题集降级" % e)
    try:
        for r in (load_json(os.path.join(outdir, "run_results.json")) or {}).get("results") or []:
            run[str(r.get("item_id"))] = r
    except Exception as e:
        log(outdir, "run_results.json 读取失败（%s），按空作答降级" % e)
    try:
        for a in (load_json(os.path.join(outdir, "adjudication.json")) or {}).get("rounds") or []:
            adj[str(a.get("item_id"))] = a
    except Exception:
        pass
    return items, run, adj


def read_scores_csv(outdir):
    """读人工语义判分（scores.csv）作为参照基线；缺文件返回空 dict。"""
    out = {}
    try:
        import csv
        with open(os.path.join(outdir, "scores.csv"), "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                sc = str(r.get("score") or "").strip()
                if sc in ("0", "1", "2"):
                    out[str(r.get("item_id"))] = int(sc)
    except Exception as e:
        log(outdir, "scores.csv 读取失败（%s），人工参照基线不可用" % e)
    return out


def build_evidence(outdir, case_path, input_dir, degrade):
    items, run, adj = collect(outdir)
    corpus, corpus_src = build_corpus(case_path, input_dir)
    adj_map = adj
    human_ref = read_scores_csv(outdir)

    basic = run_scorer(items, run, adj_map, corpus, use_reject=False, use_backcheck=False, use_adj=False)
    full = run_scorer(items, run, adj_map, corpus, use_reject=True, use_backcheck=True, use_adj=True)
    m_full = metrics_between(basic["scores"], full["scores"])
    ref_basic = agreement_with_ref(basic["scores"], human_ref)
    ref_full = agreement_with_ref(full["scores"], human_ref)

    # 机制消融：每次只关掉一个机制，看指标怎么动 —— 机制 → 指标 的定量映射
    ablations = {}
    for key, (ur, ub, ua) in {
        "no_reject": (False, True, True),
        "no_backcheck": (True, False, True),
        "no_adjudication": (True, True, False),
    }.items():
        v = run_scorer(items, run, adj_map, corpus, use_reject=ur, use_backcheck=ub, use_adj=ua)
        m = metrics_between(basic["scores"], v["scores"])
        changed = [r["item_id"] for r in m["per_item"] if r["delta"] != 0]
        # 分数没变但判定依据变了的题也算机制起作用（例如回证降档原因被 must_partial 取代）
        reason_changed = [iid for iid in v["scores"]
                          if (v["detail"][iid].get("reason") != full["detail"].get(iid, {}).get("reason"))]
        ablations[key] = {
            "config": {"reject": ur, "evidence_backcheck": ub, "adjudication": ua},
            "agreement_rate": m["agreement_rate"],
            "missed_detections": m["missed_detections"],
            "false_downgrades": m["false_downgrades"],
            "changed_items_vs_basic": changed,
            "changed_items_vs_full": [r["item_id"] for r in metrics_between(
                v["scores"], full["scores"])["per_item"] if r["delta"] != 0],
            "reason_changed_items_vs_full": reason_changed,
            "elapsed_ms": v["elapsed_ms"], "steps": v["steps"],
        }
    m_noall = metrics_between(basic["scores"], basic["scores"])
    ablations["degrade_all_off"] = {
        "config": {"reject": False, "evidence_backcheck": False, "adjudication": False},
        "agreement_rate": m_noall["agreement_rate"], "missed_detections": 0,
        "false_downgrades": 0, "changed_items_vs_basic": [],
        "changed_items_vs_full": [r["item_id"] for r in metrics_between(
            basic["scores"], full["scores"])["per_item"] if r["delta"] != 0],
        "reason_changed_items_vs_full": [iid for iid in basic["scores"]
                                         if basic["detail"][iid].get("reason")
                                         != full["detail"].get(iid, {}).get("reason")],
        "elapsed_ms": basic["elapsed_ms"], "steps": basic["steps"],
        "note": "退化档：全部增强机制关闭，等价于'只对照要点'的手写评分表；"
                "agreement_rate 对自身恒为 1.0，真正有意义的是 changed_items_vs_full",
    }

    mech_map = []
    for key, label, metric in (
        ("no_reject", "reject 语义红线（命中不可接受错误判 0）", "漏检数 / 逐项分数"),
        ("no_backcheck", "证据逐字回证（引文须在材料语料中命中）", "漏检数 / 判定依据"),
        ("no_adjudication", "双评分分歧裁定（judge_a/judge_b → adjudicated）", "逐项分数 / 分歧收敛"),
    ):
        ab = ablations.get(key) or {}
        mech_map.append({
            "mechanism": label,
            "ablation_id": key,
            "metric_affected": metric,
            "agreement_rate_without": ab.get("agreement_rate"),
            "agreement_rate_with": m_full["agreement_rate"],
            "missed_detections_without": ab.get("missed_detections"),
            "missed_detections_with": m_full["missed_detections"],
            "items_changed_when_removed": ab.get("changed_items_vs_full") or [],
            "items_reason_changed_when_removed": ab.get("reason_changed_items_vs_full") or [],
            "evidence": "同一批作答、同一语料、同一判定顺序下的逐项分数差",
        })

    # 退化模式：只保留基准档（全部增强机制关闭），显式对比"退化后 vs 完整"
    if degrade:
        full_to_basic = metrics_between(full["scores"], basic["scores"])
        ablations["degrade_all_off"]["compared_against_full"] = {
            "agreement_rate": full_to_basic["agreement_rate"],
            "items_compared": full_to_basic["items_compared"],
            "items_whose_score_changed": [r["item_id"] for r in full_to_basic["per_item"]
                                           if r["delta"] != 0],
            "lost_detections": full_to_basic["missed_detections"],
        }
        basic["label"] = "退化档（全部增强机制关闭：只对照必需要点）"
        full["label"] = "完整档（对照基准，用于量化退化损失）"

    per_item = []
    for it in items:
        iid = str(it.get("item_id"))
        b = basic["detail"].get(iid) or {}
        f = full["detail"].get(iid) or {}
        per_item.append({
            "item_id": iid, "basic_score": b.get("score"), "full_score": f.get("score"),
            "delta": (f.get("score") - b.get("score")) if (b.get("score") is not None and f.get("score") is not None) else None,
            "agree": b.get("score") == f.get("score"),
            "must_ratio": f.get("must_ratio"), "must_missing": f.get("must_missing"),
            "reject_hits": f.get("reject_hits"), "unbacked_evidence": f.get("unbacked_evidence"),
            "adjudicated": f.get("adjudicated"), "judge_delta": f.get("judge_delta"),
            "basic_reason": b.get("reason"), "full_reason": f.get("reason"),
        })

    manual_steps = 7 + len(items) * 4
    tool_steps = 4  # report / embed / verify / gain 四步机械动作
    ev = {
        "case_id": str((load_json(os.path.join(outdir, "items.json")) or {}).get("case_id") or "unknown")
        if os.path.exists(os.path.join(outdir, "items.json")) else "unknown",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "degrade" if degrade else "full",
        "n_items": len(items),
        "input_digest": sha16({"items": items,
                                "drafts": {k: (v.get("draft_md") or "") for k, v in run.items()},
                                "adj": adj_map, "corpus_sha": sha16(corpus)}),
        "corpus": {"chars": len(corpus), "sources": corpus_src,
                   "note": "回证语料 = case.json 字符串 + 材料目录文本；只做子串命中，不做语义判断"},
        "design": {
            "same_input": "两个评分配置读同一份 items / run_results / adjudication / 语料，题目集合与判定顺序一致",
            "only_difference": "启用的机制集合：A 只对照必需要点；B 额外启用 reject 红线 + 逐字回证 + 分歧裁定",
            "deterministic": "两档均为纯函数式确定性判定，同输入重复运行分数完全一致",
            "note": "score_suggest/机械判分仍是建议性档；语义终判由 verdict_rule 与人工裁定给出",
        },
        "scorers": {
            "basic_points_only": {
                "label": ("退化档（全部增强机制关闭：只对照必需要点）" if degrade
                          else "基础判分（只对照必需要点）"),
                "enabled_mechanisms": ["must_points_coverage"],
                "scores": basic["scores"], "elapsed_ms": basic["elapsed_ms"], "steps": basic["steps"],
                "detail": basic["detail"],
            },
            "full": {
                "label": ("完整档（对照基准，用于量化退化损失）" if degrade
                          else "完整评分器（要点 + reject 红线 + 逐字回证 + 分歧裁定）"),
                "enabled_mechanisms": (["must_points_coverage"] if degrade else
                                       ["must_points_coverage", "reject_redline",
                                        "evidence_backcheck", "adjudication"]),
                "scores": full["scores"], "elapsed_ms": full["elapsed_ms"], "steps": full["steps"],
                "detail": full["detail"],
            },
        },
        "metrics": {
            "agreement_rate": m_full["agreement_rate"],
            "missed_detections": m_full["missed_detections"],
            "false_downgrades": m_full["false_downgrades"],
            "same_scores": m_full["same_scores"],
            "items_compared": m_full["items_compared"],
            "per_item_compare": m_full["per_item"],
            "vs_human_semantic_scores": {
                "note": "参照基线 = scores.csv 中的人工语义判分；衡量机器判分能否复现人工判分",
                "basic": {"agreement_rate": ref_basic["agreement_rate"],
                          "items_compared": ref_basic["items_compared"],
                          "mismatched_items": ref_basic.get("mismatched_items") or []},
                "full": {"agreement_rate": ref_full["agreement_rate"],
                         "items_compared": ref_full["items_compared"],
                         "mismatched_items": ref_full.get("mismatched_items") or []},
                "basic_per_item": ref_basic["per_item"],
                "full_per_item": ref_full["per_item"],
            },
        },
        "per_item": per_item,
        "ablation": ablations,
        "mechanism_to_metric": mech_map,
        "efficiency": {
            "basic_elapsed_ms": basic["elapsed_ms"], "full_elapsed_ms": full["elapsed_ms"],
            "basic_steps": basic["steps"], "full_steps": full["steps"],
            "step_delta": full["steps"] - basic["steps"],
            "mechanical_steps_saved_vs_manual": manual_steps - tool_steps,
            "manual_step_formula": "manual = 7(建题卡/判读材料/核验数值引用/写参考答案与变体/逐题评分与依据/双评与裁定/汇总报告与装配) + 每题 4(抄要点/逐条回证/写评分行与依据/写失败样例或裁定)",
            "tool_step_formula": "tool = 4(report / embed / verify / gain 四步机械动作)",
            "note": "机械步骤数按流程清单逐项计数，可复核；不等价于人工工时（未实测，不编造）",
        },
        "boundaries": [
            "本对照只证明'同一评分器内部不同机制配置'的差异，不等于平台白板的人工对照结果。",
            "basic 档只是'人工手写要点对照评分表'的机械下界；它不含人工理解，不能代表人工水平。",
            "逐字回证只能验证引文是否在材料语料中逐字出现，无法判断引文是否被正确解读。",
            "分歧裁定依赖 adjudication.json 中真实存在的双评记录；无记录时该机制自动关闭并在消融中标出。",
            "当材料以 PDF/Office 二进制提供且未被抽取为文本时，回证语料覆盖不全，回证结论需人工复核。",
            "分数差只在小样本同输入下有意义；题量变化后必须重跑，不得沿用旧的一致率。",
        ],
        "honesty": {
            "no_fabricated_scores": "所有分数由本脚本对真实作答现场计算，无预置答案、无人工填写的对照数字。",
            "status": "ok" if items else "empty_items",
            "items_note": ("题集为空时全部指标为 null，如实记录而非填 0 冒充有效对照。"
                           if not items else "题集 %d 题，对照在同批作答上完成。" % len(items)),
        },
    }
    return ev


def main():
    ap = argparse.ArgumentParser(description="acbench 使用增益同输入对照评测器")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--case", default=None)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--degrade", action="store_true", help="退化模式：只留基准档并输出消融对照")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    outdir = args.outdir
    try:
        os.makedirs(outdir, exist_ok=True)
        ev = build_evidence(outdir, args.case, args.input_dir, args.degrade)
        path = args.json_out or os.path.join(outdir, "gain_evidence.json")
        save_json(path, ev)
        m = ev.get("metrics") or {}
        rh = (m.get("vs_human_semantic_scores") or {})
        print("[gain_eval] mode=%s items=%d 一致率(basic vs full)=%s 漏检=%d 误判=%d "
              "与人工判分一致率(basic/full)=%s/%s 耗时=%s/%sms 步骤=%s/%s → %s"
              % (ev["mode"], ev["n_items"], m.get("agreement_rate"),
                 m.get("missed_detections"), m.get("false_downgrades"),
                 (rh.get("basic") or {}).get("agreement_rate"),
                 (rh.get("full") or {}).get("agreement_rate"),
                 (ev["efficiency"] or {}).get("basic_elapsed_ms"),
                 (ev["efficiency"] or {}).get("full_elapsed_ms"),
                 (ev["efficiency"] or {}).get("basic_steps"),
                 (ev["efficiency"] or {}).get("full_steps"), path))
        return 0
    except Exception as e:
        try:
            log(outdir, "gain_eval 异常降级: %s" % e)
        except Exception:
            print("[gain_eval] 异常降级: %s" % e)
        return 0


if __name__ == "__main__":
    sys.exit(main())
