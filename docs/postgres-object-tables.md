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

| Table       | Real name              | Alias      |
|-------------|-------------------------|------------|
| `object_138`| [APE] Alarm             | `alarm`    |
| `object_160`| Site                    | `site`     |
| `object_227`| NE - Logical Technology | `ne`       |
| `object_322`| Incident                | `incident` |
| `object_324`| INC-WO                  | `inc_wo`   |

Nothing here is wired into the Noc-Dashboard app yet — this is a reference
for manually exploring the database, not a config the app reads.
