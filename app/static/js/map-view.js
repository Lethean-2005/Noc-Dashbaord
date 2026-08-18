// Map View page — plots every site read from site_cache (already filtered
// server-side to rows with a real, non-zero p_lat/p_lon; see
// app/services/map/map_view_service.py) as a colored dot on a Leaflet map,
// clustered so ~4,000 markers stay smooth and readable at low zoom instead
// of a solid wall of overlapping dots.
document.addEventListener('DOMContentLoaded', () => {
  const mapEl = document.getElementById('mapView');
  if (!mapEl) return;

  const dataEl = document.getElementById('map-view-sites-data');
  const sites = dataEl ? JSON.parse(dataEl.textContent) : [];

  // Cambodia, roughly centered — every site in this dataset falls inside
  // the country, so this is a sane default view before any marker is
  // clicked.
  const map = L.map(mapEl).setView([12.5657, 104.9910], 7);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  const DOT_COLORS = { on_air: '#10b981', planned: '#0487e2' };
  const DEFAULT_DOT_COLOR = '#94a3b8';

  function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function popupHtml(site) {
    const rows = [
      ['Status', site.status],
      ['Grade', site.site_grade],
      ['NMS', site.nms],
      ['Province', site.province],
      ['District', site.district],
      ['Commune', site.commune],
      ['Hub Site', site.hub_site],
    ]
      .filter(([, value]) => value)
      .map(([label, value]) => `<div class="map-popup-row"><strong>${label}:</strong> ${escapeHtml(value)}</div>`)
      .join('');
    const subtitle = site.site_name && site.site_name !== site.name
      ? `<div class="map-popup-row">${escapeHtml(site.site_name)}</div>`
      : '';
    return `<div class="map-popup-title">${escapeHtml(site.name || 'Unknown site')}</div>${subtitle}${rows}`;
  }

  const clusterGroup = L.markerClusterGroup();
  const markersById = new Map();
  // Built as a plain array first and added via addLayers() (bulk) once,
  // not addLayer() per marker in the loop — with up to ~4,300 sites,
  // adding one at a time forces Leaflet.markercluster to recompute
  // cluster placement after every single marker instead of batching the
  // whole set into one pass.
  const allMarkers = sites.map((site) => {
    const marker = L.circleMarker([site.lat, site.lon], {
      radius: 6,
      weight: 1,
      color: '#ffffff',
      fillColor: DOT_COLORS[site.status] || DEFAULT_DOT_COLOR,
      fillOpacity: 0.9,
    });
    marker.bindPopup(popupHtml(site));
    markersById.set(site.id, marker);
    return marker;
  });
  clusterGroup.addLayers(allMarkers);
  map.addLayer(clusterGroup);

  // Search by site code (name) or site name (fra_site_name) — a plain
  // substring match, same case-insensitive "does this contain the typed
  // text" behavior as the drilldown tables' own search box
  // (app/static/js/table.js), just scoped to two fields instead of a
  // whole row.
  const searchInput = document.getElementById('mapSearchInput');
  const resultsEl = document.getElementById('mapSearchResults');
  const MAX_RESULTS = 15;

  function renderResults(matches, query) {
    if (!query) {
      resultsEl.hidden = true;
      resultsEl.innerHTML = '';
      return;
    }
    if (!matches.length) {
      resultsEl.hidden = false;
      resultsEl.innerHTML = '<div class="map-search-empty">No site matches "' + escapeHtml(query) + '"</div>';
      return;
    }
    resultsEl.innerHTML = matches
      .slice(0, MAX_RESULTS)
      .map(
        (site) =>
          `<div class="map-search-result" data-site-id="${site.id}">` +
          `<div class="map-search-result-code">${escapeHtml(site.name)}</div>` +
          (site.site_name ? `<div class="map-search-result-name">${escapeHtml(site.site_name)}</div>` : '') +
          `</div>`
      )
      .join('');
    resultsEl.hidden = false;
  }

  function goToSite(site) {
    const marker = markersById.get(site.id);
    if (!marker) return;
    resultsEl.hidden = true;
    searchInput.value = site.name;
    // A status filter may have removed this marker from clusterGroup —
    // reset to "all" first so it's guaranteed to be there to zoom to.
    applyFilter('all');
    clusterGroup.zoomToShowLayer(marker, () => marker.openPopup());
  }

  let debounceTimer;
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const query = searchInput.value.trim().toLowerCase();
      const matches = query
        ? sites.filter(
            (site) =>
              (site.name && site.name.toLowerCase().includes(query)) ||
              (site.site_name && site.site_name.toLowerCase().includes(query))
          )
        : [];
      renderResults(matches, query);
    }, 150);
  });

  resultsEl.addEventListener('click', (event) => {
    const row = event.target.closest('.map-search-result');
    if (!row) return;
    const site = sites.find((s) => String(s.id) === row.dataset.siteId);
    if (site) goToSite(site);
  });

  document.addEventListener('click', (event) => {
    if (!event.target.closest('.map-search')) resultsEl.hidden = true;
  });

  // Status filter — a <details> dropdown card (see map-view.css), not a
  // native <select>. "All Status" shows everything (the default, already
  // active on page load since clusterGroup starts with every marker added
  // above); the other 3 options narrow it down to just that status. The
  // "N sites plotted" badge next to the title doubles as a reset back to
  // "All Status".
  const filterDetails = document.getElementById('mapStatusFilter');
  const filterLabel = document.getElementById('mapStatusFilterLabel');
  const filterOptions = filterDetails
    ? Array.from(filterDetails.querySelectorAll('.map-status-filter-option'))
    : [];
  const totalBadge = document.getElementById('mapTotalBadge');

  function matchesFilter(status, filter) {
    if (filter === 'all') return true;
    if (filter === 'other') return status !== 'on_air' && status !== 'planned';
    return status === filter;
  }

  function applyFilter(filter) {
    // addLayers() (bulk) instead of calling addLayer() once per matching
    // site — with up to ~4,300 markers, adding them one at a time forces
    // Leaflet.markercluster to recompute cluster placement after every
    // single marker; addLayers() batches the whole set into one pass.
    const matching = sites
      .filter((site) => matchesFilter(site.status, filter))
      .map((site) => markersById.get(site.id));
    clusterGroup.clearLayers();
    clusterGroup.addLayers(matching);

    const option = filterOptions.find((o) => o.dataset.filter === filter);
    if (filterLabel && option) filterLabel.textContent = option.dataset.label;
    filterOptions.forEach((o) => o.classList.toggle('active', o.dataset.filter === filter));
  }

  filterOptions.forEach((option) => {
    option.addEventListener('click', () => {
      applyFilter(option.dataset.filter);
      if (filterDetails) filterDetails.open = false;
    });
  });

  document.addEventListener('click', (event) => {
    if (filterDetails && filterDetails.open && !event.target.closest('.map-status-filter')) {
      filterDetails.open = false;
    }
  });

  if (totalBadge) {
    totalBadge.addEventListener('click', () => applyFilter('all'));
  }
});
