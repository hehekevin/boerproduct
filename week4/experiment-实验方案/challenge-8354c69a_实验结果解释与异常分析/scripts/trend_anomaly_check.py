#!/usr/bin/env python3
"""trend_anomaly_check.py — Step 3 趋势与异常机械复算（exp-result-explain）。

从 case.json 原始读数复算 n/mean/sd/最小二乘斜率/方向、z 分数离群、相对跳变、
连续平台段，与 result.analyses 的 claimed trend.direction 与 anomalies 清单对照；
缺失/非数值跳过并计数，绝不按 0 计入。阈值一律取 result.judge_rules.
detection_thresholds（缺省用内置保守默认）。
写入 result.trend_anomaly_check（仅此键）。全捕获容错，退出码恒为 0。

方向口径：rel = slope*span/mean；|rel| < 0.05 ⇒ flat，否则按符号 increasing/decreasing。
定位标志：与 SKILL.md 同包（../SKILL.md 存在）才视为挂载命中，未命中打印 WARN 不中断。

用法：
    python3 trend_anomaly_check.py --result /app/output/result.json --case /input/case.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_THRESHOLDS = {"outlier_z": 3.0, "jump_rel": 0.5,
                      "plateau_min_points": 3, "plateau_tol_rel": 0.05}
VALUE_KEYS = ("values", "readings", "points", "measurements", "series", "data")
NUM_FIELD_KEYS = ("value", "reading", "y", "result", "measurement", "value_num")


def _fnum(x):
    try:
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def extract_series(ds):
    """从数据集对象提取数值序列；返回 (values, note)。"""
    if not isinstance(ds, dict):
        return [], "数据集非对象"
    for k in VALUE_KEYS:
        v = ds.get(k)
        if isinstance(v, list) and v:
            vals, skipped = [], 0
            for e in v:
                if isinstance(e, dict):
                    f = None
                    for nk in NUM_FIELD_KEYS:
                        f = _fnum(e.get(nk))
                        if f is not None:
                            break
                    if f is None:
                        skipped += 1
                    else:
                        vals.append(f)
                else:
                    f = _fnum(e)
                    if f is None:
                        skipped += 1
                    else:
                        vals.append(f)
            return vals, ("跳过 %d 个非数值项" % skipped if skipped else "")
    return [], "未找到数值序列键（%s）" % ",".join(VALUE_KEYS)


def get_thresholds(result):
    try:
        th = (result.get("result") or {}).get("judge_rules", {}).get("detection_thresholds") or {}
        out = dict(DEFAULT_THRESHOLDS)
        for k in DEFAULT_THRESHOLDS:
            fv = _fnum(th.get(k))
            if fv is not None and fv > 0:
                out[k] = fv
        return out
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def recompute(vals, th):
    n = len(vals)
    mean = sum(vals) / n if n else None
    sd = None
    if n >= 2:
        var = sum((x - mean) ** 2 for x in vals) / (n - 1)
        sd = var ** 0.5
    slope = None
    direction = "unknown"
    if n >= 2 and mean not in (None, 0):
        idx_mean = (n - 1) / 2.0
        denom = sum((i - idx_mean) ** 2 for i in range(n))
        if denom:
            slope = sum((i - idx_mean) * (vals[i] - mean) for i in range(n)) / denom
        rel = slope * (n - 1) / abs(mean) if slope is not None else 0.0
        if abs(rel) < 0.05:
            direction = "flat"
        elif rel > 0:
            direction = "increasing"
        else:
            direction = "decreasing"
    # 离群：z 分数
    outliers = []
    if sd and sd > 0:
        outliers = [i for i, x in enumerate(vals) if abs((x - mean) / sd) > th["outlier_z"]]
    # 跳变：相邻相对变化
    jumps = []
    for i in range(1, n):
        base = vals[i - 1]
        if base != 0 and abs((vals[i] - base) / abs(base)) > th["jump_rel"]:
            jumps.append(i)
    # 平台期：连续段内相邻相对变化 ≤ tol 且段长 ≥ min_points
    plateaus, run_start = [], 0
    for i in range(1, n + 1):
        in_run = False
        if i < n and vals[i - 1] != 0:
            in_run = abs((vals[i] - vals[i - 1]) / abs(vals[i - 1])) <= th["plateau_tol_rel"]
        if not in_run:
            if i - run_start >= th["plateau_min_points"]:
                plateaus.append([run_start, i - 1])
            run_start = i
    return {"n": n, "mean": mean, "sd": sd, "slope": slope, "direction": direction,
            "outlier_indices": outliers, "jump_indices": jumps,
            "plateau_ranges": plateaus}


def parse_indices(text):
    """从 object_ref 提取索引（values[5] / index=5 / [3,7] 等），无 isalpha 参与。"""
    if not text:
        return []
    t = str(text)
    out = []
    for m in re.finditer(r"\[(\d+)(?:\s*,\s*(\d+))?\]", t):
        out.append(int(m.group(1)))
        if m.group(2):
            out.append(int(m.group(2)))
    for m in re.finditer(r"(?:index|idx|点|序号)\s*[:=]?\s*(\d+)", t):
        out.append(int(m.group(1)))
    return sorted(set(out))


def match_claimed(claimed_anoms, rec, th):
    """claimed anomalies 与复算结果对照；返回 diffs 与 match。"""
    diffs, matched_all, unknown_refs = [], True, 0
    claimed_types = {}
    for a in claimed_anoms or []:
        if not isinstance(a, dict):
            continue
        atype = str(a.get("anomaly_type") or "")
        claimed_types.setdefault(atype, []).append(a)
    # outlier / jump 按索引交集对照
    for atype, rec_idx in (("outlier", rec["outlier_indices"]), ("jump", rec["jump_indices"])):
        cl = claimed_types.get(atype, [])
        c_idx = []
        for a in cl:
            idxs = parse_indices(a.get("object_ref") or a.get("dimension") or "")
            if idxs:
                c_idx.extend(idxs)
            else:
                unknown_refs += 1
        c_set = set(c_idx)
        missed = [i for i in rec_idx if i not in c_set]
        extra = [i for i in c_set if i not in rec_idx]
        if rec_idx and missed:
            diffs.append("%s: 复算发现离群/跳变索引 %s 未被 claimed 覆盖 %s"
                         % (atype, missed, sorted(set(rec_idx) - set(missed))))
            matched_all = False
        if extra:
            diffs.append("%s: claimed 索引 %s 未被复算确认" % (atype, extra))
            matched_all = False
    # plateau 按区间重叠对照
    rec_pl = [tuple(r) for r in rec["plateau_ranges"]]
    cl_pl = claimed_types.get("plateau", [])
    hit = set()
    for a in cl_pl:
        idxs = parse_indices(a.get("object_ref") or "")
        ok = False
        if len(idxs) >= 1:
            lo = idxs[0]
            hi = idxs[-1] if len(idxs) > 1 else idxs[0]
            for r in rec_pl:
                if lo <= r[1] and hi >= r[0]:
                    ok = True
                    hit.add(r)
                    break
        if not ok:
            diffs.append("plateau: claimed %s 未被复算平台段确认（复算：%s）"
                         % (a.get("object_ref"), rec_pl))
            matched_all = False
    return diffs, matched_all, unknown_refs


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        args = ap.parse_args()
    except Exception as e:
        print("[trend_anomaly_check] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        print("[trend_anomaly_check] WARN: 定位标志未命中（脚本未与 SKILL.md 同包），仍继续")

    result, case, problems = {}, {}, []
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[trend_anomaly_check] FAIL: result.json 读取失败：%s（不中断交付）" % e)
        return 0
    try:
        if os.path.exists(args.case):
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
        else:
            problems.append("case.json 不存在: %s" % args.case)
    except Exception as e:
        problems.append("case.json 读取失败: %s" % e)

    th = get_thresholds(result)
    case_ds = {}
    for key in ("datasets", "series", "traces", "records", "data", "tables",
                "results", "experiments", "materials"):
        v = case.get(key) if isinstance(case, dict) else None
        if isinstance(v, list):
            for i, e in enumerate(v):
                if isinstance(e, dict):
                    did = str(e.get("dataset_id") or e.get("id") or e.get("name") or "%s[%d]" % (key, i))
                    case_ds[did] = e
                    case_ds["%s[%d]" % (key, i)] = e

    per_dataset, all_match = [], True
    analyses = (result.get("result") or {}).get("analyses") or []
    for a in analyses:
        aid = str(a.get("analysis_id") or "?")
        ds = case_ds.get(str(a.get("dataset_id") or ""), case_ds.get(aid))
        entry = {"analysis_id": aid, "status": "ok", "recomputed": {},
                 "claimed": {}, "diffs": [], "match": None, "missing_skipped": 0}
        vals, note = (extract_series(ds) if ds is not None else ([], "case.json 未找到对应数据集"))
        if note:
            entry["note"] = note
        if not vals:
            entry["status"] = "unavailable"
            entry["match"] = None
            problems.append("%s: %s" % (aid, note or "无数值序列"))
            per_dataset.append(entry)
            all_match = False if entry["match"] is None else all_match
            continue
        entry["missing_skipped"] = 1 if "跳过" in (note or "") else 0
        try:
            rec = recompute(vals, th)
        except Exception as e:
            entry["status"] = "unavailable"
            entry["note"] = "复算异常: %s" % e
            problems.append("%s: 复算异常 %s" % (aid, e))
            per_dataset.append(entry)
            continue
        entry["recomputed"] = rec
        entry["claimed"] = {
            "trend_direction": (a.get("trend") or {}).get("direction"),
            "anomaly_count": len(a.get("anomalies") or []),
        }
        diffs = []
        claimed_dir = (a.get("trend") or {}).get("direction")
        if claimed_dir and claimed_dir != rec["direction"]:
            diffs.append("trend: claimed=%s 但复算=%s（口径 |slope*span/mean|<0.05 ⇒ flat）"
                         % (claimed_dir, rec["direction"]))
        try:
            adiffs, amatch, unknown_refs = match_claimed(a.get("anomalies"), rec, th)
            diffs.extend(adiffs)
            if unknown_refs:
                entry["claimed_object_ref_unparsed"] = unknown_refs
            amatch = amatch and claimed_dir == rec["direction"]
        except Exception as e:
            amatch = False
            diffs.append("异常对照异常: %s" % e)
        entry["diffs"] = diffs
        entry["match"] = bool(amatch) and not diffs
        if not entry["match"]:
            all_match = False
            problems.extend(["%s: %s" % (aid, d) for d in diffs])
        per_dataset.append(entry)

    out = {
        "computed_by": "scripts/trend_anomaly_check.py",
        "thresholds_used": th,
        "direction_rule": "rel=slope*(n-1)/|mean|; |rel|<0.05⇒flat",
        "per_dataset": per_dataset,
        "all_match": all_match,
    }
    try:
        inner = result.get("result")
        if isinstance(inner, dict):
            inner["trend_anomaly_check"] = out  # 仅此键归本脚本
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("回写失败: %s" % e)

    print("[trend_anomaly_check] case_id=%s | 组数 %d | all_match=%s | marker_hit=%s"
          % (result.get("case_id"), len(per_dataset), all_match, marker_hit))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[trend_anomaly_check] 已回写 result.trend_anomaly_check")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[trend_anomaly_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
