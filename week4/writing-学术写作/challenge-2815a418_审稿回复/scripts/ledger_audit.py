#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_audit.py — 审稿回复三方一致性审计（回复信 / 修订稿 / 意见台账）

检查:
  1) 每个子要求有决策与回复文字（覆盖完整性）
  2) 改动锚点可检索: revision_log.revised 在修订稿中存在、original 在原稿中存在
  3) rejected/partially_adopted 有理由
  4) 语气词审计（无冒犯、无过度承诺）
  5) 证据状态合法（done / replaced_by_alternative / not_possible / planned）
  6) 每处修改带 revision_log 留痕（original/revised/reason/basis 四字段齐全）

用法:
  python ledger_audit.py --ledger /app/work/response_ledger.jsonl \
      --letter /app/output/response_letter.md --revised /app/output/revised.md \
      --original /app/work/extracted --out /app/output/ledger_audit.json
fail 时退出码 1，修复后重跑；报告始终写盘。
"""
import argparse, json, os, re, sys, glob

BAD_TONE = ["显然你", "你没看", "错误百出", "胡说", "荒谬", "无聊",
            "抱歉耽误您时间我们马上全部照改"]
OVERPROMISE = ["我们将补所有", "全部重做", "保证接收", "完全按照您的一切意见"]
REV_FIELDS = ("original", "revised", "reason", "basis")


def _norm(s):
    return re.sub(r"\s+", "", str(s))


def _load_original(path_or_dir):
    if not path_or_dir:
        return ""
    if os.path.isdir(path_or_dir):
        return "\n".join(open(fp, encoding="utf-8").read()
                         for fp in sorted(glob.glob(os.path.join(path_or_dir, "*.txt"))))
    return open(path_or_dir, encoding="utf-8").read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--letter", required=True)
    ap.add_argument("--revised", required=True)
    ap.add_argument("--original", default=None, help="原稿提取文本目录或文件（可选）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.ledger, encoding="utf-8") if l.strip()]
    letter_raw = open(args.letter, encoding="utf-8").read()
    letter = _norm(letter_raw)
    revised = _norm(open(args.revised, encoding="utf-8").read())
    orig = _norm(_load_original(args.original))

    problems = []

    # 1) 覆盖完整性
    uncovered = [r.get("sid") for r in rows
                 if not r.get("decision") or not str(r.get("letter_text") or "").strip()]
    if uncovered:
        problems.append({"type": "uncovered_subrequirements", "sids": uncovered[:30]})

    # 2) + 6) 改动锚点与 revision_log 留痕
    anchor_bad, revlog_bad = [], []
    for r in rows:
        for e in r.get("edits", []):
            rl = e.get("revision_log") or {}
            after = _norm(rl.get("revised") or e.get("after") or "")
            before = _norm(rl.get("original") or e.get("anchor_quote") or "")
            if after and after[:30] not in revised:
                anchor_bad.append({"sid": r.get("sid"), "eid": e.get("eid"),
                                   "issue": "revised_not_in_revised_manuscript"})
            if before and orig and before[:30] not in orig:
                anchor_bad.append({"sid": r.get("sid"), "eid": e.get("eid"),
                                   "issue": "original_not_in_baseline"})
            miss = [f for f in REV_FIELDS if not str(rl.get(f) or "").strip()]
            if miss:
                revlog_bad.append({"sid": r.get("sid"), "eid": e.get("eid"), "missing": miss})
    if anchor_bad:
        problems.append({"type": "anchor_mismatch", "count": len(anchor_bad),
                         "detail": anchor_bad[:20]})
    if revlog_bad:
        problems.append({"type": "revision_log_incomplete", "count": len(revlog_bad),
                         "detail": revlog_bad[:20]})

    # 3) rejected 有理由
    rej_bad = [r.get("sid") for r in rows
               if r.get("decision") in ("rejected", "partially_adopted")
               and len(str(r.get("decision_rationale") or "")) < 10]
    if rej_bad:
        problems.append({"type": "rejection_without_rationale", "sids": rej_bad})

    # 4) 语气
    tone_hits = [w for w in BAD_TONE + OVERPROMISE if w in letter_raw]
    if tone_hits:
        problems.append({"type": "tone_issues", "words": tone_hits})

    # 5) 证据状态
    ev_bad = [r.get("sid") for r in rows for e in r.get("evidence", [])
              if e.get("status") not in ("done", "replaced_by_alternative",
                                         "not_possible", "planned", None)]
    if ev_bad:
        problems.append({"type": "evidence_status_invalid", "sids": ev_bad})

    hard = bool(problems)
    report = {"subs_total": len(rows), "problems": problems, "fail": len(problems),
              "verdict": "pass" if not hard else "fail",
              "hint": "fail 项回台账/回复信修复后重跑；每处修改必须带 revision_log 四字段。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "subs": len(rows),
                      "problems": [p["type"] for p in problems]}, ensure_ascii=False))
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
