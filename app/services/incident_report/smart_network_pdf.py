"""Convert the filled latest Smart Network DOCX template with Word.

The DOCX renderer preserves the supplied design and six tables; this
module uses the shared Word export path for the matching PDF layout.
"""

from app.services.incident_report.smart_network_docx import build_docx
from app.services.word_export import convert_docx_to_pdf


def build_pdf(report):
    """report: same dict shape smart_network_docx.build_docx() takes.
    Returns PDF bytes."""
    return convert_docx_to_pdf(build_docx(report), doc_label="Smart Network Report")
