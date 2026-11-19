#!/usr/bin/env python3
"""track_engine.py — 时间窗 / 去重 / 版本链 / 时效排序机械引擎（lit-track-incremental）。

从 result.json 读取已判定的记录（relevance/confidence/factors 等由 Agent 填写），
机械完成四件可复算的事：

  1. 去重键归一化：title_norm = casefold + 去标点空白（\\w 含 CJK 汉字，
     **不用 isalpha 判断字母**——isalpha 对汉字返回 True，会把中文标题误判）；
     dedup_key 按 doi > arxiv_id > title_norm 优先级取值，doi/arxiv 归一化去
     前缀与版本后缀。
  2. 时间窗判定：按 result.window 声明的 start/end（ISO 8601）逐条判
     in_window；published_date < start 且 indexed_date >= start → backfill
     （延迟入库补回）；published_date < start 且 indexed_date < start →
     out_of_window（旧条目重复抓到）。
  3. 版本链合并：同 dedup_key 的条目按发表日升序构成链（preprint → published
     → revised → retracted），链内首发者 event=new（或 backfill），其余
     version_update；同日同 venue 的转载记 duplicate 并指向保留条目；
     版本标签/标题含撤稿标记 → retraction。链写入 result.version_chains，
     涉链条目 event 落定，重复条目 related_to 指向保留条目。
  4. 时效排序：按 result.rubric 事前权重机械复算 track_score（保留 4 位小数），
     平局规则 track_score 降序 → published_date 降序 → item_id 升序，产出
     result.ranking（ordered_ids / ties / top_k / k_value）与 items[].rank。

**键归属**：本脚本只写 items[].dedup_key / in_window / event / related_to /
track_score / rank、result.ranking、result.version_chains、result.dedup_policy
与 result.window 的 *_computed 附注；其余键一律不碰（多脚本禁写同一键）。

用法：
    python3 track_engine.py --result /app/output/result.json [--case /input/case.json] [--k 10] [--dry-run]
退出码恒为 0（结论记在 stdout 报告与 result.json，不中断交付）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

WEIGHT_KEYS = ("relevance", "recency", "confidence")
RETRACT_PAT = re.compile(r"retract|withdraw|撤稿|撤回|勘误", re.IGNORECASE)
DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


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
        print("[track_engine] 写盘失败 %s: %s" % (path, e))
        return False


def title_norm(title):
    """标题归一化：casefold + 去全部标点/空白。用 \\w（Unicode 词字符，含 CJK），
    不用 isalpha——汉字 isalpha()=True 会破坏 ASCII/汉字区分逻辑。"""
    s = str(title or "").casefold()
    return re.sub(r"[^\w]+", "", s, flags=re.UNICODE)


def norm_doi(doi):
    s = DOI_PREFIX.sub("", str(doi or "").strip().casefold())
    return re.sub(r"[^\w./\-]+", "", s)


def norm_arxiv(a):
    s = str(a or "").strip().casefold()
    s = re.sub(r"^(arxiv:|https?://arxiv\.org/(abs|pdf)/)", "", s)
    return re.sub(r"v\d+$", "", s).strip()


def dedup_key_of(it):
    """按 doi > arxiv_id > title_norm 优先级生成稳定去重键。"""
    d = norm_doi(it.get("doi"))
    if d:
        return "doi:" + d
    a = norm_arxiv(it.get("arxiv_id"))
    if a:
        return "arxiv:" + a
    return "title:" + title_norm(it.get("title"))


def parse_date(v):
    if isinstance(v, str):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v.strip())
        if m:
            return "-".join(m.groups())
    return None


def weights_ok(rubric):
    w = (rubric or {}).get("weights") or {}
    vals = []
    for k in WEIGHT_KEYS:
        v = w.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            return None
        vals.append(float(v))
    if abs(sum(vals) - 1.0) > 1e-6:
        return None
    return vals


def fused(weights, factors):
    if not isinstance(factors, dict):
        return None
    vals = []
    for k in WEIGHT_KEYS:
        v = factors.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        vals.append(float(v))
    return round(sum(wi * vi for wi, vi in zip(weights, vals)), 4)


def is_retraction(it):
    if str(it.get("version_tag") or "").casefold() in ("retraction", "erratum", "withdrawn"):
        return True
    if it.get("is_retraction") is True:
        return True
    return bool(RETRACT_PAT.search(str(it.get("title") or "")))


def run_engine(res):
    """主引擎（纯计算，不改盘）。返回 (problems, updates, chains, ranking, window_calc)。"""
    problems = []
    inner = res.get("result") or {}
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    if not items:
        return ["items 为空，引擎无可处理条目"], {}, [], None, {}

    rubric = inner.get("rubric") or {}
    weights = weights_ok(rubric)
    if weights is None:
        problems.append("rubric 权重未声明/非法（relevance/recency/confidence 0-1 且合计=1.0），"
                        "track_score/rank 未复算")
    wstart = parse_date((inner.get("window") or {}).get("start"))
    wend = parse_date((inner.get("window") or {}).get("end"))
    if not wstart or not wend:
        problems.append("window.start/end 未声明或非 ISO 日期，in_window 全记 null")
    elif wstart > wend:
        problems.append("window.start > window.end，in_window 全记 null")
        wstart = wend = None

    updates = {}
    for it in items:
        iid = str(it.get("item_id") or "")
        dk = dedup_key_of(it)
        if dk in ("doi:", "arxiv:", "title:"):
            problems.append("%s 无可归一化标识（标题/doi/arxiv 全空），dedup_key 记 null" % iid)
            dk = None
        pd = parse_date(it.get("published_date"))
        idate = parse_date(it.get("indexed_date"))
        if it.get("published_date") and not pd:
            problems.append("%s published_date 非 ISO 8601 可解析: %r" % (iid, it.get("published_date")))
        in_window = None
        if pd and wstart:
            in_window = wstart <= pd <= wend
        elif pd:
            in_window = False if (wstart and pd < wstart) else None
        updates[iid] = {"dedup_key": dk, "published_date_norm": pd,
                        "indexed_date_norm": idate, "in_window": in_window}

    # ---- 版本链与事件分类（并查集：同 dedup_key 或同 title_norm 归并为同链，
    #      覆盖 DOI 与 arXiv 编号并存的预印本→正式版跨键场景） ----
    parent = {str(it.get("item_id") or ""): str(it.get("item_id") or "")
              for it in items if str(it.get("item_id") or "")}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    idx_by_key = {}
    for it in items:
        iid = str(it.get("item_id") or "")
        u = updates[iid]
        if u["dedup_key"]:
            if u["dedup_key"] in idx_by_key:
                union(idx_by_key[u["dedup_key"]], iid)
            else:
                idx_by_key[u["dedup_key"]] = iid
    idx_by_title = {}
    for it in items:
        iid = str(it.get("item_id") or "")
        tn = title_norm(it.get("title"))
        if tn:
            if tn in idx_by_title:
                union(idx_by_title[tn], iid)
            else:
                idx_by_title[tn] = iid
    groups = {}
    for iid in parent:
        groups.setdefault(find(iid), []).append(iid)

    chains = []
    event_of = {}
    related_of = {}
    for _root, ids in groups.items():
        if len(ids) < 2:
            continue

        # 链内按发表日升序（缺日期的排最后，记 pending 线索）
        def sort_key(x):
            return (updates[x]["published_date_norm"] or "9999-12-31", x)
        ordered = sorted(ids, key=sort_key)
        keep = ordered[0]
        members = []
        for x in ordered:
            members.append({"item_id": x, "published_date": updates[x]["published_date_norm"],
                            "venue_type": next((str(it.get("venue_type")) for it in items
                                                if str(it.get("item_id")) == x), "unknown"),
                            "version_tag": next((it.get("version_tag") for it in items
                                                 if str(it.get("item_id")) == x), None)})
        kind = "multi_version"
        if any(next((is_retraction(it) for it in items if str(it.get("item_id")) == x), False)
               for x in ordered):
            kind = "with_retraction"
        keys = sorted({updates[x]["dedup_key"] for x in ordered if updates[x]["dedup_key"]})
        canonical_key = updates[keep]["dedup_key"]
        link_note = ("同 dedup_key=%s，按发表日升序" % canonical_key if len(keys) == 1
                     else "title_norm 相同跨键归并（keys=%s），按发表日升序" % ";".join(keys))
        chains.append({"chain_id": "vc-%02d" % (len(chains) + 1), "dedup_key": canonical_key,
                       "alt_keys": keys, "member_ids": ordered, "members": members,
                       "kind": kind, "canonical": keep,
                       "resolution": "merged", "evidence": link_note})
        for x in ordered[1:]:
            same_day = (updates[x]["published_date_norm"] == updates[keep]["published_date_norm"])
            if is_retraction(next((it for it in items if str(it.get("item_id")) == x), {})):
                event_of[x] = "retraction"
            elif same_day:
                event_of[x] = "duplicate"
            else:
                event_of[x] = "version_update"
            related_of[x] = keep

    # ---- 事件落定（单条目：backfill / out_of_window / new）----
    for it in items:
        iid = str(it.get("item_id") or "")
        u = updates[iid]
        pd, idate, inw = u["published_date_norm"], u["indexed_date_norm"], u["in_window"]
        if iid in event_of:
            u["event"] = event_of[iid]
            u["related_to"] = related_of[iid]
            continue
        if is_retraction(it):
            u["event"] = "retraction"
            continue
        if pd is None:
            u["event"] = None
            u["related_to"] = None
            problems.append("%s published_date 缺失，event 无法机械判定（须 Agent 判定并写 pending_reason）" % iid)
            continue
        if inw is True:
            u["event"] = "new"
        elif wstart and pd < wstart:
            if idate and wstart and idate >= wstart:
                u["event"] = "backfill"
            else:
                u["event"] = "out_of_window"
        elif inw is False:
            u["event"] = "out_of_window"
            problems.append("%s published_date %s 晚于窗口结束日，event=out_of_window（日期可疑须登记）"
                            % (iid, pd))
        else:
            u["event"] = None

    # 独立撤稿（不在任何版本链内）也登记单成员链，保证 retraction 事件可追溯
    chained_ids = {m for ch in chains for m in ch["member_ids"]}
    for it in items:
        iid = str(it.get("item_id") or "")
        u = updates[iid]
        if u.get("event") == "retraction" and iid not in chained_ids:
            chains.append({"chain_id": "vc-%02d" % (len(chains) + 1),
                           "dedup_key": u.get("dedup_key"), "alt_keys": [],
                           "member_ids": [iid],
                           "members": [{"item_id": iid,
                                        "published_date": u.get("published_date_norm"),
                                        "venue_type": str(it.get("venue_type") or "unknown"),
                                        "version_tag": it.get("version_tag")}],
                           "kind": "retraction", "canonical": iid,
                           "resolution": "merged",
                           "evidence": "独立撤稿通告（dedup_key=%s）" % u.get("dedup_key")})

    # ---- 时效排序 ----
    ranking = None
    if weights is not None:
        scores = []
        for it in items:
            iid = str(it.get("item_id") or "")
            s = fused(weights, it.get("factors"))
            if s is None:
                problems.append("%s factors 缺失或非法（relevance/recency/confidence 须 0-1 数值）" % iid)
                continue
            u = updates[iid]
            u["track_score"] = s
            scores.append((iid, s, u["published_date_norm"] or "0000-00-00"))
        if scores:
            # 平局规则：track_score 降序 → published_date 降序 → item_id 升序
            # （字符串日期不能取负，用三次稳定排序实现多键方向）
            ordered = sorted(scores, key=lambda t: str(t[0]))
            ordered.sort(key=lambda t: t[2], reverse=True)
            ordered.sort(key=lambda t: -t[1])
            ties = {}
            for pid, s, _d in ordered:
                ties.setdefault(s, []).append(pid)
            tie_groups = [{"track_score": s, "item_ids": ids,
                           "rule": "published_date 降序 → item_id 升序"}
                          for s, ids in sorted(ties.items(), reverse=True) if len(ids) > 1]
            ranked, rank_no, prev = [], 0, None
            for i, (pid, s, _d) in enumerate(ordered, 1):
                rank_no = rank_no if prev is not None and s == prev else i
                ranked.append({"item_id": pid, "track_score": s, "rank": rank_no})
                prev = s
            ranking = {"ordered_ids": [r["item_id"] for r in ranked],
                       "ties": tie_groups, "ranked": ranked}
    return problems, updates, chains, ranking, {"window_start": wstart, "window_end": wend}


def main() -> int:
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--result", default="/app/output/result.json")
        ap.add_argument("--case", default="/input/case.json")
        ap.add_argument("--k", type=int, default=None, help="top-k（缺省取 push 条目数）")
        ap.add_argument("--dry-run", action="store_true", help="只打印对照，不写盘")
        args = ap.parse_args()
    except Exception as e:
        print("[track_engine] 参数解析失败（已降级）: %s" % e)
        return 0

    res = load_json(args.result)
    if not isinstance(res, dict) or not isinstance(res.get("result"), dict):
        print("[track_engine] FAIL: result.json 不存在/不可解析/无 result 对象: %s（不中断交付）" % args.result)
        return 0

    inner = res["result"]
    items = [it for it in (inner.get("items") or []) if isinstance(it, dict)]
    problems, updates, chains, ranking, wcalc = run_engine(res)

    k_value = args.k if args.k is not None else sum(
        1 for it in items if isinstance(it, dict) and it.get("label") == "push")
    ranking_out = None
    if ranking:
        ranking_out = {"ordered_ids": ranking["ordered_ids"], "ties": ranking["ties"],
                       "top_k": ranking["ordered_ids"][:max(k_value, 0)], "k_value": k_value,
                       "rubric_weights": dict(zip(WEIGHT_KEYS, (inner.get("rubric") or {})
                                                  .get("weights") or {})),
                       "tie_break": (inner.get("rubric") or {}).get("tie_break")
                       or ["track_score 降序", "published_date 降序", "item_id 升序"],
                       "window": {"start": wcalc.get("window_start"),
                                  "end": wcalc.get("window_end")}}

    print("[track_engine] 窗口 %s → %s | 条目 %d | 版本链 %d | 已复算 %d"
          % (wcalc.get("window_start"), wcalc.get("window_end"), len(items),
             len(chains), sum(1 for u in updates.values() if u.get("track_score") is not None)))
    if ranking:
        for r in ranking["ranked"]:
            print("  #%02d  %s  score=%s  event=%s"
                  % (r["rank"], r["item_id"], r["track_score"],
                     updates.get(r["item_id"], {}).get("event")))
        if ranking["ties"]:
            print("  平局组 %d 组（按 published_date 降序、item_id 升序破平）" % len(ranking["ties"]))
    ev_count = {}
    for u in updates.values():
        ev_count[u.get("event")] = ev_count.get(u.get("event"), 0) + 1
    print("  事件分布: %s" % {k: v for k, v in ev_count.items() if k})
    for p in problems:
        print("  WARN: %s" % p)

    if args.dry_run:
        print("[track_engine] dry-run：不写盘。")
        return 0

    changed = copy.deepcopy(res)
    ch_inner = changed["result"]
    for it in ch_inner.get("items") or []:
        if not isinstance(it, dict):
            continue
        u = updates.get(str(it.get("item_id") or ""))
        if not u:
            continue
        it["dedup_key"] = u.get("dedup_key")
        it["in_window"] = u.get("in_window")
        if u.get("event") is not None:
            it["event"] = u["event"]
        if u.get("related_to") is not None:
            it["related_to"] = u["related_to"]
        if u.get("track_score") is not None:
            it["track_score"] = u["track_score"]
        if ranking and u.get("track_score") is not None:
            r = next(x for x in ranking["ranked"] if x["item_id"] == str(it.get("item_id")))
            it["rank"] = r["rank"]
    if chains:
        ch_inner["version_chains"] = chains
    if ranking_out:
        ch_inner["ranking"] = ranking_out
    pol = ch_inner.get("dedup_policy") or {}
    pol["applied"] = {"title_norm_example": title_norm(items[0].get("title")) if items else "",
                      "engine_version": "1.0"}
    ch_inner["dedup_policy"] = pol

    if save_json(args.result, changed):
        print("[track_engine] 已回写 dedup_key/in_window/event/related_to/track_score/rank"
              " / ranking / version_chains → %s" % args.result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[track_engine] 未预期异常（已降级，不中断交付）: %s" % e)
        sys.exit(0)
