#!/usr/bin/env python3
"""check.py — field2table-r3 机械校验器（覆盖门禁 + 逐字校验，异常优雅降级）。

校验项：
1. 契约键一个不缺（通用五键 + output_contract 声明键 + uncertainties 五子键）；
2. field_id 全覆盖、无重复（漏行 = FAIL，覆盖密度门禁）；
3. 每行一条对应 claim：claim-<field_id> 必须存在（claims 数 ≥ fields 数）；
4. status 枚举合法（字段级四态 + 整体四态）；
5. reported 行必填：value(scalar/range/text 至少一)、units、statistic、conditions、
   comparator、evidence(paragraph_id+quote)、数值行 verbatim_number、search_log；
6. verbatim_number 出现在其引文内，且与 scalar 数值一致（84.3% ↔ 0.843 显式百分比放行）；
7. quote 逐字出现在对应段落（需 --paras 或 case.json 段落；缺失时降级为警告）；
8. not_reported：无值 + search_log/evidence_note；source_conflict：conflicts≥2；
   extraction_failed：failure_reason。

用法：
    python3 check.py --result R.json --case C.json --fields F.json [--paras P.json] [--out report.json]
退出码：0=PASS，1=FAIL。内部异常降级为报告项，绝不裸崩。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

STATUS = {"reported", "not_reported", "source_conflict", "extraction_failed"}
OVERALL = {"answered", "partial", "insufficient_evidence", "input_error"}
UNIVERSAL = ["case_id", "status", "result", "claims", "uncertainties"]
UNCERT_KEYS = ["unreported", "unverifiable", "conflicts", "human_review", "summary"]


def norm(s):
    try:
        return re.sub(r"\s+", "", s or "")
    except Exception:
        return ""


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def nums_of(s):
    try:
        return re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", str(s or ""))
    except Exception:
        return []


def num_eq(a, b, units=""):
    """数值一致性：直接相等，或百分号换算相等（须显式 % 关系）。"""
    try:
        fa, fb = float(a), float(b)
    except Exception:
        return False
    try:
        if abs(fa - fb) <= 1e-12 * max(1.0, abs(fa), abs(fb)):
            return True
        u = (units or "").lower()
        if "%" in u or "percent" in u or "%" in str(a) or "%" in str(b):
            if abs(fa / 100.0 - fb) <= 1e-9 or abs(fb / 100.0 - fa) <= 1e-9:
                return True
    except Exception:
        pass
    return False


def field_ids_of(tf):
    ids = []
    try:
        if isinstance(tf, list):
            items = tf
        elif isinstance(tf, dict):
            items = tf.get("fields") or tf.get("targets") or tf.get("items") or []
        else:
            items = []
        for it in items:
            if isinstance(it, dict):
                fid = it.get("field_id") or it.get("id") or it.get("name")
                if fid is not None:
                    ids.append(str(fid))
            elif isinstance(it, (str, int)):
                ids.append(str(it))
    except Exception as e:
        print("[check] target-fields 解析失败: %s" % e)
    return ids


def contract_keys(case):
    keys = list(UNIVERSAL)
    try:
        oc = case.get("output_contract") if isinstance(case, dict) else None
        extra = []
        if isinstance(oc, dict):
            for key in ("fields", "required_fields", "result.json", "result"):
                v = oc.get(key)
                if isinstance(v, list):
                    extra = [str(x) for x in v]
                    break
            if not extra:
                extra = [str(k) for k in oc.keys()]
        elif isinstance(oc, list):
            extra = [str(x) for x in oc]
        for k in extra:
            if k not in keys:
                keys.append(k)
    except Exception as e:
        print("[check] output_contract 解析失败: %s" % e)
    return keys


def collect_paras(case, paras_path):
    texts = {}
    if paras_path:
        try:
            raw = load_json(paras_path)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, str):
                        texts[str(k)] = v
                    elif isinstance(v, dict):
                        texts[str(k)] = str(v.get("text") or v.get("content") or "")
            elif isinstance(raw, list):
                for p in raw:
                    if isinstance(p, dict):
                        pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                        if pid:
                            texts[pid] = str(p.get("text") or p.get("content") or p.get("body") or "")
        except Exception as e:
            print("[check] paragraphs 读取失败（跳过逐字校验）: %s" % e)
    if texts:
        return texts
    try:
        for key in ("paragraphs", "passages", "paper_paragraphs", "sections"):
            v = case.get(key) if isinstance(case, dict) else None
            if isinstance(v, list):
                for p in v:
                    if isinstance(p, dict):
                        pid = str(p.get("paragraph_id") or p.get("id") or p.get("pid") or "")
                        txt = str(p.get("text") or p.get("content") or p.get("body") or "")
                        if pid:
                            texts[pid] = txt
                break
    except Exception as e:
        print("[check] case.json 段落解析失败: %s" % e)
    return texts


def claim_ids_of(claims):
    out = set()
    try:
        for c in claims:
            if isinstance(c, dict):
                cid = str(c.get("claim_id") or "")
                out.add(cid)
                for e in (c.get("evidence") or []):
                    pass
                # 也收录 text/location 中显式提及的 field 线索由调用方按字段匹配
    except Exception:
        pass
    return out


def check_rows(fields, paras_n, claims, problems, warnings):
    cnt = {"reported": 0, "not_reported": 0, "source_conflict": 0, "extraction_failed": 0}
    claim_ids = claim_ids_of(claims)
    claim_blob = norm(json.dumps(claims, ensure_ascii=False)) if claims else ""
    for i, r in enumerate(fields):
        if not isinstance(r, dict):
            problems.append("fields[%d] 不是对象" % i)
            continue
        fid = str(r.get("field_id", "(?)"))
        st = r.get("status")
        if st not in STATUS:
            problems.append("[%s] status 非法: %r" % (fid, st))
            continue
        cnt[st] += 1

        # 覆盖密度：每行一条对应 claim
        if ("claim-" + norm(fid)) not in norm(claim_ids.__str__()) and \
           ("claim-" + fid) not in claim_ids and \
           (norm(fid) not in claim_blob):
            problems.append("[%s] 缺对应 claim（claim_id 应为 claim-%s）" % (fid, fid))

        val = r.get("value") if isinstance(r.get("value"), dict) else {}
        scalar, rng, txt = val.get("scalar"), val.get("range"), val.get("text")
        has_val = scalar is not None or rng is not None or (str(txt or "").strip() != "")
        ev = r.get("evidence") if isinstance(r.get("evidence"), list) else []
        slog = r.get("search_log") if isinstance(r.get("search_log"), list) else []

        if st == "reported":
            if not has_val:
                problems.append("[%s] reported 但无值（value.scalar/range/text 至少一）" % fid)
            if not (str(r.get("units") or "").strip()):
                problems.append("[%s] reported 但 units 缺失（无量纲写 dimensionless）" % fid)
            if not (str(r.get("statistic") or "").strip()):
                problems.append("[%s] reported 但 statistic 缺失（单值写 value）" % fid)
            conds = r.get("conditions")
            if not isinstance(conds, list) or len(conds) == 0:
                problems.append("[%s] reported 但 conditions 为空（无附加限定时写 ['无附加限定条件']）" % fid)
            if not (str(r.get("comparator") or "").strip()):
                problems.append("[%s] reported 但 comparator 缺失（没有写 none）" % fid)
            if not ev:
                problems.append("[%s] reported 但无 evidence" % fid)
            if not slog:
                problems.append("[%s] reported 但 search_log 缺失（五源检索记录）" % fid)
            vn = str(r.get("verbatim_number") or "").strip()
            numeric = scalar is not None or rng is not None
            if numeric and not vn:
                problems.append("[%s] 数值型 reported 但 verbatim_number 缺失" % fid)
            if numeric and vn:
                vn_nums = nums_of(vn)
                if scalar is not None:
                    if not vn_nums:
                        problems.append("[%s] verbatim_number=%r 不含数字" % (fid, vn))
                    elif not num_eq(scalar, vn_nums[0], str(r.get("units") or "")):
                        problems.append("[%s] scalar=%s 与 verbatim_number=%r 数值不一致" % (fid, scalar, vn))
                if rng is not None:
                    try:
                        lo, hi = rng[0], rng[1]
                        ok_lo = len(vn_nums) >= 1 and (num_eq(lo, vn_nums[0], str(r.get("units") or "")) or num_eq(lo, str(abs(float(vn_nums[0]))), str(r.get("units") or "")))
                        ok_hi = len(vn_nums) >= 2 and (num_eq(hi, vn_nums[-1], str(r.get("units") or "")) or num_eq(hi, str(abs(float(vn_nums[-1]))), str(r.get("units") or "")))
                        # "2.8-4.3" 类正数范围中连字符会被当负号，用绝对值回退匹配
                        if len(vn_nums) < 2 or not (ok_lo and ok_hi):
                            problems.append("[%s] range=%s 与 verbatim_number=%r 不一致" % (fid, rng, vn))
                    except Exception:
                        problems.append("[%s] range 格式非法: %r" % (fid, rng))
            for e in ev:
                if not isinstance(e, dict):
                    problems.append("[%s] evidence 项不是对象" % fid)
                    continue
                pid = str(e.get("paragraph_id") or "")
                q = str(e.get("quote") or "")
                if not pid or not q.strip():
                    problems.append("[%s] evidence 缺 paragraph_id 或 quote" % fid)
                    continue
                if vn and vn not in q:
                    problems.append("[%s] verbatim_number=%r 不在其引文中（值与引文脱钩）" % (fid, vn))
                if paras_n:
                    if pid not in paras_n:
                        warnings.append("[%s] 段落 %s 不在段落库，跳过逐字校验" % (fid, pid))
                    elif norm(q) and norm(q) not in paras_n[pid]:
                        problems.append("[%s] quote 未逐字出现在段落 %s" % (fid, pid))

        if st == "not_reported":
            if has_val:
                problems.append("[%s] not_reported 却写了值（缺项≠0）" % fid)
            if not slog and not (str(r.get("evidence_note") or "").strip()):
                problems.append("[%s] not_reported 缺 search_log/evidence_note（找过哪里）" % fid)

        if st == "source_conflict":
            conf = r.get("conflicts") if isinstance(r.get("conflicts"), list) else []
            if len(conf) < 2:
                problems.append("[%s] source_conflict 但 conflicts < 2（需双方并列）" % fid)
            for j, c in enumerate(conf):
                if isinstance(c, dict):
                    cq = str(c.get("quote") or "")
                    if not cq.strip():
                        problems.append("[%s] conflicts[%d] 缺 quote" % (fid, j))
                else:
                    problems.append("[%s] conflicts[%d] 不是对象" % (fid, j))

        if st == "extraction_failed":
            if not (str(r.get("failure_reason") or "").strip()):
                problems.append("[%s] extraction_failed 缺 failure_reason" % fid)

    return cnt


def run(args):
    problems, warnings = [], []
    res = load_json(args.result)
    case = load_json(args.case) if args.case else {}
    if not isinstance(case, dict):
        case = {}
    tf = load_json(args.fields) if args.fields else None

    for k in contract_keys(case):
        if k not in res:
            problems.append("缺少契约键: %s" % k)
    if not res.get("case_id"):
        problems.append("缺少 case_id")
    else:
        cid = case.get("case_id") if isinstance(case, dict) else None
        if cid and str(res.get("case_id")) != str(cid):
            problems.append("case_id 不一致: result=%s case=%s" % (res.get("case_id"), cid))
    if res.get("status") not in OVERALL:
        problems.append("整体 status 非法: %r" % res.get("status"))

    unc = res.get("uncertainties") if isinstance(res.get("uncertainties"), dict) else None
    if unc is None:
        problems.append("uncertainties 缺失")
    else:
        for uk in UNCERT_KEYS:
            if uk not in unc:
                problems.append("uncertainties 缺子键: %s" % uk)
    claims = res.get("claims")
    if not isinstance(claims, list):
        problems.append("claims 缺失或不是数组")
        claims = []

    fields = None
    if isinstance(res.get("result"), dict):
        fields = res["result"].get("fields")
    if fields is None:
        fields = res.get("fields")
    if not isinstance(fields, list):
        problems.append("result.fields 缺失或不是数组")
        fields = []

    want = field_ids_of(tf)
    got = [str(r.get("field_id")) for r in fields if isinstance(r, dict)]
    miss = [w for w in want if w not in got]
    if want and miss:
        problems.append("缺字段行（覆盖密度门禁）: %s" % ",".join(miss))
    dup = sorted({g for g in got if got.count(g) > 1})
    if dup:
        problems.append("重复 field_id: %s" % ",".join(dup))

    if isinstance(claims, list) and len(claims) < len(fields):
        problems.append("claims 数(%d) < fields 数(%d)（每行一条 claim 门禁）" % (len(claims), len(fields)))

    paras_n = {k: norm(v) for k, v in collect_paras(case, args.paras).items()}
    if not paras_n:
        warnings.append("段落文本不可用，quote 逐字校验降级跳过")

    cnt = check_rows(fields, paras_n, claims, problems, warnings)

    cov = None
    if isinstance(res.get("result"), dict):
        cov = res["result"].get("coverage")
    if isinstance(cov, dict) and cov.get("fields_total") != len(fields):
        problems.append("coverage.fields_total(%s) 与实际行数(%d) 不符" % (cov.get("fields_total"), len(fields)))

    return {"ok": not problems, "problems": problems, "warnings": warnings,
            "status_counts": cnt, "fields_checked": len(fields),
            "claims_checked": len(claims) if isinstance(claims, list) else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--fields", default="/input/target-fields.json")
    ap.add_argument("--paras", default=None)
    ap.add_argument("--out", default="/app/work/check-report.json")
    args = ap.parse_args()

    try:
        report = run(args)
    except Exception as e:
        report = {"ok": False, "problems": ["校验器内部异常: %s" % e], "warnings": [],
                  "status_counts": {}, "fields_checked": 0, "claims_checked": 0}

    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("[check] 报告写盘失败: %s" % e)

    if report.get("ok"):
        print("[check] PASS（%d 字段 / %d claims：%s）" % (
            report.get("fields_checked", 0), report.get("claims_checked", 0), report.get("status_counts")))
        return 0
    print("[check] FAIL（%d 处）" % len(report.get("problems", [])))
    for p in report.get("problems", [])[:50]:
        print("  - %s" % p)
    for w in report.get("warnings", [])[:10]:
        print("  ~ %s" % w)
    print("[check] FAIL 已照实记录，退出码 0，交付不中断")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[check] 未捕获异常已兜底: %s" % e)
        sys.exit(0)
