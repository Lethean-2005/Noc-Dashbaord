// Performance section — SLA Compliance/Response Time/Resolution Time/
// Site-Down Duration/Top 10 Site Down/Root Cause Breakdown/Site-Down
// Root Cause — Breakdown are all real, live data now (see
// app/routes/dashboard.py's _performance_cards_context()); this file
// draws the 2 donut charts and wires up their shared Chart/Table
// toggle + duration-bucket accordion.
(function () {
    var CAT = [
        'var(--perf-cat-1)', 'var(--perf-cat-2)', 'var(--perf-cat-3)',
        'var(--perf-cat-4)', 'var(--perf-cat-5)', 'var(--perf-cat-6)', 'var(--perf-cat-7)',
    ];

    function escapeText(value) {
        var span = document.createElement('span'); span.textContent = String(value == null ? '' : value); return span.innerHTML;
    }
    var NS = 'http://www.w3.org/2000/svg';
    function svgEl(tag, attrs) {
        var el = document.createElementNS(NS, tag);
        for (var k in attrs) el.setAttribute(k, attrs[k]);
        return el;
    }

    // ---- Response Time / Resolution Time cards — "how this is
    // calculated" help modal (real overlay + centered card, not a
    // dropdown) ----
    // Own dedicated open/close per modal — app.js's showModal()/
    // closeModal() only drive the single global #custom-modal with a
    // plain message string, not this multi-section content, so this
    // doesn't touch that shared function. display:block/none mirrors
    // that same modal's own open/close mechanic (app.js), and the
    // click-outside-to-close listener follows its same pattern too.
    function initHelpModal(prefix) {
        var btn = document.getElementById(prefix + 'HelpBtn');
        var modal = document.getElementById(prefix + 'HelpModal');
        var closeBtn = document.getElementById(prefix + 'HelpClose');
        if (!btn || !modal || !closeBtn) return;

        btn.addEventListener('click', function () { modal.style.display = 'block'; });
        closeBtn.addEventListener('click', function () { modal.style.display = 'none'; });
        modal.addEventListener('click', function (e) {
            if (e.target === modal) modal.style.display = 'none';
        });
    }

    // Everything below binds DIRECTLY to specific elements (not
    // delegated on `document`) — #perfTooltip, the help-modal buttons,
    // the 2 donuts, and the SLA spotlight card. The AJAX filter
    // swap (bottom of this file) replaces the whole Performance
    // section's HTML with fresh elements sharing the same ids, so this
    // whole block is wrapped in one function and re-run after every
    // swap — otherwise only the FIRST filter click would still have
    // working help buttons/donuts/spotlight (their listeners would
    // still point at the now-removed old elements).
    function initPerformanceCards() {
        var tip = document.getElementById('perfTooltip');
        function showTip(evt, html) {
            tip.innerHTML = html;
            tip.classList.add('show');
            tip.style.left = evt.clientX + 'px';
            tip.style.top = (evt.clientY - 12) + 'px';
        }
        function hideTip() { tip.classList.remove('show'); }

        initHelpModal('responseTime');
        initHelpModal('resolutionTime');

        // Top 10 Site Down — Overtime is now a real card, server-rendered
        // directly in performance_cards.html (IncidentService.get_top_site_down())
        // via the same .expenses-row/.expenses-bar-track markup the real
        // Incident Age chart uses — no client-side sample data/JS needed here.

        // ---- Donut builder (side by side with its legend) ----
        // `data[i].category`/`.pct` (real data — see
        // get_site_down_root_cause_breakdown()/get_site_down_root_cause_
        // week_breakdown()) name the slice and its own pct directly, so
        // this never computes either itself. `drilldownScope`,
        // when given, makes each legend row a real drilldown link —
        // .badge-item/.badge-label/.badge + data-scope/data-type is
        // app.js's own global delegated click handler (see
        // performance_cards.html's header comment for the other cards
        // that already use it) — reused as-is here instead of writing a
        // second click handler, so this only opts in the category name
        // (e.g. "MW transmission failure") as data-type, never a raw
        // index that would mean nothing to that handler's drilldown URL.
        function buildDonut(containerId, data, total, drilldownScope) {
            var container = document.getElementById(containerId);
            if (!container) return;
            var size = 148, r = 58, cx = size / 2, cy = size / 2, strokeW = 20;
            var circ = 2 * Math.PI * r;
            var gapDeg = 1.4;

            var wrap = document.createElement('div');
            wrap.className = 'perf-donut-svg-wrap';
            wrap.style.width = size + 'px';
            wrap.style.height = size + 'px';

            var svg = svgEl('svg', { viewBox: '0 0 ' + size + ' ' + size, width: size, height: size, style: 'transform:rotate(-90deg)' });
            var offset = 0;
            data.forEach(function (d, i) {
                var label = d.category;
                var frac = d.count / total;
                var gapLen = (gapDeg / 360) * circ;
                var segLen = Math.max(frac * circ - gapLen, 0);
                var circle = svgEl('circle', {
                    cx: cx, cy: cy, r: r, fill: 'none',
                    stroke: CAT[i], 'stroke-width': strokeW,
                    'stroke-dasharray': segLen.toFixed(2) + ' ' + (circ - segLen).toFixed(2),
                    'stroke-dashoffset': (-offset).toFixed(2),
                    class: 'perf-donut-segment',
                });
                circle.addEventListener('mousemove', function (e) {
                    tip.replaceChildren(document.createTextNode(label), document.createElement('br'));
                    var count = document.createElement('b'); count.textContent = d.count;
                    tip.append(count, document.createTextNode(' incidents ? ' + Math.round(frac * 100) + '%'));
                    if (d.note) tip.append(document.createElement('br'), document.createTextNode(d.note));
                    tip.classList.add('show'); tip.style.left = e.clientX + 'px'; tip.style.top = (e.clientY - 12) + 'px';
                });
                circle.addEventListener('mouseleave', hideTip);
                svg.appendChild(circle);
                offset += frac * circ;
            });
            wrap.appendChild(svg);

            var center = document.createElement('div');
            center.className = 'perf-donut-center';
            center.innerHTML = '<span class="perf-donut-center-value">' + total + '</span><span class="perf-donut-center-label">Incidents</span>';
            wrap.appendChild(center);

            var legend = document.createElement('div');
            legend.className = 'perf-donut-legend';
            data.forEach(function (d, i) {
                var label = d.category;
                var pct = d.pct != null ? d.pct : Math.round((d.count / total) * 100);
                var row = document.createElement('div');
                row.className = 'perf-donut-legend-row' + (drilldownScope ? ' badge-item' : '');
                var dot = document.createElement('span');
                dot.className = 'perf-donut-legend-dot'; dot.style.background = CAT[i];
                var text = document.createElement('span');
                text.className = d.note ? 'perf-donut-legend-text' : 'perf-donut-legend-label badge-label';
                if (d.note) {
                    var name = document.createElement('span'); name.className = 'perf-donut-legend-label badge-label'; name.textContent = label;
                    var note = document.createElement('span'); note.className = 'perf-donut-legend-note'; note.textContent = d.note;
                    text.append(name, note);
                } else text.textContent = label;
                var percentage = document.createElement('span');
                percentage.className = 'perf-donut-legend-pct' + (drilldownScope ? ' badge' : '');
                percentage.textContent = pct + '%';
                if (drilldownScope) { percentage.dataset.scope = drilldownScope; percentage.dataset.type = label; }
                row.append(dot, text, percentage);
                legend.appendChild(row);
            });

            container.appendChild(wrap);
            container.appendChild(legend);
        }

        // Root Cause Breakdown + Site-Down Root Cause — Breakdown — both
        // real data now (get_site_down_root_cause_breakdown()/
        // get_site_down_root_cause_week_breakdown()), read off each
        // container's own data-* attributes instead of being baked into
        // this file, so a real background sync lands here on the very
        // next page load with no JS change needed. "Cancelled/AutoClosed" is
        // already included as a real category (see those methods' own
        // docstrings), so no separate no-cause slice/handling here.
        function buildDonutFromDataAttrs(containerId, drilldownScope) {
            var el = document.getElementById(containerId);
            if (!el) return;
            var data = [];
            try {
                data = JSON.parse(el.getAttribute('data-categories') || '[]');
            } catch (e) { data = []; }
            var total = parseInt(el.getAttribute('data-total'), 10) || 0;
            if (data.length && total) {
                buildDonut(containerId, data, total, drilldownScope);
            }
        }
        buildDonutFromDataAttrs('donutSiteDown', 'Site-Down Root Cause Week');
        buildDonutFromDataAttrs('donutAllIncidents', 'Root Cause Breakdown');

        // Top 10 Site Down — Overtime's own "By Duration" tooltip — a
        // small 2-column table (bucket label left, count right), same
        // rich #perfTooltip the 2 donuts above use (showTip()/hideTip()),
        // not the plain CSS-only .app-tooltip every other bar/badge
        // tooltip on this page uses — content:attr() can't align two
        // columns, only a real HTML tooltip can. Durations come off each
        // bar's own data-durations JSON (get_top_site_down()'s own
        // per-bar breakdown) rather than being pre-built into a string
        // server-side, so this file controls the actual row markup.
        document.querySelectorAll('.expenses-bar-site-down[data-durations]').forEach(function (bar) {
            var siteCode = bar.getAttribute('data-site-code') || '';
            var siteName = bar.getAttribute('data-site-name') || '';
            var total = parseInt(bar.getAttribute('data-total'), 10) || 0;
            var durations = [];
            try {
                durations = JSON.parse(bar.getAttribute('data-durations') || '[]');
            } catch (e) { durations = []; }

            bar.addEventListener('mousemove', function (e) {
                var siteLabel = siteCode + (siteName ? ' — ' + siteName : '');
                var html = '<div class="perf-tooltip-title">' + siteLabel + '</div>' +
                    '<table class="perf-tooltip-table"><tr><td>Total</td><td>' + total + '</td></tr>';
                durations.forEach(function (d) {
                    if (d.count > 0) {
                        html += '<tr><td>' + escapeText(d.label) + '</td><td>' + d.count + '</td></tr>';
                    }
                });
                html += '</table>';
                showTip(e, html);
            });
            bar.addEventListener('mouseleave', hideTip);
        });

        // Response Time card's own MIN/AVG/MAX table — hovering the MIN
        // or MAX row's own cell for a given week shows which real
        // incident(s) actually produced that number (requested — the
        // bare duration alone doesn't say WHICH incident to go look
        // at), and the number itself is a real link into that
        // incident's own "By Duration" drilldown row (also requested —
        // "both can click view in drilldown"). Same showTip()/
        // #perfTooltip table mechanism as the duration tooltip above;
        // data-extreme-incidents comes off dashboard.py's own
        // _response_time_min_incident_by_week()/_max_incident_by_week()
        // (one shared helper, _response_time_extreme_incident_by_week(),
        // behind both). More than one incident can tie for the exact
        // same MIN/MAX — the first (newest) is the headline row (and
        // the one the link points to), any others are summarized as a
        // "+N more" line rather than listing every one and crowding
        // the tooltip.
        document.querySelectorAll('.perf-extreme-cell[data-extreme-incidents]').forEach(function (cell) {
            var incidents = [];
            try {
                incidents = JSON.parse(cell.getAttribute('data-extreme-incidents') || '[]');
            } catch (e) { incidents = []; }
            if (!incidents.length) return;

            cell.addEventListener('mousemove', function (e) {
                var first = incidents[0];
                var html = '<div class="perf-tooltip-title">' + escapeText(first.response_display) + '</div>' +
                    '<table class="perf-tooltip-table">' +
                    '<tr><td>Incident ID</td><td>' + escapeText(first.incident_id) + '</td></tr>' +
                    '<tr><td>Category</td><td>' + escapeText(first.category) + '</td></tr>' +
                    '</table>';
                if (incidents.length > 1) {
                    html += '<div class="perf-tooltip-note">+' + (incidents.length - 1) + ' more incident(s) tied for this value</div>';
                }
                showTip(e, html);
            });
            cell.addEventListener('mouseleave', hideTip);
        });

        // SLA Compliance card's Category filter + Compare Weeks + trend
        // chart are all server-rendered now (dashboard.py's
        // _build_sla_chart_geometry()/_build_sla_compliance_context()),
        // same .campaign-*/.volume-* markup Site-Down Duration's own
        // server-rendered chart already uses — hover tooltips work via
        // plain CSS (no JS), and Compare Weeks is a plain GET form that
        // reloads the page, same as the other two cards above.
        //
        // The two pills + header week badge always render server-side for
        // the LATEST selected week — clicking a point on the trend line
        // "spotlights" that week's numbers into the pills instead, purely
        // client-side (no page reload, since a reload would also have to
        // recompute which weeks feed the trend LINE itself, and a single
        // clicked week can't draw a line on its own — see
        // _build_sla_chart_geometry()'s own ">= 2 points" note). Every
        // point already carries its own data-* attributes (dashboard.py),
        // so this is just reading them back out, not a second data source.
        (function () {
            var card = document.getElementById('slaComplianceCard');
            if (!card) return;
            var weekBadge = document.getElementById('slaComplianceWeekBadge');
            var responsePct = document.getElementById('slaComplianceResponsePct');
            var responseFrac = document.getElementById('slaComplianceResponseFrac');
            var resolutionPct = document.getElementById('slaComplianceResolutionPct');
            var resolutionFrac = document.getElementById('slaComplianceResolutionFrac');
            var legendResponsePct = document.getElementById('slaComplianceLegendResponsePct');
            var legendResolutionPct = document.getElementById('slaComplianceLegendResolutionPct');
            if (!weekBadge || !responsePct || !responseFrac || !resolutionPct || !resolutionFrac) return;

            function pctText(v) {
                return v === '' || v === null || v === undefined ? '--' : v + '%';
            }

            card.addEventListener('click', function (e) {
                var point = e.target.closest('.sla-spotlight-point');
                if (!point) return;

                card.querySelectorAll('.sla-spotlight-point.is-active').forEach(function (p) {
                    p.classList.remove('is-active');
                });
                point.classList.add('is-active');

                var d = point.dataset;
                weekBadge.textContent = d.weekLabel;
                weekBadge.title = 'Pills below show ' + d.weekLabel + ' (' + d.isoWeek + ')';
                responsePct.textContent = pctText(d.responsePct);
                responseFrac.textContent = d.responseFrac;
                resolutionPct.textContent = pctText(d.resolutionPct);
                resolutionFrac.textContent = d.resolutionFrac;
                if (legendResponsePct) legendResponsePct.textContent = pctText(d.responsePct);
                if (legendResolutionPct) legendResolutionPct.textContent = pctText(d.resolutionPct);
            });
        })();

        initHelpModal('slaCompliance');
        initHelpModal('slaPolicy');
    }

    initPerformanceCards();

    // Response Time / Resolution Time cards' "By Duration" popups — one
    // modal per week shown in each card's own MIN/AVG/MAX table
    // (responseTimeDurationModal_<iso_week> / resolutionTimeDurationModal_
    // <iso_week>, see performance_cards.html), opened by clicking that
    // week's blue header (.perf-week-link). Matched by the common
    // "DurationModal_" substring in the id, not a fixed list of card
    // names, so another card can reuse this with zero new JS — Top 10
    // Site Down — Overtime used to (one modal per bar), replaced with a
    // plain hover tooltip instead (requested — see that card's own
    // data-tooltip in performance_cards.html), so it no longer has a
    // modal of its own. Delegated on `document` (not bound directly to
    // each trigger) — this survives the AJAX filter swap below with no
    // re-wiring needed, unlike everything in initPerformanceCards() above.
    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-week-modal]');
        if (trigger) {
            var modal = document.getElementById(trigger.getAttribute('data-week-modal'));
            if (modal) modal.style.display = 'block';
            return;
        }
        var closeEl = e.target.closest('.duration-popup-close');
        if (closeEl) {
            var openModal = closeEl.closest('.modal');
            if (openModal) openModal.style.display = 'none';
            return;
        }
        if (e.target.classList && e.target.classList.contains('modal') && e.target.id.indexOf('DurationModal_') !== -1) {
            e.target.style.display = 'none';
        }
    });

    // Root Cause Breakdown / Site-Down Root Cause — Breakdown's shared
    // Chart/Table toggle — reuses .volume-day-tab-btn's own look
    // (graph_cards.css) but needs its own handler since that pattern's
    // existing one (graph_cards.js) is scoped to .closest('.modal'),
    // and neither of these cards is inside one. Scoped to .closest
    // ('.perf-card') — not a specific card id — so it works for both
    // donut cards without a second near-identical handler. Delegated on
    // `document`, same as the modal handler above, so it survives the
    // AJAX filter swap below with no re-wiring needed.
    document.addEventListener('click', function (e) {
        var viewBtn = e.target.closest('.perf-root-cause-view-toggle .volume-day-tab-btn');
        if (!viewBtn) return;
        var card = viewBtn.closest('.perf-card');
        if (!card) return;
        var view = viewBtn.getAttribute('data-view');
        card.querySelectorAll('.perf-root-cause-view-toggle .volume-day-tab-btn').forEach(function (b) {
            b.classList.toggle('is-active', b === viewBtn);
        });
        card.querySelectorAll('.perf-root-cause-view').forEach(function (p) {
            p.classList.toggle('is-active', p.getAttribute('data-view') === view);
        });
    });

    // Both cards' table view share the same category-row duration
    // accordion too — same markup/behavior as Incident Volume's own
    // .volume-category-row/.volume-duration-panel (graph_cards.js),
    // just not scoped to .closest('.modal') since neither of these
    // cards is inside one. Scoped to .closest('.perf-card'), same
    // reasoning as the toggle handler above. Delegated on `document`,
    // survives the AJAX filter swap below with no re-wiring.
    document.addEventListener('click', function (e) {
        var categoryRow = e.target.closest('.perf-card .volume-category-row');
        if (!categoryRow) return;
        var card = categoryRow.closest('.perf-card');
        if (!card) return;
        var rowBody = categoryRow.closest('tbody');
        var panel = rowBody ? rowBody.nextElementSibling : null;
        if (!panel || !panel.classList.contains('volume-duration-panel')) return;

        var wasOpen = categoryRow.classList.contains('is-open');
        card.querySelectorAll('.volume-category-row.is-open').forEach(function (row) {
            row.classList.remove('is-open');
        });
        card.querySelectorAll('.volume-duration-panel.is-visible').forEach(function (row) {
            row.classList.remove('is-visible');
        });
        if (!wasOpen) {
            categoryRow.classList.add('is-open');
            panel.classList.add('is-visible');
        }
    });

    // Performance section's own filter forms (Response Time/Resolution
    // Time/SLA Compliance's "Filter by Category", Site-Down Duration's
    // "Filter by Duration", Top Site Down's week picker) used to be a
    // plain GET reloading the WHOLE dashboard (every alarm card, both
    // graph cards, this whole section) just to update one card — same
    // fix as graph_cards.js already applies to the 3 graph cards: fetch
    // dashboard.performance_cards (this section, server-rendered from
    // the new filters) and swap it in via innerHTML instead. innerHTML
    // (not Element.replaceWith()) because this section, unlike
    // .graph-row, isn't a single root element — performance_cards.html
    // has several top-level siblings (the cards + several modals), so
    // index.html wraps the whole include in #performanceSection for
    // this to replace as one unit. Every direct-bound listener inside
    // (help modals, donuts, spotlight card) has to be re-attached to
    // the fresh elements afterward — see initPerformanceCards()'s own
    // comment for why.
    function swapPerformanceSection(search) {
        window.NocDashboardFragments.replace({
            selector: '#performanceSection', url: '/performance-cards' + search,
            search: search, onUpdated: initPerformanceCards
        });
    }

    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form.matches('#performanceSection form.date-filter-form')) return;
        e.preventDefault();
        swapPerformanceSection(window.NocDashboardFragments.searchForForm(form));
    });

    // Each filter's own "Clear" link (a plain <a>, not a form submit —
    // same .date-filter-actions convention graph_cards.js's own link
    // handler matches) needs the same AJAX-swap treatment, otherwise
    // Apply would feel instant but Clear would still reload the page.
    document.addEventListener('click', function (e) {
        var link = e.target.closest('#performanceSection .date-filter-actions a.btn-export');
        if (!link) return;
        e.preventDefault();
        swapPerformanceSection(window.NocDashboardFragments.searchForForm(link.closest('form'), true));
    });
})();
