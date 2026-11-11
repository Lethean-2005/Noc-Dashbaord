// One filter at a time, with viewport-safe popups and delegated AJAX support.
(function () {
    const selector = 'details.date-filter, details.map-status-filter';
    let pendingFrame = null;

    function panelFor(filter) {
        const panel = filter.querySelector('.date-filter-form');
        return panel && panel.matches && panel.matches('.date-filter-form') ? panel : null;
    }
    function hidePanel(filter) {
        const panel = panelFor(filter);
        if (!panel) return;
        if (panel.hasAttribute('popover')) {
            if (panel.matches(':popover-open')) panel.hidePopover();
            panel.removeAttribute('popover');
        }
        panel.classList.remove('filter-panel-floating');
        ['top', 'left', 'max-height', 'max-width'].forEach(function (name) { panel.style.removeProperty(name); });
    }
    function closeOthers(keep) {
        document.querySelectorAll(selector).forEach(function (filter) {
            if (filter !== keep && filter.open) {
                filter.open = false;
                hidePanel(filter);
            }
        });
    }
    function positionPanel(filter) {
        const panel = panelFor(filter);
        if (!panel || !filter.open || !panel.showPopover) return;
        const button = filter.querySelector('summary');
        if (!button) return;
        panel.setAttribute('popover', 'manual');
        panel.classList.add('filter-panel-floating');
        if (!panel.matches(':popover-open')) panel.showPopover();
        const anchor = button.getBoundingClientRect();
        const margin = 8, gap = 6;
        const below = window.innerHeight - anchor.bottom - gap - margin;
        const above = anchor.top - gap - margin;
        panel.style.maxWidth = Math.max(0, window.innerWidth - margin * 2) + 'px';
        panel.style.maxHeight = Math.max(80, window.innerHeight - margin * 2) + 'px';
        const natural = panel.getBoundingClientRect();
        const openBelow = below >= natural.height || below >= above;
        panel.style.maxHeight = Math.max(80, openBelow ? below : above) + 'px';
        const size = panel.getBoundingClientRect();
        const left = Math.max(margin, Math.min(anchor.right - size.width, window.innerWidth - size.width - margin));
        const top = openBelow ? anchor.bottom + gap : anchor.top - size.height - gap;
        panel.style.left = left + 'px';
        panel.style.top = Math.max(margin, Math.min(top, window.innerHeight - size.height - margin)) + 'px';
    }
    function reposition() {
        if (pendingFrame !== null) return;
        pendingFrame = window.requestAnimationFrame(function () {
            pendingFrame = null;
            document.querySelectorAll(selector).forEach(function (filter) {
                if (filter.open) positionPanel(filter);
            });
        });
    }
    document.addEventListener('click', function (event) {
        const target = event.target;
        const filter = target && target.closest ? target.closest(selector) : null;
        closeOthers(filter);
    }, true);
    document.addEventListener('toggle', function (event) {
        const filter = event.target;
        if (!filter || !filter.matches || !filter.matches(selector)) return;
        if (filter.open) {
            closeOthers(filter);
            positionPanel(filter);
        } else hidePanel(filter);
    }, true);
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        const openFilter = Array.from(document.querySelectorAll(selector)).find(function (filter) { return filter.open; });
        if (!openFilter) return;
        closeOthers(null);
        const summary = openFilter.querySelector('summary');
        if (summary) summary.focus();
        event.preventDefault();
    });
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', function (event) {
        if (event.target.closest && event.target.closest('.date-filter-form')) return;
        reposition();
    }, true);
})();
