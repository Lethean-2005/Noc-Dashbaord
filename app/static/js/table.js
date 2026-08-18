// Shared table column sort, used by any page's clickable headers, plus the
// card-header collapse toggle and blank-cell dash fill.
let _sortCol = -1, _sortAsc = true;
function sortTable(col) {
  const table = document.querySelector('.alarm-table');
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr')).filter(r => !r.querySelector('.empty-row'));
  if (!rows.length) return;
  _sortAsc = (_sortCol === col) ? !_sortAsc : true;
  _sortCol = col;
  rows.sort((a, b) => {
    const av = a.cells[col]?.innerText.trim() || '';
    const bv = b.cells[col]?.innerText.trim() || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    const cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : av.localeCompare(bv);
    return _sortAsc ? cmp : -cmp;
  });
  rows.forEach(r => tbody.appendChild(r));
  table.querySelectorAll('th').forEach((th, i) => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (i === col) th.classList.add(_sortAsc ? 'sort-asc' : 'sort-desc');
  });
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.card-header').forEach(header => {
    header.addEventListener('click', () => {
      header.closest('.card').classList.toggle('card-collapsed');
    });
  });

  // Fill blank cells in every table with an em-dash so nothing reads empty
  // — but only truly empty cells (no element children at all). A cell
  // holding an icon-only button (e.g. the Mentor Site table's delete
  // button) has empty textContent too since SVGs render graphically, not
  // as text; without the children.length check, td.textContent = '—'
  // would wipe out that button entirely and replace it with a plain dash.
  document.querySelectorAll('.alarm-table tbody td').forEach(td => {
    if (!td.classList.contains('empty-row') && td.children.length === 0 && td.textContent.trim() === '') {
      td.textContent = '—';
    }
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
  document.querySelectorAll('.alarm-table-wrap').forEach(wrap => {
    const table = wrap.querySelector('.alarm-table');
    const header = wrap.previousElementSibling;
    if (!table || !header || !header.classList.contains('alarm-header')) return;
    const countEl = header.querySelector('.alarm-row-count');

    const rows = Array.from(table.querySelectorAll('tbody tr')).filter(r => !r.querySelector('.empty-row'));
    if (!rows.length) return;
    // Precomputed once, not per keystroke — .textContent (unlike
    // .innerText) doesn't force a layout reflow, so typing stays smooth
    // even on a few hundred rows.
    const rowText = rows.map(r => r.textContent.toLowerCase());

    const search = document.createElement('input');
    search.type = 'text';
    search.placeholder = 'Search records...';
    search.className = 'alarm-search';
    header.insertBefore(search, header.firstChild);

    let debounceTimer;
    search.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const q = search.value.trim().toLowerCase();
        let visible = 0;
        rows.forEach((row, i) => {
          const match = !q || rowText[i].includes(q);
          row.style.display = match ? '' : 'none';
          if (match) visible++;
        });
        if (countEl) countEl.textContent = `${visible} record${visible === 1 ? '' : 's'}`;
      }, 120);
    });
  });
});
