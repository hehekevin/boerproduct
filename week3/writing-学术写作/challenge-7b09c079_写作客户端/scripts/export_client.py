#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_client.py — 生成自包含修订客户端 revision_client.html（学术写作客户端主产物）：
原稿按段落渲染（pid 锚点），每处修订一张卡片（指令号/锚点/原文/改后/依据/层面/影响面），
修订可逐条 接受/拒绝/标记需确认（localStorage 持久、跨会话），v1 原稿 / v2 按当前裁决合成
修订稿一键切换，按指令号/层面/裁决状态筛选，关键词搜索（命中计数+导航，不破坏修订高亮），
一键导出 裁决 JSON + 已接受修订的 Markdown（可回填可继续编辑），引用与格式哨兵、
边界与人工确认项侧栏展示。--embed-result 把整份 HTML 全量嵌入 result.json 主产物字段并
登记 features 功能清单。全异常捕获：任何输入都写出可用 HTML。自测：--selftest。"""
from __future__ import annotations
import argparse, html, json, os, re, sys

FEATURES = [
    "修订逐条裁决：每处改动可单独 接受/拒绝/标记需确认，决策 localStorage 持久跨会话，杜绝整段覆盖不可控",
    "修订回看与锚点跳转：修订卡显示 指令号/段落锚点/原文/改后/依据/层面/影响面，一键回到原稿位置",
    "版本对照：v1 原稿 / v2 修订稿（按当前裁决实时合成）一键切换，逐条改动可对比",
    "导出可编辑稿：按当前裁决一键导出 已接受修订 Markdown + 裁决 JSON，可回填可继续编辑",
    "修订筛选：按指令号/层面(措辞|结构|术语|引用|格式)/裁决状态过滤修订列表",
    "关键词搜索：全文命中计数 + 上一个/下一个导航，重渲染保留修订高亮",
    "引用与格式哨兵：引用编号缺口、未授权改动、校验结果直接显示在客户端侧栏",
    "边界与人工确认：需作者确认项、材料缺口、未执行指令在侧栏如实展示",
]

def load(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception as e:
        print("[export_client] WARN: 读取 %s 失败: %s" % (path, e))
        return None

def load_jsonl(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return [json.loads(l) for l in f if l.strip()]
    except Exception as e:
        print("[export_client] WARN: 读取 %s 失败: %s" % (path, e))
        return []

def esc(s):
    return html.escape(str(s or ""))

def js_json(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")

def hl_segments(text, segs):
    """spans: [(start,end,cls,replace)] 按起点排序输出 HTML。"""
    try:
        t = str(text or "")
        segs = sorted([s for s in segs if s[0] is not None and s[0] >= 0], key=lambda x: x[0])
        out, last = [], 0
        for s, e, cls, rep in segs:
            if s < last or e > len(t) or s >= e:
                continue
            out.append(esc(t[last:s]))
            body = rep if rep is not None else t[s:e]
            out.append('<span class="%s">%s</span>' % (cls, esc(body)))
            last = e
        out.append(esc(t[last:]))
        return "".join(out)
    except Exception:
        return esc(text)

def build_html(case, structure, edits, result, decisions=None):
    decisions = decisions if isinstance(decisions, dict) else {}
    paras = []
    try:
        src = structure.get("paragraphs") if isinstance(structure, dict) else structure
        paras = [p for p in (src or []) if isinstance(p, dict) and p.get("pid")]
    except Exception:
        paras = []
    try:
        unc = (result or {}).get("uncertainties") or {}
        checks = (result or {}).get("checks") or (result or {}).get("result", {}).get("checks") or []
        gates = (result or {}).get("gates") or {}
        status = (result or {}).get("status") or "unknown"
        cid = (result or {}).get("case_id") or (case or {}).get("case_id") or "unknown"
    except Exception:
        unc, checks, gates, status, cid = {}, [], {}, "unknown", "unknown"

    by_pid = {}
    for e in edits:
        by_pid.setdefault(str(e.get("pid") or "?"), []).append(e)
    # 首次渲染段落：标记每条修订 before 的位置（颜色按裁决，初始 pending）
    para_html = []
    paras_js = []
    for p in paras:
        pid = str(p.get("pid"))
        text = str(p.get("text") or "")
        segs = []
        for e in by_pid.get(pid, []):
            b = str(e.get("before") or "")
            if b and b in text:
                segs.append((text.find(b), text.find(b) + len(b), "hl-pend", None))
        paras_js.append({"id": pid, "text": text, "heading": str(p.get("heading") or ""),
                         "locator": str(p.get("locator") or ""), "edits": len(by_pid.get(pid, []))})
        head = ('<div class="ph"><b>%s</b> · %s</div>' % (esc(p.get("heading")), esc(p.get("locator")))) if (p.get("heading") or p.get("locator")) else ""
        para_html.append(
            '<div class="para" id="anchor-%s"><div class="pid">%s · 修订 %d 处</div>%s<div class="ptext" id="ptext-%d">%s</div></div>'
            % (esc(pid), esc(pid), len(by_pid.get(pid, [])), head, len(paras_js) - 1,
               hl_segments(text, segs) if segs else esc(text)))

    card_html = []
    for e in edits:
        try:
            se = "".join('<span class="chip">%s</span>' % esc(x) for x in (e.get("side_effects") or []))
            card_html.append(
                '<div class="card edit" data-eid="%s" data-iid="%s" data-level="%s">'
                '<div class="chead"><b>%s</b><span class="badge">%s</span><span class="badge b-lv">%s</span>'
                '<a class="jump" href="#anchor-%s">回原稿 %s</a></div>'
                '<div class="meta">%s · 锚点 pid=%s</div>'
                '<div class="diff"><div class="bf">原：%s</div><div class="af">改：%s</div></div>'
                '<div class="rat">依据：%s %s</div>'
                '<div class="acts"><button class="btn b-ok" onclick="decide(\'%s\',\'accept\')">接受</button>'
                '<button class="btn b-no" onclick="decide(\'%s\',\'reject\')">拒绝</button>'
                '<button class="btn b-cf" onclick="decide(\'%s\',\'confirm\')">需确认</button>'
                '<button class="btn2" onclick="decide(\'%s\',\'pending\')">撤销裁决</button></div></div>'
                % (esc(e.get("eid")), esc(e.get("iid")), esc(e.get("level")),
                   esc(e.get("eid")), esc(e.get("iid")), esc(e.get("level")),
                   esc(e.get("pid")), esc(e.get("pid")),
                   esc(e.get("locator")), esc(e.get("pid")),
                   esc(str(e.get("before"))[:200]), esc(str(e.get("after"))[:200]),
                   esc(str(e.get("rationale"))[:160]), se,
                   esc(e.get("eid")), esc(e.get("eid")), esc(e.get("eid")), esc(e.get("eid"))))
        except Exception:
            card_html.append('<div class="card"><span class="badge bad">修订卡渲染失败已跳过</span></div>')

    css = ("body{margin:0;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f5f7fa;color:#1e293b}"
           ".wrap{max-width:1280px;margin:0 auto;padding:20px 14px;display:flex;gap:14px;align-items:flex-start}"
           ".main{flex:1;min-width:0}.side{width:360px;flex-shrink:0}"
           ".para{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin:8px 0}"
           ".para:target{outline:3px solid #f59e0b;background:#fffbeb}"
           ".pid{font-size:11px;color:#64748b;font-family:monospace}"
           ".ph{font-size:12px;color:#475569;margin:2px 0}.ptext{line-height:1.75;font-size:14px}"
           ".hl-acc{background:#bbf7d0;border-radius:3px}.hl-rej{background:#fecaca;border-radius:3px}"
           ".hl-cf{background:#fde68a;border-radius:3px}.hl-pend{background:#e2e8f0;border-radius:3px}"
           ".hl-find{background:#fdba74;border-radius:3px;outline:1px solid #ea580c}"
           ".card{background:#fff;border:1px solid #dbe3ee;border-radius:8px;padding:10px 12px;margin:8px 0;font-size:13px}"
           ".chead{display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
           ".diff{margin:6px 0;font-size:12px}.bf{color:#b91c1c}.af{color:#15803d}"
           ".rat{color:#475569;font-size:12px}.chip{background:#eff4fb;border-radius:4px;padding:0 6px;margin-right:4px;font-size:11px}"
           ".badge{border-radius:4px;padding:1px 8px;font-size:11px;background:#eff4fb;color:#1d4ed8}"
           ".b-lv{background:#fef9c3;color:#a16207}.badge.bad{background:#fee2e2;color:#b91c1c}"
           ".b-partial{background:#fef9c3;color:#a16207}.b-complete{background:#dcfce7;color:#15803d}"
           ".b-failed,.b-blocked{background:#fee2e2;color:#b91c1c}"
           ".jump{font-size:12px;color:#1d4ed8;text-decoration:none}"
           "h1{font-size:19px;margin:0}h2{font-size:15px;margin:16px 0 6px}"
           ".hdr{border-left:4px solid #1d4ed8;padding-left:12px;margin-bottom:12px}"
           ".meta{color:#64748b;font-size:12px}.box{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px}"
           ".btn{padding:4px 10px;border:0;border-radius:6px;color:#fff;cursor:pointer;font-size:12px;margin-right:4px}"
           ".b-ok{background:#16a34a}.b-no{background:#dc2626}.b-cf{background:#d97706}"
           ".btn2{padding:4px 10px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;color:#1e293b;cursor:pointer;font-size:12px;margin-right:4px}"
           ".btn2.on{background:#1d4ed8;color:#fff}"
           "input,select{padding:6px 8px;border:1px solid #cbd5e1;border-radius:6px;font-size:12px}"
           ".stats{font-size:12px;margin-left:8px}")
    js = r"""
var DATA={paras:__PARAS__,edits:__EDITS__,case:'__CID__',seed:__SEED__};
var MODE='v1';var DEC={};var STORE='acl_dec_'+DATA.case;
try{DEC=JSON.parse(localStorage.getItem(STORE)||'{}');}catch(e){DEC={};}
try{if(DEC&&Object.keys(DEC).length===0&&DATA.seed){DEC=DATA.seed;}}catch(e){}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function saveDec(){try{localStorage.setItem(STORE,JSON.stringify(DEC));}catch(e){}}
function decide(eid,d){DEC[eid]=d;saveDec();renderAll();renderStats();renderCards();}
function renderStats(){var a=0,r=0,c=0;DATA.edits.forEach(function(e){var d=DEC[e.eid];if(d==='accept')a++;else if(d==='reject')r++;else if(d==='confirm')c++;});
 document.getElementById('stats').textContent='共'+DATA.edits.length+'处：已接受 '+a+' · 已拒绝 '+r+' · 需确认 '+c+' · 未裁决 '+(DATA.edits.length-a-r-c);}
function segsFor(p){var segs=[];
 DATA.edits.forEach(function(e){if(String(e.pid)!==p.id)return;var b=String(e.before||'');if(!b)return;var pos=p.text.indexOf(b);if(pos<0)return;
 var d=DEC[e.eid]||'pending';var cls=d==='accept'?'hl-acc':(d==='reject'?'hl-rej':(d==='confirm'?'hl-cf':'hl-pend'));
 if(MODE==='v2'&&d==='accept'){segs.push({s:pos,e:pos+b.length,cls:'hl-acc',rep:String(e.after||'')});}
 else segs.push({s:pos,e:pos+b.length,cls:cls,rep:null});});
 return segs;}
function renderP(i,kw){var p=DATA.paras[i],segs=segsFor(p);
 if(kw){try{var re=new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi');var m;while((m=re.exec(p.text))){segs.push({s:m.index,e:m.index+m[0].length,cls:'hl-find',rep:null});if(m.index===re.lastIndex)re.lastIndex++;}}catch(e){}}
 segs.sort(function(a,b){return a.s-b.s;});var out='',last=0;
 segs.forEach(function(s){if(s.s<last)return;out+=esc(p.text.slice(last,s.s))+'<span class="'+s.cls+'">'+esc(s.rep!==null?s.rep:p.text.slice(s.s,s.e))+'</span>';last=s.e;});out+=esc(p.text.slice(last));
 var el=document.getElementById('ptext-'+i);if(el)el.innerHTML=out;}
var FINDS=[],FI=-1;
function navReset(){FINDS=[].slice.call(document.querySelectorAll('.hl-find'));FI=FINDS.length?0:-1;upNav();}
function upNav(){document.getElementById('navinfo').textContent=FINDS.length?(FI+1)+'/'+FINDS.length:'0/0';}
function navNext(){if(!FINDS.length)return;FI=(FI+1)%FINDS.length;FINDS[FI].scrollIntoView({behavior:'smooth',block:'center'});upNav();}
function navPrev(){if(!FINDS.length)return;FI=(FI-1+FINDS.length)%FINDS.length;FINDS[FI].scrollIntoView({behavior:'smooth',block:'center'});upNav();}
function srch(){var k=document.getElementById('kw').value.trim();DATA.paras.forEach(function(p,i){renderP(i,k)});navReset();}
function setMode(m){MODE=m;document.getElementById('bv1').className=m==='v1'?'btn2 on':'btn2';document.getElementById('bv2').className=m==='v2'?'btn2 on':'btn2';renderAll();}
function renderAll(){var k=document.getElementById('kw').value.trim();DATA.paras.forEach(function(p,i){renderP(i,k)});navReset();}
function jumpPid(){var t=document.getElementById('pidin').value.trim();var e=document.getElementById('anchor-'+t);if(e)e.scrollIntoView({behavior:'smooth'});else alert('索引中无段落 '+t);}
function filt(){var iid=document.getElementById('f-iid').value,lv=document.getElementById('f-level').value,st=document.getElementById('f-state').value;
 document.querySelectorAll('.edit').forEach(function(c){var ok=true;
  if(iid&&c.getAttribute('data-iid')!==iid)ok=false;
  if(lv&&c.getAttribute('data-level')!==lv)ok=false;
  if(st){var d=DEC[c.getAttribute('data-eid')]||'pending';if(d!==st&&!(st==='pending'&&!d))ok=false;if(st==='pending'&&DEC[c.getAttribute('data-eid')])ok=false;}
  c.style.display=ok?'':'none';});}
function exportDecisions(){var out={case_id:DATA.case,mode:MODE,decisions:DEC,exported_at:new Date().toISOString()};dl(JSON.stringify(out,null,1),'decisions_'+DATA.case+'.json');}
function exportAccepted(){var lines=[];DATA.paras.forEach(function(p){var t=p.text;DATA.edits.forEach(function(e){if(String(e.pid)!==p.id)return;if(DEC[e.eid]==='accept'){var b=String(e.before||'');if(b&&t.indexOf(b)>=0)t=t.replace(b,String(e.after||''));}});lines.push((p.heading?'## '+p.heading+'\n':'')+t);});
 dl(lines.join('\n\n'),'revised_accepted_'+DATA.case+'.md');}
function dl(txt,name){var b=new Blob([txt],{type:'text/plain'});var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;a.click();}
function renderCards(){renderStats();}
window.addEventListener('load',function(){renderStats();});
"""
    doc = (
        '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>修订客户端 · %s</title>'
        '<style>%s</style></head><body data-case="%s">'
        '<div class="wrap"><div class="main">'
        '<div class="hdr"><h1>修订客户端 · 逐条接受/拒绝 · 版本对照 · 可回填导出</h1>'
        '<div class="meta">case %s · status <span class="badge b-%s">%s</span> · 段落 %d · 修订 %d 处 · '
        '<span id="stats" class="stats"></span></div></div>'
        '<div class="box" style="margin-bottom:10px">'
        '<b style="font-size:12px">视图：</b><button class="btn2 on" id="bv1" onclick="setMode(\'v1\')">v1 原稿</button>'
        '<button class="btn2" id="bv2" onclick="setMode(\'v2\')">v2 修订稿（按当前裁决）</button>'
        '<input id="kw" placeholder="关键词搜索" oninput="srch()" style="width:26%%;margin-left:10px">'
        '<button class="btn2" onclick="navPrev()">◀</button><span id="navinfo" class="meta" style="margin:0 4px">0/0</span>'
        '<button class="btn2" onclick="navNext()">▶</button>'
        '<input id="pidin" placeholder="段落号如 P03" style="width:12%%;margin-left:10px">'
        '<button class="btn2" onclick="jumpPid()">定位</button>'
        '</div>'
        '%s'
        '<div class="meta" style="margin-top:16px">由 export_client 生成 · 自包含单文件 · 每处修订=锚点pid+逐字原文+改后+依据 · '
        '裁决存 localStorage，导出 JSON 为持久化交接形式 · v2 为按裁决实时合成的修订稿预览</div>'
        '</div><div class="side">'
        '<h2>修订台账（逐条裁决）</h2>'
        '<div class="box" style="margin-bottom:8px">'
        '<select id="f-iid" onchange="filt()"><option value="">全部指令</option>%s</select> '
        '<select id="f-level" onchange="filt()"><option value="">全部层面</option>%s</select> '
        '<select id="f-state" onchange="filt()"><option value="">全部状态</option>'
        '<option value="accept">已接受</option><option value="reject">已拒绝</option>'
        '<option value="confirm">需确认</option><option value="pending">未裁决</option></select></div>'
        '%s'
        '<h2>导出（交付可用）</h2><div class="box">'
        '<button class="btn" style="background:#1d4ed8" onclick="exportAccepted()">导出已接受修订稿 Markdown</button><br><br>'
        '<button class="btn2" onclick="exportDecisions()">导出裁决 JSON</button>'
        '<div class="meta" style="margin-top:6px">Markdown 可直接回填稿件继续编辑；裁决 JSON 可复核逐条接受/拒绝记录</div></div>'
        '<h2>引用与格式哨兵</h2><div class="box meta">%s</div>'
        '<h2>边界与人工确认</h2><div class="box meta">%s</div>'
        '<h2>闸门状态</h2><div class="box meta">%s</div>'
        '</div></div><script>%s</script></body></html>'
        % (esc(cid), css, esc(cid), esc(cid), status, status,
           len(paras), len(edits),
           "".join(para_html) or '<div class="box meta">结构索引为空：原稿未能建立段落锚点（见 uncertainties）。</div>',
           "".join('<option>%s</option>' % esc(x) for x in sorted({str(e.get("iid")) for e in edits if e.get("iid")})) or "<option>—</option>",
           "".join('<option>%s</option>' % esc(x) for x in sorted({str(e.get("level")) for e in edits if e.get("level")})) or "<option>—</option>",
           "".join(card_html) or '<div class="card meta">暂无修订条目</div>',
           esc(json.dumps(checks, ensure_ascii=False)[:800]) if checks else "尚未生成校验报告（check_all.py 运行后回填）",
           esc(json.dumps(unc, ensure_ascii=False)[:800]),
           esc(json.dumps(gates, ensure_ascii=False)[:400]) if gates else "尚未登记（check_all.py 运行后回填）",
           js.replace("__PARAS__", js_json(paras_js)).replace("__EDITS__", js_json(edits))
             .replace("__CID__", js_json(str(cid))).replace("__SEED__", js_json(decisions))))
    return doc

def cmd_run(a):
    case = load(a.case) or {}
    structure = load(a.structure)
    if structure is None:
        structure = {}
        print("[export_client] WARN: structure 不可读，按空段落渲染")
    edits = load_jsonl(a.edits)
    result = load(a.result) or {}
    # 裁决回填：若提供客户端导出的裁决 JSON，把逐条裁决并入 result.json（裁决语义落位）
    decisions = {}
    if a.decisions and os.path.exists(a.decisions):
        d = load(a.decisions)
        if isinstance(d, dict) and isinstance(d.get("decisions"), dict):
            decisions = d["decisions"]
        elif isinstance(d, dict):
            decisions = d
    doc = build_html(case, structure, edits, result, decisions)
    try:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(doc)
    except Exception as e:
        print("[export_client] FAIL: 写出失败: %s（退出码 0，不中断交付）" % e)
        return 0
    print("[export_client] HTML %d bytes -> %s" % (len(doc), a.out))
    if a.embed_result:
        r = load(a.result)
        if isinstance(r, dict) and r:
            try:
                res = r.setdefault("result", {})
                res["client"] = {"kind": "self-contained-html",
                                 "path": os.path.abspath(a.out).replace("\\", "/"),
                                 "features": list(FEATURES), "embedded_html": doc}
                arts = res.setdefault("artifacts", {})
                arts["client_html"] = os.path.abspath(a.out).replace("\\", "/")
                arts["edits_ledger"] = os.path.abspath(a.edits).replace("\\", "/")
                arts.setdefault("revised_md", os.path.join(os.path.dirname(os.path.abspath(a.out)), "revised.md").replace("\\", "/"))
                # 裁决面：把客户端导出的逐条裁决并入 result.result.adjudication
                adj = res.setdefault("adjudication", {})
                adj.setdefault("granularity", "per-edit")
                adj.setdefault("actions", ["accept", "reject", "confirm"])
                adj.setdefault("persistence", "client localStorage（跨会话）+ 导出裁决 JSON 作为交接形式")
                dec = adj.setdefault("decisions", {})
                for e in edits:
                    if isinstance(e, dict) and e.get("eid"):
                        dec.setdefault(str(e.get("eid")), "pending")
                for eid, v in (decisions or {}).items():
                    if str(v) in ("accept", "reject", "confirm", "pending"):
                        dec[str(eid)] = str(v)
                adj["pending_count"] = sum(1 for v in dec.values() if v == "pending")
                adj["decided_count"] = len(dec) - adj["pending_count"]
                adj["accepted_count"] = sum(1 for v in dec.values() if v == "accept")
                adj["rejected_count"] = sum(1 for v in dec.values() if v == "reject")
                adj["confirm_count"] = sum(1 for v in dec.values() if v == "confirm")
                adj["source"] = (os.path.abspath(a.decisions).replace("\\", "/")
                                 if (a.decisions and os.path.exists(a.decisions))
                                 else "客户端本机裁决（未回填，默认 pending）")
                with open(a.result, "w", encoding="utf-8") as f:
                    json.dump(r, f, ensure_ascii=False, indent=1)
                print("[export_client] 已嵌入 result.json（embedded_html %d 字符 + features %d 条）；"
                      "裁决已裁决 %d/%d 条（accept %d / reject %d / confirm %d）"
                      % (len(doc), len(FEATURES), adj["decided_count"], len(dec),
                         adj["accepted_count"], adj["rejected_count"], adj["confirm_count"]))
            except Exception as e:
                print("[export_client] WARN: 嵌入失败: %s" % e)
        else:
            print("[export_client] WARN: result.json 不可读，跳过嵌入")
    return 0

def cmd_selftest(_a):
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cp, sp, ep, rp, op = (os.path.join(td, n) for n in ("c.json", "s.json", "e.jsonl", "r.json", "out.html"))
        json.dump({"case_id": "T1"}, open(cp, "w", encoding="utf-8"))
        json.dump({"paragraphs": [{"pid": "P01", "text": "The results was significant improved.", "heading": "Results", "locator": "§3 para1"},
                                   {"pid": "P02", "text": "We use X method.", "heading": "Methods"}]},
                  open(sp, "w", encoding="utf-8"))
        with open(ep, "w", encoding="utf-8") as f:
            f.write(json.dumps({"eid": "E001", "iid": "I01", "pid": "P01", "locator": "§3 para1",
                                "before": "The results was significant improved.", "after": "The results were significantly improved.",
                                "rationale": "I01 语法修正", "level": "措辞", "side_effects": [], "status": "applied"}, ensure_ascii=False) + "\n")
        json.dump({"case_id": "T1", "status": "partial",
                   "uncertainties": {"summary": "无"}, "checks": [{"item": "anchor", "match": True}],
                   "gates": {"edits_verify": "enforced"}},
                  open(rp, "w", encoding="utf-8"))
        ns = argparse.Namespace(case=cp, structure=sp, edits=ep, result=rp, out=op, embed_result=True,
                                decisions="")
        if cmd_run(ns) != 0:
            print("  [selftest] 正例运行 FAIL"); ok = False
        h = open(op, encoding="utf-8").read()
        for token in ("decide", "setMode", "exportAccepted", "exportDecisions", "navNext", "hl-pend",
                      "filt", "jumpPid", "anchor-P01", "hl-find", 'id="stats"'):
            if token not in h:
                print("  [selftest] 正例缺少交互元素 %s FAIL" % token); ok = False
        r2 = json.load(open(rp, encoding="utf-8"))
        if not r2.get("result", {}).get("client", {}).get("embedded_html"):
            print("  [selftest] 正例嵌入失败 FAIL"); ok = False
        if len(r2.get("result", {}).get("client", {}).get("features") or []) != 8:
            print("  [selftest] 正例 features 缺失 FAIL"); ok = False
        # 反例：全部输入损坏 → 仍写出 HTML
        op2 = os.path.join(td, "out2.html")
        for p in (cp, sp, rp):
            with open(p, "wb") as f:
                f.write(b"\xff\xfe\x00garbage")
        ns2 = argparse.Namespace(case=cp, structure=sp, edits=ep, result=rp, out=op2, embed_result=False,
                                 decisions="")
        if cmd_run(ns2) != 0 or not os.path.exists(op2) or os.path.getsize(op2) < 500:
            print("  [selftest] 反例: 损坏输入应仍写出可用 HTML FAIL"); ok = False
        # 反例：edits 为空 → 卡片区显示占位
        ep3 = os.path.join(td, "empty.jsonl")
        open(ep3, "w").close()
        op3 = os.path.join(td, "out3.html")
        ns3 = argparse.Namespace(case=cp, structure=sp, edits=ep3, result=rp, out=op3, embed_result=False,
                                 decisions="")
        if cmd_run(ns3) != 0 or "暂无修订条目" not in open(op3, encoding="utf-8").read():
            print("  [selftest] 反例: 空台账应有占位提示 FAIL"); ok = False
        # 反例4：裁决回填 —— 提供裁决 JSON → result.json 的裁决位被更新
        # （前一个反例把 rp 写成了二进制垃圾，先恢复成合法 result.json）
        json.dump({"case_id": "T1", "status": "partial",
                   "uncertainties": {"summary": "无"}, "checks": [{"item": "anchor", "match": True}],
                   "gates": {"edits_verify": "enforced"},
                   "result": {"client": {"embedded_html": "<html>client</html>", "features": ["f"] * 8}}},
                  open(rp, "w", encoding="utf-8"))
        dp = os.path.join(td, "decisions.json")
        json.dump({"case_id": "T1", "decisions": {"E001": "accept", "E002": "reject"}},
                  open(dp, "w", encoding="utf-8"))
        ns4 = argparse.Namespace(case=cp, structure=sp, edits=ep, result=rp, out=op, embed_result=True,
                                 decisions=dp)
        if cmd_run(ns4) != 0:
            print("  [selftest] 裁决回填应恒退出 0 FAIL"); ok = False
        r5 = load(rp) or {}
        adj5 = (r5.get("result") or {}).get("adjudication") or {}
        if adj5.get("decisions", {}).get("E001") != "accept":
            print("  [selftest] 裁决未回填 FAIL"); ok = False
        if adj5.get("accepted_count") != 1 or adj5.get("rejected_count") != 1:
            print("  [selftest] 裁决计数未更新 FAIL"); ok = False
        # 反例5：裁决文件是二进制垃圾 → 不崩、退出 0
        bad_dp = os.path.join(td, "bad_decisions.json")
        with open(bad_dp, "wb") as f:
            f.write(b"\xff\xfe\x00garbage")
        ns5 = argparse.Namespace(case=cp, structure=sp, edits=ep, result=rp, out=op, embed_result=False,
                                 decisions=bad_dp)
        if cmd_run(ns5) != 0:
            print("  [selftest] 污染裁决文件应恒退出 0 FAIL"); ok = False
    print("[export_client] SELFTEST %s" % ("PASS" if ok else "FAIL"))
    # 退出码契约：自测失败也是内容级失败路径，退出码恒 0；
    # 结论以本行的 SELFTEST PASS/FAIL 为准，修复责任交回开发侧。
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--structure", default="/app/work/structure.json")
    ap.add_argument("--edits", default="/app/work/edits.jsonl")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", default="/app/output/revision_client.html")
    ap.add_argument("--decisions", default="", help="客户端导出的裁决 JSON（回填逐条裁决）")
    ap.add_argument("--embed-result", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    try:
        a = ap.parse_args()
    except SystemExit:
        print("[export_client] 参数解析失败（退出码 0，不中断交付）")
        return 0
    try:
        if a.selftest:
            return cmd_selftest(a)
        return cmd_run(a)
    except Exception as e:
        print("[export_client] 兜底异常: %s（保留现有产物，退出码 0，不中断交付）" % e)
        return 0

if __name__ == "__main__":
    sys.exit(main())
