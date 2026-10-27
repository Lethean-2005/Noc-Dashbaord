// Dashboard-only (Overall "/"). Each graph card's header dropdown (see
// graph_cards.html) is a plain GET form/link to dashboard.index — this
// intercepts both and fetches dashboard.graph_cards (the same 3-card row,
// server-rendered from the new filters) instead, swapping it in with
// Element.replaceWith() so applying a filter doesn't reload the whole
// dashboard (no flicker, no scroll-to-top). history.replaceState() keeps
// the URL in sync so a manual refresh — or the page's own periodic
// location.reload() (dashboard/index.html) — still picks up the applied
// filters.
(function () {
    function swapGraphRow(search) {
        fetch('/graph-cards' + search)
            .then((res) => res.text())
            .then((html) => {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = html.trim();
                const newRow = wrapper.firstElementChild;
                const oldRow = document.querySelector('.graph-row');
                if (!newRow || !oldRow) return;
                oldRow.replaceWith(newRow);
                window.history.replaceState(null, '', '/' + search);
            });
    }

    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!form.matches('.graph-row form.date-filter-form')) return;
        e.preventDefault();
        const params = new URLSearchParams(new FormData(form));
        const qs = params.toString();
        swapGraphRow(qs ? '?' + qs : '');
    });

    document.addEventListener('click', function (e) {
        const link = e.target.closest('.graph-row .date-filter-actions a.btn-export');
        if (!link) return;
        e.preventDefault();
        swapGraphRow(new URL(link.href).search);
    });

    // "By Category"/"By Severity"/"By Province"/"By Vendor" popups
    // (Incident Volume's week totals) — delegated for the same reason
    // as everything else in this file: the AJAX swap above replaces
    // these buttons/modals outright, so a listener bound directly to
    // today's element wouldn't survive it. One shared handler for all
    // four (matched by the "volume<X>Btn/Modal/Close" id convention)
    // instead of four near-identical blocks.
    document.addEventListener('click', function (e) {
        const openBtn = e.target.closest('[id^="volume"][id$="Btn"]');
        if (openBtn) {
            const modal = document.getElementById(openBtn.id.replace(/Btn$/, 'Modal'));
            if (modal) modal.style.display = 'block';
            return;
        }
        const closeBtn = e.target.closest('[id^="volume"][id$="Close"]');
        if (closeBtn) {
            const modal = document.getElementById(closeBtn.id.replace(/Close$/, 'Modal'));
            if (modal) modal.style.display = 'none';
            return;
        }
        if (
            e.target.classList && e.target.classList.contains('modal') &&
            e.target.id.indexOf('volume') === 0 && e.target.id.endsWith('Modal')
        ) {
            e.target.style.display = 'none';
        }
    });

    // Per-weekday Incident Volume popups (x-axis labels, one modal per
    // weekday — volumeDayCategoryModal_0..6, see graph_cards.html). Same
    // delegation reasoning as the button above.
    //
    // Only a shell (header + empty body) ships in the page for each of
    // the 7 weekdays — this fetches that ONE weekday's Category/
    // Severity/Province/Vendor tables from /volume-day-popup/<n> the
    // first time it's opened, using the SAME filters currently applied
    // to the graph cards (location.search, kept in sync by swapGraphRow()
    // above), instead of all 7 being pre-rendered on every page load.
    // modal.dataset.loaded guards against re-fetching on every re-open.
    // swapGraphRow() replaces the whole .graph-row (these shells
    // included) on every filter change, so a fresh unloaded shell always
    // comes back and the next open re-fetches — no stale-data risk from
    // caching a popup body across a filter change.
    document.addEventListener('click', function (e) {
        const dayBtn = e.target.closest('[data-day-modal]');
        if (dayBtn) {
            const modal = document.getElementById(dayBtn.getAttribute('data-day-modal'));
            if (!modal) return;
            modal.style.display = 'block';
            if (modal.dataset.loaded === '1') return;
            const dayIndex = modal.getAttribute('data-day-index');
            const body = modal.querySelector('.volume-day-popup-body');
            fetch('/volume-day-popup/' + dayIndex + location.search)
                .then((res) => res.text())
                .then((html) => {
                    body.innerHTML = html;
                    modal.dataset.loaded = '1';
                });
            return;
        }
        const closeEl = e.target.closest('.volume-day-category-close');
        if (closeEl) {
            const modal = closeEl.closest('.modal');
            if (modal) modal.style.display = 'none';
            return;
        }
        if (e.target.classList && e.target.classList.contains('modal') && e.target.id.startsWith('volumeDayCategoryModal_')) {
            e.target.style.display = 'none';
        }
    });

    // "Incident Age – Open"'s own worklog popups — one modal per age
    // bucket (incidentAgeWorklogModal_<badge_type>, see graph_cards.html
    // and IncidentService.get_worklog_by_age_bucket()), opened by
    // clicking that bucket's BAR specifically — app.js's own document
    // click handler bails out early for .incident-age-bar so clicking
    // it doesn't ALSO navigate to the drilldown table the way the
    // count next to it still does. Fully server-rendered (no fetch —
    // unlike the per-weekday popups above, every bucket's worklog is
    // small enough to ship inline), so opening is just a display swap.
    // The X close button is handled generically by performance.js's
    // own .duration-popup-close delegation; only the "click the
    // backdrop to close" case needs its own id-scoped check here.
    document.addEventListener('click', function (e) {
        const trigger = e.target.closest('[data-age-worklog-modal]');
        if (trigger) {
            const modal = document.getElementById(trigger.getAttribute('data-age-worklog-modal'));
            if (modal) modal.style.display = 'block';
            return;
        }
        if (
            e.target.classList && e.target.classList.contains('modal') &&
            e.target.id.indexOf('incidentAgeWorklogModal_') === 0
        ) {
            e.target.style.display = 'none';
        }
    });

    // Category/Severity/Province/Vendor tabs inside each per-weekday
    // popup above — all 4 fields are already rendered server-side (see
    // graph_cards.html), so switching tabs is just a class toggle
    // scoped to that one popup (closest('.modal')), no re-fetch.
    document.addEventListener('click', function (e) {
        const tabBtn = e.target.closest('.volume-day-tab-btn');
        if (!tabBtn) return;
        const modal = tabBtn.closest('.modal');
        if (!modal) return;
        const tab = tabBtn.getAttribute('data-tab');
        modal.querySelectorAll('.volume-day-tab-btn').forEach(function (b) {
            b.classList.toggle('is-active', b === tabBtn);
        });
        modal.querySelectorAll('.volume-day-tab-panel').forEach(function (p) {
            p.classList.toggle('is-active', p.getAttribute('data-tab') === tab);
        });
    });

    // Every category row in the popup above expands its own duration
    // panel beneath it (every category has real duration data — see
    // graph_cards.html/incident_service.py). The panel is a sibling
    // <tbody> (not the row's own next row) — see graph_cards.css's own
    // note on why duration rows live in the outer table's row grid
    // instead of a nested <table>. Accordion, not independent toggles:
    // opening one closes whichever other row was open in THIS SAME
    // modal (closest('.modal')) — two expanded at once made the popup
    // scroll awkwardly tall for no reason.
    document.addEventListener('click', function (e) {
        const categoryRow = e.target.closest('.volume-category-row');
        if (!categoryRow) return;
        const modal = categoryRow.closest('.modal');
        if (!modal) return;
        const rowBody = categoryRow.closest('tbody');
        const panel = rowBody ? rowBody.nextElementSibling : null;
        if (!panel || !panel.classList.contains('volume-duration-panel')) return;

        const wasOpen = categoryRow.classList.contains('is-open');
        modal.querySelectorAll('.volume-category-row.is-open').forEach(function (row) {
            row.classList.remove('is-open');
        });
        modal.querySelectorAll('.volume-duration-panel.is-visible').forEach(function (row) {
            row.classList.remove('is-visible');
        });
        if (!wasOpen) {
            categoryRow.classList.add('is-open');
            panel.classList.add('is-visible');
        }
    });

    // Cards 2/3 each have TWO side-by-side dropdowns (Category + Compare
    // Weeks, both .date-filter inside one .graph-filters wrapper — see
    // graph_cards.html). <details> has no built-in mutual exclusion, so
    // without this opening the 2nd while the 1st is still open leaves both
    // open, overlapping. Same fix as map-view.js's statusFilterDetails/
    // ispFilterDetails pair. Delegated on `document` with capture:true (the
    // 3rd argument) — 'toggle' doesn't bubble, but capture still sees it on
    // the way down regardless — so this keeps working after graph_cards.js's
    // own AJAX swap replaces the row with fresh <details> elements, no
    // rebinding needed.
    document.addEventListener(
        'toggle',
        function (e) {
            const details = e.target;
            if (!details.matches || !details.matches('.graph-row .date-filter') || !details.open) return;
            const group = details.closest('.graph-filters');
            if (!group) return;
            group.querySelectorAll(':scope > details.date-filter').forEach((other) => {
                if (other !== details) other.open = false;
            });
        },
        true
    );
})();
