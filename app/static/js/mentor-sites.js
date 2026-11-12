// File selection, real upload progress, and accessible site-code chips.
(function () {
    const uploadCard = document.getElementById('uploadCard');
    if (uploadCard) {
        const fi = document.getElementById('fileInput');
        const fileBtn = document.getElementById('fileBtn');
        const chip = document.getElementById('fileChip');
        const clear = document.getElementById('fileClear');
        const submit = document.getElementById('uploadBtn');
        const status = document.getElementById('mentorFileStatus');
        const error = document.getElementById('mentorFileError');
        const progress = document.getElementById('mentorUploadProgress');
        const percent = document.getElementById('mentorFilePercent');
        const complete = document.getElementById('mentorFileComplete');
        const receiptKey = 'mentor-import-completed';
        let busy = false, dragDepth = 0, validationVersion = 0, validated = false;
        try {
            const receipt = JSON.parse(sessionStorage.getItem(receiptKey) || 'null');
            sessionStorage.removeItem(receiptKey);
            if (receipt && Date.now() - receipt.time < 60000 && ['added', 'duplicate', 'invalid'].some(function (key) { return new URLSearchParams(location.search).has(key); })) {
                document.getElementById('fileName').textContent = receipt.name;
                document.getElementById('fileSize').textContent = receipt.size;
                status.textContent = receipt.status;
                progress.hidden = false; progress.value = 100;
                percent.hidden = false; percent.textContent = '100%';
                complete.toggleAttribute('hidden', !receipt.success);
                chip.hidden = false;
            }
        } catch (_) { /* Storage is optional; the import still works when unavailable. */ }
        function showError(message) {
            error.textContent = message || '';
            error.hidden = !message;
        }
        function selectFile(file) {
            if (busy) return;
            const version = ++validationVersion;
            validated = false;
            showError('');
            complete.setAttribute('hidden', ''); percent.hidden = true;
            progress.hidden = true;
            progress.value = 0;
            const maximum = Number(uploadCard.dataset.maxUploadBytes);
            if (file && (!file.name.toLowerCase().endsWith('.csv') || !file.size || file.size > maximum)) {
                showError(!file.name.toLowerCase().endsWith('.csv') ? 'Choose a CSV file. You can download the template below.' : !file.size ? 'This file is empty. Choose a CSV containing site codes.' : 'The file exceeds the allowed upload size.');
                fi.value = '';
                chip.hidden = true;
                submit.disabled = true;
                return;
            }
            if (file) {
                const transfer = new DataTransfer();
                transfer.items.add(file);
                fi.files = transfer.files;
                document.getElementById('fileName').textContent = file.name;
                document.getElementById('fileSize').textContent = file.size >= 1048576 ? (file.size / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(file.size / 1024)) + ' KB';
                status.textContent = 'Ready to import';
            } else fi.value = '';
            chip.hidden = !file;
            submit.disabled = true;
            if (file) validateSelectedFile(version);
        }
        async function validateSelectedFile(version) {
            const start = performance.now();
            progress.hidden = false; progress.value = 0;
            percent.hidden = false; percent.textContent = '0%';
            status.textContent = 'Validating file...';
            let finished = false;
            function animate(now) {
                if (version !== validationVersion || finished) return;
                const value = Math.min(95, Math.floor((now - start) / 5000 * 95));
                progress.value = value; percent.textContent = value + '%';
                requestAnimationFrame(animate);
            }
            requestAnimationFrame(animate);
            try {
                const response = await fetch(uploadCard.dataset.validateUrl, {method: 'POST', headers: {'Accept': 'application/json'}, body: new FormData(uploadCard)});
                const result = await response.json();
                await new Promise(function (resolve) { setTimeout(resolve, Math.max(0, 5000 - (performance.now() - start))); });
                if (version !== validationVersion) return;
                finished = true;
                if (!response.ok || !result.valid) throw new Error(result.error || 'File validation failed.');
                validated = true; progress.value = 100; percent.textContent = '100%';
                complete.removeAttribute('hidden');
                complete.setAttribute('aria-label', 'File validated');
                status.textContent = result.ready ? 'File validated - ready to import' : 'File validated - sites already configured';
                submit.disabled = false;
            } catch (error) {
                if (version !== validationVersion) return;
                finished = true; progress.hidden = true; percent.hidden = true;
                complete.setAttribute('hidden', ''); submit.disabled = true;
                status.textContent = 'Validation failed';
                showError(error.message || 'Unable to validate this file. Please select it again.');
            }
        }
        fileBtn.addEventListener('click', function () { if (!busy) fi.click(); });
        fi.addEventListener('change', function () { selectFile(fi.files[0]); });
        clear.addEventListener('click', function () { selectFile(null); fileBtn.focus(); });
        uploadCard.addEventListener('dragenter', function (e) { e.preventDefault(); if (!busy) { dragDepth++; uploadCard.classList.add('drag'); } });
        uploadCard.addEventListener('dragover', function (e) { e.preventDefault(); });
        uploadCard.addEventListener('dragleave', function (e) { e.preventDefault(); if (--dragDepth <= 0) { dragDepth = 0; uploadCard.classList.remove('drag'); } });
        uploadCard.addEventListener('drop', function (e) {
            e.preventDefault(); dragDepth = 0; uploadCard.classList.remove('drag');
            if (busy) return;
            if (e.dataTransfer.files.length !== 1) { selectFile(null); showError('Choose one CSV file at a time.'); return; }
            selectFile(e.dataTransfer.files[0]);
        });
        uploadCard.addEventListener('submit', function (event) {
            event.preventDefault();
            if (busy || !validated || !fi.files.length) return;
            busy = true;
            showError('');
            submit.disabled = true; clear.disabled = true; fileBtn.disabled = true;
            uploadCard.setAttribute('aria-busy', 'true');
            status.textContent = 'Importing validated site codes...';
            const xhr = new XMLHttpRequest();
            xhr.open('POST', uploadCard.action);
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.timeout = 60000;
            function failed(message) {
                busy = false; submit.disabled = false; clear.disabled = false; fileBtn.disabled = false;
                uploadCard.removeAttribute('aria-busy');
                complete.setAttribute('hidden', ''); percent.hidden = true;
                status.textContent = 'Ready to retry';
                progress.hidden = true; progress.value = 0;
                showError(message);
            }
            xhr.addEventListener('load', function () {
                if (xhr.status < 200 || xhr.status >= 300) {
                    let message = xhr.status === 413 ? 'This file exceeds the server upload limit.' : 'The import could not finish. Please try again.';
                    try { message = JSON.parse(xhr.responseText).error || message; } catch (_) { /* Non-JSON server error. */ }
                    failed(message); return;
                }
                const result = new URL(xhr.responseURL || uploadCard.action, window.location.href);
                if (result.origin !== window.location.origin) { failed('Unexpected import response. Please refresh and try again.'); return; }
                if (result.searchParams.get('error')) { failed(result.searchParams.get('error')); return; }
                progress.value = 100;
                const success = !result.searchParams.get('invalid');
                percent.textContent = '100%';
                complete.toggleAttribute('hidden', !success);
                status.textContent = !success ? 'Complete - review invalid site codes' : Number(result.searchParams.get('added')) > 0 ? 'Validated and imported' : 'Validated - sites already configured';
                try {
                    sessionStorage.setItem(receiptKey, JSON.stringify({time: Date.now(), name: document.getElementById('fileName').textContent, size: document.getElementById('fileSize').textContent, status: status.textContent, success: success}));
                } catch (_) { /* Completion feedback does not depend on browser storage. */ }
                window.setTimeout(function () { window.location.assign(result.href); }, 700);
            });
            xhr.addEventListener('error', function () { failed('Connection interrupted. Your file is kept here; try again.'); });
            xhr.addEventListener('timeout', function () { failed('The import timed out. Please try again.'); });
            xhr.send(new FormData(uploadCard));
        });
    }

    const composer = document.getElementById('composer');
    if (!composer) return;
    const area = document.getElementById('chipArea');
    const list = document.getElementById('chipList');
    const input = document.getElementById('codeInput');
    const submit = document.getElementById('importBtn');
    const clear = document.getElementById('clearCodesBtn');
    const status = document.getElementById('mentorCodeStatus');
    let codes = [];
    function refresh() {
        list.replaceChildren();
        codes.forEach(function (code) {
            const chip = document.createElement('span');
            chip.className = 'mc-chip';
            chip.appendChild(document.createTextNode(code));
            const remove = document.createElement('button');
            remove.type = 'button'; remove.className = 'mc-chip-x';
            remove.setAttribute('aria-label', 'Remove ' + code); remove.title = 'Remove ' + code;
            remove.textContent = '\u00d7';
            remove.addEventListener('click', function () { codes = codes.filter(function (value) { return value !== code; }); refresh(); input.focus(); });
            chip.appendChild(remove); list.appendChild(chip);
        });
        submit.disabled = codes.length === 0 && !input.value.trim();
        clear.disabled = codes.length === 0 && !input.value;
        status.textContent = codes.length ? codes.length + ' site code' + (codes.length === 1 ? '' : 's') + ' ready' : 'No site codes entered';
    }
    function commit(text) {
        const invalid = [];
        String(text || '').split(/[\s,;]+/).forEach(function (value) {
            const code = value.trim().toUpperCase();
            if (code && !/^[A-Za-z0-9_-]+$/.test(code)) invalid.push(code);
            else if (code && !codes.includes(code)) codes.push(code.toUpperCase());
        });
        input.value = ''; input.setCustomValidity(''); refresh();
        if (invalid.length) status.textContent = 'Enter site codes using letters, numbers, hyphens or underscores.';
    }
    area.addEventListener('click', function () { input.focus(); });
    input.addEventListener('beforeinput', function (event) {
        if (event.data && /[^A-Za-z0-9_,;\s-]/.test(event.data)) {
            event.preventDefault();
            status.textContent = 'Use letters, numbers, hyphens or underscores; leading zeroes are preserved.';
        }
    });
    input.addEventListener('input', function () {
        const invalid = /[^A-Za-z0-9_,;\s-]/.test(input.value);
        input.setCustomValidity(invalid ? 'Enter a valid site code.' : '');
        submit.disabled = invalid || (!codes.length && !input.value.trim());
        clear.disabled = !codes.length && !input.value;
    });
    input.addEventListener('keydown', function (e) {
        if (['Enter', ',', ' '].includes(e.key)) { e.preventDefault(); commit(input.value); }
        else if (e.key === 'Backspace' && !input.value && codes.length) { codes.pop(); refresh(); }
    });
    input.addEventListener('paste', function (e) { e.preventDefault(); commit(e.clipboardData.getData('text')); });
    input.addEventListener('blur', function () { if (input.value.trim()) commit(input.value); });
    clear.addEventListener('click', function () { codes = []; input.value = ''; refresh(); input.focus(); });
    composer.addEventListener('submit', function (e) {
        if (input.value.trim()) commit(input.value);
        if (!codes.length) { e.preventDefault(); input.focus(); return; }
        document.getElementById('siteCodesInput').value = codes.join(',');
        submit.disabled = true;
        composer.setAttribute('aria-busy', 'true');
    });
    refresh();
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
