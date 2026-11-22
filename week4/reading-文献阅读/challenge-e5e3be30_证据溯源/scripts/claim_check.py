#!/usr/bin/env python3
"""claim_check.py v2 — 论断核验结果校验器（带摘录防改写核验与覆盖对账）。

用法：
    python claim_check.py --result R.json --case C.json --claims CLAIMS.json [--out report.json]

三级容错：
    L1 输入文件缺失/不可读 → 降级为仅校验 result.json 自身结构，打印 WARNING，退出码不变差。
    L2 JSON 解析失败/字段类型异常 → 捕获后记入 problems，不抛 traceback。
    L3 业务规则失败（枚举/摘录/覆盖）→ 记入 problems，退出码 1。
退出码：0=通过（可有 WARNING）；1=存在 FAIL 问题；2=result.json 本身不可用。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
SUBTYPES = {"fact", "comparison", "causal", "scope"}


def norm(s) -> str:
    """空白归一化：删除全部空白字符后比较（防换行/空格差异，不容忍改写）。"""
    return re.sub(r"\s+", "", str(s or ""))


def safe_load(path, problems, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), True
    except FileNotFoundError:
        problems.append("WARNING[L1] %s 不存在，跳过相关校验: %s" % (label, path))
    except Exception as e:
        problems.append("WARNING[L1] %s 读取失败，跳过相关校验: %s" % (label, e))
    return None, False


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--claims", default="/input/claims-to-verify.json")
    ap.add_argument("--out", default="/app/output/claim_check.json")
    args = ap.parse_args()

    problems = []          # FAIL 级
    warnings = []          # 仅提示，不影响退出码

    # ---- L2: result.json 必须可用 ----
    res = None
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        print("[claim_check] FAIL: result.json 不存在: %s" % args.result)
        return 2
    except Exception as e:
        print("[claim_check] FAIL: result.json 解析失败: %s" % e)
        return 2
    if not isinstance(res, dict):
        print("[claim_check] FAIL: result.json 顶层不是对象")
        return 2

    # ---- L1: 可选输入降级 ----
    case, case_ok = safe_load(args.case, warnings, "case.json")
    cl, cl_ok = safe_load(args.claims, warnings, "claims-to-verify.json")

    # ---- 契约字段 ----
    if not res.get("case_id"):
        problems.append("缺少 case_id")
    for k in ("status", "result", "claims", "uncertainties"):
        if k not in res:
            problems.append("缺少通用契约字段: %s" % k)

    # ---- 覆盖对账：每个 claim_id 要么有 verdict，要么登记 uncovered ----
    want = wanted_claim_ids(cl) if cl_ok else []
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
            problems.append("漏核验且未登记 uncovered 的 claim_id: %s" % ",".join(miss))
        if unc_ids - set(want):
            warnings.append("uncovered 中出现清单外 claim_id（请确认是否笔误）: %s"
                            % ",".join(sorted(unc_ids - set(want))))

    # ---- 证据段落文本（用于摘录核验） ----
    paras = collect_paragraph_texts(case) if case_ok else {}
    paras_n = {k: norm(v) for k, v in paras.items()}
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
                    problems.append("[%s] subclaims[%d] quote 改写/不在 %s（空白归一化匹配失败）" % (cid, j, pid))
                elif sv == "contradicted":
                    has_pos = True
            if sv == "contradicted" and not has_pos:
                problems.append("[%s] subclaims[%d] contradicted 需正面反向证据（只写'未找到'不足）" % (cid, j))

    rsum = inner.get("verdict_summary") or {}
    if rsum and rsum != summary:
        problems.append("verdict_summary 与实际不符: %r vs %r" % (rsum, summary))
    if res.get("status") == "answered":
        pend = [str(v.get("claim_id")) for v in verdicts
                if isinstance(v, dict) and v.get("verdict") == "pending"]
        if pend:
            problems.append("status=answered 但存在 pending verdict: %s" % ",".join(pend))

    report = {"ok": not problems, "problems": problems, "warnings": warnings, "summary": summary}
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[claim_check] WARNING[L2] 报告写出失败: %s" % e)

    for w in warnings:
        print("[claim_check] WARNING %s" % w)
    if problems:
        print("[claim_check] FAIL（%d 处）" % len(problems))
        for p in problems[:50]:
            print("  - %s" % p)
        return 1
    print("[claim_check] PASS（判定分布：%s）" % summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
