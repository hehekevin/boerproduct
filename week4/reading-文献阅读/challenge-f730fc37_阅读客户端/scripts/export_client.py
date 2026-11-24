#!/usr/bin/env python3
"""export_client.py — 生成自包含阅读客户端界面 reading_client.html（交互 MVP）：
正文按段落渲染（可跳转/搜索）、选区与证据引文高亮、问答卡片一键回到原文锚点、
阅读位置与批注列表、导出视图。可选 --embed-result 把整份 HTML 字符串嵌入 result.json 主产物字段。
全异常捕获：任何输入都写出可用 HTML。自测：--selftest。"""
from __future__ import annotations
import argparse, html, json, os, sys

def norm(s):
    import re
    return re.sub(r"\s+", "", str(s or ""))

def load(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as e:
        print("[export_client] WARN: 读取 %s 失败: %s" % (path, e))
        return None

def highlight(text, quotes):
    """在段落文本中对命中引文包裹高亮 span，未命中原样返回。"""
    t = str(text or "")
    try:
        nt = norm(t)
        spans = []
        for q, cls in quotes:
            nq = norm(q)
            if not nq:
                continue
            pos = nt.find(nq)
            if pos < 0:
                continue
            # 映射回原文位置：逐字符跳过空白
            idx_map = [i for i, ch in enumerate(t) if not ch.isspace()]
            if pos >= len(idx_map):
                continue
            s = idx_map[pos]
            e = idx_map[min(pos + len(nq) - 1, len(idx_map) - 1)] + 1
            spans.append((s, e, cls))
        if not spans:
            return html.escape(t)
        spans.sort()
        out, last = [], 0
        for s, e, cls in spans:
            if s < last:
                continue
            out.append(html.escape(t[last:s]))
            out.append('<span class="%s">%s</span>' % (cls, html.escape(t[s:e])))
            last = e
        out.append(html.escape(t[last:]))
        return "".join(out)
    except Exception:
        return html.escape(t)

def build_html(case, locator, result, annotations):
    paras = []
    try:
        paras = [p for p in (locator or {}).get("paragraphs", []) if isinstance(p, dict)]
    except Exception:
        paras = []
    pid_index = {str(p.get("paragraph_id")): p for p in paras if p.get("paragraph_id")}
    try:
        items = annotations if isinstance(annotations, list) else (annotations or {}).get("annotations") or []
    except Exception:
        items = []
    try:
        qa_list = ((result or {}).get("result") or {}).get("qa") or []
    except Exception:
        qa_list = []
    try:
        unc = (result or {}).get("uncertainties") or {}
        status = (result or {}).get("status") or "unknown"
        cid = (result or {}).get("case_id") or (case or {}).get("case_id") or "unknown"
        pos = ((result or {}).get("result") or {}).get("reading_position")
    except Exception:
        unc, status, cid, pos = {}, "unknown", "unknown", None

    para_html = []
    for p in paras:
        try:
            pid = str(p.get("paragraph_id"))
            sel = ann_sel = ev = None
            for a in items:
                if str(a.get("paragraph_id")) == pid:
                    sel = sel or a.get("selection_quote")
                    ev = ev or a.get("evidence_quote")
            body = highlight(p.get("text"), [(sel, "hl-sel"), (ev, "hl-ev")])
            heading = html.escape(str(p.get("heading") or ""))
            page = p.get("page")
            head_html = ('<div class="ph">%s%s</div>' % (('<b>%s</b> · ' % heading) if heading else '',
                          ('第 %s 页 · ' % html.escape(str(page))) if page else '')) if (heading or page) else ""
            para_html.append(
                '<div class="para" id="anchor-%s"><div class="pid">%s</div>%s<div class="ptext">%s</div></div>'
                % (html.escape(pid), html.escape(pid), head_html, body))
        except Exception:
            continue

    qa_html = []
    for q in qa_list:
        try:
            selobj = q.get("selection") if isinstance(q.get("selection"), dict) else {}
            qtext = str(q.get("question") or selobj.get("quote") or "—")
            qid = html.escape(str(q.get("question_id") or "?"))
            pid = html.escape(str(selobj.get("paragraph_id") or "?"))
            page = selobj.get("page") or ""
            ans = html.escape(str(q.get("answer") or "—"))
            st = html.escape(str(q.get("status") or ""))
            evs = q.get("evidence") or []
            ev_bits = "".join(
                '<li><a href="#anchor-%s">→ %s</a>%s：%s</li>' % (
                    html.escape(str(e.get("paragraph_id") or "?")), html.escape(str(e.get("paragraph_id") or "?")),
                    ('（第%s页）' % html.escape(str(e.get("page")))) if e.get("page") else "",
                    html.escape(str(e.get("quote") or ""))) for e in evs)
            qa_html.append(
                '<div class="card"><div class="chead"><b>%s</b><span class="badge b-%s">%s</span>'
                '<a class="jump" href="#anchor-%s">回看选区 %s%s</a></div>'
                '<div class="q">问：%s</div><div class="a"><b>答：</b>%s</div>'
                '<div class="ev"><b>证据（可点击回原文）：</b><ul>%s</ul></div></div>'
                % (qid, st, st, pid, pid, (' · 第%s页' % html.escape(str(page))) if page else "",
                   html.escape(str(q.get("question") or qtext)),
                   ans, ev_bits or "<li>—</li>"))
        except Exception:
            qa_html.append('<div class="card"><span class="badge bad">渲染失败已跳过</span></div>')

    ann_html = []
    for a2 in items:
        try:
            ann_html.append('<li><a href="#anchor-%s">%s</a>：%s <span class="q-frag">「%s」</span></li>' % (
                html.escape(str(a2.get("paragraph_id") or "?")), html.escape(str(a2.get("annotation_id") or "?")),
                html.escape(str(a2.get("question") or "")[:60]), html.escape(str(a2.get("selection_quote") or "")[:60])))
        except Exception:
            continue

    css = ("body{margin:0;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#1e293b}"
           ".wrap{max-width:1200px;margin:0 auto;padding:24px 16px;display:flex;gap:16px;align-items:flex-start}"
           ".main{flex:1;min-width:0}.side{width:340px;flex-shrink:0}"
           ".para{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin:8px 0}"
           ".para:target{outline:3px solid #f59e0b;background:#fffbeb}"
           ".pid{font-size:11px;color:#64748b;font-family:monospace}"
           ".ph{font-size:12px;color:#475569;margin:2px 0}.ptext{line-height:1.7;font-size:14px}"
           ".hl-sel{background:#fef08a;border-radius:3px}.hl-ev{background:#bbf7d0;border-radius:3px}"
           ".card{background:#fff;border:1px solid #dbe3ee;border-radius:8px;padding:12px;margin:10px 0;font-size:13px}"
           ".chead{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.q{color:#334155;margin:6px 0}"
           ".a{margin:6px 0}.ev ul{margin:4px 0 0;padding-left:18px}.ev li{margin:3px 0}"
           ".badge{border-radius:4px;padding:1px 8px;font-size:11px;background:#eff4fb;color:#1d4ed8}"
           ".badge.bad,.b-insufficient_evidence,.b-input_error{background:#fee2e2;color:#b91c1c}"
           ".b-answered{background:#dcfce7;color:#15803d}.b-partial{background:#fef9c3;color:#a16207}"
           ".jump{font-size:12px;color:#1d4ed8;text-decoration:none}.q-frag{color:#94a3b8;font-size:12px}"
           "h1{font-size:19px;margin:0}h2{font-size:15px;margin:18px 0 6px}"
           ".hdr{border-left:4px solid #1d4ed8;padding-left:12px;margin-bottom:14px}"
           ".meta{color:#64748b;font-size:12px}.box{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px}")
    js = ("function go(t){var e=document.getElementById('anchor-'+t);if(e){e.scrollIntoView({behavior:'smooth'});"
          "e.style.background='#fff7ed';setTimeout(function(){e.style.background=''},1600);}else{alert('索引中无段落 '+t);}}"
          "function srch(){var k=document.getElementById('kw').value.toLowerCase();"
          "document.querySelectorAll('.ptext').forEach(function(el){"
          "el.innerHTML=el.getAttribute('data-raw')?el.textContent:el.textContent;"
          "if(k&&el.textContent.toLowerCase().indexOf(k)>=0){"
          "el.innerHTML=el.textContent.replace(new RegExp(k.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&'),'gi'),function(m){return '<span class=hl-sel>'+m+'</span>'});}}"
          ");}"
          "function jumpPid(){var t=document.getElementById('pidin').value.trim();if(t)go(t);}")
    # 保存原始文本用于搜索（ptext 重建）
    doc = (
        '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>阅读客户端 · %s</title>'
        '<style>%s</style></head><body>'
        '<div class="wrap"><div class="main">'
        '<div class="hdr"><h1>阅读客户端 · 选区问答与批注回看</h1>'
        '<div class="meta">case %s · status <span class="badge b-%s">%s</span> · 段落 %d · 问答 %d · 批注 %d</div></div>'
        '<div class="box" style="margin-bottom:10px">'
        '<input id="kw" placeholder="关键词搜索正文" oninput="srch()" style="padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;width:55%%">'
        '<input id="pidin" placeholder="段落号如 p03 / pg02-b01" style="padding:6px 10px;border:1px solid #cbd5e1;border-radius:6px;width:28%%">'
        '<button onclick="jumpPid()" style="padding:6px 14px;border:0;border-radius:6px;background:#1d4ed8;color:#fff;cursor:pointer">定位</button>'
        '</div>'
        '%s'
        '<div class="meta" style="margin-top:18px">阅读位置：%s · 由 export_client 生成 · 自包含单文件 · 锚点=paragraph_id+逐字引文+offsets</div>'
        '</div><div class="side"><h2>问答与回看</h2>%s'
        '<h2>批注沉淀</h2><div class="box"><ul>%s</ul></div>'
        '<h2>边界与不确定</h2><div class="box meta">%s</div>'
        '</div></div><script>%s</script></body></html>'
        % (html.escape(str(cid)), css, html.escape(str(cid)), status, status,
           len(paras), len(qa_list), len(items),
           "".join(para_html) or '<div class="box meta">索引为空：材料未能建立段落索引（见 uncertainties）。</div>',
           html.escape(str(pos)) if pos else "未记录",
           "".join(qa_html) or '<div class="card meta">暂无问答</div>',
           "".join(ann_html) or "<li>暂无批注</li>",
           html.escape(json.dumps(unc, ensure_ascii=False)[:600]),
           js))
    return doc

def cmd_run(a):
    case = load(a.case) or {}
    locator = load(a.locator) or {}
    result = load(a.result) or {}
    annotations = load(a.annotations)
    if annotations is None:
        annotations = []
        print("[export_client] WARN: annotations 不可读，按空批注渲染")
    doc = build_html(case, locator, result, annotations if isinstance(annotations, list) else annotations.get("annotations", []))
    try:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(doc)
    except Exception as e:
        print("[export_client] FAIL: 写出失败: %s" % e)
        return 1
    print("[export_client] HTML %d bytes -> %s" % (len(doc), a.out))
    # 可选：把整份 HTML 作为主产物嵌入 result.json
    if a.embed_result:
        r = load(a.result)
        if isinstance(r, dict) and r:
            try:
                res = r.setdefault("result", {})
                res["client"] = {
                    "kind": "self-contained-html", "path": os.path.abspath(a.out).replace("\\", "/"),
                    "embedded_html": doc}
                arts = res.setdefault("artifacts", {})
                outdir = os.path.dirname(os.path.abspath(a.out)) or "."
                arts.setdefault("client_html", os.path.abspath(a.out).replace("\\", "/"))
                arts.setdefault("annotations", os.path.abspath(a.annotations).replace("\\", "/"))
                arts.setdefault("reading_log", os.path.join(outdir, "reading_log.jsonl").replace("\\", "/"))
                with open(a.result, "w", encoding="utf-8") as f:
                    json.dump(r, f, ensure_ascii=False, indent=1)
                print("[export_client] 已嵌入 result.json（embedded_html %d 字符）并登记 artifacts" % len(doc))
            except Exception as e:
                print("[export_client] WARN: 嵌入失败: %s" % e)
        else:
            print("[export_client] WARN: result.json 不可读，跳过嵌入")
    return 0

def cmd_selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cp, lp, rp, ap_, op = (os.path.join(td, n) for n in ("c.json", "l.json", "r.json", "a.json", "out.html"))
        json.dump({"case_id": "T1"}, open(cp, "w", encoding="utf-8"))
        json.dump({"paragraphs": [{"paragraph_id": "p01", "text": "Alpha improves recall by 12%.", "page": 1}]},
                  open(lp, "w", encoding="utf-8"))
        json.dump({"case_id": "T1", "status": "answered", "result": {"qa": [{"question_id": "q1",
            "question": "提升多少？", "selection": {"paragraph_id": "p01", "quote": "Alpha improves"},
            "answer": "12%", "status": "answered",
            "evidence": [{"paragraph_id": "p01", "quote": "recall by 12%", "page": 1}]}],
            "reading_position": "p01"},
            "uncertainties": {"summary": "无"}},
            open(rp, "w", encoding="utf-8"))
        json.dump([{"annotation_id": "a-1", "paragraph_id": "p01", "selection_quote": "Alpha improves",
                    "evidence_quote": "recall by 12%", "question": "提升多少？"}], open(ap_, "w", encoding="utf-8"))
        ns = argparse.Namespace(case=cp, locator=lp, result=rp, annotations=ap_, out=op, embed_result=True)
        if cmd_run(ns) != 0:
            print("  [selftest] 正例运行 FAIL"); ok = False
        h = open(op, encoding="utf-8").read()
        if "hl-sel" not in h or "anchor-p01" not in h:
            print("  [selftest] 正例高亮/锚点缺失 FAIL"); ok = False
        r2 = json.load(open(rp, encoding="utf-8"))
        if not r2.get("result", {}).get("client", {}).get("embedded_html"):
            print("  [selftest] 正例嵌入失败 FAIL"); ok = False
        # 反例：全部输入损坏 → 仍写出 HTML
        op2 = os.path.join(td, "out2.html")
        for p in (cp, lp, rp, ap_):
            with open(p, "wb") as f:
                f.write(b"\xff\xfe\x00garbage")
        ns2 = argparse.Namespace(case=cp, locator=lp, result=rp, annotations=ap_, out=op2, embed_result=False)
        if cmd_run(ns2) != 0 or not os.path.exists(op2) or os.path.getsize(op2) < 500:
            print("  [selftest] 反例: 损坏输入应仍写出可用 HTML FAIL"); ok = False
    print("[export_client] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--locator", default="/app/work/locator.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--annotations", default="/app/output/annotations.json")
    ap.add_argument("--out", default="/app/output/reading_client.html")
    ap.add_argument("--embed-result", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try:
        if a.selftest:
            return cmd_selftest(a)
        return cmd_run(a)
    except Exception as e:
        print("[export_client] 兜底异常: %s（保留现有产物）" % e)
        return 1

if __name__ == "__main__":
    sys.exit(main())
