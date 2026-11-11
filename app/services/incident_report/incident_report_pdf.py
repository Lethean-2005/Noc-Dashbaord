"""Renders an Incident Report dict into a PDF by filling in the actual
Telcotech .docx template (see incident_report_docx.py) and converting
THAT to PDF via Microsoft Word itself (COM automation — see
app/services/word_export.py, shared with every other report type that
needs this same high-fidelity export) — not a from-scratch reportlab
reconstruction. This is what makes the PDF a true match rather than an
approximation: it's Word's own rendering engine producing the PDF, the
same way the reference IR_SMART-IX1222 PDF itself was almost certainly
produced.
"""

from app.services.incident_report.incident_report_docx import build_docx
from app.services.word_export import convert_docx_to_pdf


def build_pdf(report):
    """report: same dict shape incident_report_docx.build_docx() takes.
    Returns PDF bytes."""
    return convert_docx_to_pdf(build_docx(report), doc_label="Incident Report")
