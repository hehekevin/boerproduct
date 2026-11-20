#!/usr/bin/env python3
"""mathml2latex.py — 零依赖 MathML→LaTeX 转换与公式目录扫描（加固版）。

设计原则：**产物非空是生命线**。任何输入（合法 XML、带 DOCTYPE 的出版商 XML、
命名实体 XML、畸形截断 XML、纯文本公式）都必须产出非空结果，绝不静默返回空串。

子命令：
    --scan PATH        枚举 XML 中全部 <math> 节点：formula_id、文本摘要 → JSON
    --convert PATH     逐节点转换为 LaTeX → JSON（失败节点降级为文本拼接，标 partial）
    --text-file PATH   把整个文件当纯文本公式做规范化转 LaTeX（无 XML 时的通道）

容错链（逐级降级，每级都保证非空输出）：
  1. 标准 ET 解析原文
  2. 去 DOCTYPE + 命名/数字实体解码 + 裸 &/< 转义后再解析
  3. 正则提取 <math>…</math> / <math …/> / 未闭合 <math 块
  4. 块级解析失败 → 剥标签取纯文本 → 文本规范化为 LaTeX（标 partial+warning）
  5. 结构转换成功但 LaTeX 为空 → itertext 文本拼接回退（标 partial+warning）
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
import xml.etree.ElementTree as ET

GREEK = {
    "alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma", "delta": r"\delta",
    "epsilon": r"\epsilon", "varepsilon": r"\varepsilon", "zeta": r"\zeta",
    "eta": r"\eta", "theta": r"\theta", "vartheta": r"\vartheta", "iota": r"\iota",
    "kappa": r"\kappa", "lambda": r"\lambda", "mu": r"\mu", "nu": r"\nu", "xi": r"\xi",
    "pi": r"\pi", "rho": r"\rho", "sigma": r"\sigma", "tau": r"\tau",
    "upsilon": r"\upsilon", "phi": r"\phi", "varphi": r"\varphi", "chi": r"\chi",
    "psi": r"\psi", "omega": r"\omega", "Gamma": r"\Gamma", "Delta": r"\Delta",
    "Theta": r"\Theta", "Lambda": r"\Lambda", "Xi": r"\Xi", "Pi": r"\Pi",
    "Sigma": r"\Sigma", "Phi": r"\Phi", "Psi": r"\Psi", "Omega": r"\Omega",
}
_GREEK_RE = re.compile(
    r"(?<!\\)\b(" + "|".join(sorted(GREEK, key=len, reverse=True)) + r")\b")
OPS = {
    "+": "+", "-": "-", "\u2212": "-", "*": r"\cdot", "\u00d7": r"\times",
    "=": "=", "\u2260": r"\neq", "<": "<", ">": ">", "\u2264": r"\leq",
    "\u2265": r"\geq", "\u00b1": r"\pm", "\u2215": "/", "\u002f": "/",
    "\u2211": r"\sum", "\u220f": r"\prod", "\u222b": r"\int", "\u221e": r"\infty",
    "\u2192": r"\to", "\u21d2": r"\Rightarrow", "\u2202": r"\partial",
    "\u2248": r"\approx", "\u221d": r"\propto", "\u2208": r"\in",
    "\u221a": r"\sqrt", "\u2032": "'",
}
FUNCS = {"sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "log": r"\log",
         "ln": r"\ln", "exp": r"\exp", "max": r"\max", "min": r"\min", "lim": r"\lim"}
_UNICODE_OPS = [(ch, rep) for ch, rep in OPS.items()
                if not (ch.isascii() and ch.isalnum())]


def _local(tag) -> str:
    return tag.split("}")[-1] if "}" in str(tag) else str(tag)


# ---------------------------------------------------------------- 文本规范化
def text2latex(s: str) -> str:
    """纯文本公式 → 尽力而为的 LaTeX。保守规则，保证非空回退。"""
    out = s
    for ch, rep in _UNICODE_OPS:
        out = out.replace(ch, " " + rep + " ")
    out = _GREEK_RE.sub(lambda m: GREEK[m.group(0)], out)
    # 多字符下标加花括号：X_ab → X_{ab}（不动已有 ^{} _{}）
    out = re.sub(r"_([A-Za-z0-9]{2,})(?![\}\w])", r"_{\1}", out)
    out = re.sub(r"\^([A-Za-z0-9]{2,})(?![\}\w])", r"^{\1}", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _strip_tags_to_text(block: str) -> str:
    txt = re.sub(r"<[^>]*>", " ", block)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


# ---------------------------------------------------------------- MathML 转换
def convert(node) -> tuple[str, list]:
    """返回 (latex, warnings)。"""
    warns: list[str] = []
    tag = _local(node.tag)
    if tag in ("semantics",):
        for child in node:
            if _local(child.tag) != "annotation":
                return convert(child)
        return "", warns

    if tag in ("math", "mrow", "mstyle", "mpadded", "maction"):
        parts = []
        for ch in node:
            s, w = convert(ch)
            parts.append(s)
            warns.extend(w)
        return " ".join(p for p in parts if p), warns

    if tag == "mi":
        txt = (node.text or "").strip()
        if not txt:
            return "", warns
        if txt in FUNCS:
            return FUNCS[txt], warns
        if txt in GREEK:
            return GREEK[txt], warns
        if len(txt) > 1:
            return r"\mathrm{%s}" % txt, warns
        return txt, warns

    if tag == "mn":
        return (node.text or "").strip(), warns

    if tag == "mo":
        txt = (node.text or "").strip()
        return OPS.get(txt, txt), warns

    if tag == "mtext":
        txt = (node.text or "").strip()
        return r"\text{%s}" % txt if txt else "", warns

    if tag == "ms":
        return r"\text{%s}" % (node.text or ""), warns

    if tag == "mfrac":
        kids = [c for c in node if _local(c.tag) != "sep"]
        if len(kids) != 2:
            warns.append("mfrac 子节点数=%d" % len(kids))
        num, _ = convert(kids[0]) if kids else ("", [])
        den, _ = convert(kids[1]) if len(kids) > 1 else ("", [])
        return r"\frac{%s}{%s}" % (num, den), warns

    if tag == "msqrt":
        inner, _ = convert(_first_content(node))
        return r"\sqrt{%s}" % inner, warns

    if tag == "mroot":
        kids = list(node)
        base, _ = convert(kids[0]) if kids else ("", [])
        idx, _ = convert(kids[1]) if len(kids) > 1 else ("", [])
        return r"\sqrt[%s]{%s}" % (idx, base), warns

    if tag in ("msup", "msub", "msubsup"):
        kids = list(node)
        base, _ = convert(kids[0]) if kids else ("", [])
        sup = sub = ""
        if tag in ("msup", "msubsup") and len(kids) > 1:
            sup, _ = convert(kids[1])
        if tag in ("msub", "msubsup") and len(kids) > (2 if tag == "msubsup" else 1):
            sub, _ = convert(kids[-1])
        out = base
        if tag == "msup":
            out += "^{%s}" % sup
        elif tag == "msub":
            out += "_{%s}" % sub
        else:
            out += "_{%s}^{%s}" % (sub, sup)
        return out, warns

    if tag == "mfenced":
        open_c = node.get("open", "(")
        close_c = node.get("close", ")")
        parts = []
        for ch in node:
            s, w = convert(ch)
            parts.append(s)
            warns.extend(w)
        return open_c + " ".join(p for p in parts if p) + close_c, warns

    if tag in ("mtable", "mtr", "mtd"):
        warns.append("%s 转换为矩阵支持有限" % tag)
        parts = []
        for ch in node:
            s, w = convert(ch)
            parts.append(s)
            warns.extend(w)
        return " ".join(p for p in parts if p), warns

    if tag in ("annotation", "annotation-xml"):
        return "", warns

    warns.append("未知元素 %s（按内容拼接）" % tag)
    parts = []
    for ch in node:
        s, w = convert(ch)
        parts.append(s)
        warns.extend(w)
    if node.text and node.text.strip():
        parts.insert(0, node.text.strip())
    return " ".join(p for p in parts if p), warns


def _first_content(node):
    for ch in node:
        return ch
    return node


# ---------------------------------------------------------------- 容错解析
_BUILTINS = {"amp": "\x01", "lt": "\x02", "gt": "\x03", "quot": "\x04", "apos": "\x05"}
_BUILTIN_RESTORE = {v: "&%s;" % k for k, v in _BUILTINS.items()}


def _preprocess_xml(text: str) -> str:
    """出版商 XML 常含 DOCTYPE 与命名实体（&eta; &Delta; &plusmn;…），
    标准 ET 不认这些实体。先把 XML 内置实体换占位符，用 html.unescape
    把其余命名/数字实体解成 Unicode 字符，再恢复内置实体并转义裸 & 与裸 <。"""
    for name, tok in _BUILTINS.items():
        text = text.replace("&%s;" % name, tok)
    text = _html.unescape(text)
    text = text.replace("&", "&amp;")
    for tok, orig in _BUILTIN_RESTORE.items():
        text = text.replace(tok, orig)
    text = re.sub(r"<(?![A-Za-z/!?])", "&lt;", text)
    return text


def _strip_doctype(text: str) -> str:
    return re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", text, flags=re.S)


def _parse_tolerant(text: str) -> ET.Element:
    errors = []
    for candidate in (text, _preprocess_xml(_strip_doctype(text))):
        try:
            return ET.fromstring(candidate)
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError("; ".join(errors[:2]))


# 三级块提取：闭合块 → 自闭合块 → 未闭合尾块（截断 XML 的最后防线）。
# 允许命名空间前缀（<m:math>、<mathml:math>）。
_NS = r"(?:[A-Za-z_][\w.-]*:)?"
_MATH_BLOCK_RES = [
    re.compile(r"<%smath\b[^>]*>.*?</%smath\s*>" % (_NS, _NS), re.S | re.I),
    re.compile(r"<%smath\b[^>]*/>" % _NS, re.I),
]
# 级别2（未闭合尾块）：按开标签逐个定位，取该位置到文件尾——截断 XML 的最后防线
_MATH_OPEN_RE = re.compile(r"<%smath\b[^>]*>" % _NS, re.I)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def iter_math_items(path: str):
    """产出 (formula_id, node_or_None, text_or_None, note)。

    解析成功 → (fid, element, None, note)；块级解析失败 → (fid, None, 纯文本, note)。
    调用方对 text 非空的项做 text2latex，保证每个识别到的公式都有非空产物。
    """
    raw = _read(path)

    try:
        root = _parse_tolerant(raw)
        found = False
        for math in root.iter():
            if _local(math.tag) == "math":
                found = True
                fid = (math.get("id")
                       or math.get("{http://www.w3.org/XML/1998/namespace}id"))
                yield fid, math, None, ""
        if found:
            return
    except RuntimeError:
        pass  # 落到正则回退

    blocks = []
    consumed = [0]  # 已覆盖到的原文偏移，避免重叠块重复计数
    for level, rex in enumerate(_MATH_BLOCK_RES):
        for m in rex.finditer(raw):
            if m.start() < consumed[0]:
                continue
            consumed[0] = m.end()
            blocks.append((level, m.group(0)))
    for m in _MATH_OPEN_RE.finditer(raw):
        if m.start() < consumed[0]:
            continue
        consumed[0] = len(raw)
        blocks.append((2, raw[m.start():]))
    notes = ["XML 整体解析失败，正则回退提取 %d 个 math 块" % len(blocks)] if blocks else []

    for i, (level, block) in enumerate(blocks):
        wrapped = ("<root xmlns:m=\"http://www.w3.org/1998/Math/MathML\">%s</root>"
                   % _preprocess_xml(_strip_doctype(block)))
        try:
            node = ET.fromstring(wrapped)[0]
            fid = (node.get("id")
                   or node.get("{http://www.w3.org/XML/1998/namespace}id"))
            note = "正则回退(级别%d)" % level if level else ""
            yield fid, node, None, note
        except Exception:
            txt = _strip_tags_to_text(block)
            note = "块级解析失败，降级为文本提取（截断/畸形 XML）"
            if level == 2:
                note = "未闭合 math 块，降级为文本提取（截断 XML）"
            yield None, None, txt, note


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", dest="scan", default=None)
    ap.add_argument("--convert", dest="conv", default=None)
    ap.add_argument("--text-file", dest="textfile", default=None,
                    help="把整份文件当纯文本公式规范化为 LaTeX（无 XML 时的通道）")
    ap.add_argument("--fallback", default=None,
                    help="主文件 0 节点时尝试的备用文件（如 publisher-source.xml）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    path = args.textfile or args.conv or args.scan
    if not path:
        print("需要 --scan / --convert / --text-file 之一")
        return 2

    notes = []
    items = []
    try:
        if args.textfile:
            txt = _strip_tags_to_text(_read(path))
            items.append({"formula_id": "text-1", "index": 0,
                          "latex": text2latex(txt), "warnings": [],
                          "conversion": "partial" if txt else "failed",
                          "ambiguity_notes": "纯文本通道：结构转换不可用，文本规范化结果" if txt else "空输入"})
        else:
            try:
                entries = list(iter_math_items(path))
            except Exception as e:
                entries = []
                notes.append("读取/解析失败: %s" % e)
            if not entries and args.fallback:
                notes.append("主文件 0 个 math 节点，回退尝试 %s" % args.fallback)
                try:
                    entries = list(iter_math_items(args.fallback))
                except Exception as e:
                    notes.append("回退文件也失败: %s" % e)
                    entries = []

            for i, (fid, node, txt, note) in enumerate(entries):
                fid = fid or "math-%d" % i
                item = {"formula_id": fid, "index": i}
                if note:
                    notes.append("[%s] %s" % (fid, note))
                    item["warnings"] = [note]
                else:
                    item["warnings"] = []
                if args.scan:
                    if node is not None:
                        item["text_summary"] = re.sub(
                            r"\s+", " ", "".join(node.itertext())).strip()[:200]
                    else:
                        item["text_summary"] = (txt or "")[:200]
                else:
                    latex, warns = ("", [])
                    if node is not None:
                        try:
                            latex, warns = convert(node)
                        except Exception as e:
                            warns = ["结构转换异常: %s" % e]
                            latex = ""
                    if not latex.strip() and node is not None:
                        txt = re.sub(r"\s+", " ", " ".join(node.itertext())).strip()
                        latex = text2latex(txt)
                        warns.append("结构转换为空，回退为文本拼接")
                    elif not latex.strip() and txt:
                        latex = text2latex(txt)
                        warns.append("结构转换不可用，文本规范化结果")
                    item["latex"] = latex
                    item["warnings"] = item.get("warnings", []) + warns
                    item["conversion"] = ("full" if not warns and latex.strip()
                                          else ("partial" if latex.strip() else "failed"))
                    if item["conversion"] != "full":
                        item.setdefault("ambiguity_notes",
                                        "；".join(item["warnings"]) or "降级转换，需人工校对")
                items.append(item)
    except Exception as e:  # 兜底：任何意外也写 JSON，不留空产物
        notes.append("意外错误: %s" % e)

    payload = {"source": path, "fallback": args.fallback, "notes": notes,
               "math_nodes": len(items), "items": items}
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print("[mathml2latex] 输出写入失败: %s" % e)
        return 1
    n_fail = sum(1 for x in items if x.get("conversion") == "failed")
    print("[mathml2latex] %d 个公式对象（failed=%d）%s → %s" % (
        len(items), n_fail, ("；" + "；".join(notes)) if notes else "", args.out))
    return 0 if not n_fail else 3


if __name__ == "__main__":
    sys.exit(main())
