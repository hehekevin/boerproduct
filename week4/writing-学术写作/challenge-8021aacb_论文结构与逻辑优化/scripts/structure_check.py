#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""structure_check.py — 六类结构机检校验器（同一校验器跑两臂，FAIL 数差由机器判定）

完整臂：六类结构检测（章节结构/论证链/段落关系/重复内容/结论边界/研究问题对齐）。
消融臂 --ablate：只留表层检测（段落长度离群、空段、标题缺失计数），六类全关，
模拟「无结构级能力的基础 Agent」，用于同输入增益对照。
每条 finding 定位到 章节/段落/句子 + 逐字引文（说得清），并给出动作类型建议（改得动）。
退出码恒 0。
"""
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rlog
from claim_extractor import extract, sentences, evidence_of

CATEGORIES = ["section_structure", "question_alignment", "claim_evidence",
              "paragraph_flow", "repetition", "claim_boundary"]
CAT_ZH = {"section_structure": "章节结构", "question_alignment": "研究问题对齐",
          "claim_evidence": "论证链", "paragraph_flow": "段落关系",
          "repetition": "重复内容", "claim_boundary": "结论边界"}
CANON = ["摘要", "引言", "相关工作", "方法", "结果", "讨论", "结论", "参考文献"]
OVERCLAIM = re.compile(r"(完全证明|彻底解决|百分之?百|首次(发现|提出|证明)|全面解决|完美解决|无可争议|所有(场景|情况|条件)下(均|都)?(优|胜|成立)|显著优于(所有|一切|全部))")
CAUSAL = re.compile(r"(导致|使得|归因|驱动|证明|证实|表明.{0,6}作用|因果)")
CORR = re.compile(r"(相关|关联|回归|相关系数|r\s*[=≈]|皮尔逊|斯皮尔曼)")
LIMIT_RE = re.compile(r"(局限|限制|不足|缺点|未来|后续|有待|仍需|however[^.]{0,40}limit)", re.IGNORECASE)
AIM_RE = re.compile(r"(本文|本研究|我们)[^。]{0,24}(旨在|的目的是|的目的在于|致力于|聚焦|针对)")
PROPOSE_RE = re.compile(r"提出[^。；，]{2,24}?(方法|模型|框架|算法|体系|方案)")
TRANS = re.compile(r"(然而|因此|此外|首先|其次|再次|最后|总之|综上|一方面|另一方面|具体而言|与之相对|在此基础上|相比之下)")


def finding(fid, cat, sev, sec, para, quote, problem, basis, action):
    return {"finding_id": fid, "source": "machine", "category": cat, "category_zh": CAT_ZH[cat],
            "severity": sev,
            "location": {"section": sec.get("heading"), "paragraph": para},
            "quote": quote[:80], "problem": problem, "basis": basis,
            "suggested_action": action, "status": "pending_author"}


def d_section_structure(ms, out):
    heads = [s["heading"] for s in ms["sections"]]
    joined = " ".join(heads)
    for kw in CANON[:7]:
        if kw not in joined:
            out.append(("section_structure", "mid", None, None,
                        "缺少「%s」类章节（标题层未检出）" % kw,
                        "机检: 必备章节关键词未在标题层命中",
                        {"type": "insert", "instruction": "确认稿件是否缺少%s章节；若体裁不需要，在人工确认项中驳回此条" % kw}))
    idx = []
    for i, kw in enumerate(CANON[:7]):
        for h in heads:
            if kw in h:
                idx.append((i, h))
                break
    order = [i for i, _ in idx]
    if order != sorted(order) and len(order) >= 2:
        out.append(("section_structure", "high", None, None,
                    "章节顺序偏离常规（%s）" % " → ".join(h for _, h in idx[:4]),
                    "机检: 与常规顺序 %s 对比" % "→".join(CANON[:7]),
                    {"type": "move", "instruction": "按常规叙事顺序核对章节位置，给出应移动的章节与目标位置"}))
    for s in ms["sections"]:
        ps = s["paragraphs"]
        if len(ps) == 1 and len(ps[0]) > 200 and "参考文献" not in s["heading"]:
            out.append(("section_structure", "low", s, 1, "单段章节且超过 200 字",
                        "机检: 段落数==1 且长度>200", {"type": "split", "instruction": "按子话题拆分为多段"}))


def d_question_alignment(ms, out):
    full = [s["heading"] for s in ms["sections"]]
    def sec_text(kws):
        for s in ms["sections"]:
            if any(k in s["heading"] for k in kws):
                return s
        return None
    intro = sec_text(["引言", "introduction", "背景"]) or (ms["sections"][0] if ms["sections"] else None)
    concl = sec_text(["结论", "总结", "conclusion"])
    intro_text = " ".join(intro["paragraphs"]) if intro else ""
    if not AIM_RE.search(intro_text):
        out.append(("question_alignment", "mid", intro, None,
                    "引言/摘要未检出明确的研究目的句（本文旨在…）",
                    "机检: 目的标记正则未命中引言全文",
                    {"type": "insert", "instruction": "在引言末补一句研究目的，与贡献主张对齐"}))
    if concl and not re.search(r"(综上|本文|本研究|总体|总之)", " ".join(concl["paragraphs"])):
        out.append(("question_alignment", "mid", concl, None,
                    "结论未回扣研究问题（未检出『综上/本文/本研究』回扣标记）",
                    "机检: 回扣标记未命中结论全文",
                    {"type": "insert", "instruction": "结论首句回扣引言提出的研究问题"}))
    if concl and not LIMIT_RE.search(" ".join(concl["paragraphs"]) + " " + " ".join(
            (sec_text(["讨论", "discussion"]) or {"paragraphs": []})["paragraphs"])):
        out.append(("claim_boundary", "mid", concl, None,
                    "结论/讨论未检出局限性表述",
                    "机检: 局限标记正则未命中",
                    {"type": "insert", "instruction": "补写与数据范围匹配的局限说明，收窄结论边界"}))
    for s in ms["sections"]:
        for pi, para in enumerate(s["paragraphs"], 1):
            for m in PROPOSE_RE.finditer(para):
                span = m.group(0)
                # 只对专名（ASCII 标识符/引号内名称）做机械跨章对齐；
                # 纯描述性短语机械匹配误报率高，留给模型语义诊断层。
                names = (re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", span)
                         + re.findall(r"[「“]([^」”]{2,20})[」”]", span))
                for name in set(names):
                    others = " ".join(p for s2 in ms["sections"] if s2 is not s
                                      for p in s2["paragraphs"])
                    if name not in others:
                        out.append(("question_alignment", "high", s, pi, name,
                                    "机检: 提出的方法名 %s 仅在当前章节出现，方法/结果章节未复现（各说各话嫌疑）" % name,
                                    {"type": "narrow", "instruction": "核对方法名是否在方法/结果章节有对应实现与验证；否则收窄该处贡献表述"}))
                        break


def d_claim_evidence(ms, out):
    rows, _ = extract(ms)
    for r in rows:
        if r["support"] != "none":
            continue
        strong = bool(re.search(r"(证明|证实|表明|验证)", " ".join(r["claim_markers"])))
        out.append(("claim_evidence", "high" if strong else "mid",
                    {"heading": r["section"]}, r["paragraph"], r["quote"],
                    "机检: 论断句无任何数值/引用/图表证据标记（同句同段均未命中）",
                    {"type": "narrow", "instruction": "为该论断补证据引用，或收窄为待验证假设并标注"}))


def d_paragraph_flow(ms, out):
    for s in ms["sections"]:
        for pi, para in enumerate(s["paragraphs"], 1):
            if len(para) > 400 and not TRANS.search(para):
                out.append(("paragraph_flow", "low", s, pi, para[:60],
                            "机检: 长段落（>400 字）且无任何衔接标记",
                            {"type": "split", "instruction": "拆分并在段首补衔接词，明确与上段关系"}))
            if 0 < len(para) < 40 and "参考文献" not in s["heading"]:
                out.append(("paragraph_flow", "low", s, pi, para,
                            "机检: 过短段落（<40 字），疑信息断裂或残句",
                            {"type": "merge", "instruction": "并入相邻段落或补全论述"}))


def _norm(t):
    return re.sub(r"""[\s，。；、,.;:：“”‘’"'()（）\[\]!?！？「」『』]""", "", t).lower()


def _jaccard(a, b):
    if len(a) < 4 or len(b) < 4:
        return 0.0
    A = set(_norm(a)[i:i + 2] for i in range(len(_norm(a)) - 1))
    B = set(_norm(b)[i:i + 2] for i in range(len(_norm(b)) - 1))
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def d_repetition(ms, out):
    seen = []
    for s in ms["sections"]:
        for pi, para in enumerate(s["paragraphs"], 1):
            for sent in sentences(para):
                if len(sent) < 12:
                    continue
                n = _norm(sent)
                for (h2, p2, n2, raw2) in seen:
                    if n == n2 or (len(n) >= 12 and (n in n2 or n2 in n)):
                        out.append(("repetition", "mid", s, pi, sent[:60],
                                    "机检: 与 %s 第%d段语句重复（归一化全等或互相包含）" % (h2, p2),
                                    {"type": "merge", "instruction": "与 %s 第%d段合并表述，保留信息更全的一处" % (h2, p2)}))
                        break
                    if _jaccard(sent, raw2) >= 0.85:
                        out.append(("repetition", "low", s, pi, sent[:60],
                                    "机检: 与 %s 第%d段高度相似（二元组 Jaccard≥0.85）" % (h2, p2),
                                    {"type": "merge", "instruction": "两处表述同义，合并或删一处"}))
                        break
                else:
                    seen.append((s["heading"], pi, n, sent))


def d_claim_boundary(ms, out):
    for s in ms["sections"]:
        for pi, para in enumerate(s["paragraphs"], 1):
            for sent in sentences(para):
                if OVERCLAIM.search(sent):
                    out.append(("claim_boundary", "high", s, pi, sent[:70],
                                "机检: 超出数据范围的绝对化表述（%s）" % OVERCLAIM.search(sent).group(0),
                                {"type": "narrow", "instruction": "收窄为实验条件内的表述，如『在本文数据集上优于基线』"}))
                elif CAUSAL.search(sent) and CORR.search(sent):
                    out.append(("claim_boundary", "high", s, pi, sent[:70],
                                "机检: 同句因果词与相关统计并存，疑把相关说成因果",
                                {"type": "narrow", "instruction": "改为『相关/关联』表述或补充因果识别设计说明"}))


def run_arm(ms, ablate=False):
    out = []  # (cat, sev, sec, para, quote, problem, basis, action)
    if ablate:
        # 消融臂：仅表层检测（模拟无结构能力的基础检查）
        for s in ms["sections"]:
            for pi, para in enumerate(s["paragraphs"], 1):
                if len(para) > 800:
                    out.append(("paragraph_flow", "low", s, pi, para[:60],
                                "表层机检: 段落超长（>800 字）",
                                {"type": "split", "instruction": "段落过长，建议拆分"}))
        for kw in ("摘要", "引言", "结论"):
            if not any(kw in s["heading"] for s in ms["sections"]):
                out.append(("section_structure", "low", None, None,
                            "表层机检: 缺少「%s」标题" % kw,
                            {"type": "insert", "instruction": "补标题"}))
    else:
        d_section_structure(ms, out)
        d_question_alignment(ms, out)
        d_claim_evidence(ms, out)
        d_paragraph_flow(ms, out)
        d_repetition(ms, out)
        d_claim_boundary(ms, out)
    findings = []
    for i, (cat, sev, sec, para, quote, problem, action) in enumerate(out, 1):
        findings.append(finding("F%03d" % i, cat, sev,
                                sec or {}, para or 0, quote, problem,
                                "机检规则命中（正则/结构统计，规则口径见 problem 字段）", action))
    per = {c: sum(1 for f in findings if f["category"] == c) for c in CATEGORIES}
    return {"arm": "ablated_generic" if ablate else "skill_full",
            "ablated": ablate,
            "disabled_categories": CATEGORIES if ablate else [],
            "manuscript_stats": ms.get("stats", {}),
            "findings": findings,
            "summary": {"per_category": per,
                        "fail_count": len(findings),
                        "fail_count_definition": "每条 finding 记一次 FAIL（同一校验器两臂可机器比对）"}}


def main():
    t0 = __import__("time").time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", default="/app/work/manuscript.json")
    ap.add_argument("--out", default="/app/work/findings_machine.json")
    ap.add_argument("--ablate", action="store_true", help="只跑消融臂（表层检测）")
    try:
        args = ap.parse_args()
    except SystemExit:
        print(json.dumps({"ok": False, "note": "参数错误"}))
        return 0
    try:
        ms = json.load(open(args.manuscript, encoding="utf-8"))
        rep = run_arm(ms, ablate=args.ablate)
    except Exception as e:
        rep = {"arm": "ablated_generic" if args.ablate else "skill_full",
               "ablated": args.ablate, "error": str(e), "findings": [],
               "summary": {"per_category": {}, "fail_count": 0}}
    try:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(rep, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        rep["written"] = True
    except Exception as e:
        rep["written"] = False
        rep["write_error"] = str(e)
    print(json.dumps({"ok": True, "out": args.out, "arm": rep["arm"],
                      "fail_count": rep["summary"]["fail_count"]}, ensure_ascii=False))
    _rlog.log_call("structure_check", argv=sys.argv[1:], seconds=__import__("time").time() - t0,
                   extra={"fail_count": rep["summary"]["fail_count"], "ablate": args.ablate})
    return 0


if __name__ == "__main__":
    sys.exit(main())
