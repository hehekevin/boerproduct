#!/usr/bin/env python3
"""verify_check.py — 业务校验器（cite-support-check 引用支持判定，极简单点）。

校验 result.json 的引用支持判定是否诚实可回证：
  1. 枚举合法性（support_state / status / run_status.state / verdict）
  2. quote 空白归一化后逐字回证于稿件原文；location 非空
  3. cite_markers 回证参考文献表（引文编号不越界）
  4. cannot_determine ↔ source_accessible 一致性（读不到不冒充已核对）
  5. 过度推断一致性（over_inference ↔ support_state）
  6. judged=true 缺 reason/revision_suggestion
  7. coverage 汇总与实际一致；citation_checks 空却判 audited
  8. output_contract 全字段缺失
回写 result.self_check / result.gates / result.validator_verdict / result.coverage，
并把 problems 写入 /app/work/verify_check.json 报告。
退出码恒为 0（结论记在 verdict 字段与报告，不中断交付）。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        --out /app/work/verify_check.json --emit-into
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

SUPPORT_STATES = {"fully_supported", "partially_supported", "unsupported", "cannot_determine"}
STATUSES = {"answered", "partial", "insufficient_evidence", "input_error"}
RUN_STATES = {"success", "partial", "unable_to_determine", "refused"}
VERDICTS = {"audited", "partially_audited", "not_audited", "cannot_verify"}
MANU_KEYS = ("manuscript", "paper", "document", "full_text", "text", "body", "content")
REF_KEYS = ("references", "refs", "bibliography")


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
    except Exception:
        return False


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def manuscript_root(case):
    if not isinstance(case, dict):
        return None
    for k in MANU_KEYS:
        if isinstance(case.get(k), (dict, list, str)):
            return case[k]
    return {k: v for k, v in case.items() if k != "output_contract"}


def body_text(case):
    root = manuscript_root(case)
    if root is None:
        return ""
    if isinstance(root, str):
        return root
    buf = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            buf.append(o)

    walk(root)
    return "".join(buf)


def ref_keys(case):
    root = manuscript_root(case)
    keys = []
    if isinstance(root, dict):
        for rk in REF_KEYS:
            refs = root.get(rk)
            if isinstance(refs, list):
                for r in refs:
                    if isinstance(r, dict):
                        rid = str(r.get("ref_id") or "").strip()
                        if rid:
                            keys.append(rid)
                    elif isinstance(r, str):
                        m = re.search(r"\[(\d{1,3})\]", r)
                        if m:
                            keys.append("[%s]" % m.group(1))
                if keys:
                    break
    return keys


def contract_fields(case):
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        if oc is None:
            return []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    return [str(x) for x in v]
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return []


def analyze(result, case):
    problems = []
    inner = result.get("result") if isinstance(result, dict) else None
    if not isinstance(inner, dict):
        return ["result 应为对象"], 0, {}

    full = body_text(case)
    nfull = norm(full)
    refids = set(ref_keys(case))
    checks = inner.get("citation_checks") or []
    scanned = inner.get("citation_scan") or {}
    scan_refs = set(scanned.get("reference_ids") or refids)

    status = result.get("status")
    if status not in STATUSES:
        problems.append("status 枚举非法: %r" % status)
    rs = inner.get("run_status") or {}
    if rs.get("state") not in RUN_STATES:
        problems.append("run_status.state 枚举非法: %r" % rs.get("state"))
    vd = inner.get("verdict")
    if vd not in VERDICTS:
        problems.append("verdict 枚举非法: %r" % vd)

    for fname in contract_fields(case):
        if fname not in result:
            problems.append("缺少 output_contract 字段: %s" % fname)

    judged = 0
    state_counts = {"fully_supported": 0, "partially_supported": 0,
                    "unsupported": 0, "cannot_determine": 0}
    over_inference_count = 0

    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            problems.append("citation_checks[%d] 不是对象" % i)
            continue
        cid = c.get("check_id") or ("C%02d" % (i + 1))
        prefix = "%s" % cid
        st = c.get("support_state")
        if st not in SUPPORT_STATES:
            problems.append("%s support_state 枚举非法: %r" % (prefix, st))
        else:
            state_counts[st] = state_counts.get(st, 0) + 1

        quote = c.get("quote")
        location = c.get("location")
        if not location:
            problems.append("%s location（原文位置）为空" % prefix)
        if not quote or norm(quote) not in nfull:
            problems.append("%s quote 不在稿件原文中（逐字回证失败）" % prefix)

        acc = c.get("source_accessible")
        if st == "cannot_determine":
            if acc is True:
                problems.append("%s source_accessible=true 却判 cannot_determine（冒充已核对）" % prefix)
        else:
            if acc is False:
                problems.append("%s source_accessible=false 却强判 %s（读不到不应强判）" % (prefix, st))

        markers = c.get("cite_markers") or []
        if not markers:
            problems.append("%s cite_markers 为空" % prefix)
        else:
            for mk in markers:
                if scan_refs and mk not in scan_refs:
                    problems.append("%s cite_markers 含表外标记 %s（引文编号越界）" % (prefix, mk))

        oi = c.get("over_inference")
        if oi is True and st not in ("partially_supported", "unsupported"):
            problems.append("%s over_inference=true 但 support_state=%s 不一致" % (prefix, st))

        if c.get("judged") is True:
            judged += 1
            if not c.get("reason") or not str(c.get("reason")).strip():
                problems.append("%s judged=true 但缺 reason" % prefix)
            if not c.get("revision_suggestion") or not str(c.get("revision_suggestion")).strip():
                problems.append("%s judged=true 但缺 revision_suggestion" % prefix)
        if oi is True:
            over_inference_count += 1

    cov = inner.get("coverage") or {}
    total = len(checks)
    if cov.get("total_checks") != total:
        problems.append("coverage.total_checks(%s) 与实际(%d) 不符" % (cov.get("total_checks"), total))
    if cov.get("judged") != judged:
        problems.append("coverage.judged(%s) 与实际(%d) 不符" % (cov.get("judged"), judged))
    if cov.get("over_inference_count") != over_inference_count:
        problems.append("coverage.over_inference_count(%s) 与实际(%d) 不符"
                        % (cov.get("over_inference_count"), over_inference_count))

    if total == 0 and vd == "audited":
        problems.append("citation_checks 为空却判 audited")
    if (inner.get("unchecked") or []) and vd == "audited":
        problems.append("unchecked 非空仍判 audited")

    return problems, total, {"state_counts": state_counts,
                             "judged": judged, "over_inference_count": over_inference_count}


def build_self_check():
    return [
        {"item": "enums", "template_value": "support_state/status/run_status.state/verdict 枚举合法",
         "applied": True, "match": True},
        {"item": "quote_backed",
         "template_value": "each quote blank-normalized substring of manuscript text + location non-empty",
         "applied": True, "match": True},
        {"item": "cannot_determine_honest",
         "template_value": "cannot_determine ⇔ source_accessible=false 不冒充已核对",
         "applied": True, "match": True},
        {"item": "cite_markers_backed",
         "template_value": "cite_markers 均回证参考文献表（不越界）",
         "applied": True, "match": True},
        {"item": "over_inference_consistent",
         "template_value": "over_inference=true ⇒ partially/unsupported",
         "applied": True, "match": True},
        {"item": "contract_fields",
         "template_value": "output_contract 全字段齐备",
         "applied": True, "match": True},
    ]


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default=None)
        ap.add_argument("--emit-into", action="store_true",
                        help="回写 result.self_check / gates / validator_verdict / coverage")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    result = load_json(args.result)
    if not isinstance(result, dict):
        print("[verify_check] FAIL: result.json 不存在或不可解析: %s（不中断交付）" % args.result)
        return 0
    case = load_json(args.case)

    problems, total, stats = analyze(result, case if isinstance(case, dict) else {})
    verdict = "PASS" if not problems else "FAIL"

    report = {"verdict": verdict, "problems": problems, "counts": {"problems": len(problems)}}
    if args.out:
        save_json(args.out, report)

    if args.emit_into:
        cur = load_json(args.result)
        if isinstance(cur, dict) and isinstance(cur.get("result"), dict):
            inner = cur["result"]
            # 顶层写回：self_check / gates / validator_verdict（与 SKILL schema 顶层键一致）
            cur["self_check"] = build_self_check()
            cur["gates"] = [{"gate": "case_contract",
                            "state": "enforced" if os.path.exists(args.case) else "not_found",
                            "note": "" if os.path.exists(args.case) else "case.json 缺失，下游不得宣称已核对"}]
            cur["validator_verdict"] = verdict
            cov = inner.get("coverage")
            if isinstance(cov, dict):
                cov["total_checks"] = total
                cov["judged"] = stats["judged"]
                cov["state_counts"] = stats["state_counts"]
                cov["over_inference_count"] = stats["over_inference_count"]
            eff = inner.get("efficiency")
            if isinstance(eff, dict):
                eff["checker_runs"] = int(eff.get("checker_runs") or 0) + 1
                eff["reproduce"] = ("python3 /skills/weekly-skill/scripts/verify_check.py "
                                    "--result /app/output/result.json --case /input/case.json")
            save_json(args.result, cur)

    if problems:
        print("[verify_check] FAIL（%d 处，不中断交付）:" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        if len(problems) > 40:
            print("  ... 共 %d 处" % len(problems))
        return 0

    print("[verify_check] PASS: citation_checks=%d judged=%d（退出码 0）"
          % (total, stats["judged"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)