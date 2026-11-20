// Card-header collapse toggle and blank-cell dash fill, shared by any page
// using .alarm-table.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.card-header').forEach(header => {
    // .no-collapse (the 3 dashboard graph cards) intentionally skip the
    // collapse toggle — they have no chevron affordance for it, so a
    // header click doing an invisible collapse would look broken.
    if (header.classList.contains('no-collapse')) return;
    header.addEventListener('click', () => {
      header.closest('.card').classList.toggle('card-collapsed');
    });
  });

  function fillBlankCells(table) {
    table.querySelectorAll('tbody td').forEach(td => {
      if (!td.closest('.empty-row') && td.children.length === 0 && !td.textContent.trim()) {
        td.textContent = '\u2014';
      }
    });
  }
  const initiallyFilledTables = new WeakSet();
  document.querySelectorAll('.alarm-table').forEach(table => {
    fillBlankCells(table);
    initiallyFilledTables.add(table);
  });

  // Drilldown/table row search — filters .alarm-table rows by substring
  // match across the whole row's text, and updates that table's own
  // .alarm-row-count to reflect only the currently-visible rows. Inserted
  // as the very first element of the .alarm-header immediately preceding
  // each .alarm-table-wrap (not a page-wide document.querySelector) —
  // a page can have more than one .alarm-header (e.g. mentor/index.html:
  // the page's own title header, then a separate one right before the
  // "Configured Mentor Sites" table), and querying globally grabbed
  // whichever came first in the DOM regardless of which table it actually
  // belonged to.
  function initTableSearch(wrap) {
    const table = wrap.querySelector('.alarm-table');
    if (!table) return;
    if (initiallyFilledTables.has(table)) initiallyFilledTables.delete(table);
    else fillBlankCells(table);
    let header = wrap.previousElementSibling;
    while (header && header.classList.contains('row-cap-notice')) header = header.previousElementSibling;
    if (!header || !header.classList.contains('alarm-header')) return;
    const countEl = header.querySelector('.alarm-row-count');

    const rows = Array.from(table.querySelectorAll('tbody tr')).filter(r => !r.classList.contains('empty-row') && !r.querySelector('td.empty-row'));
    const existingSearch = header.querySelector('input.alarm-search');
    if (existingSearch) clearTimeout(existingSearch._nocSearchTimer);
    if (!rows.length) {
      if (existingSearch) { existingSearch.oninput = null; existingSearch.disabled = true; }
      return;
    }
    // Precomputed once, not per keystroke — .textContent (unlike
    // .innerText) doesn't force a layout reflow, so typing stays smooth
    // even on a few hundred rows.
    const rowText = rows.map(r => r.textContent.toLowerCase());

    const search = header.querySelector('input.alarm-search') || document.createElement('input');
    search.disabled = false;
    search.type = 'text';
    search.placeholder = 'Search records...';
    search.className = 'alarm-search';
    header.insertBefore(search, header.firstChild);

    table.querySelectorAll('.search-empty-row').forEach(row => row.remove());
    const noMatches = document.createElement('tr');
    noMatches.className = 'empty-row search-empty-row';
    noMatches.hidden = true;
    const noMatchesCell = document.createElement('td');
    const heading = table.tHead && table.tHead.rows[0];
    noMatchesCell.colSpan = heading
      ? Array.from(heading.cells).reduce((total, cell) => total + cell.colSpan, 0)
      : rows[0].cells.length;
    const emptyTemplate = document.getElementById('tableEmptyStateTemplate');
    if (emptyTemplate) noMatchesCell.appendChild(emptyTemplate.content.cloneNode(true));
    else noMatchesCell.textContent = 'No results found';
    noMatches.appendChild(noMatchesCell);
    table.tBodies[0].appendChild(noMatches);

    let previousQuery;
    function applySearch() {
        const q = search.value.trim().toLowerCase();
        if (q === previousQuery) return;
        previousQuery = q;
        let visible = 0;
        rows.forEach((row, i) => {
          const match = !q || rowText[i].includes(q);
          const display = match ? '' : 'none';
          if (row.style.display !== display) row.style.display = display;
          if (match) visible++;
        });
        noMatches.hidden = visible !== 0;
        if (countEl) countEl.textContent = `${visible} record${visible === 1 ? '' : 's'}`;
    }
    search.oninput = () => {
      clearTimeout(search._nocSearchTimer);
      search._nocSearchTimer = setTimeout(applySearch, 120);
    };
    if (search.value.trim()) applySearch();
  }
  window.NocTableSearch = initTableSearch;
  document.querySelectorAll('.alarm-table-wrap').forEach(initTableSearch);
});
