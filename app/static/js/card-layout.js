// "Card Layout" (navbar icon, see layouts/navbar.html) — pick a page
// (Overall "/" or Custom "/reports/") from the dropdown, then Default
// (fixed order) vs Custom for THAT page, independent of which page you're
// currently viewing. Choosing Custom opens a bigger "Arrange Your Cards"
// overlay showing every card on the CHOSEN page as a skeleton placeholder
// (title + shimmer body) — fetched from that page if it isn't the one
// you're on — draggable to reorder; saving persists the order for that
// page and, if it's the page you're currently on, reorders it live too.
// Cards are identified by their own .card-title text (stable regardless
// of live badge counts) rather than needing a new id added to every card
// in cards.html/reports/index.html.
(function () {
    // CARD_LAYOUT_RESET_VERSION (app/config.py, .env) — bumping this
    // config value (not this file) makes every existing saved key below
    // invisible to this code (it only ever looks for the current
    // version), so every user resets to default the next time they open
    // the dashboard. See layouts/base.html's data-card-layout-reset-version.
    const RESET_VERSION = document.body.dataset.cardLayoutResetVersion || '1';

    const MODE_KEY_PREFIX = 'card-layout-mode:' + RESET_VERSION + ':';
    const ORDER_KEY_PREFIX = 'card-order:' + RESET_VERSION + ':';
    const HIDDEN_KEY_PREFIX = 'card-hidden:' + RESET_VERSION + ':';

    function modeKey(path) { return MODE_KEY_PREFIX + path; }
    function orderKey(path) { return ORDER_KEY_PREFIX + path; }
    function hiddenKey(path) { return HIDDEN_KEY_PREFIX + path; }

    function savedHiddenTitles(path) {
        try {
            const saved = JSON.parse(localStorage.getItem(hiddenKey(path)) || '[]');
            return Array.isArray(saved) ? saved : [];
        } catch (e) { return []; }
    }

    function grid() { return document.querySelector('.dashboard-grid'); }

    function cardTitle(card) {
        const el = card.querySelector('.card-title');
        return el ? el.textContent.trim() : '';
    }

    function currentMode(path) {
        return localStorage.getItem(modeKey(path)) || 'default';
    }

    function applyOrderTo(list, path) {
        // list: array of {title, isWide, element}. Reorders it in place
        // to match the saved order for `path`, if any.
        let saved;
        try { saved = JSON.parse(localStorage.getItem(orderKey(path)) || 'null'); } catch (e) { saved = null; }
        if (!Array.isArray(saved) || !saved.length) return list;

        const byTitle = new Map(list.map((item) => [item.title, item]));
        const ordered = [];
        saved.forEach((title) => {
            const item = byTitle.get(title);
            if (item) { ordered.push(item); byTitle.delete(title); }
        });
        // Anything not in the saved order (e.g. a feature flag turned on
        // since it was saved) falls through to the end, template order.
        list.forEach((item) => { if (byTitle.has(item.title)) ordered.push(item); });
        return ordered;
    }

    function applySavedOrderToLiveGrid(gridEl, path) {
        const cards = Array.from(gridEl.children).map((el) => ({ title: cardTitle(el), element: el }));
        const ordered = applyOrderTo(cards, path);
        ordered.forEach((item) => gridEl.appendChild(item.element));
    }

    function applySavedHiddenToLiveGrid(gridEl, path) {
        const hidden = new Set(savedHiddenTitles(path));
        Array.from(gridEl.children).forEach((el) => {
            el.classList.toggle('card-hidden-by-user', hidden.has(cardTitle(el)));
        });
    }

    // ── Card list for an arbitrary page — live DOM if it's the current
    // page, otherwise fetched — already sorted to match that page's own
    // saved order. ─────────────────────────────────────────────────────
    function getCardsForPage(path) {
        if (path === window.location.pathname) {
            const gridEl = grid();
            const list = gridEl
                ? Array.from(gridEl.children).map((el) => ({
                    title: cardTitle(el),
                    isWide: el.classList.contains('card-wide'),
                    element: el,
                }))
                : [];
            return Promise.resolve(applyOrderTo(list, path));
        }

        return fetch(path)
            .then((resp) => resp.text())
            .then((html) => {
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const gridEl = doc.querySelector('.dashboard-grid');
                const list = gridEl
                    ? Array.from(gridEl.children).map((el) => ({
                        title: cardTitle(el),
                        isWide: el.classList.contains('card-wide'),
                        element: null,
                    }))
                    : [];
                return applyOrderTo(list, path);
            })
            .catch(() => []);
    }

    // ── Small "Card Layout" modal (page picker + Default / Custom) ──
    // Page picker mirrors the navbar's Theme picker exactly: a trigger
    // button that toggles a .theme-dropdown of .theme-option buttons
    // (see layout.css/theme.css) — not a native <select>.
    const layoutOverlay = document.getElementById('cardLayoutOverlay');
    const pageBtn = document.getElementById('cardLayoutPageBtn');
    const pageBtnText = document.getElementById('cardLayoutPageBtnText');
    const pageDropdown = document.getElementById('cardLayoutPageDropdown');
    let selectedMode = null;
    let selectedPagePath = '/';

    function targetPath() { return selectedPagePath; }

    function setSelectedPage(path, label) {
        selectedPagePath = path;
        if (pageBtnText) pageBtnText.textContent = label;
        if (pageDropdown) {
            pageDropdown.querySelectorAll('.theme-option').forEach((o) =>
                o.classList.toggle('active', o.dataset.pageChoice === path));
        }
        selectedMode = currentMode(path);
        updateModeSelectionUI();
    }

    window.openCardLayoutModal = function () {
        if (!layoutOverlay) return;
        const here = window.location.pathname;
        const known = pageDropdown
            ? Array.from(pageDropdown.querySelectorAll('.theme-option')).find((o) => o.dataset.pageChoice === here)
            : null;
        if (known) setSelectedPage(known.dataset.pageChoice, known.dataset.pageLabel);
        else setSelectedPage('/', 'Overall');
        layoutOverlay.hidden = false;
    };

    function updateModeSelectionUI() {
        document.querySelectorAll('.card-layout-option').forEach((btn) => {
            btn.classList.toggle('is-selected', btn.dataset.layoutOption === selectedMode);
        });
    }

    function closeLayoutModal() {
        if (layoutOverlay) layoutOverlay.hidden = true;
        if (pageDropdown) pageDropdown.classList.remove('open');
    }

    if (layoutOverlay) {
        if (pageBtn && pageDropdown) {
            pageBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                pageDropdown.classList.toggle('open');
            });
            pageDropdown.querySelectorAll('.theme-option').forEach((o) => {
                o.addEventListener('click', function (e) {
                    e.stopPropagation();
                    setSelectedPage(o.dataset.pageChoice, o.dataset.pageLabel);
                    pageDropdown.classList.remove('open');
                });
            });
            document.addEventListener('click', () => pageDropdown.classList.remove('open'));
        }

        document.querySelectorAll('.card-layout-option').forEach((btn) => {
            btn.addEventListener('click', function () {
                selectedMode = btn.dataset.layoutOption;
                updateModeSelectionUI();
            });
            // Double-click Custom to jump straight into the Arrange
            // overlay, skipping the separate Save-changes click.
            btn.addEventListener('dblclick', function () {
                if (btn.dataset.layoutOption !== 'custom') return;
                selectedMode = 'custom';
                closeLayoutModal();
                openArrangeOverlay(targetPath());
            });
        });

        const cancelBtn = document.getElementById('cardLayoutCancel');
        const closeBtn = document.getElementById('cardLayoutClose');
        const saveBtn = document.getElementById('cardLayoutSave');

        if (cancelBtn) cancelBtn.addEventListener('click', closeLayoutModal);
        if (closeBtn) closeBtn.addEventListener('click', closeLayoutModal);
        if (saveBtn) saveBtn.addEventListener('click', function () {
            const path = targetPath();
            closeLayoutModal();
            if (selectedMode === 'custom') {
                openArrangeOverlay(path);
            } else {
                localStorage.setItem(modeKey(path), 'default');
                // Default means "show everything, template order" — also
                // clears any cards hidden via the Arrange overlay, not
                // just the custom order.
                localStorage.removeItem(hiddenKey(path));
                // Only reload if we're actually looking at that page —
                // the live DOM may already show a previously-saved custom
                // order (applied on load), and default needs a re-render
                // from the server's natural order. Picking a different
                // page's Default just saves the preference for later.
                if (path === window.location.pathname) window.location.reload();
            }
        });

        layoutOverlay.addEventListener('click', function (e) {
            if (e.target === layoutOverlay) closeLayoutModal();
        });
    }

    // ── Bigger "Arrange Your Cards" overlay (skeleton drag-to-reorder) ──
    const arrangeOverlay = document.getElementById('cardArrangeOverlay');
    const arrangeGrid = document.getElementById('cardArrangeGrid');
    let draggedItem = null;
    let arrangingPath = null;

    // Hide toggle only flips this item's dataset/visual state — nothing
    // is persisted to localStorage until Save (same as drag reordering:
    // free to rearrange/toggle, only saveArrangedOrder() writes it out).
    function setItemHidden(item, isHidden) {
        item.dataset.hidden = isHidden ? 'true' : 'false';
        item.classList.toggle('is-hidden-choice', isHidden);
        const icon = item.querySelector('.card-arrange-hide-toggle i');
        if (icon) icon.className = 'ti ' + (isHidden ? 'ti-eye-off' : 'ti-eye');
    }

    function buildSkeletonItem(cardInfo) {
        const item = document.createElement('div');
        item.className = 'card-arrange-item' + (cardInfo.isWide ? ' is-wide' : '');
        item.draggable = true;
        item.dataset.cardTitle = cardInfo.title;
        item.innerHTML =
            '<div class="card-arrange-item-title"><i class="ti ti-grip-vertical"></i>' +
            (cardInfo.title || 'Card') +
            '<button type="button" class="card-arrange-hide-toggle" draggable="false" ' +
            'title="Hide/show this card"><i class="ti ti-eye"></i></button>' +
            '</div>' +
            '<div class="card-arrange-skeleton"><span></span><span></span><span></span></div>';

        const toggle = item.querySelector('.card-arrange-hide-toggle');
        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            setItemHidden(item, item.dataset.hidden !== 'true');
        });
        setItemHidden(item, cardInfo.isHidden);
        return item;
    }

    function openArrangeOverlay(path) {
        if (!arrangeOverlay || !arrangeGrid) return;
        arrangingPath = path;

        getCardsForPage(path).then((cards) => {
            const hidden = new Set(savedHiddenTitles(path));
            arrangeGrid.innerHTML = '';
            cards.forEach((cardInfo) => {
                cardInfo.isHidden = hidden.has(cardInfo.title);
                arrangeGrid.appendChild(buildSkeletonItem(cardInfo));
            });
            wireArrangeDragEvents();
            arrangeOverlay.hidden = false;
        });
    }

    function closeArrangeOverlay() {
        if (arrangeOverlay) arrangeOverlay.hidden = true;
    }

    function onDragStart(e) {
        draggedItem = e.currentTarget;
        draggedItem.classList.add('is-dragging');
        e.dataTransfer.effectAllowed = 'move';
    }

    function onDragEnd() {
        if (draggedItem) draggedItem.classList.remove('is-dragging');
        draggedItem = null;
        arrangeGrid.querySelectorAll('.drag-over').forEach((el) => el.classList.remove('drag-over'));
    }

    function onDragOver(e) {
        e.preventDefault();
        if (e.currentTarget !== draggedItem) e.currentTarget.classList.add('drag-over');
    }

    function onDragLeave(e) {
        e.currentTarget.classList.remove('drag-over');
    }

    function onDrop(e) {
        e.preventDefault();
        e.currentTarget.classList.remove('drag-over');
        if (!draggedItem || e.currentTarget === draggedItem) return;

        const items = Array.from(arrangeGrid.children);
        const draggedIndex = items.indexOf(draggedItem);
        const targetIndex = items.indexOf(e.currentTarget);

        if (draggedIndex < targetIndex) {
            e.currentTarget.after(draggedItem);
        } else {
            e.currentTarget.before(draggedItem);
        }
    }

    function wireArrangeDragEvents() {
        Array.from(arrangeGrid.children).forEach((item) => {
            item.addEventListener('dragstart', onDragStart);
            item.addEventListener('dragend', onDragEnd);
            item.addEventListener('dragover', onDragOver);
            item.addEventListener('dragleave', onDragLeave);
            item.addEventListener('drop', onDrop);
        });
    }

    function saveArrangedOrder() {
        if (!arrangingPath) return;
        const items = Array.from(arrangeGrid.children);
        const order = items.map((item) => item.dataset.cardTitle);
        const hidden = items.filter((item) => item.dataset.hidden === 'true').map((item) => item.dataset.cardTitle);

        localStorage.setItem(modeKey(arrangingPath), 'custom');
        localStorage.setItem(orderKey(arrangingPath), JSON.stringify(order));
        localStorage.setItem(hiddenKey(arrangingPath), JSON.stringify(hidden));

        // Only the page we're actually on has a live grid to reorder now
        // — the other page picks up the saved order/hidden set next time
        // it loads.
        if (arrangingPath === window.location.pathname) {
            const gridEl = grid();
            if (gridEl) {
                applySavedOrderToLiveGrid(gridEl, arrangingPath);
                applySavedHiddenToLiveGrid(gridEl, arrangingPath);
            }
        }
    }

    if (arrangeOverlay) {
        const closeBtn = document.getElementById('cardArrangeClose');
        const cancelBtn = document.getElementById('cardArrangeCancel');
        const saveBtn = document.getElementById('cardArrangeSave');

        if (closeBtn) closeBtn.addEventListener('click', closeArrangeOverlay);
        if (cancelBtn) cancelBtn.addEventListener('click', closeArrangeOverlay);
        if (saveBtn) saveBtn.addEventListener('click', function () {
            saveArrangedOrder();
            closeArrangeOverlay();
        });

        arrangeOverlay.addEventListener('click', function (e) {
            if (e.target === arrangeOverlay) closeArrangeOverlay();
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        if (arrangeOverlay && !arrangeOverlay.hidden) closeArrangeOverlay();
        else if (layoutOverlay && !layoutOverlay.hidden) closeLayoutModal();
    });

    // ── Apply the saved order/hidden set on page load ────────────────
    document.addEventListener('DOMContentLoaded', function () {
        const gridEl = grid();
        if (!gridEl) return;
        const here = window.location.pathname;
        if (currentMode(here) === 'custom') applySavedOrderToLiveGrid(gridEl, here);
        applySavedHiddenToLiveGrid(gridEl, here);
    });
})();
