/* Downstream circuit choices follow section 2 of this report. */
(function () {
    'use strict';
    var monthlyRows = document.getElementById('irOutageRows');
    if (!monthlyRows) return;
    var targets = ['irServicesOutageRows', 'irFailureRows', 'irCreditRows'].map(function (id) {
        return document.getElementById(id);
    }).filter(Boolean);
    var scheduled = false;
    var nextIdentity = 0;
    function scheduleRefresh() {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(function () {
            scheduled = false;
            refresh();
        });
    }
    function monthlyCircuitsChanged(event) {
        if (event.target.matches('[name="outage_circuit"]')) scheduleRefresh();
    }
    function refresh() {
        var entries = [];
        var inputs = new Map();
        monthlyRows.querySelectorAll('[name="outage_circuit"]').forEach(function (input) {
            if (!input.dataset.circuitIdentity) input.dataset.circuitIdentity = String(++nextIdentity);
            var entry = { id: input.dataset.circuitIdentity, value: input.value.trim() };
            inputs.set(entry.id, entry);
            if (entry.value && !entries.some(function (item) { return item.value.toLowerCase() === entry.value.toLowerCase(); })) entries.push(entry);
        });
        var signature = JSON.stringify(Array.from(inputs.values()));
        targets.forEach(function (body) {
            var changed = false;
            body.querySelectorAll('[name="outage_circuit"], [name="outage_circuit_id"], [name="react_circuit_id"], [name="credit_circuit"]').forEach(function (field) {
                if (field.dataset.circuitOptions === signature) return;
                changed = true;
                var value = field.value.trim();
                var identity = field.dataset.circuitIdentity;
                if (identity && !inputs.has(identity)) {
                    // Removing a monthly circuit also removes its dependent report rows.
                    field.closest('tr').remove();
                    return;
                }
                if (!identity) {
                    var initial = entries.find(function (entry) { return entry.value.toLowerCase() === value.toLowerCase(); });
                    if (!initial && !value) initial = entries[0];
                    if (initial) identity = initial.id;
                }
                if (identity) value = inputs.get(identity).value;
                var multiple = entries.length > 1;
                var tag = multiple ? 'SELECT' : 'INPUT';
                if (field.tagName !== tag) {
                    var replacement = document.createElement(tag.toLowerCase());
                    replacement.name = field.name;
                    replacement.className = field.className;
                    replacement.setAttribute('aria-label', 'Circuit ID from Monthly Outage Statistics');
                    var focused = document.activeElement === field;
                    field.replaceWith(replacement);
                    field = replacement;
                    if (focused) field.focus();
                }
                field.dataset.circuitOptions = signature;
                if (identity) field.dataset.circuitIdentity = identity;
                var valid = !value && !identity || entries.some(function (entry) { return entry.value === value; });
                field.setCustomValidity(valid ? '' : 'Enter the circuit ID in section 2 or select a monthly outage circuit.');
                if (multiple) {
                    var options = document.createDocumentFragment();
                    entries.forEach(function (entry) {
                        var option = document.createElement('option');
                        option.textContent = entry.value;
                        option.value = entry.value;
                        options.appendChild(option);
                    });
                    if (!valid) {
                        var missing = document.createElement('option');
                        missing.value = value;
                        missing.textContent = value || 'Enter circuit ID in section 2';
                        // Keep the selected value in Draft form data; custom validity still blocks Final.
                        options.appendChild(missing);
                    }
                    field.replaceChildren(options);
                    field.value = value;
                } else {
                    field.type = 'text';
                    field.readOnly = true;
                    field.setAttribute('aria-readonly', 'true');
                    field.placeholder = 'Enter circuit ID in section 2';
                    field.value = value;
                }
            });
            if (changed) body.dispatchEvent(new Event('change', { bubbles: true }));
        });
    }
    monthlyRows.addEventListener('input', monthlyCircuitsChanged);
    monthlyRows.addEventListener('change', monthlyCircuitsChanged);
    new MutationObserver(scheduleRefresh).observe(monthlyRows, { childList: true });
    targets.forEach(function (body) {
        body.addEventListener('change', function (event) {
            var field = event.target;
            if (!field.matches('select[name="outage_circuit_id"], select[name="react_circuit_id"], select[name="credit_circuit"]')) return;
            var input = Array.from(monthlyRows.querySelectorAll('[name="outage_circuit"]')).find(function (item) { return item.value.trim() === field.value; });
            if (input) {
                field.dataset.circuitIdentity = input.dataset.circuitIdentity;
                field.setCustomValidity('');
            }
        });
        new MutationObserver(scheduleRefresh).observe(body, { childList: true });
    });
    refresh();
}());
