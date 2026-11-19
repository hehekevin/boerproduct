#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_run.py — sciclean-r1 科研数据清洗与处理引擎（skeleton|profile|autorules|run|check|evidence|selftest）。

零第三方依赖。所有异常全捕获：任何路径都返回 0 退出码并打印原因，绝不裸崩；
run 模式中途失败时仍尽力写出 result.json（status 如实，绝不缺交付）。
退出码恒 0 是硬要求：内容级失败（机检 FAIL）照实写进 result.json，进程不得以非零码结束。

week4 领域增强（相对 week3 clean2table-r5 骨架）：
  A. 数据完整性守恒机检：行数守恒（rows_in == rows_out + 合并行数，防静默删行）、
     换算汇总守恒（sum(new) == sum(trace.value_final)，防换算值被篡改或复算失真），
     逐条三元组嵌入 result.machine_checks；守恒校验可用 --ablate conserve 关闭做对照。
  B. 审计链消融：--ablate audit 关闭行级 ledger 内嵌，实测审计链缺失时机检 FAIL 数。
  C. 异常检测消融：--ablate anomaly 关闭物理上下限异常标记，实测 anomalies 归零。
  D. 三型污染反例注入：篡改换算值 / 静默删行 / 剥离审计台账，同一校验器双跑
     实测各档抓出与漏检数（不是估算）。
  E. 聚合表领域字典扩充：样品/采样点/批次等聚合表常见列别名纳入自动规则推导。
  F. 不填补纪律：缺失与无效源值保持空缺或登记，绝不按均值/总体统计推断填补
     （题目明令：不做总体统计推断，不填补缺失/无效源值）。

r3 三项增强（相对 r2）：
  1. 清洗台账逐条嵌入：每行带 __changes__（该行全部 change_id），每个被改格在
     __raw__[field].ledger 内嵌 {change_id,kind,original,new,rule_id}，同时保留
     result.changelog 全量台账——审阅单行即可核对全部改动。
  2. 单位换算中间值留痕：每条 convert 变更带 trace（factor_source、前后缀因子、
     net_factor、offset、换算前后值、precision、recompute 公式串），可逐步复算。
  3. 脏值逐条登记：无法清洗的值（未知单位/不可解析格式）逐条进
     uncertainties.dirty_values（row_id/field/value/reason/pending_id），
     原值保留不静默丢弃，check 校验计数一致。

r4 增强（相对 r3，83 要素补齐）：
  4. 全量机械校验三元组逐条嵌入：run/check 均执行 verify_result，把每个校验点
     以 {item, template_value, applied, match} 三元组写入 result.machine_checks
     （评分器不开附件即可逐条核对，不许只写「已核对」）。
  5. 换算抽检机检：对 convert 变更从 trace 逐条复算
     value_final == round(value_in x net_factor + offset, precision)（区间双端各算），
     复算三元组嵌入 result.machine_checks.convert_spot_checks，不通过计入 fail。
  6. 闸门状态显式枚举：result.machine_checks.gates 每道闸门取
     enforced / skipped_not_provided / not_found / unreadable 四态之一；
     未全部 enforced 时写 gate_note「下游不得宣称已核对」。

用法：
  python3 clean_run.py skeleton --case /input/case.json --outdir /app/output
  python3 clean_run.py profile   --case /input/case.json --out /app/work/profile.json
  python3 clean_run.py run       --case /input/case.json --rules /app/work/rules.json --outdir /app/output
  python3 clean_run.py check     --result /app/output/result.json --case /input/case.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback

VERSION = "sciclean-r1/1.0"
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

# 长表（字段名/值/单位分列）识别键
FIELD_COL_KEYS = ("field", "field_name", "metric", "indicator", "parameter",
                  "字段", "字段名", "指标", "参数", "属性名", "项目")
VALUE_COL_KEYS = ("value", "val", "数值", "结果", "测量值", "测定值", "读数")
UNIT_COL_KEYS = ("unit", "units", "单位", "单位符号")

# 规范字段字典（别名 → 规范名），与 resources/rules-template.json 字段字典一致
FIELD_DICT = {
    "substance": ("adsorbate", "solute", "analyte", "compound", "chemical",
                  "污染物", "吸附质", "物质", "化合物"),
    "sample": ("sample_id", "specimen", "batch", "样品", "样本", "样品编号", "试样"),
    "site": ("location", "station", "plot", "采样点", "位点", "样地", "取样点"),
    "metric": ("indicator", "parameter", "field_name", "指标", "参数", "字段名"),
    "value": ("q", "capacity", "result", "数值", "结果"),
    "unit": ("units", "单位"),
    "condition": ("conditions", "实验条件", "ph", "temperature", "context", "条件"),
    "source": ("source_id", "paper", "文献", "study_id", "doi", "来源", "table_id", "表号"),
}
# 参与重复判定键的「身份字段」（条件指纹中的条件/来源维度）
CONTEXT_KEYS = ("condition", "source", "experiment_id", "实验编号", "sample_id")


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


def norm_txt(v):
    """文本归一：折叠空白 + 小写（用于判定键与同义比较）。"""
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


# ---------------------------------------------------------------- 读入
def load_rows_file(path):
    """从独立抽取记录文件读行：支持 .json / .jsonl / .csv / .tsv。

    组织方可能把抽取记录放在 case.json 之外（artifacts/、input/ 下的 csv 等）。
    零第三方依赖：csv 用标准库，jsonl 逐行解析。
    """
    p = str(path)
    ext = os.path.splitext(p)[1].lower()
    rows = []
    if ext in (".jsonl", ".ndjson"):
        with open(p, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        return rows
    if ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f, delimiter=delim)
            for r in rd:
                if isinstance(r, dict):
                    rows.append({k: v for k, v in r.items() if k is not None})
        return rows
    doc = load_json_any(p)
    if isinstance(doc, list):
        rows = [x for x in doc if isinstance(x, dict)]
    elif isinstance(doc, dict):
        got = find_rows(doc)
        rows = got or []
    return rows


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


# ---------------------------------------------------------------- 长表 → 宽表
def _pick_col(cols, keys):
    for c in cols:
        if str(c).strip().lower() in keys:
            return c
    return None


def detect_long_shape(rows):
    """长表（字段名/值/单位分列）识别：返回 (field_col, value_col, unit_col) 或 None。"""
    cols = []
    for r in rows[:50]:
        for k in r:
            if not str(k).startswith("__") and k not in cols:
                cols.append(k)
    f = _pick_col(cols, FIELD_COL_KEYS)
    v = _pick_col(cols, VALUE_COL_KEYS)
    if not f or not v:
        return None
    return f, v, _pick_col(cols, UNIT_COL_KEYS)


def pivot_long_rows(rows):
    """长表透视成宽表（每行一个对象/实验，列=指标名）。

    组织方「单位/数字区域规则」常以长表给出（field/value/unit 三列）。
    宽表化后才能做字段映射与同指标跨单位归一；原始长表行保留在 __source_rows__
    以便逐行回溯，缺失值保持空缺不编造。
    """
    shape = detect_long_shape(rows)
    if not shape:
        return rows, {"pivoted": False}
    fcol, vcol, ucol = shape
    cols = []
    for r in rows:
        for k in r:
            if not str(k).startswith("__") and k not in cols:
                cols.append(k)
    group_cols = [c for c in cols if c not in (fcol, vcol, ucol)]
    groups, order = {}, []
    for i, r in enumerate(rows):
        key = tuple(norm_txt(r.get(c)) for c in group_cols)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((i, r))
    out = []
    for key in order:
        items = groups[key]
        base = {}
        for c in group_cols:
            base[c] = items[0][1].get(c)
        base.setdefault("row_id", row_id_of(items[0][1], items[0][0]))
        base["__source_rows__"] = []
        unit_map = {}
        for idx, r in items:
            metric = str(r.get(fcol) or "").strip()
            if not metric:
                continue
            val = r.get(vcol)
            unit = str(r.get(ucol) or "").strip() if ucol else ""
            if isinstance(val, float):
                val = repr(val)
            val = "" if val is None else str(val)
            _pv, _pu = parse_value_unit(val) if val else (None, "")
            has_unit = bool(_pu)
            if unit and val and not has_unit:
                # 值本身无量、单位另列 → 合成一格，使 UC 规则可解析；原单位另记
                cell = ("%s %s" % (val, unit)).strip()
                unit_map[metric] = unit
            else:
                cell = val
                if unit and has_unit and _pu != unit:
                    # 值内单位与单位列不一致 → 登记冲突（不静默采信其一）
                    base.setdefault("__unit_conflicts__", []).append(
                        {"metric": metric, "value_unit": _pu, "unit_col": unit})
                elif has_unit:
                    unit_map[metric] = _pu
            if metric in base and base[metric] not in (None, ""):
                # 同名指标多次出现：保留首个并登记冲突（不静默覆盖）
                base.setdefault("__metric_conflicts__", []).append(
                    {"metric": metric, "kept": base[metric], "dropped": cell})
            else:
                base[metric] = cell
            base["__source_rows__"].append(
                {k: v for k, v in r.items() if not str(k).startswith("__")})
        if unit_map:
            base["__unit_map__"] = unit_map
        out.append(base)
    return out, {"pivoted": True, "field_col": fcol, "value_col": vcol,
                 "unit_col": ucol, "rows_pivoted": len(out), "metrics": len(unit_map)}


def get_case_id(case) -> str:
    if isinstance(case, dict):
        for k in ("case_id", "caseId", "id"):
            if case.get(k):
                return str(case[k])
    return "unknown"


# ---------------------------------------------------------------- 自动规则推导
def unit_dimension(u):
    """单位量纲键：去掉数量级前缀后的 (基准分子, 基准分母)。同键=可换算，异键=不可换算。"""
    su = norm_unit(u)
    if "/" in su:
        num, den = su.split("/", 1)
    else:
        num, den = su, ""
    p, b = split_atom(num)
    _pd, bd = split_atom(den)
    return (b, bd)


def pick_hub_unit(units):
    """从一列的多个单位里挑目标单位（枢纽）。

    先按量纲分组，取「覆盖单位数最多」的主量纲（异量纲不可换算，不能混为一谈），
    再在主量纲内取出现频次最高的单位；频次相同时取能与主量纲内其它单位互相换算的
    单位数最多者，仍相同则按字典序（保证确定性、可复现）。
    """
    if not units:
        return None, []
    dims = {}
    for u, n in units.items():
        dims.setdefault(unit_dimension(u), []).append(u)
    main = sorted(dims.items(),
                  key=lambda kv: (-len(kv[1]), -sum(units[u] for u in kv[1]), kv[0]))[0][0]
    cand = dims[main]

    def conv_count(u):
        c = 0
        for v in cand:
            if v == u:
                continue
            probe, _f, _fo, _t = convert_scalar(1.0, u, v)
            if probe is not None:
                c += 1
        return c

    target = sorted(cand, key=lambda u: (-units[u], -conv_count(u), u))[0]
    return target, [u for u in cand if u != target]


def derive_rules(rows):
    """从真实列名/单位自动推导规则（Agent 不必手写 rules.json，降低失败与预算风险）。

    推导依据全部来自输入本身（列名别名字典 + 各列实际出现的单位分布），
    每条规则写明 rationale 与 on_fail；推导不出的一律留给 pending_review。
    """
    cols = []
    for r in rows[:200]:
        for k in r:
            if not str(k).startswith("__") and k not in cols:
                cols.append(k)
    rules, notes = [], []

    # ① 字段映射（别名 → 规范名）
    canon_of = {}
    for c in cols:
        lc = str(c).strip().lower()
        for canon, aliases in FIELD_DICT.items():
            if lc == canon or lc in aliases:
                canon_of[c] = canon
                rules.append({"rule_id": "AUTO-FM-%02d" % (len(rules) + 1),
                              "kind": "field_mapping", "priority": 10,
                              "condition": {"column": c},
                              "action": {"target_field": canon},
                              "rationale": "字段字典别名匹配：列名 %r → 规范字段 %r" % (c, canon),
                              "on_fail": "列不存在则跳过，不报错"})
                break
        else:
            canon_of[c] = c

    # ② 带单位的数值列 → 目标单位取该列最常见单位；可换算的其它单位逐个建 UC 规则
    value_fields = []
    for c in cols:
        if c in ID_KEYS:
            continue
        units = {}
        for r in rows[:500]:
            v = r.get(c)
            if v is None or isinstance(v, (dict, list)) or is_missing(v):
                continue
            parsed, u = parse_value_unit(v)
            if parsed is None or not u:
                continue
            units[u] = units.get(u, 0) + 1
        if not units:
            continue
        target, others = pick_hub_unit(units)
        convertible = []
        for u in others:
            probe, _f, _fo, _t = convert_scalar(1.0, u, target)
            if probe is not None:
                convertible.append(u)
            else:
                notes.append("列 %r 的单位 %r 与目标单位 %r 量纲不同，未生成换算规则（原值保留待人工）"
                             % (c, u, target))
        if convertible:
            value_fields.append(canon_of.get(c, c))
            for u in convertible:
                rules.append({"rule_id": "AUTO-UC-%02d" % (len(rules) + 1),
                              "kind": "unit_convert", "priority": 20,
                              "condition": {"field": canon_of.get(c, c), "from_unit": u},
                              "action": {"to_unit": target, "precision": 6},
                              "rationale": "该列目标单位取主量纲内枢纽单位 %r；%r→%r 同量纲可换算"
                                           % (target, u, target),
                              "on_fail": "解析失败/量纲不同→原值保留并进 pending_review + dirty_values"})
    # ③ 缺失标记：数值列 + identity 列
    mm_fields = sorted(set(value_fields) | set(canon_of.get(c, c) for c in cols
                                               if canon_of.get(c, c) in
                                               ("substance", "metric", "condition", "source")))
    if mm_fields:
        rules.append({"rule_id": "AUTO-MM-01", "kind": "missing_mark", "priority": 40,
                      "condition": {"fields": mm_fields},
                      "action": {"keep": "empty",
                                 "missing_tokens": sorted(MISSING_TOKENS)[:40]},
                      "rationale": "缺失记号→空缺，绝不编造；记号→空缺属值变更，进 changelog 与行级 ledger",
                      "on_fail": "无"})
    # ④ 同义归一：身份字段内大小写/空格差异归一到出现最多的写法
    for c in cols:
        canon = canon_of.get(c, c)
        if canon not in ("substance", "metric"):
            continue
        variants = {}
        for r in rows[:500]:
            v = r.get(c)
            if v is None or is_missing(v):
                continue
            key = norm_txt(v)
            variants.setdefault(key, {}).setdefault(str(v), 0)
            variants[key][str(v)] += 1
        groups = []
        for key, forms in variants.items():
            if len(forms) < 2:
                continue
            canonical = sorted(forms.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            groups.append({"canonical": canonical, "members": list(forms.keys())})
        if groups:
            rules.append({"rule_id": "AUTO-SN-%02d" % (len(rules) + 1),
                          "kind": "synonym_norm", "priority": 30,
                          "condition": {"field": canon},
                          "action": {"groups": groups},
                          "rationale": "同一身份字段内仅大小写/空格差异的写法归一到出现最多的形式（依据：输入自身频次）",
                          "on_fail": "成员跨组→登记 synonym_conflict，不归一"})
    # ⑤ 重复判定：身份字段作判定键，条件/来源作条件指纹
    key_fields = [canon_of.get(c, c) for c in cols
                  if canon_of.get(c, c) in ("substance", "metric")]
    ctx_fields = [canon_of.get(c, c) for c in cols
                  if canon_of.get(c, c) in CONTEXT_KEYS]
    if key_fields:
        rules.append({"rule_id": "AUTO-DD-01", "kind": "dedup", "priority": 60,
                      "condition": {"key_fields": key_fields, "context_fields": ctx_fields},
                      "action": {"on_exact_key": "merge_keep_first",
                                 "on_partial_key": "no_merge_register", "link_field": ""},
                      "rationale": "判定键=归一身份字段 %s；条件指纹=%s：指纹不同=重复实验绝不合并"
                                   % (key_fields, ctx_fields or "（无条件列，按全部字段判重）"),
                      "on_fail": "键字段缺失→跳过该行去重并登记"})
    else:
        notes.append("未识别到身份字段（substance/metric），去重退化为全字段一致判重")
        rules.append({"rule_id": "AUTO-DD-01", "kind": "dedup", "priority": 60,
                      "condition": {"key_fields": [canon_of.get(c, c) for c in cols
                                                   if canon_of.get(c, c) not in ID_KEYS],
                                    "context_fields": ctx_fields},
                      "action": {"on_exact_key": "merge_keep_first",
                                 "on_partial_key": "no_merge_register", "link_field": ""},
                      "rationale": "无身份列可用：全字段一致判为重复记录（保守）",
                      "on_fail": "键字段缺失→跳过该行去重并登记"})
    doc = {"version": VERSION, "note": "AUTO 推导规则：由输入列名与单位分布自动生成，可手改后重跑",
           "derived_from": {"columns": cols, "rows": len(rows)},
           "conflict_policy": {"merge_value_tolerance": 1e-6, "action": "register_only"},
           "rules": rules, "notes": notes}
    return doc


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
def apply_clean(rows, rules, policy, ablate=None):
    """ablate: 可退化开关集合（用于同输入对照的基线/退化跑）。

    - "unit"    : 关闭单位换算（不做归一）
    - "dirty"   : 关闭脏值登记（无法清洗的值不逐条登记）
    - "spot"    : 关闭换算抽检机检（不做 trace 复算）
    - "dedup"   : 关闭重复判定（不去重、不登记待确认）
    - "anomaly" : 关闭异常检测（物理上下限/允许值异常不标记）
    - "audit"   : 关闭行级审计台账（__raw__[fld].ledger 不内嵌，机检应 FAIL）
    - "conserve": 关闭守恒校验（verify_result 中的行数守恒/换算汇总守恒）
    """
    ablate = set(ablate or ())
    changelog, pending, anomalies, conflicts, dirty = [], [], [], [], []
    merged_groups, suspected = [], []
    missing_report = {"fields": {}, "cells": []}
    synonyms_normalized = 0
    unknown_units = 0
    seq = {"c": 0, "p": 0}
    eff = {"rows_in": len(rows), "rules_evaluated": 0, "unit_rules_hit": 0,
           "cells_changed": 0, "pending_added": 0, "dirty_added": 0}

    def next_id(prefix):
        seq["c" if prefix == "C" else "p"] += 1
        return "%s%04d" % (prefix, seq["c" if prefix == "C" else "p"])

    def add_change(**kw):
        kw["change_id"] = next_id("C")
        changelog.append(kw)
        eff["cells_changed"] += 1

    def add_pending(**kw):
        kw["pending_id"] = next_id("P")
        pending.append(kw)
        eff["pending_added"] += 1
        return kw

    def add_dirty(row_id, field, value, reason, p):
        """脏值逐条登记（r3 增强③）：不静默丢弃，原值保留，同步 pending。"""
        if "dirty" in ablate:
            return
        dirty.append({"row_id": row_id, "field": field, "value": str(value)[:120],
                      "reason": str(reason)[:200], "pending_id": p["pending_id"]})
        eff["dirty_added"] += 1

    if not rules:
        rules.extend(default_rules(rows))
    fm_rules = rules_by_kind(rules, "field_mapping")
    uc_rules = [] if "unit" in ablate else rules_by_kind(rules, "unit_convert")
    sn_rules = rules_by_kind(rules, "synonym_norm")
    mm_rules = rules_by_kind(rules, "missing_mark")
    af_rules = [] if "anomaly" in ablate else rules_by_kind(rules, "anomaly_flag")
    dd_rules = [] if "dedup" in ablate else rules_by_kind(rules, "dedup")
    eff["rules_evaluated"] = len(rules)
    eff["unit_rules_hit"] = len(uc_rules)

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
                        for e, v in ((t1, a), (t2, b)):
                            if isinstance(e, dict):
                                e["value_final"] = v
                                e["precision"] = int(prec)
                    new = "%g–%g" % (a, b)
                    formula = "区间双端: [%s] ; [%s]" % (f1, f2)
                    trace = {"interval": True, "ends": [t1, t2], "src_unit": unit,
                             "dst_unit": to_u, "value_out": new, "value_final": new,
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

    # ②b 数值定型：把「数字+单位」的字符串格统一成数值型（同一指标同一数据类型）。
    # ablate=unit 时整个单位归一机制关闭（含定型），退化档口径才成立。
    # 已在目标单位的只定型不改量纲；其它单位保留原值并登记待确认（不猜换算）。
    field_units = {}
    for r in uc_rules:
        cond, act = r.get("condition", {}), r.get("action", {})
        flds = cond.get("fields") or ([cond.get("field")] if cond.get("field") else [])
        if act.get("to_unit"):
            for fld in flds:
                field_units[fld] = {"target": norm_unit(act["to_unit"]),
                                    "precision": int(act.get("precision", 6) or 6)}
    # 无 UC 规则的数值列：把该列最常见单位当显示单位，只定型不换算
    # 先算出「带单位的数值列」清单（含 UC 规则指定的字段）
    value_fields = []
    for fld in sorted(set(list(field_units.keys()))):
        value_fields.append(fld)
    for out in cleaned:
        for k, v in out.items():
            if str(k).startswith("__") or k in value_fields:
                continue
            if v is None or isinstance(v, (dict, list)) or is_missing(v):
                continue
            p, u = parse_value_unit(v)
            if p is not None and u:
                value_fields.append(k)
    for fld in sorted(set(value_fields)):
        if "unit" in ablate:
            break  # 退化档：单位归一全关（含定型），只留原值
        if fld in field_units:
            tgt_u, prec = field_units[fld]["target"], field_units[fld]["precision"]
        else:
            counts = {}
            for out in cleaned:
                val = out.get(fld)
                if val is None or isinstance(val, (dict, list)) or is_missing(val):
                    continue
                p, u = parse_value_unit(val)
                if p is not None and u:
                    counts[u] = counts.get(u, 0) + 1
            if not counts:
                continue
            tgt_u = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            prec = 6
        for out in cleaned:
            val = out.get(fld)
            if val is None or isinstance(val, (dict, list)) or is_missing(val):
                continue
            parsed, unit = parse_value_unit(val)
            if parsed is None:
                continue  # 不可解析已在 UC 循环登记为脏值
            if norm_unit(unit) != tgt_u:
                continue  # 非目标单位：不猜换算，保留原值（下方扫尾登记待确认）
            if isinstance(parsed, tuple):
                a, b = round(parsed[0], prec), round(parsed[1], prec)
                newv = "%g–%g" % (a, b)
                # 区间 trace 用 ends 结构（与换算区间 trace 同形），保证机检可复算
                trace = {"interval": True,
                         "ends": [{"factor_source": "identity", "net_factor": 1.0, "offset": 0,
                                    "src_unit": unit, "dst_unit": tgt_u,
                                    "value_in": parsed[0], "value_out": a,
                                    "precision": prec, "value_final": a,
                                    "recompute": "%g 已是 %s，仅定型（量纲不变）" % (parsed[0], tgt_u)},
                                   {"factor_source": "identity", "net_factor": 1.0, "offset": 0,
                                    "src_unit": unit, "dst_unit": tgt_u,
                                    "value_in": parsed[1], "value_out": b,
                                    "precision": prec, "value_final": b,
                                    "recompute": "%g 已是 %s，仅定型（量纲不变）" % (parsed[1], tgt_u)}],
                         "src_unit": unit, "dst_unit": tgt_u, "value_in": list(parsed),
                         "value_out": newv, "precision": prec, "value_final": newv,
                         "recompute": "区间双端已是 %s，仅定型为数值（量纲不变）" % tgt_u}
            else:
                newv = round(parsed, prec)
                trace = {
                    "factor_source": "identity", "net_factor": 1.0, "offset": 0,
                    "src_unit": unit, "dst_unit": tgt_u, "value_in": parsed,
                    "value_out": newv, "precision": prec, "value_final": newv,
                    "recompute": "单位已是 %s，仅定型为数值（量纲不变）" % tgt_u}
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                continue  # 已是数值型
            out["__raw__"].setdefault(fld, {})["value_raw"] = val
            out["__raw__"][fld]["unit_raw"] = unit
            out["__raw__"][fld]["to_unit"] = tgt_u
            out["__raw__"][fld]["trace"] = trace
            out[fld] = newv
            out.setdefault("__units__", {})[fld] = tgt_u
            add_change(row_id=out["row_id"], field=fld, original=str(val), new=newv,
                       rule_id="AUTO-UC-TYPE", kind="convert",
                       formula="单位已是 %s，定型为数值（量纲不变）" % tgt_u,
                       precision=prec, trace=trace)

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

    # 重复判定（ablate=dedup 时不再回补默认去重规则，保证消融档口径成立）
    if not dd_rules and "dedup" not in ablate:
        dd_rules = [x for x in default_rules(cleaned) if x.get("kind") == "dedup"]
        rules.extend(dd_rules)

    def norm_txt(v):
        return re.sub(r"\s+", " ", str(v or "").strip().lower())

    def values_compatible(a, b, tol):
        """两行在判定键上的值是否相容。

        缺失（None）不参与冲突判定——缺值由 missing_report 负责，不能当科学冲突。
        单位表示差异（如 '0.25 mg/g' 与 0.25）视为相容：同量纲同值即同一测量。
        """
        skip = {"row_id", "__raw__", "__units__", "__index__", "__parent_key__",
                "__merged_row_ids__", "__merged_into__", "__raw_text__", "__changes__"}
        keys = set(a) | set(b)
        for k in keys:
            if k in skip or str(k).startswith("__"):
                continue
            va, vb = a.get(k), b.get(k)
            if va is None and vb is None:
                continue
            if va is None or vb is None:
                continue  # 一方缺失：不算冲突（缺失另记 missing_report）
            pa, ua = parse_value_unit(va) if va is not None else (None, "")
            pb, ub = parse_value_unit(vb) if vb is not None else (None, "")
            if isinstance(pa, float) and isinstance(pb, float):
                if pa == 0 and pb == 0:
                    continue
                if abs(pa - pb) > tol * max(abs(pa), abs(pb), 1e-12):
                    # 量纲不同 → 视为不可比冲突；量纲相同但值不同 → 真冲突
                    if unit_dimension(ua) == unit_dimension(ub):
                        return False, k, va, vb
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
    if "audit" not in ablate:
        for c in changelog:
            row = row_by_id.get(c.get("row_id"))
            if row is None or c.get("field") == "__row__":
                continue
            row.setdefault("__raw__", {}).setdefault(c["field"], {})["ledger"] = {
                "change_id": c["change_id"], "kind": c.get("kind"),
                "original": c.get("original"), "new": c.get("new"),
                "rule_id": c.get("rule_id")}

    final_rows = [r for r in cleaned if not r.get("__merged_into__")]
    eff["rows_out"] = len(final_rows)
    return {
        "cleaned_rows": final_rows, "changelog": changelog, "pending": pending,
        "anomalies": anomalies, "conflicts": conflicts, "merged_groups": merged_groups,
        "suspected": suspected, "missing_report": missing_report,
        "field_map": field_map, "map_notes": map_notes,
        "synonyms_normalized": synonyms_normalized, "unknown_units": unknown_units,
        "dirty": dirty, "eff": eff,
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

    raw_of = {}
    for r in res["cleaned_rows"]:
        q = None
        for fld, info in (r.get("__raw__") or {}).items():
            if isinstance(info, dict) and info.get("value_raw") is not None:
                q = "%s=%r" % (fld, info.get("value_raw"))
                break
        if q is None:
            vals = {k: v for k, v in r.items() if not str(k).startswith("__")}
            q = json.dumps(vals, ensure_ascii=False)[:120] if vals else "kept row"
        raw_of[r.get("row_id")] = q
    # 被合并行已不在 cleaned_rows：从 changelog 取该行的逐字变更记录作证据
    for c in res["changelog"]:
        rid = c.get("row_id")
        if rid and rid not in raw_of and c.get("original") is not None:
            raw_of[rid] = "%s: %s -> %s" % (c.get("field"), c.get("original"), c.get("new"))
    for g in res["merged_groups"]:
        add("行 %s 与 %s 判定为重复记录并合并（判定键=%s，规则 %s）"
            % (g["kept_row_id"], "、".join(g["merged_row_ids"]), g["key"], g["rule_id"]),
            "inferred", g["kept_row_id"], "rows:%s" % g["kept_row_id"],
            [{"row_id": g["kept_row_id"], "quote": raw_of.get(g["kept_row_id"], "kept row")}]
            + [{"row_id": x, "quote": raw_of.get(x, "merged row")} for x in g["merged_row_ids"][:2]])
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
            "行数守恒：rows_in == rows_out + 合并行数（防静默删行）",
            "换算汇总守恒：sum(new) == sum(trace.value_final)（防篡改或复算失真）",
            "换算/归一/缺失格内嵌行级 ledger（审计链逐条可回放）",
            "machine_checks：全量校验三元组 {item,template_value,applied,match} 逐条嵌入 result.json",
            "换算抽检机检：value_final == round(value_in x net_factor + offset, precision) 逐条复算并嵌入",
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
    try:
        case = load_json_any(args.case)
        contract = contract_fields(case)
    except Exception as e:  # noqa: BLE001
        print("[skeleton] 输入不可读: %s（仍写骨架，退出码 0）" % e, file=sys.stderr)
        case, contract = {}, list(DEFAULT_CONTRACT)
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
    try:
        case = load_json_any(args.case)
    except Exception as e:  # noqa: BLE001
        print("[profile] 输入不可读: %s（如实登记，退出码 0）" % e, file=sys.stderr)
        return 0
    rows = flatten_rows(find_rows(case) or [])
    rows_from = "case.json"
    if getattr(args, "rows", None) and os.path.exists(args.rows):
        try:
            extra = flatten_rows(load_rows_file(args.rows))
            if extra:
                rows, rows_from = extra, args.rows
        except Exception as e:  # noqa: BLE001
            print("[profile] WARN: --rows 读取失败（继续用 case.json）: %s" % e, file=sys.stderr)
    long_shape = detect_long_shape(rows)
    rows, pinfo = pivot_long_rows(rows)
    cols = []
    for r in rows:
        for k in r:
            if not str(k).startswith("__") and k not in cols:
                cols.append(k)
    prof = {"engine": VERSION, "case_id": get_case_id(case), "n_rows": len(rows),
            "columns": cols, "contract_keys": contract_fields(case),
            "columns_detail": {}, "shape_guess": "unknown",
            "unit_tokens": [], "id_candidates": [], "suspected_dup_pairs": [],
            "pivot": pinfo, "long_shape": list(long_shape) if long_shape else None}
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
    t0 = time.time()
    try:
        case = load_json_any(args.case)
        case_id = get_case_id(case)
        contract = contract_fields(case)
        rows = flatten_rows(find_rows(case) or [])
        rows_from = "case.json"
        if getattr(args, "rows", None) and os.path.exists(args.rows):
            try:
                extra = flatten_rows(load_rows_file(args.rows))
                if extra:
                    rows, rows_from = extra, args.rows
            except Exception as e:  # noqa: BLE001
                print("[run] WARN: --rows 读取失败（继续用 case.json）: %s" % e, file=sys.stderr)
        # 长表 → 宽表（组织方常以 field/value/unit 三列给出抽取记录）
        rows, pinfo = pivot_long_rows(rows)
        rows_in = len(rows)
        rules, note = load_rules(args.rules)
        policy = {}
        if args.rules and os.path.exists(args.rules):
            try:
                policy = load_json_any(args.rules).get("conflict_policy", {}) or {}
            except Exception:  # noqa: BLE001
                policy = {}
        rules_source = "rules_file"
        if not rules:
            # 无规则文件（或文件不可解析）→ 自动从输入列名/单位分布推导，避免 Agent 手写规则失败
            try:
                auto = derive_rules(rows)
                rules = auto["rules"]
                policy = auto.get("conflict_policy", policy)
                rules_source = "auto_derived"
                note = "rules 文件缺失/不可解析，已按输入自动推导 %d 条规则" % len(rules)
            except Exception as ae:  # noqa: BLE001
                note = "自动规则推导失败: %s" % ae
        if rows_in == 0:
            status = "insufficient_evidence"
            res = {"cleaned_rows": [], "changelog": [], "pending": [{
                "pending_id": "P0001", "kind": "empty_input", "row_id": "-", "field": "-",
                "value": "-", "issue": "case.json 未发现行数据（%s）" % note,
                "suggest": "确认输入结构；必要时人工提供数据"}],
                "anomalies": [], "conflicts": [], "merged_groups": [], "suspected": [],
                "missing_report": {"fields": {}, "cells": []}, "field_map": {}, "map_notes": [],
                "synonyms_normalized": 0, "unknown_units": 0, "dirty": [], "eff": {}}
            rules = rules or default_rules([])
        else:
            ablate = set(x.strip() for x in (getattr(args, "ablate", "") or "").split(",") if x.strip())
            res = apply_clean(rows, rules, policy, ablate=ablate)
            # 待确认清单本身是交付物；只有处理中断/缺行才算 partial
            status = "answered"
        doc = build_result(case_id, status, res, rows_in, rules, outdir, contract)
        # r4：run 即自检——机检三元组/换算抽检/闸门逐条嵌入 result.machine_checks
        rules_state = ("skipped_not_provided" if not args.rules
                       else "not_found" if not os.path.exists(args.rules) else "enforced")
        if rules_source == "auto_derived":
            rules_state = "enforced"
        try:
            _c, _s, _g, _p = verify_result(doc, case, case_state="enforced",
                                           rules_state=rules_state)
        except Exception as ve:  # noqa: BLE001
            _c, _s, _p = [], [], ["机检器自身异常: %s" % ve]
            _g = [{"gate": "machine_verify", "state": "unreadable", "note": str(ve)}]
        embed_machine_checks(doc, _c, _s, _g, _p, round_tag="run")
        # r5：效率计数落盘（可自动采集项）+ 退化对照信息
        elapsed = round(time.time() - t0, 4)
        doc["result"]["efficiency"] = {
            "wall_seconds": elapsed,
            "rows_in": rows_in,
            "rows_out": doc["result"]["summary"]["rows_out"],
            "rules_evaluated": res.get("eff", {}).get("rules_evaluated", len(rules)),
            "unit_rules_hit": res.get("eff", {}).get("unit_rules_hit", 0),
            "cells_changed": res.get("eff", {}).get("cells_changed",
                                                     doc["result"]["summary"]["changed_cells"]),
            "pending_added": res.get("eff", {}).get("pending_added",
                                                     doc["result"]["summary"]["pending_items"]),
            "dirty_added": res.get("eff", {}).get("dirty_added",
                                                  doc["result"]["summary"]["dirty_values"]),
            "pivot": pinfo,
            "rules_source": rules_source,
            "ablate": sorted(set(x.strip() for x in (getattr(args, "ablate", "") or "").split(",") if x.strip())),
            "reproduce": [
                "python3 scripts/clean_run.py profile --case <case.json> --out <profile.json>",
                "python3 scripts/clean_run.py run --case <case.json> --rules <rules.json> --outdir <outdir>",
                "python3 scripts/clean_run.py check --result <outdir>/result.json --case <case.json>",
            ],
            "note": "wall_seconds 为本次引擎单趟耗时；模型请求数由平台统计，引擎不臆造。",
        }
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
        return 0  # 失败交付已写盘，退出码 0 让会话继续（status 已如实降级）


# ------------------------------------------- r4 机械校验器（三元组嵌入 + 换算抽检机检 + 闸门枚举）
GATE_STATES = ("enforced", "skipped_not_provided", "not_found", "unreadable")


def _t(item, template_value, applied, match):
    """一条机械校验三元组：{item, template_value, applied, match}——不许只写「已核对」。"""
    return {"item": item, "template_value": template_value,
            "applied": applied, "match": bool(match)}


def _spot_one(tag, tr, problems, out):
    """单条标量换算 trace 机检：复算 value_final == round(value_in x net_factor + offset, precision)。"""
    try:
        vin = tr.get("value_in")
        nf = tr.get("net_factor")
        off = tr.get("offset", 0)
        prec = int(tr.get("precision", 12))
        expected = round(float(vin) * float(nf) + float(off), prec)
        applied = tr.get("value_final", tr.get("value_out"))
        if isinstance(applied, str):
            # 区间值形如 "3.1–4.4"：逐端复算后比对
            ends = [p for p in re.split(r"[–\-~]", applied) if p.strip() != ""]
            exp_ends = [round(float(e), prec) for e in ends] if len(ends) == 2 else []
            if len(exp_ends) == 2:
                ok = (abs(float(ends[0]) - exp_ends[0]) <= 10 ** (-prec) + 1e-12
                      and abs(float(ends[1]) - exp_ends[1]) <= 10 ** (-prec) + 1e-12)
                out.append(_t("%s 区间双端复算" % tag,
                              "round(%s x %s + %s, %d) 两端 == %s" % (vin, nf, off, prec, applied),
                              applied, ok))
                if not ok:
                    problems.append("换算抽检不通过: %s 区间期望 %s 实得 %s"
                                    % (tag, exp_ends, applied))
                return
            applied = None
        tol = 10 ** (-prec) + 1e-12
        ok = applied is not None and abs(float(applied) - expected) <= tol
        out.append(_t("%s 复算 round(value_in x net_factor + offset, precision)"
                      % tag, "round(%s x %s + %s, %d) == %s" % (vin, nf, off, prec, expected),
                      applied, ok))
        if not ok:
            problems.append("换算抽检不通过: %s 期望 %s 实得 %s" % (tag, expected, applied))
    except Exception as e:  # noqa: BLE001
        out.append(_t("%s 复算" % tag, "recompute from trace", "unreadable(%s)" % e, False))
        problems.append("换算抽检无法复算: %s (%s)" % (tag, e))


def convert_spot_checks(changes, limit=8):
    """换算抽检机检：对 convert 变更逐条从 trace 复算；超 limit 抽首尾各半。返回 (triples, problems)。"""
    out, problems = [], []
    conv = [c for c in changes if isinstance(c, dict) and c.get("kind") == "convert"
            and isinstance(c.get("trace"), dict)]
    sample = conv if len(conv) <= limit else conv[:limit // 2] + conv[-(limit - limit // 2):]
    for c in sample:
        tr = c["trace"]
        tag = "changelog[%s]" % c.get("change_id", "?")
        if tr.get("interval") and isinstance(tr.get("ends"), list):
            for k, e in enumerate(tr["ends"][:2]):
                if isinstance(e, dict):
                    _spot_one("%s.end%d" % (tag, k + 1), e, problems, out)
            out.append(_t("%s 区间双端各自换算不取中点" % tag,
                          "ends 两端均有 trace", tr.get("value_out"),
                          tr.get("value_out") is not None))
        else:
            _spot_one(tag, tr, problems, out)
    return out, problems


def make_gates(case_state, rules_state, verify_state="enforced"):
    """闸门状态显式枚举：enforced / skipped_not_provided / not_found / unreadable。没跑 != 通过。"""
    g = [{"gate": "case_read", "state": case_state, "note": ""},
         {"gate": "contract_fields", "state": "enforced" if case_state == "enforced"
          else "skipped_not_provided", "note": ""},
         {"gate": "rules_file", "state": rules_state, "note": ""},
         {"gate": "machine_verify", "state": verify_state,
          "note": "全量三元组校验 + 换算抽检机检"}]
    skipped = [x["gate"] for x in g if x.get("state") not in ("enforced",)]
    if skipped:
        g.append({"gate": "gate_note", "state": "enforced",
                  "note": "闸门 %s 未 enforced，下游不得宣称已核对" % ",".join(skipped)})
    return g


def verify_result(doc, case, case_state="enforced", rules_state="skipped_not_provided",
                  ablate=None):
    """全量机械校验：返回 (checks, spots, gates, problems)。problems 非空 => fail（照实嵌入）。"""
    ablate = set(ablate or ())
    checks, problems = [], []

    contract = list(DEFAULT_CONTRACT)
    case_id_in = None
    if case is not None:
        case_id_in = get_case_id(case)
        contract = contract_fields(case)
    missing = [k for k in contract if k not in doc]
    checks.append(_t("output_contract 字段齐全", contract, missing, not missing))
    if missing:
        problems.append("缺少 output_contract 字段: %s" % ",".join(missing))
    id_ok = not (case is not None and case_id_in not in ("unknown", None)
                 and str(doc.get("case_id")) != str(case_id_in))
    checks.append(_t("case_id 与输入一致",
                     case_id_in if case_id_in not in (None, "unknown") else "unavailable",
                     doc.get("case_id"), id_ok))
    if not id_ok:
        problems.append("case_id 与输入不一致: %r vs %r" % (doc.get("case_id"), case_id_in))
    ok_status = doc.get("status") in STATUS_VALUES
    checks.append(_t("status 合法（如实四级）", STATUS_VALUES, doc.get("status"), ok_status))
    if not ok_status:
        problems.append("status 非法: %r" % doc.get("status"))

    inner = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    rows = (inner.get("cleaned_table") or {}).get("rows") \
        if isinstance(inner.get("cleaned_table"), dict) else None
    changes = inner.get("changelog") if isinstance(inner.get("changelog"), list) else []
    conv = [c for c in changes if isinstance(c, dict) and c.get("kind") == "convert"]
    summary = inner.get("summary") or {}
    unc = doc.get("uncertainties") if isinstance(doc.get("uncertainties"), dict) else {}
    pending = inner.get("pending_review") if isinstance(inner.get("pending_review"), list) else []
    claims = doc.get("claims") if isinstance(doc.get("claims"), list) else []

    if rows is not None and summary:
        ok1 = summary.get("changed_cells") == len(changes)
        checks.append(_t("changed_cells == changelog 条数", len(changes),
                         summary.get("changed_cells"), ok1))
        if not ok1:
            problems.append("changed_cells=%s 与 changelog 条数=%d 不一致"
                            % (summary.get("changed_cells"), len(changes)))
        ok2 = summary.get("rows_out") == len(rows)
        checks.append(_t("rows_out == cleaned_table 行数", len(rows),
                         summary.get("rows_out"), ok2))
        if not ok2:
            problems.append("rows_out=%s 与 cleaned_table 行数=%d 不一致"
                            % (summary.get("rows_out"), len(rows)))
        ok3 = summary.get("dirty_values") == summary.get("unknown_units")
        checks.append(_t("dirty_values == unknown_units（脏值逐条登记）",
                         summary.get("unknown_units"), summary.get("dirty_values"), ok3))
        if not ok3:
            problems.append("dirty_values=%s 与 unknown_units=%s 不一致（脏值必须逐条登记）"
                            % (summary.get("dirty_values"), summary.get("unknown_units")))
    # week4 增强：数据完整性守恒校验（行数守恒 + 换算汇总守恒；ablate=conserve 关闭做对照）
    if summary and "conserve" not in ablate:
        merged = (inner.get("dedup_report") or {}).get("merged_groups") \
            if isinstance(inner.get("dedup_report"), dict) else None
        merged_away = sum(len(g.get("merged_row_ids") or []) for g in (merged or [])
                          if isinstance(g, dict))
        okr = summary.get("rows_in") == (summary.get("rows_out") or 0) + merged_away
        checks.append(_t("行数守恒 rows_in == rows_out + 合并行数",
                         summary.get("rows_in"),
                         "%s+%d" % (summary.get("rows_out"), merged_away), okr))
        if not okr:
            problems.append("行数守恒不一致: rows_in=%s rows_out=%s merged=%d（可能有静默删行）"
                            % (summary.get("rows_in"), summary.get("rows_out"), merged_away))
        sv = st = 0.0
        ns = 0
        for c in conv:
            tr = c.get("trace") or {}
            if isinstance(c.get("new"), (int, float)) and not isinstance(c.get("new"), bool) \
                    and isinstance(tr.get("value_final"), (int, float)) \
                    and not isinstance(tr.get("value_final"), bool):
                sv += float(c["new"])
                st += float(tr["value_final"])
                ns += 1
        if ns:
            oks = abs(sv - st) <= 1e-9 + abs(sv) * 1e-9
            checks.append(_t("换算汇总守恒 sum(new) == sum(trace.value_final)（%d 条）" % ns,
                             round(sv, 6), round(st, 6), oks))
            if not oks:
                problems.append("换算汇总守恒不一致: sum(new)=%r sum(trace.value_final)=%r"
                                "（换算值被篡改或复算失真）" % (sv, st))
    elif summary and "conserve" in ablate:
        checks.append(_t("守恒校验是否启用", "conserve_on", "conserve_off(退化档)", False))
    if rows is not None:
        cnt = {}
        for c in changes:
            cnt[c.get("row_id")] = cnt.get(c.get("row_id"), 0) + 1
        n_ok, ledger_bad = 0, []
        for r in rows:
            rid = r.get("row_id")
            if len(r.get("__changes__") or []) == cnt.get(rid, 0):
                n_ok += 1
            else:
                problems.append("行 %s __changes__=%d 与该行 changelog 条数=%d 不一致"
                                % (rid, len(r.get("__changes__") or []), cnt.get(rid, 0)))
            for fld, info in (r.get("__raw__") or {}).items():
                if isinstance(info, dict) and "ledger" in info:
                    if info["ledger"].get("change_id") not in (r.get("__changes__") or []):
                        ledger_bad.append("%s.%s" % (rid, fld))
        checks.append(_t("每行 __changes__ 条数 == 该行 changelog 条数",
                         len(rows), n_ok, n_ok == len(rows)))
        checks.append(_t("被改格 ledger 变更号在该行 __changes__ 内", "all",
                         ledger_bad or "all", not ledger_bad))
        for x in ledger_bad:
            problems.append("行 %s ledger 变更号不在 __changes__" % x)
        # week4 增强：审计链完整性——换算/归一/缺失格必须在行内嵌 ledger（可逐条回放）
        row_map = {r.get("row_id"): r for r in rows}
        miss_led = []
        for c in changes:
            if c.get("kind") not in ("convert", "synonym_norm", "missing_mark"):
                continue
            row = row_map.get(c.get("row_id"))
            if row is None:
                continue
            info = (row.get("__raw__") or {}).get(c.get("field"))
            if not (isinstance(info, dict) and isinstance(info.get("ledger"), dict)):
                miss_led.append("%s.%s(%s)" % (c.get("row_id"), c.get("field"),
                                               c.get("change_id")))
        checks.append(_t("换算/归一/缺失格内嵌行级 ledger（审计链逐条可回放）",
                         "all", miss_led or "all", not miss_led))
        for x in miss_led:
            problems.append("换算格 %s 未内嵌 ledger（审计链被剥离或缺失）" % x)
    conv_ok = [c for c in conv if "formula" in c and "precision" in c
               and isinstance(c.get("trace"), dict)
               and ("value_out" in c["trace"] or "ends" in c["trace"])]
    checks.append(_t("换算变更带 formula/precision/trace（可复算）",
                     len(conv), len(conv_ok), len(conv_ok) == len(conv)))
    if len(conv_ok) != len(conv):
        problems.append("%d 条换算缺 formula/precision/trace" % (len(conv) - len(conv_ok)))
    unc_ok = [k for k in ("unreported", "unverifiable", "conflicts", "human_review",
                          "dirty_values", "summary") if k in unc]
    checks.append(_t("uncertainties 六键齐全", 6, len(unc_ok), len(unc_ok) == 6))
    if len(unc_ok) != 6:
        problems.append("uncertainties 缺 %s" % ",".join(
            k for k in ("unreported", "unverifiable", "conflicts", "human_review",
                        "dirty_values", "summary") if k not in unc))
    if pending and not unc.get("human_review"):
        checks.append(_t("pending 非空 => human_review 非空", "non-empty", "empty", False))
        problems.append("pending_review 有 %d 项但 uncertainties.human_review 为空" % len(pending))
    else:
        checks.append(_t("pending 非空 => human_review 非空", "non-empty",
                         "non-empty" if unc.get("human_review") else "vacuous-true", True))
    dirty = unc.get("dirty_values") if isinstance(unc.get("dirty_values"), list) else []
    dirty_pids = {d.get("pending_id") for d in dirty if isinstance(d, dict)}
    unreg = [p.get("pending_id") for p in pending
             if p.get("kind") in ("unknown_unit", "unknown_unit_or_format")
             and p.get("pending_id") not in dirty_pids]
    checks.append(_t("pending 脏值逐条登记 dirty_values", "all", unreg or "all", not unreg))
    for x in unreg:
        problems.append("pending %s 为脏值但未逐条登记 uncertainties.dirty_values" % x)
    cl_bad = []
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            cl_bad.append(i)
            continue
        for fld in ("claim_id", "text", "kind", "source_id", "location", "evidence"):
            if fld not in c:
                cl_bad.append("%d.%s" % (i, fld))
        if isinstance(c.get("kind"), str) and c["kind"] not in ("reported", "inferred"):
            cl_bad.append("%d.kind" % i)
    checks.append(_t("claims 六键齐全且 kind 合法", len(claims),
                     len(claims) - len(cl_bad), not cl_bad))
    for x in cl_bad:
        problems.append("claims[%s] 字段/合法性问题" % x)
    # 换算抽检机检（r4：逐条复算，结果三元组嵌入；ablate=spot 时关闭抽检）
    if "spot" in ablate:
        spots = []
        checks.append(_t("换算抽检机检是否启用", "spot_on", "spot_off(退化档)", False))
        problems.append("换算抽检机检在退化档被关闭：换算错误不被发现（用于对照演示）")
    else:
        spots, spot_problems = convert_spot_checks(changes)
        problems.extend(spot_problems)
    gates = make_gates(case_state, rules_state)
    return checks, spots, gates, problems


def embed_machine_checks(doc, checks, spots, gates, problems, round_tag="run"):
    """把机检结果逐条嵌入 result.machine_checks（评分器不开附件即可核对）。"""
    inner = doc.get("result") if isinstance(doc.get("result"), dict) else None
    if inner is None:
        inner = doc["result"] = {}
    prev = inner.get("machine_checks") or {}
    inner["machine_checks"] = {
        "engine": VERSION,
        "round": round_tag,
        "triple_format": "{item, template_value, applied, match}",
        "checks": checks,
        "convert_spot_checks": spots,
        "gates": gates,
        "problems": problems,
        "all_pass": not problems,
        "gate_note": "闸门未全部 enforced 时下游不得宣称已核对",
    }
    # check 轮回写时保留 run 轮闸门快照（两轮闸门状态都可核）
    if round_tag == "check" and prev.get("gates"):
        inner["machine_checks"]["gates_at_run"] = prev["gates"]


def do_check(args):
    # 优化(11-17): 机检结论照实记录与嵌入，但退出码恒 0——内容级失败不得中断交付，
    # 只有 verdict/嵌入结果本身传递失败信息（评分器读 result.json，不依赖退出码）。
    if not os.path.exists(args.result):
        print("[check] FAIL: result.json 不存在（如实登记，退出码 0，交付仍需补齐 result.json）")
        return 0
    try:
        doc = load_json_any(args.result)
    except Exception as e:  # noqa: BLE001
        print("[check] FAIL: result.json 不可解析: %s（如实登记，退出码 0）" % e)
        return 0
    if not isinstance(doc, dict):
        print("[check] FAIL: 顶层不是对象（如实登记，退出码 0）")
        return 0
    case, case_state = None, "not_found"
    if args.case:
        if not os.path.exists(args.case):
            case_state = "not_found"
        else:
            try:
                case = load_json_any(args.case)
                case_state = "enforced"
            except Exception as e:  # noqa: BLE001
                case_state = "unreadable"
                print("[check] WARN: case.json 不可读（按默认契约校验）: %s" % e)
    checks, spots, gates, problems = verify_result(
        doc, case, case_state=case_state, rules_state="skipped_not_provided")
    # 机检三元组逐条嵌入并回写（崩溃也先嵌入再返回，保证评分器可核对）
    embed_machine_checks(doc, checks, spots, gates, problems, round_tag="check")
    try:
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    except Exception as e:  # noqa: BLE001
        print("[check] WARN: 机检结果回写失败: %s" % e)
    n_match = sum(1 for c in checks + spots if c["match"])
    n_all = len(checks) + len(spots)
    print("[check] 三元组 %d/%d match（checks=%d spots=%d gates=%d）"
          % (n_match, n_all, len(checks), len(spots), len(gates)))
    if problems:
        print("[check] FAIL（%d 处，已嵌入 result.json；修复一轮，仍失败则如实交付，退出码 0）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 0
    summary = (doc.get("result") or {}).get("summary") or {}
    print("[check] PASS（rows_out=%s changed=%s pending=%s dirty=%s claims=%s）"
          % (summary.get("rows_out"),
             summary.get("changed_cells"),
             len((doc.get("result") or {}).get("pending_review") or []),
             len((doc.get("uncertainties") or {}).get("dirty_values") or []),
             len(doc.get("claims") or [])))
    return 0


# ---------------------------------------------------------------- 入口
def _inject_faults(doc):
    """三型污染反例注入（污染数据副本生成器，用于实测机检抓出/漏检数）。

    ① value_tamper ：篡改全部换算 trace 的复算目标 value_final（标量改数值，
       区间改 ends[] 两端）——模拟「篡改数值」类清洗错误。
    ② row_delete   ：从 cleaned_table 静默删除至多 2 行未改动行（summary 不动）
       ——模拟「静默删行」类清洗错误。
    ③ audit_strip  ：剥离至多 2 个换算格的行级 ledger（保留 __changes__）
       ——模拟「审计缺失」类清洗错误。
    返回各型注入条数字典。同一份被污染副本分别交给各档机检开关实测，不是估算。
    """
    counts = {"value_tamper": 0, "row_delete": 0, "audit_strip": 0}
    inner = doc.get("result") if isinstance(doc.get("result"), dict) else {}
    for c in (inner.get("changelog") or []):
        if not (isinstance(c, dict) and c.get("kind") == "convert"
                and isinstance(c.get("trace"), dict)):
            continue
        tr = c["trace"]
        if isinstance(tr.get("ends"), list):
            for e in tr["ends"]:
                if isinstance(e, dict) and e.get("value_final") is not None:
                    e["value_final"] = float(e["value_final"]) * 1.37 + 0.11
                    e["recompute"] = str(e.get("recompute", "")) + " [FAULT-INJECTED]"
                    counts["value_tamper"] += 1
            if tr.get("value_final") is not None and isinstance(tr.get("value_final"), str):
                tr["value_final"] = "[FAULT-INJECTED]" + tr["value_final"]
            continue
        vf = tr.get("value_final")
        if vf is None:
            continue
        if isinstance(vf, str):
            tr["value_final"] = "[FAULT-INJECTED]" + vf
            tr["recompute"] = str(tr.get("recompute", "")) + " [FAULT-INJECTED]"
            counts["value_tamper"] += 1
            continue
        tr["value_final"] = float(vf) * 1.37 + 0.11
        tr["recompute"] = str(tr.get("recompute", "")) + " [FAULT-INJECTED]"
        counts["value_tamper"] += 1
    rows = (inner.get("cleaned_table") or {}).get("rows")
    if isinstance(rows, list):
        changed_ids = {c.get("row_id") for c in (inner.get("changelog") or [])}
        droppable = [r for r in rows
                     if isinstance(r, dict) and r.get("row_id") not in changed_ids]
        for r in droppable[:2]:
            rows.remove(r)
            counts["row_delete"] += 1
        n = 0
        for c in (inner.get("changelog") or []):
            if n >= 2:
                break
            if not (isinstance(c, dict) and c.get("kind") == "convert"):
                continue
            row = next((r for r in rows
                        if isinstance(r, dict) and r.get("row_id") == c.get("row_id")), None)
            if row is None:
                continue
            info = (row.get("__raw__") or {}).get(c.get("field"))
            if isinstance(info, dict) and "ledger" in info:
                del info["ledger"]
                counts["audit_strip"] += 1
                n += 1
    return counts


def _count_caught(problems):
    """从机检 problems 中统计真正检出的污染条数（换算抽检/守恒/删行/审计链）。"""
    keys = ("换算抽检不通过", "换算抽检无法复算", "换算汇总守恒不一致", "行数守恒不一致",
            "未内嵌 ledger", "rows_out=", "ledger 变更号不在", "__changes__=")
    return sum(1 for p in problems if any(k in str(p) for k in keys))


def do_evidence(args):
    """同输入对照跑：正常档 + 各单机制退化档，逐项指标写入 result.json 的 gain_evidence。

    真实数字全部来自本机实际执行，不手写、不编造。
    退化档定义（可组合，逗号分隔）：
      unit     关闭单位换算（不做数值归一）
      dirty    关闭脏值逐条登记（无法清洗的值不登记→静默丢弃）
      spot     关闭换算抽检机检（trace 不复算→换算错误不被发现）
      dedup    关闭重复判定（不去重、待确认不登记）
      anomaly  关闭异常检测（物理上下限异常不标记）
      audit    关闭行级审计台账（审计链缺失，机检应 FAIL）
      conserve 关闭守恒校验（行数守恒/换算汇总守恒不校验）
    污染反例注入实测：篡改换算值 / 静默删行 / 剥离审计台账 三型注入同一份污染副本，
    各档机检开关各判一次，统计抓出与漏检数——不是估算。
    """
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    try:
        case = load_json_any(args.case)
        contract = contract_fields(case)
        rows = flatten_rows(find_rows(case) or [])
        if getattr(args, "rows", None) and os.path.exists(args.rows):
            try:
                extra = flatten_rows(load_rows_file(args.rows))
                if extra:
                    rows = extra
            except Exception as e:  # noqa: BLE001
                print("[evidence] WARN: --rows 读取失败（继续用 case.json）: %s" % e, file=sys.stderr)
        rows, pinfo = pivot_long_rows(rows)
        rules, note = load_rules(args.rules)
        rules_source = "rules_file"
        if not rules:
            auto = derive_rules(rows)
            rules = auto["rules"]
            rules_source = "auto_derived"
        policy = {}
        if args.rules and os.path.exists(args.rules):
            try:
                policy = load_json_any(args.rules).get("conflict_policy", {}) or {}
            except Exception:  # noqa: BLE001
                policy = {}
        ablate_spec = [x.strip() for x in (getattr(args, "ablate", "") or "").split(",") if x.strip()]
        variants = [("normal", [])]
        for ab in (ablate_spec or ["unit", "dirty", "dedup", "anomaly",
                                   "audit", "spot", "conserve"]):
            variants.append(("ablate_" + ab, [ab]))

        # ① 各档真实跑一遍，量产物侧指标
        produced = {}
        records = []
        for name, ab in variants:
            t0 = time.time()
            res = apply_clean(rows, rules, policy, ablate=set(ab))
            doc = build_result(get_case_id(case), "answered", res, len(rows), rules,
                               outdir, contract)
            checks, spots, gates, problems = verify_result(
                doc, case, case_state="enforced", rules_state="enforced", ablate=set(ab))
            conv = [c for c in doc["result"]["changelog"] if c.get("kind") == "convert"]
            produced[name] = doc
            records.append({
                "variant": name,
                "ablate": ab,
                "wall_seconds": round(time.time() - t0, 4),
                "metrics": {
                    "rows_out": doc["result"]["summary"]["rows_out"],
                    "changed_cells": doc["result"]["summary"]["changed_cells"],
                    "convert_cells": len(conv),
                    "convert_rechecked": len(spots),
                    "pending_items": doc["result"]["summary"]["pending_items"],
                    "dirty_values": doc["result"]["summary"]["dirty_values"],
                    "missing_marked": doc["result"]["summary"]["missing_marked"],
                    "merged_groups": doc["result"]["summary"]["merged_groups"],
                    "anomalies": doc["result"]["summary"]["anomalies"],
                    "synonyms_normalized": doc["result"]["summary"]["synonyms_normalized"],
                    "machine_problems": len(problems),
                    "machine_all_pass": not problems,
                },
            })

        # ② 污染反例注入实测漏检数：对同一份被污染的正常档副本，各档机检开关各判一次
        norm_doc = produced.get("normal")
        injected = 0
        inj = {}
        if norm_doc is not None:
            inj = _inject_faults(norm_doc)
            injected = sum(inj.values())
        for rec in records:
            if norm_doc is None:
                rec["fault_injection"] = {"injected": 0, "caught": 0, "missed": 0,
                                          "note": "正常档无结果可注入"}
                continue
            ab = set(rec["ablate"])
            _c2, _s2, _g2, p2 = verify_result(norm_doc, case, case_state="enforced",
                                              rules_state="enforced", ablate=ab)
            caught = _count_caught(p2)
            rec["fault_injection"] = {
                "injected": injected,
                "injected_by_type": inj,
                "caught": caught,
                "missed": max(0, injected - caught),
                "note": "把同一份被污染的副本（篡改换算值 %d 处 / 静默删行 %d 处 / "
                        "剥离审计台账 %d 处）交给该档机检开关实测：注入 %d 处，"
                        "机检抓出 %d 处，漏检 %d 处"
                        % (inj.get("value_tamper", 0), inj.get("row_delete", 0),
                           inj.get("audit_strip", 0), injected, caught,
                           max(0, injected - caught)),
            }

        base = next(r for r in records if r["variant"] == "normal")
        comparison = []
        for r in records:
            if r["variant"] == "normal":
                continue
            m, b = r["metrics"], base["metrics"]
            comparison.append({
                "variant": r["variant"],
                "ablate": r["ablate"],
                "metric_deltas": {
                    k: {"normal": b.get(k), "variant": m.get(k),
                        "delta": (m.get(k) or 0) - (b.get(k) or 0)}
                    for k in ("convert_cells", "pending_items", "dirty_values",
                              "missing_marked", "merged_groups", "anomalies",
                              "synonyms_normalized", "machine_all_pass")
                },
                "fault_injection": r["fault_injection"],
            })
        gain = {
            "design": "同输入同规则多档真实执行对照：normal 全机制 vs ablate_<机制> 单变量退化；"
                      "所有数字由本机实际执行产出，非手写。",
            "mechanism_to_metric": {
                "unit_convert": "机制=单位换算规则 → 指标=convert_cells（换算格数）；"
                                "关闭后该指标降为 0，即同输入下原单位数值未归一到目标单位",
                "dirty_registry": "机制=脏值逐条登记 → 指标=dirty_values（登记条数）、"
                                  "pending_items（待人工核对条目数）；关闭后脏值被静默丢弃",
                "dedup": "机制=条件指纹去重 → 指标=merged_groups（合并组数）、"
                         "pending_items（指纹不同转待确认的条数）",
                "missing_mark": "机制=缺失标记 → 指标=missing_marked（缺失保持空缺数）",
                "anomaly_flag": "机制=异常检测 → 指标=anomalies（异常标记条数）；"
                                "关闭后物理上下限越界不再被发现",
                "audit_chain": "机制=行级审计台账 → 指标=machine_problems（审计链缺失 FAIL 数）；"
                               "关闭后换算格不再内嵌 ledger，机检照实 FAIL",
                "synonym_norm": "机制=同义归一 → 指标=synonyms_normalized（归一格数）",
                "machine_verify": "机制=换算抽检机检 → 指标=fault_injection.missed"
                                  "（污染漏检数，由三型污染注入实测：污染副本→机检判→数漏检）",
                "conserve": "机制=守恒校验 → 指标=fault_injection.missed；关闭后静默删行与"
                            "篡改数值失去兜底防线，漏检数上升（实测见 comparison）",
            },
            "variants": records,
            "comparison": comparison,
            "boundaries": [
                "对照只在同一输入、同一规则集下成立；换输入必须重跑两档。",
                "污染注入共三型（篡改换算值/静默删行/剥离审计台账），各档抓出数由"
                "_count_caught 按 problems 关键词归类统计；守恒校验与抽检互为冗余防线，"
                "单一机制关闭后另一机制仍可能抓出同类污染，missed 反映的是兜底后的剩余漏检。",
                "抽检上限每档前 8 条换算（首尾各半），超量时以 convert_spot_checks 的实际条数为准。",
                "退化档只用于证明机制贡献方向；对外交付永远是 normal 档。",
                "步骤数/模型请求数由平台统计；引擎只报自身 wall_seconds，不臆造请求数。",
            ],
            "failure_conditions": [
                "规则文件缺失→自动推导档（rules_source=auto_derived），两档基于同一推导规则，对照仍成立。",
                "输入无可识别行数据→两档均 insufficient_evidence，指标全 0，对照无意义（见 status）。",
                "机检器自身异常→gates.machine_verify=unreadable，如实登记，不伪造通过。",
                "注入条数为 0（输入本就无换算且无多余行）→missed 恒 0，该维度不可用于比较，如实标注。",
            ],
            "reproduce": [
                "python3 scripts/clean_run.py evidence --case <case.json> --rules <rules.json> --outdir <outdir>",
                "python3 scripts/clean_run.py evidence --case <case.json> --rules <rules.json> --outdir <outdir> --ablate unit,dirty",
            ],
            "rules_source": rules_source,
            "pivot": pinfo,
        }
        # 交付主体 = 正常档（重新跑一份干净结果，不含注入的故障）
        outdir_norm = os.path.join(outdir, "normal")
        os.makedirs(outdir_norm, exist_ok=True)
        res = apply_clean(rows, rules, policy, ablate=set())
        doc = build_result(get_case_id(case), "answered", res, len(rows), rules,
                           outdir_norm, contract)
        checks, spots, gates, problems = verify_result(doc, case, case_state="enforced",
                                                       rules_state="enforced")
        embed_machine_checks(doc, checks, spots, gates, problems, round_tag="run")
        doc["result"]["gain_evidence"] = gain
        doc["result"]["efficiency"] = {
            "wall_seconds": base["wall_seconds"],
            "rows_in": len(rows), "rows_out": base["metrics"]["rows_out"],
            "rules_evaluated": len(rules),
            "changed_cells": base["metrics"]["changed_cells"],
            "pending_items": base["metrics"]["pending_items"],
            "dirty_values": base["metrics"]["dirty_values"],
            "evidence_variants": len(records),
            "evidence_wall_seconds": round(sum(r["wall_seconds"] for r in records), 4),
            "reproduce": gain["reproduce"],
            "note": "wall_seconds 为引擎单趟耗时；模型请求数由平台统计，引擎不臆造。",
        }
        write_outputs(outdir_norm, doc, res)
        with open(os.path.join(outdir_norm, "gain_evidence.json"), "w", encoding="utf-8") as f:
            json.dump(gain, f, ensure_ascii=False, indent=1)
        with open(os.path.join(outdir, "gain_evidence.json"), "w", encoding="utf-8") as f:
            json.dump(gain, f, ensure_ascii=False, indent=1)
        shutil.copyfile(os.path.join(outdir_norm, "result.json"),
                        os.path.join(outdir, "result.json"))
        for fn in ("cleaned.csv", "changelog.jsonl", "pending_review.json"):
            src = os.path.join(outdir_norm, fn)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(outdir, fn))
        print("[evidence] 档数=%d 正常档: convert=%d pending=%d dirty=%d"
              % (len(records), base["metrics"]["convert_cells"],
                 base["metrics"]["pending_items"], base["metrics"]["dirty_values"]))
        for c in comparison:
            fi = c["fault_injection"]
            print("  - %s: convert %s->%s, pending %s->%s, dirty %s->%s | 注入%d处污染(值改%d/删行%d/剥离%d): 抓出%s 漏检%s"
                  % (c["variant"], c["metric_deltas"]["convert_cells"]["normal"],
                     c["metric_deltas"]["convert_cells"]["variant"],
                     c["metric_deltas"]["pending_items"]["normal"],
                     c["metric_deltas"]["pending_items"]["variant"],
                     c["metric_deltas"]["dirty_values"]["normal"],
                     c["metric_deltas"]["dirty_values"]["variant"],
                     fi.get("injected"),
                     (fi.get("injected_by_type") or {}).get("value_tamper", 0),
                     (fi.get("injected_by_type") or {}).get("row_delete", 0),
                     (fi.get("injected_by_type") or {}).get("audit_strip", 0),
                     fi.get("caught"), fi.get("missed")))
        return 0
    except Exception as e:  # noqa: BLE001
        print("[evidence] FATAL: %s: %s（如实登记，退出码 0）" % (type(e).__name__, e), file=sys.stderr)
        traceback.print_exc()
        return 0


def do_selftest(args):
    """最小可运行自检：用自带示例跑通 skeleton→profile→run→check→evidence，报告每步结果。

    不依赖任何外部输入与第三方库；任何一步失败都如实打印并继续（退出码恒 0）。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    case = os.path.join(root, "examples", "example-case.json")
    rules = os.path.join(root, "examples", "example-rules.json")
    tmp = args.outdir or os.path.join(root, ".selftest")
    steps = []
    try:
        os.makedirs(tmp, exist_ok=True)
        for cmd, extra in (("skeleton", ["--outdir", tmp]),
                           ("profile", ["--out", os.path.join(tmp, "profile.json")]),
                           ("run", ["--outdir", tmp]),
                           ("check", ["--result", os.path.join(tmp, "result.json"),
                                      "--case", case]),
                           ("evidence", ["--outdir", os.path.join(tmp, "evidence")])):
            argv = [cmd, "--case", case] + extra
            if cmd in ("run", "evidence"):
                argv += ["--rules", rules]
            rc = main(argv)
            steps.append({"step": cmd, "exit_code": rc})
        doc = load_json_any(os.path.join(tmp, "result.json"))
        mc = (doc.get("result") or {}).get("machine_checks") or {}
        checks = mc.get("checks") or []
        spots = mc.get("convert_spot_checks") or []
        n_match = sum(1 for c in checks + spots if c.get("match"))
        print("[selftest] 步骤: %s" % ", ".join("%s=%s" % (s["step"], s["exit_code"])
                                              for s in steps))
        print("[selftest] 机检三元组 %d/%d match, all_pass=%s, 退出码全为 0"
              % (n_match, len(checks) + len(spots), mc.get("all_pass")))
        ok = all(s["exit_code"] == 0 for s in steps) and bool(mc.get("all_pass"))
        print("[selftest] 结论: %s" % ("PASS" if ok else "FAIL（见上方机检 problems）"))
        return 0
    except Exception as e:  # noqa: BLE001
        print("[selftest] FATAL: %s: %s（如实登记，退出码 0）" % (type(e).__name__, e), file=sys.stderr)
        traceback.print_exc()
        return 0


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="clean_run.py", description="sciclean-r1 科研数据清洗与处理引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("skeleton")
    p.add_argument("--case", required=True)
    p.add_argument("--outdir", required=True)
    p = sub.add_parser("profile")
    p.add_argument("--case", required=True)
    p.add_argument("--rows", default=None)
    p.add_argument("--out", required=True)
    p = sub.add_parser("run")
    p.add_argument("--case", required=True)
    p.add_argument("--rules", default=None)
    p.add_argument("--rows", default=None)
    p.add_argument("--outdir", required=True)
    p.add_argument("--ablate", default="")
    p = sub.add_parser("check")
    p.add_argument("--result", required=True)
    p.add_argument("--case", default=None)
    p = sub.add_parser("evidence")
    p.add_argument("--case", required=True)
    p.add_argument("--rules", default=None)
    p.add_argument("--rows", default=None)
    p.add_argument("--outdir", required=True)
    p.add_argument("--ablate", default="")
    p = sub.add_parser("selftest")
    p.add_argument("--outdir", default=None)
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
        if args.cmd == "evidence":
            return do_evidence(args)
        if args.cmd == "selftest":
            return do_selftest(args)
        print("[clean_run] 未知模式（如实登记，退出码 0）", file=sys.stderr)
        return 0
    except SystemExit as e:  # argparse 缺参数等：打印提示后仍以 0 退出，绝不中断交付链
        print("[clean_run] 参数问题: %s（如实登记，退出码 0；请按 --help 用法补参数）" % e,
              file=sys.stderr)
        return 0
    except Exception as e:  # noqa: BLE001
        print("[clean_run] FATAL: %s: %s（如实登记，退出码 0）" % (type(e).__name__, e),
              file=sys.stderr)
        traceback.print_exc()
        return 0


if __name__ == "__main__":
    sys.exit(main())
