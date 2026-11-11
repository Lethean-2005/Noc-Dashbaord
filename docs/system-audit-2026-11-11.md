# System review - 11 November 2026

## Smart Network Report

Updated the active Word template to Smart Network Report_Sep-Oct 2026_v1. The editor and exports now support all six tables, including Failure to React and Credit Note Summary. Report periods accept month ranges and table years follow the entered period. The original active template is backed up under docs/reference/backups.

New fields are additive database columns. Existing saved reports remain readable; new sections start blank. No reference sample records are inserted into saved reports. Restart the dashboard to apply the additive schema initialization. Preserve the existing instance directory and configuration during deployment.

Reaction delay calculates from Smart Complain to TCT Respond using entered local clocks, with invalid dates and negative intervals rejected. Existing manually entered delays remain editable and preserved. SLA decisions, credit percentages and amounts remain manual: no approved business rule was supplied to infer them. The reference contains an inconsistent sample delay and was used for layout rather than factual data.

Circuit associations extend to both new sections. Renaming inventory entries updates linked rows; removing an inventory circuit removes its linked report rows. An unmatched historical circuit now stays in draft form data instead of being omitted by a disabled selected option. Final form validation still requires a valid inventory circuit.

## Conservative cleanup

Removed eight confirmed unused static assets: three Amazon Ember WOFF2 files, Exo2-Bold.ttf, Inter-Regular.ttf, Nunito-Variable.ttf, no-data-available.png and no-results.svg. Removed obsolete font-face declarations and superseded report date/year/cell-format helpers. Active Huawei Sans fonts and SVG empty states remain.

No files in scripts were deleted. No live database, instance files, environment configuration or source-system records were changed. Pre-existing repository changes were preserved. Files with uncertain runtime use were retained.

## Verification

- Full automated suite: 681 passed before final small browser/date refinements.
- Final targeted report suite after refinements: 12 passed, including draft FormData preservation, circuit associations, persistence, template structure and removal of reference sample records.
- Syntax: 199 Python files, 20 application JavaScript files and 82 Jinja templates passed.
- Pyflakes: app, scripts and webhook passed.
- Isolated browser workflow verified editor save/reload, response delay, manual credits, circuit rename, add/remove rows, report year headers and desktop/mobile page overflow. No browser JavaScript errors occurred.
- Hidden Word export and PDF rendering succeeded. The sample has three pages and preserves the final landscape credit section; the supplied reference has four pages because it contains more rows. Visual checks confirmed readable tables and no clipped report sections.

## Limits and remaining work

These checks do not prove absence of every defect or establish production VM load capacity. No production alerts were sent, no source data was rewritten and no deployment ZIP was rebuilt. Power Automate HTTP acceptance still does not independently prove downstream delivery. Source All WO is Resolved flags can disagree with actual linked WO statuses; the existing strict check remains in place. Congestion alarm families may count the same POP separately; no unapproved counting change was made. Dedicated hardware-fault, degraded-TX and RT integration remain separate unimplemented requests.

Preview: docs/previews/smart-network-latest-preview.pdf. The preview contains illustrative records only and is not production data.
