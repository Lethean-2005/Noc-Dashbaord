// Mentor Sites composer cards. Both cards are real <form> elements
// (app/templates/mentor/index.html) posting to app/routes/mentor.py;
// this script only handles the client-side preview (file chip, code
// chips) and triggers the actual form submit on Upload/Add.
(function () {
    // ── Card 1: import file (dropzone + file row + Upload) ─────
    const uploadCard = document.getElementById('uploadCard');
    if (uploadCard) {
        const fi = document.getElementById('fileInput');
        const fileBtn = document.getElementById('fileBtn');
        const fileChip = document.getElementById('fileChip');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const fileClear = document.getElementById('fileClear');
        const uploadBtn = document.getElementById('uploadBtn');

        function reflectFile() {
            if (fi.files.length) {
                const f = fi.files[0];
                fileName.textContent = f.name;
                fileSize.textContent = f.size >= 1048576
                    ? (f.size / 1048576).toFixed(1) + ' MB'
                    : Math.max(1, Math.round(f.size / 1024)) + ' KB';
                fileChip.hidden = false;
            } else {
                fileChip.hidden = true;
            }
            uploadBtn.disabled = !fi.files.length;
        }

        fileBtn.addEventListener('click', () => fi.click());
        fi.addEventListener('change', reflectFile);
        fileClear.addEventListener('click', () => { fi.value = ''; reflectFile(); });

        ['dragenter', 'dragover'].forEach(ev =>
            uploadCard.addEventListener(ev, e => { e.preventDefault(); uploadCard.classList.add('drag'); }));
        ['dragleave', 'dragend'].forEach(ev =>
            uploadCard.addEventListener(ev, e => { e.preventDefault(); uploadCard.classList.remove('drag'); }));
        uploadCard.addEventListener('drop', e => {
            e.preventDefault(); uploadCard.classList.remove('drag');
            if (e.dataTransfer.files && e.dataTransfer.files.length) {
                fi.files = e.dataTransfer.files; reflectFile();
            }
        });

        uploadBtn.addEventListener('click', () => {
            if (fi.files.length) uploadCard.requestSubmit();
        });
    }

    // ── Card 2: typed site-code chips + Add ─────────────────────
    const composer = document.getElementById('composer');
    if (!composer) return;
    const chipArea = document.getElementById('chipArea');
    const chipList = document.getElementById('chipList');
    const input = document.getElementById('codeInput');
    const submitBtn = document.getElementById('importBtn');

    let codes = [];

    function renderChips() {
        chipList.innerHTML = '';
        codes.forEach(code => {
            const chip = document.createElement('span');
            chip.className = 'mc-chip';
            chip.appendChild(document.createTextNode(code));
            const x = document.createElement('button');
            x.type = 'button';
            x.className = 'mc-chip-x';
            x.title = 'Remove ' + code;
            x.textContent = '×';
            x.addEventListener('click', () => {
                codes = codes.filter(c => c !== code);
                renderChips();
            });
            chip.appendChild(x);
            chipList.appendChild(chip);
        });
        submitBtn.disabled = codes.length === 0;
    }

    function commitInput(text) {
        (text || '').split(/[^A-Za-z0-9_-]+/).forEach(tok => {
            const code = tok.trim().toUpperCase();
            if (code && !codes.includes(code)) codes.push(code);
        });
        input.value = '';
        renderChips();
    }

    chipArea.addEventListener('click', () => input.focus());
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
            e.preventDefault();
            commitInput(input.value);
        } else if (e.key === 'Backspace' && !input.value && codes.length) {
            codes.pop();
            renderChips();
        }
    });
    input.addEventListener('paste', e => {
        e.preventDefault();
        commitInput((e.clipboardData || window.clipboardData).getData('text'));
    });
    input.addEventListener('blur', () => { if (input.value.trim()) commitInput(input.value); });

    submitBtn.addEventListener('click', () => {
        if (input.value.trim()) commitInput(input.value);
        if (!codes.length) return;
        document.getElementById('siteCodesInput').value = codes.join(',');
        composer.requestSubmit();
    });
})();

// ── Delete confirmation modal (per-row Remove + Clear All) ─────────
// Both buttons carry data-confirm-form/-title/-desc instead of submitting
// directly (Remove) or using a native confirm() popup (Clear All was
// previously onsubmit="return confirm(...)"). One shared modal is reused
// for every row instead of one per site, since only one can ever be open
// at a time.
(function () {
    const overlay = document.getElementById('mentorConfirmOverlay');
    if (!overlay) return;
    const titleEl = document.getElementById('mentorConfirmTitle');
    const descEl = document.getElementById('mentorConfirmDesc');
    const cancelBtn = document.getElementById('mentorConfirmCancel');
    const okBtn = document.getElementById('mentorConfirmOk');
    let targetForm = null;

    function openModal(trigger) {
        targetForm = document.getElementById(trigger.dataset.confirmForm);
        if (!targetForm) return;
        titleEl.textContent = trigger.dataset.confirmTitle || 'Confirm';
        descEl.textContent = trigger.dataset.confirmDesc || '';
        overlay.hidden = false;
    }

    function closeModal() {
        overlay.hidden = true;
        targetForm = null;
    }

    document.querySelectorAll('[data-confirm-form]').forEach(function (trigger) {
        trigger.addEventListener('click', function () { openModal(trigger); });
    });

    cancelBtn.addEventListener('click', closeModal);
    okBtn.addEventListener('click', function () {
        if (targetForm) targetForm.requestSubmit();
        closeModal();
    });
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !overlay.hidden) closeModal();
    });
})();

// ── Auto-dismiss any notice banner (Success/Warning) after 10s ─────
// Two real bugs fixed here: (1) .mentor-alert has its own `display: flex`
// rule at the same specificity as the browser's default [hidden] {
// display: none } — the author rule wins (loads after the UA
// stylesheet), so setting .hidden alone left an invisible box still
// taking up its full layout space. Set display:none directly instead.
// (2) the notice is rendered server-side from query params
// (?added=/?duplicate=/etc.) — hiding it client-side never touched
// those, so refreshing re-requested the same URL and the server drew it
// right back. Strip them via history.replaceState() (same pattern
// app.js already uses for its own ?highlight= param) once dismissed.
(function () {
    const alerts = document.querySelectorAll('.mentor-alert');
    if (!alerts.length) return;

    alerts.forEach(function (alertEl) {
        setTimeout(function () {
            alertEl.style.transition = 'opacity 0.3s ease';
            alertEl.style.opacity = '0';
            setTimeout(function () { alertEl.style.display = 'none'; }, 300);
        }, 10000);
    });

    setTimeout(function () {
        const params = new URLSearchParams(window.location.search);
        ['added', 'duplicate', 'invalid', 'error'].forEach((key) => params.delete(key));
        const query = params.toString();
        window.history.replaceState({}, '', window.location.pathname + (query ? '?' + query : ''));
    }, 10300);
})();
