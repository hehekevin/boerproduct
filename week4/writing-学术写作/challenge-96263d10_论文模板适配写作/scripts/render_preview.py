#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_preview.py — 交付预览（交得出）：docx → PDF/PNG 供复核

尝试环境预装的渲染器（soffice/libreoffice）把 adapted.docx 渲染为 PDF（可选 PNG 首页）；
渲染器缺失或失败时如实记录 status=no_renderer/render_failed，交付 docx+md 不受影响，
不伪造渲染结果。退出码恒 0。
"""
import argparse, json, os, shutil, subprocess, sys, time

try:
    import _rlog
except Exception:
    _rlog = None


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 "/usr/bin/soffice", "/usr/local/bin/soffice"):
        if os.path.exists(cand):
            return cand
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/app/output/adapted.docx")
    ap.add_argument("--outdir", default="/app/output/previews")
    args, err = None, None
    try:
        args = ap.parse_args()
    except SystemExit as e:
        err = e
    if args is None:
        print(json.dumps({"ok": False, "note": "argparse error（非致命，恒 exit 0）", "detail": str(err)}, ensure_ascii=False))
        return 0
    t0 = time.time()
    os.makedirs(args.outdir, exist_ok=True)
    log = {"src": args.src, "status": None}
    if not os.path.exists(args.src):
        log["status"] = "src_missing"
        log["note"] = "源文件不存在：无预览可渲染；下游不得宣称渲染已核对"
    else:
        soffice = find_soffice()
        if not soffice:
            log["status"] = "no_renderer"
            log["note"] = "环境无 soffice/libreoffice：交付 docx+md（可编辑），不伪造渲染"
        else:
            try:
                cmd = [soffice, "--headless", "--convert-to", "pdf", "--outdir", args.outdir, args.src]
                r = subprocess.run(cmd, capture_output=True, timeout=120)
                pdf = os.path.join(args.outdir, os.path.splitext(os.path.basename(args.src))[0] + ".pdf")
                if r.returncode == 0 and os.path.exists(pdf):
                    log["status"] = "rendered"
                    log["pdf"] = pdf
                else:
                    log["status"] = "render_failed"
                    log["stderr"] = (r.stderr or b"").decode("utf-8", "ignore")[:200]
            except Exception as e:
                log["status"] = "render_failed"
                log["error"] = str(e)[:200]
    out = os.path.join(args.outdir, "render_log.json")
    try:
        json.dump(log, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log["written"] = True
    except Exception as e:
        log["written"] = False; log["write_error"] = str(e)[:200]
    print(json.dumps({"ok": True, "status": log["status"], "out": out}, ensure_ascii=False))
    if _rlog is not None:
        _rlog.log_call("render_preview", argv=sys.argv[1:], seconds=time.time() - t0,
                       extra={"status": log["status"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
