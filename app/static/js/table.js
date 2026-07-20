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
  document.querySelectorAll('.alarm-table tbody td').forEach(td => {
    if (!td.classList.contains('empty-row') && td.textContent.trim() === '') {
      td.textContent = '—';
    }
  });
});
