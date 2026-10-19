# Cambodia geo data — raw sources

Raw source files for the Map View's location search
(`app/static/js/map-view.js`, `MapViewService`). Not read by the running
app directly — the processed versions actually served live in
`app/static/data/`:

| Raw source (here) | Processed into | How |
|---|---|---|
| `CambodiaCommuneBoundaries.geojson` | `app/static/data/cambodia-commune-boundaries.geojson` | Used as-is, copied directly — already the right shape (one feature per commune, with `ADM1_EN`/`ADM2_EN`/`ADM3_EN` on every feature, so province/district/commune all resolve from this one file with no extra matching step). |
| `CambodiaVillagesList2025.csv` | `app/static/data/cambodia-villages.json` | Trimmed to just `commune_code`/`village_en`/`village_kh` (province_code/district_code/village_code dropped — unused, since province/district context is resolved from the matched commune instead) and converted to JSON. |
| `CambodiaProvinceBoundaries.geojson` (25 features) | **not used yet** | Same UN OCHA/HDX family as the commune file, but pre-dissolved — one real standalone polygon per province, instead of `map-view.js`'s current approach of visually assembling many small commune polygons together for the "Provinces" search result. Swapping to this would give a cleaner outline (no internal commune seams) for province-level results specifically. |
| `CambodiaDistrictBoundaries.geojson` (197 features) | **not used yet** | Same idea, pre-dissolved single polygon per district — same potential swap for the "Districts" search result. |

Villages have no shape or coordinate in this dataset (or any other found
— MEF's own API included) — `commune_code` here is the boundary file's
`ADM3_PCODE` with its `"KH"` country prefix stripped (e.g. boundary
`"KH010202"` ↔ CSV `"010202"`), confirmed by direct comparison. ~93% of
villages resolve to a real commune this way; the rest have genuine code
drift between the two data sources and are silently skipped rather than
shown as a broken result — see `buildVillageIndex()` in `map-view.js`.

`cambodia-260818.osm.pbf` (a full OpenStreetMap data extract) was tried
as a possible source for real village shapes — abandoned. OSM only has
23 real village polygons nationwide (vs. 14,576 official villages above)
and no shared ID with `CambodiaVillagesList2025.csv`, so linking the two
would need fragile fuzzy name-matching with a ~0.4% exact-match rate.
Not worth it; not used anywhere in the app.

Kept here for provenance/reprocessing, not committed to git (see
`.gitignore`) — the processed files under `app/static/data/` are the
ones that actually ship.
