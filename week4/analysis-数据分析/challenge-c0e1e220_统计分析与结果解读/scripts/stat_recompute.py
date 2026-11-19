#!/usr/bin/env python3
"""stat_recompute.py — 统计量复算与检验选择期望（stat-analysis-audit）。

对 result.analyses 逐组做两件事（只用标准库 statistics/math，不装 numpy）：
  1. 描述统计复算：从 case.json 数据集原始数值复算 n / mean / variance / stdev /
     分位数（线性插值法，与 statistics.quantiles 一致口径），与 claimed 统计量
     对照（默认相对容差 1e-6），diff 写 result.stat_recompute（**键归属：本脚本
     只写 stat_recompute 这一个键**，与 verify_check / gain_probe / build_skeleton /
     interpret_rollup 不冲突）。
  2. 检验选择期望：按组数 / 配对 / 正态性 / 方差齐性 / 样本量推期望检验族
     （parametric / nonparametric），与 test_registration 登记的 family/name 对照，
     失配记 method_mismatch。
数据不可得时如实登记 unavailable，绝不臆造数字。任何失败不抛出、不中断。

用法：
    python3 stat_recompute.py --result /app/output/result.json --case /input/case.json \
        [--tolerance 1e-6]
退出码恒为 0（结论记在 stdout 与 result.stat_recompute.all_match）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys

DATA_KEYS = ("datasets", "records", "data", "tables", "studies", "materials")
VAL_KEYS = ("values", "data", "measurements", "observations", "samples")


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
        print("[stat_recompute] 写盘失败 %s: %s" % (path, e))
        return False


def marker_note():
    """定位标志文件校验：脚本与 SKILL.md 同包才算挂载命中（只提示，不阻断）。"""
    m = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    return bool(os.path.exists(m))


def to_float(x):
    """严格数值解析：非数值（None/字符串/缺失标记）返回 None，不静默当 0。"""
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return None if (isinstance(x, float) and math.isnan(x)) else float(x)
    s = str(x).strip()
    if not s or s.lower() in ("na", "nan", "null", "none", "missing", "-", "n/a"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def collect_values(dataset, variable):
    """从数据集提取某变量的一维数值列表；缺值跳过并计数，绝不按 0 计入。"""
    vals, skipped = [], 0
    if not isinstance(dataset, dict):
        return vals, skipped
    # 1) 直接一维数值数组
    for vk in VAL_KEYS:
        v = dataset.get(vk)
        if isinstance(v, list) and v:
            for x in v:
                if isinstance(x, dict) and variable:
                    f = to_float(x.get(variable))
                else:
                    f = to_float(x)
                if f is None:
                    skipped += 1
                else:
                    vals.append(f)
            if vals or skipped:
                return vals, skipped
    # 2) 行记录列表（list[dict] 或 list[list]）
    rows = None
    for rk in ("rows", "records_list", "entries"):
        if isinstance(dataset.get(rk), list):
            rows = dataset[rk]
            break
    if rows is None:
        # 3) 列式存储 {col: [v,...]}
        cols = dataset.get("columns")
        if isinstance(cols, dict) and variable in cols and isinstance(cols[variable], list):
            for x in cols[variable]:
                f = to_float(x)
                if f is None:
                    skipped += 1
                else:
                    vals.append(f)
            return vals, skipped
        return vals, skipped
    for r in rows:
        if isinstance(r, dict):
            f = to_float(r.get(variable))
        elif isinstance(r, (list, tuple)):
            names = dataset.get("column_names") or dataset.get("fields") or []
            f = None
            if variable and variable in names:
                f = to_float(r[names.index(variable)])
            else:
                skipped += 1
                continue
        else:
            skipped += 1
            continue
        if f is None:
            skipped += 1
        else:
            vals.append(f)
    return vals, skipped


def quantiles_linear(vals):
    """分位数（p25/p50/p75），线性插值法；n<2 时返回空。"""
    if len(vals) < 2:
        return {}
    try:
        q = statistics.quantiles(vals, n=4, method="inclusive")
        return {"p25": q[0], "p50": q[1], "p75": q[2]}
    except Exception:
        s = sorted(vals)
        def pct(p):
            k = (len(s) - 1) * p
            f = math.floor(k)
            c = min(f + 1, len(s) - 1)
            return s[f] + (s[c] - s[f]) * (k - f)
        return {"p25": pct(0.25), "p50": pct(0.50), "p75": pct(0.75)}


def recompute(vals):
    n = len(vals)
    out = {"n": n}
    if n == 0:
        return out
    out["mean"] = statistics.fmean(vals)
    if n >= 2:
        out["variance"] = statistics.variance(vals)  # 样本方差（n-1 口径）
        out["stdev"] = statistics.stdev(vals)
    out.update(quantiles_linear(vals))
    return out


def close(a, b, tol):
    try:
        a, b = float(a), float(b)
    except Exception:
        return None
    if math.isnan(a) or math.isnan(b):
        return None
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom <= tol


def compare(rec, claimed, tol):
    diffs, match = {}, True
    for k, rv in rec.items():
        cv = claimed.get(k)
        if cv is None:
            diffs[k] = "claimed 缺失"
            continue
        ok = close(cv, rv, tol)
        if ok is False:
            diffs[k] = {"claimed": cv, "recomputed": rv,
                        "rel_diff": abs(float(cv) - float(rv)) / max(abs(float(rv)), 1e-12)}
            match = False
        elif ok is None:
            diffs[k] = "claimed 值不可解析为数值"
            match = False
    return diffs, match


def expected_test(tr):
    """按登记的假设推期望检验族与名称（与题面方向 2 对应）。"""
    n_groups = int(tr.get("n_groups") or 2)
    paired = bool(tr.get("paired"))
    assumptions = tr.get("assumptions") or {}
    normality = str(assumptions.get("normality") or tr.get("normality") or "unknown")
    var_eq = str(assumptions.get("variance_equality") or tr.get("variance_equality") or "unknown")
    normal = normality in ("yes", "true", "normal", "passed")
    # 相关性设计：相关系数检验（Pearson 需双变量正态，否则 Spearman）
    if str(tr.get("test_type") or "") == "correlation":
        if normal:
            return "parametric", ["pearson", "pearson correlation", "皮尔逊相关"]
        return "nonparametric", ["spearman", "spearman correlation", "斯皮尔曼相关"]
    if paired:
        if normal:
            return "parametric", ["paired t-test", "paired_t", "配对t检验"]
        return "nonparametric", ["wilcoxon signed-rank", "wilcoxon", "符号秩"]
    if n_groups >= 3:
        if normal:
            return "parametric", ["anova", "one-way anova", "welch anova", "方差分析"]
        return "nonparametric", ["kruskal-wallis", "kruskal"]
    # 两独立样本：非正态 ⇒ 非参数；方差不齐 ⇒ Welch
    if not normal:
        return "nonparametric", ["mann-whitney", "mann-whitney u", "wilcoxon rank-sum", "秩和检验"]
    if var_eq == "no" or var_eq in ("false", "unequal", "failed"):
        return "parametric", ["welch", "welch t", "t-test (welch)"]
    return "parametric", ["t-test", "independent t-test", "student t", "two-sample t"]


def check_test_reg(tr):
    fam_exp, names_exp = expected_test(tr)
    fam_reg = str(tr.get("test_family") or "").strip().lower()
    name_reg = str(tr.get("test_name") or "").strip().lower()
    family_match = fam_reg == fam_exp if fam_reg else None
    name_match = None
    if name_reg:
        name_match = any(n in name_reg or name_reg in n for n in names_exp)
    return {"expected_family": fam_exp, "expected_names": names_exp,
            "family_match": family_match, "name_match": name_match,
            "method_mismatch": (family_match is False) or (name_match is False)}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--tolerance", type=float, default=1e-6)
        args = ap.parse_args()
    except Exception as e:
        print("[stat_recompute] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[stat_recompute] FAIL: result.json 不存在/不可解析或缺 result 对象: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)
    if not isinstance(case, dict):
        print("[stat_recompute] case.json 不可读，复算 unavailable（不中断交付）")
        case = {}

    # 数据集索引：dataset_id → dataset 对象
    ds_index = {}
    for key in DATA_KEYS:
        v = case.get(key)
        if isinstance(v, list):
            for e in v:
                if isinstance(e, dict):
                    did = str(e.get("dataset_id") or e.get("id") or e.get("name") or "")
                    if did:
                        ds_index[did] = e

    tol = float(args.tolerance)
    per_dataset = []
    all_match = True
    for a in res["result"].get("analyses") or []:
        if not isinstance(a, dict):
            continue
        aid = str(a.get("analysis_id") or "")
        did = str(a.get("dataset_id") or "")
        desc = a.get("descriptive") or {}
        variable = str(desc.get("variable") or "")
        # claimed 统计量（*_claimed 命名 → 复算键名归一化）
        qc = desc.get("quantiles_claimed") or {}
        claimed = {
            "n": desc.get("n_claimed"),
            "mean": desc.get("mean_claimed"),
            "variance": desc.get("variance_claimed"),
            "stdev": desc.get("sd_claimed"),
            "p25": qc.get("p25"), "p50": qc.get("p50"), "p75": qc.get("p75"),
        }
        entry = {"analysis_id": aid, "dataset_id": did, "variable": variable,
                 "status": "ok", "missing_skipped": None, "recomputed": {},
                 "diffs": {}, "match": None, "test_check": None, "note": ""}
        try:
            ds = ds_index.get(did)
            if ds is None:
                entry["status"] = "unavailable"
                entry["note"] = "case.json 中找不到 dataset_id=%s 的原始数据，复算不可得（如实登记，不臆造）" % did
            else:
                vals, skipped = collect_values(ds, variable)
                entry["missing_skipped"] = skipped
                if not vals:
                    entry["status"] = "unavailable"
                    entry["note"] = "变量 %r 数值提取为空（字段缺失或非数值），复算不可得" % variable
                else:
                    rec = recompute(vals)
                    entry["recomputed"] = rec
                    diffs, match = compare(rec, claimed, tol)
                    entry["diffs"] = diffs
                    entry["match"] = match
                    if not match:
                        all_match = False
                        entry["note"] = "claimed 统计量与复算不符（容差 %g，相对误差）" % tol
            tr = a.get("test_registration") or {}
            if tr:
                tc = check_test_reg(tr)
                entry["test_check"] = tc
                if tc["method_mismatch"]:
                    all_match = False
        except Exception as e:
            entry["status"] = "error"
            entry["note"] = "复算异常（如实登记）: %s" % e
            all_match = False
        per_dataset.append(entry)

    stat_recompute = {
        "computed_by": "scripts/stat_recompute.py",
        "marker_hit": marker_note(),
        "tolerance": tol,
        "variance_convention": "样本方差（n-1）；分位数线性插值（inclusive）",
        "missing_policy": "缺失/非数值条目跳过并计数（missing_skipped），绝不按 0 计入",
        "per_dataset": per_dataset,
        "all_match": all_match,
    }
    res["result"]["stat_recompute"] = stat_recompute
    save_json(args.result, res)

    print("[stat_recompute] marker_hit=%s tolerance=%g 组数=%d all_match=%s"
          % (stat_recompute["marker_hit"], tol, len(per_dataset), all_match))
    for e in per_dataset:
        print("  %-10s %-10s match=%-5s test_mismatch=%-5s skipped=%s %s"
              % (e["analysis_id"], e["status"], e["match"],
                 (e["test_check"] or {}).get("method_mismatch"),
                 e["missing_skipped"], e["note"][:70]))
    print("[stat_recompute] done（exit 0）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[stat_recompute] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
