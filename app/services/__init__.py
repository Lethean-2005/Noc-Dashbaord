"""Business logic layer. Request flow:

    routes/  ->  services/  ->  repositories/  ->  database/

- routes/       : Flask views — parse the request, call a service, render.
- services/     : (this package) the "how"/"why" — fetches, shapes, and
                  applies rules (e.g. "0 alarms still shows every type as
                  0"). Framework-agnostic: never imports `flask`.
- repositories/ : the "where" — one method per query, no business logic.
- database/     : actual connections + raw SQL/schema.

Each service class takes its repository as a constructor argument
(`repository=None`, defaulting to the real one) so tests can pass a fake
repository instead of hitting a real database.
"""
