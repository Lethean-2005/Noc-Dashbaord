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

// Filter the current page's alarm table rows as the user types (drilldown pages).
document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('global-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', function (e) {
        const val = e.target.value.toLowerCase();
        const table = document.querySelector('.alarm-table');
        if (!table) return;
        table.querySelectorAll('tbody tr').forEach((row) => {
            if (row.classList.contains('empty-row')) return;
            row.style.display = row.textContent.toLowerCase().includes(val) ? '' : 'none';
        });
    });
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

    const SEARCH_INDEX = [
        { label: 'VVIP Site', page: '/', pageName: 'Overall Dashboard' },
        { label: 'Mentor Site', page: '/', pageName: 'Overall Dashboard' },
        { label: 'ISP POP / EZE', page: '/', pageName: 'Overall Dashboard' },
        { label: 'IP Telcotech/Cellcard', page: '/', pageName: 'Overall Dashboard' },
        { label: 'RAN Site Down', page: '/', pageName: 'Overall Dashboard' },
        { label: 'RAN Main AC Alarm', page: '/', pageName: 'Overall Dashboard' },
        { label: 'DC Low/High', page: '/', pageName: 'Overall Dashboard' },
        { label: 'RAN Tech Down', page: '/', pageName: 'Overall Dashboard' },
        { label: 'Incident', page: '/', pageName: 'Overall Dashboard' },
        { label: 'INC-WO', page: '/', pageName: 'Overall Dashboard' },
        { label: 'Incident Site Down', page: '/reports/', pageName: 'Custom Dashboard' },
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
        if (item.page === window.location.pathname) {
            findAndHighlight(item.label);
        } else {
            window.location.href = item.page + '?highlight=' + encodeURIComponent(item.label);
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
function showModal(title, message) {
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
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.badge-item').forEach(function (item) {
        item.addEventListener('click', function () {
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
            window.location.href = '/drilldown?' + params.toString();
        });
    });
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

// Confirm popup: intercept any form with data-confirm and show the styled
// dialog instead of the native browser confirm().
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        const overlay = document.getElementById('confirmOverlay');
        if (!overlay) return;
        const titleEl = document.getElementById('confirmTitle');
        const msgEl = document.getElementById('confirmMsg');
        const yesBtn = document.getElementById('confirmYes');
        const noBtn = document.getElementById('confirmNo');
        let target = null;

        document.addEventListener('submit', function (e) {
            const form = e.target.closest('form[data-confirm]');
            if (!form || form.dataset.confirmed === '1') return;
            e.preventDefault();
            target = form;
            titleEl.textContent = form.getAttribute('data-confirm-title') || 'Are you sure?';
            msgEl.textContent = form.getAttribute('data-confirm') || '';
            yesBtn.textContent = form.getAttribute('data-confirm-yes') || 'Yes, Delete!';
            noBtn.textContent = form.getAttribute('data-confirm-no') || 'No, keep it.';
            overlay.hidden = false;
            noBtn.focus();
        }, true);

        function close() { overlay.hidden = true; target = null; }
        noBtn.addEventListener('click', close);
        overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && !overlay.hidden) close();
        });
        yesBtn.addEventListener('click', function () {
            if (!target) return close();
            const form = target;
            overlay.hidden = true;
            target = null;
            form.dataset.confirmed = '1';
            if (typeof form.requestSubmit === 'function') form.requestSubmit();
            else form.submit();
            form.dataset.confirmed = '';
        });
    });
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
