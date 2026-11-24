#!/usr/bin/env python3
"""check_all.py — 机械终检（写盘前必须 PASS）：契约字段/锚点逐字/offsets/产物存在/
嵌入一致性/claims 结构/status 诚实。任何输入不崩溃，输出 check_report.json。自测：--selftest。"""
from __future__ import annotations
import argparse, json, os, re, sys

STATUS_OK = ("answered", "partial", "insufficient_evidence", "input_error")
DEFAULT_FIELDS = ["case_id", "status", "result", "claims", "uncertainties"]

def norm(s):
    return re.sub(r"\s+", "", str(s or ""))

def load(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return None

def contract_fields(case):
    try:
        oc = case.get("output_contract")
        if isinstance(oc, dict):
            return [str(k) for k in oc.keys()]
        if isinstance(oc, list):
            return [str(x) for x in oc]
    except Exception:
        pass
    return list(DEFAULT_FIELDS)

def check(args):
    problems = []
    result = load(args.result)
    if not isinstance(result, dict) or not result:
        problems.append("result.json 不存在或不可解析")
        result = {}
    case = load(args.case) or {}
    fields = contract_fields(case)
    for f in fields:
        if f not in result:
            problems.append("缺 output_contract 字段: %s" % f)
    if not str(result.get("case_id") or "").strip():
        problems.append("case_id 为空")
    elif case.get("case_id") and str(result["case_id"]) != str(case["case_id"]):
        problems.append("case_id 与输入不一致")
    if result.get("status") not in STATUS_OK:
        problems.append("status 非法: %r" % result.get("status"))

    # 段落索引（locator 优先，退化用 case 内段落）
    paras = {}
    loc = load(args.locator) if args.locator else None
    src = loc if isinstance(loc, dict) and loc.get("paragraphs") else case
    for key in ("paragraphs", "passages", "paper_paragraphs", "sections", "sentences", "blocks"):
        if isinstance(src.get(key), list):
            for i, p in enumerate(src[key]):
                try:
                    if isinstance(p, dict):
                        pid = str(p.get("paragraph_id") or p.get("id") or ("p%02d" % (i + 1)))
                        paras[pid] = str(p.get("text") or p.get("content") or p.get("body") or "")
                    else:
                        paras["p%02d" % (i + 1)] = str(p)
                except Exception:
                    continue
            break

    # annotations 锚点校验
    items = []
    ann = load(args.annotations)
    if ann is None:
        problems.append("annotations.json 不存在或不可解析")
    else:
        items = ann if isinstance(ann, list) else (ann.get("annotations") or [])
    for i, a in enumerate(items):
        if not isinstance(a, dict):
            problems.append("annotations[%d] 不是对象" % i)
            continue
        aid = a.get("annotation_id", i)
        pid = str(a.get("paragraph_id"))
        ptext = norm(paras.get(pid, ""))
        if paras and pid not in paras:
            problems.append("[%s] paragraph_id=%s 不在索引" % (aid, pid))
        else:
            if norm(a.get("selection_quote")) and ptext and norm(a["selection_quote"]) not in ptext:
                problems.append("[%s] selection_quote 锚点错位" % aid)
            if norm(a.get("evidence_quote")) and ptext and norm(a["evidence_quote"]) not in ptext:
                problems.append("[%s] evidence_quote 锚点错位" % aid)
            offs = a.get("offsets")
            if isinstance(offs, list) and len(offs) == 2 and pid in paras:
                try:
                    L = len(paras[pid])
                    if not (0 <= int(offs[0]) <= int(offs[1]) <= L):
                        problems.append("[%s] offsets 越界（段落长 %d）" % (aid, L))
                except Exception:
                    problems.append("[%s] offsets 格式错误" % aid)
        if a.get("status") == "answered" and not str(a.get("answer") or "").strip():
            problems.append("[%s] status=answered 但 answer 为空" % aid)

    # result.result.qa 结构
    res = result.get("result") if isinstance(result.get("result"), dict) else {}
    for i, q in enumerate(res.get("qa") or []):
        if not isinstance(q, dict):
            problems.append("result.qa[%d] 不是对象" % i)
            continue
        if q.get("status") not in STATUS_OK:
            problems.append("result.qa[%d] status 非法: %r" % (i, q.get("status")))
        if q.get("status") in ("answered",) and not str(q.get("answer") or "").strip():
            problems.append("result.qa[%d] answered 但 answer 为空" % i)

    # artifacts 存在性（artifacts 未登记时回退 result.json 同目录）
    arts = res.get("artifacts") if isinstance(res.get("artifacts"), dict) else {}
    rdir = os.path.dirname(os.path.abspath(args.result)) or "."
    client_path = arts.get("client_html") or os.path.join(rdir, "reading_client.html")
    if not os.path.exists(client_path):
        problems.append("客户端 HTML 缺失: %s" % client_path)
    rl_path = arts.get("reading_log") or os.path.join(rdir, "reading_log.jsonl")
    if os.path.exists(rl_path):
        try:
            with open(rl_path, "r", encoding="utf-8", errors="replace") as f:
                if not any(l.strip() for l in f):
                    problems.append("reading_log 为空")
        except Exception:
            problems.append("reading_log 不可读")
    else:
        problems.append("reading_log 缺失: %s" % rl_path)

    # 嵌入一致性：embedded_html 与外部文件一致
    emb = (res.get("client") or {}).get("embedded_html") if isinstance(res.get("client"), dict) else None
    if emb:
        try:
            disk = open(client_path, "r", encoding="utf-8", errors="replace").read()
            if norm(emb) != norm(disk):
                problems.append("embedded_html 与 %s 内容不一致" % client_path)
        except Exception as e:
            problems.append("嵌入一致性校验失败: %s" % e)
    else:
        problems.append("result.result.client.embedded_html 未嵌入（主产物须嵌入 result.json）")

    # claims 结构
    claims = result.get("claims")
    if not isinstance(claims, list) or not claims:
        problems.append("claims 为空（关键结论必须带证据）")
    else:
        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                problems.append("claims[%d] 不是对象" % i)
                continue
            for k in ("kind", "source_id", "location"):
                if not str(c.get(k) or "").strip():
                    problems.append("claims[%d] 缺 %s" % (i, k))
            if not (c.get("evidence") or c.get("evidence_quote")):
                problems.append("claims[%d] 缺 evidence" % i)

    # uncertainties
    unc = result.get("uncertainties")
    if not isinstance(unc, dict) or not str(unc.get("summary") or "").strip():
        problems.append("uncertainties 缺失或无 summary")

    report = {"ok": not problems, "problems": problems[:60],
              "counts": {"annotations": len(items), "claims": len(claims or [])}}
    try:
        with open(os.path.join(os.path.dirname(args.result) or ".", "check_report.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    if problems:
        print("[check_all] FAIL (%d 项)" % len(problems))
        for p in problems[:40]:
            print("  - %s" % p)
        return 1
    print("[check_all] PASS（契约 %d 字段 · 批注 %d · claims %d · 锚点全命中）" % (
        len(fields), len(items), len(claims or [])))
    return 0

def selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cp = os.path.join(td, "c.json"); lp = os.path.join(td, "l.json")
        rp = os.path.join(td, "r.json"); ap_ = os.path.join(td, "a.json")
        htmlp = os.path.join(td, "cli.html")
        json.dump({"case_id": "T1", "output_contract": {"case_id": 1, "status": 1, "result": 1, "claims": 1, "uncertainties": 1}}, open(cp, "w", encoding="utf-8"))
        json.dump({"paragraphs": [{"paragraph_id": "p01", "text": "Alpha improves recall by 12%."}]}, open(lp, "w", encoding="utf-8"))
        open(htmlp, "w", encoding="utf-8").write("<!DOCTYPE html><html>client</html>")
        open(os.path.join(td, "log.jsonl"), "w", encoding="utf-8").write('{"t":1}\n')
        good = {"case_id": "T1", "status": "answered", "result": {
            "qa": [{"question_id": "q1", "answer": "12%", "status": "answered"}],
            "client": {"kind": "self-contained-html", "embedded_html": open(htmlp, encoding="utf-8").read()},
            "artifacts": {"client_html": htmlp, "reading_log": os.path.join(td, "log.jsonl")}},
            "claims": [{"kind": "reported", "source_id": "T1", "location": "p01", "evidence": [{"quote": "Alpha improves"}]}],
            "uncertainties": {"summary": "无"}}
        json.dump(good, open(rp, "w", encoding="utf-8"))
        json.dump([{"annotation_id": "a-1", "paragraph_id": "p01", "selection_quote": "Alpha improves",
                    "evidence_quote": "recall by 12%", "offsets": [0, 14], "answer": "12%", "status": "answered"}],
                  open(ap_, "w", encoding="utf-8"))
        ns = argparse.Namespace(result=rp, annotations=ap_, case=cp, locator=lp)
        if check(ns) != 0:
            print("  [selftest] 正例应 PASS FAIL"); ok = False
        # 反例：锚点错位 + 嵌入不一致 + 缺字段
        bad = dict(good); bad["status"] = "answered"
        bad["claims"] = []
        bad2 = json.loads(json.dumps(good))
        bad2["result"]["client"]["embedded_html"] = "<html>different</html>"
        json.dump(bad2, open(rp, "w", encoding="utf-8"))
        json.dump([{"annotation_id": "a-1", "paragraph_id": "p01", "selection_quote": "NOT IN TEXT",
                    "offsets": [0, 999], "status": "answered", "answer": "x"}], open(ap_, "w", encoding="utf-8"))
        if check(ns) == 0:
            print("  [selftest] 反例应 FAIL FAIL"); ok = False
        # 反例2：全部文件缺失 → 报 FAIL 而非崩溃
        if check(argparse.Namespace(result=os.path.join(td, "x.json"), annotations=ap_, case=cp, locator=lp)) != 1:
            print("  [selftest] 反例2 应 FAIL FAIL"); ok = False
    print("[check_all] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--annotations", default="/app/output/annotations.json")
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--locator", default="/app/work/locator.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            return selftest(a)
        return check(a)
    except Exception as e:
        print("[check_all] 兜底异常: %s" % e)
        return 1

if __name__ == "__main__":
    sys.exit(main())
