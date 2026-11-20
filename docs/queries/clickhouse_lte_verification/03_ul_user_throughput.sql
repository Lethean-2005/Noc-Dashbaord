-- LTE UL User Avg Throughput: all observed cells, previous complete Monday-to-Sunday week.
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
    'Mbps' AS unit,
    multiIf(
        metric_value IS NULL, 'No data',
        NOT isFinite(metric_value) OR metric_value < 0, 'Invalid',
        metric_value < 2, 'Poor',
        'Met'
    ) AS status,
    formula_note
FROM
(
    SELECT
        'Huawei' AS vendor,
        cellname AS cell_name,
        toFloat64((((sum(C1526728259) - sum(C1526729415)) / nullIf((sum(C1526729416) * 0.001), 0)) / nullIf(1000000, 0))) AS metric_value,
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
        toFloat64(((((((((((sum(M8012C91) + sum(M8012C93)) + sum(M8012C95)) + sum(M8012C97)) + sum(M8012C99)) + sum(M8012C101)) + sum(M8012C103)) + sum(M8012C105)) + sum(M8012C107)) / nullIf(((((((((sum(M8012C92) + sum(M8012C94)) + sum(M8012C96)) + sum(M8012C98)) + sum(M8012C100)) + sum(M8012C102)) + sum(M8012C104)) + sum(M8012C106)) + sum(M8012C108)), 0)) / nullIf(1000, 0))) AS metric_value,
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
        toFloat64((((sum(C374107517) * 1000) + sum(C374107518)) / nullIf(sum(C374107519), 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.zte_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname
)
ORDER BY vendor, cell_name;
