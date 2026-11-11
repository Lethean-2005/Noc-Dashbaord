from pathlib import Path

from flask import Blueprint, abort, render_template, send_from_directory

from app.help_guides import CARD_GUIDES
from app.help_article_details import ARTICLE_DETAILS
from app.help_features import FEATURE_GUIDES
from app.help_reference import REFERENCE_GUIDES, EXAMPLE_TABLES

help_bp = Blueprint("help", __name__)

_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

# Only these exact filenames are downloadable — never pass the URL segment
# straight to send_from_directory, which would let a path-traversal-style
# filename reach anything else in docs/.
DOWNLOADABLE_DOCS = {
    "Noc-Dashboard-Detailed-User-Guide.pdf": "Detailed User Guide - Cards & Calculations",
    "Noc-Dashboard-Feature-User-Guide.pdf": "Feature Guide - Step by Step",
    "Noc-Dashboard-Feature-Report.pdf": "Feature Report",
    "Noc-Dashboard-User-Demo-Guide.pdf": "User Demo Guide",
    "Noc-Dashboard-Query-Data-Reference.pdf": "Query & Data Reference",
    "Noc-Dashboard-Virtual-Machine-Setup.pdf": "Virtual Machine Setup Guide",
}


HELP_ARTICLES = {'overview': 'Getting Started with Noc-Dashboard',
 'getting-started': 'Getting Started',
 'data-sources': 'Where the Data Comes From',
 'topbar-toolbar': 'The Topbar Toolbar',
 'dashboard': 'Dashboard',
 'map-view': 'Map View',
 'partner-contact': 'Partner Contact',
 'reports': 'Reports & Exporting',
 'incident-report': 'Incident Report',
 'notifications': 'Notifications & Alerting',
 'tech-stack': 'Technology Stack',
 'mentor-site': 'Mentor Site',
 'troubleshooting': 'Troubleshooting'}


HELP_TOPICS = [
        ("Getting started", "ti-compass", "Learn the dashboard and its controls.",
         ("overview", "getting-started", "dashboard", "topbar-toolbar", "tech-stack")),
        ("Live alarms & sites", "ti-activity", "Understand site, power, and device alarms.",
         ("card-vip-vvip", "card-mentor", "card-ip-ezecom", "card-ip-telcotech",
          "card-ran-site-down", "card-ran-tech-down", "card-ran-power")),
        ("Incidents & work orders", "ti-clipboard-list", "Read ticket status, age, and completion.",
         ("card-incident-status", "card-all-wo-resolved", "card-site-down-age")),
        ("Trends & SLA", "ti-chart-line", "Understand charts, calculations, and results.",
         ("card-volume", "card-closed", "card-duration", "card-top-sites", "card-root-causes",
          "card-sla", "card-response-time", "card-resolution-time")),
        ("Tools & reports", "ti-tool", "Use maps, monitoring tools, and exports.",
         ("map-view", "mentor-site", "partner-contact", "reports", "incident-report", "card-congestion")),
        ("Data & support", "ti-help", "Check refresh timing and resolve differences.",
         ("data-sources", "card-refresh", "notifications", "troubleshooting")),
    ]

HELP_TOPICS.extend([
    ("Alarm actions", "ti-clipboard-list", "Record handling, exclude interfaces, and restore visibility.",
     ("feature-acknowledge", "feature-exclude", "feature-blacklist-restore", "feature-clear-alarm")),
    ("How to use features", "ti-tool", "Step-by-step instructions with screenshot demonstrations.",
     ("feature-filters-search", "feature-mentor-import", "feature-export", "feature-report-workflow")),
    ("Quick reference", "ti-help", "Practical starting points, definitions, and checks.",
     ("guide-quick-start", "guide-glossary", "guide-verification")),
])
HELP_TOPIC_IDS = ("getting-started", "live-alarms", "incidents", "trends", "tools", "data",
                  "alarm-actions", "features", "reference")


def _article_titles():
    return {**HELP_ARTICLES, **{slug: guide["title"] for slug, guide in CARD_GUIDES.items()},
            **{slug: guide["title"] for slug, guide in FEATURE_GUIDES.items()},
            **{slug: guide["title"] for slug, guide in REFERENCE_GUIDES.items()}}


@help_bp.context_processor
def documentation_navigation():
    sections = {
        "Overview": ("overview", "getting-started", "dashboard"),
        "Workspace": ("topbar-toolbar", "map-view", "mentor-site", "partner-contact"),
        "Reports & alerts": ("reports", "incident-report", "notifications"),
        "Data & support": ("data-sources", "tech-stack", "troubleshooting"),
    }
    groups = {label: [(slug, HELP_ARTICLES[slug]) for slug in slugs]
              for label, slugs in sections.items()}
    for slug, guide in CARD_GUIDES.items():
        groups.setdefault(guide["group"], []).append((slug, guide["title"]))
    groups["How to use features"] = [(slug, guide["title"]) for slug, guide in FEATURE_GUIDES.items()]
    groups["Quick reference"] = [(slug, guide["title"]) for slug, guide in REFERENCE_GUIDES.items()]
    return {"help_navigation": groups}


@help_bp.route("/help")
def index():
    articles = _article_titles()
    topics = HELP_TOPICS
    return render_template("help/index.html", downloads=DOWNLOADABLE_DOCS,
                           articles=articles, topics=topics, topic_ids=HELP_TOPIC_IDS, card_guides=CARD_GUIDES)


@help_bp.route("/help/downloads/<filename>")
def download(filename):
    if filename not in DOWNLOADABLE_DOCS:
        abort(404)
    return send_from_directory(_DOCS_DIR, filename, as_attachment=True)


@help_bp.route("/help/articles/<slug>")
def article(slug):
    feature = FEATURE_GUIDES.get(slug)
    if feature is not None:
        return render_template("help/feature.html", article_title=feature["title"], feature=feature)
    reference = REFERENCE_GUIDES.get(slug)
    if reference is not None:
        return render_template("help/reference.html", article_title=reference["title"], reference=reference)
    guide = CARD_GUIDES.get(slug)
    if guide is not None:
        return render_template("help/card-guide.html", article_title=guide["title"], guide=guide,
                               example_tables=EXAMPLE_TABLES.get(slug, []))
    title = HELP_ARTICLES.get(slug)
    if title is None:
        abort(404)
    return render_template("help/article.html", article_title=title,
                           article_template=f"help/articles/{slug}.html",
                           article_details=ARTICLE_DETAILS.get(slug, []),
                           example_tables=EXAMPLE_TABLES.get(slug, []))


@help_bp.route("/help/topics/<topic_id>")
def topic(topic_id):
    if topic_id not in HELP_TOPIC_IDS:
        abort(404)
    title, _icon, description, slugs = HELP_TOPICS[HELP_TOPIC_IDS.index(topic_id)]
    articles = _article_titles()
    return render_template("help/topic.html", article_title=title, description=description,
                           slugs=slugs, articles=articles, card_guides=CARD_GUIDES)
