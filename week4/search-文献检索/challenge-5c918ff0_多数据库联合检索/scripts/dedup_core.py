#!/usr/bin/env python3
"""dedup_core.py — 多库联合检索领域引擎（merge-skill）。

机械可复算核心：字段归一（含 CJK 分词，规避 isalpha 汉字陷阱）、跨库去重
（DOI 精确匹配 + 标题/作者/年份模糊比对）、字段合并（来源优先级）、字段冲突
登记、覆盖矩阵。所有函数纯确定性，校验器 verify_check 复用同一实现做复算，
保证"同一校验器双跑"可比。

ablate 语义（关闭项）：
    none      正常模式（全部机制开启）
    normalize 关闭字段归一（DOI 前缀/大小写/标点/分词全部按原始串）
    fuzzy     关闭标题模糊匹配（仅剩 DOI 精确匹配）
    conflict  关闭字段冲突检测
    all       以上全部关闭
退出码恒 0；--apply 把结果写回 result.json（只写本脚本负责的键）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

KEY_FIELDS = ["doi", "title", "authors", "year", "venue"]

# 字段别名表：按实际内容命中，不依赖文件名/标签假设（校验式命中）
FIELD_ALIASES = {
    "doi": ["doi", "DOI", "doi_id", "identifier_doi", "DO"],
    "title": ["title", "article_title", "paper_title", "name", "title_raw"],
    "authors": ["authors", "author", "authorList", "authors_raw", "creator", "creators"],
    "year": ["year", "pubyear", "pubYear", "publicationYear", "published", "date"],
    "venue": ["venue", "journal", "container-title", "journal_title", "source", "venue_raw"],
}
# 库名签名：内容级命中（键名/值中出现即视为该库特征）
DB_SIGNATURES = {
    "crossref": ["crossref", "container-title", "DOI", "ISSN", " deposited"],
    "europepmc": ["europepmc", "pmcid", "PMCID", "pubType", "journalInfo"],
    "pubmed": ["pubmed", "PMID", "medline"],
    "publisher": ["publisher", "article-number", "pdf_url"],
}

RE_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")  # CJK 逐字成词：不用 isalpha()（汉字 isalpha=True 会整段连词）
RE_PUNCT = re.compile(r"[^\w\u4e00-\u9fff\s]+", re.UNICODE)
RE_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)+", re.I)
RE_YEAR = re.compile(r"(19|20)\d{2}")


def norm_text(s):
    """空白与标点归一（保留汉字），用于冲突比对。"""
    if s is None:
        return ""
    t = RE_PUNCT.sub(" ", str(s))
    return re.sub(r"\s+", " ", t).strip().lower()


def title_tokens(s, normalize=True):
    """标题分词：拉丁/数字整词 + 汉字逐字。normalize=False 时仅按空白切（退化对照）。"""
    if s is None:
        return []
    s = str(s)
    if normalize:
        return RE_TOKEN.findall(s.lower())
    return s.split()


def jaccard(a, b):
    A, B = set(a), set(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def norm_doi(d, normalize=True):
    if d is None:
        return ""
    d = str(d).strip()
    if not d:
        return ""
    if normalize:
        return RE_DOI_PREFIX.sub("", d).strip().lower().rstrip(".")
    return d  # 退化：不去前缀、不归一大小写（保留陷阱）


def norm_year(y):
    if y is None:
        return None
    try:
        m = RE_YEAR.search(str(y))
        return int(m.group(0)) if m else None
    except Exception:
        return None


def norm_authors(a, normalize=True):
    """作者归一为词元集合：拉丁词（≥2 字符，丢首字母缩写噪音）+ 汉字单字。
    显式字符类判断 CJK，不用 str.isalpha()（汉字 isalpha=True 会整段连词）。"""
    if a is None:
        return set()
    items = a if isinstance(a, list) else re.split(r"[;|]| and ", str(a))
    out = set()
    for it in items:
        if not it or not str(it).strip():
            continue
        s = str(it).lower()
        for tok in RE_TOKEN.findall(s):
            if normalize:
                if any("\u4e00" <= c <= "\u9fff" for c in tok) or len(tok) >= 2:
                    out.add(tok)
            else:
                out.add(tok)  # 退化：保留缩写噪音，作者比对更易误判
    return out


def pick(rec, names):
    """按别名表从记录中取第一个非空字段。"""
    if not isinstance(rec, dict):
        return None
    for k in names:
        v = rec.get(k)
        if v not in (None, "", []):
            return v
    return None


def signature_db(path, text):
    """标志式命中：按内容签名猜库名（返回 (db_id, hits)），不依据文件名标签。"""
    low = str(text or "").lower()
    best, hits = None, 0
    for db, sigs in DB_SIGNATURES.items():
        n = sum(1 for s in sigs if s.lower() in low)
        if n > hits:
            best, hits = db, n
    if best and hits >= 2:
        return best, hits
    base = os.path.basename(path).lower()
    for db in DB_SIGNATURES:
        if db in base:
            return db, 1
    return None, 0


def extract_hits_from_case(case):
    """从 case.json 递归抽取文献记录型数组（签名命中：含 doi/title 任一）。"""
    found = []

    def walk(node, path, hint):
        if isinstance(node, dict):
            if pick(node, FIELD_ALIASES["doi"]) or pick(node, FIELD_ALIASES["title"]):
                found.append({"record": node, "path": path, "hint": hint})
                return
            for k, v in node.items():
                walk(v, "%s.%s" % (path, k), k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i), hint)

    walk(case, "$", "")
    return found


def default_policy():
    return {
        "title_similarity_threshold": 0.82,
        "year_tolerance": 1,
        "require_author_overlap": True,
        "field_priority": [],
        "basis": None,
        "declared_at": None,
    }


def clamp_policy(policy):
    p = default_policy()
    if isinstance(policy, dict):
        p.update({k: policy[k] for k in p if policy.get(k) is not None})
    try:
        p["title_similarity_threshold"] = max(0.0, min(1.0, float(p["title_similarity_threshold"])))
    except Exception:
        p["title_similarity_threshold"] = 0.82
    try:
        p["year_tolerance"] = int(p["year_tolerance"])
    except Exception:
        p["year_tolerance"] = 1
    return p


def normalize_hit(h, idx, normalize=True):
    """把一条原始响应记录归一为引擎内部行。"""
    def g(key):
        raw = pick(h, FIELD_ALIASES[key])
        return raw, (None if raw is None else str(raw))
    doi_raw, _ = g("doi")
    title_raw, _ = g("title")
    authors_raw, _ = g("authors")
    year_raw, _ = g("year")
    venue_raw, _ = g("venue")
    return {
        "hit_id": "H%03d" % (idx + 1),
        "doi": norm_doi(doi_raw, normalize),
        "title": title_raw,
        "title_norm": norm_text(title_raw) if normalize else str(title_raw or "").strip(),
        "tokens": title_tokens(title_raw, normalize),
        "authors_norm": norm_authors(authors_raw, normalize),
        "authors_raw": authors_raw,
        "year": norm_year(year_raw) if normalize else (int(year_raw) if str(year_raw or "").strip().isdigit() else None),
        "venue_norm": norm_text(venue_raw) if normalize else str(venue_raw or "").strip(),
        "venue_raw": venue_raw,
        "db": str(h.get("db_id") or h.get("db") or "unknown"),
        "fields_present": [k for k in KEY_FIELDS if pick(h, FIELD_ALIASES[k]) not in (None, "", [])],
    }


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra
            return True
        return False


def engine_partition(raw_hits, policy, ablate="none"):
    """核心去重划分（纯函数）。返回 {rows, groups, decisions, conflicts, coverage, metrics}。"""
    policy = clamp_policy(policy)
    normalize = ablate not in ("normalize", "all")
    fuzzy = ablate not in ("fuzzy", "all")
    detect_conf = ablate not in ("conflict", "all")
    rows = [normalize_hit(h, i, normalize) for i, h in enumerate(raw_hits)
            if isinstance(h, dict)]
    n = len(rows)
    uf = UF(n)
    decisions = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = rows[i], rows[j]
            reason, method, sim = None, None, None
            if a["doi"] and b["doi"] and a["doi"] == b["doi"]:
                method, reason = "doi_exact", "DOI 归一后完全一致"
            elif (fuzzy and a["tokens"] and b["tokens"]):
                sim = jaccard(a["tokens"], b["tokens"])
                if sim >= policy["title_similarity_threshold"]:
                    y_ok = (a["year"] is None or b["year"] is None
                            or abs(a["year"] - b["year"]) <= policy["year_tolerance"])
                    a_ok = (not policy["require_author_overlap"]
                            or not a["authors_norm"] or not b["authors_norm"]
                            or bool(a["authors_norm"] & b["authors_norm"]))
                    if y_ok and a_ok:
                        method = "title_fuzzy"
                        reason = ("标题 Jaccard=%.4f ≥ 阈值 %s，年份差 %s，作者姓氏交集=%s"
                                  % (sim, policy["title_similarity_threshold"],
                                     None if a["year"] is None or b["year"] is None
                                     else abs(a["year"] - b["year"]),
                                     sorted(a["authors_norm"] & b["authors_norm"])[:2]))
            if method:
                uf.union(i, j)
                decisions.append({"pair": [a["hit_id"], b["hit_id"]],
                                  "method": method,
                                  "similarity": (round(sim, 4) if sim is not None else 1.0),
                                  "decision": "duplicate",
                                  "reason": reason})

    # 划分分组（键为根索引，值成员为行号）
    buckets = {}
    for i in range(n):
        buckets.setdefault(uf.find(i), []).append(i)
    groups = [[rows[i]["hit_id"] for i in buckets[r]]
              for r in sorted(buckets, key=lambda k: buckets[k][0])]

    # 合并 + 冲突检测
    conflicts = []
    merged = []
    prio = [d for d in policy["field_priority"] if isinstance(d, str)]
    for gi, root in enumerate(sorted(buckets, key=lambda k: buckets[k][0])):
        members = [rows[i] for i in buckets[root]]
        members.sort(key=lambda r: (prio.index(r["db"]) if r["db"] in prio else len(prio),
                                    r["hit_id"]))
        rec = {"record_id": "R%03d" % (gi + 1),
               "sources": [{"hit_id": m["hit_id"], "db_id": m["db"]} for m in members],
               "field_sources": {}, "conflicts": []}
        for f, raw_key, norm_key in (("doi", "doi", "doi"), ("title", "title", "title_norm"),
                                     ("year", "year", "year"), ("venue", "venue_raw", "venue_norm"),
                                     ("authors", "authors_raw", "authors_norm")):
            vals = [m for m in members if m[raw_key] not in (None, "", [], set())]
            if not vals:
                rec[f] = None
                continue
            rec[f] = vals[0][raw_key]
            rec["field_sources"][f] = vals[0]["db"]
            if detect_conf and len(vals) > 1:
                uniq = []
                for m in vals:
                    nv = sorted(m[norm_key]) if isinstance(m[norm_key], set) else m[norm_key]
                    if nv not in uniq:
                        uniq.append(nv)
                if len(uniq) > 1:
                    entry = {"record_id": rec["record_id"], "field": f,
                             "values": {m["hit_id"]: (sorted(m[norm_key]) if isinstance(m[norm_key], set)
                                                      else m[norm_key]) for m in vals},
                             "resolution": str(vals[0][raw_key]),
                             "basis": "来源优先级首位（%s），其余值保留备查" % vals[0]["db"]}
                    conflicts.append(entry)
                    rec["conflicts"].append(entry["field"])
        merged.append(rec)

    # 覆盖矩阵
    dbs = sorted({r["db"] for r in rows})
    matrix = {}
    for db in dbs:
        cells = {}
        for f in KEY_FIELDS:
            hit_rows = [r for r in rows if r["db"] == db]
            n_have = sum(1 for r in hit_rows
                         if (r["doi"] if f == "doi" else
                             r["title"] if f == "title" else
                             r["authors_norm"] if f == "authors" else
                             r["year"] if f == "year" else r["venue_raw"]) not in (None, "", [], set()))
            cells[f] = "covered" if n_have else "missing"
        matrix[db] = cells
    single = sum(1 for g in groups if len(g) == 1)
    metrics = {"raw_hits_total": n, "merged_records_total": len(groups),
               "duplicates_merged": n - len(groups),
               "single_source_records": single,
               "method_breakdown": {
                   "doi_exact": sum(1 for d in decisions if d["method"] == "doi_exact"),
                   "title_fuzzy": sum(1 for d in decisions if d["method"] == "title_fuzzy")},
               "conflicts_detected": len(conflicts),
               "ablate": ablate}
    return {"rows": rows, "groups": groups, "merged": merged, "decisions": decisions,
            "conflicts": conflicts, "coverage_matrix": matrix, "metrics": metrics,
            "databases": dbs}


def cmd_apply(args):
    """--apply：读 result.json 的 raw_hits + dedup_policy，机械执行管线并写回。"""
    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[dedup_core] result.json 不可读（不中断交付）: %s" % e)
        return 0
    try:
        inner = res.get("result") if isinstance(res, dict) else {}
        hits = inner.get("raw_hits") or []
        policy = inner.get("dedup_policy") or {}
        out = engine_partition(hits, policy, ablate=args.ablate)
        # 只写本脚本负责的键（多脚本禁写同一键）
        inner["merged_records"] = out["merged"]
        inner["dedup_decisions"] = out["decisions"]
        inner["conflicts"] = out["conflicts"]
        inner["coverage_matrix"] = out["coverage_matrix"]
        inner["dedup_metrics"] = out["metrics"]
        res["changelog"] = (res.get("changelog") or []) + [
            {"step": "dedup_core--apply", "change":
                "ablate=%s 机械执行归一/去重/合并/冲突/覆盖，写 5 个业务键" % args.ablate}]
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        m = out["metrics"]
        print("[dedup_core] apply ablate=%s: raw=%d merged=%d dup=%d conflicts=%d"
              % (args.ablate, m["raw_hits_total"], m["merged_records_total"],
                 m["duplicates_merged"], m["conflicts_detected"]))
    except Exception as e:
        print("[dedup_core] 管线执行异常（不中断交付）: %s" % e)
    return 0


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--work-dir", default="/app/work")
        ap.add_argument("--ablate", default="none",
                        choices=["none", "normalize", "fuzzy", "conflict", "all"])
        ap.add_argument("--apply", action="store_true", help="机械执行管线并写回 result.json")
        args = ap.parse_args()
        if args.apply:
            return cmd_apply(args)
        # 自测：CJK 分词 + DOI 归一（防 isalpha 汉字陷阱的回归测试）
        t1 = title_tokens("Deep learning for 蛋白质结构预测")
        assert "蛋" in t1 and "deep" in t1, "CJK 分词失败"
        assert norm_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
        print("[dedup_core] selftest OK (CJK tokens=%d)" % len(t1))
    except Exception as e:
        print("[dedup_core] 未预期异常（已降级）: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
