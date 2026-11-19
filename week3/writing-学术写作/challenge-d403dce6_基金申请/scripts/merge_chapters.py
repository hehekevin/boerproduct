#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_chapters.py — 把逐章写出的章节文件合并为完整 draft.json
各章文件（/app/work/chapters/chNN_*.json 或 .md）按文件名排序合并：
  - .json  : 单节 draft 片段 {"heading":..., "level":..., "paragraphs":[...], "comments":[...]}
  - .md    : 以 '#'/## 开头的 Markdown 片段（首行作 heading，其余整段作为段落）
合并产物可直接交给 docx_build.py 构建 docx/md。

用法:
  python3 merge_chapters.py --chapters-dir /app/work/chapters --out /app/work/draft.json \
      [--title "申请书标题"] [--meta-file /app/work/meta.json]
"""
import argparse, glob, json, os, re, sys

def from_md(text, fname):
    lines = text.splitlines()
    heading, level = fname, 1
    body = []
    for ln in lines:
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m and not body:
            level = min(3, len(m.group(1)))
            heading = m.group(2) or fname
            continue
        if ln.strip():
            body.append(ln.strip())
    return {"heading": heading, "level": level,
            "paragraphs": body or ["（本章为空）"]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="基金申请书（章节稿）")
    ap.add_argument("--meta-file", default=None)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.chapters_dir, "ch*.*")))
    sections, missing = [], []
    if not files:
        missing.append("chapters_dir 无 ch* 文件")
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
            if f.endswith(".json"):
                sec = json.loads(text)
                if "heading" not in sec:
                    sec["heading"] = os.path.basename(f)
                sections.append(sec)
            else:
                sections.append(from_md(text, os.path.basename(f)))
        except Exception as e:
            missing.append(f"{os.path.basename(f)}: parse_failed {str(e)[:80]}")

    draft = {"title": args.title, "meta": {}, "sections": sections,
             "references": [], "notes_for_human": []}
    if args.meta_file and os.path.exists(args.meta_file):
        try:
            draft["meta"] = json.load(open(args.meta_file, encoding="utf-8"))
        except Exception:
            missing.append("meta_file parse_failed")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(draft, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"ok": True, "out": args.out, "sections": len(sections),
                      "warnings": missing}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # 容错：合稿失败也返回 0 并如实登记，不中断交付链
        print(json.dumps({"ok": False, "error": str(e)[:300]}, ensure_ascii=False))
        sys.exit(0)
