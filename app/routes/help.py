from pathlib import Path

from flask import Blueprint, abort, render_template, send_from_directory

help_bp = Blueprint("help", __name__)

_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

# Only these exact filenames are downloadable — never pass the URL segment
# straight to send_from_directory, which would let a path-traversal-style
# filename reach anything else in docs/.
DOWNLOADABLE_DOCS = {
    "Noc-Dashboard-Feature-Report.pdf": "Feature Report",
    "Noc-Dashboard-User-Demo-Guide.pdf": "User Demo Guide",
    "Noc-Dashboard-Query-Data-Reference.pdf": "Query & Data Reference",
    "Noc-Dashboard-Virtual-Machine-Setup.pdf": "Virtual Machine Setup Guide",
}


@help_bp.route("/help")
def index():
    return render_template("help/index.html", downloads=DOWNLOADABLE_DOCS)


@help_bp.route("/help/downloads/<filename>")
def download(filename):
    if filename not in DOWNLOADABLE_DOCS:
        abort(404)
    return send_from_directory(_DOCS_DIR, filename, as_attachment=True)
