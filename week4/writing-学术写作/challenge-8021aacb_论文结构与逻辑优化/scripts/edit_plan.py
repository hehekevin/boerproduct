#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edit_plan.py — 合并机检+模型 findings，产出可执行编辑动作清单与可编辑诊断报告

输入：structure_check 机检 findings + 模型语义诊断 model_findings.json（可缺省）。
输出：/app/work/edit_actions.jsonl（有序动作）+ /app/output/findings.json（合并后清单）
      + /app/output/report.md（作者可对照逐条采纳/部分采纳/驳回的可编辑报告）。
每条建议指回原文位置与逐字引文（说得清）；动作类型限定 move/merge/split/narrow/
insert/delete（改得动）。退出码恒 0。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog

ACTION_TYPES = ("move", "merge", "split", "narrow", "insert", "delete")


def norm_quote(q):
    return re.sub(r"[\s，。；、,.;:：""''\"'()（）]", "", str(q or ""))[:30]


def merge(machine, model):
    seen, merged = set(), []
    for f in (machine or []) + (model or []):
        if not isinstance(f, dict) or not f.get("category"):
            continue
        loc_key = str((f.get("location") or {}).get("section") or "") + ":" + \
                  str((f.get("location") or {}).get("paragraph") or "")
        key = (f.get("category"), norm_quote(f.get("quote")), loc_key)
        if key in seen and f.get("source") == "machine":
            continue
        if key in seen:
            for g in merged:
                if (g["category"], norm_quote(g["quote"]),
                        str((g.get("location") or {}).get("section") or "") + ":" +
                        str((g.get("location") or {}).get("paragraph") or "")) == key:
                    g.setdefault("model_echo", True)
            continue
        g = dict(f)
        g.setdefault("source", "model")
        g.setdefault("severity", "mid")
        g.setdefault("location", {})
        g.setdefault("quote", "")
        g.setdefault("problem", "")
        g.setdefault("basis", "模型语义判断（结构级，机检无法覆盖）")
        act = g.get("suggested_action") or {}
        if act.get("type") not in ACTION_TYPES:
            act["type"] = "insert"
        if not act.get("instruction"):
            act["instruction"] = "（模型建议缺省：请按问题类型给出可执行编辑动作）"
        g["suggested_action"] = act
        g.setdefault("status", "pending_author")
        g["finding_id"] = g.get("finding_id") or "M%03d" % (len(merged) + 1)
        seen.add(key)
        merged.append(g)
    sev_rank = {"high": 0, "mid": 1, "low": 2}
    merged.sort(key=lambda f: (sev_rank.get(f.get("severity"), 3), f.get("category", "")))
    for i, f in enumerate(merged, 1):
        f["action_id"] = "E%02d" % i
    return merged


def write_report(merged, ms, path, gaps):
    def loc(f):
        l = f.get("location") or {}
        p = l.get("paragraph")
        return "%s%s" % (l.get("section") or "（未定位）", (" 第%d段" % p) if p else "")
    cats = {}
    for f in merged:
        cats.setdefault(f.get("category_zh") or f.get("category"), []).append(f)
    lines = ["# 结构诊断与修改方案（可编辑，作者逐条裁决）", "",
             "> 本报告由参赛 Skill 生成；每条问题定位到章节/段落并附逐字引文，",
             "> 作者复核后在行末勾选：[ ]采纳 / [ ]部分采纳 / [ ]驳回。示意说明见 examples/（非正式案例结果）。", ""]
    st = (ms or {}).get("stats") or {}
    lines.append("## 一、总体判断")
    lines.append("- 稿件规模：%d 章节 / %d 段 / %d 字。" % (st.get("sections", 0), st.get("paragraphs", 0), st.get("chars", 0)))
    lines.append("- 共 %d 条结构问题：高 %d / 中 %d / 低 %d。" % (
        len(merged),
        sum(1 for f in merged if f.get("severity") == "high"),
        sum(1 for f in merged if f.get("severity") == "mid"),
        sum(1 for f in merged if f.get("severity") == "low")))
    lines.append("")
    lines.append("## 二、问题清单（按六类组织，严重度排序）")
    for cat, fs in cats.items():
        lines.append("")
        lines.append("### %s（%d 条）" % (cat, len(fs)))
        for f in fs:
            act = f.get("suggested_action") or {}
            lines.append("- **%s [%s]** %s（%s）" % (f["action_id"], f.get("severity"), f.get("problem", ""), loc(f)))
            if f.get("quote"):
                lines.append("  - 原文引文：「%s」" % f["quote"])
            lines.append("  - 依据：%s" % f.get("basis", ""))
            lines.append("  - 建议动作（%s）：%s" % (act.get("type"), act.get("instruction")))
            lines.append("  - 作者决定：[ ] 采纳　[ ] 部分采纳　[ ] 驳回（理由：____）")
    lines.append("")
    lines.append("## 三、人工确认项与材料缺口")
    for g in (gaps or []):
        lines.append("- %s" % g)
    if not gaps:
        lines.append("- （无模型登记项；机检结论已全部列出，仍建议作者按引文逐条复核）")
    lines.append("")
    lines.append("## 四、修改差异记录（作者填写）")
    lines.append("| 动作 | 是否执行 | 实际改动 | 备注 |")
    lines.append("|---|---|---|---|")
    for f in merged:
        lines.append("| %s | | | |" % f["action_id"])
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        sys.stderr.write("report 写入失败: %s\n" % e)
        return False


def main():
    t0 = __import__("time").time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", default="/app/work/findings_machine.json")
    ap.add_argument("--model", default="/app/work/model_findings.json")
    ap.add_argument("--manuscript", default="/app/work/manuscript.json")
    ap.add_argument("--out-actions", default="/app/work/edit_actions.jsonl")
    ap.add_argument("--out-findings", default="/app/output/findings.json")
    ap.add_argument("--out-report", default="/app/output/report.md")
    ap.add_argument("--gaps", default=None, help="JSON 数组字符串：人工确认项/材料缺口")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误"}))
        return 0

    def load(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            return d.get("findings", []) if isinstance(d, dict) else d
        except Exception:
            return []
    model_raw = load(args.model)
    model_ok = bool(model_raw)
    machine = load(args.machine)
    merged = merge(machine, model_raw)
    ms = {}
    try:
        ms = json.load(open(args.manuscript, encoding="utf-8"))
    except Exception:
        pass
    gaps = []
    try:
        gaps = json.loads(args.gaps) if args.gaps else []
    except Exception:
        gaps = [x.strip() for x in (args.gaps or "").split(";") if x.strip()]
    if not model_ok:
        gaps.append("模型语义诊断（model_findings.json）缺失：本次仅机检结论，六类中需要语义判断的项目可能遗漏")
    out = {"ok": True, "actions": len(merged), "model_findings_present": model_ok}
    try:
        with open(args.out_actions, "w", encoding="utf-8") as f:
            for fobj in merged:
                f.write(json.dumps(fobj, ensure_ascii=False) + "\n")
        os.makedirs(os.path.dirname(args.out_findings) or ".", exist_ok=True)
        json.dump({"findings": merged, "total": len(merged),
                   "per_category": {c: sum(1 for x in merged if x["category"] == c)
                                     for c in set(x["category"] for x in merged)}},
                  open(args.out_findings, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out["report_written"] = write_report(merged, ms, args.out_report, gaps)
        out["report_path"] = args.out_report
    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)
    print(json.dumps(out, ensure_ascii=False))
    _rlog.log_call("edit_plan", argv=sys.argv[1:], seconds=__import__("time").time() - t0,
                   extra={"actions": len(merged)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
