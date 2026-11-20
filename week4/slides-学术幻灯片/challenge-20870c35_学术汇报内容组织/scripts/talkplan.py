#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""talkplan.py — 学术汇报内容组织的可核验工具（单文件四子命令）。

  extract <pdf|docx|md> --outdir DIR            源材料 → 纯文本 + 页锚点
  check   talk_plan.json [--source TEXT] [--out R.json]
                                               机械校验四元组/时长/证据/问答
  build   talk_plan.json OUT.pptx [--template T] [--log L.json]
                                               页级四元组 → 可编辑 pptx（含备注）
  render  OUT.pptx --outdir DIR                导出 PDF/PNG 预览

设计原则：talk_plan.json 是唯一事实源，deck/result.json 都从它派生，
避免"计划一份、成稿另一份"的不可核验问题。仅依赖标准库；
extract 用 PyMuPDF，build 用 python-pptx，二者缺失时如实降级并记录。
"""
import sys, os, re, json, argparse, subprocess, shutil, glob

CJK = re.compile(r'[\u4e00-\u9fff]')


def norm(s):
    return re.sub(r'\s+', '', str(s or ''))


def clen(s):
    return len(norm(s))


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def dump(obj, p):
    os.makedirs(os.path.dirname(os.path.abspath(p)) or '.', exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- extract
def cmd_extract(a):
    src, outdir = a.file, a.outdir
    os.makedirs(outdir, exist_ok=True)
    res = {"ok": False, "source": os.path.basename(src), "tool": None,
           "chars": 0, "pages": 0, "text": None, "warnings": []}
    ext = os.path.splitext(src)[1].lower()
    text = None
    if ext == '.pdf':
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(src)
            chunks = []
            for i, page in enumerate(doc, 1):
                chunks.append("\n===== PAGE %d =====\n" % i + page.get_text())
            text = "".join(chunks)
            res.update(tool='pymupdf', pages=doc.page_count)
        except Exception as e:
            res["warnings"].append("pymupdf unavailable/failed: %s" % e)
            for tool in (['pdftotext', '-layout', src, '-'],):
                if shutil.which(tool[0]):
                    try:
                        text = subprocess.run(tool, capture_output=True, text=True,
                                              timeout=180).stdout
                        res.update(tool='pdftotext')
                        break
                    except Exception as e2:
                        res["warnings"].append("pdftotext failed: %s" % e2)
    elif ext in ('.docx',):
        try:
            import docx
            text = "\n".join(p.text for p in docx.Document(src).paragraphs)
            res.update(tool='python-docx')
        except Exception as e:
            res["warnings"].append("python-docx unavailable/failed: %s" % e)
    if text is None:
        try:
            with open(src, encoding='utf-8', errors='replace') as f:
                text = f.read()
            res.update(tool=res["tool"] or 'plain-read')
        except Exception as e:
            res["warnings"].append("read failed: %s" % e)
            text = ""
    text = text or ""
    res["chars"] = len(text)
    res["pages"] = res["pages"] or len(re.findall(r'===== PAGE \d+ =====', text))
    res["scanned"] = res["chars"] < 200 and ext == '.pdf'
    if res["scanned"]:
        res["warnings"].append("文本极少，可能是扫描件：转 OCR 并用页码作 locator")
    tp = os.path.join(outdir, 'source_text.txt')
    with open(tp, 'w', encoding='utf-8') as f:
        f.write(text)
    res["text"] = tp
    res["ok"] = bool(text.strip())
    dump(res, os.path.join(outdir, 'extract_manifest.json'))
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res["ok"] else 2


# ---------------------------------------------------------------- check
AUD = {'defense', 'group_meeting', 'review', 'public', 'grant', 'lecture'}
CAT = {'mechanism', 'data', 'control', 'limitation'}
LAYOUT = {'title', 'bullets', 'figure', 'table', 'closing', 'section'}
STRENGTH = {'强', '中', '弱'}
NUM = re.compile(r'\d+(?:\.\d+)?\s*(?:%|‰)?')
STRONG_WORDS = ('证明', '首次', '显著优于', '完全', '必然')


def cmd_check(a):
    plan = load(a.plan)
    src = None
    if a.source and os.path.exists(a.source):
        with open(a.source, encoding='utf-8', errors='replace') as f:
            src = f.read()
    checks = []

    def add(code, ok, detail, level='fail'):
        checks.append({"code": code, "level": 'pass' if ok else level,
                       "detail": detail})

    # C1 契约与标识
    c = plan.get('case_id') or ''
    con = plan.get('constraints') or {}
    add('C1_contract',
        bool(c) and isinstance(con.get('duration_min'), (int, float))
        and con.get('duration_min', 0) > 0 and int(con.get('slides_max') or 0) > 0,
        "case_id=%s duration_min=%s slides_max=%s source=%s"
        % (c, con.get('duration_min'), con.get('slides_max'), con.get('source')))

    # C2 受众适配可核验
    aud = plan.get('audience') or {}
    goal = plan.get('goal') or {}
    adap = plan.get('adaptation') or []
    add('C2_audience',
        aud.get('type') in AUD and bool(aud.get('prior_knowledge'))
        and len(aud.get('concerns') or []) >= 2,
        "type=%s prior=%s concerns=%d" % (aud.get('type'), bool(aud.get('prior_knowledge')),
                                          len(aud.get('concerns') or [])))
    add('C2_goal',
        bool(goal.get('statement')) and len(goal.get('checkpoints') or []) >= 2,
        "checkpoints=%d" % len(goal.get('checkpoints') or []))
    bad_adapt = [d for d in adap if not (d.get('decision') and d.get('because')
                                         and d.get('from') in ('goal', 'audience', 'duration', 'evidence'))]
    add('C2_adaptation', len(adap) >= 3 and not bad_adapt,
        "adaptation=%d bad=%d（每条需 decision/because/from）" % (len(adap), len(bad_adapt)))

    # C3 页数 / 四元组完整性
    slides = plan.get('slides') or []
    mains = [s for s in slides if not s.get('backup')]
    backups = [s for s in slides if s.get('backup')]
    nos = [s.get('no') for s in slides]
    add('C3_pages',
        len(mains) <= int(con.get('slides_max') or 0) and len(set(nos)) == len(nos)
        and all(isinstance(n, int) for n in nos) and nos == sorted(nos),
        "main=%d max=%s backup=%d unique_no=%s" % (len(mains), con.get('slides_max'),
                                                   len(backups), len(set(nos)) == len(nos)))
    quad = []
    for s in slides:
        miss = [k for k in ('purpose', 'claim', 'evidence')
                if not s.get(k)] + ([] if (s.get('points') or []) else ['points'])
        if not isinstance(s.get('minutes'), (int, float)):
            miss.append('minutes')
        if miss:
            quad.append("s%s 缺 %s" % (s.get('no'), ','.join(miss)))
    add('C3_quad', not quad, "四元组(目的/要点/证据/时长)不全: %s" % (quad[:5] or 'none'))

    # C4 时长一致性（机械算式）
    dur = float(con.get('duration_min') or 0)
    secs = (plan.get('narrative') or {}).get('sections') or []
    s_sec = round(sum(float(x.get('minutes') or 0) for x in secs), 2)
    s_sld = round(sum(float(s.get('minutes') or 0) for s in mains), 2)
    add('C4_time_sum', abs(s_sec - dur) <= 0.05 and abs(s_sld - dur) <= 0.05,
        "duration=%.2f 节合计=%.2f 正片合计=%.2f" % (dur, s_sec, s_sld))
    covered = sorted({n for x in secs for n in (x.get('slides') or [])})
    add('C4_section_cover', covered == sorted(s.get('no') for s in mains),
        "节引用的页号与正片页号一致=%s" % (covered == sorted(s.get('no') for s in mains)))
    dens = [round(float(s.get('minutes') or 0), 2) for s in mains]
    bad_d = [s.get('no') for s in mains if not 0.4 <= float(s.get('minutes') or 0) <= 2.5]
    add('C4_density', not bad_d,
        "单页时长越界(0.4~2.5min): %s ; per_slide=%s"
        % (bad_d or 'none', round(dur / len(mains), 2) if mains else None), level='warn')
    add('C4_backup_zero', all(float(s.get('minutes') or 0) == 0 for s in backups),
        "备用页时长应为0：%s" % [s.get('no') for s in backups])

    # C5 主张颗粒度
    long_claim = [(s.get('no'), clen(s.get('claim'))) for s in slides if clen(s.get('claim')) > 25]
    too_many = [s.get('no') for s in slides if len(s.get('points') or []) > 5]
    long_pt = [(s.get('no'), clen(p)) for s in slides for p in (s.get('points') or []) if clen(p) > 40]
    add('C5_granularity', not long_claim and not too_many and not long_pt,
        "claim>25字:%s points>5:%s point>40字:%s" % (long_claim[:3], too_many[:3], long_pt[:3]))

    # C6 证据映射 + 逐字回查
    no_ev = [s.get('no') for s in slides if not (s.get('evidence') or [])]
    no_loc = [(s.get('no'), e) for s in slides for e in (s.get('evidence') or [])
              if not (e.get('locator') or '').strip()]
    add('C6_evidence', not no_ev and not no_loc,
        "无证据页:%s 无locator:%s" % (no_ev[:3], no_loc[:2]))
    if src is not None:
        ns = norm(src)
        bad_q = []
        for s in slides:
            for e in (s.get('evidence') or []):
                q = e.get('quote')
                if q and norm(q) not in ns:
                    bad_q.append({"slide": s.get('no'), "quote": str(q)[:60]})
        add('C6_verbatim', not bad_q, "quote 非逐字（改写过）: %s" % (bad_q[:4] or 'none'))
    else:
        add('C6_verbatim', False, "未提供 --source，跳过逐字回查（在 result 里记 uncertainty）",
            level='warn')

    # C7 数字可追溯：页内数字必须出现在本页 quote 或源材料
    src_n = norm(src) if src is not None else None
    untraced = []
    for s in slides:
        texts = " ".join([s.get('claim') or ''] + list(s.get('points') or []))
        quotes = norm(" ".join(str(e.get('quote') or '') for e in (s.get('evidence') or [])))
        for tok in set(NUM.findall(texts)):
            t = norm(tok)
            if t in quotes:
                continue
            if src_n is not None and t in src_n:
                continue
            untraced.append({"slide": s.get('no'), "token": tok,
                             "in_quote": False, "in_source": bool(src_n and t in src_n)})
    add('C7_numbers', not untraced, "数字无出处: %s" % (untraced[:5] or 'none'))

    # C8 结论强度与语气一致
    bad_st = [s.get('no') for s in slides if s.get('evidence_strength') not in STRENGTH]
    inflated = [s.get('no') for s in slides
                if s.get('evidence_strength') != '强'
                and any(w in (s.get('claim') or '') for w in STRONG_WORDS)]
    add('C8_strength', not bad_st and not inflated,
        "缺失强度:%s 弱证据用强断言:%s" % (bad_st[:3], inflated[:3]))

    # C9 图表引用绑定
    fig_bad = [s.get('no') for s in slides
               if (s.get('layout') == 'figure' and not s.get('figure_ref'))
               or (s.get('figure_ref') and s.get('layout') not in ('figure', 'table', 'bullets'))]
    add('C9_figure', not fig_bad, "图表引用与版式不一致: %s" % (fig_bad[:3] or 'none'),
        level='warn')

    # C10 讲稿备注：非页面复述 + 含预判问题
    bad_notes = []
    for s in mains:
        n = s.get('notes') or ''
        if not (40 <= clen(n) <= 600):
            bad_notes.append({"slide": s.get('no'), "why": "长度%s" % clen(n)})
        elif norm(n) == norm(s.get('claim')):
            bad_notes.append({"slide": s.get('no'), "why": "复述主张"})
    add('C10_notes', not bad_notes, "备注不合格: %s" % (bad_notes[:4] or 'none'))
    QMARK = ('？', '?', '若被问', '追问', '可能被问', '被问到')
    q_missing = [s.get('no') for s in mains
                 if not any(k in (s.get('notes') or '') for k in QMARK)]
    add('C10_notes_qa', not q_missing, "备注未含预判问题: %s" % (q_missing[:4] or 'none'),
        level='warn')

    # C11 问答准备
    qa = plan.get('qa') or []
    cats = {x.get('category') for x in qa}
    pno = {s.get('no') for s in slides}
    qbad = [x.get('q') for x in qa if not (x.get('q') and x.get('answer')
                                           and x.get('pointer_slide') in pno)]
    bbad = [x.get('q') for x in qa if x.get('backup_slide') not in (None, '')
            and (x.get('backup_slide') not in pno
                 or not any(s.get('no') == x.get('backup_slide') and s.get('backup') for s in slides))]
    add('C11_qa', len(qa) >= 4 and len(cats & CAT) >= 3 and not qbad and not bbad,
        "qa=%d 覆盖=%s 无效指针=%d 失效备用页=%d"
        % (len(qa), sorted(cats & CAT), len(qbad), len(bbad)))

    fails = [x for x in checks if x['level'] == 'fail']
    warns = [x for x in checks if x['level'] == 'warn']
    rep = {"plan": os.path.basename(a.plan), "source_checked": bool(src),
           "summary": {"total": len(checks), "pass": len(checks) - len(fails) - len(warns),
                       "fail": len(fails), "warn": len(warns),
                       "verdict": "pass" if not fails else "fail"},
           "metrics": {"duration_min": dur, "section_sum": s_sec, "slide_sum": s_sld,
                       "main_slides": len(mains), "backup_slides": len(backups),
                       "minutes_per_slide": round(dur / len(mains), 2) if mains else None,
                       "evidence_rows": sum(len(s.get('evidence') or []) for s in slides),
                       "qa_items": len(qa)},
           "checks": checks}
    if a.out:
        dump(rep, a.out)
    print(json.dumps(rep["summary"], ensure_ascii=False),
          json.dumps(rep["metrics"], ensure_ascii=False))
    if fails:
        print("FAIL:", json.dumps(fails, ensure_ascii=False, indent=1))
    if warns:
        print("WARN:", json.dumps(warns, ensure_ascii=False))
    return 0 if not fails else 1


# ---------------------------------------------------------------- build
FONT = os.environ.get('TALKPLAN_CJK_FONT', 'Noto Sans CJK SC')


def _layout_map(prs):
    m = {}
    for i, lay in enumerate(prs.slide_layouts):
        nm = (lay.name or '').lower()
        if 'title' in nm and 'slide' not in m:
            m['title'] = i
        elif ('two' in nm or 'content' in nm or 'text' in nm) and 'body' not in m:
            m['body'] = i
    m.setdefault('title', 0)
    m.setdefault('body', min(1, len(prs.slide_layouts) - 1))
    return m


def cmd_build(a):
    plan = load(a.plan)
    log = {"builder": None, "template": a.template, "warnings": [], "slides": []}
    try:
        from pptx import Presentation
        from pptx.util import Emu, Pt
    except Exception as e:
        log.update(builder='unavailable', warnings=["python-pptx 缺失: %s" % e])
        dump(log, a.log) if a.log else None
        print(json.dumps({"ok": False, "reason": "python_pptx_missing",
                          "detail": str(e),
                          "next": "交付 talk_plan.json + result.json（status=partial），"
                                  "并在 uncertainty 说明未产出 pptx"}, ensure_ascii=False))
        return 3
    prs = Presentation(a.template) if a.template and os.path.exists(a.template) else Presentation()
    if prs.slide_width is None or prs.slide_width < 100:
        prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    log["template_applied"] = bool(a.template and os.path.exists(a.template))
    lm = _layout_map(prs)
    W = prs.slide_width
    slides = plan.get('slides') or []
    for s in slides:
        role = 'title' if s.get('layout') == 'title' else 'body'
        sl = prs.slides.add_slide(prs.slide_layouts[lm[role]])
        # 标题
        title = s.get('claim') or s.get('title') or ''
        if s.get('layout') == 'title':
            title = s.get('title') or title
        tbox = None
        for ph in sl.placeholders:
            if ph.placeholder_format.idx == 0:
                tbox = ph
                break
        if tbox is None:
            tbox = sl.shapes.add_textbox(Emu(int(W * 0.06)), Emu(int(prs.slide_height * 0.07)),
                                         Emu(int(W * 0.88)), Emu(int(prs.slide_height * 0.16)))
        tbox.text = title
        for p in tbox.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(30 if s.get('layout') == 'title' else 24)
                r.font.name = FONT
        # 正文要点
        body = None
        for ph in sl.placeholders:
            if ph.placeholder_format.idx == 1:
                body = ph
                break
        if body is None:
            body = sl.shapes.add_textbox(Emu(int(W * 0.07)), Emu(int(prs.slide_height * 0.26)),
                                         Emu(int(W * 0.86)), Emu(int(prs.slide_height * 0.58)))
        tf = body.text_frame
        tf.word_wrap = True
        pts = s.get('points') or []
        tag = s.get('evidence_strength')
        lines = list(pts)
        meta = []
        if s.get('figure_ref'):
            meta.append("图示：%s" % s['figure_ref'])
        if tag:
            meta.append("证据强度：%s" % tag)
        if s.get('backup'):
            meta.append("备用页")
        if meta:
            lines.append("〔%s〕" % " · ".join(meta))
        tf.text = lines[0] if lines else ''
        for line in lines[1:]:
            p = tf.add_paragraph()
            p.text = line
        n = len(lines)
        size = 20 if n <= 3 else (18 if n == 4 else 16)
        for p in tf.paragraphs:
            p.space_after = Pt(8)
            for r in p.runs:
                r.font.size = Pt(size)
                r.font.name = FONT
        if n * size * 1.6 > prs.slide_height / 12700 * 0.58:
            log["warnings"].append("slide %s 可能溢出（%d 行 @%dpt），建议删要点勿缩字"
                                   % (s.get('no'), n, size))
        if s.get('notes'):
            sl.notes_slide.notes_text_frame.text = s['notes']
        log["slides"].append({"no": s.get('no'), "layout": s.get('layout'),
                              "bullets": len(pts), "font_pt": size,
                              "notes_chars": clen(s.get('notes'))})
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or '.', exist_ok=True)
    prs.save(a.out)
    log.update(builder='python-pptx', slides_built=len(slides),
               size_bytes=os.path.getsize(a.out))
    if a.log:
        dump(log, a.log)
    print(json.dumps({"ok": True, "file": a.out, "slides": len(slides),
                      "warnings": len(log["warnings"])}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- render
def cmd_render(a):
    outdir = a.outdir
    os.makedirs(outdir, exist_ok=True)
    log = {"status": "no_renderer", "pdf": None, "pngs": 0, "tried": []}
    cands = ['soffice', 'libreoffice', 'soffice.bin']
    exe = next((shutil.which(c) for c in cands if shutil.which(c)), None)
    if exe:
        log["tried"].append(exe)
        try:
            subprocess.run([exe, '--headless', '--convert-to', 'pdf', '--outdir', outdir, a.file],
                           capture_output=True, timeout=300)
            pdf = os.path.join(outdir, os.path.splitext(os.path.basename(a.file))[0] + '.pdf')
            if os.path.exists(pdf):
                log.update(status='ok', pdf=pdf)
                try:
                    import fitz
                    doc = fitz.open(pdf)
                    for i, page in enumerate(doc, 1):
                        page.get_pixmap(dpi=110).save(os.path.join(outdir, 'slide_%02d.png' % i))
                        log["pngs"] += 1
                except Exception as e:
                    log["status"] = 'pdf_only_no_png'
                    log["png_error"] = str(e)
        except Exception as e:
            log["error"] = str(e)
    else:
        log["error"] = 'soffice/libreoffice not found'
    dump(log, os.path.join(outdir, 'render_log.json'))
    print(json.dumps(log, ensure_ascii=False))
    return 0 if log["status"] == 'ok' else 4


def main():
    ap = argparse.ArgumentParser(description="talkplan — 学术汇报内容组织工具")
    sub = ap.add_subparsers(dest='cmd', required=True)

    e = sub.add_parser('extract', help='源材料→文本')
    e.add_argument('file')
    e.add_argument('--outdir', required=True)
    e.set_defaults(fn=cmd_extract)

    c = sub.add_parser('check', help='机械校验 talk_plan.json')
    c.add_argument('plan')
    c.add_argument('--source', default=None, help='源文本，用于 quote 逐字回查')
    c.add_argument('--out', default=None)
    c.set_defaults(fn=cmd_check)

    b = sub.add_parser('build', help='talk_plan.json→pptx')
    b.add_argument('plan')
    b.add_argument('out')
    b.add_argument('--template', default=None)
    b.add_argument('--log', default=None)
    b.set_defaults(fn=cmd_build)

    r = sub.add_parser('render', help='pptx→pdf/png')
    r.add_argument('file')
    r.add_argument('--outdir', required=True)
    r.set_defaults(fn=cmd_render)

    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == '__main__':
    main()
