#!/usr/bin/env python3
"""lang_detect.py — 字形（文字系统）语言判定辅助（xling-lit-recall）。

基于显式 Unicode 字符类统计各文字系统占比并给出语种猜测。
**不使用 isalpha**（汉字 isalpha()==True，会误判），全部用显式区间：
  han（汉字）\u3400-\u9fff、kana（假名）\u3040-\u30ff\u31f0-\u31ff、
  hangul \uac00-\ud7af、cyrillic \u0400-\u04ff、greek \u0370-\u03ff、
  arabic \u0600-\u06ff、hebrew \u0590-\u05ff、latin \u0041-\u024f。
拉丁字母内的语种细分用小型停用词表辅助（en/pt/es/fr/de/it），
区分不了时按占比诚实返回 multi/unknown，不冒充确定结论。

用法：
    python3 lang_detect.py --text "ピロプトーシスと炎症性腸疾患"
    python3 lang_detect.py --file title.txt [--json]
退出码恒为 0（结论在 stdout / JSON 的 guess 字段，不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import sys

SCRIPT_RANGES = (
    ("han", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF))),
    ("kana", ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF))),
    ("hangul", ((0xAC00, 0xD7AF), (0x1100, 0x11FF))),
    ("cyrillic", ((0x0400, 0x04FF),)),
    ("greek", ((0x0370, 0x03FF),)),
    ("arabic", ((0x0600, 0x06FF),)),
    ("hebrew", ((0x0590, 0x05FF),)),
    ("latin", ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F))),
)

# 小型停用词表（辅助拉丁语种细分；每语种十余个最高频词，可复用扩展）
STOPWORDS = {
    "en": {"the", "of", "and", "in", "to", "for", "on", "with", "is", "are", "by", "from"},
    "pt": {"de", "da", "do", "dos", "das", "em", "para", "com", "uma", "que", "no", "na", "os", "as"},
    "es": {"de", "la", "el", "los", "las", "en", "para", "con", "una", "que", "del", "por"},
    "fr": {"de", "la", "le", "les", "des", "et", "en", "pour", "avec", "une", "que", "du"},
    "de": {"der", "die", "das", "und", "in", "den", "von", "mit", "für", "auf", "ein", "eine"},
    "it": {"di", "il", "la", "le", "lo", "gli", "nel", "per", "con", "una", "che", "del"},
}


def composition(text):
    """按显式字符类统计各文字系统字符数（数字/标点/空白不计）。"""
    comp = {}
    for ch in str(text or ""):
        cp = ord(ch)
        for name, ranges in SCRIPT_RANGES:
            if any(lo <= cp <= hi for lo, hi in ranges):
                comp[name] = comp.get(name, 0) + 1
                break
    return comp


def script_guess(comp):
    """字形层猜测：kana+han→ja；hangul→ko；han→zh；其余按单一主字形映射。"""
    if comp.get("kana"):
        return "ja"
    if comp.get("hangul"):
        return "ko"
    if comp.get("han"):
        return "zh"
    for name, lang in (("cyrillic", "ru"), ("greek", "el"), ("arabic", "ar"), ("hebrew", "he")):
        if comp.get(name):
            return lang
    if comp.get("latin"):
        return "latin-multi"  # 拉丁内部需停用词细分
    return "unknown"


def latin_refine(text):
    """停用词比例细分拉丁语种；无足够信号返回 None（诚实不确定）。"""
    tokens = [t.strip().lower() for t in str(text or "").split() if t.strip()]
    tokens = ["".join(ch for ch in t if (0x41 <= ord(ch) <= 0x5A) or (0x61 <= ord(ch) <= 0x7A)
                      or (0xC0 <= ord(ch) <= 0x24F)) for t in tokens]
    tokens = [t for t in tokens if t]
    if len(tokens) < 3:
        return None
    scores = {}
    for lang, sw in STOPWORDS.items():
        hits = sum(1 for t in tokens if t in sw)
        scores[lang] = hits
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] >= 2 and best[1] > scores.get("en", 0) - 99:
        total = sum(scores.values())
        if best[1] * 2 > total:
            return best[0]
    return None


def detect(text):
    comp = composition(text)
    total = sum(comp.values())
    comp_ratio = {k: round(v / total, 4) for k, v in comp.items() if v} if total else {}
    guess = script_guess(comp)
    note = None
    if guess == "latin-multi":
        refined = latin_refine(text)
        if refined:
            guess, note = refined, "latin 停用词细分"
        else:
            note = "latin 语种细分证据不足，返回 multi；请结合元数据人工判定"
    elif guess == "zh" and comp.get("kana") is None and comp.get("han"):
        note = "纯汉字字形；zh/ja 需结合假名与元数据确认"
    return {"composition": comp_ratio, "guess": guess, "note": note,
            "confidence": "high" if guess not in ("unknown", "latin-multi") else "low"}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--text", default=None)
        ap.add_argument("--file", default=None)
        ap.add_argument("--json", action="store_true", help="仅输出 JSON")
        args = ap.parse_args()
    except Exception as e:
        print("[lang_detect] 参数解析失败（已降级）: %s" % e)
        return 0
    text = args.text
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print("[lang_detect] 文件读取失败（不中断）: %s" % e)
    if not text:
        print("[lang_detect] 未提供 --text/--file，输出空判定（不中断）")
        print(json.dumps({"composition": {}, "guess": "unknown", "confidence": "low"},
                         ensure_ascii=False))
        return 0
    res = detect(text)
    print(json.dumps(res, ensure_ascii=False, indent=1) if args.json
          else "[lang_detect] guess=%s confidence=%s composition=%s note=%s"
               % (res["guess"], res["confidence"], res["composition"], res["note"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[lang_detect] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
