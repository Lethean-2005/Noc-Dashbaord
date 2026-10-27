// Global dashboard chrome: clock, sidebar collapse, theme toggle, fullscreen,
// and a plain client-side filter for the current page's cards/table.
// No data fetching lives here — pages load their own data server-side.

(function () {
    function updateClock() {
        const el = document.getElementById('clock');
        if (!el) return;
        const now = new Date();
        const opts = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
        el.textContent = new Intl.DateTimeFormat('en-US', opts).format(now);
    }
    updateClock();
    setInterval(updateClock, 1000);
})();

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const mainWrapper = document.getElementById('main-wrapper');

    if (window.innerWidth <= 900) {
        // .collapsed (the desktop icon-only width) is unrelated to the
        // mobile slide-out drawer, but the sidebar carries it by default
        // (or from a saved desktop preference) — always clear it here so
        // the mobile drawer shows the full sidebar (logo, nav labels)
        // instead of the narrow 60px collapsed strip.
        sidebar.classList.remove('collapsed');
        sidebar.classList.toggle('open');
        backdrop.classList.toggle('open');
    } else {
        const isCollapsed = sidebar.classList.toggle('collapsed');
        mainWrapper.classList.toggle('sidebar-collapsed', isCollapsed);
        localStorage.setItem('sidebar-collapsed', isCollapsed ? 'true' : 'false');
        updateSidebarToggleIcon();
    }
}

function updateSidebarToggleIcon() {
    const sidebar = document.getElementById('sidebar');
    const icon = sidebar && sidebar.querySelector('.sidebar-toggle-btn i');
    if (!icon) return;
    const collapsed = sidebar.classList.contains('collapsed');
    icon.className = 'ti ' + (collapsed ? 'ti-layout-sidebar-left-expand' : 'ti-layout-sidebar-left-collapse');
}
updateSidebarToggleIcon();

// Native browser fullscreen — sidebar stays visible, and a refresh
// returns to normal (the browser drops fullscreen on reload).
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
    } else {
        document.exitFullscreen().catch(() => {});
    }
}
document.addEventListener('fullscreenchange', function () {
    const icon = document.querySelector('button[title="Fullscreen"] i');
    if (icon) icon.className = 'ti ' + (document.fullscreenElement ? 'ti-minimize' : 'ti-maximize');
});

// Dashboard card search — searches across BOTH pages that have cards (the
// Overall dashboard at "/" and the Custom dashboard at "/reports" — yes,
// that route is named "reports" for historical reasons, but the page and
// its <title> are "Custom Dashboard"), not just whichever one you're
// currently on. Page structure is static (these cards are all hardcoded
// placeholders today, see the templates), so a fixed manifest here is
// simpler and more reliable than trying to fetch/parse a page that isn't
// even loaded. A result on the CURRENT page scrolls to + highlights it;
// a result on the OTHER page navigates there and highlights it on arrival.
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('global-search');
    const resultsBox = document.getElementById('search-results');
    if (!searchInput || !resultsBox) return;

    // Card search only makes sense on the two pages that actually have
    // cards (Overall "/" and Custom "/reports/"). Everywhere else — the
    // drilldown table pages especially — the same #global-search input
    // should only run the table-row filter above, not also open a card
    // results dropdown searching pages the user isn't even looking at.
    const CARD_SEARCH_PAGES = ['/', '/reports/'];
    if (!CARD_SEARCH_PAGES.includes(window.location.pathname)) return;

    // One icon per page (matching that page's own sidebar icon, so a search
    // result reads as "this belongs to Overall" / "this belongs to Custom"
    // at a glance) instead of a single generic icon for every result.
    const PAGE_ICONS = {
        '/': 'ti-layout-dashboard',
        '/reports/': 'ti-adjustments-minus',
    };

    // `target` is the exact .card-title/.card-section-title text
    // findAndHighlight() must match on-page — only set when it differs
    // from the user-facing `label` (e.g. the card was renamed after this
    // index was written).
    const SEARCH_INDEX = [
        { label: 'VVIP Site', page: '/', pageName: 'Overall Dashboard' },
        { label: 'Mentor Site', page: '/', pageName: 'Overall Dashboard' },
        { label: 'ISP POP / EZE', page: '/', pageName: 'Overall Dashboard', target: 'IP Ezecom' },
        { label: 'IP Telcotech/Cellcard', page: '/', pageName: 'Overall Dashboard' },
        { label: 'RAN Site Down', page: '/', pageName: 'Overall Dashboard', target: 'Site Down' },
        { label: 'RAN Main AC Alarm', page: '/', pageName: 'Overall Dashboard', target: 'Main AC Alarm' },
        { label: 'DC Low/High', page: '/', pageName: 'Overall Dashboard' },
        { label: 'RAN Tech Down', page: '/', pageName: 'Overall Dashboard', target: 'Tech Down' },
        { label: 'Incident', page: '/', pageName: 'Overall Dashboard' },
        { label: 'INC-WO', page: '/', pageName: 'Overall Dashboard' },
        { label: 'Incident Site Down', page: '/reports/', pageName: 'Custom Dashboard', target: 'Current Site Down' },
        { label: 'Alarm Site Down', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'Alarm Completely Site Down', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'Alarm Main Failure', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'INC-WO Site Down', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'Alarm DG On', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'INC-WO Resolved', page: '/reports/', pageName: 'Custom Dashboard' },
        { label: 'IT NODE', page: '/reports/', pageName: 'Custom Dashboard' },
    ];

    function findAndHighlight(label) {
        let target = null;
        document.querySelectorAll('.card-title, .card-section-title').forEach(function (el) {
            if (!target && el.textContent.trim() === label) target = el.closest('.card');
        });
        if (!target) return;
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.add('search-highlight');
        setTimeout(() => target.classList.remove('search-highlight'), 1500);
    }

    // Landed here via a cross-page search result (?highlight=<label>) —
    // jump to it once the page has settled, then clean the URL so a
    // reload/bookmark doesn't re-trigger the highlight.
    (function () {
        const params = new URLSearchParams(window.location.search);
        const toHighlight = params.get('highlight');
        if (!toHighlight) return;
        setTimeout(function () { findAndHighlight(toHighlight); }, 300);
        params.delete('highlight');
        const query = params.toString();
        window.history.replaceState({}, '', window.location.pathname + (query ? '?' + query : ''));
    })();

    function closeResults() {
        resultsBox.classList.remove('open');
        resultsBox.innerHTML = '';
    }

    function goToResult(item) {
        closeResults();
        searchInput.value = '';
        searchInput.blur();
        const target = item.target || item.label;
        if (item.page === window.location.pathname) {
            findAndHighlight(target);
        } else {
            window.location.href = item.page + '?highlight=' + encodeURIComponent(target);
        }
    }

    function renderResults(matches) {
        resultsBox.innerHTML = '';

        if (matches.length === 0) {
            const none = document.createElement('div');
            none.className = 'search-result sr-none';
            none.textContent = 'No matching cards';
            resultsBox.appendChild(none);
            resultsBox.classList.add('open');
            return;
        }

        // Group results under a header per source page (mirrors the
        // Incident/INC-WO-style section-title look via .search-result-group-label).
        const order = [];
        const groups = {};
        matches.forEach(function (item) {
            if (!groups[item.pageName]) { groups[item.pageName] = []; order.push(item.pageName); }
            groups[item.pageName].push(item);
        });

        order.forEach(function (pageName) {
            const group = document.createElement('div');
            group.className = 'search-result-group';
            const groupLabel = document.createElement('div');
            groupLabel.className = 'search-result-group-label';
            groupLabel.textContent = pageName;
            group.appendChild(groupLabel);

            groups[pageName].forEach(function (item) {
                const icon = PAGE_ICONS[item.page] || 'ti-layout-grid';
                const row = document.createElement('a');
                row.href = item.page;
                row.className = 'search-result';
                row.innerHTML =
                    '<span><i class="ti ' + icon + '"></i> ' + item.label + '</span>' +
                    '<i class="ti ti-chevron-right"></i>';
                row.addEventListener('click', function (e) {
                    e.preventDefault();
                    goToResult(item);
                });
                group.appendChild(row);
            });
            resultsBox.appendChild(group);
        });
        resultsBox.classList.add('open');
    }

    searchInput.addEventListener('input', function (e) {
        const val = e.target.value.trim().toLowerCase();
        if (!val) { closeResults(); return; }

        const matches = SEARCH_INDEX.filter(function (item) {
            return item.label.toLowerCase().includes(val);
        });
        renderResults(matches);
    });

    document.addEventListener('click', function (e) {
        if (!e.target.closest('.topbar-search')) closeResults();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeResults();
    });
});

// Action icon tooltips (.app-tooltip, see layout.css) — CSS
// :hover/:focus-visible already show the bubble on desktop; this only
// handles touch devices, which have no real hover state. One tap reveals
// the tooltip; a second tap (or a tap elsewhere) follows the link/submits
// the button as normal, and any previously-shown tooltip closes first so
// only one is ever visible at a time.
(function () {
    let openTooltip = null;

    document.addEventListener('touchstart', function (e) {
        const target = e.target.closest('.app-tooltip');
        if (openTooltip && openTooltip !== target) {
            openTooltip.classList.remove('is-touched');
            openTooltip = null;
        }
        if (!target) return;
        if (!target.classList.contains('is-touched')) {
            e.preventDefault();
            target.classList.add('is-touched');
            openTooltip = target;
        }
    }, { passive: false });
})();

// Notification modal — call showModal(title, message) from anywhere.
// Title "Success"/"Error" (case-insensitive) also picks a colored icon +
// accent (green/red) via .is-success/.is-error on .modal-content — see
// app.css. Any other title (e.g. the default "Notification") stays
// neutral, no icon.
const MODAL_STATUS_ICONS = {
    success: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/><path d="M9 12l2 2l4 -4"/></svg>',
    error: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 9v4"/><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.871l-8.106 -13.534a1.914 1.914 0 0 0 -3.274 0z"/><path d="M12 16h.01"/></svg>',
};

function showModal(title, message) {
    const content = document.querySelector('#custom-modal .modal-content');
    const icon = document.getElementById('modal-status-icon');
    const key = (title || '').trim().toLowerCase();

    content.classList.remove('is-success', 'is-error');
    icon.innerHTML = MODAL_STATUS_ICONS[key] || '';
    if (key === 'success' || key === 'error') content.classList.add('is-' + key);

    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-message').textContent = message;
    document.getElementById('custom-modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('custom-modal').style.display = 'none';
}

window.addEventListener('click', function (event) {
    const modal = document.getElementById('custom-modal');
    if (event.target === modal) closeModal();
});

// Badge drill-down: click any colored badge to open its full alarm table
// page. Live badges (data-badge-key, see cards.html) carry their own
// data-scope/data-type — the ISP POP/EZE card holds two different scopes
// under one card title, so the card title alone can't tell them apart.
// Any still-static-placeholder card's badges fall back to the card's own
// title as scope — that scope won't match a real drilldown, so it renders
// an empty table rather than real per-badge data. The fallback's page
// title used to truncate the card title to its first word before this fix
// (e.g. "Alarm Completely Site Down" + "Diamond" -> "Alarm Diamond") —
// harmless-looking but silently lossy for any multi-word title; now uses
// the full card title instead.
//
// The data-scope branch had the exact same truncation bug independently:
// `scope.split(' ')[0]` kept only scope's first word, so every RAN Status
// sub-card (data-scope "RAN Site Down" / "RAN Main AC Alarm" / "DC
// Low/High" / "RAN Tech Down") collapsed to the same first-word + label
// page title when a grade badge was clicked directly (e.g. "RAN Diamond"
// for both RAN sub-cards, losing which one) — confirmed live once the 4th
// sub-card made the ambiguity between all of them obvious. Uses the full
// scope now, same fix as the fallback branch above.
// Delegated on document (not bound per-.badge-item at DOMContentLoaded)
// so badges inside a card row swapped in later — e.g. graph_cards.js
// replacing .graph-row when a filter dropdown is applied — still work
// without needing their own rebind.
document.addEventListener('click', function (e) {
    // "Incident Age – Open"'s own worklog icon (sits right after the
    // count, inside the same .badge-item row) is the one deliberate
    // exception: clicking it opens a worklog popup (graph_cards.js's
    // own data-age-worklog-modal handler) instead of this handler's
    // usual "navigate to the drilldown table" — the count itself still
    // does that, unchanged. Bailing out here before the .badge-item
    // lookup below is what actually prevents the navigation; without
    // this guard both behaviors would fire on the same click.
    if (e.target.closest('.incident-age-worklog-icon')) return;

    const item = e.target.closest('.badge-item');
    if (!item) return;

    const badge = item.querySelector('.badge');
    const label = item.querySelector('.badge-label');
    const labelText = label ? label.textContent.trim() : '';
    const valueText = badge ? badge.textContent.trim() : '0';

    let scope, pageTitle;
    if (badge && badge.hasAttribute('data-scope')) {
        scope = badge.getAttribute('data-scope');
        pageTitle = (scope + ' ' + labelText).trim();
    } else {
        const card = item.closest('.card');
        const cardTitle = card ? card.querySelector('.card-title').textContent.trim() : '';
        scope = cardTitle;
        pageTitle = (cardTitle + ' ' + labelText).trim();
    }

    const params = new URLSearchParams({
        title: pageTitle,
        label: labelText,
        value: valueText,
        scope: scope
    });
    if (badge && badge.hasAttribute('data-type')) {
        params.set('type', badge.getAttribute('data-type'));
    }

    // Incident Volume's trend dots and Incidents Closed's trend bars are
    // both already filtered server-side by their own card's Category
    // filter (volume_category / closed_category) before this click even
    // happens — but this handler only ever knew about title/label/value/
    // scope/type, so clicking through used to silently drop that filter
    // and drill into EVERY category instead of just the one being
    // charted. Forwarding the same filter value(s) already active on
    // the current page as `category` (the exact param name both
    // scopes' own drilldown fetch already reads) keeps the drilldown
    // consistent with what the chart is actually showing.
    const categoryParamByScope = {
        'Incident Volume': 'volume_category',
        'Incidents Closed': 'closed_category',
    };
    const categoryParam = categoryParamByScope[scope];
    if (categoryParam) {
        new URLSearchParams(window.location.search).getAll(categoryParam).forEach(function (v) {
            params.append('category', v);
        });
    }

    // Top 10 Site Down / Root Cause Breakdown's own filters — site
    // cross-filter (clicking a site code on Top 10 Site Down narrows
    // Root Cause Breakdown to just that site) and Top 10 Site Down's
    // own multi-select "Filter by Week" (badge_type no longer encodes
    // the week itself — see get_top_site_down()'s own docstring for
    // why — so a bar/slice click has to carry it separately or it would
    // silently reset back to "All" on every click). Needed for BOTH
    // scopes: a Top Site Down bar click should keep whichever weeks are
    // selected, and a Root Cause Breakdown slice click should keep both
    // the site AND the weeks the pie itself is currently showing.
    if (scope === 'Top Site Down' || scope === 'Root Cause Breakdown') {
        const currentParams = new URLSearchParams(window.location.search);
        if (scope === 'Root Cause Breakdown') {
            const siteCode = currentParams.get('root_cause_site');
            if (siteCode) params.set('root_cause_site', siteCode);
        }
        currentParams.getAll('top_site_down_week').forEach(function (v) {
            params.append('top_site_down_week', v);
        });
    }

    // Site-Down Root Cause — Breakdown's own cross-filters (clicking a
    // duration bucket on "Site-Down Duration — Weekly Trend"'s x-axis,
    // or that same card's Compare Weeks selection it now follows) need
    // the same carry-through, same reasoning as root_cause_site above.
    if (scope === 'Site-Down Root Cause Week' || scope === 'Site-Down Root Cause Week Duration') {
        const currentParams = new URLSearchParams(window.location.search);
        const bucket = currentParams.get('root_cause_bucket');
        if (bucket) params.set('root_cause_bucket', bucket);
        currentParams.getAll('site_down_duration_week').forEach(function (v) {
            params.append('site_down_duration_week', v);
        });
    }

    window.location.href = '/drilldown?' + params.toString();
});

// ── Badge alert light ────────────────────────────────────────────
// Badges wired to live data carry data-badge-key (see cards.html). One
// blinks whenever its count changes to a new non-zero value — server-
// rendered on each page load/reload, so no client-side fetch is needed
// here, only a before/after comparison. State (last-seen value + whether
// an alert is pending) survives a page reload via sessionStorage, so the
// blink still shows up correctly on the next manual reload/navigation
// even though the page no longer reloads itself automatically. A count
// dropping to 0 clears the alert instead of
// blinking — that's good news, never a reason to blink. Clicking a
// blinking badge acknowledges it (turns the light off) without blocking
// the existing drill-down click handler above — this listener never
// calls preventDefault/stopPropagation.
(function () {
    const BADGE_VALS = 'badge-vals', BADGE_ALERTS = 'badge-alerts';
    const loadObj = (k) => { try { return JSON.parse(sessionStorage.getItem(k) || '{}'); } catch (e) { return {}; } };
    const saveObj = (k, o) => { try { sessionStorage.setItem(k, JSON.stringify(o)); } catch (e) {} };

    document.addEventListener('DOMContentLoaded', function () {
        const badges = document.querySelectorAll('[data-badge-key]');
        if (badges.length === 0) return;

        const vals = loadObj(BADGE_VALS);
        const alerts = loadObj(BADGE_ALERTS);
        const firstRun = Object.keys(vals).length === 0;

        badges.forEach(function (el) {
            const key = el.getAttribute('data-badge-key');
            const count = parseInt(el.textContent.trim(), 10) || 0;
            const prev = vals[key];

            if (count === 0) {
                delete alerts[key];
            } else if (!firstRun && prev !== count) {
                alerts[key] = true;
            }
            vals[key] = count;
            el.classList.toggle('badge-alert', !!alerts[key]);
        });

        saveObj(BADGE_VALS, vals);
        saveObj(BADGE_ALERTS, alerts);
    });

    document.addEventListener('click', function (e) {
        // Clicking anywhere in the badge-item (the number OR its label text)
        // dismisses the blink, not just the number badge itself.
        const item = e.target.closest('.badge-item');
        const el = item ? item.querySelector('[data-badge-key]') : e.target.closest('[data-badge-key]');
        if (!el || !el.classList.contains('badge-alert')) return;
        const alerts = loadObj(BADGE_ALERTS);
        delete alerts[el.getAttribute('data-badge-key')];
        saveObj(BADGE_ALERTS, alerts);
        el.classList.remove('badge-alert');
    });
})();

// Confirm popup: the styled dialog everything on this site uses instead
// of the native browser confirm(). Two ways in:
//   1. Any <form data-confirm="..."> — submitting it is intercepted
//      automatically (see the 'submit' listener below).
//   2. window.showConfirm(message, options) — call this directly from
//      plain JS (a button click handler, a fetch()-based delete, etc.)
//      that isn't a form submission at all; resolves true/false.
// Both share the same overlay/state — only one confirm can ever be open
// at a time, which is also all this page ever needs.
function showConfirm(message, opts) {
    opts = opts || {};
    const overlay = document.getElementById('confirmOverlay');
    if (!overlay) return Promise.resolve(window.confirm(message));

    const titleEl = document.getElementById('confirmTitle');
    const msgEl = document.getElementById('confirmMsg');
    const yesBtn = document.getElementById('confirmYes');
    const noBtn = document.getElementById('confirmNo');

    titleEl.textContent = opts.title || 'Are you sure?';
    msgEl.textContent = message || '';
    yesBtn.textContent = opts.yesLabel || 'Yes, Delete!';
    noBtn.textContent = opts.noLabel || 'No, keep it.';
    overlay.hidden = false;
    noBtn.focus();

    return new Promise(function (resolve) {
        function cleanup(result) {
            overlay.hidden = true;
            yesBtn.removeEventListener('click', onYes);
            noBtn.removeEventListener('click', onNo);
            overlay.removeEventListener('click', onOverlayClick);
            document.removeEventListener('keydown', onKeydown);
            resolve(result);
        }
        function onYes() { cleanup(true); }
        function onNo() { cleanup(false); }
        function onOverlayClick(e) { if (e.target === overlay) cleanup(false); }
        function onKeydown(e) { if (e.key === 'Escape') cleanup(false); }

        yesBtn.addEventListener('click', onYes);
        noBtn.addEventListener('click', onNo);
        overlay.addEventListener('click', onOverlayClick);
        document.addEventListener('keydown', onKeydown);
    });
}
window.showConfirm = showConfirm;

(function () {
    document.addEventListener('submit', function (e) {
        const form = e.target.closest('form[data-confirm]');
        if (!form || form.dataset.confirmed === '1') return;
        e.preventDefault();
        showConfirm(form.getAttribute('data-confirm') || '', {
            title: form.getAttribute('data-confirm-title') || 'Are you sure?',
            yesLabel: form.getAttribute('data-confirm-yes') || 'Yes, Delete!',
            noLabel: form.getAttribute('data-confirm-no') || 'No, keep it.',
        }).then(function (confirmed) {
            if (!confirmed) return;
            form.dataset.confirmed = '1';
            if (typeof form.requestSubmit === 'function') form.requestSubmit();
            else form.submit();
            form.dataset.confirmed = '';
        });
    }, true);
})();

// Theme (light / dark) — persisted in localStorage.
(function () {
    const root = document.documentElement;
    function apply(t) {
        if (t === 'dark') root.setAttribute('data-theme', 'dark');
        else root.removeAttribute('data-theme');
        const icon = document.querySelector('#topbar-theme-btn i');
        if (icon) icon.className = 'ti ' + (t === 'dark' ? 'ti-moon' : 'ti-sun');
        document.querySelectorAll('.theme-option').forEach((o) =>
            o.classList.toggle('active', o.getAttribute('data-theme-choice') === t));
    }
    let cur = 'light';
    try { cur = localStorage.getItem('dash-theme') || 'light'; } catch (e) {}
    apply(cur);

    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.getElementById('topbar-theme-btn');
        const dd = document.getElementById('theme-dropdown');
        if (!btn || !dd) return;
        btn.addEventListener('click', (e) => { e.stopPropagation(); dd.classList.toggle('open'); });
        dd.querySelectorAll('.theme-option').forEach((o) => o.addEventListener('click', () => {
            const t = o.getAttribute('data-theme-choice');
            try { localStorage.setItem('dash-theme', t); } catch (e) {}
            apply(t);
            dd.classList.remove('open');
        }));
        document.addEventListener('click', () => dd.classList.remove('open'));
    });
})();

// Row 2 (RAN Status / Incident-INC-WO) height synced to match row 1
// (VVIP/Mentor/IP Ezecom/IP Telcotech) on the Overall Dashboard. CSS Grid
// only stretches cards to equal height within the same row — row 1 and
// row 2 are separate implicit grid rows, so no CSS rule alone can make one
// match the other; this is the one part of that ask that needs a small JS
// height sync instead. No-ops on any page without .card-wide cards (e.g.
// the Reports page, which reuses .dashboard-grid but has no wide cards).
(function () {
    function syncWideCardHeight() {
        const grid = document.querySelector('.dashboard-grid');
        if (!grid) return;
        const wideCards = grid.querySelectorAll(':scope > .card-wide');
        const normalCards = grid.querySelectorAll(':scope > .card:not(.card-wide)');
        if (!wideCards.length || !normalCards.length) return;

        wideCards.forEach((c) => { c.style.minHeight = ''; });
        let rowOneHeight = 0;
        normalCards.forEach((c) => { rowOneHeight = Math.max(rowOneHeight, c.getBoundingClientRect().height); });
        wideCards.forEach((c) => { c.style.minHeight = rowOneHeight + 'px'; });
    }

    document.addEventListener('DOMContentLoaded', syncWideCardHeight);
    window.addEventListener('resize', syncWideCardHeight);
})();

// "All <Field>" master checkbox — drilldown/_category_filter.html's
// Category filter AND _field_filter.html's Severity/Province/Vendor
// filters all share this same .category-filter-options/
// .category-filter-all-checkbox markup, just with a different real
// checkbox `name` per field. Checking the master checks every real
// value checkbox in that same dropdown at once (and unchecking it
// unchecks them all); checking/unchecking an individual value box in
// turn keeps the master box in sync (checked only once every real box
// is checked, OR none are — see the "0 or all" comment below). The
// master itself carries no `name`, so it never submits as a real
// filter value — Apply still submits exactly the individual boxes'
// own checked state, same "none checked = no filter" convention as
// before, this only saves clicking every box by hand. Matched by
// "any real checkbox in the group that isn't the master" rather than
// a specific `name`, so one handler covers all 4 fields. Delegated on
// `document` since a page can render more than one of these dropdowns
// (Incident Volume alone has 4 — Category/Severity/Province/Vendor).
document.addEventListener('change', function (e) {
    const master = e.target.closest('.category-filter-all-checkbox');
    if (master) {
        const group = master.closest('.category-filter-options');
        if (!group) return;
        group.querySelectorAll('input[type="checkbox"]:not(.category-filter-all-checkbox)').forEach(function (box) {
            box.checked = master.checked;
        });
        return;
    }

    const box = e.target.closest('.category-filter-options input[type="checkbox"]:not(.category-filter-all-checkbox)');
    if (!box) return;
    const group = box.closest('.category-filter-options');
    const masterBox = group ? group.querySelector('.category-filter-all-checkbox') : null;
    if (!masterBox) return;
    const boxes = Array.from(group.querySelectorAll('input[type="checkbox"]:not(.category-filter-all-checkbox)'));
    const checkedCount = boxes.filter(function (b) { return b.checked; }).length;
    masterBox.checked = checkedCount === 0 || checkedCount === boxes.length;
});

// Same sync as above, run once on load — covers visiting a URL with
// every value explicitly listed in the query string by hand, which
// the server-rendered master checkbox (checked only when NO value is
// selected) wouldn't otherwise reflect as "all".
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.category-filter-options').forEach(function (group) {
        const masterBox = group.querySelector('.category-filter-all-checkbox');
        const boxes = Array.from(group.querySelectorAll('input[type="checkbox"]:not(.category-filter-all-checkbox)'));
        if (!masterBox || !boxes.length) return;
        const checkedCount = boxes.filter(function (b) { return b.checked; }).length;
        // Either everything checked or nothing checked both mean "no
        // filter" server-side — only a PARTIAL selection should leave
        // the master unchecked.
        masterBox.checked = checkedCount === 0 || checkedCount === boxes.length;
    });
});
