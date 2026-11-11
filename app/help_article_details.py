"""Additional plain-language explanations; original Help articles stay intact."""

ARTICLE_DETAILS = {
    "overview": [
        ("How to use the dashboard", ["Start with the current fault cards when deciding what needs attention now. Use historical charts when comparing performance over time. A live alarm list, an active ticket list, and a completed-incident report answer different questions even when they mention the same site.", "Click a number to inspect its records before drawing a conclusion. Check the site or incident identifier, status, timestamp, and selected filters. An incident can affect several sites, and one site can have several alarm events, so the same number does not always represent the same unit."]),
        ("A simple investigation example", ["If a VIP site shows a power alarm, open that badge first. Confirm the site code and event, then inspect any linked incident. Next check the relevant Site Down or SLA guide if you need to understand the outage classification or deadline result. This is more reliable than adding together counts from unrelated cards."]),
        ("Where to find more detail", ["The card guides explain source data, included records, counting rules, examples, and refresh behavior one card at a time. General guides cover navigation, maps, reports, and troubleshooting. The original PDF documentation remains available from the Help center."])
    ],
    "getting-started": [
        ("Start with one question", ["Decide whether you want to see a current fault, find an incident, or review historical performance. Current alarm cards describe alarms that meet their source rules. Incident cards describe tickets and work orders. Trend cards describe records inside a reporting period.", "For a specific problem, begin with its site code or incident ID. Use the relevant page and then open a matching badge or chart count. This keeps your investigation focused on a known record rather than an unexplained total."]),
        ("Read a card step by step", ["Read the title, selected dates, and category filters before the number. Open the drilldown and check whether each row is an incident, work order, site, device alarm, or interface. The count can represent unique sites while the detail table shows several alarms per site."]),
        ("Example", ["A badge shows two affected sites. Its table contains five alarms: three at the first site and two at the second. The badge is not wrong simply because the table has five rows. It is counting different objects. The card guide explains which counting method applies."]),
        ("Before reporting a mismatch", ["Record the page name, exact badge, selected filters, and one example identifier. Check the next successful data update and compare the same scope in Streamline or the alarm source. Screenshots of two different date filters cannot establish that one count is incorrect."])
    ],
    "data-sources": [
        ("The path from source to screen", ["Background jobs collect records from the source systems and save a local copy. The dashboard reads that copy to build cards, charts, and tables. A source-system change appears after the relevant job succeeds; it is not necessarily visible immediately after a browser refresh.", "Site inventory gives alarms their site name, code, grade, owner, location, and technology context. An alarm can exist in its source but fail a card's inventory matching or status rule. Missing inventory and missing source alarms are different problems."]),
        ("Why related cards can change at different times", ["Alarm, incident, VIP, and inventory data are updated by different jobs. A new source alarm may arrive before a site's inventory designation is refreshed. Wait for the relevant dependencies, not just one timer, before assuming every card should change together."]),
        ("Example: one incident across a week boundary", ["An incident occurs Sunday night and closes Monday morning. An occurrence-based report can count it in the earlier week, while a completion report places it in the following week. Both results can be correct. The same Cambodia timezone must be used when checking the boundary."]),
        ("What to compare", ["Match status, category, date field, counting unit, and filters. Compare incident or site IDs as well as totals. The card-by-card guides describe these rules in ordinary language so users do not need to read application code."])
    ],
    "topbar-toolbar": [
        ("Refresh and data freshness", ["Refresh reloads the displayed page. It does not force every background source query to run immediately. If the saved data is unchanged, the refreshed page may show the same records. Wait for a successful source update when investigating a newly changed ticket."]),
        ("Theme and readability", ["Light and Dark change presentation, not the selected incidents or alarm rules. Use the theme that makes labels easiest to read on your screen. Changing the theme does not resolve an alarm, change SLA results, or update the source data."]),
        ("Card layout", ["A custom layout changes where cards are placed so your most useful information is easier to reach. It does not change what their badges count. When helping another user, refer to the card title rather than only saying the top-left card, because their layout may differ."]),
        ("Fullscreen", ["Fullscreen gives the dashboard more space on a monitoring display. It does not change the reporting window or the source data. Exit fullscreen using the control or the browser's fullscreen shortcut when you need access to other windows."]),
        ("Example", ["Moving the SLA card above the incident card changes only the arrangement. A Response Not Met count still uses its original SLA filter. If the count changes, investigate a filter or data update rather than assuming the new layout changed the logic."])
    ],
    "dashboard": [
        ("Use each card for its own purpose", ["VIP/VVIP focuses on strategically designated sites. Mentor Site focuses on your saved monitoring list. The IP cards describe POP and device alarms. RAN Status compares the available technology alarms with inventory. Incident / INC-WO by Status describes ticket workflows rather than raw alarms."]),
        ("A badge is not always an alarm-row total", ["Distinct-site badges count a site once per category even when it has multiple events. Incident badges count ticket IDs. WO badges count work orders. Some IP counts combine mapped POP sites and unmapped alarm records. Read the individual guide before combining values."]),
        ("Current state versus historical performance", ["An open-age chart measures tickets still active. A duration trend uses qualifying completed outages. SLA summaries use their own response and resolution cohorts. A site can appear in several contexts without those charts being duplicates."]),
        ("Example: a site with several problems", ["A monitored VIP site has a Main AC Failure event, Low DC Voltage, and one active Site Down incident. It can appear in both VIP and Mentor views, both power categories, and the incident view. These are different perspectives on the same site, not several additional sites."]),
        ("Find the detailed card guide", ["Return to Help center and choose the card's exact title under Understand each dashboard card. Each guide explains its source, rules, examples, drilldown, and update timing. Use those details to reproduce the same comparison in the source system."])
    ],
    "map-view": [
        ("Read the selected layer first", ["A map filter determines which sites or POPs you are looking at. On Air, Planned, Other, and Site Down represent different populations. A marker missing from a selected layer does not prove the site is absent from every inventory source."]),
        ("Investigate one location", ["Search a known code, select the matching result, and open its marker. Check its name, status, and ticket reference where available. Similar place names are not reliable identifiers; use the code to distinguish sites in the same area."]),
        ("Boundary selection and export", ["Choose the intended province, district, or commune before exporting a scoped list. Verify the boundary and active filter first. A boundary export should be interpreted as the selected map population, not a complete list of every incident affecting that province."]),
        ("Example", ["A site has On Air inventory and an active Site Down incident. Its outage indicator can take precedence over the ordinary inventory status color. This does not mean its inventory record was deleted or changed to Planned."]),
        ("If a marker looks wrong", ["Check coordinates, selected layer, source inventory, active ticket match, and last update. A delayed incident cache and a missing coordinate are different causes of a map discrepancy and need different checks."])
    ],
    "partner-contact": [
        ("Find the correct partner", ["Search the partner or contact information you know, then confirm the displayed organization and escalation details. Similar names can belong to different teams. Use the full record when deciding whom to contact."]),
        ("Contact data is not incident status", ["Partner Contact provides reference information for communication. It does not prove that a particular team accepted a ticket or that an outage is resolved. Use the linked operational workflow for incident status and work-order ownership."]),
        ("Example", ["An incident needs partner assistance. First verify the incident's responsible team and location, then use Partner Contact to locate the matching contact or escalation record. Do not assume the first search result is responsible for every site owned by the same organization."]),
        ("Missing or outdated details", ["The page depends on the saved source contact data and its updates. If a number or email is missing, record the exact partner and field so the source record can be checked. Repeated browser refreshes cannot supply contact information that was never entered."])
    ],
}

ARTICLE_DETAILS.update({
    "reports": [
        ("Choose the report population", ["Before exporting, decide whether you need current alarms, active tickets, completed outages, or a selected map area. These lists have different inclusion rules. A historical record can remain in a report after disappearing from a current-fault card."]),
        ("Filters matter", ["Apply the intended category, week, status, and site selections before exporting. Compare the export with the same filtered table. A spreadsheet containing raw alarm records can have more rows than a badge counting distinct sites."]),
        ("Example", ["Three events belong to one site and two events belong to another. The site badge shows 2, while an alarm-record export can contain 5 rows. This difference is expected when the export explains the underlying events."]),
        ("Read dates carefully", ["Check whether the report uses Occurred At, Created At, Resolved At, or Closed At. Use Cambodia time consistently. The selected date field can move an incident across a week boundary even though its identifier stays unchanged."]),
        ("Before sharing", ["Review the report title, selected period, total records, and a sample of identifiers. Confirm whether an empty result comes from filters or an incomplete source update. Exporting does not resolve, acknowledge, or close the source records."])
    ],
    "incident-report": [
        ("Prepare the report", ["Select the intended saved report or begin a new one. Enter the incident reference, affected service or circuits, impact, and the times required by the document. Review source details before typing a summary; a report should describe the specific incident, not assumptions based on a similar ticket."]),
        ("Draft versus completed report", ["Save as Draft is useful while information is incomplete. Save & Complete checks required fields before marking the report final. A completed document is a reporting state; it does not by itself change the operational incident to Resolved or Closed."]),
        ("Build a readable chronology", ["Record each event with its correct date and time. A timeline that crosses midnight must retain the next day's date. Add a missing event in its proper context, then review the sorted sequence rather than relying on entry order."]),
        ("Example: an overnight incident", ["Detection is recorded Monday 23:40, investigation Tuesday 00:10, and recovery Tuesday 01:20. These are three ordered events across two dates. Entering every event under Monday would misrepresent the outage even if the time values look correct."]),
        ("Circuit information", ["In the smart report, one available circuit can populate the related field automatically. With more than one circuit, choose the applicable circuit for that record. Review dependent records after deleting or renaming an inventory circuit so the report still describes the intended service."]),
        ("Export and final review", ["Save your latest changes before exporting PDF or Word. Check the incident reference, chronology, impact statements, circuit associations, and photo captions. An exported document is a saved output; later source changes do not automatically rewrite a file you already shared."])
    ],
    "notifications": [
        ("How to interpret the reference schedule", ["The table above is retained from the original documentation. The running application uses its configured job intervals and enablement settings, so an older reference interval is not a guarantee of the current delivery schedule. Source-data refresh and alert checks are also separate jobs."]),
        ("A check is not always a new message", ["A scheduled check inspects qualifying data. It can send nothing when there are no eligible records, the alert is disabled, the destination is unavailable, or the incident was already recorded as sent. Restarting the dashboard should not be treated as a request to resend every historical incident."]),
        ("Site Down threshold alerts", ["The threshold alert identifies qualifying outages that have lasted beyond its configured limit. It records delivery history so repeated checks can recognize an incident that was already announced. Multi-site messages can include a site sheet when the configured workflow supports that attachment process."]),
        ("Restoration details", ["Restoration timing follows the incident source rule. NOC/manual messages use Created At for the start and Closed At for restoration. Alarm-source messages use Issue Occurred At for the start and Cleared Alarm Received At for restoration. Root Cause uses Actual Root Cause only; Action Recovery uses Resolution only. These are different fields from the original alert's suspected cause or note."]),
        ("Example", ["An outage is announced in the morning, then restoration is confirmed later. The restoration reply refers to the earlier incident; its posted time can be later than the restoration timestamp because the source had to update and a scheduled check had to run. Those two times do not have to be identical."]),
        ("If a message does not arrive", ["First check whether the incident qualifies in the dashboard, whether it was already sent, and whether the latest source update succeeded. Then check the configured destination and workflow result. A webhook accepting a request does not alone prove the final Teams post or attachment succeeded. Avoid repeated tests to a live group without agreeing the destination and test content."])
    ],
    "tech-stack": [
        ("Why local saved data is used", ["The application separates collecting source data from displaying it. Background jobs collect records, while page requests read saved copies and calculate the view. This reduces repeated source requests when several users open the same card."]),
        ("Different types of saved information", ["Live caches are replaceable snapshots of alarms, incidents, inventory, and other source records. Saved user selections and delivery history are different: they preserve Mentor sites, congestion exclusions, reports, and previously sent alerts. A routine source refresh should not erase those saved choices."]),
        ("Browser settings versus shared data", ["Presentation choices such as the saved theme can belong to the browser. The server's instance data holds shared application information. Copying only browser settings does not transfer the server's saved exclusions or alert history."]),
        ("Updates", ["Keep both the instance folder and the connection settings when moving to a new application folder. Stop the old version before copying its database, and run only the intended version afterward. Keeping old instance data does not prevent incident and alarm caches from refreshing."]),
        ("Performance expectations", ["A fast page can still show the last successful snapshot when a source is slow or unavailable. Page loading speed and source freshness are separate checks. Investigate a stale record using source update status and filters, not only how quickly the page opened."])
    ],
    "mentor-site": [
        ("What Mentor monitoring changes", ["Mentor Site narrows monitoring to the site codes you deliberately saved. It does not change the site's grade, make it VIP, close its tickets, or delete its alarms from other cards."]),
        ("Adding codes safely", ["Use site inventory codes and preserve leading zeroes. For bulk import, download the template and keep its expected header. Read validation results before completing the add operation. An unknown code should be checked against inventory instead of repeatedly uploading the same invalid file."]),
        ("Example", ["You save sites 0460 and 1002. Only alarms and qualifying Site Down incidents matched to those codes contribute to Mentor monitoring. If 0460 has three Main AC Failure events, it still counts as one site in that category. The detail list can show all three events."]),
        ("Why a site can remain Site Down", ["An active Site Down incident can keep the site in the down group even when no corresponding down alarm is currently matched. This reflects the combined alarm-and-incident rule, not necessarily a stale alarm row."]),
        ("Removing and retaining sites", ["Removing a configured site ends its Mentor selection but does not delete the source site or its incidents. Keep instance data during upgrades to preserve the monitoring list. For the full badge definitions and source rules, open the dedicated Mentor Site card guide."])
    ],
    "troubleshooting": [
        ("Start with the exact record", ["Record a site code, incident ID, or device and interface. Include the page, badge, selected dates, and category. A total without filters is difficult to verify because several correct views can count different populations."]),
        ("A missing record", ["Check status, category, time window, source occurrence or completion date, and inventory matching. For congestion, check whether its interface is excluded. For Mentor, verify the saved site code. For VIP/VVIP, verify the strategic designation and active site inventory."]),
        ("A different number", ["Determine the counting unit first. Sites, alarm rows, incidents, and WOs are not interchangeable. Then compare the same filters and allow the relevant source jobs to finish. If the mismatch remains, compare the actual identifiers in both lists."]),
        ("SLA example", ["Response Not Met and Resolution Not Met are independent filters. An incident can fail both. Seeing two Resolution failures inside a list of fifteen Response failures does not mean the separate Resolution total must be two. Open each count to inspect its own matching population."]),
        ("An empty page after startup", ["The application can open before its first successful background sync completes. Wait for the relevant data update, then refresh. If the page remains empty, check source availability and the selected filters rather than clearing all saved instance data."]),
        ("What to report", ["Provide the exact expected identifier, where you saw it in the source, the filters and time used, and what the dashboard shows. For delivery issues, include the destination and expected alert type without sharing bot tokens or signed webhook links in the report."])
    ],
})


ARTICLE_DETAILS["map-view"].extend([
    ("Grey site status and grey POP ownership are different", [
        "For a normal site marker, green means On Air and blue means Planned. Grey is the fallback for Other or an unrecognized inventory status. If that site matches an active Site Down condition, red takes precedence over the usual inventory color.",
        "For a POP marker, amber identifies Telcotech and purple identifies Ezecom. Grey means its owner value is blank, unknown, or not recognized as one of those two names. Grey POP ownership does not say that the POP is down, Planned, or removed.",
        "Example: a grey site can have an Other inventory status while a nearby grey POP has no recognized owner. The same color is used for two separate marker types. Open the popup to confirm whether it is a site or POP before interpreting the color."
    ]),
    ("An owner value can exist but still use grey", [
        "The marker color uses the recognized owner names. A different spelling or another owner value can use the fallback grey even when the owner field is not empty. Therefore the grey POP count is not necessarily the same as a database count of blank owner fields only.",
        "Read the POP name, code, and owner information together. Missing ownership does not delete the POP from inventory. It also does not establish an outage or prove that the physical device is unmonitored."
    ]),
    ("Latitude and longitude in the popup", [
        "Latitude and Longitude show the stored coordinates for the selected site or POP, formatted to six decimal places. These are the coordinates used for its map position, not a new GPS measurement taken when you open the popup.",
        "Latitude describes north/south position and longitude east/west position. Keep them in that order when comparing with another map. If a stored value is unavailable or invalid, the popup uses an underscore rather than inventing a coordinate."
    ])
])

ARTICLE_DETAILS["dashboard"].append(("Alarm colors and workflow colors", [
    "The green-zero and red-nonzero example explains alarm-count badges. It does not mean every colored label throughout the system is an alarm-health indicator. Incident and WO badges use their workflow labels, such as New, In Progress, or Resolved, to explain what the number represents.",
    "For example, a Resolved badge can show a positive count of completed work. That count is not automatically an unhealthy result. Read the badge label and card title first, then open its detail records. Map colors have their own separate status and owner meanings."
]))
