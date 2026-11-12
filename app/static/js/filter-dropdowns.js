// One filter at a time, with viewport-safe popups and delegated AJAX support.
(function () {
    const selector = 'details.date-filter, details.map-status-filter';
    let pendingFrame = null;
    let activeFilter = null;
    let panelSizes = new WeakMap();

    function panelFor(filter) {
        const panel = filter.querySelector('.date-filter-form');
        return panel && panel.matches && panel.matches('.date-filter-form') ? panel : null;
    }
    function hidePanel(filter) {
        const panel = panelFor(filter);
        if (!panel) return;
        panelSizes.delete(panel);
        if (panel.hasAttribute('popover')) {
            if (panel.matches(':popover-open')) panel.hidePopover();
            panel.removeAttribute('popover');
        }
        panel.classList.remove('filter-panel-floating');
        ['top', 'left', 'max-height', 'max-width'].forEach(function (name) { panel.style.removeProperty(name); });
    }
    function closeOthers(keep) {
        if (activeFilter !== keep) activeFilter = null;
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
        let natural = panelSizes.get(panel);
        if (!natural) {
            panel.style.maxWidth = Math.max(0, window.innerWidth - margin * 2) + 'px';
            panel.style.maxHeight = Math.max(80, window.innerHeight - margin * 2) + 'px';
            const measured = panel.getBoundingClientRect();
            natural = {width: measured.width, height: measured.height};
            panelSizes.set(panel, natural);
        }
        const openBelow = below >= natural.height || below >= above;
        const availableHeight = Math.max(80, openBelow ? below : above);
        panel.style.maxHeight = availableHeight + 'px';
        const size = {width: natural.width, height: Math.min(natural.height, availableHeight)};
        const left = Math.max(margin, Math.min(anchor.right - size.width, window.innerWidth - size.width - margin));
        const top = openBelow ? anchor.bottom + gap : anchor.top - size.height - gap;
        panel.style.left = left + 'px';
        panel.style.top = Math.max(margin, Math.min(top, window.innerHeight - size.height - margin)) + 'px';
    }
    function reposition() {
        if (!activeFilter || !activeFilter.open || !activeFilter.isConnected || pendingFrame !== null) return;
        pendingFrame = window.requestAnimationFrame(function () {
            pendingFrame = null;
            if (activeFilter && activeFilter.isConnected) positionPanel(activeFilter);
        });
    }
    function closeFilter(filter) {
        if (!filter) return;
        filter.open = false;
        hidePanel(filter);
        if (activeFilter === filter) activeFilter = null;
    }
    document.addEventListener('click', function (event) {
        const target = event.target;
        const filter = target && target.closest ? target.closest(selector) : null;
        closeOthers(filter);
        if (filter && target.closest('.date-filter-actions a')) closeFilter(filter);
    }, true);
    document.addEventListener('toggle', function (event) {
        const filter = event.target;
        if (!filter || !filter.matches || !filter.matches(selector)) return;
        if (filter.open) {
            closeOthers(filter);
            activeFilter = filter;
            positionPanel(filter);
        } else {
            hidePanel(filter);
            if (activeFilter === filter) activeFilter = null;
        }
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
    document.addEventListener('submit', function (event) {
        const filter = event.target.closest && event.target.closest(selector);
        closeFilter(filter);
    }, true);
    function invalidatePanelSize(event) {
        if (!activeFilter || !activeFilter.contains(event.target)) return;
        const panel = panelFor(activeFilter);
        if (panel) panelSizes.delete(panel);
        reposition();
    }
    document.addEventListener('input', invalidatePanelSize);
    document.addEventListener('change', invalidatePanelSize);
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
            panelSizes = new WeakMap();
            reposition();
        });
    }
    window.addEventListener('resize', function () {
        panelSizes = new WeakMap();
        reposition();
    });
    window.addEventListener('scroll', function (event) {
        if (event.target.closest && event.target.closest('.date-filter-form')) return;
        reposition();
    }, true);
})();
