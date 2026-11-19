#!/usr/bin/env python3
"""validate_np.py: 结构校验 TriG 格式的 nanopublication 文件（仅标准库）。

用法:
    python validate_np.py nanopubs.trig

检查项:
  1) 每个 np 的四图齐全且非空（head/assertion/provenance/pubinfo）
  2) head 图包含 a np:Nanopublication 与三条 np:has* 属性
  3) provenance 图包含 prov:wasDerivedFrom 与 npex: 六要素
  4) pubinfo 图包含 pav:createdBy / prov:generatedAtTime / dcterms:license
  5) 花括号配平；断言谓词不是字面量
输出: 逐 np 的 PASS/FAIL 列表与汇总；有 FAIL 时退出码 1。
限制: 结构级启发式检查，面向本 Skill 生成约定（片段命名 assertion/provenance/
pubinfo/head），不做完整 RDF 解析；通过后仍需按自检清单做语义核对。
"""
import re
import sys

FRAGS = ("assertion", "provenance", "pubinfo", "head")

def split_base_frag(uri):
    for f in FRAGS:
        for sep in ("#", ":", "/"):
            suf = sep + f
            if uri.endswith(suf) and len(uri) > len(suf):
                cut = len(suf) if sep != ":" else len(f)
                return uri[:-cut], f
    return uri, "root"

def clean_lines(text):
    out = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)

def main():
    if len(sys.argv) < 2:
        print("usage: python validate_np.py file.trig")
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        raw = f.read()
    clean = clean_lines(raw)

    if clean.count("{") != clean.count("}"):
        print("FAIL: 花括号不配平")
        sys.exit(1)

    blocks = []
    for m in re.finditer(r'([^\s{}]+)\s*\{', clean):
        start = m.end() - 1
        depth = 0
        end = None
        for i in range(start, len(clean)):
            if clean[i] == "{":
                depth += 1
            elif clean[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            print("FAIL: 图块未闭合: " + m.group(1))
            sys.exit(1)
        blocks.append((m.group(1), clean[start + 1:end]))
    if not blocks:
        print("FAIL: 未找到任何命名图块")
        sys.exit(1)

    nps = {}
    order = []
    for uri, body in blocks:
        base, frag = split_base_frag(uri)
        if base not in nps:
            nps[base] = {}
            order.append(base)
        nps[base][frag] = (uri, body)

    results = []
    for base in order:
        parts = {k: v[1] for k, v in nps[base].items()}
        issues = []
        head_frag = None
        for frag, body in parts.items():
            if "np:Nanopublication" in body:
                head_frag = frag
        if head_frag is None:
            issues.append("缺少 head（无 np:Nanopublication 声明）")
        else:
            head_body = parts[head_frag]
            for prop in ("np:hasAssertion", "np:hasProvenance", "np:hasPublicationInfo"):
                if prop not in head_body:
                    issues.append("head 缺 " + prop)
        for f in ("assertion", "provenance", "pubinfo"):
            if f not in parts:
                issues.append("缺图: " + f)
            elif not parts[f].strip():
                issues.append(f + " 图为空")
        if "provenance" in parts:
            pv = parts["provenance"]
            for prop in ("prov:wasDerivedFrom", "npex:evidenceQuote", "npex:evidenceLocation",
                         "npex:pageBasis", "npex:assertionStrength", "npex:hedgingMarkers",
                         "npex:evidenceType"):
                if prop not in pv:
                    issues.append("provenance 缺 " + prop)
        if "pubinfo" in parts:
            pi = parts["pubinfo"]
            for prop in ("pav:createdBy", "prov:generatedAtTime", "dcterms:license"):
                if prop not in pi:
                    issues.append("pubinfo 缺 " + prop)
        if "assertion" in parts:
            for line in parts["assertion"].splitlines():
                seg = line.strip().split()
                if len(seg) >= 2 and seg[1].startswith('"'):
                    issues.append("assertion 谓词疑似字面量: " + line.strip()[:40])
        status = "PASS" if not issues else "FAIL"
        results.append((base, status, issues))

    npass = sum(1 for _, s, _ in results if s == "PASS")
    for base, status, issues in results:
        print("[%s] %s" % (status, base))
        for it in issues:
            print("      - " + it)
    print("\n汇总: %d/%d 通过" % (npass, len(results)))
    sys.exit(0 if npass == len(results) else 1)

if __name__ == "__main__":
    main()
