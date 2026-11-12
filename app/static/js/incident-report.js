// Strict entered-clock parsing for Smart Report intervals; reject rolled-over dates.
function parseSmartReportDateTime(value) {
    var text = (value || '').trim();
    var match = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})$/.exec(text);
    var year, month, day, hour, minute, second = 0;
    if (match) {
        var months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
        day = +match[1]; month = months.indexOf(match[2].toLowerCase()); year = +match[3]; hour = +match[4]; minute = +match[5];
    } else {
        match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(text);
        if (!match) return null;
        year = +match[1]; month = +match[2] - 1; day = +match[3]; hour = +match[4]; minute = +match[5]; second = +(match[6] || 0);
    }
    if (month < 0 || month > 11 || day < 1 || hour < 0 || hour > 23 || minute < 0 || minute > 59 || second > 59) return null;
    var date = new Date(Date.UTC(year, month, day, hour, minute, second));
    return date.getUTCFullYear() === year && date.getUTCMonth() === month && date.getUTCDate() === day ? date : null;
}

// Warn before leaving a report with unsaved edits.
(function () {
    var form = document.getElementById('incidentReportForm');
    if (!form) return;

    var isDirty = false;
    form.addEventListener('input', function () {
        isDirty = true;
    });
    form.addEventListener('change', function (event) {
        if (event.isTrusted) isDirty = true;
    });
    // Capture before inline remove handlers detach the clicked row.
    form.addEventListener('click', function (event) {
        if (event.target.closest('.ir-event-remove, .ir-event-insert, .ir-smart-row-remove, .ir-smart-row-insert, [id^="irAdd"], #irRemoveSecondFault')) isDirty = true;
    }, true);
    // Saving or changing report status clears the navigation warning.
    document.addEventListener('submit', function () {
        isDirty = false;
    });
    window.addEventListener('beforeunload', function (e) {
        if (!isDirty) return;
        e.preventDefault();
        e.returnValue = '';
    });
})();

// Open the report picker and navigate to the selected report.
(function () {
    var toggle = document.getElementById('irReportPickerToggle');
    var card = document.getElementById('irReportPickerCard');
    var optionsEl = document.getElementById('irReportPickerOptions');
    if (!toggle || !card || !optionsEl) return;

    function closeDropdown() {
        card.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (card.style.display === 'block') { closeDropdown(); return; }
        card.style.display = 'block';
        toggle.classList.add('is-open');
    });

    optionsEl.querySelectorAll('.pc-field-dropdown-option').forEach(function (btn) {
        btn.addEventListener('click', function () {
            window.location.href = btn.dataset.href;
        });
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
})();

// Report TYPE picker (top toolbar, left of the report picker) — same
// toggle/outside-click-close/navigate-on-click pattern as the report
// picker above, just a separate dropdown instance (see
// _type_picker.html). Both dropdowns' outside-click handlers already
// close on any click outside .pc-field-with-dropdown, which covers
// this one too without changes there.
(function () {
    var toggle = document.getElementById('irTypePickerToggle');
    var card = document.getElementById('irTypePickerCard');
    var optionsEl = document.getElementById('irTypePickerOptions');
    if (!toggle || !card || !optionsEl) return;

    function closeDropdown() {
        card.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (card.style.display === 'block') { closeDropdown(); return; }
        card.style.display = 'block';
        toggle.classList.add('is-open');
    });

    optionsEl.querySelectorAll('.pc-field-dropdown-option').forEach(function (btn) {
        btn.addEventListener('click', function () {
            window.location.href = btn.dataset.href;
        });
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
})();

// Incident Report document page — "Add Event" appends a date/time/
// description row to the Chronology of Events list, with its date
// pre-filled from the "Incident Date" field above (not today's real
// date) — confirmed needed live: the incident itself may have happened
// on a different day than whenever staff happen to be filling the form
// in, so a new chronology row should default to following the incident
// it's documenting, not the browser's clock. Falls back to the actual
// current date only if Incident Date hasn't been filled in yet, so the
// field never defaults to something visibly empty. Time still defaults
// to the real current time (that part wasn't the issue — staff log
// each event close to when it actually happens) and the saved order
// gets sorted chronologically regardless of what's typed here or in
// what order (see incident_report_service.py's own _event_sort_key()).
// Each row's own remove button is wired inline (onclick="this.closest(...).remove()",
// see document.html) since rows are static once added, no need for a
// delegated listener here; the date field's calendar icon works via
// the delegated picker handler further down this file, so a row added
// here gets the same picker with no extra wiring.
//
// Each row ALSO has its own "+" insert button (.ir-event-insert) —
// requested: staff filling in a chronology after the fact often need to
// slot a missed event in BETWEEN two already-entered ones, not just at
// the bottom via "Add Event". That handler is delegated (further down
// this IIFE) rather than wired per-row like remove is, so it covers
// both the server-rendered initial rows AND ones created here with no
// extra wiring either way.
(function () {
    var addBtn = document.getElementById('irAddEvent');
    var rows = document.getElementById('irEventRows');
    if (!rows) return;

    var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function buildEventRow(dateValue, timeValue) {
        var row = document.createElement('div');
        row.className = 'ir-event-row';
        row.innerHTML =
            '<div class="ir-date-field">' +
                '<input type="text" name="event_date" placeholder="22-Sep-2026" class="ir-date-text" required>' +
                '<button type="button" class="ir-date-pick-btn" aria-label="Pick a date"><i class="ti ti-calendar"></i></button>' +
            '</div>' +
            '<div class="ir-time-field">' +
                '<input type="text" name="event_time" placeholder="13:00" class="ir-time-only-text" required>' +
                '<button type="button" class="ir-date-pick-btn" aria-label="Pick a time"><i class="ti ti-clock"></i></button>' +
            '</div>' +
            '<input type="text" name="event_description" placeholder="What happened at this time..." required>' +
            '<button type="button" class="ir-event-insert" aria-label="Insert event below this one"><i class="ti ti-plus"></i></button>' +
            '<button type="button" class="ir-event-remove"><i class="ti ti-x"></i></button>';
        row.querySelector('.ir-date-text').value = dateValue;
        row.querySelector('input[name="event_time"]').value = timeValue;
        row.querySelector('.ir-event-remove').addEventListener('click', function () {
            row.remove();
        });
        return row;
    }

    if (addBtn) {
        addBtn.addEventListener('click', function () {
            var now = window.NocTime.parts();
            // Follows the LAST existing event row's own date first — a
            // chronology moves forward in time, so once it's already
            // progressed to a later day (e.g. rolled past midnight), the
            // next new row should keep following that same later day, not
            // jump back to the incident's original start date. Only falls
            // back to Incident Date when there's no event row yet to follow
            // (the very first "Add Event" click), and to today's real date
            // if even that's still empty.
            var existingDateInputs = rows.querySelectorAll('input[name="event_date"]');
            var lastEventDate = existingDateInputs.length
                ? existingDateInputs[existingDateInputs.length - 1].value.trim()
                : '';
            var incidentDateInput = document.querySelector('input[name="incident_date"]');
            var incidentDate = incidentDateInput ? incidentDateInput.value.trim() : '';
            var defaultDate = lastEventDate || incidentDate ||
                (now.day + '-' + MONTHS[(now.month - 1)] + '-' + now.year);
            var defaultTime = pad2(now.hour) + ':' + pad2(now.minute);
            var row = buildEventRow(defaultDate, defaultTime);
            rows.appendChild(row);
            row.querySelector('input[name="event_time"]').focus();
        });
    }

    // Per-row "+" — inserts a new blank row directly AFTER the one it
    // was clicked on (insertAdjacentElement, not rows.appendChild), so
    // it lands exactly where it's needed in the middle of the list
    // instead of always at the bottom. Defaults its date to THAT row's
    // own date (continuing from that specific point in the chronology),
    // falling back the same way "Add Event" does if that row's date is
    // still blank. Delegated on `rows` so it works for every row
    // regardless of whether it was server-rendered or added later.
    rows.addEventListener('click', function (e) {
        var insertBtn = e.target.closest('.ir-event-insert');
        if (!insertBtn) return;
        var clickedRow = insertBtn.closest('.ir-event-row');
        if (!clickedRow) return;

        var now = window.NocTime.parts();
        var clickedDate = clickedRow.querySelector('input[name="event_date"]').value.trim();
        var incidentDateInput = document.querySelector('input[name="incident_date"]');
        var incidentDate = incidentDateInput ? incidentDateInput.value.trim() : '';
        var defaultDate = clickedDate || incidentDate ||
            (now.day + '-' + MONTHS[(now.month - 1)] + '-' + now.year);
        var defaultTime = pad2(now.hour) + ':' + pad2(now.minute);
        var newRow = buildEventRow(defaultDate, defaultTime);
        clickedRow.insertAdjacentElement('afterend', newRow);
        newRow.querySelector('input[name="event_time"]').focus();
    });
})();

// "Add Second Fault" — reveals page 2 (2nd Fault Analysis & Resolution,
// Improvement and Preventive Plan, Picture Reference; see
// Incident_Report_PCCW-MX1052-MX1054.pdf, the reference this mirrors —
// a real incident whose root cause was misdiagnosed once, then found to
// actually be something else entirely). Prefixes the ORIGINAL Fault
// Analysis section's own labels with "1st " while a second fault is
// showing, matching the reference's own numbering once there are two —
// "Remove Second Fault" reverses all of it (hides page 2, clears the
// flag, drops the "1st " prefix again) rather than just hiding the
// section and leaving stale has_second_fault/label state behind.
(function () {
    var addBtn = document.getElementById('irAddSecondFault');
    var removeBtn = document.getElementById('irRemoveSecondFault');
    var page2 = document.getElementById('irPage2');
    var flagInput = document.getElementById('irHasSecondFault');
    var fault1Labels = document.querySelectorAll('#irFault1Body .ir-fault-label');
    var issuedTimeRow = document.getElementById('irIssuedTimeRow');
    var issuedTimeInput = issuedTimeRow ? issuedTimeRow.querySelector('input[name="issued_time"]') : null;
    if (!addBtn || !removeBtn || !page2 || !flagInput) return;

    function setLabelsPrefixed(prefixed) {
        Array.prototype.forEach.call(fault1Labels, function (label) {
            var has1st = label.textContent.indexOf('1st ') === 0;
            if (prefixed && !has1st) label.textContent = '1st ' + label.textContent;
            else if (!prefixed && has1st) label.textContent = label.textContent.slice(4);
        });
        // Issued Time only means anything once there are two distinct
        // causes (see Incident_Report_PCCW-MX1052-MX1054.pdf) — hidden
        // (and not required) for a single-fault report, the default.
        if (issuedTimeRow) issuedTimeRow.hidden = !prefixed;
        if (issuedTimeInput) issuedTimeInput.required = prefixed;
    }

    addBtn.addEventListener('click', function () {
        flagInput.value = '1';
        page2.hidden = false;
        addBtn.hidden = true;
        removeBtn.hidden = false;
        setLabelsPrefixed(true);
    });

    removeBtn.addEventListener('click', function () {
        flagInput.value = '';
        page2.hidden = true;
        addBtn.hidden = false;
        removeBtn.hidden = true;
        setLabelsPrefixed(false);
    });

    // An existing report that already has a second fault loads with
    // page 2 already un-hidden (document.html's own `hidden` condition)
    // — the labels need the same "1st " prefix from the start too.
    if (flagInput.value.trim()) setLabelsPrefixed(true);
})();

// Improvement and Preventive Plan — one text line per action, same
// add/remove pattern as "Add Event" above, just without the date/time
// columns it doesn't need.
(function () {
    var addBtn = document.getElementById('irAddPlanItem');
    var rows = document.getElementById('irPlanItems');
    if (!addBtn || !rows) return;

    addBtn.addEventListener('click', function () {
        var row = document.createElement('div');
        row.className = 'ir-plan-row';
        row.innerHTML =
            '<input type="text" name="improvement_item" placeholder="e.g. Strengthen coordination and escalation with relevant network partners">' +
            '<button type="button" class="ir-event-remove"><i class="ti ti-x"></i></button>';
        row.querySelector('.ir-event-remove').addEventListener('click', function () {
            row.remove();
        });
        rows.appendChild(row);
        row.querySelector('input').focus();
    });
})();

// Picture Reference — each click on "Add Picture" creates its own
// single-file input (see document.html's own note on why: a shared
// multiple-file input's FileList is read-only, so there's no clean way
// to remove just ONE already-picked file from it) with a live preview
// via URL.createObjectURL, same add/remove shell as Chronology/
// Improvement Plan above. Already-saved photos (rendered server-side
// straight from their own base64 — see document.html) use the exact
// same .ir-picture-item markup and remove the same way, just with a
// keep_picture_id hidden input instead of a file input.
(function () {
    var addBtn = document.getElementById('irAddPicture');
    var list = document.getElementById('irPictureList');
    if (!addBtn || !list) return;

    addBtn.addEventListener('click', function () {
        var input = document.createElement('input');
        input.type = 'file';
        input.name = 'picture_reference';
        input.accept = 'image/*';
        input.hidden = true;

        var item = document.createElement('div');
        item.className = 'ir-picture-item';
        item.appendChild(input);

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'ir-event-remove';
        removeBtn.innerHTML = '<i class="ti ti-x"></i>';
        removeBtn.addEventListener('click', function () {
            item.remove();
        });

        input.addEventListener('change', function () {
            if (!input.files || !input.files[0]) {
                item.remove();
                return;
            }
            var img = document.createElement('img');
            img.src = URL.createObjectURL(input.files[0]);
            item.insertBefore(img, removeBtn);
        });

        item.appendChild(removeBtn);
        list.appendChild(item);
        input.click();
    });
})();

// "Save as Draft" carries formnovalidate (see document.html) so it can
// skip every OTHER required field — but Export File Name must still be
// filled in even for a draft. formnovalidate skips the browser's own
// required check too, so this enforces just that one field manually:
// setCustomValidity() + reportValidity() shows the exact same native
// validation bubble the browser would show on its own, just scoped to
// this single input instead of the whole form.
(function () {
    var draftBtn = document.getElementById('irSaveDraftBtn');
    var fileNameInput = document.getElementById('irFileName');
    if (!draftBtn || !fileNameInput) return;

    draftBtn.addEventListener('click', function (e) {
        if (!fileNameInput.value.trim()) {
            e.preventDefault();
            fileNameInput.setCustomValidity('Enter an Export File Name before saving — even a draft needs one.');
            fileNameInput.reportValidity();
            fileNameInput.focus();
        } else {
            fileNameInput.setCustomValidity('');
        }
    });

    fileNameInput.addEventListener('input', function () {
        fileNameInput.setCustomValidity('');
    });
})();

// Export File Name auto-fill — live-builds "IR_<Customers Impacted>-
// <Service Disruption>_<Reported Date>" as those 3 fields are typed
// (matches the reference IR_SMART-IX1222_11-Sep-2026 template naming),
// starting from "IR" alone on a brand-new report. Recomputed from
// scratch on every keystroke in any of the 3 source fields (not
// incrementally appended), so filling them out of order, or editing one
// after the others are already set, still lands on the right name.
// Stops auto-updating the moment either (a) the user types into the
// filename field directly (setting .value from this file never fires
// 'input', so that listener only catches real keystrokes, not our own
// updates), or (b) the field's CURRENT value doesn't match what these 3
// fields would build right now — NOT simply "the field already had a
// value on page load": an existing Draft that was only ever auto-filled
// (never hand-edited) should keep tracking Reported Date/Customers/
// Service Disruption after a reload too, otherwise saving once silently
// freezes the name forever even though the user never customized it.
(function () {
    var fileNameInput = document.getElementById('irFileName');
    var customersInput = document.querySelector('input[name="customers_impacted"]');
    var disruptionInput = document.querySelector('input[name="service_disruption"]');
    var reportedDateInput = document.querySelector('input[name="reported_date"]');
    if (!fileNameInput || !customersInput || !disruptionInput || !reportedDateInput) return;

    function buildFileName() {
        var customers = customersInput.value.trim();
        var disruption = disruptionInput.value.trim();
        var reportedDate = reportedDateInput.value.trim();

        var name = 'IR';
        if (customers) name += '_' + customers;
        if (disruption) name += (customers ? '-' : '_') + disruption;
        if (reportedDate) name += '_' + reportedDate;
        return name;
    }

    var currentValue = fileNameInput.value.trim();
    // Empty is never "manually set" — that's just a brand-new report
    // that hasn't been auto-filled yet at all, not a customization.
    var manuallySet = currentValue !== '' && currentValue !== buildFileName();

    function refresh() {
        if (manuallySet) return;
        fileNameInput.value = buildFileName();
    }

    [customersInput, disruptionInput, reportedDateInput].forEach(function (input) {
        input.addEventListener('input', refresh);
    });
    fileNameInput.addEventListener('input', function () {
        manuallySet = true;
    });
    // "IR" is a fixed, non-deletable prefix here too — same "default
    // cannot delete" convention as Incident Number's "TCT#" — restored
    // on blur (not on every keystroke like 'input' above): checking
    // "does it start with IR" mid-typing was firing after EVERY single
    // character typed into an empty/cleared field, and prepending "IR"
    // to a still-partial value ("I", then "IR", ...) corrupted normal
    // typing into "IRIR_WhateverWasTyped" — blur only checks the final,
    // fully-typed value once the user is done editing.
    fileNameInput.addEventListener('blur', function () {
        if (fileNameInput.value.indexOf('IR') !== 0) {
            fileNameInput.value = 'IR' + fileNameInput.value;
        }
    });

    refresh();
})();

// Incident Received By — same input+dropdown-card shortcut as Partner
// Contact's Domain field (partner_contact.js's own pcDomainToggle wiring
// below is the reference this mirrors), just a fixed local name list
// instead of a server-fetched one — these are NOC staff names, not
// per-report data, so there's no cache table to fetch from. Still a
// real <input>: picking a name from the list is a shortcut, typing any
// other name by hand works exactly the same as before.
(function () {
    var NAMES = [
        'BE Chhaylong', 'YEN Vandy', 'HOEUNG Tangho', 'HOUT Heang',
        'PHIEU Phiyo', 'NGOUN Sophornrangesey', 'POL OEUN Rachhun', 'SEAK Osopol',
        'VIN Rithea', 'KHLORK Pao', 'MEAS Ratha', 'RY Yany',
        'TOUCH Oudom', 'TIT Sorphea', 'MOCH Tola', 'PHAL Ratanalike',
    ];

    var field = document.getElementById('irReceivedBy');
    var toggle = document.getElementById('irReceivedByToggle');
    var dropdown = document.getElementById('irReceivedByDropdown');
    var optionsEl = document.getElementById('irReceivedByOptions');
    if (!field || !toggle || !dropdown || !optionsEl) return;

    function closeDropdown() {
        dropdown.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (dropdown.style.display === 'block') { closeDropdown(); return; }

        var current = field.value.trim();
        optionsEl.innerHTML = '';
        NAMES.forEach(function (name) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'pc-field-dropdown-option' + (name === current ? ' is-selected' : '');

            var label = document.createElement('span');
            label.className = 'pc-field-dropdown-option-label';
            label.textContent = name;

            var check = document.createElement('span');
            check.className = 'pc-field-dropdown-option-check';
            check.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';

            btn.appendChild(label);
            btn.appendChild(check);
            btn.addEventListener('click', function () {
                field.value = name;
                field.dispatchEvent(new Event('input', { bubbles: true }));
                closeDropdown();
            });
            optionsEl.appendChild(btn);
        });

        dropdown.style.display = 'block';
        toggle.classList.add('is-open');
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
})();

// Report Time (Incident Description / Root Cause Analysis) auto-fills
// from Reported Date (Initial Incident Details) + Report Time (Detailed
// Incident Information) — combines "D-Mon-YYYY" + "HH:MM" into the
// "D-Mon-YYYY HH:MM" this field needs, live as either source changes.
// Same "locked once touched" rule as every other auto-fill on this page
// — EXCEPT "touched" has to mean more than e.isTrusted here: Report Time
// also has its own calendar picker (_datetime_field.html), which sets
// .value and dispatches a synthetic 'input' too (see day-click handler
// below), so isTrusted alone can't tell "typed by hand" apart from
// "picked via the calendar" — both are real user intent and both must
// count as "manually set" here, or picking a date there would get
// silently overwritten the next time Reported Date/Report Time above
// changes. Tagging THIS auto-fill's own dispatch with a CustomEvent
// detail (which a plain `new Event(...)` from the calendar picker never
// carries) is what lets the listener below tell the two apart correctly.
(function () {
    var reportedDateInput = document.querySelector('input[name="reported_date"]');
    var reportTimeInput = document.querySelector('input[name="report_time"]');
    var raiseTimeInput = document.querySelector('input[name="raise_time"]');
    if (!reportedDateInput || !reportTimeInput || !raiseTimeInput) return;

    var manuallySet = !!raiseTimeInput.value.trim();

    function refresh() {
        if (manuallySet) return;
        var date = reportedDateInput.value.trim();
        var time = reportTimeInput.value.trim();
        // Date is the anchor: shown alone once it's filled in (even
        // before Report Time is), and stays shown (with time appended
        // once that's filled in too) even if Report Time gets cleared
        // again afterward — this field only ever goes fully blank when
        // Reported Date ITSELF is empty.
        raiseTimeInput.value = date ? (time ? date + ' ' + time : date) : '';
        raiseTimeInput.dispatchEvent(new CustomEvent('input', { bubbles: true, detail: { source: 'autofill' } }));
    }

    reportedDateInput.addEventListener('input', refresh);
    reportTimeInput.addEventListener('input', refresh);
    raiseTimeInput.addEventListener('input', function (e) {
        if (!(e.detail && e.detail.source === 'autofill')) manuallySet = true;
    });
})();

// Time of Complaint auto-fills from Raise Time — copied verbatim, live,
// same "locked once touched" rule as the Export File Name auto-fill
// above: stops the moment Time of Complaint already held a value on
// page load (an existing report) or the user types into it directly.
(function () {
    var raiseTimeInput = document.querySelector('input[name="raise_time"]');
    var complaintTimeInput = document.querySelector('input[name="time_of_complaint"]');
    if (!raiseTimeInput || !complaintTimeInput) return;

    var manuallySet = !!complaintTimeInput.value.trim();

    raiseTimeInput.addEventListener('input', function () {
        if (manuallySet) return;
        complaintTimeInput.value = raiseTimeInput.value;
    });
    complaintTimeInput.addEventListener('input', function () {
        manuallySet = true;
    });
})();

// Date and Time (Root Cause Analysis – Chronology of Events / Details
// of Incident) auto-fills from Report Time too, with "(UTC+7)" appended
// — same "locked once touched" rule, same idea as Time of Complaint's
// own auto-fill right above, just with the timezone suffix this
// field's own placeholder ("...UTC+7") already calls for.
(function () {
    var raiseTimeInput = document.querySelector('input[name="raise_time"]');
    var dateTimeInput = document.querySelector('input[name="details_date_and_time"]');
    if (!raiseTimeInput || !dateTimeInput) return;

    var manuallySet = !!dateTimeInput.value.trim();

    raiseTimeInput.addEventListener('input', function () {
        if (manuallySet) return;
        var value = raiseTimeInput.value.trim();
        dateTimeInput.value = value ? value + ' (UTC+7)' : '';
    });
    dateTimeInput.addEventListener('input', function () {
        manuallySet = true;
    });
})();

// Report Time <-> Restored Time, calculated from Duration — whichever
// of these 3 fields you're NOT currently editing gets recomputed live
// from the other two: Report Time + Duration -> Restored Time, or
// Restored Time - Duration -> Report Time. Editing Duration with BOTH
// already filled recomputes Restored Time (Report Time is treated as
// the anchor — matches the usual incident timeline: you know when it
// started before you know when it was declared over).
//
// isCalculating is a re-entrancy guard, and setField() only writes (and
// only dispatches) when the value actually changes — without both, a
// change to one field recomputing a second, whose own listener then
// recomputes the first right back, would fire forever: Report+Duration
// gives Restored; Restored-Duration gives back the SAME Report value,
// which if written unconditionally would re-dispatch and loop again.
// Skipping the no-op write breaks that cycle after one harmless round
// trip instead of hanging the page.
(function () {
    var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var reportTimeInput = document.querySelector('input[name="raise_time"]');
    var restoredTimeInput = document.querySelector('input[name="restored_time"]');
    var durationInput = document.querySelector('input[name="duration_of_interruption"]');
    var durationMirror = document.getElementById('irDescDuration');
    if (!reportTimeInput || !restoredTimeInput || !durationInput) return;

    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function parseDateTime(value) {
        var m = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})\s+(\d{1,2}):(\d{2})$/.exec((value || '').trim());
        if (!m) return null;
        var monthIndex = MONTHS.indexOf(m[2]);
        if (monthIndex === -1) return null;
        return new Date(Date.UTC(
            parseInt(m[3], 10), monthIndex, parseInt(m[1], 10), parseInt(m[4], 10), parseInt(m[5], 10)
        ));
    }

    function formatDateTime(d) {
        return d.getUTCDate() + '-' + MONTHS[d.getUTCMonth()] + '-' + d.getUTCFullYear() +
            ' ' + pad2(d.getUTCHours()) + ':' + pad2(d.getUTCMinutes());
    }

    function parseDurationMinutes(value) {
        var m = /(\d+)\s*hrs?\s*(\d+)\s*mins?/i.exec((value || '').trim());
        if (!m) return null;
        return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    }

    function formatDuration(totalMinutes) {
        return pad2(Math.floor(totalMinutes / 60)) + 'hrs ' + pad2(totalMinutes % 60) + 'mins';
    }

    var isCalculating = false;

    function setField(input, newValue) {
        if (input.value === newValue) return;
        input.value = newValue;
        input.dispatchEvent(new CustomEvent('input', { bubbles: true, detail: { source: 'autofill' } }));
    }

    function recalculate(edited) {
        if (isCalculating) return;
        isCalculating = true;
        try {
            var durationMin = parseDurationMinutes(durationInput.value);
            var report = parseDateTime(reportTimeInput.value);
            var restored = parseDateTime(restoredTimeInput.value);

            // Whichever field was just edited, prefer deriving Duration
            // when the OTHER time is already known too (both times known
            // is more informative than a possibly-stale Duration) —
            // only fall back to deriving the missing time from Duration
            // when the sibling time isn't filled in yet. report/restored
            // are null while either field holds an unparseable/partial
            // value (e.g. mid-typing), so every branch checks its own
            // operands are actually present before doing arithmetic on
            // them — not just which field triggered the event.
            if (edited === 'report' && report) {
                if (restored) {
                    // Clamped to 0 rather than left unset when Report
                    // Time lands AFTER Restored Time — a real report can
                    // genuinely have these out of order (see
                    // IR_SMART-IX1222_15-Sep-2026.pdf: Report Time
                    // 21:23, Restored Time 19:45, Duration shown as
                    // "00hrs 00mins"), and a negative duration makes no
                    // sense to display either way.
                    var diff1 = Math.max(0, Math.round((restored.getTime() - report.getTime()) / 60000));
                    setField(durationInput, formatDuration(diff1));
                } else if (durationMin !== null) {
                    setField(restoredTimeInput, formatDateTime(new Date(report.getTime() + durationMin * 60000)));
                }
            } else if (edited === 'restored' && restored) {
                if (report) {
                    var diff2 = Math.max(0, Math.round((restored.getTime() - report.getTime()) / 60000));
                    setField(durationInput, formatDuration(diff2));
                } else if (durationMin !== null) {
                    setField(reportTimeInput, formatDateTime(new Date(restored.getTime() - durationMin * 60000)));
                }
            } else if (edited === 'duration' && durationMin !== null) {
                if (report) {
                    setField(restoredTimeInput, formatDateTime(new Date(report.getTime() + durationMin * 60000)));
                } else if (restored) {
                    setField(reportTimeInput, formatDateTime(new Date(restored.getTime() - durationMin * 60000)));
                }
            }
        } finally {
            isCalculating = false;
        }
    }

    durationInput.addEventListener('input', function () { recalculate('duration'); });
    // The Incident Description section's own Duration field mirrors
    // duration_of_interruption's value directly (see the bidirectional
    // sync above) without dispatching 'input' on the real field — this
    // listener runs AFTER that sync (attached later, same element load
    // order), so durationInput.value is already caught up by the time
    // recalculate() reads it.
    if (durationMirror) durationMirror.addEventListener('input', function () { recalculate('duration'); });
    reportTimeInput.addEventListener('input', function () { recalculate('report'); });
    restoredTimeInput.addEventListener('input', function () { recalculate('restored'); });
})();

// Calendar-icon date pickers (_date_field.html) — clicking the icon
// opens the page's one shared custom calendar dropdown (#irCalendar,
// document.html), styled like a proper calendar card instead of each
// browser's own inconsistent native <input type="date"> UI. Picking a
// day writes "D-Mon-YYYY" (the exact style the exported report needs)
// into that field's visible text input; typing the date directly still
// works exactly as before — this is purely an added shortcut, and only
// one dropdown instance exists since only one is ever open at a time.
(function () {
    var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var MONTH_NAMES = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
    ];

    var calendar = document.getElementById('irCalendar');
    var calendarBody = document.getElementById('irCalendarBody');
    var titleEl = document.getElementById('irCalendarTitle');
    var daysEl = document.getElementById('irCalendarDays');
    var timeRow = document.getElementById('irCalendarTimeRow');
    var hourInput = document.getElementById('irCalendarHourInput');
    var minuteInput = document.getElementById('irCalendarMinuteInput');
    var ampmInput = document.getElementById('irCalendarAmPmInput');
    var cancelBtn = document.getElementById('irCalendarCancel');
    var applyBtn = document.getElementById('irCalendarApply');
    if (!calendar || !titleEl || !daysEl) return;

    var activeInput = null;
    var activeBtn = null;
    var isDatetime = false;
    var isTimeOnly = false;
    // Kept 24-hour internally no matter what the widget displays — every
    // OTHER thing on this page (auto-fill chains, the Duration
    // calculator, the exported document itself) already expects plain
    // "HH:MM" 24-hour, so only display/input needs to speak 12-hour+AM/PM.
    var selectedHour = 0, selectedMinute = 0;
    var viewYear, viewMonth, selectedDay, selectedMonth, selectedYear;

    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function nowTime() {
        var d = window.NocTime.parts();
        return pad2(d.hour) + ':' + pad2(d.minute);
    }

    function clamp(n, lo, hi) {
        return Math.max(lo, Math.min(hi, n));
    }

    function to12(hour24) {
        var h = hour24 % 12;
        return { hour12: h === 0 ? 12 : h, ampm: hour24 < 12 ? 'AM' : 'PM' };
    }

    function to24(hour12, ampm) {
        var h = hour12 % 12;
        return ampm === 'PM' ? h + 12 : h;
    }

    function refreshTimeInputs() {
        var t = to12(selectedHour);
        hourInput.value = String(t.hour12);
        minuteInput.value = pad2(selectedMinute);
        ampmInput.value = t.ampm;
    }

    function currentTime() {
        return pad2(selectedHour) + ':' + pad2(selectedMinute);
    }

    function setTime(hhmm) {
        var parts = (hhmm || '').split(':');
        selectedHour = clamp(parseInt(parts[0], 10) || 0, 0, 23);
        selectedMinute = clamp(parseInt(parts[1], 10) || 0, 0, 59);
        refreshTimeInputs();
    }

    function stepHour(dir) {
        var h = to12(selectedHour).hour12 + dir;
        if (h > 12) h = 1;
        if (h < 1) h = 12;
        selectedHour = to24(h, to12(selectedHour).ampm);
        refreshTimeInputs();
    }

    function stepMinute(dir) {
        selectedMinute = (selectedMinute + dir + 60) % 60;
        refreshTimeInputs();
    }

    function stepAmPm() {
        var t = to12(selectedHour);
        selectedHour = to24(t.hour12, t.ampm === 'AM' ? 'PM' : 'AM');
        refreshTimeInputs();
    }

    // Up/down spinner arrows (Hour/Minute/AM-PM) — see the ▲▼ buttons in
    // document.html's #irCalendarTimeRow, one shared handler dispatching
    // on data-field/data-dir instead of 6 near-identical listeners.
    Array.prototype.forEach.call(document.querySelectorAll('.ir-time-spinner-arrow'), function (btn) {
        btn.addEventListener('click', function () {
            var dir = parseInt(btn.dataset.dir, 10);
            if (btn.dataset.field === 'hour') stepHour(dir);
            else if (btn.dataset.field === 'minute') stepMinute(dir);
            else stepAmPm();
        });
    });

    // Mouse-wheel over a spinner box also steps it, same as clicking its
    // own ▲▼ arrows — a plain, expected shortcut for a number spinner
    // that the reference design's tiny arrow buttons alone don't rule
    // out. { passive: false } + preventDefault() so scrolling over the
    // popup steps the value instead of scrolling the page underneath it.
    function attachWheelStep(input, onStep) {
        input.parentElement.addEventListener('wheel', function (e) {
            e.preventDefault();
            onStep(e.deltaY < 0 ? 1 : -1);
        }, { passive: false });
    }
    attachWheelStep(hourInput, stepHour);
    attachWheelStep(minuteInput, stepMinute);
    attachWheelStep(ampmInput, function () { stepAmPm(); });

    // Typing a value directly still works too — digits only while
    // typing (so a single "1" on the way to "12" isn't clamped away
    // mid-keystroke), clamped into range and folded back into
    // selectedHour/selectedMinute once the field loses focus.
    hourInput.addEventListener('input', function () {
        hourInput.value = hourInput.value.replace(/\D/g, '').slice(0, 2);
    });
    hourInput.addEventListener('blur', function () {
        var h12 = clamp(parseInt(hourInput.value, 10) || 12, 1, 12);
        selectedHour = to24(h12, to12(selectedHour).ampm);
        refreshTimeInputs();
    });
    minuteInput.addEventListener('input', function () {
        minuteInput.value = minuteInput.value.replace(/\D/g, '').slice(0, 2);
    });
    minuteInput.addEventListener('blur', function () {
        selectedMinute = clamp(parseInt(minuteInput.value, 10) || 0, 0, 59);
        refreshTimeInputs();
    });

    function parseFieldValue(value) {
        var m = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/.exec((value || '').trim());
        if (!m) return null;
        var monthIndex = MONTHS.indexOf(m[2]);
        if (monthIndex === -1) return null;
        return {
            day: parseInt(m[1], 10),
            month: monthIndex,
            year: parseInt(m[3], 10),
            time: m[4] ? pad2(parseInt(m[4], 10)) + ':' + m[5] : null,
        };
    }

    function render() {
        titleEl.textContent = MONTH_NAMES[viewMonth] + ' ' + viewYear;
        daysEl.innerHTML = '';

        var firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
        var daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
        var prevMonth = viewMonth === 0 ? 11 : viewMonth - 1;
        var prevYear = viewMonth === 0 ? viewYear - 1 : viewYear;
        var daysInPrevMonth = new Date(prevYear, prevMonth + 1, 0).getDate();

        // Leading/trailing days from adjacent months, muted and
        // non-interactive — matches the reference design's grayed
        // "30 31 ... 1 2 3" fill instead of blank grid cells.
        for (var i = 0; i < firstWeekday; i++) {
            var lead = document.createElement('span');
            lead.className = 'ir-calendar-day is-outside-month';
            lead.textContent = String(daysInPrevMonth - firstWeekday + i + 1);
            daysEl.appendChild(lead);
        }

        for (var day = 1; day <= daysInMonth; day++) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = String(day);
            btn.className = 'ir-calendar-day';
            if (day === selectedDay && viewMonth === selectedMonth && viewYear === selectedYear) {
                btn.classList.add('is-selected');
            }
            btn.addEventListener('click', (function (pickedDay) {
                return function (e) {
                    // render() below rebuilds every day button, including
                    // this one — without stopping propagation here FIRST,
                    // the click event is still bubbling toward document's
                    // outside-click-closer (below) when it fires, but by
                    // then this button has already been REMOVED from the
                    // DOM by render(), so calendar.contains(e.target)
                    // wrongly comes back false for a now-detached node —
                    // read as "clicked outside the popup" and silently
                    // closed it, discarding the pick before Apply could
                    // ever use it. Confirmed live: picking a day always
                    // closed the popup immediately, even in datetime mode
                    // where it's supposed to stay open for the time too.
                    e.stopPropagation();
                    selectedDay = pickedDay;
                    selectedMonth = viewMonth;
                    selectedYear = viewYear;
                    // Staged only — nothing reaches the field until
                    // Apply (or is thrown away by Cancel/Escape/outside
                    // click/scroll, all of which just close() below).
                    render();
                };
            })(day));
            daysEl.appendChild(btn);
        }

        var trailing = (7 - ((firstWeekday + daysInMonth) % 7)) % 7;
        for (var t = 1; t <= trailing; t++) {
            var trail = document.createElement('span');
            trail.className = 'ir-calendar-day is-outside-month';
            trail.textContent = String(t);
            daysEl.appendChild(trail);
        }
    }

    function positionNear(btn) {
        calendar.hidden = false;
        var rect = btn.getBoundingClientRect();
        calendar.style.top = (window.scrollY + rect.bottom + 4) + 'px';
        calendar.style.left = (window.scrollX + rect.right - calendar.offsetWidth) + 'px';
    }

    function open(btn) {
        activeBtn = btn;
        var dateWrap = btn.closest('.ir-date-field');
        var timeWrap = !dateWrap ? btn.closest('.ir-time-field') : null;
        var wrap = dateWrap || timeWrap;
        if (!wrap) return;

        isDatetime = !!(dateWrap && dateWrap.hasAttribute('data-datetime'));
        isTimeOnly = !!timeWrap;

        // Chronology events' own Time field (event_time) is plain
        // "HH:MM" with no date attached (event_date is its own separate
        // field right next to it) — the day grid/month nav have nothing
        // to do here, so this mode hides calendarBody entirely and shows
        // only the time row, writing straight into the field with no
        // date prefix at all.
        if (isTimeOnly) {
            activeInput = wrap.querySelector('.ir-time-only-text');
            if (!activeInput) return;
            if (calendarBody) calendarBody.hidden = true;
            if (timeRow) timeRow.hidden = false;
            setTime(activeInput.value.trim() || nowTime());
            positionNear(btn);
            return;
        }
        if (calendarBody) calendarBody.hidden = false;

        activeInput = wrap.querySelector('.ir-date-text');
        if (!activeInput) return;

        if (timeRow) timeRow.hidden = !isDatetime;

        var parsed = parseFieldValue(activeInput.value);
        if (!parsed) {
            var today = window.NocTime.parts();
            parsed = { day: today.day, month: (today.month - 1), year: today.year, time: null };
        }
        viewYear = parsed.year;
        viewMonth = parsed.month;
        selectedDay = parsed.day;
        selectedMonth = parsed.month;
        selectedYear = parsed.year;
        if (isDatetime) setTime(parsed.time || nowTime());
        render();

        positionNear(btn);
    }

    // Abandons whatever was picked in the popup since it opened — used
    // by Cancel, Escape, an outside click, and scrolling away. Nothing
    // was ever written to the field mid-selection (see render()'s day
    // click and the spinner handlers above), so there's nothing to undo
    // — this just closes without ever touching activeInput.
    function close() {
        calendar.hidden = true;
        activeInput = null;
        activeBtn = null;
    }

    // The only path that actually writes to the field — everything
    // above this point only updates the popup's own staged state.
    function applyAndClose() {
        if (activeInput) {
            if (isTimeOnly) {
                activeInput.value = currentTime();
            } else {
                var dateText = selectedDay + '-' + MONTHS[selectedMonth] + '-' + selectedYear;
                activeInput.value = isDatetime ? dateText + ' ' + currentTime() : dateText;
            }
            // Setting .value directly doesn't fire a real input event on
            // its own — dispatch one so every auto-fill chain and the
            // Chronology date preview pick it up the same way they would
            // from typing the value by hand.
            activeInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        close();
    }

    if (cancelBtn) cancelBtn.addEventListener('click', function (e) { e.stopPropagation(); close(); });
    if (applyBtn) applyBtn.addEventListener('click', function (e) { e.stopPropagation(); applyAndClose(); });

    // RE-positions the popup on scroll instead of closing it — this
    // page's actual scrolling happens inside .main-wrapper (layout.css's
    // own overflow-y:auto container, not the window/body — see
    // base.html's own note on this), but the popup is positioned with
    // window.scrollY at open() time and never rechecked afterward —
    // position:absolute doesn't move with an ANCESTOR's own scroll the
    // way it would with the window's, so scrolling .main-wrapper used to
    // leave it stuck in place, detached from its button. Previously this
    // just closed the popup on any scroll, which meant a picker opened
    // near the bottom of a short viewport could never be scrolled into
    // full view — recomputing its position here (same positionNear()
    // open() itself uses) keeps it correctly anchored to its field
    // instead, so the page can be scrolled freely with the picker still
    // open. 'scroll' doesn't bubble, so this needs capture:true to see
    // it fire on .main-wrapper (or anywhere else) on the way down — same
    // reasoning graph_cards.js uses for its own capture:true listener.
    document.addEventListener(
        'scroll',
        function (e) {
            if (!calendar.hidden && activeBtn && !calendar.contains(e.target)) positionNear(activeBtn);
        },
        true
    );

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.ir-date-pick-btn');
        if (btn) {
            e.stopPropagation();
            var fieldWrap = btn.closest('.ir-date-field') || btn.closest('.ir-time-field');
            var fieldInput = fieldWrap && fieldWrap.querySelector('.ir-date-text, .ir-time-only-text');
            if (!calendar.hidden && activeInput === fieldInput) {
                close();
            } else {
                open(btn);
            }
            return;
        }
        var nav = e.target.closest('.ir-calendar-nav');
        if (nav) {
            viewMonth += parseInt(nav.getAttribute('data-dir'), 10);
            if (viewMonth < 0) { viewMonth = 11; viewYear -= 1; }
            else if (viewMonth > 11) { viewMonth = 0; viewYear += 1; }
            // Keeps the staged selection following the browsed month —
            // same day number, clamped if the new month has fewer days
            // (e.g. 31st -> February's 28th/29th). Without this, Prev/
            // Next only changed what the grid displayed; the actual
            // staged selection stayed on whatever day/month was picked
            // (or defaulted to) when the popup opened, so Apply after
            // navigating months with no day click silently reapplied
            // that stale date instead of the month you'd navigated to.
            selectedDay = Math.min(selectedDay, new Date(viewYear, viewMonth + 1, 0).getDate());
            selectedMonth = viewMonth;
            selectedYear = viewYear;
            render();
            return;
        }
        // An outside click abandons the selection too — same reasoning
        // as Cancel/scroll-close above.
        if (!calendar.hidden && !calendar.contains(e.target)) {
            close();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !calendar.hidden) close();
    });
})();

// Chronology "Date and Time" headers (document.html) — mirrors the
// SAME day-grouping build_docx() does at export time AND the server's
// own annotate_chronology_events_with_headers() (incident_report_
// service.py, used for the initial page render): starts from
// "Incident Date", then shows one more "Date and Time: <date>" header
// for every chronology event whose own date differs from the running
// day (in row order) — INLINE, directly above the first event row of
// each day's group, not as a single line pinned above the whole list
// regardless of how many different days the events actually span.
// Recomputed from scratch on every change rather than diffed, since
// a single date edit partway through the list can ripple forward
// (every later header depends on the running day up to that point),
// and the full list is small enough that this is cheap either way.
(function () {
    var incidentDateInput = document.querySelector('input[name="incident_date"]');
    var eventRows = document.getElementById('irEventRows');
    if (!incidentDateInput || !eventRows) return;

    var MONTH_INDEX = {
        Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06',
        Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12'
    };

    // Same "date then time, ascending; unparseable/blank sorts last"
    // rule as incident_report_service.py's own _event_sort_key() — a
    // plain "YYYY-MM-DD HH:MM" string sorts correctly lexically, so
    // there's no need for real Date parsing here, just reformatting.
    function eventSortKey(dateStr, timeStr) {
        var d = /^(\d{1,2})-([A-Za-z]{3})-(\d{4})$/.exec((dateStr || '').trim());
        var t = /^(\d{1,2}):(\d{2})$/.exec((timeStr || '').trim());
        if (!d || !t || !MONTH_INDEX[d[2]]) return '9999-99-99 99:99';
        var day = d[1].length === 1 ? '0' + d[1] : d[1];
        var hour = t[1].length === 1 ? '0' + t[1] : t[1];
        return d[3] + '-' + MONTH_INDEX[d[2]] + '-' + day + ' ' + hour + ':' + t[2];
    }

    // Reorders the actual rows in the DOM to match save-time order —
    // requested: typing events out of date order (e.g. 27th, 28th,
    // 27th, 28th) left the SAME date showing as a header more than
    // once, scattered through the list, instead of once with every
    // one of its events grouped underneath — because refresh() below
    // only looks at each row's IMMEDIATE neighbor, it can't fix that
    // on its own; the rows themselves have to actually be in order
    // first. appendChild on a node already in the document MOVES it
    // (doesn't clone it), so this is a plain stable re-sort, not a
    // rebuild — every row's own listeners/typed values survive untouched.
    function sortEventRows() {
        var rows = Array.prototype.slice.call(eventRows.querySelectorAll('.ir-event-row'));
        rows.sort(function (a, b) {
            var ka = eventSortKey(
                a.querySelector('input[name="event_date"]').value,
                a.querySelector('input[name="event_time"]').value
            );
            var kb = eventSortKey(
                b.querySelector('input[name="event_date"]').value,
                b.querySelector('input[name="event_time"]').value
            );
            return ka < kb ? -1 : ka > kb ? 1 : 0;
        });
        rows.forEach(function (row) { eventRows.appendChild(row); });
    }

    function refresh() {
        eventRows.querySelectorAll('.ir-chronology-header').forEach(function (h) { h.remove(); });

        var rows = eventRows.querySelectorAll('.ir-event-row');
        if (!rows.length) return;

        var currentDay = incidentDateInput.value.trim();
        rows.forEach(function (row, i) {
            var dateInput = row.querySelector('input[name="event_date"]');
            var eventDate = dateInput ? dateInput.value.trim() : '';
            var headerDate = null;
            if (i === 0) {
                headerDate = eventDate || currentDay;
                if (eventDate) currentDay = eventDate;
            } else if (eventDate && eventDate !== currentDay) {
                headerDate = eventDate;
                currentDay = eventDate;
            }
            if (headerDate) {
                // Built with createElement/textContent, not innerHTML
                // string concatenation — headerDate comes straight from
                // a free-text field (event_date), so a raw '+' into
                // innerHTML would let something like "<img onerror=...>"
                // typed into that field execute instead of just
                // displaying as text. textContent never parses its
                // input as markup, so this is safe regardless of what
                // was typed.
                var header = document.createElement('p');
                header.className = 'ir-fixed-line ir-chronology-header';
                header.appendChild(document.createTextNode('Date and Time: '));
                var dateSpan = document.createElement('span');
                dateSpan.className = 'ir-fixed-line-date';
                dateSpan.textContent = headerDate;
                header.appendChild(dateSpan);
                row.insertAdjacentElement('beforebegin', header);
            }
        });
    }

    incidentDateInput.addEventListener('input', refresh);
    // Delegated (not bound per-row) since rows are added/removed freely
    // — this alone also covers a new row's date changing after "Add
    // Event"/the per-row "+" insert adds it (see those handlers further
    // up this file, which don't need to call refresh() themselves for
    // that reason).
    eventRows.addEventListener('input', function (e) {
        if (e.target.name === 'event_date') refresh();
    });

    // Re-sorts the ROWS THEMSELVES once a date/time value is actually
    // done changing. TWO paths set these fields, and they need two
    // different triggers:
    //   - Typing by hand: only 'focusout' (below) should sort — doing
    //     it on every keystroke would yank the row (and the field the
    //     user is actively typing in) to a new position under their
    //     cursor mid-type.
    //   - The calendar/clock picker (applyAndClose() above): clicking
    //     a day/applying a time sets .value and dispatches a plain
    //     'input' event, but NEVER actually focuses the text field
    //     itself (the click target is the picker's own popup, not the
    //     input) — so 'focusout' never fires for a picker-driven
    //     change at all. Confirmed live: picking dates entirely through
    //     the picker (27, 28, 30, then 29) left 30 sitting above 29,
    //     unsorted, because the only wired trigger (focusout) never
    //     saw it. Debouncing the SAME 'input' event this already
    //     listens to above covers the picker (whose one dispatched
    //     event settles after the debounce) without reordering mid-
    //     keystroke for manual typing (each new keystroke's 'input'
    //     resets the timer, so it only fires once typing actually
    //     pauses).
    var sortDebounce = null;
    eventRows.addEventListener('input', function (e) {
        if (e.target.name !== 'event_date' && e.target.name !== 'event_time') return;
        if (sortDebounce) clearTimeout(sortDebounce);
        sortDebounce = setTimeout(function () {
            sortDebounce = null;
            sortEventRows();
            refresh();
        }, 600);
    });
    eventRows.addEventListener('focusout', function (e) {
        if (e.target.name === 'event_date' || e.target.name === 'event_time') {
            if (sortDebounce) {
                clearTimeout(sortDebounce);
                sortDebounce = null;
            }
            sortEventRows();
            refresh();
        }
    });
    // 'click' (not 'input') because removing a row, or inserting/adding
    // one, doesn't fire any input event on its own — this fires on the
    // way down to whichever button was clicked, after that row's own
    // handler has already added/removed it (inline onclick on server-
    // rendered remove buttons, and every other handler in this file,
    // all run before this bubbles up), so by the time refresh() runs
    // here the row list is already in its new shape.
    eventRows.addEventListener('click', function (e) {
        if (e.target.closest('.ir-event-remove, .ir-event-insert')) refresh();
    });
    document.getElementById('irAddEvent') && document.getElementById('irAddEvent').addEventListener('click', refresh);

    // Initial render — a saved report's events already come back
    // chronologically sorted (see _event_sort_key(), applied on every
    // save) and the server already sends header_date-annotated rows
    // (see document.html) to match, so sortEventRows() here is just a
    // safety net, not expected to actually move anything on a normal
    // load. refresh() still needs to run once either way so later edits
    // have a correct DOM state to diff from, and so a page with zero
    // saved events (nothing for the server to annotate) gets its first
    // header as soon as "Add Event" adds the first row.
    sortEventRows();
    refresh();
})();

// Incident Number/Duration — editable in every table the exported
// report reuses them in ("Detailed Incident Information", "Incident
// Description / Root Cause Analysis", and — for Incident Number only —
// "Root Cause Analysis – Chronology of Events"'s own "Details of
// Incident" mini-table, see document.html). Only the first of each
// group carries a `name` attribute (what actually posts to the server)
// — every other one is a real, freely editable input too, just kept
// live-synced to it instead of submitting its own copy. Grouped (not
// simple pairs) because Incident Number now has TWO mirrors: typing
// into either one has to reach the OTHER mirror as well, not just the
// canonical field, so updating the canonical always re-syncs every
// mirror in its group.
(function () {
    // Incident Number always keeps its "TCT#" prefix and only accepts
    // digits after it — reapplied on every keystroke in whichever of
    // the 3 synced fields the user is actually typing into (deleting
    // the "TCT#" part, or typing a letter, gets stripped back out
    // immediately), before the sync below copies the cleaned-up value
    // to the other two.
    function sanitizeIncidentNumber(value) {
        var digits = (value || '').replace(/^TCT#/, '').replace(/\D/g, '');
        return 'TCT#' + digits;
    }

    var groups = [
        ['input[name="incident_number"]', ['#irDescIncidentNumber', '#irDetailsIncidentNumber'], sanitizeIncidentNumber],
        ['input[name="duration_of_interruption"]', ['#irDescDuration'], null],
    ];
    groups.forEach(function (group) {
        var canonical = document.querySelector(group[0]);
        if (!canonical) return;
        var mirrors = group[1]
            .map(function (sel) { return document.querySelector(sel); })
            .filter(Boolean);
        if (!mirrors.length) return;
        var sanitize = group[2];

        function syncFromCanonical() {
            mirrors.forEach(function (m) {
                if (m.value !== canonical.value) m.value = canonical.value;
            });
        }

        canonical.addEventListener('input', function () {
            if (sanitize) canonical.value = sanitize(canonical.value);
            syncFromCanonical();
        });
        mirrors.forEach(function (mirror) {
            mirror.addEventListener('input', function () {
                if (sanitize) mirror.value = sanitize(mirror.value);
                canonical.value = mirror.value;
                syncFromCanonical();
            });
        });
    });
})();

// Report Time's title — Detailed Incident Information's own select
// ("Report Time" / "Occurred Time") drives the read-only mirror's title
// in Incident Description / Root Cause Analysis, so both sections always
// show the same word. Display-only: never posted to the server, never
// saved with the report — always starts back on "Report Time" on page
// load, same as the <select>'s own default-selected option.
(function () {
    var titleSelect = document.getElementById('irReportTimeTitle');
    var mirrorTitle = document.getElementById('irDescReportTimeTitle');
    if (!titleSelect || !mirrorTitle) return;

    titleSelect.addEventListener('change', function () {
        mirrorTitle.textContent = titleSelect.value;
    });
})();

// Add or insert rows in the Smart Network report tables.
(function () {
    function buildRow(names, placeholders) {
        var tr = document.createElement('tr');
        tr.className = 'ir-smart-row';
        names.forEach(function (name, i) {
            var td = document.createElement('td');
            var input = document.createElement('input');
            input.type = 'text';
            input.name = name;
            if (placeholders[i]) input.placeholder = placeholders[i];
            td.appendChild(input);
            tr.appendChild(td);
        });
        var actionsTd = document.createElement('td');
        actionsTd.className = 'ir-smart-row-actions';
        var insertBtn = document.createElement('button');
        insertBtn.type = 'button';
        insertBtn.className = 'ir-smart-row-insert';
        insertBtn.title = 'Insert row below';
        insertBtn.innerHTML = '<i class="ti ti-plus"></i>';
        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'ir-smart-row-remove';
        removeBtn.title = 'Remove row';
        removeBtn.innerHTML = '<i class="ti ti-trash"></i>';
        removeBtn.addEventListener('click', function () { tr.remove(); });
        actionsTd.appendChild(insertBtn);
        actionsTd.appendChild(removeBtn);
        tr.appendChild(actionsTd);
        return tr;
    }

    // Per-row "+" (.ir-smart-row-insert) — same "insert directly below
    // THIS row, not just at the bottom of the table" pattern as the
    // Incident Report's own chronology events (.ir-event-insert): a
    // staff member filling in rows after the fact often needs to slot a
    // missed circuit/outage in BETWEEN two already-entered ones.
    // Delegated on the rows container rather than wired per-button, so
    // it covers both server-rendered rows and ones added here with no
    // extra wiring either way.
    function wireAddButton(buttonId, rowsContainerId, names, placeholders) {
        var btn = document.getElementById(buttonId);
        var rows = document.getElementById(rowsContainerId);
        if (!rows) return;
        if (btn) {
            btn.addEventListener('click', function () {
                rows.appendChild(buildRow(names, placeholders));
            });
        }
        rows.addEventListener('click', function (e) {
            var insertBtn = e.target.closest('.ir-smart-row-insert');
            if (!insertBtn) return;
            var clickedRow = insertBtn.closest('tr');
            if (!clickedRow) return;
            var newRow = buildRow(names, placeholders);
            clickedRow.insertAdjacentElement('afterend', newRow);
            var firstInput = newRow.querySelector('input');
            if (firstInput) firstInput.focus();
        });
    }

    wireAddButton('irAddCircuitRow', 'irCircuitsRows',
        ['circuit_customer_description', 'circuit_service', 'circuit_bandwidth', 'circuit_id'],
        ['e.g. SMART DC/DR – IPLC to SG1 via MTC', 'e.g. IPLC', 'e.g. 100G', 'e.g. MX1453-MX1454']);

    var MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];

    function monthTableFieldNames(prefix) {
        var names = [prefix + '_circuit'];
        MONTH_KEYS.forEach(function (k) { names.push(prefix + '_' + k); });
        return names;
    }

    function monthTablePlaceholders() {
        var placeholders = ['e.g. MX1453-MX1454'];
        MONTH_LABELS.forEach(function () { placeholders.push('%'); });
        return placeholders;
    }

    wireAddButton('irAddOutageRow', 'irOutageRows', monthTableFieldNames('outage'), monthTablePlaceholders());
    wireAddButton('irAddCreditRow', 'irCreditRows', monthTableFieldNames('credit'), monthTablePlaceholders());
    wireAddButton('irAddFailureRow', 'irFailureRows',
        ['react_ticket_no', 'react_circuit_id', 'react_occurred_time', 'react_smart_complain',
         'react_tct_respond', 'react_failure_to_react', 'react_sla', 'react_service_credit', 'react_note'],
        ['Ticket reference', 'Circuit from section 2', 'DD-Mon-YYYY HH:MM', 'DD-Mon-YYYY HH:MM',
         'DD-Mon-YYYY HH:MM', '00hrs 00mins', 'Pass / Fail', 'e.g. 0%', 'Complaint or response details']);
    // Section 2 is the single source for the read-only section 3 summary.
    var outageRows = document.getElementById('irOutageRows');
    var faultRows = document.getElementById('irFaultRows');
    function syncFaultSummary() {
        if (!outageRows || !faultRows) return;
        var fragment = document.createDocumentFragment();
        outageRows.querySelectorAll('tr').forEach(function (sourceRow) {
            var sourceInputs = sourceRow.querySelectorAll('input, select');
            var hasData = Array.prototype.some.call(sourceInputs, function (input) {
                return input.value.trim() !== '';
            });
            if (!hasData) return;
            var row = document.createElement('tr');
            row.className = 'ir-smart-row';
            sourceInputs.forEach(function (source) {
                var cell = document.createElement('td');
                var input = document.createElement('input');
                input.type = 'text';
                input.name = source.name.replace(/^outage_/, 'fault_');
                input.value = source.value;
                input.readOnly = true;
                input.setAttribute('aria-readonly', 'true');
                cell.appendChild(input);
                row.appendChild(cell);
            });
            fragment.appendChild(row);
        });
        faultRows.replaceChildren(fragment);
    }
    if (outageRows && faultRows) {
        outageRows.addEventListener('input', syncFaultSummary);
        outageRows.addEventListener('change', syncFaultSummary);
        new MutationObserver(syncFaultSummary).observe(outageRows, { childList: true });
        syncFaultSummary();
    }

    wireAddButton('irAddServicesOutageRow', 'irServicesOutageRows',
        ['outage_ticket_no', 'outage_circuit_id', 'outage_date_started', 'outage_date_finished',
            'outage_service', 'outage_issue_owner', 'outage_interruption', 'outage_notes'],
        ['e.g. 1979218', 'e.g. MX1453', 'e.g. 22-Sep-2026 13:30', 'e.g. 22-Sep-2026 13:55',
            'e.g. IPLC', 'e.g. TELCOTECH', 'e.g. 00hrs 25mins', 'e.g. Notes...']);
})();

// Smart Network Report — Export File Name follows Report Month live
// ("September 2027" -> "Smart Network Report_Sep 2027"), matching the
// server's own default (app/routes/incident_report.py's
// _default_smart_file_name()) so a report already shows the right
// filename the moment its month is typed, not just on next page load.
// Keeps running on every Report Month edit — a later manual edit to
// Export File Name itself is left alone until Report Month changes
// again, same "auto-fills, still freely editable" behavior as every
// other defaulted field on this form.
(function () {
    var FULL_MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    var SHORT_MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    function reportMonthToShort(text) {
        var match = /^([A-Za-z]+)(?:\s*[-\u2013/]\s*([A-Za-z]+))?\s+(\d{4})$/.exec((text || '').trim());
        if (!match) return '';
        function monthNumber(name) {
            return FULL_MONTH_NAMES.findIndex(function (full, index) {
                return full.toLowerCase() === name.toLowerCase() || SHORT_MONTH_NAMES[index].toLowerCase() === name.toLowerCase();
            });
        }
        var first = monthNumber(match[1]);
        var last = match[2] ? monthNumber(match[2]) : -1;
        if (first < 0 || match[2] && last < 0) return '';
        return SHORT_MONTH_NAMES[first] + (match[2] ? '-' + SHORT_MONTH_NAMES[last] : '') + ' ' + match[3];
    }

    var monthInput = document.querySelector('input[name="smart_report_month"]');
    var fileInput = document.querySelector('input[name="file_name"]');
    if (!monthInput || !fileInput) return;

    monthInput.addEventListener('input', function () {
        var short = reportMonthToShort(monthInput.value);
        var year = /\b(\d{4})\b/.exec(monthInput.value);
        if (year) document.querySelectorAll('.ir-smart-month-table th').forEach(function (th) {
            var match = /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}$/.exec(th.textContent.trim());
            if (match) th.textContent = match[1] + '-' + year[1].slice(-2);
        });
        fileInput.value = short ? 'Smart Network Report_' + short : 'Smart Network Report';
    });
})();

// Smart Network Report — Services Outage Report's own "Interruption"
// auto-calculates from Date Started/Date Finished the moment both
// parse (DD-Mon-YYYY HH:MM, the same format every example on this form
// already uses) — "00hrs 25mins" style, matching the real data's own
// convention exactly. Delegated on the rows container (not wired per
// row) so it covers rows added via "Add Outage Row" and the per-row
// "+" insert button with no extra wiring either way. Only overwrites
// Interruption when both dates actually parse and Finished >= Started
// — an incomplete or invalid pair leaves whatever's already typed
// there alone, rather than clobbering it with a blank/wrong value.
(function () {
    var rows = document.getElementById('irServicesOutageRows');
    if (!rows) return;


    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function parseDisplayDateTime(text) {
        return parseSmartReportDateTime(text);
    }

    function recalc(tr) {
        var startInput = tr.querySelector('input[name="outage_date_started"]');
        var endInput = tr.querySelector('input[name="outage_date_finished"]');
        var interruptionInput = tr.querySelector('input[name="outage_interruption"]');
        if (!startInput || !endInput || !interruptionInput) return;
        var start = parseDisplayDateTime(startInput.value);
        var end = parseDisplayDateTime(endInput.value);
        if (!start || !end || end < start) return;
        var totalMinutes = Math.round((end - start) / 60000);
        interruptionInput.value = pad2(Math.floor(totalMinutes / 60)) + 'hrs ' + pad2(totalMinutes % 60) + 'mins';
    }

    rows.addEventListener('input', function (e) {
        var name = e.target.name;
        if (name !== 'outage_date_started' && name !== 'outage_date_finished') return;
        var tr = e.target.closest('tr');
        if (tr) recalc(tr);
    });
})();

// Failure-to-react delay follows complaint -> response; SLA and credit remain manual.
(function () {
    var body = document.getElementById('irFailureRows');
    if (!body) return;
    function calculate(row, initial) {
        var complaint = row.querySelector('[name="react_smart_complain"]');
        var response = row.querySelector('[name="react_tct_respond"]');
        var result = row.querySelector('[name="react_failure_to_react"]');
        if (!complaint || !response || !result) return;
        if (initial && result.value.trim()) return;
        var start = parseSmartReportDateTime(complaint.value);
        var end = parseSmartReportDateTime(response.value);
        response.setCustomValidity(start && end && end < start ? 'Response must not be before the complaint time.' : '');
        if (!start || !end || end < start) {
            if (result.dataset.calculated === 'true') result.value = '';
            return;
        }
        var minutes = Math.floor((end-start) / 60000);
        result.value = String(Math.floor(minutes/60)).padStart(2,'0') + 'hrs ' + String(minutes%60).padStart(2,'0') + 'mins';
        result.dataset.calculated = 'true';
    }
    body.addEventListener('input', function (event) {
        if (event.target.matches('[name="react_smart_complain"], [name="react_tct_respond"]')) calculate(event.target.closest('tr'), false);
        if (event.target.matches('[name="react_failure_to_react"]')) delete event.target.dataset.calculated;
    });
    body.querySelectorAll('tr').forEach(function (row) { calculate(row, true); });
})();
