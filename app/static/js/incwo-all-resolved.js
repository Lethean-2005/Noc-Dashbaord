// Refresh this cached incident table without losing the operator's search/scroll.
document.addEventListener('DOMContentLoaded', function () {
    const wrap = document.getElementById('incwoAllResolvedTable');
    if (!wrap) return;
    const seconds = Number(wrap.dataset.refreshSeconds);
    const interval = (seconds > 0 ? seconds : 300) * 1000;
    let loading = false;
    async function refresh() {
        if (loading || document.hidden) return;
        loading = true;
        try {
            const response = await fetch(location.href, {cache:'no-store', headers:{'X-Drilldown-Refresh':'1'}});
            if (!response.ok) return;
            const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
            const incoming = doc.getElementById('incwoAllResolvedTable');
            if (!incoming) return;
            const body = incoming.querySelector('tbody');
            if (!body) return;
            const top = wrap.scrollTop, left = wrap.scrollLeft;
            const pageX = window.scrollX, pageY = window.scrollY;
            wrap.querySelector('tbody').replaceWith(body);
            const header = wrap.previousElementSibling;
            const nextHeader = incoming.previousElementSibling;
            ['.alarm-subtitle-btn', '.alarm-row-count'].forEach(function (selector) {
                const current = header.querySelector(selector), next = nextHeader.querySelector(selector);
                if (current && next) current.textContent = next.textContent;
            });
            if (window.NocTableSearch) window.NocTableSearch(wrap);
            wrap.scrollTop = top; wrap.scrollLeft = left;
            window.scrollTo(pageX, pageY);
        } catch (_) { /* Keep the last valid table; the next scheduled refresh retries. */ }
        finally { loading = false; }
    }
    window.setInterval(refresh, interval);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
});
