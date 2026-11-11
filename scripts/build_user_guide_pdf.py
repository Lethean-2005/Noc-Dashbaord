"""Build the additional plain-language dashboard guide without live source queries."""
from pathlib import Path
import sys
from html import escape
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents
from app.help_guides import CARD_GUIDES
from app.help_article_details import ARTICLE_DETAILS
from app.help_features import FEATURE_GUIDES
from app.help_reference import GLOSSARY, EXAMPLE_TABLES

OUTPUT = ROOT / "docs/Noc-Dashboard-Detailed-User-Guide.pdf"
INK = colors.HexColor("#20242b")
MUTED = colors.HexColor("#626974")
LINE = colors.HexColor("#dfe3e8")
BLUE = colors.HexColor("#3267d6")
FONT_DIR = ROOT / "app/static/fonts"
pdfmetrics.registerFont(TTFont("HuaweiSans", str(FONT_DIR / "HuaweiSans.ttf")))
pdfmetrics.registerFont(TTFont("HuaweiSans-Bold", str(FONT_DIR / "HuaweiSans-Bold.ttf")))
pdfmetrics.registerFontFamily("HuaweiSans", normal="HuaweiSans", bold="HuaweiSans-Bold",
                              italic="HuaweiSans", boldItalic="HuaweiSans-Bold")
STYLES = {
    "body": ParagraphStyle("GuideBody", fontName="HuaweiSans", fontSize=10.5, leading=16.5,
                           textColor=INK, spaceAfter=10, allowWidows=0, allowOrphans=0),
    "chapter": ParagraphStyle("GuideChapter", fontName="HuaweiSans-Bold", fontSize=21,
                              leading=27, textColor=INK, spaceAfter=16, keepWithNext=True),
    "section": ParagraphStyle("GuideSection", fontName="HuaweiSans-Bold", fontSize=11,
                              leading=16, textColor=INK, spaceBefore=15, spaceAfter=7,
                              keepWithNext=True),
    "small": ParagraphStyle("GuideSmall", fontName="HuaweiSans", fontSize=9, leading=13,
                            textColor=MUTED, spaceAfter=8),
    "cover": ParagraphStyle("GuideCover", fontName="HuaweiSans-Bold", fontSize=30,
                            leading=38, textColor=INK, spaceAfter=22),
    "toc": ParagraphStyle("GuideContents", fontName="HuaweiSans", fontSize=10,
                          leading=16, textColor=INK, spaceBefore=5, leftIndent=0,
                          firstLineIndent=0),
    "cell": ParagraphStyle("GuideCell", fontName="HuaweiSans", fontSize=9,
                           leading=13, textColor=INK),
}


class GuideDocument(BaseDocTemplate):
    def __init__(self, output=OUTPUT, guide_title="Detailed user guide"):
        self.guide_title = guide_title
        super().__init__(str(output), pagesize=A4, leftMargin=23*mm, rightMargin=23*mm,
                         topMargin=25*mm, bottomMargin=23*mm,
                         title="Noc-Dashboard - " + guide_title,
                         author="NOC Dashboard", subject="Cards, calculations, examples and troubleshooting")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="reading", frames=[frame], onPage=self.draw_page))
        self.heading_number = 0

    def beforeDocument(self):
        self.heading_number = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "GuideChapter":
            text = flowable.getPlainText()
            key = "chapter-" + str(self.heading_number)
            self.heading_number += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0, closed=False)
            self.notify("TOCEntry", (0, text, self.page, key))

    def draw_page(self, canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(.5)
        canvas.line(doc.leftMargin, height-17*mm, width-doc.rightMargin, height-17*mm)
        canvas.setFont("HuaweiSans", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, height-13*mm, "Noc-Dashboard | Help center")
        canvas.drawRightString(width-doc.rightMargin, height-13*mm, self.guide_title)
        canvas.line(doc.leftMargin, 16*mm, width-doc.rightMargin, 16*mm)
        canvas.drawString(doc.leftMargin, 11*mm, "Examples explain the rules; they are not live records.")
        canvas.drawRightString(width-doc.rightMargin, 11*mm, str(doc.page))
        canvas.restoreState()


def para(text, style="body"):
    return Paragraph(escape(str(text)), STYLES[style])


def table(rows, widths=None):
    data = [[para(value, "cell") for value in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#f5f6f8")),
        ("GRID", (0,0), (-1,-1), .5, LINE),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 9), ("RIGHTPADDING", (0,0), (-1,-1), 9),
        ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ]))
    return result


def section(story, heading, paragraphs):
    story.append(para(heading, "section"))
    story.extend(para(text) for text in paragraphs)


def chapter(story, title):
    story.extend([PageBreak(), para(title, "chapter")])


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = GuideDocument()
    story = [Spacer(1, 27*mm), para("NOC DASHBOARD", "small"),
             para("Understand every card.\nMake sense of every number.", "cover"),
             para("Detailed User Guide", "chapter"),
             para("A practical guide to alarms, incidents, work orders, trends, SLA results, maps, reports, and saved monitoring tools."),
             Spacer(1, 8*mm)]
    section(story, "What this guide helps you do", [
        "Read the dashboard one card at a time, understand what each count represents, and open the right detail records.",
        "Follow clear calculations and worked examples without needing application code or database file paths.",
        "Check differences between source systems, saved data, and browser views before reporting an issue.",
    ])
    story.append(para("Prepared " + date.today().strftime("%d %B %Y") + ". Existing PDF manuals remain unchanged.", "small"))
    story.extend([PageBreak(), para("Contents", "cover"),
                  para("Click a chapter title or use the PDF bookmarks to jump to a topic.", "small")])
    contents = TableOfContents()
    contents.levelStyles = [STYLES["toc"]]
    story.append(contents)

    chapter(story, "Start here: read the dashboard correctly")
    section(story, "Five things to check before comparing numbers", [
        "1. What is being counted? A site, incident, work order, device alarm, and interface are different objects.",
        "2. Which records qualify? Read the status, category, inventory, and exclusion rules for that view.",
        "3. Which date is used? Occurred At, Created At, Resolved At, and Closed At can place the same ticket in different weeks.",
        "4. Which filters are selected? Apply the same category, week, site, and root-cause filters before comparing.",
        "5. Is the data current? Reloading the browser reads the saved view; source collection must complete successfully first.",
    ])
    story.append(table([
        ["Question", "Start with"],
        ["What needs attention now?", "Live alarm cards and active incident/WO views"],
        ["Why does the badge differ from the table?", "The card's counting unit and distinct-site rules"],
        ["Did the team meet its deadlines?", "SLA Compliance and the individual incident result"],
        ["How long did work take?", "Response/Resolution time and outage duration charts"],
        ["Why is a record missing?", "Filters, inventory matching, exclusions, and update timing"],
    ], [61*mm, 103*mm]))
    section(story, "A worked example", [
        "Two sites produce five alarm rows. One parent incident has three WOs. A site badge can show 2, an alarm table can show 5 rows, the incident view can show 1, and the WO view can show 3. These numbers can all be correct because they answer different questions.",
        "For the most reliable check, choose one known identifier and follow it through the relevant card, its detail records, and the source system using the same filters.",
    ])

    for index, (slug, guide) in enumerate(CARD_GUIDES.items(), 1):
        chapter(story, f"Card {index:02d} | {guide['title']}")
        story.append(para(guide["group"], "small"))
        story.append(para(guide["intro"]))
        for heading, paragraphs in guide["sections"]:
            section(story, heading, paragraphs)
        for example in EXAMPLE_TABLES.get(slug, []):
            section(story, example["title"], [example["description"]])
            story.append(table(example["rows"], [doc.width/len(example["rows"][0])]*len(example["rows"][0])))
        section(story, "Refresh and comparison", [
            "This view uses the relevant saved datasets. Allow the corresponding source and inventory jobs to finish. A browser refresh does not force every source query.",
            "Examples in this chapter illustrate the logic and are not the current live incident, site, or alarm totals.",
        ])

    general_titles = {
        "overview": "Using the Help center and dashboard",
        "getting-started": "Getting started: a practical investigation",
        "data-sources": "Source data and comparing records",
        "topbar-toolbar": "Refresh, theme, layout, and fullscreen",
        "dashboard": "Choose the right view for your question",
        "map-view": "Map view, colors, coordinates, and boundaries",
        "partner-contact": "Partner contacts and escalation information",
        "reports": "Reports and exports",
        "incident-report": "Prepare and export an incident report",
        "notifications": "Alerts, restoration replies, and delivery checks",
        "tech-stack": "Saved data and safe application updates",
        "mentor-site": "Mentor Site: adding, importing, and retaining sites",
        "troubleshooting": "Troubleshooting step by step",
    }
    for slug, title in general_titles.items():
        chapter(story, title)
        if slug == "notifications":
            story.append(para("This chapter explains the current delivery logic. Use configured schedules rather than treating older reference intervals as the current schedule."))
        for heading, paragraphs in ARTICLE_DETAILS[slug]:
            if heading == "How to interpret the reference schedule":
                continue
            section(story, heading, paragraphs)
        if slug == "map-view":
            section(story, "Current map color reference", ["Interpret the marker type before interpreting its color. Grey has different meanings for sites and POPs."])
            story.append(table([
                ["Marker", "Color", "Meaning"],
                ["Site", "Red", "Matches active Site Down; overrides normal status color"],
                ["Site", "Green", "On Air"],
                ["Site", "Blue", "Planned"],
                ["Site", "Grey", "Other or unrecognized inventory status"],
                ["POP", "Amber", "Recognized Telcotech owner"],
                ["POP", "Purple", "Recognized Ezecom owner"],
                ["POP", "Grey", "Blank, unknown, or unrecognized owner; not an outage conclusion"],
            ], [25*mm, 25*mm, 114*mm]))

    chapter(story, "Glossary: terms used throughout the guide")
    glossary = GLOSSARY
    for title, text in glossary:
        section(story, title, [text])

    chapter(story, "Final verification checklist")
    for title, text in [
        ("The expected record", "Keep one exact site, incident, WO, or device/interface identifier."),
        ("Matching filters", "Use the same status, category, week, site, and cause selections."),
        ("Matching dates", "Check the actual date field and Cambodia timezone."),
        ("Matching unit", "Compare incidents with incidents, sites with sites, and alarm rows with alarm rows."),
        ("Source freshness", "Confirm the relevant background jobs completed, including inventory dependencies."),
        ("Preserved settings", "Check Mentor selection and interface exclusions before concluding data is missing."),
        ("Useful issue report", "Record what you expected, what you saw, exact filters, and one example identifier. Do not include credentials or signed webhook URLs."),
    ]:
        section(story, title, [text])
    doc.multiBuild(story)
    print(f"Created {OUTPUT}")
    print(f"20 card chapters; {len(general_titles)} practical topics; glossary and checklist.")


def build_feature_guide():
    output = ROOT / "docs/Noc-Dashboard-Feature-User-Guide.pdf"
    doc = GuideDocument(output, "Feature guide")
    story = [Spacer(1, 25*mm), para("NOC DASHBOARD", "small"),
             para("Feature Guide", "cover"),
             para("Step-by-step instructions for alarm actions, interface exclusions, monitoring, filtering, exports, and report preparation."),
             Spacer(1, 8*mm)]
    section(story, "Choose the right action", [
        "Acknowledge records handling and a note. Exclude Congestion saves an interface-specific visibility rule. Restore removes that rule. Clear Alarm manually changes the supported source alarm to cleared.",
        "Read the selected device, IP, interface, and occurrence time before taking an action. The detailed card and calculation explanations are in the separate Detailed User Guide.",
    ])
    story.extend([PageBreak(), para("Contents", "cover")])
    contents = TableOfContents()
    contents.levelStyles = [STYLES["toc"]]
    story.append(contents)
    for feature in FEATURE_GUIDES.values():
        chapter(story, "How to use | " + feature["title"])
        story.append(para(feature["intro"]))
        section(story, "When to use this feature", feature["before"])
        section(story, "Step-by-step instructions", [f"{i}. {step}" for i, step in enumerate(feature["steps"], 1)])
        if feature["fields"]:
            section(story, "What the fields mean", [])
            story.append(table([["Field or control", "What it means"], *feature["fields"]], [52*mm,112*mm]))
        section(story, "What changes after saving", feature["results"])
        section(story, "Scope and important distinctions", feature["limits"])
        section(story, "Worked example", [feature["example"]])
        if feature["screenshots"]:
            section(story, "Screenshot demonstration", ["Real interface captures with isolated sample data. No operational action was submitted."])
            for file, caption in feature["screenshots"]:
                image = Image(str(ROOT/"app/static/images"/file))
                factor = min(doc.width/image.imageWidth, 145*mm/image.imageHeight, .8)
                image.drawWidth = image.imageWidth*factor
                image.drawHeight = image.imageHeight*factor
                image.hAlign = "LEFT"
                story.append(KeepTogether([image, Spacer(1,3*mm), para(caption, "small"), Spacer(1,4*mm)]))

    chapter(story, "Quick action reference")
    story.append(table([
        ["Action", "What it changes"],
        ["Acknowledge / Modify Note", "Source acknowledgment or note on the supported alarm"],
        ["Exclude Congestion", "Saved local visibility for one device/interface"],
        ["Restore", "Removes one saved congestion visibility rule"],
        ["Clear Alarm", "Source alarm status and restoration timestamp"],
        ["Filter / Search", "The records being inspected; not source status"],
        ["Export", "Produces a file snapshot; not a source update"],
    ], [55*mm,109*mm]))
    doc.multiBuild(story)
    print(f"Created {output}")


if __name__ == "__main__":
    build()
    build_feature_guide()
