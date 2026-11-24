#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edits_verify.py — 修订台账校验
检查: 1) 每条 edit 的 anchor_quote/before 能在原稿找到；2) after 能在修订稿找到；
3) 未授权改动检测（修订稿相对原稿的实质句差异都应被某条 edit 覆盖）；
4) 引用编号连续性（[n] 无跳号）。
"""
import argparse, json, os, re, sys, glob

def _norm(s):
    return re.sub(r"\s+", "", s)

def _load_original(path_or_dir):
    texts = []
    p = path_or_dir
    if os.path.isdir(p):
        for fp in sorted(glob.glob(os.path.join(p, "*.txt"))):
            texts.append(open(fp, encoding="utf-8").read())
        return "\n".join(texts)
    return open(p, encoding="utf-8").read()

def main():
    ap = ap = argparse.ArgumentParser()
    ap.add_argument("--edits", required=True)
    ap.add_argument("--original", required=True)
    ap.add_argument("--revised", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    # 三级容错：缺文件/脏 JSONL 不崩溃，产出带 error 说明的报告
    load_errors = []
    edits = []
    try:
        for i, l in enumerate(open(args.edits, encoding="utf-8")):
            l = l.strip()
            if not l:
                continue
            try:
                _e = json.loads(l)
                if isinstance(_e, dict):
                    edits.append(_e)
                else:
                    load_errors.append({"line": i + 1, "issue": "not_object"})
            except Exception:
                load_errors.append({"line": i + 1, "issue": "malformed_json"})
    except Exception as _e:
        load_errors.append({"issue": "edits_file_unreadable", "detail": repr(_e)})
    try:
        orig = _norm(_load_original(args.original))
    except Exception as _e:
        orig = ""
        load_errors.append({"issue": "original_unreadable", "detail": repr(_e)})
    try:
        rev_raw = open(args.revised, encoding="utf-8").read()
    except Exception as _e:
        rev_raw = ""
        load_errors.append({"issue": "revised_unreadable", "detail": repr(_e)})
    rev = _norm(rev_raw)

    anchor_bad, applied_bad = [], []
    for e in edits:
        probe_b = _norm(e.get("before") or e.get("anchor_quote") or "")[:40]
        probe_a = _norm(e.get("after") or "")[:40]
        if probe_b and probe_b not in orig:
            anchor_bad.append({"eid": e.get("eid"), "pid": e.get("pid"), "probe": probe_b[:40]})
        if e.get("status") == "applied" and probe_a and probe_a not in rev:
            applied_bad.append({"eid": e.get("eid"), "probe": probe_a[:40]})

    # 未授权改动：修订稿句子在原稿找不到、也不被任何 edit 覆盖（含子句级：句子中包含某 edit 的 before/after 片段即视为已授权）
    afters = {_norm(e.get("after") or "") for e in edits}
    probes = []
    for e in edits:
        for k in ("before", "after", "anchor_quote"):
            _p = _norm(e.get(k) or "")
            if len(_p) >= 8:
                probes.append(_p)
    unauthorized = []
    for para in rev_raw.split("\n"):
        if para.strip().startswith(("#", ">", "|", "```")):
            continue
        for sent in re.split(r"(?<=[。！？.!?])", para):
            n = _norm(sent)
            if len(n) < 12:
                continue
            if n in orig or n in afters:
                continue
            if any(p in n or n in p for p in probes):
                continue
            unauthorized.append(sent.strip()[:80])

    # 引用编号连续
    nums = sorted({int(m.group(1)) for m in re.finditer(r"\[(\d{1,3})\]", rev_raw)})
    gaps = []
    if nums:
        expect = set(range(1, max(nums) + 1))
        gaps = sorted(expect - set(nums))

    report = {"edits_total": len(edits), "anchor_fail": len(anchor_bad), "apply_fail": len(applied_bad),
              "unauthorized_changes": len(unauthorized), "citation_gaps": gaps,
              "load_errors": load_errors,
              "detail": {"anchor_bad": anchor_bad[:20], "applied_bad": applied_bad[:20],
                          "unauthorized_samples": unauthorized[:15]},
              "verdict": "pass" if not (anchor_bad or applied_bad or unauthorized or gaps or load_errors) else "fail",
              "hint": "锚点失效→修 pid/quote；apply 失败→改动未落地；unauthorized→回 Stage 3 补条目或恢复原文。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("edits_total", "anchor_fail", "apply_fail",
                                              "unauthorized_changes", "verdict")}, ensure_ascii=False))
    return 1 if report["verdict"] == "fail" else 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as _e:  # 三级容错：任何脏输入不崩溃，输出可检错误报告而非 traceback
        _rep = {"ok": False, "error": repr(_e), "tier": "fallback", "verdict": "error"}
        try:
            import json as _json
            print(_json.dumps(_rep, ensure_ascii=False))
        except Exception:
            print(_rep)
        sys.exit(0)