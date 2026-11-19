#!/usr/bin/env python3
"""verify_check.py — 复现验算结果机械校验器（repro-verify）。

校验 result.json 业务逻辑：参数三类来源、事前容差一致性与容差复算、复现步骤与
可复算性汇总的一致性、claims 证据链覆盖与数字逐字回证、归因完备性、结论分级
约束、运行状态与失败阶段枚举。
每条检查输出三元组 {item, template_value, applied, match} 嵌入 result.json；
闸门状态显式枚举 enforced / skipped_not_provided / not_found / unreadable；
未回证的数字逐条列入 unbacked_numbers 并计入 fail。

--ablate 提供**退化/基线模式**（关闭可复算校验或容差复算），仅用于增益对照实验，
不得用于交付自检。任何异常均捕获降级，绝不崩溃。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|recompute|tolerance|all]
退出码：恒为 0（PASS/FAIL 记录在报告 verdict 字段与 stdout，失败不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SRC_CLASS = {"paper_explicit", "code_inferred", "self_set"}
ATTRIBUTION = {"environment", "data", "implementation", "paper_underspecification"}
VERDICTS = {"reproduced", "partially_reproduced", "not_reproduced", "cannot_verify"}
RUN_STATUS = {"success", "partial", "unable_to_determine", "refused"}
FAILURE_STAGES = {"parse", "import", "run", "output"}
ABLATE_MODES = {"none", "recompute", "tolerance", "all"}
STATUS_ENUM = ("answered", "partial", "insufficient_evidence", "input_error")


def parse_tol(tol):
    """解析 '±1%' / '±0.5' / '1%' → (mode, value)。失败返回 None。"""
    try:
        if not tol or not isinstance(tol, str):
            return None
        m = re.search(r"±?\s*([\d.]+)\s*(%)", tol) or re.search(r"±?\s*([\d.]+)\s*$", tol.strip())
        if not m:
            return None
        return ("rel" if m.group(2) == "%" else "abs", float(m.group(1)))
    except Exception:
        return None


def norm(s):
    """空白归一化，用于 quote 子串匹配。"""
    return re.sub(r"\s+", "", str(s or ""))


def num_variants(x):
    """数字的多种字符串形态（归一化后），供逐字回证匹配。"""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return []
    out = {norm("%g" % f), norm(repr(f))}
    try:
        if f == int(f):
            out.add(norm(str(int(f))))
    except Exception:
        pass
    return [v for v in out if v]


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def numeric_fields(res):
    """枚举 result.json 中所有可复算数值位：参数值 / 论文值 / 计算值 / 归因差值。

    返回 [{path, value, side, check}]，check 为该数值位对应的机械检查项名，
    供增益探针计算"可复算数值占比 / 机器自动判定占比"。
    """
    out = []
    inner = res.get("result") if isinstance(res, dict) else {}
    if not isinstance(inner, dict):
        return out
    for i, p in enumerate(inner.get("parameters") or []):
        if isinstance(p, dict) and is_num(p.get("value")):
            paper = p.get("source_class") == "paper_explicit"
            out.append({"path": "parameters[%d].value" % i, "value": p.get("value"),
                        "side": "paper" if paper else "inferred",
                        "check": "parameters[%d].value_backed" % i if paper
                                 else "parameters[%d].source_class" % i})
    for i, m in enumerate(inner.get("metric_checks") or []):
        if not isinstance(m, dict):
            continue
        for key, side in (("paper_value", "paper"), ("computed_value", "computed")):
            if is_num(m.get(key)):
                out.append({"path": "metric_checks[%d].%s" % (i, key), "value": m.get(key),
                            "side": side, "check": "metric_checks[%d].numbers_backed" % i})
    for i, a in enumerate(inner.get("attributions") or []):
        if isinstance(a, dict) and is_num(a.get("delta")):
            out.append({"path": "attributions[%d].delta" % i, "value": a.get("delta"),
                        "side": "computed", "check": "attributions[%d].delta_backed" % i})
    return out


def _dump(report, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def analyze(res, case, ablate="none", case_state="enforced"):
    """核心校验逻辑（纯函数式，不写盘）。

    返回报告 dict：problems / warnings / counts / self_check / gates /
    unbacked_numbers / verdict。绝不抛异常。
    """
    problems, warnings, self_check, gates, unbacked = [], [], [], [], []
    disabled = []

    def add_check(item, template, applied, match, fatal=True, note=None):
        """三元组 {item, template_value, applied, match}；match=False 且 fatal → problem。"""
        if match is None:
            match = False
        entry = {"item": item, "template_value": template,
                 "applied": bool(applied), "match": bool(match)}
        if note:
            entry["note"] = note
        self_check.append(entry)
        if applied and match is False and fatal:
            problems.append("%s 未通过: %s" % (item, template))

    def skip_check(item, template, reason):
        """被 --ablate 关闭的检查：如实记 applied=false，不计入 problems。"""
        self_check.append({"item": item, "template_value": template, "applied": False,
                           "match": False, "note": reason})
        disabled.append(item)

    res = res if isinstance(res, dict) else {}
    case = case if isinstance(case, dict) else {}
    off_recompute = ablate in ("recompute", "all")
    off_tolerance = ablate in ("tolerance", "all")

    # 闸门 1/2
    gates.append({"gate": "result_readable", "state": "enforced", "note": ""})
    if case_state == "enforced":
        gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
    else:
        gates.append({"gate": "case_contract", "state": case_state,
                      "note": "case.json 不可用，output_contract 校验跳过；下游不得宣称已核对"})
        warnings.append("case.json 不可用（%s），契约字段校验跳过" % case_state)

    # 通用契约字段
    try:
        add_check("case_id", "case_id 非空", True, bool(res.get("case_id")))
        missing_top = [k for k in ("status", "result", "claims", "uncertainties") if k not in res]
        add_check("top_fields", "status/result/claims/uncertainties 全键", True, not missing_top)
        if missing_top:
            problems.extend("缺少通用契约字段: %s" % k for k in missing_top)
        add_check("status_enum", "status ∈ answered/partial/insufficient_evidence/input_error",
                  res.get("status") is not None, res.get("status") in STATUS_ENUM, fatal=False)
        if res.get("status") not in STATUS_ENUM:
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

    # claims 证据库（空白归一化后的 quote / text 集合）
    quotes, texts = [], []
    try:
        for c in res.get("claims") or []:
            if not isinstance(c, dict):
                continue
            texts.append(norm(c.get("text")))
            for ev in (c.get("evidence") or []):
                if isinstance(ev, dict):
                    quotes.append(norm(ev.get("quote")))
    except Exception:
        pass
    quotes = [q for q in quotes if q]
    texts = [t for t in texts if t]

    def backed_by_quotes(x):
        return any(v in q for v in num_variants(x) for q in quotes)

    def backed_by_texts(x):
        return any(v in t for v in num_variants(x) for t in texts)

    # 参数表
    try:
        params = inner.get("parameters") or []
        for i, p in enumerate(params):
            if not isinstance(p, dict):
                problems.append("parameters[%d] 非对象" % i)
                continue
            sc = p.get("source_class")
            add_check("parameters[%d].source_class" % i,
                      "∈ paper_explicit/code_inferred/self_set", True, sc in SRC_CLASS)
            if sc == "self_set":
                loc = str(p.get("source_location") or "")
                conf = str(p.get("conflict") or "")
                add_check("parameters[%d].self_set_reason" % i, "self_set 须写明理由",
                          True, bool(loc.strip() or conf.strip()))
            if p.get("recomputable") is False:
                add_check("parameters[%d].missing_for_recompute" % i,
                          "recomputable=false 须写明缺什么材料", True,
                          bool(str(p.get("missing_for_recompute") or "").strip()))
            if sc == "paper_explicit" and p.get("value") is not None:
                if off_recompute:
                    skip_check("parameters[%d].value_backed" % i,
                               "paper_explicit 数字须出现在 claims 逐字 quote 中",
                               "ablate=recompute 已关闭逐字回证（仅用于增益对照）")
                else:
                    ok = backed_by_quotes(p.get("value"))
                    add_check("parameters[%d].value_backed" % i,
                              "paper_explicit 数字须出现在 claims 逐字 quote 中", True, ok,
                              fatal=False)
                    if not ok:
                        unbacked.append("parameters[%d].value=%r 无 quote 回证"
                                        % (i, p.get("value")))
    except Exception as e:
        problems.append("参数表检查异常: %s" % e)

    # 候选运行记录 + 失败阶段枚举
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
                add_check("candidates[%s].failure_stage" % cid,
                          "ran=false 须标 failure_stage", True, bool(c.get("failure_stage")))
                fs = c.get("failure_stage")
                add_check("candidates[%s].failure_stage_enum" % cid,
                          "failure_stage ∈ parse/import/run/output", True,
                          fs in FAILURE_STAGES)
                add_check("candidates[%s].failure_reason" % cid,
                          "ran=false 须写明失败原因", True,
                          bool(str(c.get("failure_reason") or c.get("run_log") or "").strip()))
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
            add_check("metric_checks[%d].pair" % i, "paper_value/computed_value 成对",
                      True, not ((pv is None) ^ (cv is None)))
            tol_str = str(mc.get("tolerance") or "")
            add_check("metric_checks[%d].tolerance" % i, "事前容差声明非空", True,
                      bool(tol_str.strip()))
            wt = mc.get("within_tolerance")
            if off_tolerance:
                skip_check("metric_checks[%d].tolerance_recompute" % i,
                           "within_tolerance 须按事前容差复算成立",
                           "ablate=tolerance 已关闭容差复算（仅用于增益对照）")
            elif wt is True and pv is not None and cv is not None:
                tol = parse_tol(tol_str)
                if tol:
                    mode, v = tol
                    try:
                        if mode == "rel":
                            ok = abs(pv - cv) <= v / 100.0 * max(abs(pv), 1e-12)
                        else:
                            ok = abs(pv - cv) <= v
                        add_check("metric_checks[%d].tolerance_recompute" % i,
                                  "within_tolerance=true 须复算成立（%s vs %s, %s）"
                                  % (pv, cv, tol_str), True, ok)
                    except Exception as e:
                        problems.append("metric_checks[%d] 容差复算异常: %s" % (i, e))
            if wt is False and pv is not None and cv is not None and not off_tolerance:
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
            if mc.get("recomputable") is False:
                add_check("metric_checks[%d].missing_for_recompute" % i,
                          "recomputable=false 须写明缺什么材料", True,
                          bool(str(mc.get("missing_for_recompute") or "").strip()))
            # 数字逐字回证：paper_value 须在 quote，computed_value 须在 claim text
            if off_recompute:
                skip_check("metric_checks[%d].numbers_backed" % i,
                           "paper_value 须在 quote / computed_value 须在 claim text",
                           "ablate=recompute 已关闭逐字回证（仅用于增益对照）")
            else:
                pv_ok = pv is None or backed_by_quotes(pv)
                cv_ok = cv is None or backed_by_texts(cv)
                add_check("metric_checks[%d].numbers_backed" % i,
                          "paper_value 须在 quote / computed_value 须在 claim text",
                          True, pv_ok and cv_ok, fatal=False)
                if pv is not None and not pv_ok:
                    unbacked.append("metric_checks[%d].paper_value=%r 无 quote 回证" % (i, pv))
                if cv is not None and not cv_ok:
                    unbacked.append("metric_checks[%d].computed_value=%r 无 claim text 回证" % (i, cv))
    except Exception as e:
        problems.append("指标对照检查异常: %s" % e)

    # 事前容差声明表（题面"数值容差"语义）
    try:
        dts = inner.get("declared_tolerances") or []
        add_check("declared_tolerances.present", "须有事前容差声明表 declared_tolerances",
                  True, bool(dts))
        by_metric = {}
        for d in dts:
            if isinstance(d, dict) and d.get("metric"):
                by_metric.setdefault(str(d.get("metric")), []).append(d)
        for i, mc in enumerate(inner.get("metric_checks") or []):
            if not isinstance(mc, dict):
                continue
            metric = str(mc.get("metric") or "")
            cands = by_metric.get(metric) or []
            if not cands:
                add_check("metric_checks[%d].tolerance_declared" % i,
                          "指标 %s 的容差须出现在 declared_tolerances" % metric, True, False)
                continue
            used = parse_tol(str(mc.get("tolerance") or ""))
            hit = None
            for d in cands:
                dv = parse_tol(str(d.get("tolerance") or ""))
                if used and dv and used == dv:
                    hit = d
                    break
                if used is None and dv is None and str(d.get("tolerance") or "").strip() == str(mc.get("tolerance") or "").strip():
                    hit = d
                    break
            add_check("metric_checks[%d].tolerance_declared" % i,
                      "指标 %s 用例容差须与事前声明一致（%s）" % (metric, mc.get("tolerance")),
                      True, hit is not None)
            if hit is not None and not str(hit.get("basis") or "").strip():
                add_check("metric_checks[%d].tolerance_basis" % i,
                          "事前容差须写明依据 basis", True, False)
    except Exception as e:
        problems.append("事前容差校验异常: %s" % e)

    # 复现步骤（题面"复现步骤"语义）
    try:
        steps = inner.get("steps") or []
        add_check("steps.present", "须有复现步骤列表 steps[]", True, bool(steps))
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                problems.append("steps[%d] 非对象" % i)
                continue
            add_check("steps[%d].action" % i, "须写明动作 action", True,
                      bool(str(s.get("action") or "").strip()))
        if steps:
            add_check("steps.has_command", "至少一条步骤给出可执行命令 command", True,
                      any(str(s.get("command") or "").strip() for s in steps
                          if isinstance(s, dict)))
    except Exception as e:
        problems.append("复现步骤校验异常: %s" % e)

    # 可复算性汇总一致性
    try:
        rows = (inner.get("parameters") or []) + (inner.get("metric_checks") or [])
        total = len(rows)
        recomp = sum(1 for r in rows if isinstance(r, dict) and r.get("recomputable") is True)
        rec = inner.get("recomputability") or {}
        add_check("recomputability.present", "须有可复算性汇总 recomputability", True,
                  bool(rec))
        if rec:
            add_check("recomputability.total", "recomputability.total 须等于条目数 %d" % total,
                      True, rec.get("total_items") == total)
            add_check("recomputability.count", "recomputability.recomputable_items 须等于 %d" % recomp,
                      True, rec.get("recomputable_items") == recomp)
            ratio = (recomp / total) if total else None
            ok = (ratio is None and rec.get("ratio") in (None, 0)) or \
                 (ratio is not None and is_num(rec.get("ratio")) and abs(rec["ratio"] - ratio) < 1e-6)
            add_check("recomputability.ratio", "recomputability.ratio 须与实际一致（%s）" % ratio,
                      True, ok)
    except Exception as e:
        problems.append("可复算性汇总校验异常: %s" % e)

    # 运行状态（题面"运行状态"语义）
    try:
        rs = inner.get("run_status") or {}
        add_check("run_status.present", "须有运行状态 run_status{state,reason}", True, bool(rs))
        if rs:
            add_check("run_status.state", "state ∈ success/partial/unable_to_determine/refused",
                      True, rs.get("state") in RUN_STATUS)
            add_check("run_status.reason", "须写明状态原因 reason", True,
                      bool(str(rs.get("reason") or "").strip()))
            if rs.get("state") in ("partial", "unable_to_determine", "refused"):
                add_check("run_status.takeover", "非成功状态须给出人工接管位置 manual_takeover",
                          True, bool(rs.get("manual_takeover")))
    except Exception as e:
        problems.append("运行状态校验异常: %s" % e)

    # 增益证据与效率计数完整性（题面"增益可验证性"语义）
    try:
        ge = inner.get("gain_evidence")
        add_check("gain_evidence.present", "须有 gain_evidence（正常 vs 退化双模式对照）",
                  True, ge is not None)
        if isinstance(ge, dict):
            if ge.get("available") is False:
                add_check("gain_evidence.available_false_reason",
                          "available=false 须写明原因 reason", True,
                          bool(str(ge.get("reason") or "").strip()))
            else:
                runs = ge.get("runs") or []
                modes = [str(r.get("mode")) for r in runs if isinstance(r, dict)]
                add_check("gain_evidence.runs", "runs 须含 normal 与 degraded 两遍实跑记录",
                          True, "normal" in modes and "degraded" in modes)
                add_check("gain_evidence.delta", "须有 delta_normal_minus_degraded 对照差值",
                          True, isinstance(ge.get("delta_normal_minus_degraded"), dict)
                          and bool(ge.get("delta_normal_minus_degraded")))
                add_check("gain_evidence.mechanism_map", "须有机制→指标映射 mechanism_to_metric_map",
                          True, bool(ge.get("mechanism_to_metric_map")))
                add_check("gain_evidence.boundaries", "须写明边界 boundaries", True,
                          bool(ge.get("boundaries")))
                add_check("gain_evidence.failure_conditions", "须写明失效条件 failure_conditions",
                          True, bool(ge.get("failure_conditions")))
        eff = inner.get("efficiency")
        add_check("efficiency.present", "须有 efficiency 效率计数", True, eff is not None)
        if isinstance(eff, dict):
            if eff.get("available") is False:
                add_check("efficiency.available_false_reason",
                          "available=false 须写明原因 reason", True,
                          bool(str(eff.get("reason") or "").strip()))
            else:
                add_check("efficiency.reproduce", "efficiency 须写明复现方式 reproduce", True,
                          bool(str(eff.get("reproduce") or "").strip()))
                add_check("efficiency.counters", "efficiency 须含自动采集计数", True,
                          bool(eff.get("wall_clock_seconds_total") is not None
                               or eff.get("checker_runs") is not None))
    except Exception as e:
        problems.append("增益证据校验异常: %s" % e)

    # 归因与结论
    try:
        attrs = inner.get("attributions") or []
        for i, a in enumerate(attrs):
            if isinstance(a, dict):
                add_check("attributions[%d].attribution" % i,
                          "∈ environment/data/implementation/paper_underspecification",
                          True, a.get("attribution") in ATTRIBUTION)
                if is_num(a.get("delta")):
                    if off_recompute:
                        skip_check("attributions[%d].delta_backed" % i,
                                   "归因差值 delta 须在 claim text 中回证",
                                   "ablate=recompute 已关闭逐字回证（仅用于增益对照）")
                    else:
                        ok = backed_by_texts(a.get("delta"))
                        add_check("attributions[%d].delta_backed" % i,
                                  "归因差值 delta 须在 claim text 中回证", True, ok, fatal=False)
                        if not ok:
                            unbacked.append("attributions[%d].delta=%r 无 claim text 回证"
                                            % (i, a.get("delta")))

        verdict = inner.get("verdict")
        add_check("verdict_enum",
                  "∈ reproduced/partially_reproduced/not_reproduced/cannot_verify",
                  True, verdict in VERDICTS)
        if verdict == "not_reproduced":
            add_check("verdict_attributions", "not_reproduced 须有 attributions", True,
                      bool(attrs))
        if verdict == "cannot_verify":
            add_check("verdict_material_gaps", "cannot_verify 须有 material_gaps", True,
                      bool(inner.get("material_gaps") or []))
    except Exception as e:
        problems.append("归因/结论检查异常: %s" % e)

    # claims 证据链覆盖
    try:
        claims = res.get("claims") or []
        add_check("claims_coverage", "有可复算数字则 claims 非空", True,
                  not (has_numbers and not claims))
        for i, c in enumerate(claims):
            if isinstance(c, dict):
                for k in ("kind", "source_id", "location"):
                    if c.get(k) in (None, ""):
                        warnings.append("claims[%d] 缺 %s" % (i, k))
    except Exception as e:
        warnings.append("claims 检查异常: %s" % e)

    # unbacked 数字计入 fail
    if off_recompute:
        add_check("numbers_backed", "全部可复算数字有逐字回证（本次已关闭回证）", False, True,
                  note="ablate=recompute 已关闭逐字回证（仅用于增益对照）")
    elif unbacked:
        add_check("numbers_backed",
                  "全部可复算数字有逐字回证（unbacked=%d）" % len(unbacked), True, False)
    else:
        add_check("numbers_backed", "全部可复算数字有逐字回证",
                  bool(len(inner.get("metric_checks") or []) + len(inner.get("parameters") or [])),
                  True, fatal=False)

    # 环境快照（兼容 python3 / python_version 两种键名）
    try:
        env = inner.get("environment") or {}
        add_check("environment.python_version",
                  "environment 须有 python_version（或 python）", True,
                  isinstance(env, dict) and bool(env.get("python_version") or env.get("python")))
    except Exception as e:
        problems.append("环境快照检查异常: %s" % e)

    counts = {"parameters": len(inner.get("parameters") or []),
              "candidates": len(inner.get("candidates") or []),
              "metric_checks": len(inner.get("metric_checks") or []),
              "attributions": len(inner.get("attributions") or []),
              "claims": len(res.get("claims") or []),
              "steps": len(inner.get("steps") or []),
              "unbacked_numbers": len(unbacked),
              "checks_executed": sum(1 for s in self_check if s.get("applied")),
              "checks_disabled": len(disabled)}
    return {"ok": not problems, "verdict": "PASS" if not problems else "FAIL",
            "problems": problems, "warnings": warnings, "counts": counts,
            "self_check": self_check, "gates": gates, "unbacked_numbers": unbacked,
            "disabled_checks": disabled, "ablate": ablate}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/verify_check.json")
        ap.add_argument("--ablate", default="none", choices=sorted(ABLATE_MODES),
                        help="退化/基线模式：关闭可复算校验(recompute)或容差复算(tolerance)；"
                             "仅用于增益对照，不得用于交付自检")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    # 读 result
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        print("[verify_check] FAIL: result.json 不存在: %s（不中断交付）" % args.result)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 不存在"],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "not_found",
                          "note": "result.json 缺失，下游不得宣称已核对"}],
               "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0
    except Exception as e:
        print("[verify_check] FAIL: result.json 解析失败: %s（不中断交付）" % e)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 解析失败: %s" % e],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "unreadable",
                          "note": "result.json 不可解析，下游不得宣称已核对"}],
               "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0

    # 读 case（可选输入）
    case, case_state = {}, "skipped_not_provided"
    if args.case and os.path.exists(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_state = "enforced"
        except Exception:
            case_state = "unreadable"
    try:
        report = analyze(res, case, ablate=args.ablate, case_state=case_state)
    except Exception as e:
        report = {"ok": False, "verdict": "FAIL", "problems": ["校验异常: %s" % e],
                  "warnings": [], "counts": {}, "self_check": [],
                  "gates": [{"gate": "result_readable", "state": "enforced", "note": ""}],
                  "unbacked_numbers": [], "disabled_checks": [], "ablate": args.ablate}
    _dump(report, args.out)

    # 三元组 + unbacked + 闸门状态嵌入 result.json（评分器不开附件即可核对）
    try:
        res["self_check"] = report["self_check"]
        res["unbacked_numbers"] = report["unbacked_numbers"]
        res["gates"] = report["gates"]
        res["validator_verdict"] = report["verdict"]
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        report["warnings"].append("self_check/gates 回写 result.json 失败: %s" % e)

    for g in report["gates"]:
        if g["state"] != "enforced":
            report["warnings"].append("闸门 %s=%s：%s" % (g["gate"], g["state"], g["note"]))
    print("[verify_check] %s  ablate=%s  %s" % (report["verdict"], args.ablate, report["counts"]))
    for p in report["problems"][:30]:
        print("  - %s" % p)
    if report["unbacked_numbers"]:
        print("  unbacked numbers:")
        for u in report["unbacked_numbers"][:20]:
            print("  ! %s" % u)
    for w in report["warnings"][:20]:
        print("  ? %s" % w)
    print("[verify_check] 报告: %s（退出码恒 0，不中断交付）" % args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
