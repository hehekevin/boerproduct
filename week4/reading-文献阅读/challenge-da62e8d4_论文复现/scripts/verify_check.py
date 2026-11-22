#!/usr/bin/env python3
"""verify_check.py — 复现验算结果机械校验器（repro-verify）。

校验 result.json 业务逻辑：参数三类来源、容差一致性、claims 证据链覆盖、
归因完备性、结论分级约束、recomputable 标注。任何异常均捕获降级，绝不崩溃。

用法：
    python verify_check.py --result /app/output/result.json --case /input/case.json [--out /app/work/verify_check.json]
退出码：0=通过（可有 warnings）；1=存在 problems。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

SRC_CLASS = {"paper_explicit", "code_inferred", "self_set"}
ATTRIBUTION = {"environment", "data", "implementation", "paper_underspecification"}
VERDICTS = {"reproduced", "partially_reproduced", "not_reproduced", "cannot_verify"}


def parse_tol(tol):
    """解析 '±1%' / '±0.5' / '1%' → (mode, value)。失败返回 None。"""
    try:
        if not tol or not isinstance(tol, str):
            return None
        m = re.match(r"^\s*±?\s*([\d.]+)\s*(%?)\s*$", tol.strip())
        if not m:
            return None
        return ("rel" if m.group(2) == "%" else "abs", float(m.group(1)))
    except Exception:
        return None


def _dump(problems, warnings, out_path, counts=None):
    try:
        report = {"ok": not problems, "problems": problems, "warnings": warnings,
                  "counts": counts or {}}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/verify_check.json")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败: %s" % e)
        return 1

    problems, warnings = [], []
    res = {}

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        problems.append("result.json 不存在: %s" % args.result)
        _dump(problems, warnings, args.out)
        return 1
    except Exception as e:
        problems.append("result.json 解析失败: %s" % e)
        _dump(problems, warnings, args.out)
        return 1

    # 通用契约字段
    try:
        if not res.get("case_id"):
            problems.append("缺少 case_id")
        for k in ("status", "result", "claims", "uncertainties"):
            if k not in res:
                problems.append("缺少通用契约字段: %s" % k)
        if res.get("status") not in ("answered", "partial", "insufficient_evidence",
                                     "input_error", None):
            warnings.append("status 非约定枚举: %r" % res.get("status"))
    except Exception as e:
        problems.append("契约字段检查异常: %s" % e)

    inner = {}
    try:
        inner = res.get("result") if isinstance(res.get("result"), dict) else {}
        if not inner:
            problems.append("result 为空或非对象")
    except Exception:
        inner = {}

    # 参数表
    try:
        params = inner.get("parameters") or []
        for i, p in enumerate(params):
            if not isinstance(p, dict):
                problems.append("parameters[%d] 非对象" % i)
                continue
            sc = p.get("source_class")
            if sc not in SRC_CLASS:
                problems.append("parameters[%d] source_class 非法: %r" % (i, sc))
            if sc == "self_set":
                loc = str(p.get("source_location") or "")
                conf = str(p.get("conflict") or "")
                if not loc.strip() and not conf.strip():
                    problems.append("parameters[%d] self_set 缺理由" % i)
            if p.get("recomputable") is False and not str(p.get("missing_for_recompute") or "").strip():
                problems.append("parameters[%d] recomputable=false 但缺 missing_for_recompute" % i)
    except Exception as e:
        problems.append("参数表检查异常: %s" % e)

    # 候选运行记录
    ran_ids = set()
    try:
        for c in inner.get("candidates") or []:
            if not isinstance(c, dict):
                continue
            cid = str(c.get("candidate_id"))
            if c.get("ran"):
                ran_ids.add(cid)
                if not str(c.get("run_log") or "").strip():
                    warnings.append("候选 %s ran=true 但 run_log 为空" % cid)
            else:
                if not c.get("failure_stage"):
                    problems.append("候选 %s ran=false 但缺 failure_stage" % cid)
    except Exception as e:
        problems.append("候选检查异常: %s" % e)

    # 指标对照
    has_numbers = False
    try:
        mcs = inner.get("metric_checks") or []
        for i, mc in enumerate(mcs):
            if not isinstance(mc, dict):
                continue
            pv, cv = mc.get("paper_value"), mc.get("computed_value")
            if pv is not None or cv is not None:
                has_numbers = True
            if (pv is None) ^ (cv is None):
                problems.append("metric_checks[%d] paper_value/computed_value 只填一个" % i)
            tol_str = str(mc.get("tolerance") or "")
            if not tol_str.strip():
                problems.append("metric_checks[%d] 缺事前容差声明" % i)
            wt = mc.get("within_tolerance")
            if wt is True and pv is not None and cv is not None:
                tol = parse_tol(tol_str)
                if tol:
                    mode, v = tol
                    try:
                        if mode == "rel":
                            ok = abs(pv - cv) <= v / 100.0 * max(abs(pv), 1e-12)
                        else:
                            ok = abs(pv - cv) <= v
                        if not ok:
                            problems.append("metric_checks[%d] within_tolerance=true 但复算超容差 (%s vs %s, %s)"
                                            % (i, pv, cv, tol_str))
                    except Exception as e:
                        problems.append("metric_checks[%d] 容差复算异常: %s" % (i, e))
            if wt is False and pv is not None and cv is not None:
                tol = parse_tol(tol_str)
                if tol:
                    mode, v = tol
                    diff = abs(pv - cv)
                    ok = (diff <= v / 100.0 * max(abs(pv), 1e-12)) if mode == "rel" else (diff <= v)
                    if ok:
                        warnings.append("metric_checks[%d] within_tolerance=false 但复算在容差内，请复核" % i)
            cid = str(mc.get("candidate_id") or "")
            if cid and cid not in ran_ids and cv is not None:
                problems.append("metric_checks[%d] 候选 %s 未运行却有 computed_value" % (i, cid))
            if mc.get("recomputable") is False and not str(mc.get("missing_for_recompute") or "").strip():
                problems.append("metric_checks[%d] recomputable=false 但缺 missing_for_recompute" % i)
    except Exception as e:
        problems.append("指标对照检查异常: %s" % e)

    # 归因与结论
    try:
        attrs = inner.get("attributions") or []
        for i, a in enumerate(attrs):
            if isinstance(a, dict) and a.get("attribution") not in ATTRIBUTION:
                problems.append("attributions[%d] attribution 非法: %r" % (i, a.get("attribution")))

        verdict = inner.get("verdict")
        if verdict not in VERDICTS:
            problems.append("verdict 非法/缺失: %r" % verdict)
        if verdict == "not_reproduced" and not attrs:
            problems.append("verdict=not_reproduced 但 attributions 为空")
        if verdict == "cannot_verify" and not (inner.get("material_gaps") or []):
            problems.append("verdict=cannot_verify 但 material_gaps 为空")
    except Exception as e:
        problems.append("归因/结论检查异常: %s" % e)

    # claims 证据链覆盖
    try:
        claims = res.get("claims") or []
        n_params = len(inner.get("parameters") or [])
        if has_numbers and not claims:
            problems.append("存在可复算数字（metric_checks）但 claims 为空")
        elif n_params + len(inner.get("metric_checks") or []) > 0 and claims:
            covered = sum(1 for c in claims if isinstance(c, dict)
                          and str(c.get("evidence") or "").strip() or (c.get("evidence") is not None))
            if covered < len(claims):
                warnings.append("部分 claim 缺 evidence 字段内容")
        for i, c in enumerate(claims):
            if isinstance(c, dict):
                for k in ("kind", "source_id", "location"):
                    if c.get(k) in (None, ""):
                        warnings.append("claims[%d] 缺 %s" % (i, k))
    except Exception as e:
        warnings.append("claims 检查异常: %s" % e)

    # 环境快照（兼容 python / python_version 两种键名，修复 r2 误报回归）
    try:
        env = inner.get("environment") or {}
        if not isinstance(env, dict) or not (env.get("python_version") or env.get("python")):
            problems.append("environment 缺 python_version（或 python）")
    except Exception as e:
        problems.append("环境快照检查异常: %s" % e)

    counts = {"parameters": len(inner.get("parameters") or []),
              "candidates": len(inner.get("candidates") or []),
              "metric_checks": len(inner.get("metric_checks") or []),
              "attributions": len(inner.get("attributions") or []),
              "claims": len(res.get("claims") or [])}
    _dump(problems, warnings, args.out, counts)

    if problems:
        print("[verify_check] FAIL（%d 处）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        for w in warnings[:20]:
            print("  ? %s" % w)
        return 1
    print("[verify_check] PASS  %s" % counts)
    for w in warnings[:20]:
        print("  ? %s" % w)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(1)
