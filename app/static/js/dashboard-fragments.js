// Cancel superseded filter requests and preserve filters owned by other cards.
(function () {
    const requests = new Map();
    function controlledNames(form) {
        return Array.from(form.elements).filter(function (input) {
            return input.name && input.type !== 'hidden' && input.type !== 'submit';
        }).map(function (input) { return input.name; });
    }
    function searchForForm(form, clear) {
        const params = new URLSearchParams(window.location.search);
        const names = new Set(controlledNames(form));
        names.forEach(function (name) { params.delete(name); });
        if (!clear) {
            const values = new FormData(form);
            names.forEach(function (name) {
                values.getAll(name).forEach(function (value) { if (value !== '') params.append(name, value); });
            });
        }
        const query = params.toString();
        return query ? '?' + query : '';
    }
    async function replace(options) {
        let target = document.querySelector(options.selector);
        if (!target) return;
        const ongoing = requests.get(options.selector);
        if (ongoing && ongoing.requestUrl === options.url) return;
        const baseline = new URLSearchParams(window.location.search);
        const requested = new URLSearchParams(options.search);
        const changedNames = new Set([...baseline.keys(), ...requested.keys()]);
        for (const name of changedNames) {
            if (JSON.stringify(baseline.getAll(name)) === JSON.stringify(requested.getAll(name))) changedNames.delete(name);
        }
        const previous = requests.get(options.selector);
        if (previous) previous.abort();
        const controller = new AbortController();
        controller.requestUrl = options.url;
        requests.set(options.selector, controller);
        target.setAttribute('aria-busy', 'true');
        try {
            const response = await fetch(options.url, { signal: controller.signal });
            if (!response.ok) throw new Error('The dashboard could not update. Please try again.');
            const html = await response.text();
            if (requests.get(options.selector) !== controller) return;
            if (options.replaceRoot) {
                const holder = document.createElement('div');
                holder.innerHTML = html.trim();
                if (!holder.firstElementChild) throw new Error('The dashboard returned an empty response.');
                const replacement = holder.firstElementChild;
                target.replaceWith(replacement);
                target = replacement;
            } else target.innerHTML = html;
            const merged = new URLSearchParams(window.location.search);
            changedNames.forEach(function (name) {
                merged.delete(name);
                requested.getAll(name).forEach(function (value) { merged.append(name, value); });
            });
            const query = merged.toString();
            window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash);
            if (options.onUpdated) options.onUpdated();
        } catch (error) {
            if (error.name !== 'AbortError' && requests.get(options.selector) === controller) {
                if (typeof window.showModal === 'function') window.showModal('Unable to update', error.message);
            }
        } finally {
            if (requests.get(options.selector) === controller) {
                target.removeAttribute('aria-busy');
                requests.delete(options.selector);
            }
        }
    }
    window.NocDashboardFragments = { replace: replace, searchForForm: searchForForm };
})();
