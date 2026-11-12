# Dashboard UI and performance audit - 5 November 2026

## Fixed and verified

- Category/week dropdowns could extend below the viewport and be covered by
  neighboring cards. Modern browsers now use native top-layer popups, sized
  and positioned within the viewport, with scrollable content. Existing native
  details behavior remains available as a fallback. Card hover no longer moves
  the entire card or creates an unnecessary transformed stacking context.
- Root-cause donut percentages inherited white text and a 30px fixed width from
  generic status badges. They now use theme-aware text and enough space for
  percentages. Checked in light and dark themes.
- Filter updates could arrive out of order, replace newer selections, or treat
  an HTTP error page as dashboard markup. Superseded requests are cancelled;
  stale responses are ignored; failed requests preserve the current content.
- Applying a second card filter could restore stale hidden values from an older
  fragment. Forms now preserve the current URL state for other cards.
- The browser clock previously used the viewer's timezone. It now uses the
  configured timezone, with a reused Intl formatter. Tested with a UTC browser
  and Asia/Phnom_Penh application configuration.
- Mentor import now offers a keyboard-accessible CSV dropzone, real selected-file
  information, actual upload-byte progress, server validation feedback, and retry
  handling. File type, empty file, and size checks use the configured server limit.
- Mentor code entry supports multi-line paste, deduplicated removable chips,
  leading zeroes, clear-all, and submission directly after typing.
- Repeated codes within a CSV previously inflated the added count. The in-file
  duplicate tracking now updates after each successful insert.
- Blacklist retains a table when empty, with a small SVG/message and an 11px note
  directly beneath its title. Congestion tooltips use a visible 1px border and
  3px corners without blur or shadow.

## Font verification

Fresh desktop browser checks confirmed Huawei Sans is loaded and applied to
Partner Contact and Mentor Sites, including table text and controls. Their
existing declarations did not require another font override. A browser serving
older stylesheet URLs should be refreshed to load the current styles.

## Performance evidence and limits

An isolated copy of the local cache was profiled without starting sync or alert
threads. Dashboard rendering measured about 2.58 seconds cold (including template
compilation) and 0.24 seconds on the next warm request. A cold live browser load
measured about 4.7 seconds; the document contained approximately 5,200 elements
and 603 KB of uncompressed HTML. These are individual local measurements, not
production averages or a claimed before/after speedup.

The implemented frontend changes avoid obsolete updates, needless hover
transforms, and repeated clock-formatter construction. The existing section-only
AJAX updates are retained. Screenshots were captured at desktop and mobile sizes.

## Recommendations requiring a separate decision

1. Fix the previously verified oldest-week SLA UTC/Cambodia cutoff mismatch in
   both summary and detail queries. The UI work did not change that data logic.
2. Centralize the repeated Streamline host in configuration. It is repeated in
   drilldown templates, map JavaScript, Telegram exports, and Teams helpers.
   No source-system host was changed in this pass.
3. Lazy-render remaining large weekly/modal detail tables to reduce initial DOM
   and HTML size. Measure this separately using representative VM traffic before
   changing caching lifetimes or refresh schedules.
4. Treat webhook acceptance separately from confirmed Teams/SharePoint delivery;
   the existing HTTP 202 response cannot verify the final attachment upload.

## Validation

- Python regression tests cover Mentor CSV handling, dashboard pages, SLA
  drilldowns, blacklist persistence/restoration, and shared page rendering.
- Node tests cover filter dismissal, stale-response protection, HTTP failures,
  and retaining other cards' query parameters.
- Headless Edge checks covered desktop and mobile dropdown positioning, touch
  interaction, outside-click/Escape closing, actual computed colors/fonts,
  congestion tooltip borders, and blacklist note/empty state sizing.
- A real upload request was exercised against an isolated temporary database:
  two unique sites added and a repeated site skipped. The live Mentor list was
  not changed by the browser tests.

Final checks: 530 Python tests passed, 10 Node behavior tests passed, and the
listed desktop/mobile browser checks passed with no JavaScript errors. The
browser's dark-theme text was checked after its color transition completed.


## Follow-up completed - 6 November 2026

The application retains its no-login PC/VM workflow as requested.

- Response and Resolution Time summary/detail queries now use the same Cambodia
  Monday cutoff, converted to the source's naive UTC timestamp representation.
  The application timezone is Asia/Phnom_Penh. Browser calendar/report defaults
  use explicit Cambodia date parts, and duration arithmetic is independent of
  the viewer's timezone/DST. MSSQL manual alarm timestamps derive from UTC+7,
  captured once per action; no alarm action was executed during verification.
- Root-cause labels/notes use DOM text nodes. Other dynamic tooltip strings are
  escaped. Browser checks with HTML-like labels confirmed literal rendering.
- Responses include nosniff, SAMEORIGIN framing, and strict-origin referrers.
  The compatible CSP limits base URLs, objects and framing without blocking the
  existing inline scripts, maps, styles or exports. HSTS is sent only over HTTPS.
- STREAMLINE_BASE_URL in configuration now supplies UI, map, export and alert
  source links; its default remains the existing Streamline endpoint.
- Mentor is site-database-only by the user's final decision. Manual/CSV input
  supports alphanumeric site identities and leading zeroes. POP NCODE/CODE
  catalogues and POP/device alarms are not used by Mentor. I0143 is therefore
  rejected unless it exists in site_cache.standard_code.
- Mentor matching uses parameterized filtered SQL with site indexes. In one
  local sample of 100 reads: site index 0.93ms vs scan 29.04ms; alarm-site index
  4.64ms vs scan 47.57ms. These are query samples, not whole-system speedups.
- Incident Age worklog detail tables are fetched only when their popup is opened.
  Initial worklog availability loads IDs only. Existing per-day volume popups
  were already lazy-loaded. Other weekly detail tables remain server-rendered.
- Local dashboard sample: 599,571 uncompressed HTML bytes; 1.94s first request
  and 0.55s subsequent request. Dataset and compilation effects limit comparisons
  to earlier measurements; no production-load improvement percentage is claimed.

Verification: 543 Python tests and 12 Node tests passed; Pyflakes clean.
Headless Edge verified real I0143 validation without saving, lazy worklog loading,
headers, no JavaScript errors, and literal root-cause text. Browser timezone was
America/New_York; a fixed UTC instant still produced the correct Cambodia date.


## INC-WO: All Resolved - 6 November 2026

The Incident/INC-WO by Status card now has a separate incident-count badge below
Overdue L3. The existing resolved-WO badge is labelled Resolved WOs. The new
badge uses object_322.all_wo_is_resolved = true and checks every linked WO in
object_324 without excluding closed/unknown-status siblings before grouping.
There must be at least one WO, every WO must be strictly resolved, and the
parent incident must not already be closed. Its cached snapshot, badge,
drilldown and CSV export all contain one row per qualifying incident.

Source verification found 68 non-closed incidents with a true source flag;
2 still had an In Progress WO, so the strict badge included 66 incidents.
Only a new local summary cache was written; no source incidents/WOs were changed.
The summary is refreshed in the regular incident sync cycle. Failures retain the
previous successful snapshot rather than replacing it with a false zero.

Validation: 544 Python tests passed. The actual summary SQL was tested with
mixed statuses, closed/null WO states, zero WOs, false source flags and closed
parent incidents. Live Edge checks confirmed the 66-row incident drilldown,
exclusion of the two inconsistent records, and site-only Mentor validation
with letter entry. No browser JavaScript errors were observed.


### Follow-up audit: circuit fields and congestion blacklist

- Circuit updates run once per browser frame and skip unchanged fields. Editing unrelated inventory fields does not rebuild circuit choices or the fault summary.
- Blacklist requests cancel when replaced or dismissed. Late responses cannot overwrite the current list. Requests bypass the browser cache.
- Interface, additional info and notes persist with exclusion rules. Existing schemas upgrade without deleting rules; missing historical metadata stays blank.
- Shortened reviewed comments and removed real incident examples. No unused imports or undefined names were reported by Pyflakes. All SQL files have query-loader references; none were removed as unused.
- Baseline: 556 Python tests passed. After the changes, 65 affected Python tests and 12 existing JavaScript checks passed. Edge reported no dashboard JavaScript errors; local median frame interval was 8.3 ms. This measures the local browser, not VM load or source database query latency.


## Dashboard initial loading review - 12 November 2026

Existing request logs showed dashboard server render times of approximately 1.96-4.27 seconds under the user's active PC workload. Profiling identified historical performance context and template construction as the largest part of initial page rendering.

The live cards and graph row remain server-rendered immediately. Historical performance cards now load through the existing /performance-cards route when their section approaches the viewport. This reduces critical-path work rather than changing query definitions or caching data for longer. Requests retain current filters; chart initialization runs after insertion. Failed loads retain a Retry control. Hash links into historical cards trigger loading before scrolling. The full-page fallback is /?load_performance=1; DASHBOARD_LAZY_PERFORMANCE=false disables the optimization after a web-process restart.

Week labels in the root-cause table are computed once per selected week rather than reformatting the same label for each category/duration cell. No counting, sorting, deduplication or duration predicates changed.

Five-run local median comparison using one consistent, temporary read-only-source cache snapshot:

| Render | Median server time | Initial HTML |
|---|---:|---:|
| Full-page compatibility mode | 448.1 ms | 591.6 KiB |
| Deferred initial page | 104.1 ms | 160.4 KiB |
| Historical section, loaded separately | 358.0 ms | 431.5 KiB |

Initial server time improved by approximately 77%, and initial HTML by approximately 73%. These are warm local test-client measurements, not production VM timings or total-load CPU savings. Historical calculations still run when the section is needed. Hardware load, memory pressure, source freshness and network conditions can affect real performance.

Validation: 730 Python tests, 14 JavaScript regression tests, Python static checks and JavaScript syntax checks passed. An isolated Edge browser verified deferred loading, HTTP failure/retry, subsequent filter swaps and absence of page JavaScript errors. Comparing 3,465 historical DOM elements between full-page and fragment rendering on the same populated snapshot produced identical values, links and attributes. Existing filter/drilldown/SLA tests passed.

The repeatable benchmark is scripts/diagnostics/profile_dashboard.py. It clones the local cache through SQLite's backup API into a temporary test instance, disables jobs and delivery through testing configuration, measures renders and removes its snapshot. It does not modify the production cache or send alerts.

No production process was restarted, no live sync or notification was triggered, and no commit, push or deployment ZIP was created during this review. Existing dedicated-worker and API changes remain in the working tree.


## Historical drilldown review - 12 November 2026

Large historical tables were measured as a remaining bottleneck: the populated SLA view had 20,104 rows and approximately 14 MiB HTML, and Resolution Time had 12,241 rows and approximately 4.9 MiB HTML. Paging was evaluated but removed at the user's request. The active implementation shows all matching historical rows together, with no 100-row limit or Previous/Next controls. Existing in-page search and complete exports are retained.

The earlier deferred dashboard chart loading and precomputed week-label improvements remain active. No source SQL, database schema, notification rules or live records were changed. Further historical-table optimization must preserve the all-rows view the user requested.

The live cache returned ok from a read-only PRAGMA quick_check. Original paging experiment results are not performance claims for the restored all-rows tables. No commit, push, production restart or ZIP build was performed.


## Filter interaction review - 12 November 2026

Filter placement previously measured popup bounds twice on every outer scroll reposition and scanned all filters in each animation frame. Placement now tracks the active filter, measures popup size once per open/input/resize/font update, and reuses those dimensions while scrolling. Internal option-list scrolling does not schedule placement work. Popup dimensions are invalidated when relevant inputs or viewport/font dimensions change. Stable scrollbar space prevents list-width shifts.

Apply and Clear close the floating popup without altering field values. Identical repeated Apply clicks while the same request is pending no longer abort and restart that request. Different later requests still cancel/ignore stale responses, and other cards' current filter parameters remain preserved. Scheduled page refresh now defers during active filter-fragment requests while retaining the existing refresh schedule and maximum deferral behavior.

Validation: 16 JavaScript regression tests and 12 focused Python/browser tests passed. An isolated Edge check measured one popup size read on open and no additional popup size reads while internally scrolling or scrolling the page. The popup stayed within desktop/mobile viewport bounds after resize. Apply closure, outside click, Escape, checkbox interaction, failed-load retry, repeated filter updates and all-rows historical-table visibility passed. JavaScript syntax checks passed.

No pagination was reintroduced. No source records, database tables, sync intervals or alert rules were changed. These checks confirm the tested local browser behaviors, not a production VM frame-rate guarantee. Changes remain local until an authorized deployment.


## Follow-up project performance review - 12 November 2026

A fresh five-run benchmark on an isolated SQLite backup measured median server render times of 53.4 ms for the initial dashboard, 201.9 ms for the full-page compatibility mode and 160.7 ms for the separately loaded historical section. Initial HTML was 158.9 KiB versus 590.1 KiB for full rendering. These are warm local test-client timings under the current PC workload, not VM or end-to-end browser timings. The historical section still runs when needed; the measurements do not imply that its CPU work disappeared.

Table search now skips repeated normalized queries and writes a row's display style only when visibility changes. Browser verification with 1,000 rows confirmed all records remain available, clearing search restores all rows, and an equivalent query causes zero row-style mutations. Dynamically initialized blank cells use the same em dash as initial tables instead of a question mark. No pagination, count definitions, SQL or notification rules changed.

Read-only database quick_check returned ok. Worker heartbeat was healthy with 20 job loops at the time of inspection. Python syntax parsing passed for 193 application/script/entry-point files; Pyflakes reported no findings. All browser JavaScript files passed syntax checks, and all 16 JavaScript regressions passed. Three focused browser tests passed, covering chart retry, filter scrolling and table search. No manual test notifications were sent.

Large all-row historical drilldowns remain the main known browser-rendering constraint. They retain every matching row as requested. Actual VM contention, source query latency and concurrent-user load require measurement on that VM. Saved data, environment settings and scripts were preserved. No commit, push, deployment or ZIP build was performed.

Full Python regression suite completed: 752 passed in 134.64 seconds. The added table-search browser regression also passed in the separate three-test browser run.


## Release verification - v19.3.8, 12 November 2026

The full final Python suite passed: 824 tests. The shared HTTP error handler covers all 31 Werkzeug HTTP error statuses with browser pages or API JSON, preserving Allow and Retry-After headers and hiding internal exception details. Normal startup ensures a separate worker; calendar-date filters include complete Cambodia days. Existing saved data and notification schedules are preserved. The deployment ZIP excludes instance, real environment configuration, logs, virtual environments and tests. Copy the existing VM .env and complete instance folder during upgrade, and install requirements into the new project virtual environment.

Smart Report follow-up: section 2 Monthly Outage Statistics now supplies downstream circuit choices. One circuit fills automatically; multiple circuits provide a dropdown. Renaming keeps linked rows associated, and removing a source circuit removes only its dependent rows. Section 1 inventory is independent. A blank monthly row is present on new reports so January through December can be entered immediately. Section 3 remains a mirror of section 2. All twelve months passed browser input and save/reload/DOCX export checks. Reference-template export tests passed. Monthly table widths were aligned for readable horizontal scrolling. The focused 22-test report suite passed.

Final release check after the Smart Report follow-up: all 826 Python tests passed. JavaScript regressions (16), JavaScript syntax checks and Pyflakes passed. The rebuilt 410-file ZIP passed archive integrity and source parity checks.
