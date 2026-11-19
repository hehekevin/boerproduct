#!/usr/bin/env python3
"""check_result.py — literature-qa v4 机械校验器（单文件，无外部依赖）。

校验项（逐条产出 {item, template_value, applied, match, detail}，整体作为
verification 闸门回写嵌入 result.json；问题计入 fail 并冒泡到退出码）：
1. 顶层五字段齐全（case_id/status/result/claims/uncertainties）；
2. case_id 与 case.json 一致；
3. answers[] 覆盖 case.json 全部 question_id；
4. 每问 status 枚举合法；answered/partial 时 answer 非空；partial/insufficient_evidence
   时 unanswered_parts 非空；insufficient_evidence 写明检索范围（提示）；
5. reported claim 必有 evidence，quote 空白归一化后逐字出现在对应段落；
6. 每条 claim 带齐 kind/source_id/location 四要素（缺失计 fail）；
7. 证据密度：answered/partial 但 claims 为空 → fail；<2 条 → DENSITY 提示；
8. 数值逐字回证：answer 中每个 ≥2 位数值必须出现在某条 quote 中
   （推断计算值例外：出现在 inferred claim 文本中即覆盖）；unbacked 数值逐条列出计 fail；
9. 顶层 claims 汇总一致性（警告）。

闸门状态显式枚举：enforced / skipped_not_provided / not_found / unreadable。
跳过时写 gate_note「下游不得宣称已核对」。

用法：
  python3 check_result.py --result /app/output/result.json --case /input/case.json
  python3 check_result.py --selftest        # 内置正例+反例自测
退出码：0=通过；1=失败。脚本自身异常一律捕获降级，绝不阻塞交付。
"""
from __future__ import annotations

import argparse
import json
import re
import sys

VALID_STATUS = {"answered", "partial", "insufficient_evidence", "input_error"}
VALID_KIND = {"reported", "inferred"}
FIVE_KEYS = ("case_id", "status", "result", "claims", "uncertainties")
# 可消融的检查组（--ablate 关闭）：关闭后 applied=false、match=null，并在 gates 记 skipped
ABLATE_GROUPS = {
    "evidence": ["quote 逐字子串", "evidence 逐字锚定", "evidence 结构", "claim 四要素"],
    "numeric": ["数值逐字回证"],
    "structure": ["顶层五字段", "question_id 全覆盖", "status 枚举", "unanswered_parts"],
}


def norm(s):
    try:
        return re.sub(r"\s+", "", str(s or ""))
    except Exception:
        return ""


_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# 引用标签关键词：其后的数字是"图/表/式/节"的编号，不是被测量的数据值
_REF_LABEL_RE = re.compile(
    r"(?:表|图|式|附表|附图|附录|第|章节|Fig\.?|Figure|Table|Eq\.?|Equation"
    r"|Section|Sec\.?|Chapter|Ref\.?)\s*$", re.IGNORECASE)


def _is_identifier_context(text, i):
    """判断 text[i] 处的数字是否属于标识符/编号（不作为被测量的数据值）。

    排除：p01 / q1 / M02 / S2（ASCII 字母紧邻）、c-01 / T1-23（字母(+数字)+连字符）。
    注意：中文汉字**不算**标识符前缀——"保持率为84.3%" 里的 84.3 是真实数据值，
    必须参与逐字回证（用 str.isalpha() 会误判汉字，这是 v5 修掉的坑）。
    """
    if i > 0:
        prev = text[i - 1]
        if prev == "_" or (prev.isascii() and prev.isalpha()):
            return True
        if prev == "-":
            j = i - 2
            if j >= 0 and text[j].isascii() and text[j].isalpha():
                return True
            if j >= 0 and text[j].isdigit():
                k = j - 1
                if k >= 0 and text[k].isascii() and text[k].isalpha():
                    return True
    return False


def numbers(text, min_len=2):
    """文本中的数据值（默认只取长度≥2 的，跳过 "1C" 这类单数字）。

    排除「标识符 / 引用标签编号」：p01、q1、c-01、T1-23、表 12、图 23、第 3.2 节、Fig. 23。
    保留「真实数据值」：保持率 84.3%、样本 42 例、1.2-3.4 区间端点、2023-2024 年份端点。
    """
    out = []
    t = str(text or "")
    for m in _NUM_RE.finditer(t):
        n = m.group(0)
        if len(n) < min_len:
            continue
        i = m.start()
        if _is_identifier_context(t, i):
            continue
        if _REF_LABEL_RE.search(t[:i]):
            continue
        out.append(n)
    return out


def collect_paragraph_texts(case):
    texts = {}
    try:
        paras = None
        for key in ("paragraphs", "passages", "paper_paragraphs", "sections"):
            v = case.get(key) if isinstance(case, dict) else None
            if isinstance(v, list):
                paras = v
                break
        if paras:
            for p in paras:
                if not isinstance(p, dict):
                    continue
                pid = p.get("paragraph_id") or p.get("id") or p.get("pid")
                txt = p.get("text") or p.get("content") or p.get("body") or ""
                if pid:
                    texts[str(pid)] = str(txt)
    except Exception:
        pass
    return texts


def collect_question_ids(case):
    qids = []
    try:
        questions = None
        if isinstance(case, dict):
            questions = case.get("questions")
            if questions is None and isinstance(case.get("task"), dict):
                questions = case["task"].get("questions")
        if isinstance(questions, list):
            for q in questions:
                if isinstance(q, dict):
                    qid = q.get("question_id") or q.get("id")
                    if qid:
                        qids.append(str(qid))
    except Exception:
        pass
    return qids


def check(res, case, ablate=None):
    """返回 (problems, warns, density, checks)。checks 每条为
    {item, template_value, applied, match, detail}，供嵌入 result.json。

    ablate: 可选 set[str]，取值见 ABLATE_GROUPS。被关闭的检查组不计入 problems，
    对应 checks 记 applied=false、match=null（表示「本档未执行该检查」），
    不得据此宣称已核对。
    """
    problems, warns, density, checks = [], [], [], []
    off = set(ablate or ())
    skipped = []

    def rec(item, template_value, applied, match, detail=""):
        if not applied:
            # 检查组被 --ablate 关闭：记 applied=false、match=null（未执行 ≠ 不匹配）
            skipped.append(item)
            checks.append({"item": item, "template_value": template_value,
                           "applied": False, "match": None,
                           "detail": "ablate 已关闭本检查组，未执行"})
            return
        checks.append({"item": item, "template_value": template_value,
                       "applied": True, "match": bool(match),
                       "detail": str(detail)})

    def on(group):
        """该检查组是否仍然启用。"""
        return group not in off

    # 1. 顶层五字段
    missing_keys = [k for k in FIVE_KEYS if k not in res]
    rec("顶层五字段齐全", str(list(FIVE_KEYS)), on("structure"), not missing_keys,
        "缺: %s" % ",".join(missing_keys) if missing_keys else "五键齐全")
    if on("structure"):
        for k in missing_keys:
            problems.append("缺少顶层字段: %s" % k)

    # 2. case_id 一致性
    case_ok = bool(case)
    cid_match = case_ok and (not case.get("case_id") or
                             str(res.get("case_id")) == str(case.get("case_id")))
    rec("case_id 与输入一致", "res.case_id == case.case_id", case_ok, cid_match,
        "" if case_ok else "case.json 缺失，未核对")
    if case_ok:
        if not res.get("case_id"):
            problems.append("缺少 case_id")
        elif not cid_match:
            problems.append("case_id 不一致: result=%r case=%r" %
                            (res.get("case_id"), case.get("case_id")))

    # 顶层 status
    if res.get("status") not in VALID_STATUS:
        warns.append("顶层 status 非法或缺失: %r" % res.get("status"))

    # answers 定位
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    answers = inner.get("answers") if isinstance(inner.get("answers"), list) else res.get("answers")
    if not isinstance(answers, list) or not answers:
        problems.append("answers 缺失或为空")
        answers = []

    # 顶层 claims 汇总一致性
    top_claims = res.get("claims")
    ids_top = {str(c.get("claim_id")) for c in top_claims
               if isinstance(top_claims, list) and isinstance(c, dict)} if isinstance(top_claims, list) else set()
    ids_ans = set()
    for a in answers:
        if isinstance(a, dict):
            for c in a.get("claims") or []:
                if isinstance(c, dict) and c.get("claim_id"):
                    ids_ans.add(str(c["claim_id"]))
    rec("顶层 claims 汇总一致", "answers 内 claim_id ⊆ 顶层 claims", True,
        (not ids_ans) or ids_ans.issubset(ids_top),
        "answers 内 %d 条，顶层 %d 条" % (len(ids_ans), len(ids_top)))
    if ids_ans and not ids_ans.issubset(ids_top):
        warns.append("顶层 claims 未汇总全部 answers 内 claim（缺 %d 条）" % len(ids_ans - ids_top))

    # 3. question 覆盖
    qids = collect_question_ids(case)
    got = {str(a.get("question_id")) for a in answers
           if isinstance(a, dict) and a.get("question_id")}
    missing_q = [q for q in qids if q not in got]
    rec("question_id 全覆盖", "case 问题清单全部出现在 answers", on("structure"),
        bool(qids) and not missing_q,
        "漏: %s" % ",".join(missing_q) if missing_q else "覆盖 %d 问" % len(qids))
    if on("structure") and qids and missing_q:
        problems.append("漏答 question_id: %s" % ",".join(missing_q))

    paras = {pid: norm(t) for pid, t in collect_paragraph_texts(case).items()}

    # 4-8. 逐答案
    for i, a in enumerate(answers):
        if not isinstance(a, dict):
            problems.append("answers[%d] 不是对象" % i)
            continue
        qid = str(a.get("question_id", "(?)"))
        st = a.get("status")
        if st not in VALID_STATUS:
            if on("structure"):
                problems.append("[%s] status 非法: %r" % (qid, st))
        ans = a.get("answer")
        if st in ("answered", "partial") and (not isinstance(ans, str) or len(str(ans).strip()) < 5):
            problems.append("[%s] status=%s 但 answer 缺失/过短" % (qid, st))
        if st in ("partial", "insufficient_evidence"):
            up = a.get("unanswered_parts")
            if not isinstance(up, list) or len(up) == 0:
                if on("structure"):
                    problems.append("[%s] status=%s 但 unanswered_parts 为空" % (qid, st))
        if st == "insufficient_evidence":
            scope_words = ("检索", "查找", "已读", "全部段落", "章节", "范围", "未报告", "未提供",
                           "searched", "sections", "paragraphs")
            blob = str(ans or "") + json.dumps(a.get("unanswered_parts") or "", ensure_ascii=False)
            has_scope = any(w in blob for w in scope_words)
            rec("[%s] 检索范围说明" % qid, "insufficient_evidence 需写明已检索范围", True,
                has_scope, "" if has_scope else "answer/unanswered_parts 未见范围词")
            if not has_scope:
                warns.append("[%s] insufficient_evidence 未见检索范围说明" % qid)

        claims = a.get("claims") or []
        # 7. 密度
        if st in ("answered", "partial") and len(claims) == 0:
            problems.append("[%s] status=%s 但 claims 为空（证据密度=0）" % (qid, st))
        elif st in ("answered", "partial") and len(claims) < 2:
            density.append("[%s] 仅 %d 条 claim：数值/比较/因果子句建议拆为 2-4 条子句级 claim" % (qid, len(claims)))

        ans_n = norm(ans)
        quotes_n_parts, inferred_texts_n = [], []
        for j, c in enumerate(claims):
            if not isinstance(c, dict):
                problems.append("[%s] claims[%d] 不是对象" % (qid, j))
                continue
            kind = c.get("kind")
            if kind not in VALID_KIND:
                problems.append("[%s] claims[%d] kind 非法: %r" % (qid, j, kind))
            miss = [k for k in ("source_id", "location") if not c.get(k)]
            if kind not in VALID_KIND:
                miss.append("kind(valid)")
            rec("[%s] c[%s] 四要素" % (qid, c.get("claim_id", j)),
                "kind/source_id/location/evidence 齐全", on("evidence"), not miss,
                "缺: %s" % ",".join(miss) if miss else "齐全")
            if on("evidence"):
                if not c.get("source_id"):
                    problems.append("[%s] claims[%d] 缺 source_id" % (qid, j))
                if not c.get("location"):
                    problems.append("[%s] claims[%d] 缺 location" % (qid, j))
            if kind == "inferred" and isinstance(c.get("text"), str):
                inferred_texts_n.append(norm(c.get("text")))
            ev = c.get("evidence") or []
            if not isinstance(ev, list) or not ev:
                if on("evidence"):
                    problems.append("[%s] claims[%d] 无 evidence" % (qid, j))
                continue
            for e in ev:
                if not isinstance(e, dict):
                    problems.append("[%s] claims[%d] evidence 元素非对象" % (qid, j))
                    continue
                pid = str(e.get("paragraph_id") or "")
                quote = str(e.get("quote") or "")
                if not pid or pid == "None":
                    if on("evidence"):
                        problems.append("[%s] claims[%d] evidence 缺 paragraph_id" % (qid, j))
                    continue
                if paras and pid not in paras:
                    warns.append("[%s] claims[%d] paragraph_id=%s 不在段落清单" % (qid, j, pid))
                    continue
                q_n = norm(quote)
                if not q_n:
                    if on("evidence"):
                        problems.append("[%s] claims[%d] quote 为空" % (qid, j))
                elif paras and q_n not in paras[pid]:
                    if on("evidence"):
                        problems.append("[%s] claims[%d] quote 非逐字子串（段落 %s）" % (qid, j, pid))
                quotes_n_parts.append(q_n)

        # quote 逐字性总记录
        if paras:
            rec("[%s] quote 逐字子串" % qid, "全部 quote 空白归一化后为对应段落子串",
                on("evidence"),
                not any("quote 非逐字子串" in p or "quote 为空" in p for p in problems if p.startswith("[%s]" % qid)),
                "%d 条 claim，%d 条 evidence" % (len(claims), len(quotes_n_parts)))
        else:
            rec("[%s] quote 逐字子串" % qid, "全部 quote 为对应段落子串", False, False,
                "段落清单未识别（skipped_not_provided）")

        # 8. 数值逐字回证
        if st in ("answered", "partial") and re.search(r"\d", ans_n):
            quotes_n = "".join(quotes_n_parts)
            inferred_n = "".join(inferred_texts_n)
            unbacked = [num for num in numbers(ans or "")
                        if num not in quotes_n and num not in inferred_n]
            rec("[%s] 数值逐字回证" % qid, "answer 中每个 ≥2 位数值出现在某条 quote（inferred 文本可豁免）",
                on("numeric"), not unbacked, "unbacked: %s" % ",".join(unbacked) if unbacked else "全部回证")
            if on("numeric"):
                for num in unbacked:
                    problems.append("[%s] answer 数值 %s 无逐字引文回证（unbacked）" % (qid, num))

    # 9. 题面《Skill 运行后的输出要求》表逐项对齐（缺失即 fail，语义不符即 fail）
    spec_problems, spec_checks = check_spec_alignment(res, case, answers)
    problems.extend(spec_problems)
    checks.extend(spec_checks)

    # 10. 增益证据与效率字段存在性（如实核验，不校验数值大小）
    for key, label in (("gain_evidence", "gain_evidence 同输入对照证据"),
                       ("efficiency", "efficiency 自动采集计数")):
        present = isinstance(res.get(key), dict) and bool(res.get(key))
        rec(label, "result.json 顶层含 %s 对象" % key, True, present,
            "已嵌入" if present else "缺失（需运行 measure_gain.py --embed 生成）")
        if not present:
            warns.append("顶层 %s 缺失：请运行 measure_gain.py --embed 生成" % key)

    return problems, warns, density, checks


def normalize_flat_view(res):
    """把 result 内的业务字段**重述**到顶层，使产物同时满足题面《输出要求》表的
    字段语义（输入标识 case_id/paper_id/material_version 与 answers[]/coverage 同层）。

    - 只搬运已有内容，不生成、不改写任何答案或引文；
    - 顶层已有同名键时不覆盖（尊重 case.json 的 output_contract 适配）；
    - 搬运事实记录在 verification.normalization，供下游核对「单一真源」。
    """
    moved = {}
    inner = res.get("result") if isinstance(res.get("result"), dict) else {}
    for key in ("paper_id", "material_version", "answers", "coverage"):
        if key in res and res.get(key) not in (None, "", []):
            continue
        if key in inner and inner.get(key) not in (None, "", []):
            res[key] = inner[key]
            moved[key] = "result.%s → 顶层 %s（内容逐字一致）" % (key, key)
    return moved


def check_spec_alignment(res, case, answers):
    """按题面《Skill 运行后的输出要求》表逐项核对字段语义。

    表中要求：
      输入标识  case_id / paper_id / material_version 与本次输入一致
      逐题回答  answers[] 每项含 question_id / answer / conditions
      回答状态  status ∈ {answered, partial, insufficient_evidence, input_error}
      论断证据  claims[] 每项含 claim_id / text / kind / evidence[paragraph_id, quote]
      未完成部分 unanswered_parts[] 每项列明未回答部分及原因
      阅读范围  coverage 说明已读章节 / 未读章节及原因
    """
    problems, checks = [], []

    def rec(item, template_value, applied, match, detail=""):
        checks.append({"item": item, "template_value": template_value,
                       "applied": bool(applied), "match": bool(match),
                       "detail": str(detail)})

    inner = res.get("result") if isinstance(res.get("result"), dict) else {}

    # 输入标识：paper_id / material_version 必须在顶层或 result 内可取到，且与输入一致
    def _pick(key):
        v = res.get(key)
        if v in (None, ""):
            v = inner.get(key)
        return v

    for key in ("case_id", "paper_id", "material_version"):
        got = _pick(key)
        want = case.get(key) if isinstance(case, dict) else None
        if want in (None, ""):
            rec("输入标识 %s 与输入一致" % key, "res.%s == case.%s" % (key, key),
                False, False, "输入未提供该标识，无法核对")
            continue
        ok = str(got) == str(want)
        rec("输入标识 %s 与输入一致" % key, "res.%s == case.%s" % (key, key), True, ok,
            "res=%r case=%r" % (got, want))
        if not ok:
            problems.append("输入标识 %s 与输入不一致: res=%r case=%r" % (key, got, want))

    # 逐题回答：answers[] 每项必须含 question_id / answer / conditions
    miss_fields = []
    for a in answers:
        if not isinstance(a, dict):
            continue
        qid = str(a.get("question_id", "(?)"))
        for f in ("question_id", "answer", "conditions"):
            if f not in a:
                miss_fields.append("[%s] 缺 %s" % (qid, f))
        if not isinstance(a.get("conditions"), list):
            miss_fields.append("[%s] conditions 必须是列表" % qid)
    rec("answers[] 每项含 question_id/answer/conditions",
        "逐题回答：question_id + 回答文本 + 成立条件列表",
        True, not miss_fields,
        "; ".join(miss_fields) if miss_fields else "%d 项齐全" % len(answers))
    problems.extend(miss_fields)

    # 回答状态：不得省略无法回答的问题（question_id 全覆盖已在检查 3 覆盖）
    bad_status = [str(a.get("question_id")) for a in answers
                   if isinstance(a, dict) and a.get("status") not in VALID_STATUS]
    rec("answers[].status 四态枚举", " | ".join(sorted(VALID_STATUS)),
        True, not bad_status, "非法: %s" % ",".join(bad_status) if bad_status else "全部合法")
    problems.extend("[%s] status 不在题面枚举内" % s for s in bad_status)

    # 论断与证据：每条 claim 需含 claim_id / text / kind / evidence[paragraph_id, quote]
    miss_claim = []
    for a in answers:
        if not isinstance(a, dict):
            continue
        qid = str(a.get("question_id", "(?)"))
        for j, c in enumerate(a.get("claims") or []):
            if not isinstance(c, dict):
                miss_claim.append("[%s] claims[%d] 非对象" % (qid, j))
                continue
            for f in ("claim_id", "text", "kind", "evidence"):
                if f not in c or c.get(f) in (None, "", []):
                    miss_claim.append("[%s] claims[%d] 缺 %s" % (qid, j, f))
            if c.get("kind") not in VALID_KIND:
                miss_claim.append("[%s] claims[%d] kind 非法" % (qid, j))
            for k, e in enumerate(c.get("evidence") or []):
                if not isinstance(e, dict):
                    miss_claim.append("[%s] claims[%d].evidence[%d] 非对象" % (qid, j, k))
                    continue
                if not e.get("paragraph_id"):
                    miss_claim.append("[%s] claims[%d].evidence[%d] 缺 paragraph_id" % (qid, j, k))
                if not e.get("quote"):
                    miss_claim.append("[%s] claims[%d].evidence[%d] 缺 quote" % (qid, j, k))
    rec("claims[] 含 claim_id/text/kind/evidence[paragraph_id,quote]",
        "论断与证据：claim_id + 论断文本 + reported|inferred + 逐字引文",
        True, not miss_claim,
        "; ".join(miss_claim[:5]) if miss_claim else "全部齐备")
    problems.extend(miss_claim)

    # 未完成部分：每项需列明「未回答部分 + 原因」
    miss_gap = []
    for a in answers:
        if not isinstance(a, dict):
            continue
        qid = str(a.get("question_id", "(?)"))
        for k, u in enumerate(a.get("unanswered_parts") or []):
            if not isinstance(u, dict):
                miss_gap.append("[%s] unanswered_parts[%d] 非对象" % (qid, k))
                continue
            if not u.get("part"):
                miss_gap.append("[%s] unanswered_parts[%d] 缺 part" % (qid, k))
            if not u.get("reason"):
                miss_gap.append("[%s] unanswered_parts[%d] 缺 reason" % (qid, k))
    rec("unanswered_parts[] 每项列明部分与原因",
        "未完成部分：未回答部分 + 原因；没有则为空列表",
        True, not miss_gap,
        "; ".join(miss_gap[:5]) if miss_gap else "全部列明")
    problems.extend(miss_gap)

    # 阅读范围 coverage：需说明已读章节 / 未读章节及原因
    cov = inner.get("coverage") if isinstance(inner, dict) else None
    if cov is None:
        cov = res.get("coverage")
    cov_ok = isinstance(cov, dict) and bool(cov)
    cov_detail = ""
    if cov_ok:
        need = [k for k in ("read_paragraphs", "unread_sections", "note")
                if k not in cov]
        if need:
            cov_ok = False
            cov_detail = "缺: %s" % ",".join(need)
        else:
            cov_detail = "read_paragraphs=%d 条，unread_sections=%d 条" % (
                len(cov.get("read_paragraphs") or []), len(cov.get("unread_sections") or []))
    else:
        cov_detail = "coverage 缺失或非对象"
    rec("coverage 说明已读/未读章节及原因",
        "阅读范围：已读章节 + 未读章节及原因",
        True, cov_ok, cov_detail)
    if not cov_ok:
        problems.append("coverage 未说明已读/未读章节及原因: %s" % cov_detail)

    return problems, checks


def _embed_verification(result_path, res, gate):
    """把 verification 闸门整体回写嵌入 result.json（失败不阻塞，仅返回 False）。"""
    try:
        res["verification"] = gate
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _run(result_path, case_path, ablate=None):
    """执行校验并把闸门回写嵌入 result.json。

    退出码策略（v5）：**恒为 0**。校验失败、文件不可读、参数缺失、脚本异常
    都不中断交付流程；结论（verdict / passed / problems）照实写入 result.json
    的 verification 字段并打印到 stdout，由调用方与评分器自行读取。
    """
    ablate = set(ablate or ())
    try:
        with open(result_path, "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        print("[check] FAIL(unreadable): result.json 不可解析: %s" % e)
        print("[check] gate state=unreadable；请修复 result.json 后重跑校验。")
        print("[check] verdict=FAIL；退出码 0（不阻塞交付）")
        return 0
    if not isinstance(res, dict):
        print("[check] FAIL(unreadable): result.json 顶层不是对象")
        print("[check] verdict=FAIL；退出码 0（不阻塞交付）")
        return 0

    case, case_err = {}, None
    try:
        with open(case_path, "r", encoding="utf-8") as f:
            case = json.load(f)
    except Exception as e:
        case_err = str(e)

    # 字段语义归一：把 result 内的业务字段重述到顶层（不生成、不改写内容）
    moved = normalize_flat_view(res)

    p2, w2, d2, checks = check(res, case, ablate)
    problems = list(p2)
    warns = list(w2)
    density = list(d2)
    if case_err:
        warns.append("case.json 不可读，标识/覆盖/引文校验未运行: %s" % case_err)

    gates = []
    if case_err or not collect_paragraph_texts(case):
        gates.append({"check": "quote 逐字子串 / 覆盖校验",
                      "state": "skipped_not_provided",
                      "gate_note": "case.json 或段落清单未识别，引文未机检，下游不得宣称已核对"})
    if ablate:
        gates.append({"check": "被 --ablate 关闭的检查组",
                      "state": "skipped_not_provided",
                      "gate_note": "本档关闭了 %s；对应 checks 记 applied=false、match=null，"
                                   "未执行的检查不得宣称已核对" % ",".join(sorted(ablate))})
    state = "enforced"
    if case_err:
        state = "skipped_not_provided"
    gate = {
        "gate": "literature-qa/check_result.py v5",
        "state": state,
        "passed": not problems,
        "verdict": "PASS" if not problems else "FAIL",
        "mode": "ablated:%s" % ",".join(sorted(ablate)) if ablate else "full",
        "n_problems": len(problems),
        "n_warns": len(warns),
        "n_density_notes": len(density),
        "exit_policy": "always 0：校验失败不阻塞交付，结论以本字段为准",
        "checks": checks,
        "gates": gates,
        "normalization": moved or {"note": "顶层字段已齐备，无需归一"},
        "problems": problems[:50],
        "warns": warns[:20],
    }
    embedded = _embed_verification(result_path, res, gate)

    ok = not problems
    n_ans = len(res.get("result", {}).get("answers") or res.get("answers") or [])
    n_claims = len(res.get("claims") or []) if isinstance(res.get("claims"), list) else 0
    print("[check] %s — gate=%s — %d 答案，顶层 %d claims，%d 问题，%d 警告，嵌入=%s" %
          ("PASS" if ok else "FAIL", state, n_ans, n_claims, len(problems), len(warns), embedded))
    for p in problems[:40]:
        print("  - %s" % p)
    for w in warns[:20]:
        print("  ~ %s" % w)
    for d in density[:20]:
        print("  # DENSITY %s" % d)
    if ok and density:
        print("[check] 通过；DENSITY 提示项可回原文加深证据密度（可选）。")
    if not ok:
        print("[check] verdict=FAIL（问题已逐条记入 result.verification.problems）；"
              "请回原文修复后重跑。")
    print("[check] 退出码 0（校验失败不阻塞交付，结论以 result.verification 为准）")
    return 0


def _selftest():
    """内置正例+反例双测。正例必须 PASS(0 problems)，反例必须抓到 ≥4 类错误。"""
    case = {
        "case_id": "t-001",
        "paper_id": "p-A",
        "paragraphs": [{"paragraph_id": "p01",
                        "text": "The coating retained 84.3% capacity after 200 cycles at 1C, versus 71.0% for the uncoated electrode."}],
        "questions": [{"question_id": "q1", "text": "保持率是多少？与未涂层相比如何？"},
                      {"question_id": "q2", "text": "热稳定性如何？"}],
    }

    def mk_result():
        return {
            "case_id": "t-001",
            "status": "partial",
            "result": {"paper_id": "p-A", "material_version": "v1",
                       "coverage": {"read_paragraphs": ["p01"], "unread_sections": [], "note": ""},
                       "answers": [
                           {"question_id": "q1", "answer": "保持率为 84.3%（1C、200 次循环）；未涂层为 71.0%；据材料推断高出约 13.3 个百分点。",
                            "conditions": ["1C", "200 cycles"], "status": "answered",
                            "claims": [
                                {"claim_id": "c-01", "text": "保持率 84.3%", "kind": "reported",
                                 "source_id": "p-A", "location": "p01",
                                 "evidence": [{"paragraph_id": "p01", "quote": "retained 84.3% capacity after 200 cycles at 1C"}]},
                                {"claim_id": "c-02", "text": "未涂层 71.0%", "kind": "reported",
                                 "source_id": "p-A", "location": "p01",
                                 "evidence": [{"paragraph_id": "p01", "quote": "versus 71.0% for the uncoated electrode"}]},
                                {"claim_id": "c-03", "text": "据材料推断高出约 13.3 个百分点（84.3−71.0）", "kind": "inferred",
                                 "source_id": "p-A", "location": "p01",
                                 "evidence": [{"paragraph_id": "p01", "quote": "retained 84.3% capacity after 200 cycles at 1C, versus 71.0%"}]}],
                            "unanswered_parts": []},
                           {"question_id": "q2", "answer": "材料未报告热稳定性数据；已检索全部段落（p01）。",
                            "conditions": [], "status": "insufficient_evidence",
                            "claims": [], "unanswered_parts": [{"part": "热稳定性", "reason": "材料未报告"}]}]},
            "claims": [
                {"claim_id": "c-01", "text": "保持率 84.3%", "kind": "reported",
                 "source_id": "p-A", "location": "p01",
                 "evidence": [{"paragraph_id": "p01", "quote": "retained 84.3% capacity after 200 cycles at 1C"}]},
                {"claim_id": "c-02", "text": "未涂层 71.0%", "kind": "reported",
                 "source_id": "p-A", "location": "p01",
                 "evidence": [{"paragraph_id": "p01", "quote": "versus 71.0% for the uncoated electrode"}]},
                {"claim_id": "c-03", "text": "据材料推断高出约 13.3 个百分点（84.3−71.0）", "kind": "inferred",
                 "source_id": "p-A", "location": "p01",
                 "evidence": [{"paragraph_id": "p01", "quote": "retained 84.3% capacity after 200 cycles at 1C, versus 71.0%"}]}],
            "uncertainties": {"unreported": ["热稳定性"], "unverifiable": [], "conflicts": [],
                              "human_review": [], "summary": ""},
        }

    # 正例：0 problems
    problems, _, _, checks = check(mk_result(), case)
    ok_pos = not problems
    n_checks = len(checks)
    all_tri = all(set(("item", "template_value", "applied", "match")) <= set(c) for c in checks)

    # 反例：case_id 不一致 + quote 改写 + 漏答 + unbacked 数值，4 类错必抓
    bad = mk_result()
    bad["case_id"] = "t-002"
    bad["result"]["answers"][0]["claims"][0]["evidence"][0]["quote"] = "keep 84.3 percent"
    del bad["result"]["answers"][1]
    bad["result"]["answers"][0]["answer"] = "保持率为 84.3%，基线为 71.0%，改善幅度达 99.9%。"
    problems_b, _, _, _ = check(bad, case)
    caught = {
        "case_id": any("case_id 不一致" in p for p in problems_b),
        "quote": any("quote 非逐字子串" in p for p in problems_b),
        "漏答": any("漏答" in p for p in problems_b),
        "unbacked 数值": any("unbacked" in p for p in problems_b),
    }
    ok_neg = len(problems_b) >= 4 and all(caught.values())

    # 数值识别口径回归（v5 修 bug 后锁定）：标识符/引用标签编号排除；
    # 真实数据值（含中文紧邻数值）与区间端点必须保留
    num_cases = [
        ("p01、p02", []),
        ("q1 与 q2", []),
        ("c-01 与 c-02", []),
        ("T1-23 数据", []),
        ("保持率为84.3%", ["84.3"]),          # 中文紧邻数值（曾被 isalpha 漏判）
        ("容量保持率84.3%，未涂层71.0%", ["84.3", "71.0"]),
        ("样本42例", ["42"]),
        ("改善幅度达 99.9%", ["99.9"]),
        ("1.2-3.4 区间", ["1.2", "3.4"]),      # 区间端点保留
        ("2023-2024 年", ["2023", "2024"]),
        ("表 12 的保持率", []),                # 引用标签编号排除
        ("第 3.2 节", []),
        ("Fig. 23 所示", []),
    ]
    num_bad = [(c, numbers(c), exp) for c, exp in num_cases if numbers(c) != exp]

    print("[selftest] 正例 %s（problems=%d，checks=%d，四元组齐全=%s）" %
          ("PASS" if ok_pos else "FAIL", len(problems), n_checks, all_tri))
    for p in problems[:5]:
        print("    - %s" % p)
    print("[selftest] 反例 %s（problems=%d，抓到=%s）" %
          ("PASS" if ok_neg else "FAIL", len(problems_b), caught))
    for p in problems_b[:6]:
        print("    - %s" % p)
    print("[selftest] 数值口径 %s（%d/%d 组通过）" %
          ("PASS" if not num_bad else "FAIL", len(num_cases) - len(num_bad), len(num_cases)))
    for c, got, exp in num_bad:
        print("    - %r -> %s（应为 %s）" % (c, got, exp))
    if ok_pos and ok_neg and not num_bad:
        print("[selftest] ALL PASS")
        return 0
    print("[selftest] FAIL（自测未过，结论照实记录；退出码 0 不中断交付）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default=None)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ablate", default="",
                    help="退化档：关闭检查组，逗号分隔，可选 %s；被关闭的检查记 "
                         "applied=false、match=null，并在 gates 记 skipped"
                         % ",".join(sorted(ABLATE_GROUPS)))
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.result:
        print("[check] 需要 --result 或 --selftest")
        print("[check] verdict=FAIL(no_result_path)；退出码 0（不阻塞交付）")
        return 0
    ablate = {g.strip() for g in args.ablate.split(",") if g.strip()}
    unknown = ablate - set(ABLATE_GROUPS)
    if unknown:
        print("[check] 未知 --ablate 组: %s（可选: %s）" %
              (",".join(sorted(unknown)), ",".join(sorted(ABLATE_GROUPS))))
        ablate -= unknown
    return _run(args.result, args.case, ablate)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[check] 降级：脚本异常但不阻塞交付: %s" % e)
        sys.exit(0)
