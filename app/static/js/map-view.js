// Map View page — plots every site read from site_cache (already filtered
// server-side to rows with a real, non-zero p_lat/p_lon; see
// app/services/map/map_view_service.py) as a colored dot on a Leaflet map.
// Every site is shown individually, all the time, at every zoom level —
// no marker clustering (removed per explicit request; dense areas like
// Phnom Penh will visually overlap at low zoom, which is the accepted
// tradeoff for always seeing every real marker rather than a bundled
// count).
document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("mapView");
  if (!mapEl) return;

  const dataEl = document.getElementById("map-view-sites-data");
  const sites = dataEl ? JSON.parse(dataEl.textContent) : [];
  const popsDataEl = document.getElementById("map-view-pops-data");
  const pops = popsDataEl ? JSON.parse(popsDataEl.textContent) : [];
  // Read by the boundary export's fetch() POST — CSRFProtect rejects a
  // POST with no valid token, and fetch has no <form> to carry one.
  const CSRF_TOKEN =
    document.querySelector('meta[name="csrf-token"]')?.content || "";

  // Cambodia, roughly centered — every site in this dataset falls inside
  // the country, so this is a sane default view before any marker is
  // clicked.
  const map = L.map(mapEl).setView([12.5657, 104.991], 7);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  // Every up site (the vast majority — ~4,300 of ~4,340 at any given
  // time) is drawn on this single shared canvas instead of Leaflet's
  // default SVG renderer, which would otherwise create one real <path>
  // DOM element per marker. At this dataset's size that was the actual
  // cause of a 15s+ page load (confirmed via profiling) — thousands of
  // SVG nodes is dramatically more expensive to create/layout/paint than
  // one canvas everything is drawn onto. Down sites are the one
  // exception (see createSiteMarker below): they stay on the map's
  // default SVG renderer because setSiteDownBlink's CSS blink animation
  // needs a real marker._path element to toggle a class on — a canvas
  // marker has no such element. Down sites are always a small minority,
  // so this costs nothing in practice.
  const canvasRenderer = L.canvas();

  // Builds one site's marker with the right renderer for its current
  // is_down state (see canvasRenderer comment above) — shared by the
  // initial full render and refreshSites()'s live upgrade path, so a
  // site that goes down after load gets a real blink-capable marker
  // instead of silently staying on canvas forever.
  function createSiteMarker(site) {
    const marker = L.circleMarker([site.lat, site.lon], {
      radius: 6,
      weight: 1,
      color: "#ffffff",
      fillColor: siteDotColor(site),
      fillOpacity: 0.9,
      className: site.is_down ? "site-dot-down" : "",
      ...(site.is_down ? {} : { renderer: canvasRenderer }),
    });
    marker.bindPopup(popupHtml(site));
    return marker;
  }

  const DOT_COLORS = { on_air: "#10b981", planned: "#0487e2" };
  const DEFAULT_DOT_COLOR = "#94a3b8";
  // A currently-open Site Down incident (site.is_down, from the
  // already-synced incident_site_down cache) always wins over the normal
  // status color — a down site is the most urgent thing to see on this
  // map, regardless of its on_air/planned lifecycle status.
  const DOWN_COLOR = "#ef4444";
  const POP_COLOR = "#94a3b8";
  // Same Streamline host every drilldown template already links Incident
  // IDs to (see e.g. drilldown/incident_site_down.html) — a down site's
  // incident ID link goes straight to the real record there instead of
  // this app's own drilldown page.
  const STREAMLINE_INCIDENT_URL = (numericId) =>
    `${document.body.dataset.streamlineBase}/incident/form/${numericId}`;
  // POP's pro_owner (TBL_POP.PRO_OWNER) badge color — falls back to gray
  // for any value not in this map instead of hiding the badge entirely.
  const OWNER_BADGE_COLORS = { Telcotech: "#eab308", Ezecom: "#a855f7" };
  const DEFAULT_OWNER_BADGE_COLOR = "#94a3b8";
  // Same per-level colors as the location search's own section headers
  // (.map-search-group-title-province/-district/-commune/-village in
  // map-view.css) — reused here so the boundary card's title reads the
  // same way regardless of which level you picked.
  const LEVEL_TITLE_COLORS = {
    province: "#ef4444",
    district: "#8b5cf6",
    commune: "#2563eb",
    village: "#f59e0b",
  };

  function siteDotColor(site) {
    return site.is_down
      ? DOWN_COLOR
      : DOT_COLORS[site.status] || DEFAULT_DOT_COLOR;
  }

  // Toggles the CSS blink animation (site-dot-down, map-view.css) on a
  // down site's actual rendered <path> — marker.setStyle() only touches
  // Leaflet's own style options (fill/stroke/etc.), never the element's
  // className, so a down site picked up on refreshSites() needs this
  // done by hand instead of just passing className through options again.
  function setSiteDownBlink(marker, isDown) {
    if (!marker._path) return;
    marker._path.classList.toggle("site-dot-down", !!isDown);
  }

  // Same owner colors as the popup badge (OWNER_BADGE_COLORS) — falls
  // back to POP_COLOR (grey) for a blank/unknown pro_owner.
  function popDotColor(pop) {
    return OWNER_BADGE_COLORS[pop.pro_owner] || POP_COLOR;
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function coordinateDisplay(value) {
    if (value === null || value === undefined || String(value).trim() === "") return "_";
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(6) : "_";
  }

  function popupHtml(site) {
    const rows = [
      ["Status", site.status],
      ["Grade", site.site_grade],
      ["NMS", site.nms],
      ["Province", site.province],
      ["District", site.district],
      ["Commune", site.commune],
      ["Village", site.village],
      ["Hub Site", site.hub_site],
      ["Latitude", coordinateDisplay(site.lat)],
      ["Longitude", coordinateDisplay(site.lon)],
    ]
      .filter(([, value]) => value)
      .map(
        ([label, value]) =>
          `<div class="map-popup-row"><strong>${label}:</strong> ${escapeHtml(value)}</div>`,
      )
      .join("");
    const subtitle =
      site.site_name && site.site_name !== site.name
        ? `<div class="map-popup-row">${escapeHtml(site.site_name)}</div>`
        : "";
    const downBanner = site.is_down
      ? '<div class="map-popup-down-banner">⚠ Site Down</div>'
      : "";
    const outage =
      site.is_down && site.occurred_at
        ? `<div class="map-popup-row"><strong>Occurred At:</strong> ${escapeHtml(site.occurred_at)}</div>`
        : "";
    const incidentLink =
      site.is_down && site.incident_id
        ? '<div class="map-popup-row"><strong>Incident:</strong> ' +
          (site.incident_numeric_id
            ? `<a href="${STREAMLINE_INCIDENT_URL(site.incident_numeric_id)}" target="_blank" rel="noopener">${escapeHtml(site.incident_id)}</a>`
            : escapeHtml(site.incident_id)) +
          "</div>"
        : "";
    return `<div class="map-popup-title">${escapeHtml(site.name || "Unknown site")}</div>${subtitle}${downBanner}${outage}${incidentLink}${rows}`;
  }

  // Same "banner right under the title" spot as a down site's ⚠ Site Down
  // banner, just no icon — a plain color-coded owner label instead.
  function ownerBadgeHtml(proOwner) {
    if (!proOwner) return "";
    const color = OWNER_BADGE_COLORS[proOwner] || DEFAULT_OWNER_BADGE_COLOR;
    return `<div class="map-popup-owner-badge" style="background:${color}">${escapeHtml(proOwner)}</div>`;
  }

  function popupHtmlForPop(pop) {
    const rows = [
      ["Code", pop.code],
      ["Type", pop.type],
      ["Province", pop.province],
      ["District", pop.district],
      ["Commune", pop.commune],
      ["Latitude", coordinateDisplay(pop.lat)],
      ["Longitude", coordinateDisplay(pop.lon)],
    ]
      .filter(([, value]) => value)
      .map(
        ([label, value]) =>
          `<div class="map-popup-row"><strong>${label}:</strong> ${escapeHtml(value)}</div>`,
      )
      .join("");
    return `<div class="map-popup-title">${escapeHtml(pop.name || "Unknown POP")}</div>${ownerBadgeHtml(pop.pro_owner)}${rows}`;
  }

  function haversineMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  // Nearest entry (from either sites or pops) to a typed lat/lon — lets a
  // coordinate search resolve against real plotted data instead of
  // dropping a blank, unlabeled pin. Straight linear scan; simple and
  // fast enough for a once-per-debounced-keystroke lookup.
  function findNearestAmong(candidates, lat, lon) {
    let entry = null;
    let distanceM = Infinity;
    candidates.forEach((candidate) => {
      const d = haversineMeters(lat, lon, candidate.lat, candidate.lon);
      if (d < distanceM) {
        distanceM = d;
        entry = candidate;
      }
    });
    return { entry, distanceM };
  }

  // Cambodia admin boundaries (province/district/commune shapes) — used
  // by location search below to draw+zoom to a place, separate from the
  // site markers. Lazy-loaded in the background: the source file is
  // 6.6MB (real commune-level polygon detail for the whole country), so
  // it must never block the initial map/marker render. Location search
  // silently has zero results until this resolves; site search works
  // immediately either way.
  const BOUNDARIES_URL = "/static/data/cambodia-commune-boundaries.geojson";
  // Village names/codes only (province_code/district_code/village_code
  // dropped when this was generated from CambodiaVillagesList2025.csv —
  // not needed here, since province/district context comes from whatever
  // commune a village resolves to below). No coordinates, no shape — see
  // buildVillageIndex()'s own comment for why villages resolve to their
  // parent commune's shape rather than having one of their own.
  const VILLAGES_URL = "/static/data/cambodia-villages.json";
  let boundaryIndex = [];
  let villageIndex = [];
  let boundaryLayer = null;
  let coordMarker = null;
  const boundarySitesEl = document.getElementById("mapBoundarySites");
  let boundarySiteMatches = [];
  let boundarySiteEntry = null;

  // Standard ray-casting point-in-polygon test — `ring` is a GeoJSON linear
  // ring, an array of [lng, lat] pairs.
  function pointInRing(lat, lon, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      const crosses =
        yi > lat !== yj > lat &&
        lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
      if (crosses) inside = !inside;
    }
    return inside;
  }

  // ring[0] is the outer boundary, any further rings are holes cut out of it.
  function pointInPolygon(lat, lon, geometry) {
    const polygons =
      geometry.type === "MultiPolygon"
        ? geometry.coordinates
        : [geometry.coordinates];
    return polygons.some(
      ([outer, ...holes]) =>
        pointInRing(lat, lon, outer) &&
        !holes.some((hole) => pointInRing(lat, lon, hole)),
    );
  }

  // Which commune (if any) a typed lat/lon falls inside — lets coordinate
  // search resolve a real Province › District › Commune, not just the
  // nearest site/POP. Linear scan over every commune polygon; only run
  // once per debounced keystroke, so this is fine.
  function findContainingCommune(lat, lon) {
    return (
      boundaryIndex.find(
        (entry) =>
          entry.level === "commune" &&
          entry.features.some((f) => pointInPolygon(lat, lon, f.geometry)),
      ) || null
    );
  }

  // Each raw feature is one commune, carrying its own province (ADM1_EN)
  // and district (ADM2_EN) name — so district/province "shapes" are built
  // here by grouping every commune that shares that parent name, not read
  // as their own pre-drawn polygon (this file only has real standalone
  // shapes at the commune level).
  function buildBoundaryIndex(features) {
    const provinces = new Map();
    const districts = new Map();
    const index = [];

    features.forEach((feature) => {
      const p = feature.properties;
      if (!provinces.has(p.ADM1_EN)) provinces.set(p.ADM1_EN, []);
      provinces.get(p.ADM1_EN).push(feature);

      const districtKey = p.ADM2_EN + "|" + p.ADM1_EN;
      if (!districts.has(districtKey)) {
        districts.set(districtKey, {
          name: p.ADM2_EN,
          province: p.ADM1_EN,
          features: [],
        });
      }
      districts.get(districtKey).features.push(feature);

      index.push({
        level: "commune",
        name: p.ADM3_EN,
        district: p.ADM2_EN,
        province: p.ADM1_EN,
        features: [feature],
      });
    });

    provinces.forEach((feats, name) =>
      index.push({ level: "province", name, features: feats }),
    );
    districts.forEach((d) =>
      index.push({
        level: "district",
        name: d.name,
        province: d.province,
        features: d.features,
      }),
    );

    return index;
  }

  // There's no village shape or coordinate anywhere in any data source
  // found for this (confirmed against the MEF village API and this CSV
  // both) — so a village "result" resolves to its PARENT COMMUNE's real
  // shape instead of its own precise spot. commune_code (this CSV) and
  // ADM3_PCODE (the boundary file) use different code formats — commune_code
  // is the boundary file's ADM3_PCODE with its "KH" country prefix
  // stripped (e.g. boundary "KH010202" <-> village CSV "010202") —
  // confirmed by direct comparison, ~93% of villages resolve this way;
  // the rest have a commune_code with no matching boundary commune (real
  // code drift between the two data sources) and are silently skipped
  // rather than shown as a broken/unclickable result.
  function buildVillageIndex(villages, communeFeatures) {
    const communesByCode = new Map();
    communeFeatures.forEach((feature) => {
      const code = feature.properties.ADM3_PCODE.slice(2);
      if (!communesByCode.has(code)) {
        communesByCode.set(code, {
          district: feature.properties.ADM2_EN,
          province: feature.properties.ADM1_EN,
          features: [],
        });
      }
      communesByCode.get(code).features.push(feature);
    });

    const index = [];
    villages.forEach((v) => {
      const commune = communesByCode.get(v.commune_code);
      if (!commune) return;
      index.push({
        level: "village",
        name: v.village_en,
        district: commune.district,
        province: commune.province,
        features: commune.features,
      });
    });
    return index;
  }

  Promise.all([
    fetch(BOUNDARIES_URL).then((res) => res.json()),
    fetch(VILLAGES_URL).then((res) => res.json()),
  ])
    .then(([geojson, villages]) => {
      boundaryIndex = buildBoundaryIndex(geojson.features);
      villageIndex = buildVillageIndex(villages, geojson.features);
    })
    .catch(() => {
      // Boundaries/villages are an enhancement, not core functionality —
      // a failed fetch just means location search stays empty; site
      // plotting and site search are unaffected.
    });

  function clearBoundary() {
    if (boundaryLayer) {
      map.removeLayer(boundaryLayer);
      boundaryLayer = null;
    }
    if (coordMarker) {
      map.removeLayer(coordMarker);
      coordMarker = null;
    }
    if (boundarySitesEl) {
      boundarySitesEl.hidden = true;
      boundarySitesEl.innerHTML = "";
    }
    boundarySiteMatches = [];
    boundarySiteEntry = null;
  }

  // Computed directly from the raw [lng, lat] coordinates rather than
  // trusting L.geoJSON(...).getBounds() — same manual walk-every-point
  // approach already proven working for this exact "zoom to a drawn
  // boundary" case in the sibling cambodia-dashboard project
  // (lib helpers there: visitCoords()/computeBounds()).
  function computeFeatureBounds(features) {
    let minLat = Infinity,
      minLng = Infinity,
      maxLat = -Infinity,
      maxLng = -Infinity;
    function visit(coords) {
      if (typeof coords[0] === "number") {
        const [lng, lat] = coords;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
      } else {
        coords.forEach(visit);
      }
    }
    features.forEach((f) => visit(f.geometry.coordinates));
    return minLat === Infinity
      ? null
      : [
          [minLat, minLng],
          [maxLat, maxLng],
        ];
  }

  // Every item (site or POP) whose lat/lon falls inside entry's boundary
  // shape — a cheap bounding-box check first (computeFeatureBounds,
  // already computed for fitBounds anyway) so the real point-in-polygon
  // test only runs against items that could plausibly be inside.
  function withinBoundary(entry, bounds, list) {
    const [[minLat, minLng], [maxLat, maxLng]] = bounds;
    return list.filter((item) => {
      if (
        item.lat < minLat ||
        item.lat > maxLat ||
        item.lon < minLng ||
        item.lon > maxLng
      )
        return false;
      return entry.features.some((f) =>
        pointInPolygon(item.lat, item.lon, f.geometry),
      );
    });
  }

  function smallBadgeHtml(text, color) {
    return `<span class="map-search-result-badge" style="background:${color}">${escapeHtml(text)}</span>`;
  }

  // Floating card over the map's right side listing every site AND POP
  // inside the just-drawn boundary — same row markup as the search-result
  // dropdowns (.map-search-result etc., styled in map-view.css), plus a
  // small owner badge on POP rows (same colors as popDotColor()) and a
  // "Site Down" badge on down sites (site.is_down, already cached via
  // incident_site_down — nothing new synced here, just surfaced). Clicking
  // a row opens that entity's real popup (goToSite/goToPop), same as
  // everywhere else.
  function renderBoundarySites(entry) {
    if (!boundarySitesEl) return;
    boundarySiteEntry = entry;
    const bounds = computeFeatureBounds(entry.features);
    let matchedSites = bounds ? withinBoundary(entry, bounds, sites) : [];
    let matchedPops = bounds ? withinBoundary(entry, bounds, pops) : [];

    // Mirror applyFilter()'s own rules so a province search while, say,
    // "Telcotech" is the active ISP filter shows only Telcotech's POPs
    // here too — same subset that's actually plotted on the map right
    // now, not every site/POP regardless of the filter (currentFilter/
    // matchesFilter/matchesPopFilter/ISP_FILTERS are all declared further
    // down but same enclosing DOMContentLoaded scope, ready by call time).
    if (ISP_FILTERS.includes(currentFilter)) {
      matchedSites = [];
      matchedPops = matchedPops.filter((p) =>
        matchesPopFilter(p, currentFilter),
      );
    } else if (currentFilter !== "all") {
      matchedSites = matchedSites.filter((s) =>
        matchesFilter(s, currentFilter),
      );
      matchedPops = [];
    }

    boundarySiteMatches = [
      ...matchedSites.map((s) => ({ ...s, _resultType: "site" })),
      ...matchedPops.map((p) => ({ ...p, _resultType: "pop" })),
    ];
    // Status breakdown grid — same categories as the main status filter
    // dropdown (On Air/Planned/Other/Site Down), 3 columns × 2 rows, each
    // value colored to match its legend dot (DOT_COLORS/DOWN_COLOR/
    // POP_COLOR) so the number reads the same way the dots on the map do.
    const stats = { on_air: 0, planned: 0, other: 0, site_down: 0 };
    matchedSites.forEach((s) => {
      if (s.status === "on_air") stats.on_air++;
      else if (s.status === "planned") stats.planned++;
      else stats.other++;
      if (s.is_down) stats.site_down++;
    });
    const statHtml = (label, value, color) =>
      `<div class="map-boundary-sites-stat"><span class="map-boundary-sites-stat-label">${label}</span>` +
      `<span class="map-boundary-sites-stat-value"${color ? ` style="color:${color}"` : ""}>${value}</span></div>`;
    const statsGrid =
      '<div class="map-boundary-sites-stats">' +
      statHtml("Total", matchedSites.length) +
      statHtml("On Air", stats.on_air, DOT_COLORS.on_air) +
      statHtml("Planned", stats.planned, DOT_COLORS.planned) +
      statHtml("Other", stats.other, DEFAULT_DOT_COLOR) +
      statHtml("Site Down", stats.site_down, DOWN_COLOR) +
      statHtml("POPs", matchedPops.length, POP_COLOR) +
      "</div>";
    // Title shows the level word right after the name ("Prey Veng
    // Province" vs "Prey Veng Commune") — Cambodia's admin names repeat
    // across levels (a commune can share its province's name), so the
    // bare name alone is ambiguous. Color follows the same
    // province/district/commune/village scheme as search results; the
    // breadcrumb under it shows whatever parent context this level has.
    const titleColor = LEVEL_TITLE_COLORS[entry.level];
    const levelLabel = entry.level
      ? entry.level.charAt(0).toUpperCase() + entry.level.slice(1)
      : "";
    const breadcrumb = [entry.district, entry.province]
      .filter(Boolean)
      .join(" › ");
    const header =
      '<div class="map-boundary-sites-header">' +
      "<div>" +
      `<div class="map-boundary-sites-title"${titleColor ? ` style="color:${titleColor}"` : ""}>${escapeHtml(entry.name)}${levelLabel ? " " + escapeHtml(levelLabel) : ""}</div>` +
      (breadcrumb
        ? `<div class="map-boundary-sites-breadcrumb">${escapeHtml(breadcrumb)}</div>`
        : "") +
      statsGrid +
      "</div>" +
      '<button type="button" class="map-boundary-sites-close" aria-label="Close">&times;</button>' +
      "</div>";
    if (!boundarySiteMatches.length) {
      boundarySitesEl.innerHTML =
        header +
        '<div class="map-search-empty">No plotted sites or POPs inside this boundary</div>';
      boundarySitesEl.hidden = false;
      return;
    }
    const rowsHtml = boundarySiteMatches
      .map((entity, index) => {
        const isPop = entity._resultType === "pop";
        const location = [entity.province, entity.district, entity.commune]
          .filter(Boolean)
          .join(" › ");
        const codeLine = isPop ? entity.code || entity.name : entity.name;
        const nameLine = isPop
          ? entity.name !== codeLine
            ? entity.name
            : ""
          : entity.site_name;
        const badge = isPop
          ? entity.pro_owner
            ? smallBadgeHtml(
                entity.pro_owner,
                OWNER_BADGE_COLORS[entity.pro_owner] ||
                  DEFAULT_OWNER_BADGE_COLOR,
              )
            : ""
          : entity.is_down
            ? smallBadgeHtml("Site Down", DOWN_COLOR)
            : "";
        return (
          `<div class="map-search-result" data-result-index="${index}">` +
          `<div class="map-search-result-code">${escapeHtml(codeLine)}${badge}</div>` +
          (nameLine
            ? `<div class="map-search-result-name">${escapeHtml(nameLine)}</div>`
            : "") +
          (location
            ? `<div class="map-search-result-location">${escapeHtml(location)}</div>`
            : "") +
          (isPop
            ? `<div class="map-search-result-pop-tag" style="color:${OWNER_BADGE_COLORS[entity.pro_owner] || DEFAULT_OWNER_BADGE_COLOR}">POP Site</div>`
            : "") +
          "</div>"
        );
      })
      .join("");
    // Export sits in its own fixed footer (outside the scrollable list),
    // same "always reachable, not lost mid-scroll" spot as a report
    // download button in a typical detail-card layout.
    boundarySitesEl.innerHTML =
      header +
      `<div class="map-boundary-sites-list">${rowsHtml}</div>` +
      '<div class="map-boundary-sites-footer">' +
      '<button type="button" class="map-boundary-sites-export"><i class="ti ti-download"></i> Export</button>' +
      "</div>";
    boundarySitesEl.hidden = false;
  }

  // Same styled .xlsx interface as the main map Export button (dark-navy
  // header, borders — see _write_xlsx_sheet() in app/routes/map_view.py),
  // scoped to this boundary's own sites/POPs, 2 sheets ("Site by
  // Province" / "ISP Site by Province"). The point-in-polygon filtering
  // already happened client-side (renderBoundarySites()) — this just
  // ships that already-computed list to the server to format as .xlsx,
  // since building styled Excel output isn't something to do in the
  // browser.
  function exportBoundaryXlsx() {
    if (!boundarySiteEntry || !boundarySiteMatches.length) return;
    const payload = {
      name: boundarySiteEntry.name,
      sites: boundarySiteMatches.filter((e) => e._resultType === "site"),
      pops: boundarySiteMatches.filter((e) => e._resultType === "pop"),
    };
    fetch("/map/export-boundary.xlsx", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF_TOKEN,
      },
      body: JSON.stringify(payload),
    })
      .then((res) => {
        // Without this check, a failed request (expired session, server
        // error, ...) still gets its response body downloaded and forced
        // into a ".xlsx" name — Excel then reports "file format is not
        // valid" because it's really an HTML/JSON error page, not a real
        // workbook. Reject instead so the .catch() below can say so.
        if (!res.ok) throw new Error(`export failed: ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${boundarySiteEntry.name.replace(/[^a-z0-9]+/gi, "_")}_site_by_province.xlsx`;
        link.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => {
        alert("Export failed. Please refresh the page and try again.");
      });
  }

  if (boundarySitesEl) {
    boundarySitesEl.addEventListener("click", (event) => {
      if (event.target.closest(".map-boundary-sites-close")) {
        clearBoundary();
        return;
      }
      if (event.target.closest(".map-boundary-sites-export")) {
        exportBoundaryXlsx();
        return;
      }
      const row = event.target.closest(".map-search-result");
      if (!row) return;
      const entity = boundarySiteMatches[Number(row.dataset.resultIndex)];
      if (!entity) return;
      if (entity._resultType === "pop") goToPop(entity);
      else goToSite(entity);
    });
  }

  function goToLocation(entry) {
    if (entry.level === "coordinate") {
      goToCoordinate(entry, locationSearchInput, locationResultsEl);
      return;
    }
    hideSearchResults(locationResultsEl);
    locationSearchInput.value = entry.name;
    clearBoundary();
    boundaryLayer = L.geoJSON(
      { type: "FeatureCollection", features: entry.features },
      {
        // interactive: false — the boundary is a visual outline only, not
        // a clickable shape; without this, its fill (even at low opacity)
        // still captures clicks/hover meant for a site marker sitting on
        // top of it.
        interactive: false,
        style: {
          color: "#2563eb",
          weight: 2,
          fillColor: "#2563eb",
          fillOpacity: 0.05,
        },
      },
    ).addTo(map);
    // bringToFront()/bringToBack() only exist on individual L.Path layers
    // (each circleMarker), not on a plain L.layerGroup() — markersGroup
    // itself has no such method. Iterate the group's own markers instead,
    // keeping every site dot clickable above the boundary fill (belt and
    // braces alongside interactive: false above).
    markersGroup.eachLayer((layer) => layer.bringToFront());
    const bounds = computeFeatureBounds(entry.features);
    if (bounds) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
    renderBoundarySites(entry);
  }

  const markersGroup = L.layerGroup();
  const markersById = new Map();
  sites.forEach((site) => {
    const marker = createSiteMarker(site);
    markersById.set(site.id, marker);
    markersGroup.addLayer(marker);
  });
  markersGroup.addTo(map);

  // POP markers — a separate layer, off by default, colored by owner
  // (see popDotColor()). Not pre-added to popsGroup here — which markers
  // are in that group is decided per-filter in applyFilter() below, same
  // as sites, so "ISP TELCOTECH"/"ISP EZECOM" can each show just their
  // own subset while "All Status" shows both together.
  const popsGroup = L.layerGroup();
  const popMarkersById = new Map();
  pops.forEach((pop) => {
    const marker = L.circleMarker([pop.lat, pop.lon], {
      radius: 6,
      weight: 1,
      color: "#ffffff",
      fillColor: popDotColor(pop),
      fillOpacity: 0.9,
    });
    marker.bindPopup(popupHtmlForPop(pop));
    popMarkersById.set(pop.id, marker);
  });

  // Two fully independent search boxes — one searches plotted sites (code
  // or name), the other searches Cambodia's admin boundaries
  // (province/district/commune, via boundaryIndex above). Different data
  // sources, different result actions (open a site popup vs. draw+zoom a
  // shape), so they're kept as two separate input/results pairs rather
  // than one merged list.
  const MAX_RESULTS = 15;
  const GOTO_ZOOM = 15; // close enough to read a single site clearly
  // "lat, lon" or "lat lon" — e.g. "12.5657, 104.9910" — typed into the
  // location search box jumps straight to that point instead of matching
  // a place name.
  const COORD_PATTERN = /^(-?\d{1,3}(?:\.\d+)?)[,\s]+(-?\d{1,3}(?:\.\d+)?)$/;
  // Within this distance, a typed coordinate counts as "this IS that site"
  // (opens its real popup) rather than just a plain unlabeled pin.
  const COORD_SITE_MATCH_METERS = 100;

  // Shared by both search boxes — parses a "lat, lon" query and searches
  // ALL plotted locations (sites AND pops, via findNearestAmong) plus
  // which real Province › District › Commune the point falls inside (via
  // findContainingCommune), not just whichever marker is nearest.
  function buildCoordinateEntry(query) {
    const match = query.match(COORD_PATTERN);
    if (!match) return null;
    const lat = Number(match[1]);
    const lon = Number(match[2]);
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
    const nearestSite = findNearestAmong(sites, lat, lon);
    const nearestPop = findNearestAmong(pops, lat, lon);
    const popIsCloser =
      nearestPop.entry &&
      (!nearestSite.entry || nearestPop.distanceM < nearestSite.distanceM);
    return {
      level: "coordinate",
      lat,
      lon,
      name: `${lat}, ${lon}`,
      nearest: popIsCloser ? nearestPop.entry : nearestSite.entry,
      nearestType: popIsCloser ? "pop" : "site",
      nearestDistanceM: popIsCloser
        ? nearestPop.distanceM
        : nearestSite.distanceM,
      containingCommune: findContainingCommune(lat, lon),
    };
  }

  function coordinateLocationLine(entry) {
    return entry.containingCommune
      ? `${escapeHtml(entry.containingCommune.province)} › ${escapeHtml(entry.containingCommune.district)} › ${escapeHtml(entry.containingCommune.name)}`
      : "";
  }

  function coordinateResultHtml(entry) {
    const isMatch =
      entry.nearest && entry.nearestDistanceM <= COORD_SITE_MATCH_METERS;
    const label = entry.nearestType === "pop" ? "POP" : "site";
    const nearestLine = entry.nearest
      ? isMatch
        ? `Matches ${label} ${escapeHtml(entry.nearest.name)}`
        : `Nearest ${label}: ${escapeHtml(entry.nearest.name)} (${Math.round(entry.nearestDistanceM)}m away)`
      : "";
    const subtitle = [coordinateLocationLine(entry), nearestLine]
      .filter(Boolean)
      .map((line) => `<div class="map-search-result-location">${line}</div>`)
      .join("");
    return (
      '<div class="map-search-group-title">Coordinates</div>' +
      '<div class="map-search-result" data-result-index="0">' +
      `<div class="map-search-result-code">Go to ${entry.lat}, ${entry.lon}</div>` +
      subtitle +
      "</div>"
    );
  }

  // Popup for a dropped coordinate pin (no exact match) — click the "Go
  // to nearest..." link to jump there, same as picking it from search
  // (see the document click delegation below).
  function coordMarkerPopupHtml(entry) {
    const locationRow = entry.containingCommune
      ? `<div class="map-popup-row">${coordinateLocationLine(entry)}</div>`
      : "";
    if (!entry.nearest) {
      return (
        `<div class="map-popup-title">${entry.lat}, ${entry.lon}</div>` +
        (locationRow || '<div class="map-popup-row">No nearby location</div>')
      );
    }
    const label = entry.nearestType === "pop" ? "POP" : "site";
    return (
      `<div class="map-popup-title">${entry.lat}, ${entry.lon}</div>${locationRow}` +
      `<div class="map-popup-row">Nearest ${label}: ` +
      `<strong>${escapeHtml(entry.nearest.name)}</strong> (${Math.round(entry.nearestDistanceM)}m away)</div>` +
      '<div class="map-popup-row"><a href="#" class="map-popup-goto-site" ' +
      `data-result-type="${entry.nearestType}" data-site-id="${escapeHtml(entry.nearest.id)}">Go to nearest ${label}</a></div>`
    );
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".map-popup-goto-site");
    if (!link) return;
    event.preventDefault();
    if (link.dataset.resultType === "pop") {
      const pop = pops.find((p) => String(p.id) === link.dataset.siteId);
      if (pop) goToPop(pop);
    } else {
      const site = sites.find((s) => String(s.id) === link.dataset.siteId);
      if (site) goToSite(site);
    }
  });

  // If the nearest location is basically at this exact coordinate, jump
  // to it as a real site/POP (its own popup, same as picking it from
  // search) instead of dropping an unlabeled pin.
  function goToCoordinate(entry, inputEl, resultsEl) {
    hideSearchResults(resultsEl);
    inputEl.value = entry.name;
    clearBoundary();
    if (entry.nearest && entry.nearestDistanceM <= COORD_SITE_MATCH_METERS) {
      if (entry.nearestType === "pop") goToPop(entry.nearest);
      else goToSite(entry.nearest);
      return;
    }
    coordMarker = L.marker([entry.lat, entry.lon]).addTo(map);
    coordMarker.bindPopup(coordMarkerPopupHtml(entry)).openPopup();
    map.setView([entry.lat, entry.lon], GOTO_ZOOM);
  }

  // Closes a results dropdown with the same fade+lift feel it opened
  // with (mapSearchResultsIn, map-view.css) instead of an instant snap —
  // every place that used to do `el.hidden = true` directly for the site/
  // location search results goes through this now, so opening and
  // closing read as one consistent motion. Cancels any close already in
  // flight if the box reopens before it finishes (fast type-clear-type).
  function hideSearchResults(el) {
    if (!el || el.hidden) return;
    clearTimeout(el._pcCloseTimer);
    el.classList.add("is-closing");
    el._pcCloseTimer = setTimeout(() => {
      el.hidden = true;
      el.classList.remove("is-closing");
      el.innerHTML = "";
    }, 120);
  }

  // ---- Site search (code / name) ----
  const searchInput = document.getElementById("mapSearchInput");
  const resultsEl = document.getElementById("mapSearchResults");
  let siteMatches = [];
  let siteCoordEntry = null;

  // Matched fields: site code, site name, and village (site-level data
  // with no shape of its own — see docs/map-view-colors.md's own note on
  // why province/district/commune moved to the location search instead).
  const SITE_SEARCH_FIELDS = ["name", "site_name", "village"];
  const POP_SEARCH_FIELDS = ["name", "code"];

  function siteMatchesQuery(site, query) {
    return SITE_SEARCH_FIELDS.some((field) => {
      const value = site[field];
      return value && value.toLowerCase().includes(query);
    });
  }

  function popMatchesQuery(pop, query) {
    return POP_SEARCH_FIELDS.some((field) => {
      const value = pop[field];
      return value && value.toLowerCase().includes(query);
    });
  }

  function renderSiteResults(query) {
    // Cancel any close still in flight — a fresh render (typing again
    // right after clearing) always wins over a fade-out that was already
    // on its way out.
    clearTimeout(resultsEl._pcCloseTimer);
    resultsEl.classList.remove("is-closing");

    if (!query) {
      hideSearchResults(resultsEl);
      siteMatches = [];
      siteCoordEntry = null;
      return;
    }

    siteCoordEntry = buildCoordinateEntry(query);
    if (siteCoordEntry) {
      siteMatches = [];
      resultsEl.innerHTML = coordinateResultHtml(siteCoordEntry);
      resultsEl.hidden = false;
      return;
    }
    // Capped independently, not combined-then-sliced — a query with many
    // site matches (e.g. "12") would otherwise crowd out every POP match.
    const matchedSites = sites
      .filter((site) => siteMatchesQuery(site, query))
      .slice(0, MAX_RESULTS)
      .map((site) => ({ ...site, _resultType: "site" }));
    const matchedPops = pops
      .filter((pop) => popMatchesQuery(pop, query))
      .slice(0, MAX_RESULTS)
      .map((pop) => ({ ...pop, _resultType: "pop" }));
    siteMatches = [...matchedSites, ...matchedPops];
    if (!siteMatches.length) {
      resultsEl.hidden = false;
      resultsEl.innerHTML =
        '<div class="map-search-empty">No site/POP matches "' +
        escapeHtml(query) +
        '"</div>';
      return;
    }
    resultsEl.innerHTML = siteMatches
      .map((entry, index) => {
        const isPop = entry._resultType === "pop";
        const location = [entry.province, entry.district, entry.commune]
          .filter(Boolean)
          .join(" › ");
        // POP's code is its own "site code" equivalent — shown on top with
        // its name right under it, same layout as a real site's
        // code/site_name pair. Falls back to name alone if a POP has no
        // code, same as a site with no separate site_name.
        const codeLine = isPop ? entry.code || entry.name : entry.name;
        const nameLine = isPop
          ? entry.name !== codeLine
            ? entry.name
            : ""
          : entry.site_name;
        return (
          `<div class="map-search-result" data-result-index="${index}">` +
          `<div class="map-search-result-code">${escapeHtml(codeLine)}</div>` +
          (nameLine
            ? `<div class="map-search-result-name">${escapeHtml(nameLine)}</div>`
            : "") +
          (location
            ? `<div class="map-search-result-location">${escapeHtml(location)}</div>`
            : "") +
          (isPop
            ? `<div class="map-search-result-pop-tag" style="color:${OWNER_BADGE_COLORS[entry.pro_owner] || DEFAULT_OWNER_BADGE_COLOR}">POP Site</div>`
            : "") +
          `</div>`
        );
      })
      .join("");
    resultsEl.hidden = false;
  }

  function goToSite(site) {
    const marker = markersById.get(site.id);
    if (!marker) return;
    hideSearchResults(resultsEl);
    searchInput.value = site.name;
    clearBoundary();
    // A status filter may have hidden this marker — reset to "all" first
    // so it's guaranteed to be on the map to pan/zoom to.
    applyFilter("all");
    map.setView(marker.getLatLng(), GOTO_ZOOM);
    marker.openPopup();
  }

  function goToPop(pop) {
    const marker = popMarkersById.get(pop.id);
    if (!marker) return;
    hideSearchResults(resultsEl);
    searchInput.value = pop.name;
    clearBoundary();
    // A site-status filter (or a different owner's filter) may have this
    // marker's layer off the map — switch to its own owner's filter first
    // (falling back to "pop_no_owner" for a blank/unknown owner) so it's
    // guaranteed visible to pan/zoom to.
    const ownerFilter =
      pop.pro_owner === "Telcotech"
        ? "pop_telcotech"
        : pop.pro_owner === "Ezecom"
          ? "pop_ezecom"
          : "pop_no_owner";
    applyFilter(ownerFilter);
    map.setView(marker.getLatLng(), GOTO_ZOOM);
    marker.openPopup();
  }

  // Clear (×) button — shown once the input has text, clicking it empties
  // the box, hides its results, and refocuses it. Shared by both search
  // boxes below.
  function wireSearchClear(input, clearBtn, onClear) {
    if (!clearBtn) return;
    const toggle = () => {
      clearBtn.hidden = !input.value;
    };
    input.addEventListener("input", toggle);
    toggle();
    clearBtn.addEventListener("click", () => {
      input.value = "";
      clearBtn.hidden = true;
      onClear();
      input.focus();
    });
  }

  let siteDebounceTimer;
  searchInput.addEventListener("input", () => {
    clearTimeout(siteDebounceTimer);
    siteDebounceTimer = setTimeout(
      () => renderSiteResults(searchInput.value.trim().toLowerCase()),
      150,
    );
  });
  wireSearchClear(searchInput, document.getElementById("mapSearchClear"), () =>
    renderSiteResults(""),
  );

  // Clicking back into the box (text still there from before, results
  // already closed after picking one) reopens the same results instead
  // of staying closed until another keystroke — no re-typing needed to
  // see the list again.
  searchInput.addEventListener("focus", () => {
    if (searchInput.value.trim())
      renderSiteResults(searchInput.value.trim().toLowerCase());
  });

  resultsEl.addEventListener("click", (event) => {
    const row = event.target.closest(".map-search-result");
    if (!row) return;
    if (siteCoordEntry) {
      goToCoordinate(siteCoordEntry, searchInput, resultsEl);
      return;
    }
    const entry = siteMatches[Number(row.dataset.resultIndex)];
    if (!entry) return;
    if (entry._resultType === "pop") goToPop(entry);
    else goToSite(entry);
  });

  // ---- Location search (province / district / commune) ----
  const locationSearchInput = document.getElementById("mapLocationSearchInput");
  const locationResultsEl = document.getElementById("mapLocationSearchResults");
  let locationMatches = [];

  function renderLocationResults(query) {
    clearTimeout(locationResultsEl._pcCloseTimer);
    locationResultsEl.classList.remove("is-closing");

    if (!query) {
      hideSearchResults(locationResultsEl);
      locationMatches = [];
      return;
    }

    const coordEntry = buildCoordinateEntry(query);
    if (coordEntry) {
      locationMatches = [coordEntry];
      locationResultsEl.innerHTML = coordinateResultHtml(coordEntry);
      locationResultsEl.hidden = false;
      return;
    }

    // Grouped into sections by level, provinces first — same idea as a
    // typical "Countries / States / Cities" location-search layout: the
    // broadest match surfaces first, since searching "Kam" should show
    // provinces (Kampong Cham, Kampot, ...) before individual communes
    // that merely happen to start with the same letters.
    const PER_SECTION = 6;
    // Exact/starts-with beats merely-contains before the PER_SECTION cutoff
    // below — without this, searching "Kor" (a real commune name, Prey
    // Chhor district, Kampong Cham) buried it past position 6, since 23
    // OTHER communes ("Angkor Ban", "Ankor Chey", "Chikor", "Nokor Thum",
    // "Krakor", ...) all also contain "kor" as a substring somewhere in
    // their name and happen to come first in the data's own order — the
    // actual commune named "Kor" never made it into the truncated list
    // even though it's genuinely in the data. Array.sort is stable, so
    // matches tied on rank keep their original relative order.
    function matchRank(name) {
      const lower = name.toLowerCase();
      if (lower === query) return 0;
      if (lower.startsWith(query)) return 1;
      return 2;
    }
    const byRelevance = (a, b) => matchRank(a.name) - matchRank(b.name);
    const allMatches = boundaryIndex.filter((entry) =>
      entry.name.toLowerCase().includes(query),
    );
    const provinceMatches = allMatches
      .filter((e) => e.level === "province")
      .sort(byRelevance)
      .slice(0, PER_SECTION);
    const districtMatches = allMatches
      .filter((e) => e.level === "district")
      .sort(byRelevance)
      .slice(0, PER_SECTION);
    const communeMatches = allMatches
      .filter((e) => e.level === "commune")
      .sort(byRelevance)
      .slice(0, PER_SECTION);
    // Villages sort last — they're the least precise result (resolves to
    // its parent commune's shape, not its own spot; see
    // buildVillageIndex()'s own comment).
    const villageMatches = villageIndex
      .filter((entry) => entry.name.toLowerCase().includes(query))
      .sort(byRelevance)
      .slice(0, PER_SECTION);
    locationMatches = [
      ...provinceMatches,
      ...districtMatches,
      ...communeMatches,
      ...villageMatches,
    ];

    if (!locationMatches.length) {
      locationResultsEl.hidden = false;
      locationResultsEl.innerHTML = boundaryIndex.length
        ? '<div class="map-search-empty">No province/district/commune/village matches "' +
          escapeHtml(query) +
          '"</div>'
        : '<div class="map-search-empty">Boundaries still loading…</div>';
      return;
    }

    let html = "";
    let index = 0;
    [
      ["Provinces", provinceMatches, "province"],
      ["Districts", districtMatches, "district"],
      ["Communes", communeMatches, "commune"],
      ["Villages", villageMatches, "village"],
    ].forEach(([title, entries, level]) => {
      if (!entries.length) return;
      html += `<div class="map-search-group-title map-search-group-title-${level}">${title}</div>`;
      entries.forEach((entry) => {
        const context = [entry.district, entry.province]
          .filter(Boolean)
          .join(" › ");
        html +=
          `<div class="map-search-result" data-result-index="${index}">` +
          `<div class="map-search-result-code">${escapeHtml(entry.name)}</div>` +
          (context
            ? `<div class="map-search-result-location">${escapeHtml(context)}</div>`
            : "") +
          `</div>`;
        index++;
      });
    });
    locationResultsEl.innerHTML = html;
    locationResultsEl.hidden = false;
  }

  let locationDebounceTimer;
  locationSearchInput.addEventListener("input", () => {
    clearTimeout(locationDebounceTimer);
    locationDebounceTimer = setTimeout(
      () =>
        renderLocationResults(locationSearchInput.value.trim().toLowerCase()),
      150,
    );
  });

  // Same reopen-on-refocus behavior as the site search box above.
  locationSearchInput.addEventListener("focus", () => {
    if (locationSearchInput.value.trim())
      renderLocationResults(locationSearchInput.value.trim().toLowerCase());
  });

  // Clearing the location search also closes the province/district/
  // commune stats card (#mapBoundarySites) it opened — without this the
  // X only closed the now-already-hidden results dropdown (goToLocation
  // hides it the moment a result is picked), leaving the boundary card
  // sitting there with nothing to dismiss it.
  wireSearchClear(
    locationSearchInput,
    document.getElementById("mapLocationSearchClear"),
    () => {
      renderLocationResults("");
      clearBoundary();
    },
  );

  locationResultsEl.addEventListener("click", (event) => {
    const row = event.target.closest(".map-search-result");
    if (!row) return;
    const entry = locationMatches[Number(row.dataset.resultIndex)];
    if (entry) goToLocation(entry);
  });

  document.addEventListener("click", (event) => {
    if (!searchInput.closest(".map-search").contains(event.target))
      hideSearchResults(resultsEl);
    if (!locationSearchInput.closest(".map-search").contains(event.target))
      hideSearchResults(locationResultsEl);
  });

  // Status filter — two separate <details> dropdown cards (see
  // map-view.css), not native <select>s: one for site status, one for ISP
  // POP owner. Both feed the same single currentFilter/applyFilter() below
  // (still mutually exclusive across all options — this is a UI grouping
  // split, not a "combine both filters" redesign). The "N sites plotted"
  // badge next to the title doubles as a reset back to "All Status".
  const statusFilterDetails = document.getElementById("mapStatusFilter");
  const statusFilterLabel = document.getElementById("mapStatusFilterLabel");
  const ispFilterDetails = document.getElementById("mapIspFilter");
  const ispFilterLabel = document.getElementById("mapIspFilterLabel");
  const filterDetailsList = [statusFilterDetails, ispFilterDetails].filter(
    Boolean,
  );
  const filterOptions = Array.from(
    document.querySelectorAll(".map-status-filter-option"),
  );
  const totalBadge = document.getElementById("mapTotalBadge");
  let currentFilter = "on_air";

  // Export button reads whatever filter is active right at click time —
  // no need to keep its href in sync on every applyFilter() call, setting
  // it inside the click handler still runs before the browser follows the
  // link. The server (export_xlsx() in app/routes/map_view.py) does the
  // actual filtering + picks the matching filename (e.g. "Nokia-site-
  // mapview.xlsx", "ISP_TELCOTECH-mapview.xlsx"); this just tells it which.
  const exportLink = document.getElementById("mapExportLink");
  if (exportLink) {
    const baseExportHref = exportLink.getAttribute("href");
    exportLink.addEventListener("click", () => {
      exportLink.href =
        currentFilter === "all"
          ? baseExportHref
          : `${baseExportHref}?filter=${encodeURIComponent(currentFilter)}`;
    });
  }

  // "On Air" row's own nested NMS breakdown (see the expand-arrow wiring
  // below) — each sub-filter narrows "on_air" down to one vendor.
  const ON_AIR_NMS_FILTERS = {
    on_air_nokia: "Nokia",
    on_air_huawei: "Huawei",
    on_air_zte: "ZTE",
  };
  // "recent_all" lives in the ISP dropdown (label/count-wise) but isn't a
  // POP-only filter like the rest — it's the one combined view, on-air
  // sites AND every ISP POP together, so it gets its own branch in
  // applyFilter() below rather than going through matchesPopFilter().
  const ISP_FILTERS = [
    "recent_all",
    "pop_all",
    "pop_telcotech",
    "pop_ezecom",
    "pop_no_owner",
  ];
  const ISP_POP_ONLY_FILTERS = ["pop_all", "pop_telcotech", "pop_ezecom", "pop_no_owner"];

  function matchesFilter(site, filter) {
    if (filter === "all") return true;
    // Orthogonal to the status-based filters below — a down site still
    // has its own on_air/planned/other status too.
    if (filter === "site_down") return !!site.is_down;
    if (filter === "other")
      return site.status !== "on_air" && site.status !== "planned";
    if (filter in ON_AIR_NMS_FILTERS)
      return (
        site.status === "on_air" && site.nms === ON_AIR_NMS_FILTERS[filter]
      );
    return site.status === filter;
  }

  // Only ever called with one of ISP_POP_ONLY_FILTERS — the "All Status"
  // branch below adds every POP unfiltered instead.
  function matchesPopFilter(pop, filter) {
    if (filter === "pop_all") return true;
    if (filter === "pop_no_owner") return !pop.pro_owner;
    return filter === "pop_telcotech"
      ? pop.pro_owner === "Telcotech"
      : pop.pro_owner === "Ezecom";
  }

  // ISP_POP_ONLY_FILTERS are part of this same mutually-exclusive set —
  // picking one hides every site marker and shows only the matching
  // POPs; picking anything else hides the POP layer again except
  // "All Status" and "recent_all", which both show every POP (all
  // owners) alongside sites.
  function applyFilter(filter) {
    currentFilter = filter;
    markersGroup.clearLayers();
    popsGroup.clearLayers();
    if (filter === "recent_all") {
      // The one combined view: on-air sites AND every ISP POP together,
      // not the usual "ISP filter hides sites" behavior.
      sites.forEach((site) => {
        if (site.status === "on_air")
          markersGroup.addLayer(markersById.get(site.id));
      });
      pops.forEach((pop) => popsGroup.addLayer(popMarkersById.get(pop.id)));
      popsGroup.addTo(map);
    } else if (ISP_POP_ONLY_FILTERS.includes(filter)) {
      pops.forEach((pop) => {
        if (matchesPopFilter(pop, filter))
          popsGroup.addLayer(popMarkersById.get(pop.id));
      });
      popsGroup.addTo(map);
    } else {
      sites.forEach((site) => {
        if (matchesFilter(site, filter))
          markersGroup.addLayer(markersById.get(site.id));
      });
      // "All Status" shows POPs alongside every site; a narrower status
      // filter (on_air/planned/other/site_down) hides them again so the
      // map stays focused on just that subset.
      if (filter === "all") {
        pops.forEach((pop) => popsGroup.addLayer(popMarkersById.get(pop.id)));
        popsGroup.addTo(map);
      } else {
        map.removeLayer(popsGroup);
      }
    }

    // Each dropdown's own summary label reflects the active filter only
    // when it belongs to that dropdown's group; otherwise it falls back to
    // its own default text (selecting an ISP owner, for instance, doesn't
    // change what the status dropdown's label reads).
    const option = filterOptions.find((o) => o.dataset.filter === filter);
    const isIspFilter = ISP_FILTERS.includes(filter);
    if (statusFilterLabel)
      statusFilterLabel.textContent =
        !isIspFilter && option ? option.dataset.label : "All Status";
    if (ispFilterLabel)
      ispFilterLabel.textContent =
        isIspFilter && option ? option.dataset.label : "ISP Site";
    filterOptions.forEach((o) =>
      o.classList.toggle("active", o.dataset.filter === filter),
    );

    // The boundary card (province/district/commune/village search result)
    // already narrows to currentFilter the moment it's opened — see
    // renderBoundarySites()'s own comment — but until now that was a
    // one-time snapshot: picking a different ISP/status filter while the
    // card was still open left it showing the OLD filter's sites/POPs.
    // Re-running it here with the just-updated currentFilter keeps it live
    // instead of requiring the user to close and re-search.
    if (boundarySiteEntry) renderBoundarySites(boundarySiteEntry);
  }

  filterOptions.forEach((option) => {
    option.addEventListener("click", () => {
      applyFilter(option.dataset.filter);
      const details = option.closest("details.map-status-filter");
      if (details) details.open = false;
    });
  });

  // Opening one filter dropdown closes the other — they sit side by side
  // now (see .map-header-title-group), so both open at once would overlap.
  filterDetailsList.forEach((details) => {
    details.addEventListener("toggle", () => {
      if (details.open) {
        filterDetailsList.forEach((other) => {
          if (other !== details) other.open = false;
        });
      }
    });
  });

  // "On Air" row's expand arrow — toggles its NMS sublist without also
  // triggering the row's own filter-click handler above (stopPropagation,
  // since the button sits nested inside that row).
  document.querySelectorAll(".map-status-filter-expand").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      const sublist = btn
        .closest(".map-status-filter-option-group")
        ?.querySelector(".map-status-filter-sublist");
      if (!sublist) return;
      sublist.hidden = !sublist.hidden;
      btn.classList.toggle("expanded", !sublist.hidden);
    });
  });

  document.addEventListener("click", (event) => {
    filterDetailsList.forEach((details) => {
      if (details.open && !details.contains(event.target)) details.open = false;
    });
  });

  if (totalBadge) {
    totalBadge.addEventListener("click", () => {
      applyFilter("all");
      clearBoundary();
    });
  }

  // Default view is "On Air" only — the map's day-to-day use is watching
  // live sites, so Planned/Other/POPs start hidden; "All Status" (or the
  // "N sites plotted" badge) is one click away to see everything.
  applyFilter("on_air");

  // Auto-refresh — polls the same site_cache/incident_site_down data the
  // page loaded with (site_cache/incident_site_down sync in the background
  // every 5 min, see SITE_SYNC_INTERVAL_SECONDS/INCIDENT_SYNC_INTERVAL_SECONDS
  // in app/config.py) and updates marker colors + counts in place, never a
  // full page reload — that would reset the user's pan/zoom/search/filter.
  const SITES_URL = "/map/sites.json";
  const REFRESH_INTERVAL_MS = 60000;

  function updateCounts(statusCounts) {
    if (totalBadge) {
      const n = statusCounts.all;
      totalBadge.textContent = `${n} site${n !== 1 ? "s" : ""} plotted`;
    }
    filterOptions.forEach((option) => {
      const countEl = option.querySelector(".map-status-filter-count");
      const count = statusCounts[option.dataset.filter];
      if (countEl && count !== undefined) countEl.textContent = count;
    });
  }

  // Guards against a slow request still being in flight when the next
  // 60s tick fires, and skips the tick entirely while the tab is hidden
  // (background tabs don't need a live map, and it saves a request).
  let refreshInFlight = false;

  function refreshSites() {
    if (refreshInFlight || document.hidden) return;
    refreshInFlight = true;
    fetch(SITES_URL)
      .then((res) => res.json())
      .then(
        ({
          sites: freshSites,
          status_counts: statusCounts,
          pops: freshPops,
        }) => {
          const freshById = new Map(freshSites.map((s) => [s.id, s]));
          sites.forEach((site) => {
            const fresh = freshById.get(site.id);
            if (!fresh) return;
            Object.assign(site, fresh);
            const marker = markersById.get(site.id);
            if (!marker) return;
            if (site.is_down && !marker._path) {
              // Just went down, and this marker is still the canvas-rendered
              // one createSiteMarker() gave it while it was up — canvas
              // markers have no _path for setSiteDownBlink's CSS animation
              // to target, so swap in a fresh SVG-backed marker instead of
              // silently never blinking (createSiteMarker already sets the
              // right fill color/popup content for the new state).
              markersGroup.removeLayer(marker);
              const upgraded = createSiteMarker(site);
              markersById.set(site.id, upgraded);
              markersGroup.addLayer(upgraded);
              return;
            }
            marker.setStyle({ fillColor: siteDotColor(site) });
            setSiteDownBlink(marker, site.is_down);
            marker.setPopupContent(popupHtml(site));
          });
          const freshPopById = new Map((freshPops || []).map((p) => [p.id, p]));
          pops.forEach((pop) => {
            const fresh = freshPopById.get(pop.id);
            if (!fresh) return;
            Object.assign(pop, fresh);
            const marker = popMarkersById.get(pop.id);
            if (!marker) return;
            marker.setStyle({ fillColor: popDotColor(pop) });
            marker.setPopupContent(popupHtmlForPop(pop));
          });

          const onAirNmsCounts = {};
          Object.entries(ON_AIR_NMS_FILTERS).forEach(([filter, vendor]) => {
            onAirNmsCounts[filter] = sites.filter(
              (s) => s.status === "on_air" && s.nms === vendor,
            ).length;
          });
          updateCounts({
            ...statusCounts,
            recent_all:
              sites.filter((s) => s.status === "on_air").length + pops.length,
            pop_all: pops.length,
            pop_telcotech: pops.filter((p) => p.pro_owner === "Telcotech")
              .length,
            pop_ezecom: pops.filter((p) => p.pro_owner === "Ezecom").length,
            pop_no_owner: pops.filter((p) => !p.pro_owner).length,
            ...onAirNmsCounts,
          });
          applyFilter(currentFilter);
        },
      )
      .catch(() => {
        // A failed refresh just leaves the map showing last-known data
        // until the next tick — never worth interrupting the user over.
      })
      .finally(() => {
        refreshInFlight = false;
      });
  }

  setInterval(refreshSites, REFRESH_INTERVAL_MS);
});
