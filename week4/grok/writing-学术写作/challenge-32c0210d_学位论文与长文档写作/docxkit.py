"""docxkit — stdlib Markdown + valid editable DOCX writer (no python-docx needed).

Emits the editable manuscript required by the writing track: manuscript.md and a
minimal-but-valid OOXML manuscript.docx (headings hierarchy, paragraphs, figure
captions, references, declarations). Text stays editable (real runs, not images);
heading styles bind to a styles.xml so Word/Markdown keep structure (改得动).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


def _md(ir: dict) -> str:
    out = [f"# {ir.get('title', '')}", ""]
    if ir.get("abstract"):
        out += ["## Abstract", "", ir["abstract"], ""]
    for s in ir.get("sections", []):
        lvl = min(max(int(s.get("level", 1)), 1), 4)
        out += ["#" * (lvl + 1) + " " + s.get("heading", ""), ""]
        for p in s.get("paragraphs", []):
            out += [p.get("text", ""), ""]
        for f in s.get("figures", []):
            out += [f"**{f.get('ref', 'Figure')}** {f.get('caption', '')}", ""]
    if ir.get("citations"):
        out += ["## References", ""]
        for i, c in enumerate(ir["citations"], 1):
            out += [f"[{i}] {c.get('authors', '')} ({c.get('year', '')}). {c.get('title', '')}. "
                    f"{c.get('journal', '')}. doi:{c.get('doi', '')}", ""]
    for d in ir.get("declarations", []):
        out += [f"## {d.get('name', 'Declaration')}", "", d.get("text", ""), ""]
    return "\n".join(out)


def _p(text, style=None):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def _docx_body(ir: dict) -> str:
    body = [_p(ir.get("title", ""), "Title")]
    if ir.get("abstract"):
        body += [_p("Abstract", "Heading1"), _p(ir["abstract"])]
    for s in ir.get("sections", []):
        lvl = min(max(int(s.get("level", 1)), 1), 3)
        body += [_p(s.get("heading", ""), f"Heading{lvl}")]
        for p in s.get("paragraphs", []):
            body += [_p(p.get("text", ""))]
        for f in s.get("figures", []):
            body += [_p(f"{f.get('ref', 'Figure')} {f.get('caption', '')}", "Caption")]
    if ir.get("citations"):
        body += [_p("References", "Heading1")]
        for i, c in enumerate(ir["citations"], 1):
            body += [_p(f"[{i}] {c.get('authors', '')} ({c.get('year', '')}). {c.get('title', '')}. "
                        f"{c.get('journal', '')}. doi:{c.get('doi', '')}")]
    for d in ir.get("declarations", []):
        body += [_p(d.get("name", "Declaration"), "Heading1"), _p(d.get("text", ""))]
    return "".join(body)


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:rPr><w:i/><w:sz w:val="20"/></w:rPr></w:style>
</w:styles>"""


def write_docx(path: Path, ir: dict) -> None:
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:body>{_docx_body(ir)}<w:sectPr/></w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)


def write_manuscript(ir: dict, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "manuscript.md"
    md.write_text(_md(ir), encoding="utf-8")
    docx = out_dir / "manuscript.docx"
    write_docx(docx, ir)
    return {"md": str(md), "docx": str(docx)}