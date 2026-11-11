// Search each guide once; hide topic groups without matches.
(function () {
    'use strict';
    const input = document.getElementById('helpSearchInput');
    if (!input) return;
    const guides = Array.from(document.querySelectorAll('.help-home-topic .help-guide-link'));
    const groups = Array.from(document.querySelectorAll('.help-home-topic'));
    const status = document.getElementById('helpSearchStatus');
    const empty = document.getElementById('helpNoResults');
    const countLabel = document.getElementById('helpGuideCount');
    const popular = document.getElementById('helpPopular');
    const clear = document.getElementById('helpClearSearch');
    function search() {
        const query = input.value.trim().toLowerCase();
        const terms = query.split(/\s+/).filter(Boolean);
        let count = 0;
        guides.forEach(function (link) {
            const text = (link.dataset.search || link.textContent).toLowerCase();
            const matches = terms.every(function (term) { return text.includes(term); });
            link.parentElement.hidden = !matches;
            if (matches) count++;
        });
        groups.forEach(function (group) {
            group.hidden = !Array.from(group.querySelectorAll('li')).some(function (row) { return !row.hidden; });
        });
        empty.hidden = count !== 0;
        popular.hidden = !!query;
        countLabel.textContent = count + (count === 1 ? ' guide' : ' guides');
        status.textContent = query ? count + (count === 1 ? ' guide found' : ' guides found') : '';
    }
    input.addEventListener('input', search);
    clear.addEventListener('click', function () { input.value = ''; search(); input.focus(); });
})();
