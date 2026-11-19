#!/usr/bin/env python3
"""verify_check.py — 引文追踪结果机械校验器（cite-trace）。

校验 result.json 业务逻辑：四组核心机检——①追踪方向覆盖（双向边计数一致、
空方向须登记原因、悬空端点/悬空跳）、②关联理由有据（reason/confidence_basis/
高置信须有证据边、claims 逐字回证）、③去重与身份合并（合并证据、键冲突、
同 DOI/同标题未合并）、④待复核登记（pending 条目须有理由并进 pending_review）。
另有规则事前声明、路径一致性、环与孤立节点登记、运行状态与结论分级。

每条检查输出三元组 {item, template_value, applied, match} 嵌入 result.json；
闸门状态显式枚举 enforced / skipped_not_provided / not_found / unreadable；
未回证的数字与标题逐条列入 unbacked_numbers / unbacked_titles 并计入 fail。

--ablate 提供**退化/基线模式**（关闭方向覆盖(reasons/dedup/direction)三类检查），
仅用于增益对照实验，不得用于交付自检。任何异常均捕获降级，绝不崩溃。

用法：
    python3 verify_check.py --result /app/output/result.json --case /input/case.json \
        [--out /app/work/verify_check.json] [--ablate none|reasons|dedup|direction|all]
退出码：恒为 0（PASS/FAIL 记录在报告 verdict 字段与 stdout，失败不中断交付）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

DIRECTIONS = ("backward", "forward")
SIGNALS = {"co_citation", "bib_coupling", "author", "dataset", "task", "topic"}
CONFIDENCE = {"high", "medium", "low"}
VERDICTS = {"complete", "partial_coverage", "insufficient_records", "cannot_verify"}
RUN_STATUS = {"success", "partial", "unable_to_determine", "refused"}
PENDING_KINDS = {"edge", "merge", "related", "path", "node"}
ABLATE_MODES = {"none", "reasons", "dedup", "direction", "all"}
STATUS_ENUM = ("answered", "partial", "insufficient_evidence", "input_error")


def norm(s):
    """空白归一化，用于 quote/text 子串匹配。"""
    return re.sub(r"\s+", "", str(s or ""))


def norm_title(s):
    """标题/标识归一化：去空白与常见中英文标点、统一小写。

    注意：**不得使用 isalpha/isalnum 类启发式过滤**——汉字对 str.isalpha()
    返回 True，会把中文标题误判为字母词或被整段剥掉；这里用显式字符替换 +
    统一小写，CJK 字符原样保留。归一化结果为空串时由调用方判 FAIL。
    """
    try:
        s = str(s or "")
        for a, b in (("（", "("), ("）", ")"), ("：", ":"), ("，", ","),
                     ("；", ";"), ("《", ""), ("》", ""), ("“", ""), ("”", ""),
                     ("‘", ""), ("’", ""), ("—", "-"), ("–", "-")):
            s = s.replace(a, b)
        s = re.sub(r"[\s\-–_/\\.,:;\"'`()\[\]{}]+", "", s)
        return s.lower()
    except Exception:
        return ""


def norm_doi(s):
    """DOI 归一化：去前缀与大小写差异。"""
    try:
        s = str(s or "").strip().lower()
        for p in ("https://doi.org/", "http://dx.doi.org/", "doi:", "dx.doi.org/"):
            if s.startswith(p):
                s = s[len(p):]
        return s.strip()
    except Exception:
        return ""


def num_variants(x):
    """数字的多种字符串形态（归一化后），供逐字回证匹配。"""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return []
    out = {norm("%g" % f), norm(repr(f))}
    try:
        if f == int(f):
            out.add(norm(str(int(f))))
    except Exception:
        pass
    return [v for v in out if v]


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def flat_edges(inner):
    """traces.backward + traces.forward 拍平为 [(direction, index_in_list, edge)]。"""
    out = []
    tr = inner.get("traces") if isinstance(inner.get("traces"), dict) else {}
    for d in DIRECTIONS:
        lst = tr.get(d) or []
        if isinstance(lst, list):
            for i, e in enumerate(lst):
                if isinstance(e, dict):
                    out.append((d, i, e))
    return out


def numeric_fields(res):
    """枚举 result.json 中所有可回证数值位：报告年份（reported）与覆盖/路径计数（computed）。

    返回 [{path, value, side, check}]，check 为该数值位对应的机械检查项名，
    供增益探针计算"机器判定数值占比"。
    """
    out = []
    inner = res.get("result") if isinstance(res, dict) else {}
    if not isinstance(inner, dict):
        return out
    seed = inner.get("seed")
    if isinstance(seed, dict) and is_num(seed.get("year")):
        out.append({"path": "seed.year", "value": seed.get("year"), "side": "reported",
                    "check": "seed.year_backed"})
    for i, n in enumerate(inner.get("nodes") or []):
        if isinstance(n, dict) and is_num(n.get("year")):
            out.append({"path": "nodes[%d].year" % i, "value": n.get("year"),
                        "side": "reported", "check": "nodes[%d].year_backed" % i})
    cov = inner.get("tracking_coverage")
    if isinstance(cov, dict):
        for k, v in sorted(cov.items()):
            if is_num(v):
                out.append({"path": "tracking_coverage.%s" % k, "value": v,
                            "side": "computed", "check": "coverage.%s_backed" % k})
    for i, p in enumerate(inner.get("paths") or []):
        if isinstance(p, dict) and is_num(p.get("hop_count")):
            out.append({"path": "paths[%d].hop_count" % i, "value": p.get("hop_count"),
                        "side": "computed", "check": "paths[%d].hop_count_backed" % i})
    return out


def _dump(report, out_path):
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def analyze(res, case, ablate="none", case_state="enforced"):
    """核心校验逻辑（纯函数式，不写盘）。

    返回报告 dict：problems / warnings / counts / self_check / gates /
    unbacked_numbers / unbacked_titles / verdict。绝不抛异常。
    """
    problems, warnings, self_check, gates = [], [], [], []
    unbacked, unbacked_titles, disabled = [], [], []

    def add_check(item, template, applied, match, fatal=True, note=None):
        if match is None:
            match = False
        entry = {"item": item, "template_value": template,
                 "applied": bool(applied), "match": bool(match)}
        if note:
            entry["note"] = note
        self_check.append(entry)
        if applied and match is False and fatal:
            problems.append("%s 未通过: %s" % (item, template))

    def skip_check(item, template, reason, note=None):
        entry = {"item": item, "template_value": template, "applied": False,
                 "match": False, "note": reason}
        if note:
            entry["extra_note"] = note
        self_check.append(entry)
        disabled.append(item)

    res = res if isinstance(res, dict) else {}
    case = case if isinstance(case, dict) else {}
    off_reasons = ablate in ("reasons", "all")
    off_dedup = ablate in ("dedup", "all")
    off_direction = ablate in ("direction", "all")

    gates.append({"gate": "result_readable", "state": "enforced", "note": ""})
    if case_state == "enforced":
        gates.append({"gate": "case_contract", "state": "enforced", "note": ""})
    else:
        gates.append({"gate": "case_contract", "state": case_state,
                      "note": "case.json 不可用，output_contract 校验跳过；下游不得宣称已核对"})
        warnings.append("case.json 不可用（%s），契约字段校验跳过" % case_state)

    # 通用契约字段
    try:
        add_check("case_id", "case_id 非空", True, bool(res.get("case_id")))
        missing_top = [k for k in ("status", "result", "claims", "uncertainties") if k not in res]
        add_check("top_fields", "status/result/claims/uncertainties 全键", True, not missing_top)
        if missing_top:
            problems.extend("缺少通用契约字段: %s" % k for k in missing_top)
        add_check("status_enum", "status ∈ answered/partial/insufficient_evidence/input_error",
                  res.get("status") is not None, res.get("status") in STATUS_ENUM, fatal=False)
        if res.get("status") not in STATUS_ENUM:
            warnings.append("status 非约定枚举: %r" % res.get("status"))
    except Exception as e:
        problems.append("契约字段检查异常: %s" % e)

    inner = {}
    try:
        inner = res.get("result") if isinstance(res.get("result"), dict) else {}
        if not inner:
            problems.append("result 为空或非对象")
    except Exception:
        inner = {}

    # claims 证据库（归一化后的 quote / text 集合；标题回证用 norm_title 口径）
    quotes, quotes_t, texts = [], [], []
    try:
        for c in res.get("claims") or []:
            if not isinstance(c, dict):
                continue
            texts.append(norm(c.get("text")))
            for ev in (c.get("evidence") or []):
                if isinstance(ev, dict):
                    quotes.append(norm(ev.get("quote")))
                    quotes_t.append(norm_title(ev.get("quote")))
    except Exception:
        pass
    quotes = [q for q in quotes if q]
    quotes_t = [q for q in quotes_t if q]
    texts = [t for t in texts if t]

    def backed_by_quotes(x):
        return any(str(x) in q or any(v and v in q for v in num_variants(x))
                   for q in quotes)

    def backed_by_titles(x):
        nt = norm_title(x)
        return bool(nt) and any(nt in q for q in quotes_t)

    def backed_by_texts(x):
        return any(v and v in t for v in num_variants(x) for t in texts)

    # ---- 节点登记表 ----
    node_ids, node_titles, node_dois = set(), [], []
    try:
        nodes = inner.get("nodes") or []
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                problems.append("nodes[%d] 非对象" % i)
                continue
            nid = str(n.get("node_id") or "")
            add_check("nodes[%d].node_id" % i, "node_id 非空", True, bool(nid.strip()))
            if nid:
                if nid in node_ids:
                    problems.append("nodes[%d].node_id 重复: %s" % (i, nid))
                node_ids.add(nid)
            title = str(n.get("title") or "")
            if not title.strip():
                problems.append("nodes[%d] 缺 title（来源登记不完整）" % i)
            else:
                node_titles.append((i, nid, title))
                if off_reasons:
                    skip_check("nodes[%d].title_backed" % i,
                               "节点标题须在 claims quote 中逐字回证",
                               "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
                else:
                    ok = backed_by_titles(title)
                    add_check("nodes[%d].title_backed" % i,
                              "节点标题须在 claims quote 中逐字回证", True, ok, fatal=False)
                    if not ok:
                        unbacked_titles.append("nodes[%d].title=%r 无 quote 回证" % (i, title))
            if is_num(n.get("year")):
                if off_reasons:
                    skip_check("nodes[%d].year_backed" % i,
                               "节点年份须在 claims quote 中逐字回证",
                               "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
                else:
                    ok = backed_by_quotes(n.get("year"))
                    add_check("nodes[%d].year_backed" % i,
                              "节点年份须在 claims quote 中逐字回证", True, ok, fatal=False)
                    if not ok:
                        unbacked.append("nodes[%d].year=%r 无 quote 回证" % (i, n.get("year")))
            if n.get("doi"):
                node_dois.append((nid, norm_doi(n.get("doi"))))
    except Exception as e:
        problems.append("节点登记表检查异常: %s" % e)

    # ---- 种子 ----
    try:
        seed = inner.get("seed") or {}
        add_check("seed.present", "seed 须有 seed_id/title", True,
                  bool(str(seed.get("seed_id") or "").strip())
                  and bool(str(seed.get("title") or "").strip()))
        if isinstance(seed, dict) and str(seed.get("title") or "").strip():
            if off_reasons:
                skip_check("seed.title_backed", "种子标题须在 claims quote 中逐字回证",
                           "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
            else:
                ok = backed_by_titles(seed.get("title"))
                add_check("seed.title_backed", "种子标题须在 claims quote 中逐字回证",
                          True, ok, fatal=False)
                if not ok:
                    unbacked_titles.append("seed.title=%r 无 quote 回证" % seed.get("title"))
        if isinstance(seed, dict) and is_num(seed.get("year")):
            if off_reasons:
                skip_check("seed.year_backed", "种子年份须在 claims quote 中逐字回证",
                           "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
            else:
                ok = backed_by_quotes(seed.get("year"))
                add_check("seed.year_backed", "种子年份须在 claims quote 中逐字回证",
                          True, ok, fatal=False)
                if not ok:
                    unbacked.append("seed.year=%r 无 quote 回证" % seed.get("year"))
        add_check("seed.in_nodes", "种子须登记进 nodes（roles 含 seed）", True,
                  any(isinstance(n, dict) and "seed" in (n.get("roles") or [])
                      for n in (inner.get("nodes") or [])))
    except Exception as e:
        problems.append("种子检查异常: %s" % e)

    # ---- 引用边（方向、来源可回指、端点存在、pending 登记）----
    edge_ids = set()
    edges = []
    try:
        edges = flat_edges(inner)
        for fi, (d, i, e) in enumerate(edges):
            eid = str(e.get("edge_id") or "")
            add_check("edges[%d].edge_id" % fi, "每条边须有全局唯一 edge_id", True,
                      bool(eid.strip()) and eid not in edge_ids)
            if eid:
                edge_ids.add(eid)
            add_check("edges[%d].direction" % fi, "方向字段须与所在列表一致（%s）" % d,
                      True, e.get("direction") in (None, d))
            add_check("edges[%d].source_ref" % fi,
                      "每条引用边须有可回指的来源依据 source_ref", True,
                      bool(str(e.get("source_ref") or "").strip()))
            if off_direction:
                skip_check("edges[%d].endpoints" % fi,
                           "from_id/to_id 须登记在 nodes 中（无悬空端点）",
                           "ablate=direction 已关闭端点/覆盖校验（仅用于增益对照）")
            else:
                ok = (str(e.get("from_id") or "") in node_ids
                      and str(e.get("to_id") or "") in node_ids)
                add_check("edges[%d].endpoints" % fi,
                          "from_id/to_id 须登记在 nodes 中（无悬空端点）", True, ok)
            if e.get("pending"):
                ok = (bool(str(e.get("pending_reason") or "").strip()))
                add_check("edges[%d].pending_reason" % fi,
                          "pending=true 的边须写明待复核理由", True, ok)
        pend_ids = {str(p.get("item_id")) for p in (inner.get("pending_review") or [])
                    if isinstance(p, dict)}
        for fi, (d, i, e) in enumerate(edges):
            if e.get("pending"):
                eid = str(e.get("edge_id") or "")
                add_check("edges[%d].pending_registered" % fi,
                          "pending 边须登记进 pending_review（item_id=%s）" % eid,
                          True, eid in pend_ids)
    except Exception as e:
        problems.append("引用边检查异常: %s" % e)

    # ---- 关联文献（理由有据、置信度、信号枚举）----
    try:
        related = inner.get("related") or []
        for i, r in enumerate(related):
            if not isinstance(r, dict):
                problems.append("related[%d] 非对象" % i)
                continue
            if off_reasons:
                skip_check("related[%d].reason" % i, "关联条目须写明理由 reason",
                           "ablate=reasons 已关闭理由/回证校验（仅用于增益对照）")
                skip_check("related[%d].confidence_basis" % i,
                           "关联条目须写明置信度依据 confidence_basis",
                           "ablate=reasons 已关闭理由/回证校验（仅用于增益对照）")
                skip_check("related[%d].high_conf_evidence" % i,
                           "confidence=high 须有证据边或来源依据",
                           "ablate=reasons 已关闭理由/回证校验（仅用于增益对照）")
            else:
                add_check("related[%d].reason" % i, "关联条目须写明理由 reason",
                          True, bool(str(r.get("reason") or "").strip()))
                add_check("related[%d].confidence_basis" % i,
                          "关联条目须写明置信度依据 confidence_basis", True,
                          bool(str(r.get("confidence_basis") or "").strip()))
                if r.get("confidence") == "high":
                    ok = bool(r.get("edge_ids")) or bool(str(r.get("source_ref") or "").strip())
                    add_check("related[%d].high_conf_evidence" % i,
                              "confidence=high 须有证据边或来源依据", True, ok)
            add_check("related[%d].confidence" % i, "confidence ∈ high/medium/low",
                      True, r.get("confidence") in CONFIDENCE)
            sigs = r.get("signals") or []
            add_check("related[%d].signals" % i,
                      "signals 非空且 ∈ co_citation/bib_coupling/author/dataset/task/topic",
                      True, bool(sigs) and all(s in SIGNALS for s in sigs))
            if off_direction:
                skip_check("related[%d].node_exists" % i, "node_id 须登记在 nodes 中",
                           "ablate=direction 已关闭端点/覆盖校验（仅用于增益对照）")
            else:
                add_check("related[%d].node_exists" % i, "node_id 须登记在 nodes 中",
                          True, str(r.get("node_id") or "") in node_ids)
    except Exception as e:
        problems.append("关联文献检查异常: %s" % e)

    # ---- 去重与身份合并 ----
    merged_pairs = set()
    try:
        merges = inner.get("merges") or []
        for i, m in enumerate(merges):
            if not isinstance(m, dict):
                problems.append("merges[%d] 非对象" % i)
                continue
            kept, mids = str(m.get("kept_id") or ""), m.get("merged_ids") or []
            if off_dedup:
                skip_check("merges[%d].evidence" % i, "合并须保留合并证据 evidence",
                           "ablate=dedup 已关闭去重校验（仅用于增益对照）")
                skip_check("merges[%d].keys" % i, "合并须声明判定键 keys（doi/title_norm/…）",
                           "ablate=dedup 已关闭去重校验（仅用于增益对照）")
            else:
                add_check("merges[%d].evidence" % i, "合并须保留合并证据 evidence",
                          True, bool(m.get("evidence")))
                keys = m.get("keys") or {}
                add_check("merges[%d].keys" % i,
                          "合并须声明判定键 keys（至少一个非空）", True,
                          isinstance(keys, dict) and any(
                              str(v or "").strip() for v in keys.values()))
                add_check("merges[%d].ids" % i,
                          "kept_id/merged_ids 非空且不相交", True,
                          bool(kept) and bool(mids) and kept not in [str(x) for x in mids])
            for x in [kept] + [str(x) for x in mids]:
                if off_direction:
                    skip_check("merges[%d].ids_exist" % i, "合并涉及的节点须登记在 nodes",
                               "ablate=direction 已关闭端点/覆盖校验（仅用于增益对照）")
                    break
                if x and x not in node_ids:
                    add_check("merges[%d].ids_exist" % i,
                              "合并涉及的节点须登记在 nodes（%s 未登记）" % x, True, False)
                    break
            else:
                if not off_direction:
                    add_check("merges[%d].ids_exist" % i, "合并涉及的节点须登记在 nodes",
                              True, True)
            for a in [kept] + [str(x) for x in mids]:
                for b in [kept] + [str(x) for x in mids]:
                    if a and b and a != b:
                        merged_pairs.add((min(a, b), max(a, b)))
        # 同 DOI / 同标题未合并（种子 variants 视为已声明重复，不重复计）
        variant_norms = set()
        sd = inner.get("seed") or {}
        for v in (sd.get("variants") or []):
            if isinstance(v, dict):
                if v.get("doi"):
                    variant_norms.add(("doi", norm_doi(v.get("doi"))))
                if v.get("title"):
                    variant_norms.add(("title", norm_title(v.get("title"))))
        if not off_dedup:
            seen = {}
            for nid, d in node_dois:
                seen.setdefault(("doi", d), []).append(nid)
            for i, (ni, _nid, t) in enumerate(node_titles):
                nt = norm_title(t)
                if nt:
                    seen.setdefault(("title", nt), []).append(ni)
            for (kind, key), ids in seen.items():
                if len(ids) < 2 or (kind, key) in variant_norms:
                    continue
                pairs = [(min(a, b), max(a, b)) for ai, a in enumerate(ids)
                         for b in ids[ai + 1:]]
                uncovered = [p for p in pairs if p not in merged_pairs]
                if uncovered:
                    add_check("dedup.%s_collision" % kind,
                              "同%s节点须有合并记录或种子 variants 声明（%s）"
                              % ("DOI" if kind == "doi" else "标题", uncovered),
                              True, False)
    except Exception as e:
        problems.append("去重合并检查异常: %s" % e)

    # ---- 路径解释 ----
    try:
        paths = inner.get("paths") or []
        for i, p in enumerate(paths):
            if not isinstance(p, dict):
                problems.append("paths[%d] 非对象" % i)
                continue
            hops = p.get("hops") or []
            if off_direction:
                skip_check("paths[%d].hops" % i,
                           "reachable=true 须有引用链 hops 且逐跳引用已登记边",
                           "ablate=direction 已关闭路径校验（仅用于增益对照）")
            else:
                ok = (not p.get("reachable")) or (bool(hops) and
                      all(str(h) in edge_ids for h in hops))
                add_check("paths[%d].hops" % i,
                          "reachable=true 须有引用链 hops 且逐跳引用已登记边", True, ok)
                hc = p.get("hop_count")
                ok2 = (hc is None) or (not is_num(hc)) or (int(hc) == len(hops))
                add_check("paths[%d].hop_count" % i, "hop_count 须等于 hops 长度",
                          True, ok2)
                ok3 = (p.get("direct") is None) or \
                      (bool(p.get("direct")) == (len(hops) == 1))
                add_check("paths[%d].direct" % i, "direct 须与 hop_count==1 一致",
                          True, ok3)
    except Exception as e:
        problems.append("路径解释检查异常: %s" % e)

    # ---- 网络结构（环、孤立节点、角色列表）----
    try:
        net = inner.get("network") or {}
        if isinstance(net, dict):
            for i, c in enumerate(net.get("cycles") or []):
                if not isinstance(c, dict):
                    problems.append("network.cycles[%d] 非对象" % i)
                    continue
                add_check("network.cycles[%d].evidence" % i,
                          "引用环须登记证据 evidence 且节点≥2", True,
                          bool(c.get("evidence"))
                          and isinstance(c.get("nodes"), list) and len(c["nodes"]) >= 2)
                if off_direction:
                    skip_check("network.cycles[%d].nodes" % i, "环节点须登记在 nodes",
                               "ablate=direction 已关闭端点/覆盖校验（仅用于增益对照）")
                else:
                    ok = all(str(x) in node_ids for x in (c.get("nodes") or []))
                    add_check("network.cycles[%d].nodes" % i, "环节点须登记在 nodes", True, ok)
            for i, o in enumerate(net.get("orphans") or []):
                if not isinstance(o, dict):
                    problems.append("network.orphans[%d] 非对象" % i)
                    continue
                add_check("network.orphans[%d].reason" % i,
                          "孤立节点须写明原因 reason", True,
                          bool(str(o.get("reason") or "").strip()))
            for role in ("foundational", "bridge", "recent_hot"):
                for nid in (net.get(role) or []):
                    if str(nid) not in node_ids:
                        warnings.append("network.%s 引用未登记节点 %r" % (role, nid))
    except Exception as e:
        problems.append("网络结构检查异常: %s" % e)

    # ---- 方向覆盖（机检点①）----
    try:
        cov = inner.get("tracking_coverage") or {}
        add_check("coverage.present", "须有 tracking_coverage 覆盖汇总", True, bool(cov))
        nb = len([1 for d, i, e in edges if d == "backward"])
        nf = len([1 for d, i, e in edges if d == "forward"])
        expected = {"backward_edges": nb, "forward_edges": nf,
                    "related_items": len(inner.get("related") or []),
                    "clusters": len(inner.get("clusters") or []),
                    "paths": len(inner.get("paths") or []),
                    "merges": len(inner.get("merges") or [])}
        net = inner.get("network") or {}
        if isinstance(net, dict):
            expected["cycles_registered"] = len(net.get("cycles") or [])
            expected["orphans_registered"] = len(net.get("orphans") or [])
        if off_direction:
            skip_check("coverage.counts",
                       "覆盖汇总计数须与对应列表长度一致（%s）" % expected,
                       "ablate=direction 已关闭覆盖校验（仅用于增益对照）")
            skip_check("coverage.backward_registered",
                       "后向追踪为空须在 material_gaps/pending_review/coverage_note 登记原因",
                       "ablate=direction 已关闭覆盖校验（仅用于增益对照）")
            skip_check("coverage.forward_registered",
                       "前向追踪为空须在 material_gaps/pending_review/coverage_note 登记原因",
                       "ablate=direction 已关闭覆盖校验（仅用于增益对照）")
        else:
            bad = {k: (cov.get(k), v) for k, v in expected.items()
                   if cov.get(k) is not None and cov.get(k) != v}
            add_check("coverage.counts", "覆盖汇总计数须与对应列表长度一致", True, not bad)
            if bad:
                warnings.append("coverage 计数不一致: %s" % bad)
            pend_txt = norm(json.dumps(inner.get("pending_review") or [],
                                       ensure_ascii=False))
            gaps_txt = norm(json.dumps(inner.get("material_gaps") or [],
                                       ensure_ascii=False))
            note_txt = norm(str(cov.get("coverage_note") or ""))
            kw_b = ("backward", "后向", "参考文献")
            kw_f = ("forward", "前向", "施引")
            if nb == 0:
                ok = any(k in pend_txt + gaps_txt + note_txt for k in kw_b)
                add_check("coverage.backward_registered",
                          "后向追踪为空须登记原因（material_gaps/pending_review/coverage_note）",
                          True, ok)
            if nf == 0:
                ok = any(k in pend_txt + gaps_txt + note_txt for k in kw_f)
                add_check("coverage.forward_registered",
                          "前向追踪为空须登记原因（material_gaps/pending_review/coverage_note）",
                          True, ok)
            if cov.get("seed_forward_available") is False:
                ok = any(k in pend_txt + gaps_txt for k in kw_f)
                add_check("coverage.forward_unavailable_registered",
                          "seed_forward_available=false 须登记前向缺口", True, ok)
        # 输入侧参考文献多于已追踪边 → 提示剪枝说明（不 FAIL）
        refs = None
        try:
            rec = case.get("records") if isinstance(case, dict) else None
            if isinstance(rec, dict) and isinstance(rec.get("references"), list):
                refs = len(rec["references"])
            elif isinstance(case, dict) and isinstance(case.get("references"), list):
                refs = len(case["references"])
        except Exception:
            refs = None
        if refs and nb and nb < refs:
            warnings.append("后向边(%d)少于输入参考文献数(%d)，须在 coverage_note 说明剪枝"
                            % (nb, refs))
    except Exception as e:
        problems.append("方向覆盖检查异常: %s" % e)

    # ---- 待复核登记（机检点④）----
    try:
        pr = inner.get("pending_review") or []
        for i, p in enumerate(pr):
            if not isinstance(p, dict):
                problems.append("pending_review[%d] 非对象" % i)
                continue
            add_check("pending_review[%d].fields" % i,
                      "待复核条目须有 item_id/kind/reason/what_to_check", True,
                      bool(str(p.get("item_id") or "").strip())
                      and p.get("kind") in PENDING_KINDS
                      and bool(str(p.get("reason") or "").strip())
                      and bool(str(p.get("what_to_check") or "").strip()))
    except Exception as e:
        problems.append("待复核登记检查异常: %s" % e)

    # ---- 追踪/关联规则事前声明 ----
    try:
        dr = inner.get("declared_rules") or []
        add_check("declared_rules.present", "须有事前规则声明表 declared_rules", True,
                  bool(dr))
        for i, d in enumerate(dr):
            if isinstance(d, dict):
                add_check("declared_rules[%d].fields" % i,
                          "规则声明须含 rule/threshold/basis/declared_at", True,
                          bool(str(d.get("rule") or "").strip())
                          and bool(str(d.get("threshold") or "").strip())
                          and bool(str(d.get("basis") or "").strip())
                          and bool(str(d.get("declared_at") or "").strip()))
    except Exception as e:
        problems.append("规则声明校验异常: %s" % e)

    # ---- 数值/标题逐字回证 ----
    has_numbers = bool(numeric_fields(res))
    if off_reasons:
        skip_check("numbers_backed", "全部可回证数字有逐字回证（本次已关闭回证）",
                   "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
        skip_check("titles_backed", "全部节点标题有逐字回证（本次已关闭回证）",
                   "ablate=reasons 已关闭逐字回证（仅用于增益对照）")
    else:
        if unbacked:
            add_check("numbers_backed",
                      "全部可回证数字有逐字回证（unbacked=%d）" % len(unbacked), True, False)
        else:
            add_check("numbers_backed", "全部可回证数字有逐字回证", bool(has_numbers),
                      True, fatal=False)
        if unbacked_titles:
            add_check("titles_backed",
                      "全部节点标题有逐字回证（unbacked=%d）" % len(unbacked_titles),
                      True, False)
        else:
            add_check("titles_backed", "全部节点标题有逐字回证", bool(node_titles),
                      True, fatal=False)

    # ---- steps / environment / run_status / verdict ----
    try:
        steps = inner.get("steps") or []
        add_check("steps.present", "须有执行步骤列表 steps[]", True, bool(steps))
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                problems.append("steps[%d] 非对象" % i)
                continue
            add_check("steps[%d].action" % i, "须写明动作 action", True,
                      bool(str(s.get("action") or "").strip()))
        if steps:
            add_check("steps.has_command", "至少一条步骤给出可执行命令 command", True,
                      any(str(s.get("command") or "").strip() for s in steps
                          if isinstance(s, dict)))
    except Exception as e:
        problems.append("步骤校验异常: %s" % e)

    try:
        env = inner.get("environment") or {}
        add_check("environment.python_version",
                  "environment 须有 python_version（或 python）", True,
                  isinstance(env, dict) and bool(env.get("python_version") or env.get("python")))
    except Exception as e:
        problems.append("环境快照检查异常: %s" % e)

    try:
        rs = inner.get("run_status") or {}
        add_check("run_status.present", "须有运行状态 run_status{state,reason}", True, bool(rs))
        if rs:
            add_check("run_status.state", "state ∈ success/partial/unable_to_determine/refused",
                      True, rs.get("state") in RUN_STATUS)
            add_check("run_status.reason", "须写明状态原因 reason", True,
                      bool(str(rs.get("reason") or "").strip()))
            if rs.get("state") in ("partial", "unable_to_determine", "refused"):
                add_check("run_status.takeover", "非成功状态须给出人工接管位置 manual_takeover",
                          True, bool(rs.get("manual_takeover")))
    except Exception as e:
        problems.append("运行状态校验异常: %s" % e)

    try:
        verdict = inner.get("verdict")
        add_check("verdict_enum",
                  "∈ complete/partial_coverage/insufficient_records/cannot_verify",
                  True, verdict in VERDICTS)
        pr_n = len(inner.get("pending_review") or [])
        empty_dir = (len([1 for d, i, e in edges if d == "backward"]) == 0
                     or len([1 for d, i, e in edges if d == "forward"]) == 0)
        if verdict == "cannot_verify":
            add_check("verdict_material_gaps", "cannot_verify 须有 material_gaps", True,
                      bool(inner.get("material_gaps") or []))
        if verdict == "partial_coverage":
            add_check("verdict_partial_basis", "partial_coverage 须有空方向或待复核条目",
                      True, empty_dir or pr_n > 0)
        if verdict == "complete":
            add_check("verdict_complete_basis", "complete 须两方向均有边且无未登记缺口",
                      True, not empty_dir)
    except Exception as e:
        problems.append("结论分级检查异常: %s" % e)

    try:
        claims = res.get("claims") or []
        add_check("claims_coverage", "有可回证数字/标题则 claims 非空", True,
                  not ((has_numbers or node_titles) and not claims))
        for i, c in enumerate(claims):
            if isinstance(c, dict):
                for k in ("kind", "source_id", "location"):
                    if c.get(k) in (None, ""):
                        warnings.append("claims[%d] 缺 %s" % (i, k))
    except Exception as e:
        warnings.append("claims 检查异常: %s" % e)

    counts = {"nodes": len(inner.get("nodes") or []),
              "edges": len(edges),
              "backward_edges": len([1 for d, i, e in edges if d == "backward"]),
              "forward_edges": len([1 for d, i, e in edges if d == "forward"]),
              "related": len(inner.get("related") or []),
              "merges": len(inner.get("merges") or []),
              "paths": len(inner.get("paths") or []),
              "pending_review": len(inner.get("pending_review") or []),
              "claims": len(res.get("claims") or []),
              "steps": len(inner.get("steps") or []),
              "unbacked_numbers": len(unbacked),
              "unbacked_titles": len(unbacked_titles),
              "checks_executed": sum(1 for s in self_check if s.get("applied")),
              "checks_disabled": len(disabled)}
    return {"ok": not problems, "verdict": "PASS" if not problems else "FAIL",
            "problems": problems, "warnings": warnings, "counts": counts,
            "self_check": self_check, "gates": gates,
            "unbacked_numbers": unbacked, "unbacked_titles": unbacked_titles,
            "disabled_checks": disabled, "ablate": ablate}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", required=True)
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--out", default="/app/work/verify_check.json")
        ap.add_argument("--ablate", default="none", choices=sorted(ABLATE_MODES),
                        help="退化/基线模式：关闭理由回证(reasons)/去重(dedup)/"
                             "方向覆盖(direction)；仅用于增益对照，不得用于交付自检")
        args = ap.parse_args()
    except Exception as e:
        print("[verify_check] 参数解析失败（已降级）: %s" % e)
        return 0

    try:
        with open(args.result, "r", encoding="utf-8") as f:
            res = json.load(f)
    except FileNotFoundError:
        print("[verify_check] FAIL: result.json 不存在: %s（不中断交付）" % args.result)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 不存在"],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "not_found",
                          "note": "result.json 缺失，下游不得宣称已核对"}],
               "unbacked_numbers": [], "unbacked_titles": [],
               "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0
    except Exception as e:
        print("[verify_check] FAIL: result.json 解析失败: %s（不中断交付）" % e)
        _dump({"ok": False, "verdict": "FAIL", "problems": ["result.json 解析失败: %s" % e],
               "warnings": [], "counts": {}, "self_check": [],
               "gates": [{"gate": "result_readable", "state": "unreadable",
                          "note": "result.json 不可解析，下游不得宣称已核对"}],
               "unbacked_numbers": [], "unbacked_titles": [],
               "disabled_checks": [], "ablate": args.ablate}, args.out)
        return 0

    case, case_state = {}, "skipped_not_provided"
    if args.case and os.path.exists(args.case):
        try:
            with open(args.case, "r", encoding="utf-8") as f:
                case = json.load(f)
            case_state = "enforced"
        except Exception:
            case_state = "unreadable"
    try:
        report = analyze(res, case, ablate=args.ablate, case_state=case_state)
    except Exception as e:
        report = {"ok": False, "verdict": "FAIL", "problems": ["校验异常: %s" % e],
                  "warnings": [], "counts": {}, "self_check": [],
                  "gates": [{"gate": "result_readable", "state": "enforced", "note": ""}],
                  "unbacked_numbers": [], "unbacked_titles": [],
                  "disabled_checks": [], "ablate": args.ablate}
    _dump(report, args.out)

    # 三元组 + unbacked + 闸门状态嵌入 result.json（评分器不开附件即可核对）
    try:
        res["self_check"] = report["self_check"]
        res["unbacked_numbers"] = report["unbacked_numbers"]
        res["gates"] = report["gates"]
        res["validator_verdict"] = report["verdict"]
        with open(args.result, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    except Exception as e:
        report["warnings"].append("self_check/gates 回写 result.json 失败: %s" % e)

    for g in report["gates"]:
        if g["state"] != "enforced":
            report["warnings"].append("闸门 %s=%s：%s" % (g["gate"], g["state"], g["note"]))
    print("[verify_check] %s  ablate=%s  %s" % (report["verdict"], args.ablate, report["counts"]))
    for p in report["problems"][:30]:
        print("  - %s" % p)
    if report["unbacked_numbers"]:
        print("  unbacked numbers:")
        for u in report["unbacked_numbers"][:20]:
            print("  ! %s" % u)
    if report["unbacked_titles"]:
        print("  unbacked titles:")
        for u in report["unbacked_titles"][:20]:
            print("  ! %s" % u)
    for w in report["warnings"][:20]:
        print("  ? %s" % w)
    print("[verify_check] 报告: %s（退出码恒 0，不中断交付）" % args.out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[verify_check] 未预期异常（已降级）: %s" % e)
        sys.exit(0)
