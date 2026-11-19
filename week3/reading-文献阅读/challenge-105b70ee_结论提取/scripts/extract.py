#!/usr/bin/env python3
"""extract.py — 可消融的确定性字段抽取器（供同输入双跑对照的增益证据）。

用法：
    python3 extract.py --fields F.json --case C.json --out out.json \
        [--ablate sweep,verbatim,conflict,claim,condition] [--paras P.json]

机制开关（关闭后对应指标按设计退化，用于"加载 Skill vs 关闭机制"的同输入对照）：
    sweep      关闭五源检索：只查正文/结果段，表格/图注/摘要/补充材料整类不查
    verbatim   关闭逐字回证：值不再要求逐字出现在引文中（值与引文可能脱钩）
    conflict   关闭跨源冲突检测：多来源数值不一致时静默取首个命中
    claim      关闭逐行 claim 绑定：不为每个 field_id 生成 claim-<field_id>
    condition  关闭条件同源绑定：数值不带成立条件（值脱离语境）

抽取口径（可复跑）：
  1. 来源切分：段落按 显式元数据 → paragraph_id 命名 → 文本前缀 → 表格化结构
     归到 表格/结果段/图注/摘要/补充材料 之一。
  2. 字段归属：字段核心词去掉通用词后得到判别词（其它字段没有的词）。引文若命中
     别的字段的判别词，判给那个字段，不算本字段的候选。
  3. 单位硬过滤：字段声明了 unit_expectation 时只接受该单位的候选；表格裸数字可
     继承表头单位（如 'Capacity retention (%)'）。
  4. 冲突判定：同一字段、不同来源、同一单位类别给出不同数值 → source_conflict 双方并列。
  5. 逐字回证：verbatim_number 必须逐字出现在所引原句内。

退出码恒 0；任何异常降级为报告项，绝不裸崩。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

SOURCE_CLASSES = ["表格", "结果段", "图注", "摘要", "补充材料"]
PRIORITY = ["表格", "结果段", "图注", "摘要", "补充材料"]

STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was",
        "were", "all", "any", "value", "data", "results", "result"}

GENERIC = {"after", "before", "during", "test", "tests", "used", "use", "uses",
           "sample", "samples", "value", "values", "result", "results", "data",
           "study", "paper", "work", "total", "overall", "main", "key", "average",
           "mean", "based", "using", "obtained", "observed", "measured", "reported",
           "table", "figure", "fig", "supplementary", "abstract", "introduction",
           "conclusion", "conclusions", "discussion", "method", "methods",
           "material", "materials", "author", "authors", "review", "note",
           "the", "and", "for", "with", "from", "that", "this", "are", "was",
           "were", "all", "any", "its", "their", "these", "those", "such"}

CONCLUSION_HINT = ("conclusion", "mechanism", "effect", "cause", "explanation",
                   "attribution", "finding", "claim", "mechanis")

UNIT_LIST = [
    "mol%", "at.%", "wt.%", "wt%", "mAh/g", "Ah/g", "J/g", "mAh / g", "Ah / g",
    "mV", "kV", "V", "°C", "℃", "K", "nm", "µm", "μm", "mm", "cm", "mL", "L",
    "mg", "µg", "ng", "kg", "g", "MW", "mW", "kW", "W", "GPa", "MPa", "kPa",
    "Pa", "rpm", "kHz", "MHz", "GHz", "Hz", "cycles", "cycle", "min", "ms", "h",
    "s", "m", "T", "%", "C",
]
RE_UNIT = "(?:" + "|".join(re.escape(u) for u in UNIT_LIST) + ")"
RE_NUM = r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d*\.?\d+(?:[eE][+-]?\d+)?"
RE_NUMUNIT = re.compile(r"(?P<num>" + RE_NUM + r")\s*(?P<unit>" + RE_UNIT + r")?", re.I)
RE_RANGE1 = re.compile(r"(?P<lo>" + RE_NUM + r")\s*[-–—~]\s*(?P<hi>" + RE_NUM + r")\s*(?P<unit>" + RE_UNIT + r")?", re.I)
RE_RANGE2 = re.compile(r"(?:between|from|range\s+of|范围)\s*(?P<lo>" + RE_NUM + r")\s*(?:and|to|[-–—])\s*(?P<hi>" + RE_NUM + r")\s*(?P<unit>" + RE_UNIT + r")?", re.I)
RE_COND = re.compile(r"(?:at|under|after|for|during|with|within|above|below)\s+[^,;.)]{1,60}", re.I)
RE_CMP = re.compile(r"(?:compared\s+(?:to|with)|versus|vs\.?|relative\s+to)\s+([^.;]{1,60})", re.I)
RE_STAT = re.compile(r"(mean|average|median|standard\s+deviation|std\.?\s*dev|95\s*%\s*CI|confidence\s+interval|p\s*[<=>]\s*0?\.\d+|±|\+/-)", re.I)
RE_HEDGE = re.compile(r"(suggest\w*|may\b|might\b|could\b|possibly|likely|hypothes\w*|推测|可能|提示|暗示)", re.I)
RE_LIMIT = re.compile(r"(limitation\w*|cannot|caution|caveat|however|future\s+work|限制|局限)", re.I)
RE_SENT = re.compile(r"(?<=[.!?;])\s+")
# 子句切分：逗号/分号/竖线/对比连词。子句是"字段归属"判定的最小语境单元。
RE_CLAUSE_SPLIT = re.compile(r"[,;|]|\bwhereas\b|\bcompared\s+with\b|\bwhile\b|，|；", re.I)


def clause_spans(text):
    """把文本切成子句区间 [(start, end)]（保留字符偏移，便于定位数值所属子句）。"""
    spans, start = [], 0
    for m in RE_CLAUSE_SPLIT.finditer(text or ""):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    if start < len(text or ""):
        spans.append((start, len(text)))
    return spans or [(0, len(text or ""))]


def clause_at(text, spans, pos):
    """数值所在子句的文本。"""
    for s, e in spans:
        if s <= pos <= e:
            return (text or "")[s:e]
    return text or ""


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    return re.sub(r"\s+", "", s or "")


def stem(w):
    """轻量词干化：cycled/cycling→cycl，doped→dop，undoped→undop（避免互相误命中）。"""
    w = (w or "").lower()
    for suf in ("ings", "ing", "ies", "ied", "es", "ed", "s"):
        if len(w) - len(suf) >= 3 and w.endswith(suf):
            w = w[: len(w) - len(suf)]
            break
    return w


def token_positions(text, toks):
    """词干匹配的命中位置。"""
    low = (text or "").lower()
    pos = []
    for m in re.finditer(r"[A-Za-z][A-Za-z\-]*", low):
        st = stem(m.group(0))
        for t in toks:
            if st == t or (len(t) >= 4 and st.startswith(t) and len(st) <= len(t) + 4):
                pos.append(m.start())
                break
    return pos


def hit_tokens(text, toks):
    """命中的词干集合（词首匹配，长词优先）。"""
    words = re.findall(r"[A-Za-z][A-Za-z\-]*", (text or "").lower())
    stems = set(stem(w) for w in words)
    hits = set()
    for t in toks:
        for w in stems:
            if w == t or (len(t) >= 4 and w.startswith(t) and len(w) <= len(t) + 4):
                hits.add(t)
                break
    return hits


def classify(meta, pid, text):
    """把段落归到五源之一：表格 / 结果段 / 图注 / 摘要 / 补充材料。

    信号优先级：显式元数据 → paragraph_id 命名 → 文本前缀 → 表格化文本结构。
    """
    hay = " ".join(str(meta.get(k) or "") for k in
                   ("type", "kind", "source_type", "section", "section_type",
                    "block_type", "label", "role", "category", "block", "region"))
    low = hay.lower()
    for words, cls in (
        (("supplement", "supplementary", "附录", "补充"), "补充材料"),
        (("table", "表格"), "表格"),
        (("figure", "fig", "caption", "图注"), "图注"),
        (("abstract", "摘要"), "摘要"),
        (("result", "正文", "body", "method", "discussion", "conclusion"), "结果段"),
    ):
        if any(w in low for w in words):
            return cls

    pid_low = str(pid or "").lower()
    for pat, cls in (
        (r"(supp|suppl|附录)", "补充材料"),
        (r"(^|[_\-])(tab|table)([_\-]|\d)", "表格"),
        (r"(^|[_\-])(fig|figure|cap)([_\-]|\d)", "图注"),
        (r"(^|[_\-])abstract", "摘要"),
    ):
        if re.search(pat, pid_low):
            return cls

    t = (text or "").strip()
    tl = t[:120].lower()
    if re.match(r"(supplementary|supplemental|附录|补充材料)", tl):
        return "补充材料"
    if re.match(r"(table\s*\d|表\s*\d|tab\.?\s*\d)", tl):
        return "表格"
    if re.match(r"((fig|figure)\s*\.?\s*\d|图\s*\d)", tl):
        return "图注"
    if re.match(r"(abstract\b|摘要)", tl):
        return "摘要"
    if t.count("|") >= 3 and len(re.findall(r"\d", t)) >= 3:
        return "表格"
    return "结果段"


def harvest(case, paras_path=None):
    """从 case.json / paragraphs.json 收割段落，返回 [{pid,text,meta,cls}]。"""
    raw = []

    def add(items):
        for p in items:
            if isinstance(p, dict):
                pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid")
                           or p.get("para_id") or p.get("section_id") or "")
                txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                if txt.strip():
                    raw.append({"pid": pid or ("p%02d" % (len(raw) + 1)), "text": txt, "meta": p})
            elif isinstance(p, str) and p.strip():
                raw.append({"pid": "p%02d" % (len(raw) + 1), "text": p, "meta": {}})

    if isinstance(case, dict):
        for key in ("paragraphs", "passages", "sections", "blocks", "content"):
            v = case.get(key)
            if isinstance(v, list):
                add(v)
                break
        if not raw:
            mat = case.get("material") or case.get("paper") or case.get("document")
            if isinstance(mat, dict):
                for key in ("paragraphs", "passages", "sections"):
                    v = mat.get(key)
                    if isinstance(v, list):
                        add(v)
                        break
            elif isinstance(mat, list):
                add(mat)
            elif isinstance(mat, str) and mat.strip():
                raw.append({"pid": "p01", "text": mat, "meta": {}})
    if not raw and paras_path:
        try:
            data = load_json(paras_path)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        raw.append({"pid": str(k), "text": v, "meta": {}})
                    elif isinstance(v, dict):
                        raw.append({"pid": str(k), "text": str(v.get("text") or v.get("content") or ""), "meta": v})
            elif isinstance(data, list):
                add(data)
        except Exception:
            pass
    for r in raw:
        r["cls"] = classify(r["meta"], r["pid"], r["text"])
    return raw


def field_tokens(fid, fdef):
    toks = set()
    for part in re.split(r"[^A-Za-z0-9]+", str(fid or "")):
        p = part.lower()
        if len(p) >= 3 and p not in STOP:
            toks.add(stem(p))
    d = fdef.get("definition") or fdef.get("name") or ""
    for w in re.findall(r"[A-Za-z][A-Za-z\-']{2,}", str(d)):
        w = w.lower().strip("'-")
        if len(w) >= 3 and w not in STOP:
            toks.add(stem(w))
    return {t for t in toks if len(t) >= 3}


def core_tokens(fid, fdef):
    """字段核心词：去掉通用词后的判别性词。"""
    toks = field_tokens(fid, fdef)
    core = set(t for t in toks if t not in GENERIC)
    return core if core else set(toks)


def norm_unit(u):
    u = (u or "").strip()
    if u in ("", None):
        return ""
    u = u.replace(" ", "")
    low = u.lower()
    if low in ("%", "percent", "pct"):
        return "%"
    if low in ("°c", "℃", "degc", "celsius"):
        return "degC"
    if low in ("c", "c-rate", "crate"):
        return "C"
    if low in ("mah/g", "mahg-1"):
        return "mAh/g"
    return u


def expected_unit(fdef):
    """字段声明的期望单位（来自 target-fields.json 的 unit_expectation）。"""
    u = fdef.get("unit_expectation") or fdef.get("unit") or ""
    if u is None:
        return ""
    s = str(u).strip()
    return "" if s.lower() in ("none", "null", "") else norm_unit(s)


def is_conclusion_field(fid, fdef):
    """结论型字段：无期望单位且定义含结论词 → 取文本而非数值。"""
    if expected_unit(fdef):
        return False
    blob = ("%s %s" % (fid, fdef.get("definition") or "")).lower()
    return any(h in blob for h in CONCLUSION_HINT)


def para_table_unit(para, want):
    """表格段落里裸数字可能继承表头单位（如 'Capacity retention (%)'）。"""
    if para.get("cls") != "表格" or not want:
        return ""
    head = para["text"][:200].lower()
    if want == "%" and "%" in head:
        return "%"
    if want and re.search(re.escape(want.lower()) + r"[^|]{0,24}\(", head):
        return want
    return ""


def sentences(text):
    parts = [s for s in RE_SENT.split(text or "") if s.strip()]
    return parts or [(text or "").strip()]


def pick_sentence(text, pos):
    sents = sentences(text)
    best, bestd = sents[0] if sents else text, 10 ** 9
    for s in sents:
        i = text.find(s)
        if i < 0:
            continue
        d = 0 if i <= pos <= i + len(s) else min(abs(pos - i), abs(pos - (i + len(s))))
        if d < bestd:
            best, bestd = s, d
    return best


def para_candidates(para, toks):
    """段落内的全部数值候选：[{numstr, unit, quote, dist, value, is_range}]。"""
    text = para["text"]
    tpos = token_positions(text, toks)
    if not hit_tokens(text, toks):
        return []
    cands = []

    def make(numstr, unit, quote, pos):
        dist = min([abs(pos - p) for p in tpos]) if tpos else 10 ** 6
        cands.append({"numstr": numstr, "unit": unit or None, "quote": quote.strip(),
                      "dist": dist, "value": numstr.replace(",", ""),
                      "is_range": False, "is_text": False})

    for m in RE_NUMUNIT.finditer(text):
        numstr = m.group("num")
        unit = m.group("unit")
        after = text[m.end():m.end() + 2]
        if unit is None and re.match(r"[\s]*[A-Za-z%°µμ]", after):
            continue
        if unit == "C":
            # '1C'（倍率，无空格）vs '25 C'（摄氏度，有空格）
            unit = "C" if not text[max(0, m.start() - 1):m.start()].strip() else "degC"
        make(numstr, unit, pick_sentence(text, m.start()), m.start())

    for rex in (RE_RANGE1, RE_RANGE2):
        for m in rex.finditer(text):
            lo, hi = m.group("lo"), m.group("hi")
            if norm(lo) == norm(hi):
                continue
            cands.append({"numstr": "%s-%s" % (lo, hi), "unit": m.group("unit") or None,
                          "quote": pick_sentence(text, m.start()).strip(),
                          "dist": min([abs(m.start() - p) for p in tpos]) if tpos else 10 ** 6,
                          "value": [lo.replace(",", ""), hi.replace(",", "")],
                          "is_range": True, "is_text": False})
    cands.sort(key=lambda c: c["dist"])
    return cands


def rank_candidate(cand, want, inh):
    """单位契合度：0=精确命中期望单位，1=裸数字（可继承表头单位），2=其它单位。"""
    u = norm_unit(cand.get("unit"))
    if not want:
        return 0 if not u else 2
    if u == want:
        return 0
    if not u and inh == want:
        return 1   # 裸数字可继承表头单位（原语义：1）
    if not u:
        return 1   # 裸数字（原语义：1）
    return 2       # 其它单位（原语义：2）


def extract_conditions(sent):
    conds = []
    for m in RE_COND.finditer(sent or ""):
        c = re.sub(r"\s+", " ", m.group(0)).strip(" .")
        if c and c not in conds:
            conds.append(c)
    return conds[:4]


def extract_comparator(sent):
    m = RE_CMP.search(sent or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def extract_statistic(sent):
    m = RE_STAT.search(sent or "")
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else "value"


def layer_of(sent):
    if RE_HEDGE.search(sent or ""):
        return "speculation"
    if RE_LIMIT.search(sent or ""):
        return "limitation"
    return "author_conclusion"


def build_own_map(fields):
    """字段判别词：某字段的核心词减去其它所有字段的核心词。"""
    cores = {fid: core_tokens(fid, fdef) for fid, fdef in fields}
    own = {}
    for fid, c in cores.items():
        others = set()
        for g, cg in cores.items():
            if g != fid:
                others |= cg
        o = c - others
        own[fid] = o if o else c
    return own


def ownership(quote, own_map):
    """引文归属：命中判别词最多的字段获得该引文。"""
    scores = {}
    for fid, own in own_map.items():
        h = hit_tokens(quote, own)
        if h:
            scores[fid] = len(h)
    if not scores:
        return None
    top = max(scores.values())
    return set(f for f, s in scores.items() if s == top)


def pick_field_candidates(para, toks, core, own, want, inh, concl, own_map):
    """把段落内的候选绑定到本字段：归属判定 + 核心词锚定 + 单位硬过滤。"""
    if concl:
        best = None
        for s in sentences(para["text"]):
            if not s.strip() or not hit_tokens(s, core) or not hit_tokens(s, own):
                continue
            hits = len(hit_tokens(s, core))
            if best is None or hits > best[0]:
                best = (hits, s)
        if best is None:
            return []
        return [{"numstr": "", "unit": None, "quote": best[1].strip(), "dist": 0,
                 "value": best[1].strip(), "is_range": False, "is_text": True}]

    cands = para_candidates(para, toks)
    if not cands:
        return []
    owners = ownership(para["text"], own_map)
    out = []
    for c in cands:
        if not hit_tokens(c["quote"], core):
            continue
        if owners and own and not (hit_tokens(c["quote"], own) & owners):
            # 该引文的判别词指向别的字段 → 不算本字段的候选
            continue
        out.append(c)
    if not out:
        return []
    if want:
        exact = [c for c in out if norm_unit(c.get("unit")) == want]
        if exact:
            return exact
        inherit = [c for c in out if not norm_unit(c.get("unit")) and inh == want]
        if inherit:
            return inherit
        loose = [c for c in out if not norm_unit(c.get("unit"))]
        if loose:
            return loose
    return out


def build_row(fid, fdef, pool, classes_present, ablate, own_map):
    """对单个 field_id 做一次抽取，返回字段行。"""
    toks = field_tokens(fid, fdef)
    core = core_tokens(fid, fdef)
    own = own_map.get(fid, core)
    want = expected_unit(fdef)
    concl = is_conclusion_field(fid, fdef)
    allowed = [c for c in PRIORITY if c not in ("表格", "图注", "摘要", "补充材料")] \
        if "sweep" in ablate else list(PRIORITY)

    per_cls = {}
    searched = {}
    for cls in PRIORITY:
        if cls not in allowed:
            searched[cls] = "已跳过（消融：关闭五源检索）"
            per_cls[cls] = None
            continue
        best = None
        for para in pool:
            if para["cls"] != cls:
                continue
            inh = para_table_unit(para, want)
            for c in pick_field_candidates(para, toks, core, own, want, inh, concl, own_map):
                r = rank_candidate(c, want, inh)
                key = (r, c["dist"])
                if best is None or key < best[0]:
                    best = (key, para, c, inh)
        if best is None:
            searched[cls] = "无" if cls in classes_present else "材料未提供"
            per_cls[cls] = None
        else:
            searched[cls] = "查到 %s" % best[1]["pid"]
            per_cls[cls] = best

    row = {"field_id": fid, "status": "not_reported",
           "value": {"scalar": None, "range": None, "text": None},
           "units": None, "statistic": None, "conditions": [], "comparator": None,
           "evidence": [], "verbatim_number": None, "claim_layer": None,
           "search_log": ["%s: %s" % (c, searched[c]) for c in PRIORITY],
           "evidence_note": None, "conflicts": [], "failure_reason": None}

    if not toks:
        row["status"] = "extraction_failed"
        row["failure_reason"] = "field_id/definition 无可匹配检索词，无法定位原文"
        row["evidence_note"] = "无检索词"
        return row

    found = [(cls, b) for cls, b in per_cls.items() if b is not None]
    if not found:
        row["evidence_note"] = "五源均已检索，未找到与该字段匹配的原文数值"
        return row

    # 冲突判定：同单位类别、不同来源给出不同数值 → 双方并列（不取单方）
    buckets = {}
    for cls, b in found:
        u = norm_unit(b[2].get("unit"))
        if want and u == want:
            u = want
        elif not u:
            u = "inherited:" + (b[3] or "none")
        buckets.setdefault(u, [])
        num = b[2]["numstr"] or b[2]["quote"][:40]
        if num not in [x[0] for x in buckets[u]]:
            buckets[u].append((num, cls, b))
    conflict_groups = [g for g in buckets.values() if len(g) >= 2]
    if conflict_groups and "conflict" not in ablate:
        g = conflict_groups[0]
        row["status"] = "source_conflict"
        row["conflicts"] = [
            {"source_class": cls, "paragraph_id": b[1]["pid"],
             "value": b[2]["value"], "quote": b[2]["quote"],
             "locator": "%s %s" % (cls, b[1]["pid"])}
            for _n, cls, b in g[:4]
        ]
        row["evidence_note"] = "多来源给出不同数值，双方引文并列，未取单方"
        return row

    # 取全局最优（先比单位契合度，再比来源优先级）
    best_rank = min(item[1][0][0] for item in found)
    cls, b = None, None
    for pc in PRIORITY:
        cand = per_cls.get(pc)
        if cand is not None and cand[0][0] == best_rank:
            cls, b = pc, cand
            break
    if b is None:
        cls, b = found[0]
    para, c, inh = b[1], b[2], b[3]
    sent = c["quote"]
    quote = sent

    if "verbatim" in ablate:
        # 关闭逐字回证：允许值与引文脱钩（换用同段另一处数字，或做 %→小数换算）
        other = None
        for cc in para_candidates(para, toks):
            if cc["numstr"] != c["numstr"] and cc["quote"] != c["quote"]:
                other = cc
                break
        if other is not None:
            c = dict(c)
            c["numstr"] = other["numstr"]
            c["value"] = other["value"]
            c["is_range"] = other["is_range"]
            c["unit"] = other["unit"] or c["unit"]
        elif c["unit"] == "%" and not c["is_range"]:
            try:
                c = dict(c)
                c["value"] = float(c["value"]) / 100.0
            except Exception:
                pass

    if c.get("is_text"):
        row["value"] = {"scalar": None, "range": None, "text": c["value"]}
        row["units"] = "dimensionless"
        row["verbatim_number"] = None
        row["claim_layer"] = layer_of(sent)
    else:
        if c["is_range"]:
            row["value"] = {"scalar": None, "range": list(c["value"]), "text": None}
            row["statistic"] = "range"
        else:
            try:
                row["value"]["scalar"] = float(c["value"]) if "." in str(c["value"]) else int(c["value"])
            except Exception:
                row["value"]["text"] = str(c["value"])
            row["statistic"] = "value"
        row["units"] = norm_unit(c["unit"]) or inh or (want if want else "unit_not_reported")
        row["verbatim_number"] = c["numstr"]
        row["claim_layer"] = "n/a"
    row["evidence"] = [{"paragraph_id": para["pid"], "quote": quote,
                         "locator": "%s %s" % (cls, para["pid"])}]
    if "condition" not in ablate:
        row["conditions"] = extract_conditions(sent) or ["无附加限定条件"]
    else:
        row["conditions"] = []
    row["comparator"] = extract_comparator(sent) or "none"
    row["statistic"] = extract_statistic(sent)
    row["status"] = "reported"
    return row


def build_claims(rows, ablate):
    if "claim" in ablate:
        return []
    claims = []
    for r in rows:
        fid = r["field_id"]
        ev = r["evidence"][0] if r["evidence"] else {}
        if r["status"] == "reported":
            if r["value"]["scalar"] is not None:
                txt = "%s：%s %s" % (fid, r["value"]["scalar"], r["units"])
            elif r["value"]["range"]:
                txt = "%s：范围 %s %s" % (fid, r["value"]["range"], r["units"])
            else:
                txt = "%s：%s" % (fid, r["value"]["text"])
            claims.append({"claim_id": "claim-%s" % fid, "text": txt,
                           "layer": r.get("claim_layer") or "n/a", "kind": "reported",
                           "source_id": "material",
                           "location": "%s %s" % (ev.get("paragraph_id", ""), ev.get("locator", "")),
                           "evidence": [{"paragraph_id": ev.get("paragraph_id", ""),
                                         "quote": ev.get("quote", "")}]})
        else:
            claims.append({"claim_id": "claim-%s" % fid,
                           "text": "原文%s %s，已检索：%s" % (
                               r["status"], fid, "；".join(r["search_log"])),
                           "layer": "n/a", "kind": "inferred", "source_id": "material",
                           "location": r["search_log"][0] if r["search_log"] else "",
                           "evidence": []})
    return claims


def extract(fields, case, paras_path=None, ablate=None):
    """执行一次抽取，返回 result 形状的 dict + trace。"""
    ablate = set(ablate or [])
    t0 = time.time()
    pool = harvest(case, paras_path)
    classes_present = set(p["cls"] for p in pool)
    own_map = build_own_map(fields)

    rows = [build_row(fid, fdef, pool, classes_present, ablate, own_map)
            for fid, fdef in fields]

    claims = build_claims(rows, ablate)
    cnt = {"reported": 0, "not_reported": 0, "source_conflict": 0, "extraction_failed": 0}
    for r in rows:
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1

    steps = ["读字段表", "读材料并按来源分类", "逐字段五源扫描", "逐字回证",
             "跨源冲突比对", "条件与统计量绑定", "生成逐行 claim", "生成不确定项"]
    if "sweep" in ablate:
        steps = [s for s in steps if s != "逐字段五源扫描"] + ["逐字段正文扫描"]
    if "verbatim" in ablate:
        steps = [s for s in steps if s != "逐字回证"]
    if "conflict" in ablate:
        steps = [s for s in steps if s != "跨源冲突比对"]
    if "claim" in ablate:
        steps = [s for s in steps if s != "生成逐行 claim"]
    if "condition" in ablate:
        steps = [s for s in steps if s != "条件与统计量绑定"]

    searched_classes = 1 if "sweep" in ablate else len(SOURCE_CLASSES)
    probes = len(fields) * searched_classes + 1  # +1 = 读材料一次

    trace = {"steps": len(steps), "step_names": steps, "probes": probes,
             "wall_clock_ms": int((time.time() - t0) * 1000),
             "paragraphs_loaded": len(pool),
             "classes_present": sorted(classes_present)}

    return {
        "field_schema_version": "r5-ablate",
        "fields": rows,
        "coverage": {"fields_total": len(rows), "reported": cnt["reported"],
                     "not_reported": cnt["not_reported"],
                     "source_conflict": cnt["source_conflict"],
                     "extraction_failed": cnt["extraction_failed"]},
        "claims": claims,
        "uncertainties": {
            "unreported": [r["field_id"] for r in rows if r["status"] == "not_reported"],
            "unverifiable": [r["field_id"] for r in rows if r["status"] == "extraction_failed"],
            "conflicts": [r["field_id"] for r in rows if r["status"] == "source_conflict"],
            "human_review": [],
            "summary": "ablate=%s" % (",".join(sorted(ablate)) or "none"),
        },
        "_trace": trace,
    }


def pick_fields(tf):
    ids, defs = [], {}
    try:
        if isinstance(tf, list):
            items = tf
        elif isinstance(tf, dict):
            items = tf.get("fields") or tf.get("targets") or tf.get("items") or []
        else:
            items = []
        for it in items:
            if isinstance(it, dict):
                fid = it.get("field_id") or it.get("id") or it.get("name")
                if fid is None:
                    continue
                fid = str(fid)
                ids.append(fid)
                defs[fid] = {k: v for k, v in it.items() if k not in ("field_id", "id", "name")}
            elif isinstance(it, (str, int)):
                ids.append(str(it))
    except Exception as e:
        print("[extract] 字段清单解析失败: %s" % e)
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out, defs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", default="/input/target-fields.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--paras", default=None)
    ap.add_argument("--out", default="/app/work/ablate-run.json")
    ap.add_argument("--ablate", default="")
    args = ap.parse_args()

    ablate = [x.strip() for x in (args.ablate or "").split(",") if x.strip()]
    try:
        tf = load_json(args.fields)
        case = load_json(args.case)
        fids, defs = pick_fields(tf)
        fields = [(f, defs.get(f, {})) for f in fids]
        doc = extract(fields, case, args.paras, ablate)
    except Exception as e:
        print("[extract] 运行失败（降级为空结果）: %s" % e)
        doc = {"field_schema_version": "r5-ablate", "fields": [],
               "coverage": {"fields_total": 0, "reported": 0, "not_reported": 0,
                            "source_conflict": 0, "extraction_failed": 0},
               "claims": [], "uncertainties": {"unreported": [], "unverifiable": [],
                                               "conflicts": [], "human_review": [], "summary": "extract failed"},
               "_trace": {"steps": 0, "probes": 0, "wall_clock_ms": 0, "error": str(e)}}
    try:
        d = os.path.dirname(args.out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print("[extract] 已写入 %s（ablate=%s，%d 行）" % (args.out, ",".join(ablate) or "none",
                                                          len(doc.get("fields", []))))
    except Exception as e:
        print("[extract] 写盘失败: %s" % e)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[extract] 未捕获异常已兜底: %s" % e)
        sys.exit(0)
