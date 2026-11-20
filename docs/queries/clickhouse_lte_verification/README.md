# LTE KPI verification queries

These are standalone read-only queries. Run one SQL file at a time.
They do not create views, tables, caches, dashboard cards, or scheduled jobs.
All observed nonblank cell names across Huawei, Nokia and ZTE are included. No LIMIT or 45-cell filter is applied.
Cells with missing denominator/data remain in the result as No data; impossible negative or over-100 percentage values are marked Invalid.
Cells absent from all source observations cannot be listed without an inventory join.

Period: previous completed Monday-to-Sunday week, Cambodia time, with an exclusive end boundary.
This is weekly counter aggregation, not a busy-hour KPI or average of daily percentage values.
Rates use unrounded values for threshold tests; display_value is rounded only for presentation.
For badge counts, count status=Poor. No data and Invalid must not be counted as healthy/Met.

Targets: PRB <=80%; DL throughput >=3 Mbps; UL throughput >=2 Mbps; call setup >=98%;
E-RAB drop <2%; RRC setup >=98%; E-RAB setup >=98%; availability >=98%.

Formula notes:
- Nokia call setup: the stored catalog formula is inconsistent with its documented E-RAB attempt/success counters.
  The query derives CSSR as RRC success percentage times E-RAB success percentage divided by 100.
  Confirm this definition with the KPI owner before production caching.
- ZTE availability follows the existing v_mis_side_level_kpi_monthly definition: reported service plus energy-saving seconds
  divided by 3600 seconds times row count. This assumes hourly samples; confirm granularity before caching.
- Nokia E-RAB drop retains the existing formula catalog expression, including repeated adjustment counters.
  This has not been certified against an external vendor KPI specification.
- The queries analyze all cells with observations. Inventory-based availability and missing-report detection require additional rules.

Query plans are checked with EXPLAIN only. Plan validation does not certify source data quality or business definitions.
