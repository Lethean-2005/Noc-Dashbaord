// Add/Add Contact/Edit Partner modal (see partner_contact/index.html).
// One shared modal handles all three actions, picked by `mode`:
//   'create'      — openPartnerModal('create') — blank form (Partner +
//                   its first Contact together); posts to create. To add
//                   a 2nd/3rd/etc. contact to that partner afterward, use
//                   its row's "Add Contact" button instead of reopening
//                   this form.
//   'edit'        — openPartnerModal('edit', button) — button is the
//                   row's Edit icon; its data-* attributes pre-fill the
//                   whole form, posts to update.
//   'add-contact' — openPartnerModal('add-contact', button) — button is
//                   the row's "Add Contact" icon; only partner_id/name/
//                   type/domain are pre-filled (and locked read-only)
//                   from it, everything else starts blank for the NEW
//                   contact, posts to add_contact. Never touches
//                   TBL_PARTNER, so it doesn't create a duplicate
//                   partner the way filling out "Add Partner" again
//                   would.
// Delete has no JS of its own — its per-row form just uses the app-wide
// data-confirm popup (see app.js).

const PC_USERNAME_KEY = 'nocAckUsername';

// Shared by pcFitAllColumns() below.
const PC_COL_MIN_WIDTH = 40;
const PC_COL_MAX_WIDTH = 1000;

const PC_MODAL_TEXT = {
    create: {
        url: () => window.NOC_PARTNER_CREATE_URL,
        title: 'Add Partner',
        subtitle: 'Add a new partner and contact record',
        submit: 'Save Partner',
    },
    edit: {
        url: () => window.NOC_PARTNER_UPDATE_URL,
        title: 'Edit Partner',
        subtitle: "Update this partner's contact details",
        submit: 'Save Changes',
    },
    'add-contact': {
        url: () => window.NOC_PARTNER_ADD_CONTACT_URL,
        title: 'Add Contact',
        subtitle: 'Add another contact for this partner',
        submit: 'Save Contact',
    },
};

// Tracked so the Partner Name field's live duplicate check (below) only
// ever runs in 'create' mode — in 'edit' mode the field holds the row's
// OWN existing name, which would otherwise always flag itself as a
// duplicate; 'add-contact' locks the field read-only anyway.
let pcModalMode = 'create';

// Set once "New" (Add Partner mode) saves just the Partner row — from
// then on this modal is in "split" mode: Partner Name/Type/Domain are
// locked (already saved), and the form's own submit adds Contact after
// Contact to THIS partner_id via fetch instead of navigating away. null
// means "not split" — the modal behaves exactly as before.
let pcSplitPartnerId = null;

// Full record for every row currently in the split panel's mini-table,
// keyed by contact_id — lets Edit populate the form instantly from
// memory (no re-fetch needed) and lets Delete/Update find that row's
// <tr> again. Reset alongside pcSplitPartnerId in pcExitSplitMode().
let pcMiniContacts = {};

// Set while editing an existing mini-table row (pcStartEditMiniContact) —
// null means the form's next save is a plain "add a new contact".
let pcEditingContactId = null;

// True once anything actually saved during this split-panel visit
// (partner created, contact added/edited/deleted) — closePartnerModal()
// reloads the page when this is true, so the main grid behind the modal
// picks up what just changed instead of sitting stale until a manual
// refresh. Stays false (no reload — an instant close) if the modal was
// just opened and closed without saving anything.
let pcSplitHasChanges = false;

const PC_CONTACT_FIELD_IDS = [
    'pcEscalationLevel', 'pcEscalationMatrix',
    'pcContactName', 'pcContactRole', 'pcPhoneNumber', 'pcEmail',
    'pcRemark',
];

function pcClearContactFields() {
    PC_CONTACT_FIELD_IDS.forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
}

// Reverses pcEnterSplitMode() below — called at the top of every
// openPartnerModal() so reopening this modal (any mode, including
// 'create' again) never carries split state over from a previous visit.
function pcExitSplitMode() {
    pcSplitPartnerId = null;
    pcEditingContactId = null;
    pcMiniContacts = {};
    pcSplitHasChanges = false;
    document.getElementById('pcMiniEditOverlay').style.display = 'none';
    document.getElementById('pcSplitStatusHint').textContent = '';
    document.getElementById('pcSplitStatusHint').classList.remove('pc-field-hint-warning');
    const card = document.getElementById('partnerModalCard');
    if (card) card.classList.remove('pc-split');
    document.getElementById('pcModalSplitRight').style.display = 'none';
    document.getElementById('pcMiniContactsBody').innerHTML = '';
    document.getElementById('pcMiniContactsEmpty').style.display = '';
    document.getElementById('pcNewPartnerBtn').style.display = 'none';
    document.getElementById('pcNewPartnerBtn').textContent = 'New';
    document.getElementById('partnerModalSubmit').style.display = '';
}

// "New" makes sense in 'create' mode (see below) and in 'add-contact'
// mode, which enters split immediately on open (openPartnerModal) since
// it always already has a real partner_id — nothing to create first.
// Before split in 'create' mode specifically, it also needs Partner
// Name/Type/Domain all filled and the name not already flagged as a
// duplicate (pcPartnerNameHint, wired below). Once split (either mode),
// it stays visible unconditionally — every click adds one Contact (see
// its click handler below; editing an existing one happens in its own
// popup instead — pcStartEditMiniContact), and Partner Name/Type/Domain
// are locked read-only anyway, nothing left to validate here.
function pcUpdateNewButtonVisibility() {
    const btn = document.getElementById('pcNewPartnerBtn');
    if (!btn) return;
    if (pcSplitPartnerId) {
        btn.style.display = (pcModalMode === 'create' || pcModalMode === 'add-contact') ? '' : 'none';
        return;
    }
    if (pcModalMode !== 'create') {
        btn.style.display = 'none';
        return;
    }
    const name = document.getElementById('pcPartnerName').value.trim();
    const type = document.getElementById('pcPartnerType').value.trim();
    const domain = document.getElementById('pcDomain').value.trim();
    const isDuplicate = document.getElementById('pcPartnerNameHint').classList.contains('pc-field-hint-warning');
    btn.style.display = (name && type && domain && !isDuplicate) ? '' : 'none';
}

// Called after "New" successfully saves the Partner row (see its click
// handler below) — switches the modal into the two-column layout. From
// here on, "New" stays "New" and stays visible — every further click
// adds one Contact to THIS partner_id, appends it to the live list on
// the right, and clears the form for the next one (see the New button's
// click handler below, which branches on pcSplitPartnerId). The
// original "Save Partner" submit button is hidden — "New" does its job
// now — but the form can still be submitted via Enter for the same effect.
// `keepContactFields` (default false): pass true when the Contact
// fields already had real data typed into them before this call (see
// the "New" click handler's 'create' branch) — that data is about to be
// auto-saved as this partner's first Contact right after, so it must
// NOT be wiped here the way it normally is for a fresh split-mode start.
function pcEnterSplitMode(partner, keepContactFields) {
    pcSplitPartnerId = partner.partner_id;

    document.getElementById('pcPartnerId').value = partner.partner_id;
    document.getElementById('pcPartnerName').readOnly = true;
    document.getElementById('pcPartnerType').readOnly = true;
    document.getElementById('pcDomain').readOnly = true;

    const card = document.getElementById('partnerModalCard');
    if (card) card.classList.add('pc-split');
    document.getElementById('pcModalSplitRight').style.display = '';

    document.getElementById('partnerModalSubmit').style.display = 'none';

    if (!keepContactFields) pcClearContactFields();
    document.getElementById('pcContactName').focus();
}

// Fixed-length truncation + "…" (matches the main .pc-grid's own popup
// fields' truncation convention elsewhere on this page) rather than
// relying on CSS ellipsis alone — the full value is still on the <td>
// itself via `title`, readable on hover.
function pcTruncateText(text, max) {
    text = text || '';
    return text.length > max ? text.slice(0, max) + '…' : text;
}

const PC_MINI_COLUMNS = [
    { key: 'escalation_level', max: 10 },
    { key: 'escalation_matrix', max: 14 },
    { key: 'contact_name', max: 18 },
    { key: 'contact_role', max: 16 },
    { key: 'phone_number', max: 16 },
    { key: 'email', max: 20 },
    { key: 'remark', max: 20 },
];

function pcRenderMiniContactRow(contact) {
    const tr = document.createElement('tr');
    tr.dataset.contactId = contact.contact_id;

    PC_MINI_COLUMNS.forEach(function (col) {
        const td = document.createElement('td');
        const value = contact[col.key] || '';
        td.textContent = pcTruncateText(value, col.max);
        if (value) td.title = value;
        tr.appendChild(td);
    });

    const actionsTd = document.createElement('td');
    actionsTd.className = 'pc-mini-td-actions';

    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'pc-mini-action-btn';
    editBtn.title = 'Edit';
    editBtn.innerHTML = '<i class="ti ti-edit"></i>';
    editBtn.addEventListener('click', function () { pcStartEditMiniContact(contact.contact_id); });

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'pc-mini-action-btn pc-mini-action-btn-danger';
    deleteBtn.title = 'Delete';
    deleteBtn.innerHTML = '<i class="ti ti-trash"></i>';
    deleteBtn.addEventListener('click', function () { pcDeleteMiniContact(contact.contact_id); });

    actionsTd.appendChild(editBtn);
    actionsTd.appendChild(deleteBtn);
    tr.appendChild(actionsTd);

    return tr;
}

// Briefly highlights `tr` (just added/saved) then lets the CSS
// transition fade it back to normal on its own — see .pc-mini-row-flash
// (tables.css). Runs on the next frame so the class-add itself is what
// triggers the transition, not a value already present at insert time.
function pcFlashMiniRow(tr) {
    requestAnimationFrame(function () {
        tr.classList.add('pc-mini-row-flash');
        setTimeout(function () { tr.classList.remove('pc-mini-row-flash'); }, 500);
    });
}

// Shared by pcAppendMiniContactRow (a genuinely new/just-saved row —
// flashes) and pcLoadExistingContacts (rows that already existed before
// this modal opened — no flash, they're not "new").
function pcInsertMiniContactRow(contact) {
    pcMiniContacts[contact.contact_id] = contact;
    document.getElementById('pcMiniContactsEmpty').style.display = 'none';
    const tr = pcRenderMiniContactRow(contact);
    document.getElementById('pcMiniContactsBody').appendChild(tr);
    return tr;
}

function pcAppendMiniContactRow(contact) {
    pcFlashMiniRow(pcInsertMiniContactRow(contact));
}

// Populates the mini-table with a partner's ALREADY-EXISTING Contacts —
// called right after entering split mode via "Add Contact" (see
// openPartnerModal), so clicking Add Contact on a partner that already
// has e.g. 5 Contacts shows all 5 immediately instead of starting the
// list empty and hiding what's already there. A no-op (stays on "No
// contacts added yet.") if this partner genuinely has none yet.
function pcLoadExistingContacts(partnerId) {
    fetch(window.NOC_PARTNER_CONTACTS_URL + '?partner_id=' + encodeURIComponent(partnerId))
        .then(function (res) { return res.json(); })
        .then(function (data) {
            (data.contacts || []).forEach(pcInsertMiniContactRow);
        })
        .catch(function () { /* split mode still works for adding new ones either way */ });
}

function pcUpdateMiniContactRow(contact) {
    pcMiniContacts[contact.contact_id] = contact;
    const tbody = document.getElementById('pcMiniContactsBody');
    const old = tbody.querySelector('tr[data-contact-id="' + contact.contact_id + '"]');
    const tr = pcRenderMiniContactRow(contact);
    if (old) tbody.replaceChild(tr, old);
    else tbody.appendChild(tr);
    pcFlashMiniRow(tr);
}

// Fades + collapses `contactId`'s row before actually removing it (see
// .pc-mini-row-leaving, tables.css) instead of an instant jump-cut.
function pcRemoveMiniRow(contactId) {
    delete pcMiniContacts[contactId];
    const tbody = document.getElementById('pcMiniContactsBody');
    const tr = tbody.querySelector('tr[data-contact-id="' + contactId + '"]');
    if (!tr) return;
    tr.classList.add('pc-mini-row-leaving');
    setTimeout(function () {
        tr.remove();
        if (!tbody.children.length) {
            document.getElementById('pcMiniContactsEmpty').style.display = '';
        }
    }, 180);
}

// Opens the dedicated Edit Contact popup (index.html's #pcMiniEditOverlay
// — a separate small card, not the Add Partner form) pre-filled from
// pcMiniContacts — instant, no network round trip, since the full record
// is already held in memory from when the row was added/last saved.
function pcStartEditMiniContact(contactId) {
    const contact = pcMiniContacts[contactId];
    if (!contact) return;
    pcEditingContactId = contactId;

    const fieldMap = {
        escalation_level: 'pcMiniEditEscalationLevel',
        escalation_matrix: 'pcMiniEditEscalationMatrix',
        contact_name: 'pcMiniEditContactName',
        contact_role: 'pcMiniEditContactRole',
        phone_number: 'pcMiniEditPhoneNumber',
        email: 'pcMiniEditEmail',
        remark: 'pcMiniEditRemark',
    };
    Object.keys(fieldMap).forEach(function (key) {
        document.getElementById(fieldMap[key]).value = contact[key] || '';
    });

    document.querySelectorAll('#pcMiniContactsBody tr').forEach(function (tr) {
        tr.classList.toggle('pc-mini-row-flash', tr.dataset.contactId === contactId);
    });
    document.getElementById('pcMiniEditHint').textContent = '';
    document.getElementById('pcMiniEditHint').classList.remove('pc-field-hint-warning');
    document.getElementById('pcMiniEditOverlay').style.display = 'block';
    document.getElementById('pcMiniEditContactName').focus();
}

function pcCloseMiniEdit() {
    pcEditingContactId = null;
    document.getElementById('pcMiniEditOverlay').style.display = 'none';
    document.getElementById('pcMiniEditHint').textContent = '';
    document.getElementById('pcMiniEditHint').classList.remove('pc-field-hint-warning');
    document.querySelectorAll('#pcMiniContactsBody tr.pc-mini-row-flash').forEach(function (tr) {
        tr.classList.remove('pc-mini-row-flash');
    });
}

// #pcMiniEditForm's own submit handler (wired below) calls this — saves
// via update-contact-only, refreshes that row in place on success, then
// closes the popup. Partner Name/Type/username come from the main form
// (still locked/valid there — the popup only ever edits Contact fields).
function pcSaveMiniEdit(event) {
    event.preventDefault();
    const mainForm = document.getElementById('partnerForm');
    const csrfToken = mainForm.querySelector('[name=csrf_token]').value;
    const saveBtn = document.querySelector('#pcMiniEditForm button[type="submit"]');

    const fieldMap = {
        escalation_level: 'pcMiniEditEscalationLevel',
        escalation_matrix: 'pcMiniEditEscalationMatrix',
        contact_name: 'pcMiniEditContactName',
        contact_role: 'pcMiniEditContactRole',
        phone_number: 'pcMiniEditPhoneNumber',
        email: 'pcMiniEditEmail',
        remark: 'pcMiniEditRemark',
    };
    const params = {
        csrf_token: csrfToken,
        partner_id: pcSplitPartnerId,
        contact_id: pcEditingContactId,
        partner_name: document.getElementById('pcPartnerName').value.trim(),
        partner_type: document.getElementById('pcPartnerType').value.trim(),
        username: document.getElementById('pcUsername').value.trim(),
    };
    Object.keys(fieldMap).forEach(function (key) {
        params[key] = document.getElementById(fieldMap[key]).value.trim();
    });

    const hint = document.getElementById('pcMiniEditHint');
    hint.textContent = '';
    hint.classList.remove('pc-field-hint-warning');

    saveBtn.disabled = true;
    fetch(window.NOC_PARTNER_UPDATE_CONTACT_ONLY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(params).toString(),
    })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            saveBtn.disabled = false;
            if (!data.ok) {
                hint.textContent = data.error === 'missing_fields'
                    ? 'Please fill in every required field (marked *).'
                    : 'Could not save — please try again.';
                hint.classList.add('pc-field-hint-warning');
                return;
            }
            pcSplitHasChanges = true;
            pcUpdateMiniContactRow(data);
            pcCloseMiniEdit();
        })
        .catch(function () {
            saveBtn.disabled = false;
            hint.textContent = 'Network error — please try again.';
            hint.classList.add('pc-field-hint-warning');
        });
}

function pcDeleteMiniContact(contactId) {
    // Same styled popup (window.showConfirm, app.js) the main grid's own
    // per-row Delete uses via data-confirm — this button isn't a form
    // submit, so it calls that popup directly instead.
    window.showConfirm('Delete this partner contact record? This cannot be undone.', {
        yesLabel: 'Yes, Delete!',
    }).then(function (confirmed) {
        if (!confirmed) return;

        const tbody = document.getElementById('pcMiniContactsBody');
        const tr = tbody.querySelector('tr[data-contact-id="' + contactId + '"]');
        const buttons = tr ? tr.querySelectorAll('button') : [];
        buttons.forEach(function (b) { b.disabled = true; });

        const form = document.getElementById('partnerForm');
        const csrfToken = form.querySelector('[name=csrf_token]').value;
        fetch(window.NOC_PARTNER_DELETE_CONTACT_ONLY_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ csrf_token: csrfToken, contact_id: contactId }).toString(),
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.ok) {
                    buttons.forEach(function (b) { b.disabled = false; });
                    const hint = document.getElementById('pcSplitStatusHint');
                    hint.textContent = 'Could not delete this contact — please try again.';
                    hint.classList.add('pc-field-hint-warning');
                    return;
                }
                pcSplitHasChanges = true;
                if (pcEditingContactId === contactId) pcCloseMiniEdit();
                pcRemoveMiniRow(contactId);
            })
            .catch(function () {
                buttons.forEach(function (b) { b.disabled = false; });
                const hint = document.getElementById('pcSplitStatusHint');
                hint.textContent = 'Network error — please try again.';
                hint.classList.add('pc-field-hint-warning');
            });
    });
}

function openPartnerModal(mode, button) {
    pcExitSplitMode();
    const overlay = document.getElementById('partnerModalOverlay');
    const form = document.getElementById('partnerForm');
    const title = document.getElementById('partnerModalTitle');
    const subtitle = document.getElementById('partnerModalSubtitle');
    const submitBtn = document.getElementById('partnerModalSubmit');
    const partnerNameField = document.getElementById('pcPartnerName');
    const partnerTypeField = document.getElementById('pcPartnerType');
    const domainField = document.getElementById('pcDomain');
    const text = PC_MODAL_TEXT[mode];
    pcModalMode = mode;

    const pcNameHint = document.getElementById('pcPartnerNameHint');
    pcNameHint.textContent = '';
    pcNameHint.classList.remove('pc-field-hint-warning');

    // Only the "just added a contact, reopened for another" auto-open
    // path (see index.html's status-handling script) shows this — and
    // it sets the notice text/visibility itself, AFTER this call returns.
    document.getElementById('pcModalNotice').style.display = 'none';

    form.action = text.url();
    title.textContent = text.title;
    subtitle.textContent = text.subtitle;
    submitBtn.textContent = text.submit;

    // Only 'edit' pre-fills every field from the clicked row; 'add-contact'
    // pre-fills just partner_id/name/type/domain (this contact belongs
    // to that existing partner) and leaves the rest blank for the new
    // contact; 'create' starts fully blank.
    const alwaysPrefilled = ['pcPartnerId', 'pcPartnerName', 'pcPartnerType', 'pcDomain'];
    const fields = {
        pcPartnerId: 'partnerId',
        pcContactId: 'contactId',
        pcPartnerName: 'partnerName',
        pcPartnerType: 'partnerType',
        pcDomain: 'domain',
        pcEscalationLevel: 'escalationLevel',
        pcEscalationMatrix: 'escalationMatrix',
        pcContactName: 'contactName',
        pcContactRole: 'contactRole',
        pcPhoneNumber: 'phoneNumber',
        pcEmail: 'email',
        pcRemark: 'remark',
    };
    Object.keys(fields).forEach(function (elId) {
        const prefill = mode === 'edit' || (mode === 'add-contact' && alwaysPrefilled.includes(elId));
        document.getElementById(elId).value = prefill ? (button.dataset[fields[elId]] || '') : '';
    });

    // In add-contact mode, Partner Name/Type are locked to the partner
    // the clicked row belongs to — this form only ever adds a Contact,
    // it never changes the Partner itself (see add_contact() route).
    partnerNameField.readOnly = mode === 'add-contact';
    partnerTypeField.readOnly = mode === 'add-contact';

    // Domain is only ever WRITTEN in 'create' mode (create() route) —
    // update() doesn't touch TBL_PARTNER.Domain, so editing it in
    // 'edit'/'add-contact' mode would silently do nothing; locked
    // read-only there so it doesn't look editable when it isn't. Its
    // dropdown-card toggle button follows the same rule — nothing to
    // pick when the field itself can't be changed.
    if (domainField) domainField.readOnly = mode !== 'create';
    const domainToggle = document.getElementById('pcDomainToggle');
    if (domainToggle) domainToggle.style.display = mode === 'create' ? '' : 'none';

    // 'add-contact' always already has a real partner_id (the row's own)
    // — nothing to create first, so it goes straight into split mode
    // instead of 'create' mode's two-step "New" (create) then "New"
    // (add) — same split UI, same "New adds a Contact, click again for
    // more" loop, just skipping the partner-creation half of it.
    if (mode === 'add-contact') {
        pcEnterSplitMode({
            partner_id: button.dataset.partnerId,
            partner_name: button.dataset.partnerName,
            partner_type: button.dataset.partnerType,
            domain: button.dataset.domain,
        });
        // Shows what this partner already has (e.g. 5 existing Contacts)
        // instead of starting the list empty and hiding them — see
        // pcLoadExistingContacts's own docstring.
        pcLoadExistingContacts(button.dataset.partnerId);
    }

    // Same cache-and-lock behavior as the alarm Acknowledge/Clear popups
    // (see acknowledge.js): a name saved in this browser before (from
    // either this modal or the Ack/Clear popups, same localStorage key)
    // wins; otherwise falls back to NOC_DEFAULT_ACK_USERNAME (the OS
    // account the Flask server itself runs as) so the field isn't empty
    // even on the very first time this browser ever opens this modal.
    const usernameField = document.getElementById('pcUsername');
    const cachedName = localStorage.getItem(PC_USERNAME_KEY) || '';
    const suggestedDefault = window.NOC_DEFAULT_ACK_USERNAME || '';
    const value = cachedName || suggestedDefault;
    usernameField.value = value;
    usernameField.readOnly = !!value;
    usernameField.title = value
        ? 'Locked — clear this site\'s browser storage to change it'
        : '';

    pcUpdateNewButtonVisibility();
    overlay.style.display = 'block';
}

function closePartnerModal() {
    document.getElementById('partnerModalOverlay').style.display = 'none';
    const domainDropdown = document.getElementById('pcDomainDropdown');
    if (domainDropdown) domainDropdown.style.display = 'none';
    const domainToggle = document.getElementById('pcDomainToggle');
    if (domainToggle) domainToggle.classList.remove('is-open');

    // Split-panel writes (create-partner-only/add-contact-only/update-
    // contact-only/delete-contact-only) resync the cache in the
    // background rather than making each click wait for it (see
    // _resync_async(), the route file) — so the main grid behind this
    // modal is still showing whatever it had at page load. Reloading
    // here, only when something was actually saved, is what makes that
    // catch up without needing a manual refresh; closing after just
    // looking around (nothing saved) stays instant, no reload.
    if (pcSplitHasChanges) {
        window.location.reload();
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('partnerModalOverlay');
    const form = document.getElementById('partnerForm');
    if (!overlay || !form) return;

    window.addEventListener('click', function (event) {
        if (event.target === overlay) closePartnerModal();
    });

    const miniEditOverlay = document.getElementById('pcMiniEditOverlay');
    const miniEditForm = document.getElementById('pcMiniEditForm');
    if (miniEditOverlay && miniEditForm) {
        window.addEventListener('click', function (event) {
            if (event.target === miniEditOverlay) pcCloseMiniEdit();
        });
        miniEditForm.addEventListener('submit', pcSaveMiniEdit);
    }

    form.addEventListener('submit', function (event) {
        const name = document.getElementById('pcUsername').value.trim();
        if (name) localStorage.setItem(PC_USERNAME_KEY, name);

        // Split mode: native required-field validation has already run
        // (this listener only fires once the form is actually valid) —
        // add this one Contact via fetch and stay open for the next one,
        // instead of letting the form navigate away like every other mode.
        if (pcSplitPartnerId) {
            event.preventDefault();
            pcSubmitSplitContact();
        }
    });

    const resetBtn = document.getElementById('pcResetBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', function () {
            // Split mode: Partner Name/Type/Domain are locked read-only
            // display of what's ALREADY saved — a native form.reset()
            // would blank them back to empty since they have no `value`
            // attribute, even though the saved partner_id is still live.
            // Only the Contact fields being typed should clear. (Editing
            // an existing row happens in its own popup now — #pcMiniEdit*,
            // pcStartEditMiniContact — so this form is only ever "add".)
            if (pcSplitPartnerId) {
                pcClearContactFields();
                document.getElementById('pcContactName').focus();
            } else {
                form.reset();
            }
        });
    }

    const newBtn = document.getElementById('pcNewPartnerBtn');
    if (newBtn) {
        newBtn.addEventListener('click', function () {
            // Once split, "New" stays "New" but its job changes: every
            // click from here on adds one Contact to the partner already
            // saved, instead of creating a(nother) Partner. reportValidity()
            // triggers the browser's own native required-field bubbles
            // (New is type="button", so it wouldn't otherwise get that
            // check for free the way the old submit button did).
            if (pcSplitPartnerId) {
                if (!form.reportValidity()) {
                    // Native browser validation already points at the exact
                    // invalid field with its own bubble — this is a second,
                    // impossible-to-miss confirmation in a wide layout where
                    // that bubble can land far from where the eye is.
                    const hint = document.getElementById('pcSplitStatusHint');
                    hint.textContent = 'Please fill in every required field (marked *) before clicking New.';
                    hint.classList.add('pc-field-hint-warning');
                    return;
                }
                pcSubmitSplitContact();
                return;
            }

            const partnerName = document.getElementById('pcPartnerName').value.trim();
            const partnerType = document.getElementById('pcPartnerType').value.trim();
            const domain = document.getElementById('pcDomain').value.trim();
            const username = document.getElementById('pcUsername').value.trim();
            const hint = document.getElementById('pcPartnerNameHint');
            if (!partnerName || !partnerType || !domain || !username) return;

            const csrfToken = form.querySelector('[name=csrf_token]').value;
            newBtn.disabled = true;
            fetch(window.NOC_PARTNER_CREATE_PARTNER_ONLY_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({
                    csrf_token: csrfToken,
                    partner_name: partnerName,
                    partner_type: partnerType,
                    domain: domain,
                    username: username,
                }).toString(),
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    newBtn.disabled = false;
                    if (!data.ok) {
                        hint.textContent = data.error === 'duplicate'
                            ? 'This partner name already exists.'
                            : 'Could not save — check the required fields.';
                        hint.classList.add('pc-field-hint-warning');
                        return;
                    }
                    pcSplitHasChanges = true;
                    // If the Contact fields were ALSO already filled in
                    // (the form has always invited filling Partner + its
                    // first Contact together in one go), save that
                    // Contact too right away instead of silently
                    // clearing what was already typed — pcEnterSplitMode()
                    // normally starts them blank, ready for the next one.
                    const hadContact = document.getElementById('pcContactName').value.trim();
                    pcEnterSplitMode(data, !!hadContact);
                    if (hadContact) {
                        if (form.reportValidity()) {
                            pcSubmitSplitContact();
                        } else {
                            const splitHint = document.getElementById('pcSplitStatusHint');
                            splitHint.textContent = 'Partner saved. Finish the required contact fields (marked *) and click New again to save this contact.';
                            splitHint.classList.add('pc-field-hint-warning');
                        }
                    }
                })
                .catch(function () { newBtn.disabled = false; });
        });
    }

    // Partner Type/Domain also gate the "New" button (Partner Name's own
    // input listener, below, handles Partner Name's side of this).
    ['pcPartnerType', 'pcDomain'].forEach(function (id) {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', pcUpdateNewButtonVisibility);
    });
});

// What "New" (and Enter, via the form submit handler above) does once
// split — see pcEnterSplitMode(). Always adds a brand new Contact to
// pcSplitPartnerId (editing an existing row happens in its own popup —
// #pcMiniEditOverlay, pcSaveMiniEdit — not through this form). Appends
// the new row to the live mini-table the moment the response comes
// back — no page reload, no reopening the modal — then clears the form
// so "New" can be clicked again immediately for the next contact.
function pcSubmitSplitContact() {
    const form = document.getElementById('partnerForm');
    const newBtn = document.getElementById('pcNewPartnerBtn');
    const csrfToken = form.querySelector('[name=csrf_token]').value;
    const username = document.getElementById('pcUsername').value.trim();

    const fieldMap = {
        escalation_level: 'pcEscalationLevel',
        escalation_matrix: 'pcEscalationMatrix',
        contact_name: 'pcContactName',
        contact_role: 'pcContactRole',
        phone_number: 'pcPhoneNumber',
        email: 'pcEmail',
        remark: 'pcRemark',
    };
    const params = { csrf_token: csrfToken, partner_id: pcSplitPartnerId, username: username };
    Object.keys(fieldMap).forEach(function (key) {
        params[key] = document.getElementById(fieldMap[key]).value.trim();
    });

    const hint = document.getElementById('pcSplitStatusHint');
    hint.textContent = '';
    hint.classList.remove('pc-field-hint-warning');

    newBtn.disabled = true;
    fetch(window.NOC_PARTNER_ADD_CONTACT_ONLY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(params).toString(),
    })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            newBtn.disabled = false;
            if (!data.ok) {
                hint.textContent = data.error === 'missing_fields'
                    ? 'Please fill in every required field (marked *) before clicking New.'
                    : 'Could not save this contact — please try again.';
                hint.classList.add('pc-field-hint-warning');
                return;
            }
            pcSplitHasChanges = true;
            pcAppendMiniContactRow(data);
            pcClearContactFields();
            document.getElementById('pcContactName').focus();
        })
        .catch(function () {
            newBtn.disabled = false;
            hint.textContent = 'Network error — please try again.';
            hint.classList.add('pc-field-hint-warning');
        });
}

// Live "this partner already exists" hint under Partner Name — Add
// Partner mode only (see pcModalMode above). Debounced 350ms so it
// doesn't fire a request on every keystroke, just once typing pauses.
document.addEventListener('DOMContentLoaded', function () {
    const nameField = document.getElementById('pcPartnerName');
    const hint = document.getElementById('pcPartnerNameHint');
    if (!nameField || !hint) return;

    let debounceTimer = null;
    nameField.addEventListener('input', function () {
        clearTimeout(debounceTimer);
        const value = nameField.value.trim();
        if (pcModalMode !== 'create' || !value) {
            hint.textContent = '';
            hint.classList.remove('pc-field-hint-warning');
            pcUpdateNewButtonVisibility();
            return;
        }
        debounceTimer = setTimeout(function () {
            fetch(window.NOC_PARTNER_CHECK_NAME_URL + '?name=' + encodeURIComponent(value))
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    // Bail if the field changed again while this request
                    // was in flight — an in-flight response for stale
                    // text shouldn't overwrite what's now on screen.
                    if (nameField.value.trim() !== value) return;
                    if (data.exists) {
                        hint.textContent = 'This partner name already exists.';
                        hint.classList.add('pc-field-hint-warning');
                    } else {
                        hint.textContent = '';
                        hint.classList.remove('pc-field-hint-warning');
                    }
                    pcUpdateNewButtonVisibility();
                })
                .catch(function () { /* silent — submit's own server-side check is the real guard */ });
        }, 350);
    });
});

// Shared by the Remark and Email "view full value" popups (both reuse
// the same .pc-remark-card look, see index.html/tables.css) — one pair
// of open/close functions instead of a near-identical copy per field.
function pcOpenValueCard(overlayId, textElId, text) {
    document.getElementById(textElId).textContent = text;
    document.getElementById(overlayId).style.display = 'block';
}

function pcCloseValueCard(overlayId) {
    document.getElementById(overlayId).style.display = 'none';
}

// Email's view icon (index.html) calls this directly with the row's
// full email string — unlike Remark, the cell itself still has a real
// mailto: link in it, so only the icon opens the popup, not the whole
// cell (clicking the truncated email text should still open the mail
// client, not this). Doesn't reuse pcOpenValueCard's textContent set —
// the popup text here needs to BE a clickable mailto: link, built via
// createElement/textContent (not innerHTML) so the email string can't
// be interpreted as markup even though it's free-form data.
function pcOpenEmailModal(text) {
    const el = document.getElementById('pcEmailModalText');
    el.textContent = '';
    const link = document.createElement('a');
    link.href = 'mailto:' + text;
    link.textContent = text;
    el.appendChild(link);
    document.getElementById('pcEmailOverlay').style.display = 'block';
}

function pcCloseEmailModal() {
    pcCloseValueCard('pcEmailOverlay');
}

// Click outside any open value card (Email, ...) to close it —
// .pc-value-overlay is shared by every one of them.
document.addEventListener('DOMContentLoaded', function () {
    window.addEventListener('click', function (event) {
        if (event.target.classList && event.target.classList.contains('pc-value-overlay')) {
            event.target.style.display = 'none';
        }
    });
});

// Columns don't drag-resize — every column just fits its own content
// automatically on load (see the DOMContentLoaded handler below).
//
// This used to estimate each column's width in JS (an offscreen span
// measuring text) instead of asking the browser directly — that kept
// silently under-measuring real content (HURRICANE ELECTRIC and
// similar getting cut to "...") because a JS-side guess can drift from
// actual rendering for all sorts of reasons: the webfont not loaded
// yet, getComputedStyle(el).font returning empty in some browsers,
// small padding/border rounding, etc. — a losing game of chasing each
// symptom individually.
//
// The browser's own table-layout:auto algorithm doesn't have any of
// those problems — it lays out real text in the real font it already
// has loaded, so "natural width" is exactly what will render, by
// definition. The only reason this file moved away from it earlier was
// that Remark used to wrap onto multiple lines (white-space: pre-line),
// and auto-layout would squeeze that one wrapping column to satisfy
// every other nowrap column's minimum width. Remark stopped wrapping
// several changes ago (it truncates to one line + a popup now, same as
// every other column) — so every column here is nowrap, nothing can
// get squeezed, and the original approach is simply correct again.
function pcFitAllColumns() {
    const grid = document.querySelector('.pc-grid');
    if (!grid) return;
    const headers = grid.querySelectorAll('thead th[data-col]');
    if (!headers.length) return;

    grid.style.tableLayout = 'auto';
    headers.forEach(function (th) {
        if (th.dataset.col === '0') return; // No. stays at its fixed width — see <col id="pc-col-0">, index.html.
        const col = document.getElementById('pc-col-' + th.dataset.col);
        if (col) col.style.width = '';
    });
    void grid.offsetWidth; // Force layout before measuring below.

    headers.forEach(function (th) {
        if (th.dataset.col === '0') return;
        const col = document.getElementById('pc-col-' + th.dataset.col);
        if (!col) return;
        const natural = Math.ceil(th.getBoundingClientRect().width);
        col.style.width = Math.min(PC_COL_MAX_WIDTH, Math.max(PC_COL_MIN_WIDTH, natural)) + 'px';
    });

    grid.style.tableLayout = 'fixed';
}

document.addEventListener('DOMContentLoaded', function () {
    const grid = document.querySelector('.pc-grid');
    if (!grid) return;

    // Every column fits its own content on load — no column starts
    // truncated with "..." until the data changes underneath it.
    pcFitAllColumns();

    // .pc-grid renders in Nunito (a webfont, tables.css), which usually
    // hasn't finished loading yet at DOMContentLoaded — measuring before
    // it's ready falls back to a system font's (narrower) metrics, so a
    // column can end up JUST slightly too tight once Nunito actually
    // paints in, silently truncating text that should have fit. Re-fit
    // once the browser confirms every font on the page is loaded so the
    // measurement matches what's really rendered.
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(pcFitAllColumns);
    }
});

// Domain's dropdown-card (index.html's #pcDomainDropdown — same shell as
// the dashboard's Filter by Category, .date-filter-form). Fetched once
// on page load, not lazily per-open, since the list is small and
// doesn't change mid-session. Domain stays a real <input>, not a
// <select> — this dropdown only ever fills it, typing a genuinely new
// Domain by hand still works exactly the same as before.
let pcDomainOptionsPromise = null;

function pcFetchDomainOptions() {
    if (pcDomainOptionsPromise) return pcDomainOptionsPromise;
    pcDomainOptionsPromise = window.NOC_PARTNER_DOMAINS_URL
        ? fetch(window.NOC_PARTNER_DOMAINS_URL)
            .then(function (res) { return res.json(); })
            .then(function (data) { return data.domains || []; })
            .catch(function () { return []; })
        : Promise.resolve([]);
    return pcDomainOptionsPromise;
}

document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('pcDomainToggle');
    const dropdown = document.getElementById('pcDomainDropdown');
    const optionsEl = document.getElementById('pcDomainOptions');
    const domainField = document.getElementById('pcDomain');
    if (!toggle || !dropdown || !optionsEl || !domainField) return;

    function closeDropdown() {
        dropdown.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (dropdown.style.display === 'block') { closeDropdown(); return; }
        pcFetchDomainOptions().then(function (domains) {
            const current = domainField.value.trim();
            optionsEl.innerHTML = '';
            if (!domains.length) {
                const empty = document.createElement('div');
                empty.className = 'pc-field-dropdown-empty';
                empty.textContent = 'No domains yet — type one below.';
                optionsEl.appendChild(empty);
            } else {
                domains.forEach(function (d) {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'pc-field-dropdown-option' + (d === current ? ' is-selected' : '');

                    const label = document.createElement('span');
                    label.className = 'pc-field-dropdown-option-label';
                    label.textContent = d;

                    const check = document.createElement('span');
                    check.className = 'pc-field-dropdown-option-check';
                    check.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';

                    btn.appendChild(label);
                    btn.appendChild(check);
                    btn.addEventListener('click', function () {
                        domainField.value = d;
                        domainField.dispatchEvent(new Event('input', { bubbles: true }));
                        closeDropdown();
                    });
                    optionsEl.appendChild(btn);
                });
            }
            dropdown.style.display = 'block';
            toggle.classList.add('is-open');
        });
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
});

// Escalation Level's dropdown-card — same shell/behavior as Domain's
// above, just its own fetch/field/options ids and endpoint.
let pcEscalationLevelOptionsPromise = null;

function pcFetchEscalationLevelOptions() {
    if (pcEscalationLevelOptionsPromise) return pcEscalationLevelOptionsPromise;
    pcEscalationLevelOptionsPromise = window.NOC_PARTNER_ESCALATION_LEVELS_URL
        ? fetch(window.NOC_PARTNER_ESCALATION_LEVELS_URL)
            .then(function (res) { return res.json(); })
            .then(function (data) { return data.escalation_levels || []; })
            .catch(function () { return []; })
        : Promise.resolve([]);
    return pcEscalationLevelOptionsPromise;
}

document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('pcEscalationLevelToggle');
    const dropdown = document.getElementById('pcEscalationLevelDropdown');
    const optionsEl = document.getElementById('pcEscalationLevelOptions');
    const levelField = document.getElementById('pcEscalationLevel');
    if (!toggle || !dropdown || !optionsEl || !levelField) return;

    function closeDropdown() {
        dropdown.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (dropdown.style.display === 'block') { closeDropdown(); return; }
        pcFetchEscalationLevelOptions().then(function (levels) {
            const current = levelField.value.trim();
            optionsEl.innerHTML = '';

            // Always offered, even when the DB-backed list below is
            // empty — clicking it empties the field instead of requiring
            // the user to close this popover and delete the text by
            // hand. Not one of `levels` (those are real values already
            // in use elsewhere), so it's built separately rather than
            // folded into the forEach below.
            const blankBtn = document.createElement('button');
            blankBtn.type = 'button';
            blankBtn.className = 'pc-field-dropdown-option pc-field-dropdown-option-blank' + (!current ? ' is-selected' : '');
            const blankLabel = document.createElement('span');
            blankLabel.className = 'pc-field-dropdown-option-label';
            blankLabel.textContent = '(Blank)';
            const blankCheck = document.createElement('span');
            blankCheck.className = 'pc-field-dropdown-option-check';
            blankCheck.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';
            blankBtn.appendChild(blankLabel);
            blankBtn.appendChild(blankCheck);
            blankBtn.addEventListener('click', function () {
                levelField.value = '';
                levelField.dispatchEvent(new Event('input', { bubbles: true }));
                closeDropdown();
            });
            optionsEl.appendChild(blankBtn);

            if (!levels.length) {
                const empty = document.createElement('div');
                empty.className = 'pc-field-dropdown-empty';
                empty.textContent = 'No escalation levels yet — type one below.';
                optionsEl.appendChild(empty);
            } else {
                levels.forEach(function (lvl) {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'pc-field-dropdown-option' + (lvl === current ? ' is-selected' : '');

                    const label = document.createElement('span');
                    label.className = 'pc-field-dropdown-option-label';
                    label.textContent = lvl;

                    const check = document.createElement('span');
                    check.className = 'pc-field-dropdown-option-check';
                    check.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';

                    btn.appendChild(label);
                    btn.appendChild(check);
                    btn.addEventListener('click', function () {
                        levelField.value = lvl;
                        levelField.dispatchEvent(new Event('input', { bubbles: true }));
                        closeDropdown();
                    });
                    optionsEl.appendChild(btn);
                });
            }
            dropdown.style.display = 'block';
            toggle.classList.add('is-open');
        });
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
});

// Escalation Matrix's dropdown-card — same shell/behavior as Escalation
// Level's above, just its own fetch/field/options ids and endpoint.
let pcEscalationMatrixOptionsPromise = null;

function pcFetchEscalationMatrixOptions() {
    if (pcEscalationMatrixOptionsPromise) return pcEscalationMatrixOptionsPromise;
    pcEscalationMatrixOptionsPromise = window.NOC_PARTNER_ESCALATION_MATRIX_URL
        ? fetch(window.NOC_PARTNER_ESCALATION_MATRIX_URL)
            .then(function (res) { return res.json(); })
            .then(function (data) { return data.escalation_matrix_values || []; })
            .catch(function () { return []; })
        : Promise.resolve([]);
    return pcEscalationMatrixOptionsPromise;
}

document.addEventListener('DOMContentLoaded', function () {
    const toggle = document.getElementById('pcEscalationMatrixToggle');
    const dropdown = document.getElementById('pcEscalationMatrixDropdown');
    const optionsEl = document.getElementById('pcEscalationMatrixOptions');
    const matrixField = document.getElementById('pcEscalationMatrix');
    if (!toggle || !dropdown || !optionsEl || !matrixField) return;

    function closeDropdown() {
        dropdown.style.display = 'none';
        toggle.classList.remove('is-open');
    }

    toggle.addEventListener('click', function (event) {
        event.stopPropagation();
        if (dropdown.style.display === 'block') { closeDropdown(); return; }
        pcFetchEscalationMatrixOptions().then(function (matrices) {
            const current = matrixField.value.trim();
            optionsEl.innerHTML = '';

            // Always offered, even when the DB-backed list below is
            // empty — clicking it empties the field instead of requiring
            // the user to close this popover and delete the text by
            // hand. Not one of `matrices` (those are real values already
            // in use elsewhere), so it's built separately rather than
            // folded into the forEach below.
            const blankBtn = document.createElement('button');
            blankBtn.type = 'button';
            blankBtn.className = 'pc-field-dropdown-option pc-field-dropdown-option-blank' + (!current ? ' is-selected' : '');
            const blankLabel = document.createElement('span');
            blankLabel.className = 'pc-field-dropdown-option-label';
            blankLabel.textContent = '(Blank)';
            const blankCheck = document.createElement('span');
            blankCheck.className = 'pc-field-dropdown-option-check';
            blankCheck.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';
            blankBtn.appendChild(blankLabel);
            blankBtn.appendChild(blankCheck);
            blankBtn.addEventListener('click', function () {
                matrixField.value = '';
                matrixField.dispatchEvent(new Event('input', { bubbles: true }));
                closeDropdown();
            });
            optionsEl.appendChild(blankBtn);

            if (!matrices.length) {
                const empty = document.createElement('div');
                empty.className = 'pc-field-dropdown-empty';
                empty.textContent = 'No escalation matrices yet — type one below.';
                optionsEl.appendChild(empty);
            } else {
                matrices.forEach(function (mtx) {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'pc-field-dropdown-option' + (mtx === current ? ' is-selected' : '');

                    const label = document.createElement('span');
                    label.className = 'pc-field-dropdown-option-label';
                    label.textContent = mtx;

                    const check = document.createElement('span');
                    check.className = 'pc-field-dropdown-option-check';
                    check.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';

                    btn.appendChild(label);
                    btn.appendChild(check);
                    btn.addEventListener('click', function () {
                        matrixField.value = mtx;
                        matrixField.dispatchEvent(new Event('input', { bubbles: true }));
                        closeDropdown();
                    });
                    optionsEl.appendChild(btn);
                });
            }
            dropdown.style.display = 'block';
            toggle.classList.add('is-open');
        });
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.pc-field-with-dropdown')) return;
        closeDropdown();
    });
});

// Import password gate (#pcImportPasswordModal) in front of the Import
// button. The password is verified server-side (verify_import_password
// in routes/partner_contact.py) — this file never holds the real value,
// only whatever the user typed, kept in pcPendingImportPassword just
// long enough to attach to the actual import upload (pcHandleImportFile)
// and cleared as soon as that request settles.
//
// Deliberately two steps, not one: after a correct password this does
// NOT script-trigger the native file dialog itself. Closing a modal and
// opening the file dialog back-to-back in the same tick left the OS
// mouse cursor invisible over Chrome/the dialog on this machine (a GPU
// compositing glitch). Splitting it into its own "Choose File" button
// means the file dialog only ever opens from a fresh, separate click,
// with a real render in between — not a race a script has to win.
let pcPendingImportPassword = '';
// 'password' (verify what was typed) or 'choose-file' (open the picker) —
// which action the single footer button performs next; pcImportPasswordAction
// below reads this instead of the page needing two separate buttons.
let pcImportStep = 'password';

function pcOpenImportPasswordModal() {
    const modal = document.getElementById('pcImportPasswordModal');
    const passwordStep = document.getElementById('pcImportPasswordStep');
    const chooseFileStep = document.getElementById('pcImportChooseFileStep');
    const input = document.getElementById('pcImportPasswordInput');
    const error = document.getElementById('pcImportPasswordError');
    const subtitle = document.getElementById('pcImportPasswordSubtitle');
    const actionBtn = document.getElementById('pcImportPasswordAction');
    if (!modal || !input) return;
    input.value = '';
    error.hidden = true;
    input.classList.remove('is-shake');
    passwordStep.hidden = false;
    chooseFileStep.hidden = true;
    subtitle.textContent = 'Enter the password to continue.';
    actionBtn.textContent = 'Confirm';
    pcImportStep = 'password';
    modal.style.display = 'block';
    input.focus();
}

function pcCloseImportPasswordModal() {
    const modal = document.getElementById('pcImportPasswordModal');
    if (modal) modal.style.display = 'none';
}

function pcImportPasswordAction() {
    if (pcImportStep === 'password') {
        pcConfirmImportPassword();
    } else {
        pcChooseImportFile();
    }
}

function pcConfirmImportPassword() {
    const input = document.getElementById('pcImportPasswordInput');
    const error = document.getElementById('pcImportPasswordError');
    const subtitle = document.getElementById('pcImportPasswordSubtitle');
    const actionBtn = document.getElementById('pcImportPasswordAction');
    if (!input) return;

    const attempted = input.value;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const formData = new FormData();
    formData.append('password', attempted);
    formData.append('csrf_token', csrfToken);

    if (actionBtn) actionBtn.disabled = true;
    fetch(window.NOC_PARTNER_VERIFY_IMPORT_PASSWORD_URL, { method: 'POST', body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (actionBtn) actionBtn.disabled = false;
            if (data.ok) {
                pcPendingImportPassword = attempted;
                document.getElementById('pcImportPasswordStep').hidden = true;
                document.getElementById('pcImportChooseFileStep').hidden = false;
                subtitle.textContent = 'Password confirmed.';
                actionBtn.textContent = 'Choose File';
                pcImportStep = 'choose-file';
                return;
            }
            error.hidden = false;
            input.classList.remove('is-shake');
            // Force the animation to restart even if it's already mid-shake
            // from a previous wrong attempt — reading offsetWidth flushes the
            // class removal before re-adding it.
            void input.offsetWidth;
            input.classList.add('is-shake');
            input.value = '';
            input.focus();
        })
        .catch(function () {
            if (actionBtn) actionBtn.disabled = false;
        });
}

function pcChooseImportFile() {
    pcCloseImportPasswordModal();
    // Double requestAnimationFrame: the first fires before the browser's
    // next paint, the second only after that paint has actually happened —
    // so the modal-closed frame is guaranteed on screen before the native
    // file dialog takes over, instead of guessing with a fixed setTimeout.
    requestAnimationFrame(function () {
        requestAnimationFrame(function () {
            document.getElementById('pcImportFileInput').click();
        });
    });
}

(function () {
    const closeBtn = document.getElementById('pcImportPasswordClose');
    const actionBtn = document.getElementById('pcImportPasswordAction');
    const input = document.getElementById('pcImportPasswordInput');
    const modal = document.getElementById('pcImportPasswordModal');
    if (closeBtn) closeBtn.addEventListener('click', pcCloseImportPasswordModal);
    if (actionBtn) actionBtn.addEventListener('click', pcImportPasswordAction);
    if (input) {
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') pcImportPasswordAction();
        });
    }
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) pcCloseImportPasswordModal();
        });
    }
})();

// Import button (header toolbar) — uploads the filled-in template
// (.xlsx/.csv) to NOC_PARTNER_IMPORT_URL. Only Partner Name is checked
// for duplicates server-side (see import_rows() docstring); if any
// partner in the file already existed, that's surfaced here as a plain
// popup via showModal() (app.js) — not a row-by-row report — since that's
// the only thing the user can't tell just by re-opening the file.
function pcHandleImportFile(input) {
    const file = input.files && input.files[0];
    if (!file) return;

    const username = localStorage.getItem(PC_USERNAME_KEY) || window.NOC_DEFAULT_ACK_USERNAME || '';
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

    const formData = new FormData();
    formData.append('file', file);
    formData.append('username', username);
    formData.append('csrf_token', csrfToken);
    formData.append('import_password', pcPendingImportPassword);

    input.disabled = true;
    fetch(window.NOC_PARTNER_IMPORT_URL, { method: 'POST', body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            input.value = '';
            input.disabled = false;
            pcPendingImportPassword = '';

            if (!data.ok) {
                const message = data.error === 'unreadable_file'
                    ? "Couldn't read that file — make sure it's a real .xlsx or .csv (the Template button gives you a valid starting point)."
                    : 'Import failed — please check the file and try again.';
                window.showModal('Error', message);
                return;
            }

            const lines = [];
            lines.push(data.partners_created + ' partner(s) created, ' + data.contacts_added + ' contact(s) added.');
            if (data.existing_partners && data.existing_partners.length) {
                lines.push('Partner already existed (not re-created, contacts added to it): ' + data.existing_partners.join(', ') + '.');
            }
            if (data.failed_rows && data.failed_rows.length) {
                lines.push(data.failed_rows.length + ' row(s) skipped — ' +
                    data.failed_rows.map(function (r) { return 'row ' + r.row + ': ' + r.reason; }).join('; '));
            }

            window.showModal(
                data.failed_rows && data.failed_rows.length ? 'Import Finished (with skipped rows)' : 'Success',
                lines.join(' ')
            );
            setTimeout(function () { window.location.reload(); }, 1200);
        })
        .catch(function () {
            input.value = '';
            input.disabled = false;
            window.showModal('Error', 'Import failed — network error, please try again.');
        });
}

// "View all contacts for this partner" popup — clicking anywhere in a
// record's row (any column) opens this, same columns as the main
// Contact Partner grid/mini-table (PC_MINI_COLUMNS) — Level, Matrix,
// Contact Name, Role, Phone, Email, Remark — full values, no
// truncation, since the point is seeing everything at once. Fetches
// the same endpoint the split-panel's "Add Contact" pre-fill uses
// (partner_contacts()). An 8th "Actions" column (pencil icon) lets
// each row be edited IN PLACE here too — requested as a faster path
// than reopening the main Edit Partner form just to fix one contact's
// phone number or role, same update-contact-only write the split-panel
// mini-table's own Edit popup already uses, just inline instead of a
// second popup on top of this one.
const PC_ESCALATION_COLS = 8;

// This popup's own partner context (id/name/type) — stashed on open so
// pcSaveEscalationRow() below has them without needing to re-fetch or
// thread them through every row. update_contact_only() requires all
// three alongside contact_id (see that route's own docstring: it
// writes Partner fields too, since Partner/Contact are saved together
// server-side even when only a Contact field actually changed here).
let pcEscalationPartner = { id: '', name: '', type: '' };
// contact_id -> full contact record, refreshed each time this popup
// opens or a row saves — lets Cancel restore a row's exact prior
// values without a network round trip, same as pcMiniContacts does
// for the split-panel mini-table.
let pcEscalationContacts = {};

function pcOpenPartnerContactsModal(partnerId, partnerName, partnerType) {
    if (!partnerId) return;
    const overlay = document.getElementById('pcPartnerContactsOverlay');
    const title = document.getElementById('pcPartnerContactsTitle');
    const body = document.getElementById('pcPartnerContactsModalBody');
    if (!overlay || !title || !body) return;

    pcEscalationPartner = { id: partnerId, name: partnerName, type: partnerType };
    pcEscalationContacts = {};
    title.textContent = partnerName + ' — ' + partnerType;
    body.innerHTML = '';
    const loadingTr = document.createElement('tr');
    const loadingTd = document.createElement('td');
    loadingTd.colSpan = PC_ESCALATION_COLS;
    loadingTd.className = 'pc-escalation-empty';
    loadingTd.textContent = 'Loading…';
    loadingTr.appendChild(loadingTd);
    body.appendChild(loadingTr);
    overlay.style.display = 'block';

    fetch(window.NOC_PARTNER_CONTACTS_URL + '?partner_id=' + encodeURIComponent(partnerId))
        .then(function (res) { return res.json(); })
        .then(function (data) {
            const contacts = (data.contacts || []).slice().sort(function (a, b) {
                const na = parseInt(String(a.escalation_level || '').replace(/\D/g, ''), 10);
                const nb = parseInt(String(b.escalation_level || '').replace(/\D/g, ''), 10);
                if (!isNaN(na) && !isNaN(nb) && na !== nb) return na - nb;
                return String(a.escalation_level || '').localeCompare(String(b.escalation_level || ''));
            });
            pcRenderPartnerContactsRows(body, contacts);
        })
        .catch(function () {
            body.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = PC_ESCALATION_COLS;
            td.className = 'pc-escalation-empty';
            td.textContent = 'Failed to load — please try again.';
            tr.appendChild(td);
            body.appendChild(tr);
        });
}

function pcRenderPartnerContactsRows(body, contacts) {
    body.innerHTML = '';
    if (!contacts.length) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = PC_ESCALATION_COLS;
        td.className = 'pc-escalation-empty';
        td.textContent = 'No contacts added yet for this partner.';
        tr.appendChild(td);
        body.appendChild(tr);
        return;
    }
    contacts.forEach(function (c) {
        pcEscalationContacts[c.contact_id] = c;
        body.appendChild(pcRenderEscalationRow(c));
    });
}

// Builds ONE row in read-only display mode — same shape the plain
// version always rendered (text + mailto: link + copy button per
// cell), plus the trailing pencil-only Actions cell.
function pcRenderEscalationRow(c) {
    const tr = document.createElement('tr');
    tr.dataset.contactId = c.contact_id;
    PC_MINI_COLUMNS.forEach(function (col) {
        const td = document.createElement('td');
        td.dataset.field = col.key;
        const value = c[col.key];
        // Same mailto: link as the main grid's Email column — built
        // via createElement/textContent (not innerHTML), so a
        // free-form value can never be interpreted as markup.
        if (col.key === 'email' && value) {
            const link = document.createElement('a');
            link.href = 'mailto:' + value;
            link.textContent = value;
            td.appendChild(link);
        } else {
            td.textContent = value || '-';
        }
        if (value) td.appendChild(pcMakeCopyButton(value));
        tr.appendChild(td);
    });

    const actionsTd = document.createElement('td');
    actionsTd.className = 'pc-escalation-td-actions';
    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'pc-mini-action-btn';
    editBtn.title = 'Edit';
    editBtn.innerHTML = '<i class="ti ti-edit"></i>';
    editBtn.addEventListener('click', function () { pcStartEditEscalationRow(c.contact_id); });
    actionsTd.appendChild(editBtn);
    tr.appendChild(actionsTd);

    return tr;
}

// Shared by Escalation Level/Matrix's "choose an existing value"
// dropdown — a free-text <input> with a toggle button that opens a
// list of values already in use elsewhere (plus "(Blank)"), same
// pcFetchEscalationLevelOptions()/pcFetchEscalationMatrixOptions()
// (already memoized above) the Add Partner form's own Level/Matrix
// fields use. These icons are shared across both that form's Level
// field, its Matrix field, and every inline-edit row's own Level/
// Matrix cell below — pulled out once here instead of inline SVG
// repeated a third time.
const PC_SELECTOR_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M8 9l4 -4l4 4"/><path d="M16 15l-4 4l-4 -4"/></svg>';
const PC_CHECK_ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>';

// field key -> its fetch function + empty-list message, so
// pcBuildEscalationDropdownCell() below can build either column from
// one shared code path instead of two near-identical ones.
const PC_FIELD_DROPDOWN_SOURCES = {
    escalation_level: {
        fetch: function () { return pcFetchEscalationLevelOptions(); },
        empty: 'No escalation levels yet — type one below.',
        label: 'Escalation Level',
    },
    escalation_matrix: {
        fetch: function () { return pcFetchEscalationMatrixOptions(); },
        empty: 'No escalation matrices yet — type one below.',
        label: 'Escalation Matrix',
    },
};

// Builds one <td>'s worth of markup for a dropdown-backed field
// (Level/Matrix) — the input itself plus its toggle + (closed) card.
// Opening/populating/closing is handled by ONE delegated listener
// (see the IIFE below pcSaveEscalationRow) instead of binding a fresh
// closure here per row per edit — rows get discarded and rebuilt a
// lot (every Cancel, every Save) and a per-row listener would just
// keep accumulating orphaned closures on `document` over a long NOC
// shift instead of ever being cleaned up.
function pcBuildEscalationDropdownCell(td, fieldKey, value) {
    const source = PC_FIELD_DROPDOWN_SOURCES[fieldKey];
    const wrap = document.createElement('div');
    wrap.className = 'pc-field-with-dropdown';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'pc-escalation-edit-input';
    input.dataset.field = fieldKey;
    input.value = value || '';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'pc-field-selector-btn';
    toggle.title = 'Choose an existing value';
    toggle.dataset.pcDropdownToggle = fieldKey;
    toggle.innerHTML = PC_SELECTOR_ICON_SVG;

    const dropdown = document.createElement('div');
    dropdown.className = 'pc-field-dropdown-card';
    dropdown.style.display = 'none';
    const header = document.createElement('div');
    header.className = 'pc-field-dropdown-header';
    const headerLabel = document.createElement('span');
    headerLabel.textContent = source.label;
    header.appendChild(headerLabel);
    const optionsEl = document.createElement('div');
    optionsEl.className = 'pc-field-dropdown-options';
    dropdown.appendChild(header);
    dropdown.appendChild(optionsEl);

    wrap.appendChild(input);
    wrap.appendChild(toggle);
    wrap.appendChild(dropdown);
    td.appendChild(wrap);
}

// Opens/populates `fieldKey`'s dropdown-card for whichever row's
// toggle was just clicked — same option-building logic as the Add
// Partner form's own per-field blocks (pcFetchEscalationLevelOptions
// wiring above), generalized to work off the clicked toggle's own
// closest wrapper instead of fixed element ids.
function pcOpenEscalationFieldDropdown(toggle) {
    const fieldKey = toggle.dataset.pcDropdownToggle;
    const source = PC_FIELD_DROPDOWN_SOURCES[fieldKey];
    const wrap = toggle.closest('.pc-field-with-dropdown');
    if (!source || !wrap) return;
    const input = wrap.querySelector('input');
    const dropdown = wrap.querySelector('.pc-field-dropdown-card');
    const optionsEl = wrap.querySelector('.pc-field-dropdown-options');

    if (dropdown.style.display === 'block') {
        dropdown.style.display = 'none';
        toggle.classList.remove('is-open');
        return;
    }
    pcCloseAllEscalationFieldDropdowns();

    source.fetch().then(function (values) {
        const current = input.value.trim();
        optionsEl.innerHTML = '';

        const blankBtn = document.createElement('button');
        blankBtn.type = 'button';
        blankBtn.className = 'pc-field-dropdown-option pc-field-dropdown-option-blank' + (!current ? ' is-selected' : '');
        const blankLabel = document.createElement('span');
        blankLabel.className = 'pc-field-dropdown-option-label';
        blankLabel.textContent = '(Blank)';
        const blankCheck = document.createElement('span');
        blankCheck.className = 'pc-field-dropdown-option-check';
        blankCheck.innerHTML = PC_CHECK_ICON_SVG;
        blankBtn.appendChild(blankLabel);
        blankBtn.appendChild(blankCheck);
        blankBtn.addEventListener('click', function () {
            input.value = '';
            dropdown.style.display = 'none';
            toggle.classList.remove('is-open');
        });
        optionsEl.appendChild(blankBtn);

        if (!values.length) {
            const empty = document.createElement('div');
            empty.className = 'pc-field-dropdown-empty';
            empty.textContent = source.empty;
            optionsEl.appendChild(empty);
        } else {
            values.forEach(function (v) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'pc-field-dropdown-option' + (v === current ? ' is-selected' : '');
                const label = document.createElement('span');
                label.className = 'pc-field-dropdown-option-label';
                label.textContent = v;
                const check = document.createElement('span');
                check.className = 'pc-field-dropdown-option-check';
                check.innerHTML = PC_CHECK_ICON_SVG;
                btn.appendChild(label);
                btn.appendChild(check);
                btn.addEventListener('click', function () {
                    input.value = v;
                    dropdown.style.display = 'none';
                    toggle.classList.remove('is-open');
                });
                optionsEl.appendChild(btn);
            });
        }
        dropdown.style.display = 'block';
        toggle.classList.add('is-open');
    });
}

function pcCloseAllEscalationFieldDropdowns() {
    document.querySelectorAll('#pcPartnerContactsModalBody .pc-field-dropdown-card').forEach(function (d) {
        d.style.display = 'none';
    });
    document.querySelectorAll('#pcPartnerContactsModalBody .pc-field-selector-btn.is-open').forEach(function (t) {
        t.classList.remove('is-open');
    });
}

// One delegated pair of listeners for every row's Level/Matrix
// dropdown, wired once at load instead of per-row — see
// pcBuildEscalationDropdownCell()'s own comment for why.
document.addEventListener('click', function (event) {
    const toggle = event.target.closest('#pcPartnerContactsModalBody [data-pc-dropdown-toggle]');
    if (toggle) {
        event.stopPropagation();
        pcOpenEscalationFieldDropdown(toggle);
        return;
    }
    if (!event.target.closest('#pcPartnerContactsModalBody .pc-field-with-dropdown')) {
        pcCloseAllEscalationFieldDropdowns();
    }
});

// Swaps one row from display mode into inline-editable inputs — same
// fields update_contact_only() accepts (Level, Matrix, Contact Name,
// Role, Phone, Email, Remark), one plain text <input> per cell, no
// separate popup on top of this one. Inputs live directly in the
// <td>s (not inside a <form> — a <form> isn't valid as a <tr>'s child
// and browsers silently hoist it out, which risks breaking the table
// layout), so Save/Cancel are wired as plain button click handlers
// below rather than a form submit. Level/Matrix get the same "choose
// an existing value" dropdown picker the Add Partner form's own
// fields have (requested — free text still works, but existing
// values are one click away instead of needing to be retyped exactly).
function pcStartEditEscalationRow(contactId) {
    const c = pcEscalationContacts[contactId];
    const tbody = document.getElementById('pcPartnerContactsModalBody');
    const tr = tbody ? tbody.querySelector('tr[data-contact-id="' + contactId + '"]') : null;
    if (!c || !tr) return;

    PC_MINI_COLUMNS.forEach(function (col) {
        const td = tr.querySelector('td[data-field="' + col.key + '"]');
        if (!td) return;
        td.innerHTML = '';
        if (PC_FIELD_DROPDOWN_SOURCES[col.key]) {
            pcBuildEscalationDropdownCell(td, col.key, c[col.key]);
            return;
        }
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'pc-escalation-edit-input';
        input.dataset.field = col.key;
        input.value = c[col.key] || '';
        td.appendChild(input);
    });

    const actionsTd = tr.querySelector('.pc-escalation-td-actions');
    actionsTd.innerHTML = '';
    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'pc-mini-action-btn pc-escalation-action-save';
    saveBtn.title = 'Save';
    saveBtn.innerHTML = '<i class="ti ti-check"></i>';
    saveBtn.addEventListener('click', function () { pcSaveEscalationRow(contactId); });

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'pc-mini-action-btn pc-escalation-action-cancel';
    cancelBtn.title = 'Cancel';
    cancelBtn.innerHTML = '<i class="ti ti-x"></i>';
    cancelBtn.addEventListener('click', function () { pcCancelEditEscalationRow(contactId); });

    actionsTd.appendChild(saveBtn);
    actionsTd.appendChild(cancelBtn);

    tr.classList.add('pc-escalation-row-editing');
    const firstInput = tr.querySelector('td[data-field="contact_name"] input');
    if (firstInput) firstInput.focus();

    // Enter saves, Escape cancels — same as every other single-row
    // inline edit UX, without needing a real <form> to get that for
    // free from native submit/reset.
    tr.querySelectorAll('.pc-escalation-edit-input').forEach(function (input) {
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') { event.preventDefault(); pcSaveEscalationRow(contactId); }
            if (event.key === 'Escape') { event.preventDefault(); pcCancelEditEscalationRow(contactId); }
        });
    });
}

function pcCancelEditEscalationRow(contactId) {
    const c = pcEscalationContacts[contactId];
    const tbody = document.getElementById('pcPartnerContactsModalBody');
    const tr = tbody ? tbody.querySelector('tr[data-contact-id="' + contactId + '"]') : null;
    if (!c || !tr) return;
    const fresh = pcRenderEscalationRow(c);
    tbody.replaceChild(fresh, tr);
}

// update_contact_only() (same endpoint the split-panel mini-table's
// Edit popup posts to) requires contact_name/contact_role/
// phone_number/email non-empty — checked client-side first so a blank
// required field shakes in place instead of a round trip just to find
// out "missing_fields".
const PC_ESCALATION_REQUIRED = ['contact_name', 'contact_role', 'phone_number', 'email'];

function pcSaveEscalationRow(contactId) {
    const tbody = document.getElementById('pcPartnerContactsModalBody');
    const tr = tbody ? tbody.querySelector('tr[data-contact-id="' + contactId + '"]') : null;
    if (!tr) return;

    const values = {};
    let firstInvalid = null;
    PC_MINI_COLUMNS.forEach(function (col) {
        const input = tr.querySelector('td[data-field="' + col.key + '"] input');
        const value = input ? input.value.trim() : '';
        values[col.key] = value;
        if (!firstInvalid && PC_ESCALATION_REQUIRED.indexOf(col.key) !== -1 && !value) {
            firstInvalid = input;
        }
    });
    if (firstInvalid) {
        firstInvalid.classList.remove('is-shake');
        void firstInvalid.offsetWidth; // restart the animation if it's already mid-shake
        firstInvalid.classList.add('is-shake');
        firstInvalid.focus();
        return;
    }

    const buttons = tr.querySelectorAll('.pc-escalation-td-actions button');
    buttons.forEach(function (b) { b.disabled = true; });

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const username = localStorage.getItem(PC_USERNAME_KEY) || window.NOC_DEFAULT_ACK_USERNAME || '';
    const params = Object.assign({
        csrf_token: csrfToken,
        partner_id: pcEscalationPartner.id,
        contact_id: contactId,
        partner_name: pcEscalationPartner.name,
        partner_type: pcEscalationPartner.type,
        username: username,
    }, values);

    fetch(window.NOC_PARTNER_UPDATE_CONTACT_ONLY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(params).toString(),
    })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            buttons.forEach(function (b) { b.disabled = false; });
            if (!data.ok) {
                tr.querySelectorAll('.pc-escalation-edit-input').forEach(function (input) {
                    input.classList.add('is-shake');
                });
                return;
            }
            pcEscalationContacts[contactId] = Object.assign({ contact_id: contactId }, data);
            const fresh = pcRenderEscalationRow(pcEscalationContacts[contactId]);
            tbody.replaceChild(fresh, tr);
            fresh.classList.add('pc-escalation-row-flash');
            setTimeout(function () { fresh.classList.remove('pc-escalation-row-flash'); }, 700);
            // Keeps the split-panel mini-table's own copy of this same
            // contact (if its "Add Contact" panel is open on this
            // partner right now) from showing stale values too.
            if (pcMiniContacts[contactId]) {
                pcUpdateMiniContactRow(pcEscalationContacts[contactId]);
            }
        })
        .catch(function () {
            buttons.forEach(function (b) { b.disabled = false; });
            tr.querySelectorAll('.pc-escalation-edit-input').forEach(function (input) {
                input.classList.add('is-shake');
            });
        });
}

// Copy icon shown per cell (always visible on touch/coarse-pointer
// devices, fades in on hover elsewhere — see .pc-escalation-copy-btn
// in tables.css) — clicking it copies that cell's raw value (not the
// truncated/displayed text, there isn't any truncation here anyway)
// to the clipboard and flips to a checkmark for a second as
// confirmation.
//
// navigator.clipboard requires a secure context (HTTPS, or
// http://localhost) — it's silently undefined on a plain-HTTP LAN
// address, which is exactly how a touch-screen NOC display usually
// reaches this app. Falling back to the older execCommand('copy')
// (via a temporary offscreen textarea) is what actually makes Copy
// work there instead of doing nothing with no error at all.
function pcCopyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(value);
    }
    return new Promise(function (resolve, reject) {
        const textarea = document.createElement('textarea');
        textarea.value = value;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        try {
            document.execCommand('copy') ? resolve() : reject();
        } catch (e) {
            reject(e);
        } finally {
            document.body.removeChild(textarea);
        }
    });
}

function pcMakeCopyButton(value) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pc-escalation-copy-btn';
    btn.title = 'Copy';
    // Both icons exist in the DOM at once, stacked — toggling
    // .is-copied crossfades between them via CSS (see
    // .pc-escalation-copy-btn .ti-copy/.ti-check in tables.css)
    // instead of an instant innerHTML swap.
    btn.innerHTML = '<i class="ti ti-copy"></i><i class="ti ti-check"></i>';
    let resetTimer = null;
    btn.addEventListener('click', function (event) {
        event.stopPropagation();
        pcCopyText(value).then(function () {
            clearTimeout(resetTimer);
            btn.classList.add('is-copied');
            resetTimer = setTimeout(function () {
                btn.classList.remove('is-copied');
            }, 1000);
        });
    });
    return btn;
}

function pcClosePartnerContactsModal() {
    const overlay = document.getElementById('pcPartnerContactsOverlay');
    if (overlay) overlay.style.display = 'none';
}

// Whole-row click delegation — clicking any column opens the popup
// above, EXCEPT the Actions column and any cell that already has its
// own click behavior (the Actions column's buttons, Email's mailto:
// link), which keep doing what they already do instead of being
// overridden.
(function () {
    const tbody = document.getElementById('pc-tbody');
    if (!tbody) return;
    tbody.addEventListener('click', function (event) {
        const row = event.target.closest('.pc-record-row');
        if (!row) return;
        if (event.target.closest('.pc-grid-td-actions')) return;
        if (event.target.closest('a, button')) return;
        pcOpenPartnerContactsModal(row.dataset.partnerId, row.dataset.partnerName, row.dataset.partnerType);
    });
})();
