#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_run.py — clean2table-r3 清洗引擎（skeleton | profile | run | check）。

零第三方依赖。所有异常全捕获：返回非零码并打印原因，绝不裸崩；
run 模式中途失败时仍尽力写出 result.json（status 如实，绝不缺交付）。

r3 三项增强（相对 r2）：
  1. 清洗台账逐条嵌入：每行带 __changes__（该行全部 change_id），每个被改格在
     __raw__[field].ledger 内嵌 {change_id,kind,original,new,rule_id}，同时保留
     result.changelog 全量台账——审阅单行即可核对全部改动。
  2. 单位换算中间值留痕：每条 convert 变更带 trace（factor_source、前后缀因子、
     net_factor、offset、换算前后值、precision、recompute 公式串），可逐步复算。
  3. 脏值逐条登记：无法清洗的值（未知单位/不可解析格式）逐条进
     uncertainties.dirty_values（row_id/field/value/reason/pending_id），
     原值保留不静默丢弃，check 校验计数一致。

用法：
  python clean_run.py skeleton --case /input/case.json --outdir /app/output
  python clean_run.py profile   --case /input/case.json --out /app/work/profile.json
  python clean_run.py run       --case /input/case.json --rules /app/work/rules.json --outdir /app/output
  python clean_run.py check     --result /app/output/result.json --case /input/case.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import traceback

VERSION = "clean2table-r3/1.0"
DEFAULT_CONTRACT = ["case_id", "status", "result", "claims", "uncertainties"]
STATUS_VALUES = ["answered", "partial", "insufficient_evidence", "input_error"]

PREFIX = {"T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "K": 1e3, "": 1.0,
          "m": 1e-3, "u": 1e-6, "\u00b5": 1e-6, "\u03bc": 1e-6,
          "n": 1e-9, "p": 1e-12, "f": 1e-15}

MISSING_TOKENS = {"", "na", "n/a", "n.a.", "nd", "n.d.", "n/d", "-", "--", "—",
                  "none", "null", "nan", "?", "unknown", "unk", "未报告", "无", "缺失"}

ROW_KEYS = ("records", "rows", "extractions", "data", "items", "table",
            "observations", "entries", "points", "measurements", "values")
ID_KEYS = ("row_id", "id", "uid", "record_id", "行号", "行id")


# ---------------------------------------------------------------- 单位
def norm_unit(u: str) -> str:
    """归一单位写法：μ/µ 统一、去空格与中点、'g-1'→'/g'。"""
    s = str(u or "").strip()
    s = s.replace("\u00b5", "\u03bc").replace("\u2022", "*").replace("\u00b7", "*")
    s = re.sub(r"[\s\*]+([A-Za-z\u03bc%]+)-1", r"/\1", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", "", s)
    return s


def split_atom(u: str):
    if len(u) >= 2 and u[0] in PREFIX and u[0] != "":
        return u[0], u[1:]
    return "", u


def parse_value_unit(text):
    """'48.2 kPa'→(48.2,'kPa')；'3.1-4.4 mg/L'→((3.1,4.4),'mg/L')；失败→(None, 原串)。"""
    if text is None:
        return None, ""
    s = str(text).strip()
    if not s:
        return None, ""
    m = re.match(r"^([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*[-\u2013~]\s*"
                 r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(.+)$", s)
    if m:
        return (float(m.group(1)), float(m.group(2))), norm_unit(m.group(3))
    m = re.match(r"^([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(\S.*)$", s)
    if m:
        return float(m.group(1)), norm_unit(m.group(2))
    return None, norm_unit(s)


def convert_scalar(value, src_unit, dst_unit, factor=None, offset=0.0):
    """线性换算。返回 (新值, factor, formula, trace) 或 (None, None, reason, None)。不猜。

    trace 为中间值留痕：factor_source（identity|rule|si_prefix）、前后缀因子、
    net_factor、offset、value_in/value_out、recompute 公式串——换算可逐步复算。
    """
    su, du = norm_unit(src_unit), norm_unit(dst_unit)
    if su == du and factor is None:
        trace = {"factor_source": "identity", "net_factor": 1.0, "offset": 0.0,
                 "src_unit": su, "dst_unit": du, "value_in": value, "value_out": value,
                 "recompute": "%g x 1 + 0 = %g" % (value, value)}
        return value, 1.0, "同单位无换算", trace
    if factor is not None:
        pre = value * factor + offset
        trace = {"factor_source": "rule", "rule_factor": factor, "offset": offset,
                 "src_unit": su, "dst_unit": du, "value_in": value, "value_out": pre,
                 "recompute": "%g x %g %+g = %g" % (value, factor, offset, pre)}
        formula = "%g %s x %g %+g = %g %s" % (value, su or "-", factor, offset, pre, du or "-")
        return pre, factor, formula, trace

    def side(u):
        return (u.split("/", 1) + [""])[:2] if "/" in u else (u, "")

    sn, sd = side(su)
    dn, dd = side(du)
    if norm_unit(sd) != norm_unit(dd):
        return None, None, "分母单位不同: %r vs %r（不猜换算）" % (sd, dd), None
    sp, sb = split_atom(sn)
    dp, db = split_atom(dn)
    if sb != db:
        return None, None, "单位基准不同: %r vs %r（不猜换算）" % (sb, db), None
    if sp not in PREFIX or dp not in PREFIX:
        return None, None, "前缀无法识别: %r -> %r" % (sp, dp), None
    fac = PREFIX[sp] / PREFIX[dp]
    pre = value * fac + offset
    trace = {"factor_source": "si_prefix",
             "src_prefix": sp or "(none)", "src_prefix_factor": PREFIX[sp],
             "dst_prefix": dp or "(none)", "dst_prefix_factor": PREFIX[dp],
             "src_base": sb, "dst_base": db, "src_denom": sd, "dst_denom": dd,
             "net_factor": fac, "offset": offset,
             "src_unit": su, "dst_unit": du, "value_in": value, "value_out": pre,
             "recompute": "%g x (%g/%g) %+g = %g" % (value, PREFIX[sp], PREFIX[dp], offset, pre)}
    formula = "%g %s x %g %+g = %g %s" % (value, su, fac, offset, pre, du)
    return pre, fac, formula, trace


def is_missing(val) -> bool:
    if val is None:
        return True
    return str(val).strip().lower() in MISSING_TOKENS


# ---------------------------------------------------------------- 读入
def load_json_any(path):
    """utf-8 / utf-8-sig / gbk / latin-1 依次尝试；仍失败抛异常。"""
    last = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def contract_fields(case) -> list:
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None:
        return list(DEFAULT_CONTRACT)
    if isinstance(oc, dict):
        for key in ("fields", "required_fields", "result.json", "result"):
            v = oc.get(key)
            if isinstance(v, list):
                return [str(x) for x in v]
        return [str(k) for k in oc.keys()] or list(DEFAULT_CONTRACT)
    if isinstance(oc, list) and oc:
        return [str(x) for x in oc]
    return list(DEFAULT_CONTRACT)


def find_rows(obj, depth=0):
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("columns"), list) and isinstance(obj.get("data"), list):
            cols = [str(c) for c in obj["columns"]]
            out = []
            for d in obj["data"]:
                if isinstance(d, dict):
                    out.append(d)
                elif isinstance(d, list):
                    out.append({c: (d[i] if i < len(d) else None) for i, c in enumerate(cols)})
            return out
        for k in ROW_KEYS:
            v = obj.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
        if depth < 3:
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    r = find_rows(v, depth + 1)
                    if r:
                        return r
    return None


def flatten_rows(rows):
    """行内嵌 list-of-dicts（如 measurements）则展开为多行，保留父信息。"""
    out = []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            out.append({"__raw_text__": str(r), "__index__": i})
            continue
        nested = [k for k, v in r.items()
                  if isinstance(v, list) and v and isinstance(v[0], dict)]
        if not nested:
            rr = dict(r)
            rr["__index__"] = i
            out.append(rr)
            continue
        k = nested[0]
        base = {kk: vv for kk, vv in r.items() if kk != k}
        for j, sub in enumerate(r[k]):
            merged = dict(base)
            if isinstance(sub, dict):
                merged.update(sub)
            merged["__index__"] = "%d.%d" % (i, j)
            merged["__parent_key__"] = k
            out.append(merged)
    return out


def row_id_of(row, i) -> str:
    for k in ID_KEYS:
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return "row-%03d" % (i + 1)


def get_case_id(case) -> str:
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id"):
            if case.get(k):
                return str(case[k])
    return "unknown"


# ---------------------------------------------------------------- 规则
def load_rules(path):
    if not path or not os.path.exists(path):
        return [], "no-rules-file"
    doc = load_json_any(path)
    rules = doc if isinstance(doc, list) else (doc.get("rules") or [])
    rules = [r for r in rules if isinstance(r, dict)]
    rules.sort(key=lambda r: (r.get("priority", 100), str(r.get("rule_id", ""))))
    return rules, None


def rules_by_kind(rules, kind):
    return [r for r in rules if r.get("kind") == kind]


def default_rules(rows):
    """无规则文件时的保守兜底：缺失标记 + 全字段一致判重（row_id 不参与判定键）。"""
    fields = []
    for r in rows[:50]:
        for k in r:
            if not k.startswith("__") and k not in ID_KEYS and k not in fields:
                fields.append(k)
    return [
        {"rule_id": "AUTO-MM", "kind": "missing_mark", "priority": 900,
         "condition": {"fields": fields},
         "action": {"keep": "empty"},
         "rationale": "兜底：缺失标记不编造", "on_fail": "无"},
        {"rule_id": "AUTO-DD", "kind": "dedup", "priority": 999,
         "condition": {"key_fields": fields, "context_fields": []},
         "action": {"on_exact_key": "merge_keep_first", "on_partial_key": "no_merge_register"},
         "rationale": "兜底：全字段一致判为重复记录", "on_fail": "键不全则跳过"},
    ]


# ---------------------------------------------------------------- 清洗
def apply_clean(rows, rules, policy):
    changelog, pending, anomalies, conflicts, dirty = [], [], [], [], []
    merged_groups, suspected = [], []
    missing_report = {"fields": {}, "cells": []}
    synonyms_normalized = 0
    unknown_units = 0
    seq = {"c": 0, "p": 0}

    def next_id(prefix):
        seq["c" if prefix == "C" else "p"] += 1
        return "%s%04d" % (prefix, seq["c" if prefix == "C" else "p"])

    def add_change(**kw):
        kw["change_id"] = next_id("C")
        changelog.append(kw)

    def add_pending(**kw):
        kw["pending_id"] = next_id("P")
        pending.append(kw)
        return kw

    def add_dirty(row_id, field, value, reason, p):
        """脏值逐条登记（r3 增强③）：不静默丢弃，原值保留，同步 pending。"""
        dirty.append({"row_id": row_id, "field": field, "value": str(value)[:120],
                      "reason": str(reason)[:200], "pending_id": p["pending_id"]})

    if not rules:
        rules.extend(default_rules(rows))
    fm_rules = rules_by_kind(rules, "field_mapping")
    uc_rules = rules_by_kind(rules, "unit_convert")
    sn_rules = rules_by_kind(rules, "synonym_norm")
    mm_rules = rules_by_kind(rules, "missing_mark")
    af_rules = rules_by_kind(rules, "anomaly_flag")
    dd_rules = rules_by_kind(rules, "dedup")

    field_map, map_notes = {}, []
    for r in fm_rules:
        cond = r.get("condition", {})
        cols = cond.get("columns") or ([cond.get("column")] if cond.get("column") else [])
        tgt = (r.get("action") or {}).get("target_field")
        for c in cols:
            if not c or not tgt:
                continue
            if c in field_map:
                map_notes.append("列 %s 被 %s 与 %s 重复映射，保留先者" % (c, field_map[c][1], r.get("rule_id")))
                continue
            field_map[c] = (tgt, r.get("rule_id"), r.get("rationale", ""))

    cleaned = []
    for i, row in enumerate(rows):
        rid = row_id_of(row, i)
        out = {"row_id": rid}
        raw = {}
        for k, v in row.items():
            if str(k).startswith("__"):
                continue
            tgt, fm_rid, fm_rat = field_map.get(k) or field_map.get(str(k).lower()) or (k, None, None)
            if tgt in out and tgt != k:
                raw.setdefault("__extra__", {})[k] = v
                p = add_pending(row_id=rid, field=tgt, value=str(v)[:120], kind="field_collision",
                                issue="多列映射到同一目标字段 %s（源列 %s）" % (tgt, k),
                                suggest="人工确认保留哪一列")
                add_dirty(rid, tgt, v, "多列映射冲突，未清洗", p)
                continue
            out[tgt] = v
            raw[tgt] = {"source_column": k, "value": v}
            if fm_rid:
                raw[tgt]["field_mapping_rule"] = fm_rid
        out["__raw__"] = raw
        cleaned.append(out)

    # 单位换算（r3：每条换算带 trace 中间值留痕）
    for r in uc_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        fields = cond.get("fields") or ([cond.get("field")] if cond.get("field") else [])
        for fld in fields:
            for out in cleaned:
                val = out.get(fld)
                if val is None or isinstance(val, (dict, list)):
                    continue
                parsed, unit = parse_value_unit(val)
                if parsed is None:
                    if not is_missing(val):
                        unknown_units += 1
                        p = add_pending(row_id=out["row_id"], field=fld, value=str(val)[:120],
                                        kind="unknown_unit_or_format",
                                        issue="无法解析数值/单位：%r" % str(val)[:80],
                                        suggest="人工确认数值格式或单位后补规则")
                        add_dirty(out["row_id"], fld, val, "无法解析数值/单位，原值保留", p)
                    continue
                if cond.get("from_unit") and norm_unit(cond["from_unit"]) != unit:
                    continue
                to_u = act.get("to_unit", "")
                prec = act.get("precision")
                fac_ov = act.get("factor")
                off = act.get("offset", 0.0)
                if isinstance(parsed, tuple):
                    a, fa, f1, t1 = convert_scalar(parsed[0], unit, to_u, fac_ov, off)
                    b, fb, f2, t2 = convert_scalar(parsed[1], unit, to_u, fac_ov, off)
                    if a is None:
                        unknown_units += 1
                        p = add_pending(row_id=out["row_id"], field=fld, value=str(val)[:120],
                                        kind="unknown_unit", issue=str(b) or str(f2),
                                        suggest="人工确认单位换算关系后补规则（不猜）")
                        add_dirty(out["row_id"], fld, val, str(b) or str(f2), p)
                        continue
                    if prec is not None:
                        a, b = round(a, int(prec)), round(b, int(prec))
                    new = "%g\u2013%g" % (a, b)
                    formula = "区间双端: [%s] ; [%s]" % (f1, f2)
                    trace = {"interval": True, "ends": [t1, t2], "src_unit": unit,
                             "dst_unit": to_u, "value_out": new,
                             "recompute": "区间双端各自换算，不取中点"}
                    if prec is not None:
                        trace["precision"] = int(prec)
                else:
                    nv, fac, formula, tr = convert_scalar(parsed, unit, to_u, fac_ov, off)
                    if nv is None:
                        unknown_units += 1
                        p = add_pending(row_id=out["row_id"], field=fld, value=str(val)[:120],
                                        kind="unknown_unit", issue=formula,
                                        suggest="人工确认单位换算关系后补规则（不猜）")
                        add_dirty(out["row_id"], fld, val, formula, p)
                        continue
                    new = round(nv, int(prec)) if prec is not None else round(nv, 12)
                    tr["precision"] = int(prec) if prec is not None else 12
                    tr["value_final"] = new
                    trace = tr
                out["__raw__"].setdefault(fld, {})["value_raw"] = val
                out["__raw__"][fld]["unit_raw"] = unit
                out["__raw__"][fld]["to_unit"] = to_u
                out["__raw__"][fld]["trace"] = trace
                out[fld] = new
                out.setdefault("__units__", {})[fld] = to_u or unit
                add_change(row_id=out["row_id"], field=fld, original=str(val),
                           new=new, rule_id=r.get("rule_id"), kind="convert",
                           formula=formula, precision=prec, trace=trace)

    # r3 增强③扫尾：带单位但未被任何换算规则处理的值逐条登记（不静默跳过）
    target_units = set()
    uc_fields = set()
    for r in uc_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        flds = cond.get("fields") or ([cond.get("field")] if cond.get("field") else [])
        uc_fields |= set(flds)
        if act.get("to_unit"):
            target_units.add(norm_unit(act["to_unit"]))
    for fld in uc_fields:
        for out in cleaned:
            val = out.get(fld)
            if val is None or isinstance(val, (dict, list)) or is_missing(val):
                continue
            raw_f = (out.get("__raw__") or {}).get(fld)
            if isinstance(raw_f, dict) and "trace" in raw_f:
                continue  # 已换算，trace 留痕
            parsed, unit = parse_value_unit(val)
            if parsed is None:
                continue  # 不可解析已在上方 UC 循环登记
            if not unit or unit in target_units:
                continue  # 纯数值（无量纲）或已是目标单位：视为已规范
            unknown_units += 1
            p = add_pending(row_id=out["row_id"], field=fld, value=str(val)[:120],
                            kind="unknown_unit",
                            issue="单位 %r 未被任何换算规则处理，原值保留" % unit,
                            suggest="补 UC 规则（from_unit=%s）或人工确认单位语义" % unit)
            add_dirty(out["row_id"], fld, val,
                      "单位 %r 未被任何换算规则处理，原值保留" % unit, p)

    # 同义归一
    for r in sn_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        fld = cond.get("field")
        groups = act.get("groups") or []
        lookup, dup = {}, {}
        for g in groups:
            canon = str(g.get("canonical", "")).strip()
            for m in g.get("members", []) + [canon]:
                key = str(m).strip().lower()
                if not key:
                    continue
                if key in lookup and lookup[key] != canon:
                    dup[key] = (lookup[key], canon)
                lookup[key] = canon
        for key, pair in dup.items():
            add_pending(row_id="-", field=fld, value=key, kind="synonym_conflict",
                        issue="同义成员 %r 同时映射到 %r 与 %r，未归一" % (key, pair[0], pair[1]),
                        suggest="人工裁决归一映射后合并到一个组")
        for out in cleaned:
            if not fld:
                continue
            val = out.get(fld)
            if val is None:
                continue
            canon = lookup.get(str(val).strip().lower())
            if canon and str(val).strip() != canon:
                add_change(row_id=out["row_id"], field=fld, original=str(val), new=canon,
                           rule_id=r.get("rule_id"), kind="synonym_norm",
                           formula="同义映射: %r -> %r" % (str(val), canon), precision=None)
                out["__raw__"].setdefault(fld, {})["value_raw"] = val
                out[fld] = canon
                synonyms_normalized += 1

    # 缺失标记
    for r in mm_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        fields = cond.get("fields") or ([cond.get("field")] if cond.get("field") else [])
        tokens = set(t.strip().lower() for t in (act.get("missing_tokens") or []))
        for out in cleaned:
            for fld in fields:
                val = out.get(fld)
                hit = (val is not None and str(val).strip().lower() in (tokens or MISSING_TOKENS)) or val is None
                if not hit:
                    continue
                if val is None:
                    missing_report["fields"][fld] = missing_report["fields"].get(fld, 0) + 1
                    missing_report["cells"].append({"row_id": out["row_id"], "field": fld})
                    continue
                add_change(row_id=out["row_id"], field=fld, original=str(val), new=None,
                           rule_id=r.get("rule_id"), kind="missing_mark",
                           formula="缺失记号 %r -> 空缺（不编造）" % str(val), precision=None)
                out["__raw__"].setdefault(fld, {})["value_raw"] = val
                out[fld] = None
                missing_report["fields"][fld] = missing_report["fields"].get(fld, 0) + 1
                missing_report["cells"].append({"row_id": out["row_id"], "field": fld})

    # 异常标记（不改值）
    for r in af_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        fld = cond.get("field")
        for out in cleaned:
            val = out.get(fld) if fld else None
            parsed, _u = parse_value_unit(val) if val is not None else (None, "")
            nums = [parsed] if isinstance(parsed, float) else (list(parsed) if isinstance(parsed, tuple) else [])
            bad = []
            for n in nums:
                if cond.get("min") is not None and n < float(cond["min"]):
                    bad.append("低于 min=%s" % cond["min"])
                if cond.get("max") is not None and n > float(cond["max"]):
                    bad.append("高于 max=%s" % cond["max"])
            if cond.get("allowed") and str(val) not in [str(a) for a in cond["allowed"]]:
                bad.append("不在允许值集合")
            if bad:
                anomalies.append({"row_id": out["row_id"], "field": fld, "value": str(val)[:120],
                                  "rule_id": r.get("rule_id"), "issue": "；".join(bad)})
                add_pending(row_id=out["row_id"], field=fld, value=str(val)[:120], kind="anomaly",
                            issue="；".join(bad), suggest="人工核实（原值保留不改）")

    # 重复判定
    if not dd_rules:
        dd_rules = [x for x in default_rules(cleaned) if x.get("kind") == "dedup"]
        rules.extend(dd_rules)

    def norm_txt(v):
        return re.sub(r"\s+", " ", str(v or "").strip().lower())

    def values_compatible(a, b, tol):
        skip = {"row_id", "__raw__", "__units__", "__index__", "__parent_key__",
                "__merged_row_ids__", "__merged_into__", "__raw_text__", "__changes__"}
        keys = set(a) | set(b)
        for k in keys:
            if k in skip or str(k).startswith("__"):
                continue
            va, vb = a.get(k), b.get(k)
            if va is None and vb is None:
                continue
            pa, _ = parse_value_unit(va) if va is not None else (None, "")
            pb, _ = parse_value_unit(vb) if vb is not None else (None, "")
            if isinstance(pa, float) and isinstance(pb, float):
                if pa == 0 and pb == 0:
                    continue
                if abs(pa - pb) > tol * max(abs(pa), abs(pb), 1e-12):
                    return False, k, va, vb
            elif norm_txt(va) != norm_txt(vb):
                return False, k, va, vb
        return True, None, None, None

    for r in dd_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        key_f = cond.get("key_fields") or []
        ctx_f = cond.get("context_fields") or []
        link_f = act.get("link_field") or ""
        use_sig = (r.get("rule_id") == "AUTO-DD")  # 兜底：全字段一致（容忍稀疏列）
        tol = float(policy.get("merge_value_tolerance", 1e-6))
        groups, skipped = {}, []
        for idx, out in enumerate(cleaned):
            if out.get("__merged_into__"):
                continue
            if link_f and out.get(link_f):
                target = str(out[link_f]).strip()
                groups.setdefault(("__link__", target), []).append(idx)
                continue
            if use_sig:
                sig = tuple(sorted((k, norm_txt(v)) for k, v in out.items()
                                   if not str(k).startswith("__") and k not in ID_KEYS
                                   and v is not None and str(v) != ""))
                groups.setdefault(sig, []).append(idx)
                continue
            if key_f and any(out.get(k) in (None, "") for k in key_f):
                skipped.append(out["row_id"])
                continue
            key = tuple(norm_txt(out.get(k)) for k in key_f) + tuple(norm_txt(out.get(c)) for c in ctx_f)
            groups.setdefault(key, []).append(idx)

        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            is_link = isinstance(key, tuple) and key and key[0] == "__link__"
            primary = idxs[0]
            merged_here = []
            for j in idxs[1:]:
                ok, dk, va, vb = values_compatible(cleaned[primary], cleaned[j], tol)
                same_ctx = True
                if not is_link and ctx_f:
                    same_ctx = all(norm_txt(cleaned[primary].get(c)) == norm_txt(cleaned[j].get(c))
                                   for c in ctx_f)
                if not same_ctx:
                    suspected.append({"row_a": cleaned[primary]["row_id"], "row_b": cleaned[j]["row_id"],
                                      "key": [str(x) for x in key] if not is_link else list(key),
                                      "reason": "条件指纹不同：重复实验可能，绝不合并"})
                    p = add_pending(row_id=cleaned[j]["row_id"], field="__row__",
                                    value=cleaned[j]["row_id"], kind="suspected_duplicate",
                                    issue="与 %s 同物质同指标但条件指纹不同（重复实验 vs 重复记录待判定）"
                                          % cleaned[primary]["row_id"],
                                    suggest="人工判定后决定是否合并（默认不合并）")
                    add_dirty(cleaned[j]["row_id"], "__row__", cleaned[j]["row_id"],
                              "条件指纹不同，去重未判定，整行保留待人工判定", p)
                    continue
                if not ok:
                    conflicts.append({"what": "同判定键行值不一致（疑似科学冲突，不裁决）",
                                      "where": [cleaned[primary]["row_id"], cleaned[j]["row_id"]],
                                      "field": dk,
                                      "values": [str(va)[:120], str(vb)[:120]],
                                      "rule_id": r.get("rule_id")})
                    add_pending(row_id=cleaned[j]["row_id"], field=str(dk),
                                value=str(vb)[:120], kind="value_conflict",
                                issue="与 %s 判定键相同但 %s 不一致（%s vs %s），未合并"
                                      % (cleaned[primary]["row_id"], dk, va, vb),
                                suggest="人工裁决科学冲突（字面换算不能替代裁决）")
                    continue
                cleaned[j]["__merged_into__"] = cleaned[primary]["row_id"]
                cleaned[primary].setdefault("__merged_row_ids__", []).append(cleaned[j]["row_id"])
                merged_here.append(cleaned[j]["row_id"])
                add_change(row_id=cleaned[j]["row_id"], field="__row__",
                           original=cleaned[j]["row_id"], new=cleaned[primary]["row_id"],
                           rule_id=r.get("rule_id"), kind="merge",
                           formula="判定键=%s；值相容(容差 %g)，合并到 %s"
                                   % (str(key)[:160], tol, cleaned[primary]["row_id"]),
                           precision=None)
            if merged_here:
                merged_groups.append({"kept_row_id": cleaned[primary]["row_id"],
                                      "merged_row_ids": merged_here,
                                      "key": [str(x)[:60] for x in key][:10] if not is_link else list(key),
                                      "rule_id": r.get("rule_id")})
        if skipped:
            add_pending(row_id=",".join(skipped[:20]), field="__row__", value="-",
                        kind="dedup_skipped",
                        issue="判定键字段缺失，%d 行跳过去重" % len(skipped),
                        suggest="补齐键字段或改判定键规则后重跑")

    # r3 增强①：行级台账索引 + 被改格内嵌 ledger（__changes__ / __raw__[fld].ledger）
    row_by_id = {}
    for out in cleaned:
        row_by_id[out["row_id"]] = out
    row_changes = {}
    for c in changelog:
        row_changes.setdefault(c.get("row_id"), []).append(c["change_id"])
    for out in cleaned:
        out["__changes__"] = list(row_changes.get(out["row_id"], []))
    for c in changelog:
        row = row_by_id.get(c.get("row_id"))
        if row is None or c.get("field") == "__row__":
            continue
        row.setdefault("__raw__", {}).setdefault(c["field"], {})["ledger"] = {
            "change_id": c["change_id"], "kind": c.get("kind"),
            "original": c.get("original"), "new": c.get("new"),
            "rule_id": c.get("rule_id")}

    final_rows = [r for r in cleaned if not r.get("__merged_into__")]
    return {
        "cleaned_rows": final_rows, "changelog": changelog, "pending": pending,
        "anomalies": anomalies, "conflicts": conflicts, "merged_groups": merged_groups,
        "suspected": suspected, "missing_report": missing_report,
        "field_map": field_map, "map_notes": map_notes,
        "synonyms_normalized": synonyms_normalized, "unknown_units": unknown_units,
        "dirty": dirty,
    }


# ---------------------------------------------------------------- 产物
def build_claims(res, rows_in):
    claims = []
    n = 0

    def add(text, kind, source_id, location, quotes):
        nonlocal n
        n += 1
        claims.append({"claim_id": "CL%03d" % n, "text": text, "kind": kind,
                       "source_id": source_id, "location": location,
                       "evidence": [{"paragraph_id": str(q.get("row_id", "")),
                                     "quote": str(q.get("quote", ""))[:240]} for q in quotes[:3]]})

    for g in res["merged_groups"]:
        add("行 %s 与 %s 判定为重复记录并合并（判定键=%s，规则 %s）"
            % (g["kept_row_id"], "、".join(g["merged_row_ids"]), g["key"], g["rule_id"]),
            "inferred", g["kept_row_id"], "rows:%s" % g["kept_row_id"],
            [{"row_id": g["kept_row_id"], "quote": "kept row"}]
            + [{"row_id": x, "quote": "merged row"} for x in g["merged_row_ids"][:2]])
    by_rule = {}
    for c in res["changelog"]:
        if c.get("kind") in ("convert", "synonym_norm", "missing_mark"):
            by_rule.setdefault((c.get("rule_id"), c.get("kind"), c.get("field")), []).append(c)
    for (rid, kind, fld), items in by_rule.items():
        sample = items[0]
        trace_note = ""
        if kind == "convert" and isinstance(sample.get("trace"), dict):
            trace_note = "；trace 中间值可复算（%s）" % sample["trace"].get("recompute", "")
        add("规则 %s 对字段 %s 执行 %s 共 %d 格（样例：%s -> %s，公式与 trace 见 changelog%s）"
            % (rid, fld, kind, len(items), sample.get("original"), sample.get("new"), trace_note),
            "inferred", str(rid), "changelog:%s" % sample.get("change_id"),
            [{"row_id": c.get("row_id"), "quote": "%s: %s -> %s" % (c.get("field"), c.get("original"), c.get("new"))}
             for c in items[:3]])
    for d in res.get("dirty", [])[:10]:
        add("行 %s 字段 %s 存在无法清洗的脏值 %r，原值保留并登记待确认（%s）"
            % (d.get("row_id"), d.get("field"), d.get("value"), d.get("reason")),
            "reported", d.get("row_id"), "uncertainties.dirty_values[%s]" % d.get("pending_id"),
            [{"row_id": d.get("row_id"), "quote": str(d.get("value"))}])
    if not claims:
        add("未发生任何改动：输入已符合目标规范或规则未命中", "inferred", "run", "result.summary", [])
    return claims


def build_result(case_id, status, res, rows_in, rules, outdir, contract):
    columns = []
    for r in res["cleaned_rows"]:
        for k in r:
            if not str(k).startswith("__") and k not in columns:
                columns.append(k)
    dirty = res.get("dirty", [])
    summary = {
        "rows_in": rows_in,
        "rows_out": len(res["cleaned_rows"]),
        "changed_cells": len(res["changelog"]),
        "merged_groups": len(res["merged_groups"]),
        "missing_marked": sum(res["missing_report"]["fields"].values()),
        "unknown_units": res["unknown_units"],
        "dirty_values": len(dirty),
        "synonyms_normalized": res["synonyms_normalized"],
        "anomalies": len(res["anomalies"]),
        "conflicts": len(res["conflicts"]),
        "pending_items": len(res["pending"]),
    }
    human_review = ["[%s] %s（%s）" % (p.get("pending_id"), p.get("issue", "")[:80], p.get("row_id", ""))
                    for p in res["pending"]]
    unreported = [{"row_id": c["row_id"], "field": c["field"]} for c in res["missing_report"]["cells"][:50]]
    result = {
        "engine": VERSION,
        "cleaned_table": {"columns": columns, "rows": res["cleaned_rows"]},
        "changelog": res["changelog"],
        "pending_review": res["pending"],
        "field_mapping": {"map": [{"source_column": k, "target_field": v[0],
                                   "rule_id": v[1], "rationale": v[2]} for k, v in res["field_map"].items()],
                          "notes": res["map_notes"],
                          "unmapped_fields": [c for c in columns
                                              if c not in [v[0] for v in res["field_map"].values()]]},
        "rules_applied": [{"rule_id": r.get("rule_id"), "kind": r.get("kind"),
                           "priority": r.get("priority"), "rationale": r.get("rationale", "")}
                          for r in rules],
        "dedup_report": {"merged_groups": res["merged_groups"], "suspected_pairs": res["suspected"]},
        "missing_report": res["missing_report"],
        "anomalies": res["anomalies"],
        "conflicts": res["conflicts"],
        "summary": summary,
        "artifacts": {
            "cleaned_csv": os.path.join(outdir, "cleaned.csv"),
            "changelog_jsonl": os.path.join(outdir, "changelog.jsonl"),
            "pending_review_json": os.path.join(outdir, "pending_review.json"),
        },
        "check_standard": [
            "output_contract 键一个不缺", "case_id 与输入一致",
            "changelog 条数 == changed_cells", "换算类变更必须带 formula 与 precision",
            "换算类变更必须带 trace（net_factor 与换算前后值，可逐步复算）",
            "每行 __changes__ 条数 == 该行 changelog 条数；被改格 __raw__[fld].ledger 内嵌台账",
            "pending_review 非空 => uncertainties.human_review 非空",
            "dirty_values 逐条登记且 == summary.unknown_units",
            "rows_out == cleaned_table 行数 == cleaned.csv 数据行数", "status 如实",
        ],
    }
    doc = {"case_id": case_id, "status": status, "result": result, "claims": [],
           "uncertainties": {"unreported": unreported,
                             "unverifiable": [],
                             "conflicts": res["conflicts"],
                             "human_review": human_review,
                             "dirty_values": dirty,
                             "summary": ""}}
    if res["unknown_units"]:
        doc["uncertainties"]["unverifiable"] = [
            "无法清洗的脏值 %d 处，已逐条登记 uncertainties.dirty_values（原值保留，不静默丢弃，同步 pending_review）"
            % res["unknown_units"]]
    doc["claims"] = build_claims(res, rows_in)
    doc["uncertainties"]["summary"] = (
        "清洗完成：rows_in=%d rows_out=%d changed=%d merged=%d pending=%d dirty=%d；"
        "改动均含 row_id+rule_id+原值->新值并逐条内嵌行级台账；换算含公式、精度与 trace 中间值（可复算）；"
        "无法清洗的脏值逐条登记不静默丢弃；不同条件/来源不错并；科学冲突只登记不裁决；缺失保持空缺。" % (
            summary["rows_in"], summary["rows_out"], summary["changed_cells"],
            summary["merged_groups"], summary["pending_items"], summary["dirty_values"]))
    for k in contract:
        if k not in doc:
            doc[k] = "unknown"
    return doc


def write_outputs(outdir, doc, res):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    table = doc.get("result", {}).get("cleaned_table") or {}
    cols = table.get("columns") or []
    if cols or table.get("rows"):
        with open(os.path.join(outdir, "cleaned.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["row_id"] + cols, extrasaction="ignore")
            w.writeheader()
            for r in table.get("rows") or []:
                row = {"row_id": r.get("row_id")}
                for c in cols:
                    row[c] = r.get(c)
                w.writerow(row)
    with open(os.path.join(outdir, "changelog.jsonl"), "w", encoding="utf-8") as f:
        for c in doc.get("result", {}).get("changelog") or []:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(outdir, "pending_review.json"), "w", encoding="utf-8") as f:
        json.dump(doc.get("result", {}).get("pending_review") or [], f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 模式
def do_skeleton(args):
    case = load_json_any(args.case)
    contract = contract_fields(case)
    doc = {"case_id": get_case_id(case), "status": "partial", "result": {},
           "claims": [],
           "uncertainties": {"unreported": [], "unverifiable": [], "conflicts": [],
                             "human_review": [], "dirty_values": [],
                             "summary": "骨架已落盘，待清洗填充"}}
    for k in contract:
        if k not in doc:
            doc[k] = [] if k.endswith("s") else "unknown"
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("[skeleton] 已写 %s（键: %s）" % (os.path.join(args.outdir, "result.json"), ",".join(doc.keys())))
    return 0


def do_profile(args):
    case = load_json_any(args.case)
    rows = flatten_rows(find_rows(case) or [])
    cols = []
    for r in rows:
        for k in r:
            if not str(k).startswith("__") and k not in cols:
                cols.append(k)
    prof = {"engine": VERSION, "case_id": get_case_id(case), "n_rows": len(rows),
            "columns": cols, "contract_keys": contract_fields(case),
            "columns_detail": {}, "shape_guess": "unknown",
            "unit_tokens": [], "id_candidates": [], "suspected_dup_pairs": []}
    unit_tokens, long_votes = set(), 0
    for c in cols:
        vals = [r.get(c) for r in rows]
        nonnull = [v for v in vals if not is_missing(v)]
        samples = [str(v)[:60] for v in nonnull[:5]]
        units_here = set()
        for v in nonnull[:200]:
            _p, u = parse_value_unit(v)
            if u:
                units_here.add(u)
        unit_tokens |= units_here
        if c.lower() in ("field", "field_name", "metric", "indicator", "parameter", "指标"):
            long_votes += 1
        if c.lower() in ("value", "val", "数值", "amount", "q", "result"):
            long_votes += 1
        if c.lower() in ("unit", "units", "单位"):
            long_votes += 1
        prof["columns_detail"][c] = {"missing": len(vals) - len(nonnull), "n_distinct":
                                     len(set(str(v) for v in nonnull)),
                                     "units": sorted(units_here)[:10], "samples": samples}
        if c.lower() in ID_KEYS or "id" in c.lower():
            prof["id_candidates"].append(c)
    prof["unit_tokens"] = sorted(unit_tokens)[:40]
    prof["shape_guess"] = "long(字段名/值/单位分列)" if long_votes >= 2 else "wide(每行一条记录)"
    key_cand = [c for c in cols if c.lower() in ("substance", "adsorbate", "analyte", "物质", "compound")]
    val_cand = [c for c in cols if c.lower() in ("value", "val", "q", "capacity", "数值", "result")]
    for i in range(len(rows)):
        for j in range(i + 1, min(len(rows), i + 8)):
            a, b = rows[i], rows[j]
            if key_cand and val_cand:
                if all(norm_txt2(a.get(k)) == norm_txt2(b.get(k)) for k in key_cand):
                    if norm_txt2(a.get(val_cand[0])) == norm_txt2(b.get(val_cand[0])):
                        prof["suspected_dup_pairs"].append([row_id_of(a, i), row_id_of(b, j)])
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=1)
    print("[profile] rows=%d cols=%d shape=%s units=%s" %
          (prof["n_rows"], len(cols), prof["shape_guess"], prof["unit_tokens"][:12]))
    print("[profile] 列: %s" % ",".join(cols))
    return 0


def norm_txt2(v):
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def do_run(args):
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    case_id, status, res, rows_in, rules = "unknown", "partial", None, 0, []
    try:
        case = load_json_any(args.case)
        case_id = get_case_id(case)
        contract = contract_fields(case)
        rows = flatten_rows(find_rows(case) or [])
        rows_in = len(rows)
        rules, note = load_rules(args.rules)
        policy = {}
        if args.rules and os.path.exists(args.rules):
            try:
                policy = load_json_any(args.rules).get("conflict_policy", {}) or {}
            except Exception:  # noqa: BLE001
                policy = {}
        if rows_in == 0:
            status = "insufficient_evidence"
            res = {"cleaned_rows": [], "changelog": [], "pending": [{
                "pending_id": "P0001", "kind": "empty_input", "row_id": "-", "field": "-",
                "value": "-", "issue": "case.json 未发现行数据（%s）" % note,
                "suggest": "确认输入结构；必要时人工提供数据"}],
                "anomalies": [], "conflicts": [], "merged_groups": [], "suspected": [],
                "missing_report": {"fields": {}, "cells": []}, "field_map": {}, "map_notes": [],
                "synonyms_normalized": 0, "unknown_units": 0, "dirty": []}
            rules = rules or default_rules([])
        else:
            res = apply_clean(rows, rules, policy)
            # 待确认清单本身是交付物；只有处理中断/缺行才算 partial
            status = "answered"
        doc = build_result(case_id, status, res, rows_in, rules, outdir, contract)
        write_outputs(outdir, doc, res)
        print("[run] status=%s rows_in=%d rows_out=%d changed=%d merged=%d pending=%d dirty=%d -> %s"
              % (doc["status"], rows_in, doc["result"]["summary"]["rows_out"],
                 doc["result"]["summary"]["changed_cells"], doc["result"]["summary"]["merged_groups"],
                 doc["result"]["summary"]["pending_items"], doc["result"]["summary"]["dirty_values"],
                 outdir))
        return 0
    except Exception as e:  # noqa: BLE001
        err = "%s: %s" % (type(e).__name__, e)
        print("[run] FATAL: %s" % err, file=sys.stderr)
        traceback.print_exc()
        try:
            doc = {"case_id": case_id, "status": "input_error" if res is None else "partial",
                   "result": {"error": err, "partial": res is not None,
                              "rows_in": rows_in, "engine": VERSION},
                   "claims": [],
                   "uncertainties": {"unreported": [], "unverifiable": [],
                                     "conflicts": [], "dirty_values": [],
                                     "human_review": ["运行中断于: %s" % err],
                                     "summary": "运行中断，已按协议交付部分结果：%s" % err}}
            write_outputs(outdir, doc, {"cleaned_rows": [], "changelog": [], "pending": []})
            print("[run] 已按失败交付协议写 result.json（status=%s）" % doc["status"])
        except Exception as e2:  # noqa: BLE001
            print("[run] 连失败交付也失败: %s" % e2, file=sys.stderr)
        return 1


def do_check(args):
    problems = []
    if not os.path.exists(args.result):
        print("[check] FAIL: result.json 不存在")
        return 1
    try:
        doc = load_json_any(args.result)
    except Exception as e:  # noqa: BLE001
        print("[check] FAIL: result.json 不可解析: %s" % e)
        return 1
    if not isinstance(doc, dict):
        print("[check] FAIL: 顶层不是对象")
        return 1
    contract = list(DEFAULT_CONTRACT)
    case = None
    if args.case and os.path.exists(args.case):
        try:
            case = load_json_any(args.case)
            contract = contract_fields(case)
        except Exception as e:  # noqa: BLE001
            problems.append("case.json 读取失败（按默认契约校验）: %s" % e)
    for k in contract:
        if k not in doc:
            problems.append("缺少 output_contract 字段: %s" % k)
    if not doc.get("case_id"):
        problems.append("缺少 case_id")
    elif case and get_case_id(case) not in ("unknown", str(doc.get("case_id"))):
        problems.append("case_id 与输入不一致: %r vs %r" % (doc.get("case_id"), get_case_id(case)))
    if doc.get("status") not in STATUS_VALUES:
        problems.append("status 非法: %r" % doc.get("status"))
    inner = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    rows = (inner.get("cleaned_table") or {}).get("rows") if isinstance(inner.get("cleaned_table"), dict) else None
    changes = inner.get("changelog") if isinstance(inner.get("changelog"), list) else []
    summary = inner.get("summary") or {}
    if rows is not None and summary:
        if summary.get("changed_cells") != len(changes):
            problems.append("changed_cells=%s 与 changelog 条数=%d 不一致"
                            % (summary.get("changed_cells"), len(changes)))
        if summary.get("rows_out") != len(rows):
            problems.append("rows_out=%s 与 cleaned_table 行数=%d 不一致"
                            % (summary.get("rows_out"), len(rows)))
        if summary.get("dirty_values") != summary.get("unknown_units"):
            problems.append("dirty_values=%s 与 unknown_units=%s 不一致（脏值必须逐条登记）"
                            % (summary.get("dirty_values"), summary.get("unknown_units")))
    cnt_by_row = {}
    for c in changes:
        cnt_by_row[c.get("row_id")] = cnt_by_row.get(c.get("row_id"), 0) + 1
    for i, c in enumerate(changes):
        if not isinstance(c, dict):
            problems.append("changelog[%d] 不是对象" % i)
            continue
        for fld in ("change_id", "row_id", "field", "original", "new", "rule_id", "kind"):
            if fld not in c:
                problems.append("changelog[%d] 缺 %s" % (i, fld))
        if c.get("kind") == "convert" and ("formula" not in c or "precision" not in c):
            problems.append("changelog[%d] 换算缺 formula/precision" % i)
        if c.get("kind") == "convert":
            tr = c.get("trace")
            if not isinstance(tr, dict) or ("value_out" not in tr and "ends" not in tr):
                problems.append("changelog[%d] 换算缺 trace 中间值留痕（可复算）" % i)
    if rows is not None:
        for r in rows:
            rid = r.get("row_id")
            expect = cnt_by_row.get(rid, 0)
            got = len(r.get("__changes__") or [])
            if expect != got:
                problems.append("行 %s __changes__=%d 与该行 changelog 条数=%d 不一致" % (rid, got, expect))
            for fld, info in (r.get("__raw__") or {}).items():
                if isinstance(info, dict) and "ledger" in info:
                    cid = info["ledger"].get("change_id")
                    if cid not in r.get("__changes__", []):
                        problems.append("行 %s 字段 %s ledger(%s) 不在该行 __changes__" % (rid, fld, cid))
    unc = doc.get("uncertainties") if isinstance(doc.get("uncertainties"), dict) else {}
    for k in ("unreported", "unverifiable", "conflicts", "human_review", "dirty_values", "summary"):
        if k not in unc:
            problems.append("uncertainties 缺 %s" % k)
    pending = inner.get("pending_review") if isinstance(inner.get("pending_review"), list) else []
    if pending and not unc.get("human_review"):
        problems.append("pending_review 有 %d 项但 uncertainties.human_review 为空" % len(pending))
    dirty = unc.get("dirty_values") if isinstance(unc.get("dirty_values"), list) else []
    dirty_pids = {d.get("pending_id") for d in dirty if isinstance(d, dict)}
    for p in pending:
        if p.get("kind") in ("unknown_unit", "unknown_unit_or_format") and p.get("pending_id") not in dirty_pids:
            problems.append("pending %s 为脏值但未逐条登记 uncertainties.dirty_values" % p.get("pending_id"))
    claims = doc.get("claims") if isinstance(doc.get("claims"), list) else []
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            problems.append("claims[%d] 不是对象" % i)
            continue
        for fld in ("claim_id", "text", "kind", "source_id", "location", "evidence"):
            if fld not in c:
                problems.append("claims[%d] 缺 %s" % (i, fld))
        if isinstance(c.get("kind"), str) and c["kind"] not in ("reported", "inferred"):
            problems.append("claims[%d].kind 非法: %r" % (i, c.get("kind")))
    if problems:
        print("[check] FAIL（%d 处）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 1
    print("[check] PASS（rows_out=%s changed=%s pending=%s dirty=%s claims=%s）"
          % (summary.get("rows_out"), len(changes), len(pending), len(dirty), len(claims)))
    return 0


# ---------------------------------------------------------------- 入口
def parse_args(argv):
    ap = argparse.ArgumentParser(prog="clean_run.py", description="clean2table-r3 清洗引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("skeleton")
    p.add_argument("--case", required=True)
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("profile")
    p.add_argument("--case", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("run")
    p.add_argument("--case", required=True)
    p.add_argument("--rules", default=None)
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("check")
    p.add_argument("--result", required=True)
    p.add_argument("--case", default=None)
    return ap.parse_args(argv)


def main(argv=None):
    try:
        args = parse_args(argv if argv is not None else sys.argv[1:])
        if args.cmd == "skeleton":
            return do_skeleton(args)
        if args.cmd == "profile":
            return do_profile(args)
        if args.cmd == "run":
            return do_run(args)
        if args.cmd == "check":
            return do_check(args)
        print("[clean_run] 未知模式", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print("[clean_run] FATAL: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
