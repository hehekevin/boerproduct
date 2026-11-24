#!/usr/bin/env python3
"""make_result.py — 机械生成/更新/校验 result.json。保证 output_contract 字段一个不缺。
自测：--selftest 用合成正例+反例验证。全异常捕获，失败也写盘。"""
from __future__ import annotations
import argparse, copy, json, os, sys

DEFAULT_FIELDS = ["case_id", "status", "result", "claims", "uncertainties"]
STATUS_OK = ("answered", "partial", "insufficient_evidence", "input_error")

def contract_fields(case):
    """从 case.json 提取 output_contract 顶层字段名清单。容错：dict/list/缺失。"""
    try:
        oc = case.get("output_contract")
        if isinstance(oc, dict):
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return list(DEFAULT_FIELDS)

def skeleton(case):
    cid = "unknown"
    try:
        cid = str(case.get("case_id") or "unknown")
    except Exception:
        pass
    sk = {}
    for f in contract_fields(case):
        if f == "case_id":
            sk[f] = cid
        elif f == "status":
            sk[f] = "partial"
        elif f == "result":
            sk[f] = {"client": {"kind": "self-contained-html", "path": "/app/output/reading_client.html", "embedded_html": ""},
                     "qa": [], "annotations_count": 0, "reading_position": None}
        elif f == "claims":
            sk[f] = []
        elif f == "uncertainties":
            sk[f] = {"unreported": [], "unverifiable": [], "conflicts": [], "human_review": [],
                     "summary": "骨架阶段：尚未完成任何分析。"}
        else:
            sk[f] = [] if f not in ("result", "claims") else []
    return sk

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as e:
        print("[make_result] WARN: 读取 %s 失败: %s" % (path, e))
        return {}

def write_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[make_result] FAIL: 写 %s 失败: %s" % (path, e))
        return False

def deep_merge(dst, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v

def cmd_init(a):
    case = load_json(a.case)
    sk = skeleton(case)
    if not case:
        sk["uncertainties"]["summary"] = "case.json 不可读或为空：按默认五字段契约推进，结果以实际可读材料为准。"
    if write_json(a.out, sk):
        print("[make_result] INIT: %d 个契约字段 -> %s" % (len(sk), ",".join(sk.keys())))
        return 0
    return 1

def cmd_merge(a):
    r = load_json(a.result)
    patch = load_json(a.patch)
    if not isinstance(r, dict) or not r:
        print("[make_result] FAIL: result.json 不可读，先运行 --init")
        return 1
    before = set(r.keys())
    deep_merge(r, patch)
    missing = [f for f in contract_fields(load_json(a.case)) if f not in r]
    for f in missing:
        r[f] = [] if f in ("claims", "uncertainties") else "unknown"
    if r.get("status") not in STATUS_OK:
        r["status"] = "partial"
    ok = write_json(a.result, r)
    print("[make_result] MERGE: 新增键 %s；契约缺键已补 %s" % (
        sorted(set(r.keys()) - before) or "无", missing or "无"))
    return 0 if ok else 1

def cmd_check(a):
    r = load_json(a.result)
    if not isinstance(r, dict) or not r:
        print("[make_result] FAIL: result.json 不存在或不可解析")
        return 1
    missing = [f for f in contract_fields(load_json(a.case)) if f not in r]
    problems = []
    if missing:
        problems.append("缺契约字段: %s" % missing)
    if r.get("status") not in STATUS_OK:
        problems.append("status 非法: %r" % r.get("status"))
    if not str(r.get("case_id") or "").strip():
        problems.append("case_id 为空")
    for p in problems:
        print("  - %s" % p)
    print("[make_result] %s (%d 字段)" % ("FAIL" if problems else "PASS", len(r)))
    return 1 if problems else 0

def cmd_selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        # 正例：dict 契约
        cp = os.path.join(td, "case.json")
        write_json(cp, {"case_id": "T-POS", "output_contract": {"case_id": "", "status": "", "result": "", "claims": "", "uncertainties": ""}})
        rp = os.path.join(td, "result.json")
        if cmd_init(argparse.Namespace(case=cp, out=rp)) != 0:
            ok = False
        r = load_json(rp)
        if set(contract_fields(load_json(cp))) - set(r.keys()):
            print("  [selftest] 正例缺键 FAIL"); ok = False
        # 正例 merge
        pp = os.path.join(td, "patch.json")
        write_json(pp, {"result": {"qa": [{"question_id": "q1"}]}, "status": "answered"})
        if cmd_merge(argparse.Namespace(result=rp, patch=pp, case=cp)) != 0:
            ok = False
        if load_json(rp).get("status") != "answered":
            print("  [selftest] merge 后 status 错误 FAIL"); ok = False
        if cmd_check(argparse.Namespace(result=rp, case=cp)) != 0:
            print("  [selftest] 正例 check FAIL"); ok = False
        # 反例1：case 不可读
        rp2 = os.path.join(td, "r2.json")
        if cmd_init(argparse.Namespace(case=os.path.join(td, "nope.json"), out=rp2)) != 0:
            print("  [selftest] 反例1: case 缺失时 init 应仍写盘 FAIL"); ok = False
        if not load_json(rp2):
            print("  [selftest] 反例1: 骨架为空 FAIL"); ok = False
        # 反例2：result 损坏时 check 应报 FAIL 而非崩溃
        bad = os.path.join(td, "bad.json")
        with open(bad, "wb") as f:
            f.write(b"\xff\xfe garbage")
        if cmd_check(argparse.Namespace(result=bad, case=cp)) == 0:
            print("  [selftest] 反例2: 损坏 result 应 FAIL FAIL"); ok = False
    print("[make_result] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default="/app/output/result.json")
    ap.add_argument("--patch", default=None)
    a = ap.parse_args()
    try:
        if a.selftest:
            return cmd_selftest(a)
        if a.init:
            return cmd_init(argparse.Namespace(case=a.case, out=a.out))
        if a.merge:
            return cmd_merge(argparse.Namespace(result=a.result, patch=a.patch or "", case=a.case))
        if a.check:
            return cmd_check(argparse.Namespace(result=a.result, case=a.case))
        ap.print_help()
        return 2
    except Exception as e:
        print("[make_result] 兜底异常: %s（保留现有 result.json）" % e)
        return 1

if __name__ == "__main__":
    sys.exit(main())
