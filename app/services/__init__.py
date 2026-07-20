"""Business logic layer.

If you're new to this codebase, here's the request flow:

    routes/  ->  services/  ->  repositories/  ->  database/

- routes/       : Flask views. Parse the request, call a service, render a
                  template or return JSON. No business logic here.
- services/     : (this package) The "how" and "why". Decides what data to
                  fetch, combines/shapes it, and applies any rules — e.g.
                  "a card with 0 alarms still shows every alarm type as 0".
                  Framework-agnostic: a service never imports `flask`.
- repositories/ : The "where". One method per query, no business logic —
                  just "give me these rows from Postgres/MSSQL/the cache".
- database/     : Actual connections + the raw SQL/schema.

Each service class takes its repository as a constructor argument
(`repository=None`, defaulting to the real one) so tests can pass in a fake
repository instead of hitting a real database.
"""
