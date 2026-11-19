#!/usr/bin/env python3
"""kb_index.py — Step 2 机械检索与未命中判定（kbqa-cite 科研知识库问答）。

对 result.questions 中每个子问题，在知识库条目上做确定性的词面重叠打分：
中文按 CJK 连续串切 2-gram、英文/数字按 [A-Za-z0-9]+ 切词（用正则而非 str.isalpha，
规避汉字 isalpha()==True 的陷阱），idf 加权后输出 top-k 候选条目与分数。
top1 分数低于阈值（默认 0.02）或零重叠 → 判定检索未命中候选（miss_candidate），
登记进 /app/work/retrieval.json，供 Agent 作答时逐条核实；**本脚本不写
result.json**（键归属：result.json 只由 build_skeleton / verify_check /
gain_probe / Agent 更新各自键），也未命中≠最终结论，最终以答案里的 status=miss
+ gaps 登记为准。

用法：
    python3 kb_index.py --result /app/output/result.json --case /input/case.json \
        --work-dir /app/work [--topk 3] [--threshold 0.02]
退出码恒为 0（失败以 WARN 报告，报告仍写出）。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

CJK = re.compile(r"[\u4e00-\u9fff]+")
ASCII_TOK = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")


def tokens(text):
    """中文 2-gram + 英文/数字词。小写归一；不用 isalpha（汉字陷阱）。"""
    text = str(text or "").lower()
    out = []
    for seg in CJK.findall(text):
        seg = "^" + seg + "$"
        out.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    out.extend(ASCII_TOK.findall(text))
    return out


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
    except Exception as e:
        print("[kb_index] 写盘失败 %s: %s" % (path, e))
        return False


def collect_entries(res, case):
    """条目池 = result.knowledge_base.entries + case.json 常见键兜底。"""
    pool = {}
    inner = (res or {}).get("result") or {}
    kb = inner.get("knowledge_base") or {}
    for e in (kb.get("entries") or []):
        if isinstance(e, dict) and e.get("entry_id"):
            pool[str(e["entry_id"])] = {"title": e.get("title") or "",
                                        "kind": e.get("kind") or "unknown"}
    if not pool and isinstance(case, dict):
        for key in ("kb_entries", "entries", "knowledge_base", "documents",
                    "notes", "faqs", "files", "materials", "corpus", "items"):
            v = case.get(key)
            if isinstance(v, list):
                for i, e in enumerate(v):
                    if isinstance(e, dict):
                        eid = str(e.get("entry_id") or e.get("doc_id") or
                                  e.get("id") or "E%02d" % (i + 1))
                        pool.setdefault(eid, {"title": str(e.get("title") or e.get("name") or ""),
                                              "kind": str(e.get("kind") or e.get("type") or "unknown")})
                if pool:
                    break
    return pool


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--manifest", default=None,
                        help="条目内容台账（默认 work-dir/entries.json）")
        ap.add_argument("--topk", type=int, default=3)
        ap.add_argument("--threshold", type=float, default=0.02)
        args = ap.parse_args()
    except Exception as e:
        print("[kb_index] 参数解析失败（已降级）: %s" % e)
        return 0

    problems = []
    res = load_json(args.result)
    case = load_json(args.case)
    if not isinstance(res, dict):
        problems.append("result.json 不存在或不可解析: %s" % args.result)
    manifest_path = args.manifest or os.path.join(args.work_dir or ".", "entries.json")
    manifest = load_json(manifest_path) or {}
    contents = {}
    for m in (manifest.get("entries") or []):
        if isinstance(m, dict) and m.get("entry_id") and m.get("content"):
            contents[str(m["entry_id"])] = str(m["content"])

    pool = collect_entries(res if isinstance(res, dict) else {},
                           case if isinstance(case, dict) else {})
    if not pool:
        problems.append("知识库条目池为空（result.knowledge_base.entries 与 case.json 均未提取到）")

    # 条目语料：台账正文（有则用）+ 标题
    corpus = {}
    for eid, meta in pool.items():
        corpus[eid] = "%s\n%s" % (meta.get("title") or "", contents.get(eid, ""))
    tfs, doc_len = {}, {}
    for eid, text in corpus.items():
        tk = tokens(text)
        tfs[eid] = {}
        for t in tk:
            tfs[eid][t] = tfs[eid].get(t, 0) + 1
        doc_len[eid] = max(len(tk), 1)
    N = max(len(pool), 1)
    df = {}
    for eid, tf in tfs.items():
        for t in tf:
            df[t] = df.get(t, 0) + 1

    def score(query_tokens, eid):
        s = 0.0
        for t in set(query_tokens):
            if t in tfs[eid]:
                idf = math.log((N + 1) / (df.get(t, 0) + 1)) + 1.0
                s += idf * tfs[eid][t] / doc_len[eid]
        return round(s, 4)

    # 子问题来源：result.questions[].subquestions（Step 1 已拆解）
    subs = []
    if isinstance(res, dict):
        for q in ((res.get("result") or {}).get("questions") or []):
            if not isinstance(q, dict):
                continue
            sqs = q.get("subquestions") or []
            if sqs:
                for sq in sqs:
                    if isinstance(sq, dict):
                        subs.append({"sub_id": str(sq.get("sub_id") or ""),
                                     "sub_question": str(sq.get("sub_question") or ""),
                                     "question_id": str(q.get("question_id") or "")})
            else:
                subs.append({"sub_id": str(q.get("question_id") or ""),
                             "sub_question": str(q.get("question") or ""),
                             "question_id": str(q.get("question_id") or ""),
                             "not_decomposed": True})
    if not subs:
        problems.append("result.questions 无子问题（先完成 Step 1 拆解再跑检索）")

    results = []
    n_miss = 0
    for sub in subs:
        qt = tokens(sub["sub_question"])
        ranked = sorted(((score(qt, eid), eid) for eid in pool),
                        key=lambda t: (-t[0], t[1]))
        top = ranked[:max(int(args.topk), 1)] if ranked else []
        top1 = top[0][0] if top else 0.0
        miss_cand = (not qt) or top1 < float(args.threshold)
        if miss_cand:
            n_miss += 1
        results.append({
            "sub_id": sub["sub_id"], "question_id": sub["question_id"],
            "sub_question": sub["sub_question"],
            "top_candidates": [{"entry_id": eid, "score": s} for s, eid in top],
            "top1_score": top1, "miss_candidate": bool(miss_cand),
            "miss_note": "top1 低于阈值 %.3f，可能检索未命中——须人工核实后以 status=miss"
                         " + gaps 登记或补充证据" % float(args.threshold)
                         if miss_cand else "",
        })

    report = {
        "tool": "scripts/kb_index.py",
        "case_id": (res or {}).get("case_id") if isinstance(res, dict) else None,
        "params": {"topk": int(args.topk), "threshold": float(args.threshold),
                   "entries": len(pool), "with_content": len(contents)},
        "queries": len(subs),
        "miss_candidates": n_miss,
        "results": results,
        "problems": problems,
        "note": "词面重叠打分只是召回策略：命中候选仍须 Agent 逐条读原文核对语义相关性；"
                "miss_candidate 须在作答阶段核实为 status=miss 并登记 gaps，不得静默忽略。",
    }
    out_path = os.path.join(args.work_dir or ".", "retrieval.json")
    save_json(out_path, report)

    print("[kb_index] 子问题 %d 个 | 条目 %d 个（含正文 %d）| 未命中候选 %d 个"
          % (len(subs), len(pool), len(contents), n_miss))
    for r in results:
        cands = ", ".join("%s:%s" % (c["entry_id"], c["score"])
                          for c in r["top_candidates"]) or "-"
        print("  %s  top1=%s  %s  [%s]"
              % (r["sub_id"], r["top1_score"],
                 "MISS?" if r["miss_candidate"] else "hit", cands))
    for p in problems:
        print("  WARN: %s" % p)
    print("[kb_index] 报告已写: %s" % os.path.abspath(out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[kb_index] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
