// Lightweight calendar date-picker — no external library, matching the
// project's existing "vanilla JS only" approach (see app.js's top comment).
//
// Wires any [data-date-picker] wrapper (see drilldown/alarms.html) into a
// clickable field: a visible "trigger" button shows the chosen date, and
// clicking it opens a calendar popup (month header with prev/next arrows,
// Su-Sa weekday row, day grid, filled circle on the selected day). Picking
// a day writes the ISO date into the wrapper's hidden <input>, which is
// what actually gets submitted by the surrounding filter form.
(function () {
    const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    const DAY_NAMES = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

    function pad(n) { return String(n).padStart(2, '0'); }
    function toISO(y, m, d) { return `${y}-${pad(m + 1)}-${pad(d)}`; }
    function formatDisplay(y, m, d) { return `${d} ${MONTH_NAMES[m].slice(0, 3)} ${y}`; }

    function renderCalendar(popup, state, onPick, today) {
        popup.innerHTML = '';

        const header = document.createElement('div');
        header.className = 'dp-header';

        const prev = document.createElement('button');
        prev.type = 'button';
        prev.className = 'dp-nav';
        prev.innerHTML = '<i class="ti ti-chevron-left"></i>';
        prev.addEventListener('click', function () {
            state.month -= 1;
            if (state.month < 0) { state.month = 11; state.year -= 1; }
            renderCalendar(popup, state, onPick, today);
        });

        const monthLabel = document.createElement('span');
        monthLabel.className = 'dp-month-label';
        monthLabel.textContent = `${MONTH_NAMES[state.month]} ${state.year}`;

        const next = document.createElement('button');
        next.type = 'button';
        next.className = 'dp-nav';
        next.innerHTML = '<i class="ti ti-chevron-right"></i>';
        next.addEventListener('click', function () {
            state.month += 1;
            if (state.month > 11) { state.month = 0; state.year += 1; }
            renderCalendar(popup, state, onPick, today);
        });

        header.appendChild(prev);
        header.appendChild(monthLabel);
        header.appendChild(next);
        popup.appendChild(header);

        const weekRow = document.createElement('div');
        weekRow.className = 'dp-week-row';
        DAY_NAMES.forEach(function (name) {
            const cell = document.createElement('span');
            cell.className = 'dp-weekday';
            cell.textContent = name;
            weekRow.appendChild(cell);
        });
        popup.appendChild(weekRow);

        const grid = document.createElement('div');
        grid.className = 'dp-grid';
        const firstWeekday = new Date(state.year, state.month, 1).getDay();
        const daysInMonth = new Date(state.year, state.month + 1, 0).getDate();

        for (let i = 0; i < firstWeekday; i++) {
            const blank = document.createElement('span');
            blank.className = 'dp-day dp-day-blank';
            grid.appendChild(blank);
        }
        for (let day = 1; day <= daysInMonth; day++) {
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'dp-day';
            cell.textContent = day;
            const sel = state.selected;
            if (sel && sel.year === state.year && sel.month === state.month && sel.day === day) {
                cell.classList.add('dp-day-selected');
            } else if (today && today.year === state.year && today.month === state.month && today.day === day) {
                cell.classList.add('dp-day-today');
            }
            cell.addEventListener('click', function () { onPick(state.year, state.month, day); });
            grid.appendChild(cell);
        }
        popup.appendChild(grid);
    }

    function initField(field) {
        const trigger = field.querySelector('.dp-trigger');
        const triggerText = field.querySelector('.dp-trigger-text');
        const hidden = field.querySelector('input[type="hidden"]');
        if (!trigger || !triggerText || !hidden) return;

        const popup = document.createElement('div');
        popup.className = 'dp-popup';
        popup.hidden = true;
        field.appendChild(popup);

        const now = new Date();
        const today = { year: now.getFullYear(), month: now.getMonth(), day: now.getDate() };
        const parts = hidden.value ? hidden.value.split('-').map(Number) : null;
        const state = {
            year: parts ? parts[0] : today.year,
            month: parts ? parts[1] - 1 : today.month,
            selected: parts ? { year: parts[0], month: parts[1] - 1, day: parts[2] } : null,
        };

        function pick(y, m, d) {
            state.selected = { year: y, month: m, day: d };
            hidden.value = toISO(y, m, d);
            triggerText.textContent = formatDisplay(y, m, d);
            popup.hidden = true;
        }

        renderCalendar(popup, state, pick, today);

        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            const willOpen = popup.hidden;
            // Close any other open picker before opening this one.
            document.querySelectorAll('.dp-popup').forEach(function (p) { p.hidden = true; });
            popup.hidden = !willOpen;
        });

        popup.addEventListener('click', function (e) { e.stopPropagation(); });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-date-picker]').forEach(initField);
    });

    // One shared outside-click listener closes any open picker, regardless
    // of how many [data-date-picker] fields are on the page.
    document.addEventListener('click', function () {
        document.querySelectorAll('.dp-popup').forEach(function (p) { p.hidden = true; });
    });
})();
