#!/usr/bin/env python3
"""anomaly_detect.py — 异常点机械检测（exp-result-anomaly，核心脚本）。

只做一件事：从 case.json 的数值序列机械检出异常点，定位到 样本/批次/通道/
孔位/时间点 维度，给出异常程度、判定阈值、与对照基线的偏离幅度。

检测口径（阈值取 result.thresholds，缺省用内置默认，事前声明后禁改）：
- outlier：|z| > outlier_z（z 用样本 sd，n<2 或 sd=0 时跳过）
- jump   ：|(v[i]-v[i-1])/v[i-1]| > jump_rel（i 为跳变落点）
- plateau：连续段相邻相对变化 ≤ plateau_tol_rel 且段长 ≥ plateau_min_points

维度定位：值点若为 dict 且带 sample/batch/channel/well/time 等键，用该键值定位；
否则退回 dataset 的 dimension 字段（缺省"时间点"）+ 数组索引。

写入 result.anomalies 与 result.detection（仅这两键归本脚本，possible_cause
留 null 由模型配一句话）。全捕获容错，退出码恒为 0。

用法：
    python3 anomaly_detect.py --result /app/output/result.json --case /input/case.json \
        [--max-per-case 8]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DEFAULT_THRESHOLDS = {"outlier_z": 3.0, "jump_rel": 0.5,
                      "plateau_min_points": 3, "plateau_tol_rel": 0.05}
DATA_KEYS = ("datasets", "series", "traces", "records", "data", "tables",
             "results", "experiments", "materials", "readings", "curves")
VALUE_KEYS = ("values", "readings", "points", "measurements", "series", "data",
              "traces", "records", "results", "curves", "intensities", "absorbances")
NUM_FIELD_KEYS = ("value", "reading", "y", "result", "measurement", "value_num",
                  "intensity", "absorbance", "concentration", "strength")
DIM_FIELD_KEYS = ("sample", "sample_id", "batch", "batch_id", "channel", "channel_id",
                  "well", "well_id", "time", "time_point", "point", "index", "replicate")
DIM_LABEL = {"sample": "样本", "sample_id": "样本", "batch": "批次", "batch_id": "批次",
             "channel": "通道", "channel_id": "通道", "well": "孔位", "well_id": "孔位",
             "time": "时间点", "time_point": "时间点", "point": "时间点",
             "index": "时间点", "replicate": "重复"}


def _fnum(x):
    try:
        if isinstance(x, bool):
            return None
        return float(x)
    except Exception:
        return None


def get_thresholds(result):
    try:
        th = (result.get("result") or {}).get("thresholds") or {}
        out = dict(DEFAULT_THRESHOLDS)
        for k in DEFAULT_THRESHOLDS:
            fv = _fnum(th.get(k))
            if fv is not None and fv > 0:
                out[k] = fv
        return out
    except Exception:
        return dict(DEFAULT_THRESHOLDS)


def extract_series(ds):
    """返回 (points, dimension, unit, note)；points 为 [{v, meta}]。"""
    if not isinstance(ds, dict):
        return [], "时间点", None, "数据集非对象"
    unit = ds.get("unit") or ds.get("uom") or None
    dim = str(ds.get("dimension") or ds.get("dim") or "时间点")
    for k in VALUE_KEYS:
        v = ds.get(k)
        if isinstance(v, list) and v:
            points, skipped = [], 0
            for e in v:
                if isinstance(e, dict):
                    f = None
                    for nk in NUM_FIELD_KEYS:
                        f = _fnum(e.get(nk))
                        if f is not None:
                            break
                    if f is None:
                        skipped += 1
                        continue
                    meta = {"idx": len(points)}
                    for dk in DIM_FIELD_KEYS:
                        dv = e.get(dk)
                        if dv is not None:
                            meta[dk] = str(dv)
                    points.append({"v": f, "meta": meta})
                else:
                    f = _fnum(e)
                    if f is None:
                        skipped += 1
                    else:
                        points.append({"v": f, "meta": {"idx": len(points)}})
            note = ("跳过 %d 个非数值项" % skipped) if skipped else ""
            return points, dim, unit, note
    return [], dim, unit, "未找到数值序列键 %s" % ",".join(VALUE_KEYS)


def _ref_label(meta):
    parts = []
    for dk in ("sample", "sample_id", "batch", "batch_id", "channel", "channel_id",
               "well", "well_id", "time", "time_point", "point", "replicate"):
        if dk in meta:
            parts.append("%s=%s" % (DIM_LABEL.get(dk, dk), meta[dk]))
    parts.append("index=%d" % meta.get("idx", 0))
    return ", ".join(parts)


def _dimension(meta, fallback):
    for dk in ("sample", "sample_id", "batch", "batch_id", "channel", "channel_id",
               "well", "well_id"):
        if dk in meta:
            return DIM_LABEL.get(dk, dk)
    return fallback


def pct(x, base):
    if base in (None, 0):
        return None
    return (x - base) / abs(base) * 100.0


def detect(points, th, dim, unit, dataset_id):
    """检出 anomalies，返回 (list, stats)。"""
    vals = [p["v"] for p in points]
    n = len(vals)
    anomalies = []
    seen = set()  # (type, idx) 去重
    if n < 2:
        return anomalies, {"n": n, "skipped_noise": 0}
    mean = sum(vals) / n
    sd = None
    if n >= 2:
        var = sum((x - mean) ** 2 for x in vals) / (n - 1)
        sd = var ** 0.5

    def add(atype, i, severity, observed, baseline, threshold_used, deviation):
        key = (atype, i)
        if key in seen:
            return
        seen.add(key)
        base_ref = baseline.get("reference") if isinstance(baseline, dict) else None
        anomalies.append({
            "anomaly_id": None,  # 回填编号
            "dataset_id": dataset_id,
            "dimension": _dimension(points[i]["meta"], dim),
            "object_ref": _ref_label(points[i]["meta"]),
            "anomaly_type": atype,
            "observed_value": round(observed, 6),
            "unit": unit,
            "threshold_used": threshold_used,
            "severity": severity,
            "baseline": baseline,
            "baseline_ref": base_ref,
            "deviation": deviation,
            "evidence_location": "datasets[%s][%d]" % (dataset_id, i),
            "possible_cause": None,
        })

    # outlier（z 分数，对照基线用中位数避免离群点污染）
    if sd and sd > 0:
        sval = sorted(vals)
        mid = sval[n // 2] if n % 2 else (sval[n // 2 - 1] + sval[n // 2]) / 2.0
        for i, x in enumerate(vals):
            z = (x - mean) / sd
            if abs(z) > th["outlier_z"]:
                dev = pct(x, mid)
                add("outlier", i,
                    "z=%.2f" % z, x,
                    {"value": round(mid, 6), "reference": "全序列中位数"},
                    "outlier_z=%.2f" % th["outlier_z"],
                    ("%+.1f%%" % dev) if dev is not None else "无法计算（基线为0）")
    # jump（相对跳变）
    for i in range(1, n):
        prev = vals[i - 1]
        if prev != 0:
            rel = abs((vals[i] - prev) / abs(prev))
            if rel > th["jump_rel"]:
                dev = pct(vals[i], prev)
                add("jump", i,
                    "相对前一读数 %.1f%%" % (rel * 100), vals[i],
                    {"value": round(prev, 6), "reference": "相邻前一个读数"},
                    "jump_rel=%.2f" % th["jump_rel"],
                    ("%+.1f%%" % dev) if dev is not None else "无法计算（基线为0）")
    # plateau（平台段）——正常结构，仅作背景统计，不报异常（避免把正常平台当异常）
    plateaus = []
    run_start = 0
    for i in range(1, n + 1):
        in_run = False
        if i < n and vals[i - 1] != 0:
            in_run = abs((vals[i] - vals[i - 1]) / abs(vals[i - 1])) <= th["plateau_tol_rel"]
        if not in_run:
            seg_len = i - run_start
            if seg_len >= th["plateau_min_points"]:
                plateaus.append({"start": run_start, "end": i - 1,
                                 "length": seg_len,
                                 "mean": round(sum(vals[run_start:i]) / seg_len, 6)})
            run_start = i
    stats = {"n": n, "mean": round(mean, 6),
             "sd": None if sd is None else round(sd, 6),
             "plateaus": plateaus}
    return anomalies, stats


def main():
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--max-per-case", type=int, default=8)
        args = ap.parse_args()
    except Exception as e:
        print("[anomaly_detect] 参数解析失败（已降级）: %s" % e)
        return 0

    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")
    marker_hit = os.path.exists(marker)
    if not marker_hit:
        print("[anomaly_detect] WARN: 定位标志未命中（脚本未与 SKILL.md 同包），仍继续")

    result, case, problems = {}, {}, []
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            result = json.load(f)
    except Exception as e:
        print("[anomaly_detect] FAIL: result.json 读取失败：%s（不中断交付）" % e)
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
    datasets = []
    for key in DATA_KEYS:
        v = case.get(key) if isinstance(case, dict) else None
        if isinstance(v, list):
            for i, e in enumerate(v):
                if isinstance(e, dict):
                    did = str(e.get("dataset_id") or e.get("id") or e.get("name") or "%s[%d]" % (key, i))
                    datasets.append((did, e))
                elif isinstance(e, (int, float)):
                    datasets.append(("%s[%d]" % (key, i), {"values": [e]}))
    # case.json 本身若就是含数值数组的 dict
    if not datasets and isinstance(case, dict):
        for key in DATA_KEYS:
            v = case.get(key)
            if isinstance(v, list) and v and all(_fnum(x) is not None for x in v):
                datasets.append((key, {"values": v}))

    all_anoms, detection, scanned = [], [], 0
    for did, ds in datasets:
        points, dim, unit, note = extract_series(ds)
        scanned += 1
        if not points:
            detection.append({"dataset_id": did, "status": "unavailable", "note": note})
            problems.append("%s: %s" % (did, note))
            continue
        try:
            anoms, stats = detect(points, th, dim, unit, did)
        except Exception as e:
            detection.append({"dataset_id": did, "status": "error", "note": str(e)})
            problems.append("%s: 检测异常 %s" % (did, e))
            continue
        for a in anoms:
            a["anomaly_id"] = "AN-%02d" % (len(all_anoms) + 1)
            all_anoms.append(a)
        detection.append({"dataset_id": did, "status": "ok", "stats": stats,
                          "detected": len(anoms)})

    # 封顶：按 severity 强度排序（outlier>jump>plateau，再按 |偏离|），每案例至多 max-per-case
    type_rank = {"outlier": 0, "jump": 1, "plateau": 2}
    all_anoms.sort(key=lambda a: (type_rank.get(a["anomaly_type"], 9),
                                  _fnum(re.sub(r"[^0-9.\-]", "", a.get("severity") or "")) or 0))
    full = list(all_anoms)
    capped = full[:max(0, args.max_per_case)]

    out_detection = {
        "computed_by": "scripts/anomaly_detect.py",
        "thresholds_used": th,
        "datasets_scanned": scanned,
        "anomalies_detected_total": len(full),
        "anomalies_reported": len(capped),
        "per_dataset": detection,
    }
    try:
        inner = result.get("result")
        if isinstance(inner, dict):
            inner["anomalies"] = capped          # 仅这两键归本脚本
            inner["detection"] = out_detection
            if not inner.get("thresholds"):
                inner["thresholds"] = dict(th)
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except Exception as e:
        problems.append("回写失败: %s" % e)

    print("[anomaly_detect] case_id=%s | 扫描 %d 组 | 检出 %d | 上报 %d | marker_hit=%s"
          % (result.get("case_id"), scanned, len(full), len(capped), marker_hit))
    for pr in problems:
        print("  WARN: %s" % pr)
    print("[anomaly_detect] 已回写 result.anomalies / result.detection")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[anomaly_detect] 未预期异常（已降级）: %s" % e)
        sys.exit(0)