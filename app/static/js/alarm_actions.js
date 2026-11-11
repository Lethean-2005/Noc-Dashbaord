// Three-dot Action menu (dropdown) + Clear Alarm popup — EZE / TCT / ISP
// POP drilldown tables only (see drilldown/alarms.html +
// drilldown/_alarm_action_menu.html). Loaded after acknowledge.js, which
// still owns the Acknowledge/Modify modal (openAckModal/closeAckModal) —
// this file only adds the dropdown that wraps it plus the new Clear
// Alarm action, so the already-working Ack path stays untouched.
//
// Reuses acknowledge.js's _cachedAckUsername() (a plain global function,
// not wrapped in an IIFE) for the Clear popup's "Your Name" field too —
// same browser identity for both actions, one shared localStorage key.

// The table's own scroll container (.alarm-table-wrap, see tables.css) has
// overflow: auto with a max-height, which clips a normally-positioned
// dropdown the moment its row is near the bottom of that scrollable area
// (confirmed from a real screenshot — the menu rendered half cut-off under
// the table's own scrollbar). Fixed here by making .alarm-action-menu
// position: fixed (see tables.css) and computing its on-screen top/right
// from the trigger button's real bounding box instead of relying on CSS
// alone, so it always renders fully on top of the table regardless of
// scroll position.
function toggleAlarmActionMenu(event, button) {
    event.stopPropagation();
    const menu = button.nextElementSibling;
    const isOpen = menu.classList.contains('open');
    closeAlarmActionMenus();
    if (isOpen) return;

    const rect = button.getBoundingClientRect();
    menu.classList.add('open');
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const below = window.innerHeight - rect.bottom - 4;
    const top = height > below && rect.top > height + 4 ? rect.top - height - 4 : rect.bottom + 4;
    menu.style.top = Math.max(8, Math.min(top, window.innerHeight - height - 8)) + 'px';
    menu.style.left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8)) + 'px';
    menu.style.right = 'auto';
}

function closeAlarmActionMenus() {
    document.querySelectorAll('.alarm-action-menu.open').forEach((m) => m.classList.remove('open'));
}

function openClearModal(button) {
    closeAlarmActionMenus();
    document.getElementById('clearId').value = button.dataset.id;

    const usernameField = document.getElementById('clearUsername');
    const stored = _cachedAckUsername();
    const suggestedDefault = window.NOC_DEFAULT_ACK_USERNAME || '';
    const value = stored || suggestedDefault;
    usernameField.value = value;
    usernameField.readOnly = !!value;
    usernameField.title = value
        ? 'Locked — clear this site\'s browser storage to change it'
        : '';

    document.getElementById('clearModalOverlay').style.display = 'block';
}

function closeClearModal() {
    document.getElementById('clearModalOverlay').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('click', closeAlarmActionMenus);

    // position: fixed means the open menu no longer tracks .alarm-table-wrap's
    // own scroll position automatically — close it on scroll (either the
    // table itself or the page) instead of leaving it floating over the
    // wrong row.
    const tableWrap = document.querySelector('.alarm-table-wrap');
    if (tableWrap) tableWrap.addEventListener('scroll', closeAlarmActionMenus);
    window.addEventListener('scroll', closeAlarmActionMenus, true);

    const overlay = document.getElementById('clearModalOverlay');
    const form = document.getElementById('clearForm');
    if (!overlay || !form) return;

    window.addEventListener('click', function (event) {
        if (event.target === overlay) closeClearModal();
    });

    form.addEventListener('submit', function () {
        const name = document.getElementById('clearUsername').value.trim();
        if (name) localStorage.setItem(ACK_USERNAME_KEY, name);
    });
});
