-- E-RAB Call Drop Rate: all observed cells, previous complete Monday-to-Sunday week.
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
        metric_value >= 2, 'Poor',
        'Met'
    ) AS status,
    formula_note
FROM
(
    SELECT
        'Huawei' AS vendor,
        cellname AS cell_name,
        toFloat64(((sum(C1526727546) / nullIf(((sum(C1526727546) + sum(C1526727547)) + sum(C1526741752)), 0)) * 100)) AS metric_value,
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
        toFloat64((100 * (((((((((sum(M8006C261) + sum(M8006C254)) - sum(M8006C254)) - sum(M8006C254)) - sum(M8006C254)) - sum(M8006C301)) + sum(M8006C254)) + sum(M8006C254)) + sum(M8006C313)) / nullIf(((((((((((((((sum(M8006C254) + sum(M8006C261)) + sum(M8006C6)) + sum(M8006C7)) + sum(M8006C8)) + sum(M8006C9)) + sum(M8006C277)) - sum(M8006C301)) + sum(M8006C303)) + sum(M8006C306)) + sum(M8006C254)) + sum(M8006C310)) + sum(M8006C254)) + sum(M8006C312)) + sum(M8006C313)), 0)))) AS metric_value,
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
        toFloat64(100.0 * ((((((((sum(C373210381) + sum(C373210391)) + sum(C373210421)) + sum(C373210441)) + sum(C373210451)) + sum(C373210511)) + sum(C373210521)) + sum(C373505354)) / nullIf(((((sum(C373210461) + sum(C373240828)) + sum(C373505473)) + sum(C373505481)) + sum(C373546257)), 0))) AS metric_value,
        'Counter formula catalog' AS formula_note
    FROM NetCoreDB.zte_counter_history
    WHERE collecttime >= period_start
      AND collecttime < period_end
      AND cellname != ''
    GROUP BY cellname
)
ORDER BY vendor, cell_name;
