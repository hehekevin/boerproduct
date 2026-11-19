#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""align_check.py — 双语对齐 / 术语锁定 / 数字单位保真 校验（可修复 · 可退化消融）

检查项:
  1) 段级对齐（段数/段号/role 一一对应）
  2) 数字保真：数值·量级·单位比对，支持 万/亿 ↔ thousand/million/billion 跨语向量级换算
  3) 引用标记序列一致（[n] / (Author, Year)）
  4) 术语锁定：只允许锁定译法；禁用变体出现即命中；原文术语残留命中
  5) 覆盖度/漏译检测（空译文 / 译文异常短）

新增能力:
  --fix-out PATH   对确定性可修项做**保守自动修复**并写出修复后译文 + 修改记录
  --ablate LIST    退化/消融模式：term_lock,num_verify,cite_anchor,coverage（关闭对应机制用于同输入对照）
  --metrics-out    输出逐项对照指标（术语一致率 / 数字单位保真率 / 漏译率 / 需人工核对条目数）

诚实原则:
  - 校验只报告 + 保守修复；无法自动修复的一律进 needs_human，不臆造译文。
  - **所有失败路径 exit 0**：verdict/fail 如实写入报告与 stdout，绝不中断交付流水线。
  - 「管线自己发现了什么」与「产物实际是什么样」分开记录（detected_by_pipeline vs artifact_*），
    退化模式下前者为 0 而后者不变——这正是消融证据要呈现的事实，不做美化。
"""
import argparse, json, os, re, sys, time

# ---------------- 单位词表（显式词表，避免把 and/of 等虚词误当单位） ----------------
_UNIT_VOCAB = {
    "%": "percent", "‰": "percent", "percent": "percent",
    "mg": "mass", "kg": "mass", "g": "mass", "μg": "mass", "ug": "mass", "ng": "mass",
    "t": "mass", "ton": "mass", "毫克": "mass", "千克": "mass", "克": "mass",
    "微克": "mass", "纳克": "mass", "吨": "mass",
    "ml": "volume", "l": "volume", "μl": "volume", "ul": "volume", "dl": "volume",
    "毫升": "volume", "微升": "volume", "升": "volume", "分升": "volume",
    "mm": "length", "cm": "length", "m": "length", "km": "length", "μm": "length",
    "um": "length", "nm": "length", "pm": "length",
    "毫米": "length", "厘米": "length", "米": "length", "千米": "length",
    "微米": "length", "纳米": "length",
    "s": "time", "ms": "time", "μs": "time", "min": "time", "h": "time", "d": "time",
    "wk": "time", "year": "time", "yr": "time", "month": "time", "day": "time",
    "hour": "time", "minute": "time", "second": "time", "decade": "time",
    "years": "time", "months": "time", "days": "time", "hours": "time",
    "minutes": "time", "seconds": "time", "weeks": "time",
    "年": "time", "岁": "time", "月": "time", "天": "time", "日": "time", "周": "time",
    "小时": "time", "分钟": "time", "秒": "time", "毫秒": "time", "十年": "time",
    "mmol": "mol", "mol": "mol", "μmol": "mol", "umol": "mol", "nmol": "mol",
    "毫摩尔": "mol", "摩尔": "mol", "微摩尔": "mol", "纳摩尔": "mol",
    "mmHg": "press", "kPa": "press", "Pa": "press", "psi": "press", "bar": "press",
    "atm": "press",
    "元": "money", "美元": "money", "欧元": "money", "rmb": "money", "cny": "money",
    "usd": "money", "eur": "money",
    "例": "count", "名": "count", "人": "count", "只": "count", "株": "count",
    "次": "count", "篇": "count", "页": "count", "个": "count", "种": "count",
    "类": "count", "家": "count", "所": "count", "台": "count", "辆": "count",
    "座": "count", "部": "count", "条": "count", "件": "count", "张": "count",
    "头": "count", "匹": "count", "组": "count", "份": "count", "位": "count",
    "patients": "count", "patient": "count", "subjects": "count", "subject": "count",
    "participants": "count", "cases": "count", "mice": "count", "rats": "count",
    "samples": "count", "sample": "count", "cells": "count", "cell": "count",
    "features": "count", "feature": "count", "hospitals": "count", "hospital": "count",
    "centers": "count", "center": "count", "points": "count", "images": "count",
    "pixels": "count", "genes": "count", "proteins": "count", "species": "count",
    "reads": "count", "copies": "count", "sites": "count", "lesions": "count",
    "folds": "count", "units": "count",
    "倍": "ratio", "fold": "ratio",
    "Hz": "freq", "kHz": "freq", "MHz": "freq", "GHz": "freq", "rpm": "freq",
    "bpm": "freq",
    "°C": "temp", "℃": "temp", "°F": "temp", "K": "temp",
    "IU": "iu", "U/L": "conc", "ppm": "conc", "ppb": "conc",
    "MB": "size", "GB": "size", "KB": "size", "TB": "size", "PB": "size",
    "bp": "size", "kb": "size", "Mb": "size", "Gb": "size",
    "mm²": "area", "cm²": "area", "m²": "area", "km²": "area",
}
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(_UNIT_VOCAB, key=len, reverse=True))
_UNIT_RE = re.compile(r"^(" + _UNIT_ALT + r")(?:\s*/\s*(" + _UNIT_ALT + r"))?")
_SCALE_RE = re.compile(r"^(百万|千万|千|万|亿|thousand|million|billion)", re.I)
_SCALE_MAP = {"千": 1e3, "万": 1e4, "亿": 1e8, "百万": 1e6, "千万": 1e7,
              "thousand": 1e3, "million": 1e6, "billion": 1e9}
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")

_LOOSE_CLASSES = {"count", "none", "ratio", "other"}
_CITE_RE = re.compile(r"\[\d{1,3}\]|\([A-Z][a-zA-Z]+(?:\s+et al\.?)?,\s*\d{4}\)")


def _fmt(v):
    if v is None:
        return ""
    if abs(v - round(v)) < 1e-12:
        return str(int(round(v)))
    s = ("%.10f" % v).rstrip("0").rstrip(".")
    return s if s else "0"


def _fmt_grouped(v, use_comma):
    if not use_comma:
        return _fmt(v)
    neg = v < 0
    iv = int(abs(round(v)))
    s = "{:,}".format(iv)
    if abs(abs(v) - iv) > 1e-12:
        s += _fmt(abs(abs(v) - iv))[1:]
    return ("-" + s) if neg else s


def _unit_at(text, p):
    """在位置 p（允许前导空白）解析单位/复合单位。返回 (unit, unit_class, 消耗长度)。"""
    um = _UNIT_RE.match(text[p:].lstrip())
    if not um:
        return None, "none", 0
    pad = len(text[p:]) - len(text[p:].lstrip())
    u1, u2 = um.group(1), um.group(2)
    nxt = text[p + pad + um.end():p + pad + um.end() + 1]
    if u1.isascii() and nxt.isalpha():
        return None, "none", 0
    c1 = _UNIT_VOCAB.get(u1, "other")
    c2 = _UNIT_VOCAB.get(u2, "other") if u2 else None
    cls = (c1 + "/" + c2) if u2 else c1
    return (u1 + ("/" + u2 if u2 else "")), cls, pad + len(um.group(0))


def scan_numbers(text):
    """数字 token 列表：{start,end,value(绝对值),unit,unit_class,scale_word,text}
    - 数字与量词/单位之间允许空白（"12,345 patients" / "12,345 例"）
    - 先判复合单位（"毫克/千克" 整体一个单位），再判量级词（"1.2 million" / "120 万"）
    - 复合单位 "mg/kg" 与 "毫克/千克" 同归 mass/mass，跨语向可比
    - 引用标记（[1] / (Author, 2020)）先遮蔽，避免把引用序号误当数字
    - token 区间只含「数字 + 量级词」，不含单位，便于精确回写
    """
    out = []
    if not text:
        return out
    masked = _CITE_RE.sub(lambda m: " " * len(m.group(0)), text)
    for m in _NUM_RE.finditer(masked):
        raw_num = m.group(1)
        try:
            val = float(raw_num.replace(",", ""))
        except Exception:
            continue
        pos = m.end()
        scale = 1.0
        scale_word = None
        unit = None
        unit_class = "none"

        unit, unit_class, _adv = _unit_at(masked, pos)
        if unit is None:
            sm = _SCALE_RE.match(masked[pos:].lstrip())
            if sm:
                pad = len(masked[pos:]) - len(masked[pos:].lstrip())
                scale_word = sm.group(1)
                scale = _SCALE_MAP[scale_word.lower()]
                pos += pad + len(sm.group(0))
                unit, unit_class, _adv = _unit_at(masked, pos)
        out.append({"start": m.start(), "end": pos, "digits_end": m.end(),
                    "raw": raw_num, "value": val * scale, "unit": unit,
                    "unit_class": unit_class, "scale": scale, "scale_word": scale_word,
                    "had_comma": "," in raw_num,
                    "text": masked[m.start():pos].strip()})
    return out


def _cites(s):
    return _CITE_RE.findall(s or "")


def _load_jsonl(path):
    if not path or not os.path.exists(path):
        return None
    rows = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({"_bad_line": i})
    return rows


def _match_numbers(src_nums, tgt_nums):
    """先按**数值**做顺序无关匹配（中文语序与英文不同，位置对齐会误报）。
    返回 (值匹配对, 未匹配源, 未匹配译文)。"""
    used, by_value, unmatched_src = set(), [], []
    for s in src_nums:
        hit = None
        for i, t in enumerate(tgt_nums):
            if i in used:
                continue
            if abs(s["value"] - t["value"]) <= max(1e-9, abs(s["value"]) * 1e-9):
                hit = i
                break
        if hit is None:
            unmatched_src.append(s)
        else:
            used.add(hit)
            by_value.append((s, tgt_nums[hit]))
    unmatched_tgt = [t for i, t in enumerate(tgt_nums) if i not in used]
    return by_value, unmatched_src, unmatched_tgt


def _pair_leftovers(unmatched_src, unmatched_tgt):
    """把「值匹配」后剩下的源/译数字按各自出现顺序两两配对，用于诊断「某个数字被改错」。
    不能用原始下标配对——中英语序不同会让正确的数字被错配。"""
    pairs = []
    for i, s in enumerate(unmatched_src):
        if i < len(unmatched_tgt):
            pairs.append((s, unmatched_tgt[i]))
    return pairs


def _num_pair_issues(src_nums, tgt_nums):
    """比对数字：返回 (hard_issues, soft_issues, fix_plan)。
    - 数值按**值**顺序无关匹配（跨语向语序差异不误报）
    - 匹配上的：单位类别比对（hard=关键单位错配；soft=可接受的单位省略）
    - 匹配不上的：按剩余出现顺序配对，诊断为 value_mismatch；数量不等则 count_mismatch
    """
    hard, soft, fix_plan = [], [], []
    by_value, unmatched_src, unmatched_tgt = _match_numbers(src_nums, tgt_nums)

    for s, t in by_value:
        sc, tc = s["unit_class"], t["unit_class"]
        if sc == tc:
            continue
        if "none" in (sc, tc):
            soft.append({"type": "unit_dropped" if tc == "none" else "unit_added",
                         "src": s["text"], "tgt": t["text"], "src_class": sc, "tgt_class": tc,
                         "hint": "一侧未带出单位，需人工确认（部分中文表达允许省略计量单位）"})
        elif sc in _LOOSE_CLASSES and tc in _LOOSE_CLASSES:
            soft.append({"type": "unit_loose", "src": s["text"], "tgt": t["text"],
                         "src_class": sc, "tgt_class": tc})
        else:
            hard.append({"type": "unit_mismatch", "src": s["text"], "tgt": t["text"],
                         "src_class": sc, "tgt_class": tc,
                         "hint": "单位类别错配（如 %↔倍、mg↔kg）"})

    if unmatched_src or unmatched_tgt:
        for s, t in _pair_leftovers(unmatched_src, unmatched_tgt):
            if abs(s["value"] - t["value"]) > max(1e-9, abs(s["value"]) * 1e-9):
                hard.append({"type": "number_value_mismatch", "src": s["text"], "tgt": t["text"],
                             "src_value": _fmt(s["value"]), "tgt_value": _fmt(t["value"]),
                             "hint": "数值/量级与原文不符（四舍五入、量级错配或数字改写）"})
                fix_plan.append((s, t))
        if len(unmatched_src) != len(unmatched_tgt):
            hard.append({"type": "number_count_mismatch", "src_count": len(src_nums),
                         "tgt_count": len(tgt_nums),
                         "src": [n["text"] for n in src_nums][:8],
                         "tgt": [n["text"] for n in tgt_nums][:8],
                         "hint": "数字个数与原文不一致（漏数/增数），不自动修复，需人工核对"})
    return hard, soft, fix_plan


def _fix_number_token(src_num, tgt_num):
    """按译文原有量级风格，把数字纠正为原文绝对值。返回 (start, end, 替换文本)。
    替换区间为译文的**整个数字 token**（含量级词），避免只换数字部分留下旧量级词。"""
    if tgt_num["scale_word"]:
        val = src_num["value"] / tgt_num["scale"]
        txt = _fmt_grouped(val, tgt_num.get("had_comma")) + tgt_num["scale_word"]
    else:
        txt = _fmt_grouped(src_num["value"], tgt_num.get("had_comma"))
    return tgt_num["start"], tgt_num["end"], txt


def _seg_term_issues(src_text, tgt_text, terms, lower_src=True):
    """单段术语检查：返回 (missing_locked[], forbidden_used[])。"""
    missing, forbidden = [], []
    src_l = src_text.lower() if lower_src else src_text
    for t in terms:
        src = t.get("src") or ""
        tgt = t.get("tgt") or ""
        if not src or not tgt or t.get("status") == "pending":
            continue
        key = src.lower() if lower_src else src
        if key and key in src_l and tgt not in tgt_text:
            missing.append({"term": src, "expected": tgt, "reason": "locked_translation_missing"})
        for fv in (t.get("forbidden") or []):
            if fv and fv in tgt_text and fv not in tgt:
                forbidden.append({"term": src, "forbidden_found": fv,
                                  "reason": "forbidden_variant_used"})
    return missing, forbidden


def _key_facts(src_text, tgt_text, terms=None):
    """源文的关键事实锚点：数字 / 引用标记 / 锁定术语。用于判定「译文是否整体缺失内容」。"""
    facts = []
    src_nums = scan_numbers(src_text)
    tgt_nums = scan_numbers(tgt_text)
    tgt_vals = [n["value"] for n in tgt_nums]
    for n in src_nums:
        if not any(abs(n["value"] - v) <= max(1e-9, abs(n["value"]) * 1e-9) for v in tgt_vals):
            facts.append({"kind": "number", "value": n["text"]})
    src_c, tgt_c = _cites(src_text), _cites(tgt_text)
    for c in src_c:
        if c not in tgt_c:
            facts.append({"kind": "citation", "value": c})
    for t in (terms or []):
        if not isinstance(t, dict) or t.get("status") == "pending":
            continue
        src, tgt = t.get("src") or "", t.get("tgt") or ""
        if not src or not tgt:
            continue
        if src.lower() in (src_text or "").lower() and tgt not in (tgt_text or ""):
            facts.append({"kind": "term", "value": src})
    return facts


def _is_truncated(src_text, tgt_text, terms=None):
    """判定译文是否「整体截断/缺失内容」。
    不用「字符长度比」做主判据——中英字符压缩率差异大（英文 120 字符 ≈ 中文 30 字符），
    长度比会误报。改用**关键事实锚点**：源文有数字/引用/术语而译文一个都没落地，
    且译文长度显著偏短，才判定为疑似截断。"""
    if not tgt_text or not tgt_text.strip():
        return True, {"reason": "empty_translation"}
    if not src_text:
        return False, {}
    missing = _key_facts(src_text, tgt_text, terms)
    if not missing:
        return False, {}
    ratio = len(tgt_text) / max(1, len(src_text))
    if ratio < 0.5:
        return True, {"reason": "key_facts_missing_and_short", "ratio": round(ratio, 3),
                      "missing_facts": missing[:6]}
    return False, {}


def evaluate_artifact(rows, segs, terms):
    """**独立评估器**：与运行模式无关，始终以全强度规则度量产物。
    用于同输入 A/B 对照时保证「两个产物用同一把尺子量」。"""
    segs = [s for s in segs if isinstance(s, dict) and s.get("seg")]
    rows_by = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get("seg") and "_bad_line" not in r:
            rows_by[r["seg"]] = r
    locked = [t for t in (terms or [])
              if isinstance(t, dict) and "_bad_line" not in t and t.get("tgt") and t.get("status") != "pending"]

    per = {}
    hard_items = 0
    soft_items = 0
    for s in segs:
        seg = s["seg"]
        r = rows_by.get(seg)
        tgt_text = ((r or {}).get("tgt_text") or "")
        src_text = s.get("src_text") or ""
        rec = {"seg": seg, "term_ok": True, "num_ok": True, "cite_ok": True, "omitted": False,
               "term_issues": [], "num_issues": [], "cite_issues": []}

        trunc, tinfo = _is_truncated(src_text, tgt_text, locked)
        if trunc:
            rec["omitted"] = True
            rec["num_issues"].append({"type": "omitted_or_truncated", **tinfo})
            hard_items += 1
            if not tgt_text.strip():
                rec["term_ok"] = rec["num_ok"] = rec["cite_ok"] = False
                per[seg] = rec
                continue

        missing, forbidden = _seg_term_issues(src_text, tgt_text, locked)
        if missing or forbidden:
            rec["term_ok"] = False
            rec["term_issues"] = missing + forbidden
            hard_items += len(missing) + len(forbidden)

        sn, tn = scan_numbers(src_text), scan_numbers(tgt_text)
        h, so, _fp = _num_pair_issues(sn, tn)
        if h:
            rec["num_ok"] = False
            rec["num_issues"].extend(h)
            hard_items += len(h)
        if so:
            rec["num_issues"].extend(so)
            soft_items += len(so)

        sc, tc = _cites(src_text), _cites(tgt_text)
        if sc != tc:
            rec["cite_ok"] = False
            rec["cite_issues"].append({"src": sc, "tgt": tc})
            hard_items += 1

        per[seg] = rec

    total = max(1, len(segs))
    metrics = {
        "segments": len(segs),
        "translated": sum(1 for s in segs if (rows_by.get(s["seg"]) or {}).get("tgt_text")),
        "term_consistency_rate": round(sum(1 for r in per.values() if r["term_ok"]) / total, 4),
        "number_unit_fidelity_rate": round(sum(1 for r in per.values() if r["num_ok"]) / total, 4),
        "citation_alignment_rate": round(sum(1 for r in per.values() if r["cite_ok"]) / total, 4),
        "omission_rate": round(sum(1 for r in per.values() if r["omitted"]) / total, 4),
        "needs_human_items": hard_items + soft_items,
        "hard_issues": hard_items,
        "soft_issues": soft_items,
    }
    return {"per_segment": per, "metrics": metrics}


def _apply_fixes(segs, trs, terms, ablate, changes):
    """对确定性可修项做保守修复，返回修复后的 rows。
    只修两类：① 禁用变体 → 锁定译法；② 数字被改错 → 回写原文值（保持译文量级风格）。
    引用错位、单位错配、漏译一律不自动修（无法确定作者意图）。"""
    fixed = []
    for s in segs:
        seg = s["seg"]
        t = trs.get(seg)
        if not t:
            continue
        row = dict(t)
        txt = row.get("tgt_text", "") or ""
        src_text = s.get("src_text") or ""
        if "term_lock" not in ablate:
            for term_row in (terms or []):
                if not isinstance(term_row, dict) or term_row.get("status") == "pending":
                    continue
                locked = term_row.get("tgt")
                if not locked:
                    continue
                for fv in (term_row.get("forbidden") or []):
                    if fv and fv in txt and fv not in locked:
                        txt = txt.replace(fv, locked)
                        changes.append({"seg": seg, "kind": "term_fix", "from": fv, "to": locked,
                                        "term": term_row.get("src"),
                                        "rule": "禁用变体 → 锁定译法（术语表显式登记，确定性可修）"})
        if "num_verify" not in ablate:
            sn, tn = scan_numbers(src_text), scan_numbers(txt)
            _h, _s, fix_plan = _num_pair_issues(sn, tn)
            edits = []
            for a, b in fix_plan:
                st, en, nt = _fix_number_token(a, b)
                if nt and nt != b["text"]:
                    edits.append((st, en, nt, a["text"], b["text"]))
            if edits:
                for st, en, nt, _a, _b in sorted(edits, key=lambda x: x[0], reverse=True):
                    txt = txt[:st] + nt + txt[en:]
                changes.append({"seg": seg, "kind": "number_fix", "before": t.get("tgt_text", ""),
                                "after": txt,
                                "detail": [{"src": a, "was": b, "now": nt}
                                           for _st, _en, nt, a, b in edits][:6],
                                "rule": "数值与原文不符 → 回写原文绝对值（保持译文量级风格）"})
        row["tgt_text"] = txt
        fixed.append(row)
    return fixed


def analyze(segs, trrows, terms, ablate=None, fix=False):
    """核心分析。返回 (report, fixed_rows, changes, per_seg_metrics)。

    detected_by_pipeline : 管线（受 ablate 开关影响）自己发现了多少问题
    artifact_*            : 独立评估器对**最终产物**的全强度判定（不受 ablate 影响）
    消融模式下 detected_by_pipeline 会显著下降而 artifact_* 基本不变——
    这正是「机制失效=问题不再被看见」的可测证据。
    """
    ablate = set(ablate or [])
    t0 = time.time()
    segs = [s for s in segs if isinstance(s, dict) and "_bad_line" not in s and s.get("seg")]
    trs = {r["seg"]: r for r in trrows if isinstance(r, dict) and "_bad_line" not in r and r.get("seg")}

    problems = []
    detected = {"segment": 0, "number": 0, "citation": 0, "term": 0, "coverage": 0, "soft": 0}
    changes = []

    # ---- 1) 段对应 ----
    seg_ids = {s["seg"] for s in segs}
    missing = sorted(seg_ids - set(trs))
    extra = sorted(set(trs) - seg_ids)
    role_bad = [s["seg"] for s in segs if s["seg"] in trs and s.get("role") and trs[s["seg"]].get("role")
                and trs[s["seg"]]["role"] != s["role"]]
    if missing or extra or role_bad:
        detected["segment"] += 1
        problems.append({"type": "segment_mismatch", "missing": missing[:20],
                         "extra": extra[:20], "role_bad": role_bad[:20],
                         "hint": "段号/段数/role 未一一对应"})

    # ---- 2) 逐段检测（受 ablate 开关控制） ----
    num_detail, cite_detail, term_detail, cov_detail = [], [], [], []
    for s in segs:
        seg = s["seg"]
        t = trs.get(seg)
        src_text = s.get("src_text") or ""
        tgt_text = (t or {}).get("tgt_text") or ""
        if not t or not tgt_text.strip():
            continue
        if "num_verify" not in ablate:
            sn, tn = scan_numbers(src_text), scan_numbers(tgt_text)
            h, so, _fp = _num_pair_issues(sn, tn)
            for x in h:
                x["seg"] = seg
                num_detail.append(x)
                detected["number"] += 1
            for x in so:
                x["seg"] = seg
                detected["soft"] += 1
        if "cite_anchor" not in ablate:
            sc, tc = _cites(src_text), _cites(tgt_text)
            if sc != tc:
                cite_detail.append({"seg": seg, "src": sc[:10], "tgt": tc[:10],
                                    "hint": "引用标记序列不一致（漏引/改编号），需人工核对原位"})
                detected["citation"] += 1
        if "term_lock" not in ablate and terms:
            missing_t, forbidden_t = _seg_term_issues(src_text, tgt_text, terms)
            for x in missing_t:
                x["seg"] = seg
            for x in forbidden_t:
                x["seg"] = seg
            term_detail.extend(missing_t + forbidden_t)
            detected["term"] += len(missing_t) + len(forbidden_t)
        if "coverage" not in ablate:
            trunc, tinfo = _is_truncated(src_text, tgt_text, terms)
            if trunc:
                cov_detail.append(dict({"seg": seg}, **tinfo))
                detected["coverage"] += 1

    if num_detail:
        problems.append({"type": "number_mismatch", "count": len(num_detail), "detail": num_detail[:15]})
    if cite_detail:
        problems.append({"type": "citation_mismatch", "count": len(cite_detail), "detail": cite_detail[:15]})
    if term_detail:
        problems.append({"type": "term_violation", "count": len(term_detail), "detail": term_detail[:15]})
    if cov_detail:
        problems.append({"type": "omission", "count": len(cov_detail), "detail": cov_detail[:15]})

    # ---- 3) 修复 + 最终产物 ----
    raw_rows = [dict(trs[s["seg"]]) for s in segs if s["seg"] in trs]
    pre_ev = evaluate_artifact(raw_rows, segs, terms)
    fixed_rows = _apply_fixes(segs, trs, terms, ablate, changes) if fix else raw_rows
    post_ev = evaluate_artifact(fixed_rows, segs, terms)
    ev = post_ev

    hard = [p for p in problems if p["type"] in ("segment_mismatch", "number_mismatch",
                                                "citation_mismatch", "term_violation")]
    det_hard = (detected["segment"] + detected["number"] + detected["citation"] + detected["term"])
    pre_hard = pre_ev["metrics"]["hard_issues"]
    report = {
        "segments": len(segs), "translated": len(trs),
        "problems": problems, "fail": len(hard),
        "verdict": "pass" if not hard else "fail",
        "ablate": sorted(ablate), "fixes_applied": len(changes),
        "detected_by_pipeline": detected,
        "detected_total": sum(detected.values()),
        "detection_recall": round(det_hard / pre_hard, 4) if pre_hard else None,
        "artifact_metrics": post_ev["metrics"],
        "pre_fix_artifact_metrics": pre_ev["metrics"],
        "omitted_segments": [seg for seg, r in post_ev["per_segment"].items() if r["omitted"]],
        "elapsed_sec": round(time.time() - t0, 3),
        "hint": "verdict 照实记录；本脚本任何失败路径均 exit 0，不中断交付流水线。"
                "detected_by_pipeline=管线自己发现的问题数；detection_recall=发现数/修复前产物实际问题数；"
                "artifact_metrics=独立评估器对修复后产物的全强度判定。",
    }
    return report, fixed_rows, changes, post_ev["per_segment"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", required=True)
    ap.add_argument("--translation", required=True)
    ap.add_argument("--aligned", default=None)
    ap.add_argument("--terminology", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--fix-out", default=None, help="写出修复后的 translation.jsonl")
    ap.add_argument("--fix-changes", default=None, help="写出修改记录 JSON")
    ap.add_argument("--ablate", default="", help="退化模式：term_lock,num_verify,cite_anchor,coverage")
    ap.add_argument("--metrics-out", default=None)
    args = ap.parse_args()

    ablate = [x.strip() for x in (args.ablate or "").split(",") if x.strip()]
    segs = _load_jsonl(args.segments)
    trrows = _load_jsonl(args.translation)
    terms = _load_jsonl(args.terminology) if args.terminology else None

    if segs is None or trrows is None:
        report = {"verdict": "error", "fail": 1, "problems": [],
                  "hint": "segments.jsonl / translation.jsonl 缺失，无法校验；请补齐后重跑。本脚本不中断流水线（exit 0）。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "error", "hint": report["hint"]}, ensure_ascii=False))
        return 0

    report, fixed_rows, changes, per_seg = analyze(segs, trrows, terms, ablate=ablate, fix=True)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if args.fix_out:
        os.makedirs(os.path.dirname(args.fix_out) or ".", exist_ok=True)
        with open(args.fix_out, "w", encoding="utf-8") as f:
            for r in fixed_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if args.fix_changes:
        os.makedirs(os.path.dirname(args.fix_changes) or ".", exist_ok=True)
        json.dump(changes, open(args.fix_changes, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if args.metrics_out:
        os.makedirs(os.path.dirname(args.metrics_out) or ".", exist_ok=True)
        json.dump(report["artifact_metrics"], open(args.metrics_out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    print(json.dumps({"verdict": report["verdict"], "segments": report["segments"],
                      "translated": report["translated"], "fail": report["fail"],
                      "detected_total": report["detected_total"], "fixes": len(changes),
                      "ablate": ablate, "elapsed_sec": report["elapsed_sec"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
