#!/usr/bin/env python3
"""claim_check.py v4 — 论断核验结果校验器（摘录防改写 + 覆盖对账 + 闸门状态 + 题面对齐）。

用法：
    python3 claim_check.py --result R.json --case C.json --claims CLAIMS.json [--out report.json]

三级容错：
    L1 输入文件缺失/不可读 → 降级为仅校验 result.json 自身结构，打印 WARNING，闸门记 not_found/unreadable。
    L2 JSON 解析失败/字段类型异常 → 捕获后记入 problems，不抛 traceback。
    L3 业务规则失败（枚举/摘录/覆盖/对账/题面对齐）→ 记入 problems。
退出码：**恒为 0**。校验结论一律写进报告的 ok/problems/warnings 字段由调用方读取，
脚本不中断交付链（交付失败不得由校验器单方面阻断）；问题清单照实打印，不隐藏。

消融开关（--ablate / 环境变量 CLAIM_AUDIT_ABLATE=1）
----------------------------------------------
关掉「逐字回证」与「覆盖对账」两道闸门，用于复现**未加载本技能质量闸门**时的基线行为，
从而在同输入下量化闸门的可测效应。消融态下这两道闸门发现的内容级问题降级为 WARNING
（照实打印，不隐藏），闸门状态记 ablated_off，报告写明本次不含内容级保证。
其余结构/枚举校验照常执行。任何状态退出码均为 0（含参数错误）。

闸门状态（gates，显式枚举，写入报告）：enforced（已运行）/ skipped_not_provided（输入
缺必要内容）/ not_found（输入文件不存在）/ unreadable（输入不可读）/ ablated_off（被
消融开关关闭）。非 enforced 时报告附带 gate_note：该闸未运行，下游不得宣称已核对。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
SUBTYPES = {"fact", "comparison", "causal", "scope"}
MODIFIER_KEYS = ("comparator", "negation", "significance", "conditions")
ABLATE_ENV = "CLAIM_AUDIT_ABLATE"


class Exit0Parser(argparse.ArgumentParser):
    """参数错误也 exit 0：校验器不因调用方笔误而崩溃或阻断交付链。"""

    def error(self, message):  # noqa: D401
        print("[claim_check] FAIL 参数错误: %s" % message)
        print("[claim_check] exit=0（结论：FAIL，报告未生成）")
        raise SystemExit(0)


def ablate_requested(args) -> bool:
    """消融开关：--ablate 或环境变量 CLAIM_AUDIT_ABLATE=1/true/on。"""
    if getattr(args, "ablate", False):
        return True
    return str(os.environ.get(ABLATE_ENV, "")).strip().lower() in ("1", "true", "yes", "on")


def norm(s) -> str:
    """空白归一化：删除全部空白字符后比较（防换行/空格差异，不容忍改写）。"""
    return re.sub(r"\s+", "", str(s or ""))


def safe_load(path, problems, label):
    """返回 (数据, 是否可用, 闸门状态)。状态：enforced/not_found/unreadable。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), True, "enforced"
    except FileNotFoundError:
        problems.append("WARNING[L1] %s 不存在，跳过相关校验: %s" % (label, path))
        return None, False, "not_found"
    except Exception as e:
        problems.append("WARNING[L1] %s 读取失败，跳过相关校验: %s" % (label, e))
        return None, False, "unreadable"


def collect_paragraph_texts(case):
    texts = {}
    if not isinstance(case, dict):
        return texts
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections"):
        v = case.get(key)
        if isinstance(v, list):
            for p in v:
                if isinstance(p, dict):
                    pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                    txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                    if pid:
                        texts[pid] = txt
            break
    return texts


def wanted_claim_ids(cl):
    want = []
    items = cl if isinstance(cl, list) else (cl.get("claims") or cl.get("items") or []) if isinstance(cl, dict) else []
    for it in items:
        if isinstance(it, dict):
            cid = it.get("claim_id") or it.get("id") or it.get("claim") or it.get("text")
            if cid is not None:
                want.append(str(cid))
        elif isinstance(it, (str, int)):
            want.append(str(it))
    return want


def uncovered_ids(res):
    """从 uncertainties.uncovered 收集已登记的 claim_id。"""
    unc = res.get("uncertainties") if isinstance(res, dict) else None
    out = set()
    if isinstance(unc, dict):
        for it in unc.get("uncovered") or []:
            if isinstance(it, dict) and it.get("claim_id") is not None:
                out.add(str(it["claim_id"]))
            elif isinstance(it, str):
                out.add(it)
    return out


def sub_of(v):
    """取某条 verdict 的 subclaims 列表（仅对象元素）。"""
    if not isinstance(v, dict):
        return []
    return [s for s in (v.get("subclaims") or []) if isinstance(s, dict)]


def main() -> int:
    ap = Exit0Parser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--claims", default="/input/claims-to-verify.json")
    ap.add_argument("--out", default="/app/output/claim_check.json")
    ap.add_argument("--require-gain", action="store_true",
                    help="额外要求 result.json 含 gain_evidence（增益证据块）")
    ap.add_argument("--ablate", action="store_true",
                    help="消融基线：关闭逐字回证与覆盖对账两道闸门（等价环境变量 CLAIM_AUDIT_ABLATE=1）")
    args = ap.parse_args()
    ablated = ablate_requested(args)

    problems = []          # FAIL 级
    warnings = []          # 仅提示，不影响结论
    gates = {}             # 闸门状态显式枚举：enforced/skipped_not_provided/not_found/unreadable/ablated_off
    gate_notes = []        # 非 enforced 闸门的提示，写入报告供回填 result.json
    fatal = None           # result.json 本身不可用时的说明（仍 exit 0）
    summary = {}           # 判定分布（fatal 路径为空）

    def finish(res_payload):
        """统一落盘 + 打印 + 返回退出码（恒 0）。"""
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(res_payload, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[claim_check] WARNING 报告写出失败: %s" % e)
        for w in warnings:
            print("[claim_check] WARNING %s" % w)
        if problems:
            print("[claim_check] FAIL（%d 处）" % len(problems))
            for p in problems[:50]:
                print("  - %s" % p)
            print("[claim_check] gates: %s" % gates)
        else:
            print("[claim_check] PASS（判定分布：%s；闸门：%s）" % (summary, gates))
        for n in gate_notes:
            print("[claim_check] gate_note %s" % n)
        print("[claim_check] exit=0（校验结论见报告 ok/problems 字段，不中断交付）")
        return 0

    # ---- L2: result.json 必须可用 ----
    res = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        fatal = "result.json 不存在: %s" % args.result
    except Exception as e:
        fatal = "result.json 解析失败: %s" % e
    if fatal is None and not isinstance(res, dict):
        fatal = "result.json 顶层不是对象"
    if fatal is not None:
        problems.append(fatal)
        print("[claim_check] FAIL: %s" % fatal)
        return finish({"ok": False, "fatal": fatal, "problems": problems, "warnings": warnings,
                       "summary": {}, "gates": {}, "gate_notes": [], "exit_code": 0})

    # ---- L1: 可选输入降级（闸门状态显式登记） ----
    case, case_ok, case_state = safe_load(args.case, warnings, "case.json")
    cl, cl_ok, cl_state = safe_load(args.claims, warnings, "claims-to-verify.json")

    # ---- 契约字段 ----
    if not res.get("case_id"):
        problems.append("缺少 case_id")
    for k in ("status", "result", "claims", "uncertainties"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)

    # ---- 覆盖对账：每个 claim_id 要么有 verdict，要么登记 uncovered ----
    want = wanted_claim_ids(cl) if cl_ok else []
    gates["coverage_audit"] = ("ablated_off" if ablated else
                               ("enforced" if (cl_ok and want) else
                                (cl_state if not cl_ok else "skipped_not_provided")))
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    verdicts = inner.get("verdicts")
    if not isinstance(verdicts, list):
        problems.append("result.verdicts 缺失")
        verdicts = []
    got = {str(v.get("claim_id")) for v in verdicts if isinstance(v, dict)}
    unc_ids = uncovered_ids(res)
    if want:
        miss = [w for w in want if w not in got and w not in unc_ids]
        if miss:
            msg = "漏核验且未登记 uncovered 的 claim_id: %s" % ",".join(miss)
            # 消融基线下该闸关闭：内容级问题降级为 WARNING（照实打印，不隐藏），闸门状态已记 ablated_off
            (warnings if ablated else problems).append(
                ("WARNING[ablate] " + msg) if ablated else msg)
        if unc_ids - set(want):
            warnings.append("uncovered 中出现清单外 claim_id（请确认是否笔误）: %s"
                            % ",".join(sorted(unc_ids - set(want))))

    # ---- 证据段落文本（用于摘录核验） ----
    paras = collect_paragraph_texts(case) if case_ok else {}
    paras_n = {k: norm(v) for k, v in paras.items()}
    gates["quote_verification"] = ("ablated_off" if ablated else
                                   ("enforced" if paras else
                                    (case_state if not case_ok else "skipped_not_provided")))
    if case_ok and not paras:
        warnings.append("case.json 未解析出段落文本，摘录核验降级为跳过")

    # ---- 逐 verdict 校验 ----
    summary = {"supported": 0, "partially_supported": 0, "contradicted": 0, "insufficient_evidence": 0}
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            problems.append("verdicts[%d] 不是对象" % i)
            continue
        cid = str(v.get("claim_id") or "(?)")
        verdict = v.get("verdict")
        if verdict == "pending":
            continue
        if verdict not in VERDICTS:
            problems.append("[%s] verdict 非法: %r" % (cid, verdict))
            continue
        summary[verdict] += 1
        subs = v.get("subclaims") or []
        if not subs and verdict != "insufficient_evidence":
            problems.append("[%s] 无 subclaims（未拆解）" % cid)
        for j, s in enumerate(subs):
            if not isinstance(s, dict):
                problems.append("[%s] subclaims[%d] 不是对象" % (cid, j))
                continue
            sv = s.get("verdict")
            if sv not in VERDICTS:
                problems.append("[%s] subclaims[%d] verdict 非法" % (cid, j))
            if s.get("type") not in SUBTYPES:
                problems.append("[%s] subclaims[%d] type 非法: %r" % (cid, j, s.get("type")))
            if not (s.get("rationale") or "").strip():
                problems.append("[%s] subclaims[%d] 缺 rationale" % (cid, j))
            ev = s.get("evidence") or []
            if sv in ("supported", "partially_supported") and not ev:
                problems.append("[%s] subclaims[%d] 判 %s 却无证据" % (cid, j, sv))
            has_pos = False
            for e in ev:
                if not isinstance(e, dict):
                    problems.append("[%s] subclaims[%d] evidence 元素不是对象" % (cid, j))
                    continue
                pid = str(e.get("paragraph_id") or "")
                q = str(e.get("quote") or "")
                if not norm(q):
                    problems.append("[%s] subclaims[%d] evidence.quote 为空" % (cid, j))
                    continue
                if pid not in paras_n:
                    if paras:
                        warnings.append("[%s] subclaims[%d] paragraph_id=%s 不在段落表（跨段/表文字化，请人工核对摘录）"
                                        % (cid, j, pid))
                    continue
                # 摘录防改写核验：所有带证据的判定都要求逐字（空白归一化）子串匹配
                if norm(q) not in paras_n[pid]:
                    msg = "[%s] subclaims[%d] quote 改写/不在 %s（空白归一化匹配失败）" % (cid, j, pid)
                    # 消融基线下逐字回证闸关闭：改写摘录只报警不判 FAIL（基线真实行为：改写不被拦截）
                    (warnings if ablated else problems).append(
                        ("WARNING[ablate] " + msg) if ablated else msg)
                elif sv == "contradicted":
                    has_pos = True
            if sv == "contradicted" and not has_pos:
                problems.append("[%s] subclaims[%d] contradicted 需正面反向证据（只写'未找到'不足）" % (cid, j))

    # ---- 题面对齐：保留比较对象/否定/显著性/条件（题面"Preserve comparator, negation,
    #      significance and conditions"）——有 modifiers 字段则逐项校验键齐全 ----
    gates["modifier_preservation"] = "enforced"
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            continue
        cid = str(v.get("claim_id") or "(?)")
        for j, s in enumerate(sub_of(v)):
            mods = s.get("modifiers")
            if mods is None:
                warnings.append("[%s] subclaims[%d] 无 modifiers（比较对象/否定/显著性/条件是否保留无法机检）"
                                % (cid, j))
                continue
            if not isinstance(mods, dict):
                problems.append("[%s] subclaims[%d] modifiers 不是对象" % (cid, j))
                continue
            for mk in MODIFIER_KEYS:
                if mk not in mods:
                    problems.append("[%s] subclaims[%d] modifiers 缺字段: %s" % (cid, j, mk))

    # ---- 题面对齐：status 诚实四级 + 异常原因与人工接管位置 ----
    status = res.get("status")
    if status not in ("answered", "partial", "insufficient_evidence", "input_error"):
        problems.append("status 非法（须为 answered/partial/insufficient_evidence/input_error）: %r" % status)
    if status == "input_error" and not (res.get("error") or {}).get("reason"):
        problems.append("status=input_error 必须在 error.reason 写明异常原因")

    # ---- 题面对齐：未报告 / 无法判断 / 冲突 三类边界须显式分列 ----
    unc_obj = res.get("uncertainties") if isinstance(res.get("uncertainties"), dict) else None
    if unc_obj is None:
        problems.append("uncertainties 不是对象（未报告/无法判断/冲突需分列）")
    else:
        for k in ("uncovered", "unreported", "unverifiable", "conflicts", "human_review"):
            if k not in unc_obj:
                problems.append("uncertainties 缺字段: %s" % k)
        for c in (unc_obj.get("conflicts") or []):
            if isinstance(c, dict) and len(c.get("where") or []) < 2:
                problems.append("uncertainties.conflicts 条目需并列双方出处（where≥2）: %r" % (c.get("what"),))

    # ---- 题面对齐：证据与边界 —— 每条 verdict 需带 source_id/location 可回溯 ----
    for i, v in enumerate(verdicts):
        if not isinstance(v, dict):
            continue
        cid = str(v.get("claim_id") or "(?)")
        subs = sub_of(v)
        for j, s in enumerate(subs):
            for e in (s.get("evidence") or []):
                if isinstance(e, dict) and not (str(e.get("paragraph_id") or "").strip()
                                               or str(e.get("locator") or "").strip()):
                    problems.append("[%s] subclaims[%d] evidence 缺 paragraph_id/locator（无法回溯定位）" % (cid, j))

    # ---- 增益证据块（可选强制）：gain_evidence / efficiency 须含双臂与指标 ----
    if args.require_gain:
        gates["gain_evidence_audit"] = "enforced"
        ge = res.get("gain_evidence")
        if not isinstance(ge, dict):
            problems.append("缺少 gain_evidence（须含 arms.full / arms.ablated 与逐项指标）")
        else:
            arms = ge.get("arms") if isinstance(ge.get("arms"), dict) else {}
            for side in ("full", "ablated"):
                m = (arms.get(side) or {}).get("metrics") if isinstance(arms.get(side), dict) else None
                if not isinstance(m, dict):
                    problems.append("gain_evidence.arms.%s.metrics 缺失" % side)
                    continue
                for k in ("verdict_coverage_rate", "evidence_backverify_rate",
                          "uncovered_miss_count", "manual_review_items", "steps", "rounds"):
                    if k not in m:
                        problems.append("gain_evidence.arms.%s.metrics 缺指标: %s" % (side, k))
        eff = res.get("efficiency")
        if not isinstance(eff, dict):
            problems.append("缺少 efficiency（效率计数与复现方式）")
        else:
            for k in ("reproduce", "steps", "rounds"):
                if not eff.get(k) and eff.get(k) != 0:
                    problems.append("efficiency 缺字段: %s" % k)
    else:
        gates["gain_evidence_audit"] = "skipped_not_provided"

    rsum = inner.get("verdict_summary") or {}
    gates["verdict_summary_audit"] = "enforced" if rsum else "skipped_not_provided"
    if rsum and rsum != summary:
        problems.append("verdict_summary 与实际不符: %r vs %r" % (rsum, summary))
    if res.get("status") == "answered":
        pend = [str(v.get("claim_id")) for v in verdicts
                if isinstance(v, dict) and v.get("verdict") == "pending"]
        if pend:
            problems.append("status=answered 但存在 pending verdict: %s" % ",".join(pend))

    # 非 enforced 闸门：写 gate_note，下游不得宣称已核对
    for g, st in gates.items():
        if st != "enforced":
            gate_notes.append("gate %s = %s：该闸未运行，下游不得宣称已核对" % (g, st))

    report = {"ok": not problems, "problems": problems, "warnings": warnings,
              "summary": summary, "gates": gates, "gate_notes": gate_notes,
              "ablation": {"active": ablated,
                           "switch": "--ablate 或环境变量 CLAIM_AUDIT_ABLATE=1",
                           "disabled_gates": (["coverage_audit", "quote_verification"]
                                              if ablated else [])},
              "exit_code": 0}
    return finish(report)


if __name__ == "__main__":
    sys.exit(main())
