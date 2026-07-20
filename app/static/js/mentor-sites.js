// Mentor Sites composer cards — cosmetic only. There's no mentor_sites
// table or upload endpoint yet, so typing/dropping just updates the
// on-page preview; Upload/Add explain that via the notification modal
// instead of silently doing nothing.
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
            if (typeof showModal === 'function') {
                showModal('Not Available', 'File import is not wired up to a backend yet — this is a style-only preview.');
            }
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
        if (typeof showModal === 'function') {
            showModal('Not Available', 'Adding sites is not wired up to a backend yet — this is a style-only preview.');
        }
    });
})();
