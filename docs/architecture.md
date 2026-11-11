# Code architecture

This document establishes the structure for incremental cleanup. Existing imports, URLs, SQL results and database tables remain compatible. The proposed modules below are a plan, not a claim that files have already moved.

## Existing structure and responsibilities

```text
app/
  __init__.py              Application creation and registration
  config.py               Environment configuration
  extensions.py           Shared Flask extensions
  routes/                 HTTP input, validation, responses and page assembly
  services/<feature>/     Feature rules, calculations and workflows
  repositories/<feature>/ Data access and cache operations
  database/
    queries/              Source SQL queries
    cache.py              Local SQLite schema initialization
    connection.py         Source connection management
    mssql.py              SQL Server connection management
    sql_loader.py         Query loading
  utils/                  Small shared formatting and parsing helpers
  templates/              Jinja pages and shared partials
  static/css/components/  Feature styles
  static/js/              Browser interaction and rendering
webhook/                  External workflow adapters
scripts/                  Deployment, diagnostics and manual tools; preserve files
tests/                   Automated regressions (at repository root)
docs/                     Guides, architecture and verification notes
instance/                 Persistent runtime data; preserve during updates
```

## Dependency direction

Routes call services; services call repositories; repositories load queries and use database connections. Services and repositories must not import routes. Browser code calls application endpoints rather than source databases. Shared utilities must remain small and must not start jobs or send alerts on import.

App creation wires extensions, routes, database initialization and configured background jobs. Testing must use an isolated instance and disable real delivery. Existing scheduling and source adapters may use Flask configuration; introducing a new framework is unnecessary.

## Naming and code rules

Use feature names consistently. Name functions after behavior, such as get_incidents, calculate_delay or exclude_interface. Keep SQL in query files and bind values through parameters. Keep handlers focused on request/response work. Keep report rendering separate from report persistence. Explain business rules and unusual constraints in comments; omit narration of obvious statements and production record IDs.

Keep source timestamps and Cambodia display conversions explicit. Reuse existing helpers before introducing another parser, formatter or cache. Never change count definitions, deduplication keys or notification timing as a side effect of restructuring.

## Prioritized module splits

Measured on 11 November 2026: dashboard.py has 2,804 lines, incident_service.py 2,879, incident_sync_service.py 1,276, and cache.py 1,519. These sizes identify review candidates rather than defects by themselves. Services and repositories currently have no imports from app.routes.

1. Separate dashboard route registration by domain: incidents, alarms and trends. Keep existing endpoint names and URLs, with the current dashboard blueprint acting as the compatibility entry point.
2. Separate incident read calculations into status, SLA and trend services. Keep the current IncidentService public methods as delegating wrappers until all callers migrate. Keep incident synchronization and alert delivery separate.
3. Separate cache schema definitions from initialization orchestration. Preserve table names and additive upgrades; verify an older populated database before adopting the split.
4. Separate application wiring into extensions, HTTP registration and job startup modules. Preserve environment loading before Config imports and retain existing startup guards so jobs cannot start twice.
5. Split browser modules only at clear feature boundaries. Preserve event handlers, circuit identity associations, request cancellation and dropdown keyboard behavior. Avoid broad cosmetic rewrites.

Do not create empty directories for every proposed module. Add each module when its implementation and verification are ready.

## Safe implementation sequence

Work in small, independently reviewable changes. For each module extraction: record callers and public interfaces, move one responsibility, retain compatibility wrappers where needed, run relevant tests, and check browser or export behavior when affected. Run the broader suite after connected changes. Compare summary and drilldown counts whenever query logic changes. Measure performance on representative data before claiming improvement.

No commits or pushes are authorized by this document. Preserve scripts, environment files, instance data and unrelated working-tree changes. Do not deploy or rebuild a ZIP as part of structural preparation.

## Completion criteria

A structural change is complete when existing endpoints and public interfaces work, relevant regressions pass, no new import cycles appear, source data semantics remain unchanged, and persistent data survives restart. Production load performance requires a separate VM measurement.
