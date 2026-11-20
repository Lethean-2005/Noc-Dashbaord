-- LTE DL User Avg Throughput: all observed cells, previous complete Monday-to-Sunday week.
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
        metric_value < 3, 'Poor',
        'Met'
    ) AS status,
    formula_note
FROM
(
    SELECT
        'Huawei' AS vendor,
        cellname AS cell_name,
        toFloat64((((sum(C1526728261) - sum(C1526729005)) / nullIf((sum(C1526729015) * 0.001), 0)) / nullIf(1000000, 0))) AS metric_value,
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
        toFloat64(((((((((((sum(M8012C117) + sum(M8012C119)) + sum(M8012C121)) + sum(M8012C123)) + sum(M8012C125)) + sum(M8012C127)) + sum(M8012C129)) + sum(M8012C131)) + sum(M8012C133)) / nullIf(((((((((sum(M8012C118) + sum(M8012C120)) + sum(M8012C122)) + sum(M8012C124)) + sum(M8012C126)) + sum(M8012C128)) + sum(M8012C130)) + sum(M8012C132)) + sum(M8012C134)), 0)) / nullIf(1000, 0))) AS metric_value,
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
        toFloat64((((sum(C374107514) * 1000) + sum(C374107515)) / nullIf(sum(C374107516), 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.zte_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname
)
ORDER BY vendor, cell_name;
