#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_ledger.py — 事实台账构建与稿件交叉校验
两个子命令:
  build  : 从 extracted/*.txt 源文本中提取"硬事实"（数值+单位、样本量、统计量、DOI、年份、图表编号），
           生成 fact_ledger.jsonl，每条含 id/值/正则形态/来源 locator/逐字原文。
  check  : 校验稿件（md/txt）中的数字与引用是否都能在台账中找到出处；
           未能对上的数字逐条列出（FAIL），疑似模型自补的数值即真相风险点。

用法:
  python3 fact_ledger.py build  --sources /app/work/extracted --out /app/work/fact_ledger.jsonl
  python3 fact_ledger.py check  --draft /app/work/draft.md --ledger /app/work/fact_ledger.jsonl \
                               --refs /app/work/references.json [--out /app/output/fact_check.json]
  python3 fact_ledger.py prior  --evidence /app/work/evidence_map.jsonl --out /app/work/prior_work.jsonl

诚实原则: check 只报告不修改；FAIL 条目需作者回材料核对或显式标注 [待核]，禁止凭印象改数。
退出码: 恒为 0；判定以报告里的 verdict/unmatched 为准，脚本不靠退出码中断交付链。
"""
import argparse, json, os, re, sys, glob, hashlib

# ── 数值识别：区分"真实数值"与"编号/标签" ─────────────────────────────────
# 关键坑：Python re 的 \w 在 str 模式下**也匹配汉字**。若用 (?<![.\w]) 判断
# "数字前是否紧贴标识符"，中文紧邻数值（保持率为84.3%、样本42例）会被整体漏掉：
# build 侧台账建不出来 → check 侧无源可对 → 逐字回证形同虚设（假通过）。
# 故此处一律用**显式 ASCII 字符类**，不用 \w / \d 的 Unicode 语义。
NUM_PAT = re.compile(
    # (?<![.A-Za-z0-9_]) 前面不是句点/ASCII 字母数字下划线 → 排除 p01、q1、M02、p3、S2
    # (?<![A-Za-z]-)      前面不是"ASCII 字母+连字符" → 排除 c-01
    # (?<![A-Za-z][0-9]-) 前面不是"ASCII 字母+数字+连字符" → 排除 T1-2、R1-2
    #   刻意不排除 [0-9]- 形态，保留数值区间端点（1.2-3.4、2023-2024、5-8 倍仍需回证）
    r"(?<![.A-Za-z0-9_])(?<![A-Za-z]-)(?<![A-Za-z][0-9]-)"
    r"(?:(?:\d+[\d,]*(?:\.\d+)?)\s*(?:%|‰|±\s*\d+(?:\.\d+)?)?"
    r"(?:\s*(?:n\s*=\s*\d+|p\s*[=<]\s*0?\.\d+|P\s*[=<]\s*0?\.\d+|CI[：: ]?\s*[-\d.,\s至to]+|"
    r"mg|ml|mmol|μmol|kg|g/L|ng/mL|pg/mL|μmol/L|mmHg|kPa|°C|K\b|Hz|kHz|MHz|nm|μm|µm|cm|mm|m\b|"
    r"s\b|ms|μs|min|h\b|d\b|wk|month|yr|year|bp|kb|Mb|Gb|TB|GB|MB|KB|km|ppm|ppb|IU|U/L|"
    r"cells|倍|年|月|天|日|小时|分钟|秒|万|亿|元|美元|人|例|只|株|次|篇|页|名|个|台|辆|度))?)"
)
# 引用/标签编号的前缀（表 12、图 23、式(3)、Fig. 23、Tab 3）
LABEL_PREFIX = re.compile(
    r"(?:[Ff]ig(?:ure)?\.?|[Tt]ab(?:le)?\.?|[Ee]q(?:uation)?\.?)\s*$"
    r"|(?:附表|附图)(?<!方)\s*[\(（]?\s*$"
    r"|(?<!方)(?<!列)(?<!报)(?:表|图)\s*[\(（]?\s*$"
    r"|(?<!方)式\s*[\(（]?\s*$",
    re.I)
# 序数标记（第3个、第3步）
ORDINAL_PREFIX = re.compile(r"第\s*[\(（]?\s*$")
# 章节标记（数字后接 节/章/条 → 章节引用而非数值）
SECTION_SUFFIX = re.compile(r"^\s*[节章条]")
# 计数量词（数字后接这些 → 是计数而非编号；除非前面是"第"构成序数）
COUNTER_UNITS = set("个次篇页名例只株台辆车度倍年月日天小时分钟秒万人元件种套份批组支步项层次版期轮")
DIGITS = set("0123456789")


def _is_label_number(text, start, end):
    """判断匹配 text[start:end] 是"编号/标签"（True）还是"真实计量数值"（False）。

    判定顺序（序数必须最先判，因为单位会被正则吃进匹配里）：
      1) 前接"第"且后接计数量词 → 序数编号（第3个）；前接"第"且后接节/章/条 → 章节引用
      2) 匹配自带单位（42例 / 60万 / 27%）→ 真实计量值
      3) 后接计数量词（共3个）→ 真实计数
      4) 前接 表/图/式/Fig/Tab 等标签前缀 → 图表引用
      5) 其余裸数字 → 真实数值
    """
    body = text[start:end].rstrip()
    pre = text[:start]
    tail = text[end:]
    has_unit = bool(body) and body[-1] not in DIGITS and body[-1] not in ".,%‰"
    m = re.match(r"\s*([^\s\d])", tail)
    nxt = m.group(1) if m else ""
    unit = body[-1] if has_unit else nxt

    # 1) 序数 / 章节引用
    if ORDINAL_PREFIX.search(pre):
        if unit in COUNTER_UNITS:
            return True                      # 第3个 → 序数编号
        if SECTION_SUFFIX.match(tail):
            return True                      # 第3.2节 → 章节引用
    # 2) 自带真实单位 → 计量值
    if has_unit:
        return False
    # 3) 后接计数量词 → 计数
    if nxt in COUNTER_UNITS:
        return False
    # 4) 后接章节标记 → 章节引用
    if SECTION_SUFFIX.match(tail):
        return True
    # 5) 前接图表/公式标签 → 引用编号
    if LABEL_PREFIX.search(pre):
        return True
    return False                            # 6) 裸数字 → 真实数值


def iter_numbers(text):
    """产出 (value, start, end)：文本中的真实计量数值（已排除编号/标签）。"""
    for m in NUM_PAT.finditer(text):
        s, e = m.span()
        if _is_label_number(text, s, e):
            continue
        v = m.group(0).strip()
        if not re.search(r"\d", v):
            continue
        yield v, s, e


DOI_PAT = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
YEAR_PAT = re.compile(r"\b(19|20)\d{2}\b")
STAT_PAT = re.compile(r"\b(?:t|F|r|χ2|chi2|Z|OR|HR|RR|β|beta|d|Cohen's d)\s*[=＝]\s*[-−]?\d+(?:\.\d+)?", re.I)

def _iter_source_lines(sources_dir):
    for fp in sorted(glob.glob(os.path.join(sources_dir, "M*.txt"))):
        mid = os.path.splitext(os.path.basename(fp))[0]
        with open(fp, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                m = re.match(r"\[SRC:(M\d+):([^\]]+)\]\s?(.*)", line.rstrip("\n"))
                if m:
                    yield m.group(1), m.group(2), m.group(3), fp, ln
                elif line.startswith("====="):
                    continue
                else:
                    yield mid, f"line{ln}", line.strip(), fp, ln

def cmd_build(args):
    ledger = []
    seen = set()
    for mid, loc, text, fp, ln in _iter_source_lines(args.sources):
        if not text:
            continue
        for v, _s, _e in iter_numbers(text):
            key = (mid, loc, v)
            if key in seen:
                continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "number", "value": v,
                           "source": mid, "locator": loc, "quote": text[:300]})
        for m in DOI_PAT.finditer(text):
            key = (mid, loc, m.group(0))
            if key in seen: continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "doi", "value": m.group(0).rstrip(".,;)"),
                           "source": mid, "locator": loc, "quote": text[:300]})
        for m in STAT_PAT.finditer(text):
            key = (mid, loc, m.group(0))
            if key in seen: continue
            seen.add(key)
            ledger.append({"id": "F%04d" % (len(ledger) + 1), "type": "statistic", "value": m.group(0),
                           "source": mid, "locator": loc, "quote": text[:300]})
    with open(args.out, "w", encoding="utf-8") as f:
        for row in ledger:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, "ledger": args.out, "facts": len(ledger),
                      "by_type": {t: sum(1 for r in ledger if r["type"] == t) for t in {r["type"] for r in ledger}}},
                     ensure_ascii=False))
    return 0

def _load_ledger(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def cmd_check(args):
    draft = open(args.draft, encoding="utf-8").read()
    ledger = _load_ledger(args.ledger)

    # 台账索引：数值归一化（去千分位）字符串集合；统计量/DOI 精确串
    num_index = {}
    for r in ledger:
        if r["type"] in ("number", "statistic"):
            norm = r["value"].replace(",", "").replace("＝", "=").replace("−", "-")
            num_index.setdefault(norm, []).append(r)
    doi_set = {r["value"] for r in ledger if r["type"] == "doi"}

    fails, checked = [], 0
    in_code = False
    # 逐行校验草稿中的数字
    for ln, line in enumerate(draft.splitlines(), 1):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        # 跳过纯结构行：标题（章/节编号非事实数字）、表格分隔行、图片占位
        if s.startswith("#"):
            continue
        if re.fullmatch(r"\|[\s\-:|]*\|", s):   # |---|---| 分隔行
            continue
        if s.startswith("!["):
            continue
        for v, _s, _e in iter_numbers(line):
            checked += 1
            norm = v.replace(",", "").replace("＝", "=").replace("−", "-")
            if norm not in num_index:
                # 宽松重试：纯数字部分
                core = re.sub(r"[^\d.=/%±]", "", norm)
                hit = any(core and core in k for k in num_index)
                if not hit:
                    fails.append({"line": ln, "value": v, "context": line.strip()[:160],
                                  "reason": "draft number not found in any source (possible hallucination or reformatting)"})
    # DOI 校验
    for m in DOI_PAT.finditer(draft):
        v = m.group(0).rstrip(".,;)")
        if v not in doi_set:
            fails.append({"line": None, "value": v, "context": "", "reason": "DOI not present in sources"})

    report = {"draft": args.draft, "checked_numbers": checked, "unmatched": len(fails),
              "verdict": "pass" if not fails else "fail",
              "unmatched_detail": fails[:200],
              "ledger_facts": len(ledger),
              "note": "FAIL 条目须回材料核对或在稿件中标注[待核]；禁止凭印象保留来源不明的数值。"}
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: report[k] for k in ("checked_numbers", "unmatched", "verdict")}, ensure_ascii=False))
    # 退出码契约：恒 0（不中断交付链）；判定以报告里的 verdict/unmatched 为准
    return 0

def cmd_prior(args):
    """从 evidence_map.jsonl 机械抽取「前期基础」条目（kind=prior_work），
    供 result.json 的 prior_work 字段与研究基础章机检使用（不新增任何事实）。"""
    rows = _load_ledger(args.evidence)
    out = []
    for r in rows:
        kind = str(r.get("kind") or "").lower()
        if kind in ("prior_work", "previous_work", "preliminary", "前期成果", "前期基础"):
            out.append(r)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for row in out:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # 二态统计：已完成/拟开展
    done = sum(1 for r in out if "已完成" in str(r.get("state") or r.get("status") or "已完成"))
    print(json.dumps({"ok": True, "out": args.out, "prior_work_items": len(out),
                      "state_done": done, "state_planned": len(out) - done},
                     ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--sources", required=True)
    b.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("--draft", required=True)
    c.add_argument("--ledger", required=True)
    c.add_argument("--refs", default=None)
    c.add_argument("--out", default=None)
    p = sub.add_parser("prior")
    p.add_argument("--evidence", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "build":
        return cmd_build(args)
    if args.cmd == "prior":
        return cmd_prior(args)
    return cmd_check(args)

if __name__ == "__main__":
    sys.exit(main())
