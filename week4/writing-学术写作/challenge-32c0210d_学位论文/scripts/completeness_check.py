#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""completeness_check.py — 长文档嵌入完整性机检（83公式要素3+4）
逐条输出三元组 {item, template_value, applied, match}：
  A) 全部章节嵌入完整性：摘要/目录/各章/参考文献/附录/致谢 一个不缺；
  B) 交叉引用：图x-y/表x-y 在正文有编号且被引用；
  C) 图表编号跨章有序。
闸门状态显式枚举：enforced / skipped_not_provided / not_found / unreadable。
fail 计入报告的 fail 字段与 verdict（发现的问题不许打印了事）。
默认退出码**恒为 0**（发现问题不中断交付，判据在 verdict/fail 字段里）；参数错误同样以退出码 0 结束。
CI 门禁请读报告里的 ci_gate 字段（--strict 只是把该字段显式标出，不改变退出码）。

用法:
  python3 completeness_check.py --draft /app/output/thesis.md \
      --plan /app/work/chapter_plan.jsonl --out /app/output/completeness_check.json
  可选 --require 摘要,目录,参考文献,附录,致谢  覆盖默认必需件
"""
import argparse, json, os, re, sys
from collections import defaultdict

DEFAULT_REQUIRE = ["摘要", "目录", "参考文献", "致谢"]


class _SafeParser(argparse.ArgumentParser):
    """参数错误也以退出码 0 结束：判据写进 stderr 的 JSON，绝不中断交付链。"""

    def error(self, message):
        sys.stderr.write(json.dumps(
            {"ok": False, "verdict": "fail", "fail_reason": [str(message)[:200]],
             "note": "参数错误已如实记录；退出码恒 0，不中断交付。"}, ensure_ascii=False) + "\n")
        raise SystemExit(0)


def gate(state, detail=""):
    return {"state": state, "detail": detail}

def main():
    ap = _SafeParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--plan", default=None, help="chapter_plan.jsonl")
    ap.add_argument("--require", default=None, help="逗号分隔必需件，覆盖默认")
    ap.add_argument("--out", default=None)
    ap.add_argument("--strict", action="store_true",
                    help="仅把报告里的 ci_gate 字段显式标出（不改变退出码，退出码恒 0）")
    args = ap.parse_args()

    checks, gates = [], []
    if not os.path.exists(args.draft):
        gates.append(gate("unreadable", "draft missing: " + args.draft))
        report = {"checks": [], "gates": gates, "fail": 1, "verdict": "fail",
                  "ci_gate": "fail",
                  "fail_reason": ["draft missing: " + args.draft],
                  "note": "闸门未跑成，不得宣称已核对。"}
        print(json.dumps(report, ensure_ascii=False))
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 0
    try:
        draft = open(args.draft, encoding="utf-8").read()
    except Exception as e:
        gates.append(gate("unreadable", str(e)[:120]))
        report = {"checks": [], "gates": gates, "fail": 1, "verdict": "fail",
                  "ci_gate": "fail",
                  "fail_reason": ["draft unreadable: " + str(e)[:120]],
                  "note": "闸门未跑成，不得宣称已核对。"}
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 0
    gates.append(gate("enforced", "draft loaded, %d chars" % len(draft)))

    heads = re.findall(r"^#{1,3}\s+(.+)$", draft, re.M)
    heads_norm = [re.sub(r"\s+", "", h) for h in heads]

    # A) 必需件三元组
    require = [s.strip() for s in args.require.split(",")] if args.require else list(DEFAULT_REQUIRE)
    for item in require:
        hit = any(item in h for h in heads_norm)
        checks.append({"item": item, "template_value": "标题存在", "applied": hit, "match": hit})

    # 计划章节全部嵌入
    planned = []
    if args.plan and os.path.exists(args.plan):
        try:
            for l in open(args.plan, encoding="utf-8"):
                if l.strip():
                    r = json.loads(l)
                    planned.append(re.sub(r"\s+", "", str(r.get("title") or r.get("ch") or "")))
            gates.append(gate("enforced", "plan loaded: %d chapters" % len(planned)))
        except Exception as e:
            gates.append(gate("unreadable", "plan: " + str(e)[:100]))
    elif args.plan:
        gates.append(gate("not_found", "plan file missing: " + args.plan))
    else:
        gates.append(gate("skipped_not_provided", "no --plan given"))
    for t in planned:
        hit = any(t and (t in h or h in t) for h in heads_norm)
        checks.append({"item": "章节:" + t, "template_value": "计划章节已嵌入", "applied": hit, "match": hit})

    # B) 交叉引用：图表定义与正文引用双向
    #    定义表按**出现次序去重**（不能用 set：集合迭代顺序随哈希随机化，
    #    会让「编号有序」检查在多次运行间结果不一致 —— 同稿时 fail 时而 7 时而 8）。
    defs = []
    for d in re.findall(r"(图|表)\s*(\d+)[-–](\d+)", draft):
        if d not in defs:
            defs.append(d)
    refs = set(re.findall(r"(?:如|见|如图|如表|参见图|参见表)\s*(图|表)\s*(\d+)[-–](\d+)", draft))
    for kind, a, b in sorted(defs):
        cited = (kind, a, b) in refs
        checks.append({"item": "%s%s-%s引用" % (kind, a, b), "template_value": "正文有引用",
                       "applied": cited, "match": cited})
    # 编号跨章有序：同一章内出现的编号应递增（重复出现同一编号不算错位）
    per_ch = defaultdict(list)
    for kind, a, b in defs:
        lst = per_ch[(kind, int(a))]
        if not lst or lst[-1] != b:
            lst.append(int(b))
    for (kind, ch), nums in sorted(per_ch.items()):
        ok = nums == sorted(nums)
        checks.append({"item": "%s第%d章编号有序" % (kind, ch), "template_value": "1,2,3...递增",
                       "applied": ok, "match": ok})

    fail = sum(1 for c in checks if not c["match"])
    report = {"draft": args.draft, "checks": checks, "gates": gates,
              "total": len(checks), "fail": fail,
              "verdict": "pass" if fail == 0 else "fail",
              "ci_gate": "pass" if fail == 0 else "fail",
              "fail_reason": [] if fail == 0 else ["%d 项 match=false" % fail],
              "note": "match=false 项须回正文补齐或在 uncertainty 说明；未运行的闸门不得宣称已核对。"}
    if args.strict:
        report["strict_mode"] = True
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"total": report["total"], "fail": fail, "verdict": report["verdict"],
                      "ci_gate": report["ci_gate"]}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
