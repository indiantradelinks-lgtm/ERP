"""One-off: render NOVENTIQ_APPLICATION_ASSESSMENT.md to a shareable PDF (read-only)."""
from markdown_it import MarkdownIt
from weasyprint import HTML

md = open("/app/NOVENTIQ_APPLICATION_ASSESSMENT.md").read()
body = MarkdownIt("commonmark", {"html": True}).enable("table").render(md)

CSS = """
@page { size: A4; margin: 16mm 14mm 14mm 14mm;
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 7pt; color: #64748B; } }
body { font-family: "DejaVu Sans", Helvetica, sans-serif; font-size: 8.2pt; color: #0F172A; line-height: 1.45; }
h1 { font-size: 15pt; color: #1E3A5F; margin: 0 0 2pt; }
h2 { font-size: 10.5pt; color: #1E3A5F; border-bottom: 1px solid #CBD5E1; padding-bottom: 2pt;
     margin: 14pt 0 5pt; page-break-after: avoid; }
h3 { font-size: 9pt; color: #334155; margin: 9pt 0 3pt; page-break-after: avoid; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0 8pt; font-size: 7.4pt; }
th { background: #1E3A5F; color: #fff; text-align: left; }
th, td { border: 0.4pt solid #CBD5E1; padding: 3pt 4pt; vertical-align: top; }
tr:nth-child(even) td { background: #F1F5F9; }
code, pre { font-family: "DejaVu Sans Mono", monospace; font-size: 7pt; background: #F1F5F9; }
pre { padding: 5pt; border: 0.4pt solid #CBD5E1; white-space: pre-wrap; }
hr { border: none; border-top: 1px solid #CBD5E1; margin: 10pt 0; }
li { margin-bottom: 2pt; }
em { color: #475569; }
"""

HTML(string=f"<style>{CSS}</style>{body}").write_pdf("/app/Noventiq-Application-Assessment.pdf")
print("written")
