# Map View — color scheme

Every site is plotted individually, no clustering — dense areas overlap
at low zoom, zoom in to separate them.

## Site dot colors

Based on `site_cache.status`, with `is_down` (open Site Down incident)
overriding all of them. Defined in `map-view.js`'s `DOT_COLORS`/
`DEFAULT_DOT_COLOR`/`DOWN_COLOR`, mirrored in `map-view.css`'s
`.map-dot-*` classes.

| Color | Hex | Meaning |
|---|---|---|
| 🔴 Red | `#ef4444` | `is_down` — open Site Down incident (overrides status below) |
| 🟢 Green | `#10b981` | `status = on_air` |
| 🔵 Blue | `#0487e2` | `status = planned` |
| ⚪ Grey | `#94a3b8` | anything else — "Other" |

## Location search section titles

Province/District/Commune/Village result groups in the location search
dropdown — color is on the section title only, not per-row.

| Color | Hex | Level |
|---|---|---|
| 🔴 Red | `#ef4444` | Province |
| 🟣 Violet | `#8b5cf6` | District |
| 🔵 Blue | `#2563eb` | Commune |
| 🟠 Amber | `#f59e0b` | Village |
