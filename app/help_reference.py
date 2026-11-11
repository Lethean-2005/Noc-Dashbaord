"""Shared worked examples and reference material for Help and the PDF."""

EXAMPLE_TABLES = {
    "card-sla": [{"title": "Worked example: two overlapping lists",
        "description": "The Response and Resolution columns count separate lists. Only the incidents that fail both appear in both lists.",
        "rows": [["Incident group", "Count", "Response Not Met list", "Resolution Not Met list"],
                 ["Response failed only", "13", "Included", "Not included"],
                 ["Both failed", "2", "Included", "Included"],
                 ["Resolution failed only", "17", "Not included", "Included"],
                 ["Total in each list", "", "15", "19"]]}],
    "card-all-wo-resolved": [{"title": "Worked example: check the flag and every WO",
        "description": "Each qualifying row contributes one incident to the badge, regardless of its number of WOs.",
        "rows": [["Example", "Total WOs", "Resolved WOs", "Qualifies?"],
                 ["Flag true; all WOs Resolved", "5", "5", "Yes, if parent conditions pass"],
                 ["Flag true; one WO In Progress", "5", "4", "No"],
                 ["Flag false; all WOs Resolved", "5", "5", "No"],
                 ["No linked WOs", "0", "0", "No"]]}],
    "map-view": [{"title": "Current map color reference",
        "description": "Identify whether the marker is a site or POP before interpreting its color.",
        "rows": [["Marker", "Color", "Meaning"], ["Site", "Red", "Active Site Down takes precedence"],
                 ["Site", "Green", "On Air"], ["Site", "Blue", "Planned"],
                 ["Site", "Grey", "Other or unrecognized inventory status"],
                 ["POP", "Amber", "Recognized Telcotech owner"], ["POP", "Purple", "Recognized Ezecom owner"],
                 ["POP", "Grey", "Blank, unknown, or unrecognized owner; not proof of an outage"]]}],
}

QUICK_START = [
    ("What is being counted?", "A site, incident, work order, device alarm, and interface are different objects."),
    ("Which records qualify?", "Check the status, category, inventory matching, and exclusions for that view."),
    ("Which date is used?", "Occurred At, Created At, Resolved At, and Closed At can place one incident in different weeks."),
    ("Which filters are selected?", "Match category, week, site, and root cause before comparing results."),
    ("Is the data current?", "The relevant background jobs must finish successfully; browser refresh alone does not query every source."),
]

VERIFICATION_CHECKLIST = [
    ("The expected record", "Keep one exact site, incident, WO, or device/interface identifier."),
    ("Matching filters", "Use the same status, category, week, site, and cause selections."),
    ("Matching dates", "Check the actual date field and Cambodia timezone."),
    ("Matching unit", "Compare incidents with incidents, sites with sites, and alarm rows with alarm rows."),
    ("Source freshness", "Confirm the relevant background jobs completed, including inventory dependencies."),
    ("Preserved settings", "Check Mentor selection and interface exclusions before concluding data is missing."),
    ("Useful issue report", "Record what you expected, what you saw, exact filters, and an example identifier. Do not share credentials or signed webhook URLs."),
]

GLOSSARY = [('Alarm',
  'An event reported by a monitoring source. It is not the same object as an incident ticket.'),
 ('Incident', 'A parent ticket describing an operational issue; it can affect more than one site.'),
 ('INC-WO', 'A work order linked to an incident. One incident can have several WOs.'),
 ('Cache', 'The saved local copy used by the dashboard after a background source update.'),
 ('Drilldown', 'The detailed records behind a selected badge, chart value, or table count.'),
 ('Inventory',
  'The reference data for sites, POPs, technologies, ownership, grades, and location.'),
 ('Response SLA', 'The recorded result for meeting the applicable response deadline.'),
 ('Resolution SLA', 'The recorded result for meeting the applicable resolution deadline.'),
 ('Not Graded', 'No recorded resolution SLA result; it must not be assumed to mean Met.'),
 ('Cohort', 'The set of records matching a specific date field, reporting window, and filters.'),
 ('SRAN',
  'The supported shared-baseband/connectivity event classification, not a new name for every '
  'full-site outage.'),
 ('Exclusion',
  'A saved interface-specific congestion visibility rule; it does not delete the source alarm.')]

REFERENCE_GUIDES = {
    "guide-quick-start": {"title": "Quick start: read the dashboard correctly",
        "intro": "Check these five points before comparing numbers. Then open one known record and follow it through the matching view.",
        "entries": QUICK_START,
        "example": "Two sites produce five alarms. One parent incident has three WOs. Counts of 2 sites, 5 alarm rows, 1 incident, and 3 WOs can all be correct.",
    },
    "guide-glossary": {"title": "Glossary: dashboard terms in plain language",
        "intro": "Use these definitions while reading cards, filters, action dialogs, and exported records.",
        "entries": GLOSSARY,
    },
    "guide-verification": {"title": "Verification checklist: compare records correctly",
        "intro": "Follow this checklist when a count or record differs between the dashboard and another system.",
        "entries": VERIFICATION_CHECKLIST,
        "example": "A record absent from a filtered table may be outside the selected date range, excluded by a saved rule, unmatched to inventory, or waiting for a successful update. Compare the exact identifier before assuming it was deleted.",
    },
}
