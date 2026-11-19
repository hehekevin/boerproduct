#!/usr/bin/env python3
"""plan_queries.py — Step 1 查询规划与关键词扩展（lit-search-pro）。

从 case.json 的科研问题机械生成：
  1. 多轮查询计划 result.query_plan[]：round1 核心术语 / round2 扩展术语 /
     round3 相关与上位术语 / round4 补漏与验证；
  2. 关键词扩展 result.keyword_expansion[]：复数、连字符变体、缩写展开
     （内置常见学术缩写表）、缩写反推、大小写归一变体，每项带 kind 与
     source_basis（规则名），可被 Agent 人工复核补充。
键分工：本脚本只写 result.json 的 query_plan 与 keyword_expansion 两个键，
不触碰其他键（多脚本禁写同一键）。同步落盘 /app/work/query_plan.json。
全捕获容错，退出码恒为 0。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# 常见学术缩写表（保守、通用；领域私有缩写应由 Agent 结合材料补充）
ACRONYM_TABLE = {
    "cnn": "convolutional neural network",
    "rnn": "recurrent neural network",
    "gan": "generative adversarial network",
    "gnn": "graph neural network",
    "mpnn": "message passing neural network",
    "llm": "large language model",
    "nlp": "natural language processing",
    "svm": "support vector machine",
    "bert": "bidirectional encoder representations from transformers",
    "vae": "variational autoencoder",
    "rl": "reinforcement learning",
    "dnn": "deep neural network",
    "kge": "knowledge graph embedding",
    "kg": "knowledge graph",
}

STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with",
    "how", "does", "do", "is", "are", "was", "were", "can", "could", "should",
    "what", "which", "when", "where", "why", "whether", "via", "using", "use",
    "study", "improve", "improves", "improved", "effect", "effects", "their",
}


def extract_question(case):
    """从 case.json 提取科研问题（兼容多种键名）。"""
    if not isinstance(case, dict):
        return ""
    for key in ("research_question", "question", "research_question_text", "task"):
        v = case.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for key in ("task", "case", "input"):
        v = case.get(key)
        if isinstance(v, dict):
            for k2 in ("research_question", "question"):
                if isinstance(v.get(k2), str) and v[k2].strip():
                    return v[k2].strip()
    return ""


def extract_phrases(question):
    """切分术语：引号短语 + 双词以上名词短语（简单启发式，不追求完美）。"""
    phrases = []
    # 引号短语优先
    for m in re.finditer(r"[\"'\u201c\u201d]([^\"'\u201c\u201d]{2,60})[\"'\u201c\u201d]", question):
        phrases.append(m.group(1).strip())
    # 英文分词成 bigram/trigram 候选（去停用词）
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{1,}", question)
    clean = [t for t in tokens if t.lower().strip("-") not in STOPWORDS and len(t) > 1]
    for n in (3, 2):
        for i in range(len(clean) - n + 1):
            g = [w.lower() for w in clean[i:i + n]]
            phrases.append(" ".join(g))
    # 去重保序
    seen, out = set(), []
    for p in phrases:
        k = re.sub(r"\s+", " ", p.lower())
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return out[:6]


def expand_keywords(question, materials_text=""):
    """机械关键词扩展：kind ∈ variant/abbreviation/synonym_expansion/acronym_backform。

    变体规则保守化：
      - plural_strip：复数去 s（networks→network）；
      - y→ies（property→properties）；
      - 形容词后缀（al/ar/ic/ive/ous）不加复数（避免 moleculars/neurals 类垃圾词）。
    """
    expansions = []
    seen = set()
    ADJ_SUFFIX = ("al", "ar", "ic", "ive", "ous", "ing", "ed")

    def add(term, kind, basis):
        k = term.lower()
        if k not in seen and len(k) > 2:
            seen.add(k)
            expansions.append({"term": term, "kind": kind, "source_basis": basis})

    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", question)
    lowers = {t.lower().strip("-") for t in tokens
              if t.lower().strip("-") not in STOPWORDS}

    for t in sorted(lowers):
        # 1) 复数变体（保守规则）
        if t.endswith("ies") and len(t) > 4:
            add(t[:-3] + "y", "variant", "rule:plural_ies_to_y")
        elif t.endswith("s") and not t.endswith("ss") and len(t) > 3:
            add(t[:-1], "variant", "rule:plural_strip")
        elif t.endswith("y") and len(t) > 3 and t[-2] not in "aeiou":
            add(t[:-1] + "ies", "variant", "rule:plural_y_to_ies")
        elif not t.endswith("s") and not t.endswith(ADJ_SUFFIX):
            add(t + "s", "variant", "rule:plural_add")
        # 2) 连字符变体
        if " " in t or "-" in t:
            add(t.replace(" ", "-") if " " in t else t.replace("-", " "),
                "variant", "rule:hyphen_space")
        # 3) 缩写展开（小写在表内）
        if t in ACRONYM_TABLE:
            add(ACRONYM_TABLE[t], "abbreviation", "rule:acronym_table:%s" % t)
            add(t.upper(), "abbreviation", "rule:acronym_uppercase:%s" % t)
    # 4) 缩写反推：问题中全大写缩写 → 标记待人工展开
    for m in re.finditer(r"\b[A-Z]{2,6}\b", question):
        ac = m.group(0).lower()
        if ac not in ACRONYM_TABLE:
            add(ac, "acronym_backform", "rule:question_acronym_needs_manual_expansion")
    # 5) 材料文本中的全大写缩写（常见于检索响应）
    if materials_text:
        for m in re.finditer(r"\b[A-Z]{2,6}\b", materials_text[:8000]):
            ac = m.group(0).lower()
            if ac in ACRONYM_TABLE and ac not in seen:
                add(ACRONYM_TABLE[ac], "abbreviation", "rule:material_acronym:%s" % ac)
    return expansions[:20]


def build_plan(question, phrases, databases):
    """多轮查询计划：每轮一个目的，数据库轮换组合。"""
    dbs = [d for d in databases if d] or ["Crossref", "EuropePMC", "OpenAlex"]
    plan = []
    for i, p in enumerate(phrases[:3]):
        plan.append({"round": 1, "query": p, "databases": dbs[:2],
                     "purpose": "核心术语首查（round%d）" % (i + 1), "status": "planned"})
    expanded = [e["term"] for e in expand_keywords(question)][:3]
    for i, t in enumerate(expanded):
        plan.append({"round": 2, "query": t, "databases": dbs[1:3] or dbs[:1],
                     "purpose": "扩展术语召回（round%d）" % (i + 1), "status": "planned"})
    for i, p in enumerate(phrases[3:5]):
        plan.append({"round": 3, "query": p + " survey review",
                     "databases": dbs[:1],
                     "purpose": "相关与上位术语补查（round%d）" % (i + 1), "status": "planned"})
    plan.append({"round": 4, "query": phrases[0] + " benchmark dataset" if phrases
                 else "benchmark dataset", "databases": dbs,
                 "purpose": "补漏与验证：数据集/基准方向反查遗漏", "status": "planned"})
    return plan


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("[plan_queries] 写盘失败 %s: %s" % (path, e))
        return False


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--work-dir", default="/app/work")
        args = ap.parse_args()
    except SystemExit:  # argparse error 也退出码 0（题面硬约束）
        return 0
    except Exception as e:
        print("[plan_queries] 参数解析失败（已降级）: %s" % e)
        return 0

    case = load_json(args.case) or {}
    question = extract_question(case)
    if not question:
        print("[plan_queries] WARN: case.json 未找到科研问题（生成空计划，不中断）")
        question = ""

    # 材料文本（用于缩写发现）
    materials_text = json.dumps(case, ensure_ascii=False)[:16000]

    phrases = extract_phrases(question) if question else []
    scope = case.get("scope") if isinstance(case.get("scope"), dict) else {}
    databases = scope.get("databases") if isinstance(scope.get("databases"), list) else []
    plan = build_plan(question, phrases, databases)
    expansions = expand_keywords(question, materials_text)

    # 落盘工作文件
    save_json(os.path.join(args.work_dir or ".", "query_plan.json"),
              {"case_id": case.get("case_id"), "question": question,
               "plan": plan, "keyword_expansion": expansions})
    save_json(os.path.join(args.work_dir or ".", "keyword_expansion.json"),
              {"original_terms": phrases, "expansion": expansions})

    # 只写 query_plan / keyword_expansion 两个键
    res = load_json(args.result)
    if isinstance(res, dict) and isinstance(res.get("result"), dict):
        try:
            res["result"]["query_plan"] = plan
            res["result"]["keyword_expansion"] = expansions
            if question and not res["result"].get("research_question"):
                res["result"]["research_question"] = question
            save_json(args.result, res)
            print("[plan_queries] 已回写 result.json: query_plan=%d 条, keyword_expansion=%d 条"
                  % (len(plan), len(expansions)))
        except Exception as e:
            print("[plan_queries] 回写 result.json 失败（工作文件仍在）: %s" % e)
    else:
        print("[plan_queries] WARN: result.json 不存在或无 result 对象，计划只落盘工作目录")

    print("[plan_queries] 科研问题: %s" % (question[:80] or "(未提供)"))
    for e in expansions[:10]:
        print("  expand: %-40s kind=%s basis=%s" % (e["term"], e["kind"], e["source_basis"]))
    for p in plan:
        print("  round%d [%s] %s" % (p["round"], ",".join(p["databases"]), p["query"]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[plan_queries] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
