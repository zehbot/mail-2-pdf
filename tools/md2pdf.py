#!/usr/bin/env python3
"""Markdown -> PDF (A4, druckfreundlich).

Aufruf:
    .venv/bin/python tools/md2pdf.py docs/speiseplan-per-mail.md docs/speiseplan-per-mail.pdf

Benötigt: pip install weasyprint markdown
"""

import sys
from pathlib import Path
import markdown
from weasyprint import HTML

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
md = src.read_text(encoding="utf-8")

html_body = markdown.markdown(
    md,
    extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
)

CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 16mm 16mm;
  @bottom-center {
    content: "Seite " counter(page) " von " counter(pages);
    font-size: 8pt;
    color: #777;
  }
}
body {
  font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: #222;
}
h1 { font-size: 19pt; margin: 0 0 6pt; color: #004466; }
h2 { font-size: 13.5pt; margin: 16pt 0 6pt; padding-bottom: 2pt;
     border-bottom: 1px solid #ddd; color: #004466; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; page-break-after: avoid; }
p  { margin: 0 0 6pt; }
ul, ol { margin: 0 0 8pt 0; padding-left: 16pt; }
li { margin-bottom: 2pt; }
code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 9pt;
  background: #f5f5f5;
  padding: 1pt 3pt;
  border-radius: 2pt;
}
pre {
  background: #f5f5f5;
  border: 1px solid #e3e3e3;
  border-left: 3px solid #08c;
  border-radius: 3pt;
  padding: 6pt 8pt;
  margin: 6pt 0 10pt;
  white-space: pre-wrap;
  word-wrap: break-word;
  page-break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: 8.5pt; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 6pt 0 10pt;
  font-size: 9.5pt;
  page-break-inside: avoid;
}
th, td { border: 1px solid #ddd; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f0f3f6; }
blockquote {
  margin: 6pt 0;
  padding: 5pt 10pt;
  background: #f7fafc;
  border-left: 3px solid #08c;
}
hr { border: 0; border-top: 1px solid #ddd; margin: 12pt 0; }
a { color: #08c; text-decoration: none; }
strong { color: #000; }
"""

html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Speiseplan hochladen – Anleitung für Lehrkräfte</title>
<style>{CSS}</style></head><body>{html_body}</body></html>"""

HTML(string=html, base_url=str(src.parent)).write_pdf(str(dst))
print(f"  geschrieben: {dst} ({dst.stat().st_size // 1024} kB)")
