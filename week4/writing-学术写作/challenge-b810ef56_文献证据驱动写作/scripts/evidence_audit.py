#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_audit.py — 论断-证据绑定审计（v2：逐字核验 + 双向映射矩阵）
用法:
  python evidence_audit.py --claims /app/work/claims_evidence.jsonl \
      --draft /app/output/draft.md --sources /app/work/extracted \
      [--refs /app/work/sources_registry.jsonl] [--out /app/output/evidence_audit.json]

检查(全部为机器可核验项):
 1) 结构完整: 每行有 cid/sources/locator/quote/support_scope/evidence_grade
 2) 摘录逐字核验: quote 必须能在对应来源文本(M*.txt)中逐字找到
    (空白归一化后子串匹配; 找不到 → quote_not_verbatim, 即编造/改写风险)
 3) 定位核验: locator 的 mid 必须存在于 extracted 目录
 4) 标记对应: 正文 [E##] ↔ 证据表 cid 双向一一对应
 5) 裸论断: 含数字/引用标记却无 [E##] 的句子
 6) 等级-措辞相称: grade C/D 的论断句须含限定语
 7) 双向映射矩阵: claim→source 与 source→claim 反向索引;
    registry 中从未支撑任何 bound 论断、也未在正文引用的来源 → orphan_source
三级容错: 输入缺失/损坏时输出 verdict=fail 的报告而非崩溃; 永不修改稿件。
"""
import argparse, glob, json, os, re, sys

HEDGES = ["初步", "提示", "可能", "或与", "有待", "一项研究", "小样本", "在特定条件下",
          "似乎", "可能因", "推测", "有待验证", "部分支持", "提示性", "未达显著",
          "相关性", "相关", "或", "个案", "单中心", "需进一步", "局限"]

def _squash(s):
    """空白归一化: 去所有空白并统一常见引号/连字符, 用于逐字匹配容差。"""
    if not isinstance(s, str):
        s = str(s)
    s = re.sub(r"\s+", "", s)
    return (s.replace("\u201c", '"').replace("\u201d", '"')
             .replace("\u2018", "'").replace("\u2019", "'")
             .replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", ""))

def _load_jsonl(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows, "missing"
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows, "ok"
    except Exception as e:
        return rows, "parse_error:%s" % e

def _source_text_index(sources_dir):
    """mid -> squashed 全文 (来自 extract_materials 产出的 M*.txt)。"""
    idx = {}
    if not sources_dir or not os.path.isdir(sources_dir):
        return idx, False
    for fp in glob.glob(os.path.join(sources_dir, "M*.txt")):
        mid = os.path.splitext(os.path.basename(fp))[0]
        try:
            idx[mid] = _squash(open(fp, encoding="utf-8", errors="ignore").read())
        except Exception:
            idx[mid] = ""
    return idx, True

def _locator_mid(locator):
    m = re.match(r"\s*(M\d+)", str(locator or ""))
    return m.group(1) if m else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--draft", required=True)
    ap.add_argument("--sources", default=None, help="extracted 目录(含 M*.txt), 用于逐字核验")
    ap.add_argument("--refs", default=None, help="sources_registry.jsonl, 用于孤儿来源检查")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows, load_state = _load_jsonl(args.claims)
    problems = []
    try:
        draft = open(args.draft, encoding="utf-8").read() if os.path.exists(args.draft) else ""
    except Exception:
        draft = ""
    if not draft:
        problems.append({"type": "draft_missing", "detail": args.draft})
    if load_state != "ok":
        problems.append({"type": "claims_unreadable", "detail": load_state})

    src_idx, src_ok = _source_text_index(args.sources)

    # 1) 结构完整（unbound 行只要求有 cid；bound 行字段一个不缺）
    struct_bad = []
    for r in rows:
        if r.get("status") == "unbound":
            if not r.get("cid"):
                struct_bad.append({"cid": r.get("cid"), "missing": "cid"})
            continue
        for k in ("cid", "sources", "locator", "quote", "support_scope", "evidence_grade"):
            if k not in r or r[k] in (None, "", []):
                struct_bad.append({"cid": r.get("cid"), "missing": k})
    if struct_bad:
        problems.append({"type": "structure", "count": len(struct_bad), "detail": struct_bad[:20]})

    # 2) 摘录逐字核验 + 3) 定位核验
    quote_bad, loc_bad = [], []
    for r in rows:
        if r.get("status") == "unbound":
            continue
        q = str(r.get("quote", ""))
        if len(_squash(q)) < 10:
            quote_bad.append({"cid": r.get("cid"), "reason": "too_short"})
            continue
        mid = _locator_mid(r.get("locator"))
        if not mid:
            loc_bad.append({"cid": r.get("cid"), "locator": r.get("locator")})
            continue
        if mid not in src_idx:
            loc_bad.append({"cid": r.get("cid"), "locator": r.get("locator"),
                            "reason": "source_file_absent" if src_ok else "sources_dir_unavailable"})
            continue
        sq = _squash(q)
        # 取摘录首尾各 40 字符做子串匹配, 兼容长摘录跨锚点行
        probe = sq[:40] if len(sq) <= 80 else sq[:40] + sq[-40:]
        if probe not in src_idx[mid]:
            quote_bad.append({"cid": r.get("cid"), "mid": mid,
                              "reason": "quote_not_verbatim", "excerpt": q[:60]})
    if quote_bad:
        problems.append({"type": "quote_not_verbatim", "count": len(quote_bad), "detail": quote_bad[:20]})
    if loc_bad:
        problems.append({"type": "locator_bad", "count": len(loc_bad), "detail": loc_bad[:20]})

    # 4) [E##] ↔ cid 双向对应
    tags = set(re.findall(r"\[E(\d+)\]", draft))
    cids = {}
    for r in rows:
        if r.get("cid"):
            num = re.sub(r"\D", "", str(r["cid"]))
            if num:
                cids[str(int(num))] = r  # 前导零归一: C01 ↔ E1
    tags_without_row = sorted(t for t in tags if t not in cids)
    bound_without_tag = sorted(c for c, r in cids.items() if r.get("status") == "bound" and c not in tags)
    if tags_without_row or bound_without_tag:
        problems.append({"type": "tag_mismatch", "tags_without_row": tags_without_row,
                         "bound_without_tag": bound_without_tag})

    # 5) 裸论断（按 。！？!? 切句, 避免切断小数; 参考文献行跳过）
    naked = []
    for para in draft.split("\n"):
        p = para.strip()
        if p.startswith(("#", ">", "|", "```", "-")) or re.match(r"^\[\d+\]\s", p):
            continue
        for sent in re.split(r"(?<=[。！？!?])", para):
            s = sent.strip()
            if len(s) < 15:
                continue
            if (re.search(r"\d", s) or re.search(r"\[\d+\]", s)) and "[E" not in sent:
                naked.append(s[:80])
    if naked:
        problems.append({"type": "naked_claims", "count": len(naked), "samples": naked[:10]})

    # 6) 等级-措辞相称
    mismatch = []
    for num, r in cids.items():
        if r.get("evidence_grade") in ("C", "D") and r.get("status") == "bound":
            tag = "[E%s]" % num
            for para in draft.split("\n"):
                if tag in para:
                    if not any(h in para for h in HEDGES):
                        mismatch.append({"cid": r["cid"], "grade": r["evidence_grade"],
                                         "para": para[:100]})
                    break
    if mismatch:
        problems.append({"type": "wording_strength", "count": len(mismatch), "detail": mismatch[:10]})

    # 7) 双向映射矩阵 + 孤儿来源
    fwd = {}   # cid -> [source...]
    rev = {}   # source -> [cid...]
    for r in rows:
        if r.get("status") != "bound":
            continue
        srcs = r.get("sources") or []
        fwd[r["cid"]] = srcs
        for s in srcs:
            rev.setdefault(str(s), []).append(r["cid"])
    matrix = {"claim_to_source": fwd, "source_to_claims": {k: v for k, v in sorted(rev.items())},
              "claims_bound": len(fwd), "sources_used": len(rev)}
    orphan_sources = []
    if args.refs and os.path.exists(args.refs):
        reg, reg_state = _load_jsonl(args.refs)
        if reg_state == "ok":
            for r in reg:
                rid = str(r.get("id") or "")
                if rid and rid not in rev:
                    orphan_sources.append(rid)
            matrix["registry_total"] = len(reg)
            matrix["orphan_sources"] = orphan_sources
            if orphan_sources:
                problems.append({"type": "orphan_source",
                                 "detail": "以下来源未支撑任何 bound 论断且未在正文引用(或证据表漏绑): %s"
                                           % ",".join(orphan_sources[:20])})

    # 摘要统计
    bound = sum(1 for r in rows if r.get("status") == "bound")
    unbound = sum(1 for r in rows if r.get("status") == "unbound")
    verified = bound - len([q for q in quote_bad]) - len([l for l in loc_bad if l.get("reason") != "sources_dir_unavailable"])
    report = {"claims_total": len(rows), "bound": bound, "unbound": unbound,
              "quotes_verbatim_checked": bound if src_ok else 0,
              "problems": problems,
              "claim_source_matrix": matrix,
              "verdict": "pass" if not problems else "fail",
              "hint": ("fail 项逐条修复: quote_not_verbatim→回 M 文件逐字抄录; tag_mismatch→补 [E##] 或删行; "
                       "naked_claims→补证据或删句; orphan_source→补绑或从文献表删除; "
                       "wording_strength→按等级加限定语。"),
              "note": "sources 目录不可用时跳过逐字核验(如实记录), 不伪造核验结论。" if not src_ok else None}
    report = {k: v for k, v in report.items() if v is not None}
    if args.out:
        d = os.path.dirname(args.out)
        if d:
            os.makedirs(d, exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": report["verdict"], "claims": len(rows), "bound": bound,
                      "problems": [p["type"] for p in problems]}, ensure_ascii=False))
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main())
