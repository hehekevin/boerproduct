#!/usr/bin/env python3
"""stat_recompute.py — 统计量数值复算引擎（research-stat-audit 研究方法与统计审查）。

从 result.json 的 findings[].stat_claim 读取稿件报告的统计量断言，用纯标准库
机械复算并判一致性，回写 result.stat_recompute（本脚本唯一写键）。

支持的复算类型（type）：
  r_to_t      r 与 n → t=r*sqrt((n-2)/(1-r^2))，df=n-2，正态近似 p；核对 claimed t/p/p_max
  t_to_p      t（可选 df）→ 正态近似双侧 p；核对 claimed p（容差 0.015）或 p_max
  ci_from_se  est/se/level → 期望 CI 宽 2*z*se（容差 5%）；核对 claimed ci_low/ci_high
              （z 取 0.90/0.95/0.99 常数表）且 est 须落在 CI 内
  ci_vs_null  CI 与 null 值 → 排除 null ⇔ claimed significant 一致
  df_vs_n     n 与设计 → 期望自由度（two_group n-2 / paired n-1 / one_sample n-1）；
              claimed df 超过 n-1 即不一致（df 与样本量矛盾的机械下界）
  group_shares 各组 n 求和/百分比范围核对 claimed total

一致性输出三值：true / false / indeterminate（参数不全或类型未知）。近似口径：
标准库无 t 分布分位数，p 值用正态近似（df<30 时容差放宽到 0.015 并在 detail 注明）。

**键归属**：本脚本只写 result.stat_recompute 一个键；coverage/unchecked 归
coverage_audit.py，gain_evidence/efficiency 归 gain_probe.py，self_check 等四键
归 verify_check.py，其余归 build_skeleton + Agent。
退出码恒为 0（结论记在 stdout 与报告，不中断交付）。
用法：
    python3 stat_recompute.py --result /app/output/result.json [--out 报告路径] [--emit-into]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

SUPPORTED_TYPES = ("r_to_t", "t_to_p", "ci_from_se", "ci_vs_null", "df_vs_n", "group_shares")
LEVELS_Z = {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}
P_TOL = 0.01          # 正态近似 p 值容差（df>=30）
P_TOL_SMALL_DF = 0.015
CI_TOL = 0.05         # CI 宽度相对容差 5%


def two_sided_p_normal(z):
    """正态近似双侧 p 值。"""
    z = abs(float(z))
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def z_for_level(level):
    try:
        return LEVELS_Z.get(round(float(level), 2))
    except Exception:
        return None


def _num(x):
    """宽松取数：接受 int/float 或数字字符串。"""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.strip())
        except Exception:
            return None
    return None


def _indeterminate(detail):
    return {"computed": None, "consistent": None, "detail": detail}


def compute_check(claim):
    """纯函数：复算单条 stat_claim，返回 {computed, consistent, detail}。不写盘。"""
    if not isinstance(claim, dict):
        return _indeterminate("stat_claim 非对象")
    t = claim.get("type")
    p = claim.get("params") if isinstance(claim.get("params"), dict) else {}
    c = claim.get("claimed") if isinstance(claim.get("claimed"), dict) else {}
    try:
        if t == "r_to_t":
            r, n = _num(p.get("r")), _num(p.get("n"))
            if r is None or n is None or n < 3 or not (-1.0 < r < 1.0):
                return _indeterminate("r_to_t 需 r∈(-1,1) 且 n≥3")
            df = n - 2.0
            tval = r * math.sqrt(df / (1.0 - r * r))
            papprox = two_sided_p_normal(tval)
            computed = {"t": round(tval, 4), "df": int(df), "p_approx": round(papprox, 5)}
            oks = [True]
            notes = []
            ct = _num(c.get("t"))
            if ct is not None:
                oks.append(abs(ct - tval) <= max(0.05, 0.02 * abs(tval)))
                notes.append("t")
            cp = _num(c.get("p"))
            if cp is not None:
                oks.append(abs(cp - papprox) <= P_TOL)
                notes.append("p")
            cpm = _num(c.get("p_max"))
            if cpm is not None:
                oks.append(papprox <= cpm)
                notes.append("p_max")
            detail = "t=r*sqrt((n-2)/(1-r^2))=%.4f，正态近似 p=%.4g；核对项：%s" % (
                tval, papprox, ",".join(notes) or "无")
            return {"computed": computed, "consistent": all(oks), "detail": detail}
        if t == "t_to_p":
            tv, df = _num(p.get("t")), _num(p.get("df"))
            if tv is None:
                return _indeterminate("t_to_p 需 t")
            papprox = two_sided_p_normal(tv)
            tol = P_TOL_SMALL_DF if (df is not None and df < 30) else P_TOL
            computed = {"p_approx": round(papprox, 5), "approx": "normal",
                        "tolerance": tol}
            oks, notes = [True], []
            cp = _num(c.get("p"))
            if cp is not None:
                oks.append(abs(cp - papprox) <= tol)
                notes.append("p=%.4g" % cp)
            cpm = _num(c.get("p_max"))
            if cpm is not None:
                oks.append(papprox <= cpm)
                notes.append("p<=%.4g" % cpm)
            detail = "正态近似双侧 p(|t|=%.4g)=%.4g（%s）；核对项：%s" % (
                tv, papprox, "df=%.0f<30 容差放宽" % df if (df is not None and df < 30) else "df≥30 或未报",
                ",".join(notes) or "无")
            return {"computed": computed, "consistent": all(oks), "detail": detail}
        if t == "ci_from_se":
            se, lv = _num(p.get("se")), _num(p.get("level", 0.95))
            lo, hi = _num(c.get("ci_low")), _num(c.get("ci_high"))
            est = _num(p.get("est"))
            if se is None or se <= 0 or lo is None or hi is None:
                return _indeterminate("ci_from_se 需 se 与 claimed ci_low/ci_high")
            z = z_for_level(lv or 0.95)
            if z is None:
                return _indeterminate("level 仅支持 0.90/0.95/0.99")
            width, expect = hi - lo, 2.0 * z * se
            width_ok = abs(width - expect) <= CI_TOL * expect if expect > 0 else False
            est_ok = True
            if est is not None:
                est_ok = lo <= est <= hi
            computed = {"expected_width": round(expect, 5), "claimed_width": round(width, 5),
                        "z": z, "level": lv, "est_within_ci": est_ok}
            detail = ("95%% CI 宽应≈2*z*se=%.5f，报告宽=%.5f（相对差 %.1f%%，容差 5%%）"
                      % (expect, width, 100.0 * abs(width - expect) / expect if expect > 0 else 0))
            return {"computed": computed, "consistent": bool(width_ok and est_ok), "detail": detail}
        if t == "ci_vs_null":
            lo, hi = _num(p.get("ci_low")), _num(p.get("ci_high"))
            nv = _num(p.get("null_value", 0.0))
            sig = c.get("significant")
            if lo is None or hi is None or not isinstance(sig, bool):
                return _indeterminate("ci_vs_null 需 ci_low/ci_high 与 claimed significant(bool)")
            excludes = not (lo <= (nv or 0.0) <= hi)
            computed = {"excludes_null": excludes, "null_value": nv}
            detail = ("CI [%s, %s]%s null=%s，claimed significant=%s"
                      % (lo, hi, "排除" if excludes else "包含", nv, sig))
            return {"computed": computed, "consistent": bool(excludes == sig), "detail": detail}
        if t == "df_vs_n":
            n = _num(p.get("n"))
            design = str(p.get("design") or "unknown")
            df = _num(c.get("df"))
            if n is None or df is None or n < 2:
                return _indeterminate("df_vs_n 需 n 与 claimed df")
            expected = {"two_group": n - 2.0, "paired": n - 1.0, "one_sample": n - 1.0}.get(design)
            upper_ok = df <= n - 1.0
            if expected is None:
                consistent = upper_ok
                detail = ("设计未知，机械下界 df≤n-1=%.0f；报告 df=%.0f" % (n - 1.0, df))
            else:
                consistent = upper_ok and abs(df - expected) < 0.5
                detail = ("%s 设计期望 df=%.0f（n=%.0f），报告 df=%.0f%s"
                          % (design, expected, n, df,
                             "；df 超出 n-1，与样本量矛盾" if not upper_ok else ""))
            return {"computed": {"expected_df": expected, "n_minus_1": n - 1.0},
                    "consistent": bool(consistent), "detail": detail}
        if t == "group_shares":
            ns = p.get("group_ns")
            total = _num(c.get("total"))
            if not isinstance(ns, list) or not ns:
                return _indeterminate("group_shares 需 params.group_ns 列表")
            vals = [_num(x) for x in ns]
            if any(v is None for v in vals):
                return _indeterminate("group_ns 含非数值")
            s = sum(vals)
            oks, notes = [True], []
            if total is not None:
                oks.append(abs(s - total) < 0.5)
                notes.append("total=%.0f" % total)
            pct = c.get("percentages")
            if isinstance(pct, list) and len(pct) == len(vals):
                pv = [_num(x) for x in pct]
                if all(v is not None for v in pv):
                    oks.append(all(-0.01 <= v <= 100.01 for v in pv))
                    oks.append(abs(sum(pv) - 100.0) <= 1.0)
                    notes.append("percentages 和=%.1f" % sum(pv))
            computed = {"sum_group_ns": s, "n_groups": len(vals)}
            detail = "各组 n 求和=%.0f；核对项：%s" % (s, ",".join(notes) or "无")
            return {"computed": computed, "consistent": all(oks), "detail": detail}
        return _indeterminate("未知复算类型 %r（支持：%s）" % (t, ",".join(SUPPORTED_TYPES)))
    except Exception as e:
        return _indeterminate("复算异常: %s" % e)


def recompute_all(findings):
    """对 findings[].stat_claim 逐条复算，返回 checks 列表。"""
    checks = []
    for i, f in enumerate(findings or []):
        if not isinstance(f, dict):
            continue
        sc = f.get("stat_claim")
        if not isinstance(sc, dict):
            continue
        fid = str(f.get("finding_id") or "findings[%d]" % i)
        out = compute_check(sc)
        checks.append({"finding_id": fid, "type": sc.get("type"),
                       "claimed": sc.get("claimed"), "params": sc.get("params"),
                       "computed": out["computed"], "consistent": out["consistent"],
                       "detail": out["detail"]})
    return checks


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--out", default=None, help="复算报告落盘路径")
        ap.add_argument("--emit-into", action="store_true",
                        help="把 stat_recompute 回写 result.json 的 result.stat_recompute")
        args, _unknown = ap.parse_known_args()
    except SystemExit as e:
        if isinstance(e.code, int) and e.code not in (0, None):
            print("[stat_recompute] 参数错误/未知参数（已降级，失败路径恒 exit 0）")
        sys.exit(0)
    except Exception as e:
        print("[stat_recompute] 参数解析失败（已降级）: %s" % e)
        return 0

    res = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[stat_recompute] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % e)
        return 0
    if not isinstance(res, dict):
        print("[stat_recompute] FAIL: result.json 顶层非对象（不中断交付）")
        return 0

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    findings = [f for f in (inner.get("findings") or []) if isinstance(f, dict)]
    checks = recompute_all(findings)
    counts = {
        "claims_total": len(checks),
        "consistent": sum(1 for c in checks if c["consistent"] is True),
        "inconsistent": sum(1 for c in checks if c["consistent"] is False),
        "indeterminate": sum(1 for c in checks if c["consistent"] is None),
    }
    stat_block = {
        "tool": "scripts/stat_recompute.py",
        "supported_types": list(SUPPORTED_TYPES),
        "checks": checks,
        "counts": counts,
        "approx_note": "p 值由正态近似复算（标准库无 t 分布分位数），df<30 时容差 0.015；"
                       "CI 复算相对容差 5%；consistent=false 表示稿件报告的统计量组合与复算矛盾，"
                       "是缺陷证据而非脚本错误。",
    }
    if args.out:
        try:
            d = os.path.dirname(args.out)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(stat_block, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[stat_recompute] 报告写盘失败: %s" % e)
    if args.emit_into and isinstance(res.get("result"), dict):
        try:
            res["result"]["stat_recompute"] = stat_block
            with open(args.result, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[stat_recompute] 回写 result.json 失败: %s" % e)

    print("[stat_recompute] claims=%d（一致=%d 矛盾=%d 无法判定=%d）"
          % (counts["claims_total"], counts["consistent"], counts["inconsistent"],
             counts["indeterminate"]))
    for c in checks:
        tag = {True: "一致", False: "矛盾", None: "无法判定"}[c["consistent"]]
        print("  %s [%s] %s：%s" % (c["finding_id"], c["type"], tag, c["detail"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[stat_recompute] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
