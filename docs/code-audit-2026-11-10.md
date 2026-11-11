# Code audit - 10 November 2026

Assessment: the application passes its existing checks, but it is not free of logic and maintenance issues. This audit changes no runtime code, live records, alert history, deployment files, or VM settings.

## Fixes verified after the audit

- Circuit rows keep a stable inventory association during rename. Temporary blank IDs retain their outage data. Removing an inventory row removes only its dependent report rows.
- User row additions/removals and selection changes trigger the unsaved-edit warning; initialization and successful submission do not.
- Weekday popups check HTTP status, show retry guidance, block duplicate in-flight requests, and ignore responses for detached modals.
- Badge reads now select only required columns. On 5,000 synthetic alarms, identical counts took a median 48.3 ms versus 117.8 ms for the full-payload calculation. This is a local benchmark, not a VM load test.
- Scheduler comments now match the five-minute defaults.
- Removed 5 obsolete manual alert scripts and 13 generated preview artifacts. The scripts folder and automated regression suite are retained.
- Final checks: 565 Python tests, 14 JavaScript tests, application syntax checks and Pyflakes passed.
- No live records, external flow configuration or ZIP archives were changed. The delivery-confirmation limitation below still requires Power Automate run history or completion feedback.

The following findings describe the initial audit; the three confirmed bugs have now been fixed.

## Confirmed bugs

1. **High - circuit rename can misattribute outage data.** `app/static/js/smart-circuits.js:56` selects the first inventory circuit when the previous selection disappears. Reproduced with two inventory circuits and an outage assigned to the second: renaming the second reassigned its existing percentage data to the first. Preserve an explicit row/circuit association during rename; do not silently move recorded outage data to another circuit.
2. **Medium - deleting a saved report row misses the unsaved-change warning.** `app/static/js/incident-report.js:7` marks the form dirty only on input. Removing an existing row triggers no input event. An isolated browser check confirmed that beforeunload was not cancelled after deletion. Track structural changes and user selections as well as typing, while keeping initial rendering clean.
3. **Medium - weekday popup accepts server failures as loaded content.** `app/static/js/graph_cards.js:84` reads the response without checking its status and has no rejection handler. A mocked HTTP 500 response was inserted into the popup and marked loaded, preventing a normal retry on reopen. Check response.ok, display an inline retryable error, and mark loaded only after success.

## Delivery limitation

`app/services/incident/site_down_24h_alert_service.py:477` treats any HTTP 2xx as success, and line 536 records that result in the deduplication ledger. HTTP 202 confirms webhook acceptance, not completion of subsequent Teams/SharePoint actions. If the flow fails after accepting the request, the dashboard can retain a sent marker without a Teams message. Confirm delivery through Power Automate run history or a completion acknowledgement before representing it as confirmed delivery. This review did not send messages or inspect flow runs.

## Performance and maintainability

- Alarm badge methods still load full Ezecom/Telcotech cache tables for counting, then apply exclusions and aggregate in Python. This is a scaling concern, not a measured VM slowdown. Measure representative cache sizes and query timings before moving counts and exclusion predicates into indexed SQL.
- Large modules concentrate unrelated responsibilities: incident_service.py (2,879 lines), dashboard.py (2,811), tables.css (2,321), partner_contact.js (1,902). Split them gradually by feature with regression checks; a bulk rewrite is unnecessary.
- `site_down_24h_alert_scheduler.py:6` and `:9` describe 24-hour and 15-minute defaults, while `app/config.py:274` and `:280` both default to 300 seconds. Correct the comments; the runtime configuration is authoritative.

## Checks passed

- 562 Python tests and 14 JavaScript tests.
- Syntax validation: 184 Python files, 18 JavaScript files, 60 Jinja templates.
- Pyflakes reported no unused imports or undefined names.
- Static reference scan found no SQL files without application references. This does not prove every named query is exercised at runtime.
- Three targeted browser fixtures confirmed the bugs above without editing real data or contacting Teams/Telegram.

## Scope limits

This is a local source and test audit, not an exhaustive proof of correctness, a production database reconciliation, a VM load test, or a penetration test. Existing tests passed before the targeted browser reproductions; passing tests do not cover the three confirmed gaps. No login change is proposed: the application's no-login deployment is intentional.

Recommended order: correct circuit reassignment, add structural dirty tracking, then harden weekday popup failure handling. Follow with measured SQL optimization and smaller feature modules.
