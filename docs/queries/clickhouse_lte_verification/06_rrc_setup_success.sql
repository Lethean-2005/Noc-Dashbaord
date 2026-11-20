-- LTE RRC Setup Success Rate: all observed cells, previous complete Monday-to-Sunday week.
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
        metric_value < 98, 'Poor',
        'Met'
    ) AS status,
    formula_note
FROM
(
    SELECT
        'Huawei' AS vendor,
        cellname AS cell_name,
        toFloat64(((sum(C1526726659) / nullIf(sum(C1526726658), 0)) * 100)) AS metric_value,
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
        toFloat64((100 * (sum(M8013C5) / nullIf((((((((sum(M8013C17) + sum(M8013C18)) + sum(M8013C19)) + sum(M8013C21)) + sum(M8013C31)) + sum(M8013C34)) + sum(M8013C93)) + sum(M8013C91)), 0)))) AS metric_value,
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
        toFloat64(100.0 * (((((((sum(C373200000) + sum(C373200004)) + sum(C373200008)) + sum(C373200012)) + sum(C373200016)) + sum(C373200120)) + sum(C373200152)) / nullIf((((((((((((((((((((((((((((sum(C373200000) + sum(C373200004)) + sum(C373200008)) + sum(C373200012)) + sum(C373200016)) + sum(C373200120)) + sum(C373200001)) + sum(C373200002)) + sum(C373200003)) + sum(C373200005)) + sum(C373200006)) + sum(C373200007)) + sum(C373200009)) + sum(C373200010)) + sum(C373200011)) + sum(C373200013)) + sum(C373200014)) + sum(C373200015)) + sum(C373200017)) + sum(C373200018)) + sum(C373200019)) + sum(C373200121)) + sum(C373200122)) + sum(C373200123)) + sum(C373200152)) + sum(C373200153)) + sum(C373200154)) + sum(C373200155)), 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.zte_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname
)
ORDER BY vendor, cell_name;
