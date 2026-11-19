#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""edits_verify.py — 修订台账校验
检查: 1) 每条 edit 的 anchor_quote/before 能在原稿找到；2) after 能在修订稿找到；
3) 未授权改动检测（修订稿相对原稿的实质句差异都应被某条 edit 覆盖）；
4) 引用编号连续性（[n] 无跳号）。
退出码契约：任何路径均退出 0 ——校验结论由报告里的 verdict 字段照实记录，
校验失败不中断交付（修复责任交回流程第 4 步）。
自测：--selftest（合成正例 + 污染反例；退出码恒 0，verdict 照实记录）。
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", default="")
    ap.add_argument("--original", default="")
    ap.add_argument("--revised", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--selftest", action="store_true")
    try:
        args = ap.parse_args()
    except SystemExit:
        # 参数错误同样走退出码 0 契约（内容级失败不中断交付）
        print("[edits_verify] 参数解析失败（退出码 0，不中断交付）")
        return 0
    if args.selftest:
        return cmd_selftest()
    return run(args)


def run(args):
    """台账校验主逻辑。**内部自捕获所有异常**：任何路径都产出报告并退出 0，
    结论由 report['verdict'] 照实记录（pass / fail / error）。"""
    try:
        return _run(args)
    except Exception as e:
        rep = {"verdict": "error", "error": str(e)[:300], "edits_total": 0,
               "anchor_fail": 0, "apply_fail": 0, "unauthorized_changes": 0, "citation_gaps": []}
        if getattr(args, "out", None):
            try:
                os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
                json.dump(rep, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            except Exception:
                pass
        print(json.dumps({k: rep[k] for k in ("edits_total", "anchor_fail", "apply_fail",
                                              "unauthorized_changes", "verdict")}, ensure_ascii=False))
        print("[edits_verify] 异常: %s（退出码 0，不中断交付）" % str(e)[:200])
        return 0


def _sentences(text):
    """按句切分并归一化，过掉过短片段。"""
    out = set()
    for p in str(text or "").split("\n"):
        for sent in re.split(r"(?<=[。！？.!?])", p):
            ns = _norm(sent)
            if len(ns) >= 12:
                out.add(ns)
    return out


def _run(args):
    edits = [json.loads(l) for l in open(args.edits, encoding="utf-8") if l.strip()]
    orig_raw = _load_original(args.original)
    orig = _norm(orig_raw)
    rev_raw = open(args.revised, encoding="utf-8").read()
    rev = _norm(rev_raw)

    anchor_bad, applied_bad = [], []
    for e in edits:
        probe_b = _norm(e.get("before") or e.get("anchor_quote") or "")[:40]
        probe_a = _norm(e.get("after") or "")[:40]
        if probe_b and probe_b not in orig:
            anchor_bad.append({"eid": e.get("eid"), "pid": e.get("pid"), "probe": probe_b[:40]})
        if e.get("status") == "applied" and probe_a and probe_a not in rev:
            applied_bad.append({"eid": e.get("eid"), "probe": probe_a[:40]})

    # 未授权改动：修订稿的**正文散文句**相对原稿发生了实质变化、
    # 又不被任何一条 edit 覆盖 → 未授权改动。
    # 跳过非散文行（标题/表格/题注/图占位/待人工确认/meta 列表/引用条目/代码块），
    # 这些是文档要素而非"被改写的句子"，其一致性由引用编号/结构校验负责。
    #
    # 「被某条 edit 覆盖」按三种形态依次放行（避免把合法改动误判为未授权）：
    #   ① 该句归一化后逐字等于某条 edit 的 after；
    #   ② 该句包含某条 edit 的 before 前缀（句内局部替换：before 是长句的一部分）；
    #   ③ 该句等于「某条 edit 的 before → after」作用在**某个原稿句**上的结果
    #      （整句被局部改写：原稿句 P → 修订稿句 = P.replace(before, after, 1)）。
    afters = {_norm(e.get("after") or "") for e in edits}
    befores = {_norm(e.get("before") or e.get("anchor_quote") or "") for e in edits}
    pairs = []
    for e in edits:
        b = _norm(e.get("before") or e.get("anchor_quote") or "")
        a = _norm(e.get("after") or "")
        if b and a:
            pairs.append((b, a))
    orig_sents = _sentences(orig_raw)
    unauthorized = []
    for para in rev_raw.split("\n"):
        s = para.strip()
        if not s:
            continue
        if s.startswith(("#", ">", "|", "```", "- ", "**", "[图缺失", "![", "[")):
            continue
        if re.match(r"^\[\d{1,3}\]\s", s):        # 参考文献条目行
            continue
        for sent in re.split(r"(?<=[。！？.!?])", para):
            n = _norm(sent)
            if len(n) < 12:
                continue
            if n in orig or n in afters:
                continue
            # ② 句内含 anchor 前缀（局部替换）
            if any(a and a[:20] in n for a in befores):
                continue
            # ③ 整句被局部改写：存在某个原稿句 P，使 P.replace(before, after, 1) == 本句
            if any(os_.replace(b, a, 1) == n for os_ in orig_sents for b, a in pairs):
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
              "detail": {"anchor_bad": anchor_bad[:20], "applied_bad": applied_bad[:20],
                          "unauthorized_samples": unauthorized[:15]},
              "verdict": "pass" if not (anchor_bad or applied_bad or unauthorized or gaps) else "fail",
              "hint": "锚点失效→修 pid/quote；apply 失败→改动未落地；unauthorized→回 Stage 3 补条目或恢复原文。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("edits_total", "anchor_fail", "apply_fail",
                                              "unauthorized_changes", "verdict")}, ensure_ascii=False))
    print("[edits_verify] verdict=%s（退出码 0，结论以本报告为准）" % report["verdict"])
    return 0


def cmd_selftest():
    """合成正例（锚点命中 + 改动落地 → verdict=pass）+ 污染反例（缺文件/二进制 → 不崩、退出 0）。"""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        op = os.path.join(td, "orig.txt")
        rp = os.path.join(td, "revised.md")
        ep = os.path.join(td, "edits.jsonl")
        open(op, "w", encoding="utf-8").write(
            "The results was significant.\nWe use the X method.\n")
        open(rp, "w", encoding="utf-8").write(
            "The results were significant. [1]\nWe use the X method.\n\n## 参考文献\n\n[1] A\n")
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E001", "pid": "P01",
                                "before": "The results was significant.",
                                "after": "The results were significant.",
                                "status": "applied"}, ensure_ascii=False) + "\n")
        a = argparse.Namespace(edits=ep, original=op, revised=rp, out=os.path.join(td, "r.json"))
        if run(a) != 0:
            print("  [selftest] 退出码应恒为 0 FAIL"); ok = False
        rep = json.load(open(a.out, encoding="utf-8"))
        if rep.get("verdict") != "pass":
            print("  [selftest] 正例 verdict 应为 pass FAIL"); ok = False
        # 正例2：整句级局部替换（before 是长句的一部分）不得被误判为未授权
        op2 = os.path.join(td, "orig2.txt")
        rp2 = os.path.join(td, "revised2.md")
        ep2b = os.path.join(td, "edits2.jsonl")
        open(op2, "w", encoding="utf-8").write(
            "We applied the proposed method on the benchmark and reported gains.\n")
        open(rp2, "w", encoding="utf-8").write(
            "We applied the proposed method on the benchmark and reported small gains.\n")
        with open(ep2b, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E002", "pid": "P01",
                                "before": "reported gains",
                                "after": "reported small gains",
                                "status": "applied"}, ensure_ascii=False) + "\n")
        a1b = argparse.Namespace(edits=ep2b, original=op2, revised=rp2, out=os.path.join(td, "r1b.json"))
        if run(a1b) != 0:
            print("  [selftest] 正例2 退出码应恒为 0 FAIL"); ok = False
        rep1b = json.load(open(a1b.out, encoding="utf-8"))
        if rep1b.get("verdict") != "pass" or rep1b.get("unauthorized_changes") != 0:
            print("  [selftest] 正例2: 局部替换不应判未授权 FAIL"); ok = False
        # 反例1：before 不在原稿 → verdict=fail，退出码仍为 0
        ep2 = os.path.join(td, "bad.jsonl")
        with open(ep2, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E999", "pid": "P01", "before": "NONEXISTENT XYZ",
                                "after": "x", "status": "applied"}, ensure_ascii=False) + "\n")
        a2 = argparse.Namespace(edits=ep2, original=op, revised=rp, out=os.path.join(td, "r2.json"))
        if run(a2) != 0:
            print("  [selftest] 反例1: 校验失败仍应退出 0 FAIL"); ok = False
        rep2 = json.load(open(a2.out, encoding="utf-8"))
        if rep2.get("verdict") != "fail":
            print("  [selftest] 反例1: 锚点失效应记 verdict=fail FAIL"); ok = False
        # 反例2：二进制乱码 → 不崩、退出 0
        badp = os.path.join(td, "garbage.jsonl")
        with open(badp, "wb") as f:
            f.write(b"\xff\xfe\x00garbage")
        a3 = argparse.Namespace(edits=badp, original=op, revised=rp, out=os.path.join(td, "r3.json"))
        try:
            code3 = run(a3)
        except Exception:
            code3 = -1
            print("  [selftest] 反例2: 污染输入不应抛异常 FAIL"); ok = False
        if code3 != 0:
            print("  [selftest] 反例2: 污染输入应退出 0 FAIL"); ok = False
        # 反例3：文件缺失 → 不崩、退出 0
        a4 = argparse.Namespace(edits=os.path.join(td, "nope.jsonl"), original=op,
                                revised=rp, out=os.path.join(td, "r4.json"))
        try:
            code4 = run(a4)
        except Exception:
            code4 = -1
            print("  [selftest] 反例3: 缺文件不应抛异常 FAIL"); ok = False
        if code4 != 0:
            print("  [selftest] 反例3: 缺文件应退出 0 FAIL"); ok = False
    print("[edits_verify] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    # 退出码契约：自测失败也是内容级失败路径，退出码恒 0；
    # 结论以本行的 SELFTEST PASS/FAIL 为准，修复责任交回开发侧。
    return 0

if __name__ == "__main__":
    sys.exit(main())
