# PostgreSQL "object_N" Table Reference

The PostgreSQL database (`cellcard-temp-stg-full-access-db`, see `.env` for
connection details) stores its data in generically-named foreign tables —
`object_1`, `object_2`, `object_3`, ... `object_438` (443 total). These names
carry no meaning on their own.

## How the real name is found

`object_1` is the platform's own model registry — every other `object_N`
table has a matching row in it, keyed by `id`. Look up the real name with:

```sql
SELECT id, name, plural, alias, type
FROM object_1
WHERE id = <the number from object_N>;
```

## Known tables

| Table        | Real name               | Alias      |
|--------------|--------------------------|------------|
| `object_138` | [APE] Alarm              | `alarm`    |
| `object_160` | Site                     | `site`     |
| `object_162` | Province                 | `province` |
| `object_164` | District                 | `district` |
| `object_166` | Commune                  | `commune`  |
| `object_168` | Village                  | `village`  |
| `object_227` | NE - Logical Technology  | `ne`       |
| `object_308` | Physical Location        | `ploc`     |
| `object_310` | Team                     | `team`     |
| `object_322` | Incident                 | `incident` |
| `object_324` | INC-WO                   | `inc_wo`   |

All of these are actively queried by the app — see the matching `.sql`
file under `app/database/queries/` for exactly which columns each one
pulls (e.g. `object_138` → `ape_alarm.sql`, `object_322` →
`incident_by_status.sql`/`incident_site_down.sql`). Each is synced on its
own background schedule into a local SQLite cache table
(`app/database/cache.py`) — pages never query these directly. This file
stays useful beyond that as a quick reference for manually exploring the
database (e.g. finding a new `object_N` table's real name via `object_1`
below) when wiring up something new.
