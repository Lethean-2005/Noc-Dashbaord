// Acknowledge/Modify popup — EZE / TCT / ISP POP drilldown tables only
// (see drilldown/alarms.html + drilldown/_ack_button.html).
//
// This app has no login system (app/extensions.py's load_user() is a
// stub) and no website can read the visiting browser's Windows username —
// there is no browser API for that, by design. So "who acknowledged this"
// is captured client-side instead: the "Your Name" field is pre-filled
// with whatever this browser last actually saved (localStorage), or if
// nothing's been saved yet, with window.NOC_DEFAULT_ACK_USERNAME (see
// drilldown/alarms.html + dashboard.py's _DEFAULT_ACK_USERNAME — whichever
// OS account the Flask server process itself runs as: your own account
// when testing locally, svc_nocremote on the VM). Either way, the field is
// always locked read-only — there is deliberately no in-app way to edit
// it. To correct it or hand this browser to someone else, clear this
// site's data/localStorage in the browser itself (DevTools -> Application
// -> Local Storage, or the browser's "Clear browsing data" for this site).
const ACK_USERNAME_KEY = 'nocAckUsername';

// Known-bad values that got cached by mistake before the popup's old
// server-account default (svc_nocremote, the VM's Flask process account)
// was removed — anyone who clicked OK without editing it during that
// window has this stuck in their browser's localStorage. Treating it as
// "nothing cached" here self-heals every affected browser the next time
// they open the popup, instead of requiring each person to manually clear
// their own browser storage.
const ACK_USERNAME_BLOCKLIST = new Set(['']);

function _cachedAckUsername() {
    const cached = localStorage.getItem(ACK_USERNAME_KEY) || '';
    if (ACK_USERNAME_BLOCKLIST.has(cached.toLowerCase())) {
        localStorage.removeItem(ACK_USERNAME_KEY);
        return '';
    }
    return cached;
}

// The stored NOTE is "TT/INC-WOID: note text" (see AlarmService.
// acknowledge_note() — it combines the two into MSSQL's single NOTE
// column). Splitting on the first ": " to pre-fill both fields is
// best-effort display only — if the existing note has no ": " in it
// (e.g. it was written by some other, older tool), the whole thing just
// goes into the Note field with TT/INC-WOID left blank, which is still
// safe to re-submit.
function _splitExistingNote(rawNote) {
    const sep = rawNote.indexOf(': ');
    if (sep === -1) return { ttIncWoId: '', note: rawNote };
    return { ttIncWoId: rawNote.slice(0, sep), note: rawNote.slice(sep + 2) };
}

function openAckModal(button) {
    const overlay = document.getElementById('ackModalOverlay');
    const { ttIncWoId, note } = _splitExistingNote(button.dataset.note || '');
    document.getElementById('ackId').value = button.dataset.id;
    document.getElementById('ackTtIncWo').value = ttIncWoId;
    document.getElementById('ackNote').value = note;

    const usernameField = document.getElementById('ackUsername');
    const stored = _cachedAckUsername();
    const suggestedDefault = window.NOC_DEFAULT_ACK_USERNAME || '';
    const value = stored || suggestedDefault;
    usernameField.value = value;
    // Always locked when there's anything to show at all — either a real
    // prior submission or the server's suggested default.
    usernameField.readOnly = !!value;
    usernameField.title = value
        ? 'Locked — clear this site\'s browser storage to change it'
        : '';
    overlay.style.display = 'block';
}

function closeAckModal() {
    document.getElementById('ackModalOverlay').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('ackModalOverlay');
    const form = document.getElementById('ackForm');
    if (!overlay || !form) return;

    window.addEventListener('click', function (event) {
        if (event.target === overlay) closeAckModal();
    });

    form.addEventListener('submit', function () {
        const name = document.getElementById('ackUsername').value.trim();
        if (name) localStorage.setItem(ACK_USERNAME_KEY, name);
    });
});
