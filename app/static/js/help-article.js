// Build article anchors from existing headings without rewriting the content.
(function () {
    'use strict';
    const content = document.getElementById('helpArticleContent');
    const toc = document.getElementById('helpArticleToc');
    if (!content || !toc) return;
    const headings = Array.from(content.querySelectorAll('h3, h4, .help-subhead')).filter(function (heading) { return heading.textContent.trim(); });
    const links = new Map();
    const fragment = document.createDocumentFragment();
    headings.forEach(function (heading, index) {
        if (!heading.id) heading.id = 'article-section-' + (index + 1);
        const link = document.createElement('a');
        link.href = '#' + heading.id;
        link.textContent = heading.textContent.trim();
        fragment.appendChild(link);
        links.set(heading.id, link);
    });
    if (headings.length) toc.replaceChildren(fragment);
    function activate(id) {
        links.forEach(function (link, key) {
            link.classList.toggle('is-active', key === id);
            if (key === id) link.setAttribute('aria-current', 'location');
            else link.removeAttribute('aria-current');
        });
    }
    if (headings.length) activate(headings[0].id);
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(function (entries) {
            const visible = entries.filter(function (entry) { return entry.isIntersecting; });
            if (visible.length) activate(visible[0].target.id);
        }, {rootMargin: '-85px 0px -65% 0px', threshold: 0});
        headings.forEach(function (heading) { observer.observe(heading); });
    }
    toc.addEventListener('click', function (event) {
        const link = event.target.closest('a');
        if (link) activate(link.hash.slice(1));
    });
    const button = document.querySelector('.help-docs-menu');
    const sidebar = document.getElementById('helpDocsSidebar');
    if (button && sidebar) button.addEventListener('click', function () {
        const expanded = button.getAttribute('aria-expanded') !== 'true';
        button.setAttribute('aria-expanded', String(expanded));
        sidebar.classList.toggle('is-open', expanded);
    });
    const current = sidebar && sidebar.querySelector('[aria-current="page"]');
    if (current && window.matchMedia('(min-width: 761px)').matches) {
        const offset = current.offsetTop - sidebar.offsetTop;
        sidebar.scrollTop = Math.max(0, offset - sidebar.clientHeight / 2);
    }
    if (location.hash) {
        const target = headings.find(function (heading) { return '#' + heading.id === location.hash; });
        if (target) target.scrollIntoView({block: 'start'});
    }
})();
