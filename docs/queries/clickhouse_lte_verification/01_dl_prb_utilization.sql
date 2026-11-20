-- DL PRB Utilization Rate: all observed cells, previous complete Monday-to-Sunday week.
-- No source data is modified. There is no cell-selection filter and no row limit.
WITH
    toDateTime(toStartOfWeek(toDate(now('Asia/Phnom_Penh')), 1), 'Asia/Phnom_Penh') AS period_end,
    period_end - INTERVAL 7 DAY AS period_start
SELECT
    period_start,
    period_end AS period_end_exclusive,
    vendor,
    cell_name,
    metric_value,
    round(metric_value, 2) AS display_value,
    '%' AS unit,
    multiIf(
        metric_value IS NULL, 'No data',
        NOT isFinite(metric_value) OR metric_value < 0 OR metric_value > 100, 'Invalid',
        metric_value > 80, 'Poor',
        'Met'
    ) AS status,
    formula_note
FROM
(
    SELECT
        'Huawei' AS vendor,
        cellname AS cell_name,
        toFloat64(((sum(C1526726740) / nullIf(sum(C1526728433), 0)) * 100)) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.huawei_4gcounter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname

    UNION ALL

    SELECT
        'Nokia' AS vendor,
        cellname AS cell_name,
        toFloat64((avg(M8011C37) / nullIf(10, 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.nokia_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname

    UNION ALL

    SELECT
        'ZTE' AS vendor,
        cellname AS cell_name,
        toFloat64(100.0 * (sum(C373424610) / nullIf(sum(C373424611), 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.zte_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname
)
ORDER BY vendor, cell_name;
