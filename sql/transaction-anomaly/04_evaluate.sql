-- Transaction Anomaly Detection — untouched holdout evaluation
-- Run after 03_score.sql.
-- Holdout: steps 481–720 (days 21–30), 2,592 fraud transactions.

DROP TABLE IF EXISTS test_rule_scorecard;

CREATE TABLE test_rule_scorecard AS
WITH test AS (
    SELECT * FROM scored WHERE split = 'test'
),
rule_rows AS (
    UNPIVOT test
    ON r0_baseline, r2_large, r4_busy_receiver, r5_off_hours
    INTO NAME rule VALUE flag
)
SELECT
    rule,
    SUM(flag)::BIGINT AS alerts,
    SUM(flag * is_fraud)::BIGINT AS fraud_caught,
    ROUND(
        100.0 * SUM(flag * is_fraud) / NULLIF(SUM(flag), 0),
        3
    ) AS precision_pct,
    ROUND(
        100.0 * SUM(flag * is_fraud)
        / (SELECT SUM(is_fraud) FROM test),
        3
    ) AS recall_pct,
    ROUND(SUM(flag) / 10.0, 1) AS alerts_per_day
FROM rule_rows
GROUP BY rule
ORDER BY rule;

SELECT * FROM test_rule_scorecard;

DROP TABLE IF EXISTS test_ranked;

CREATE TABLE test_ranked AS
SELECT
    *,
    ROW_NUMBER() OVER (
        ORDER BY rule_score DESC, step, tx_id
    ) AS rules_queue_rank,
    ROW_NUMBER() OVER (
        ORDER BY risk_score DESC, step, tx_id
    ) AS score_queue_rank
FROM scored
WHERE split = 'test'
  AND queue_eligible = 1;

-- Headline comparison at a fixed 200-alert/day review budget.
-- The rule-only queue is FIFO within equal point totals. The combined queue
-- uses the amount z-score to resolve those ties and reorder the queue.
WITH holdout AS (
    SELECT SUM(is_fraud) AS total_fraud FROM test_ranked
),
results AS (
    SELECT
        'existing_rule' AS method,
        COUNT(*) FILTER (WHERE r0_baseline = 1) AS alerts,
        SUM(is_fraud) FILTER (WHERE r0_baseline = 1) AS fraud_caught
    FROM test_ranked

    UNION ALL

    SELECT
        'rules_fifo' AS method,
        2000 AS alerts,
        SUM(is_fraud) FILTER (WHERE rules_queue_rank <= 2000) AS fraud_caught
    FROM test_ranked

    UNION ALL

    SELECT
        'rules_plus_z_score' AS method,
        2000 AS alerts,
        SUM(is_fraud) FILTER (WHERE score_queue_rank <= 2000) AS fraud_caught
    FROM test_ranked
)
SELECT
    method,
    alerts,
    fraud_caught,
    ROUND(100.0 * fraud_caught / NULLIF(alerts, 0), 2) AS precision_pct,
    ROUND(100.0 * fraud_caught / total_fraud, 2) AS recall_pct,
    ROUND(alerts / 10.0, 1) AS alerts_per_day
FROM results
CROSS JOIN holdout
ORDER BY
    CASE method
        WHEN 'existing_rule' THEN 1
        WHEN 'rules_fifo' THEN 2
        ELSE 3
    END;

DROP TABLE IF EXISTS test_threshold_curve;

CREATE TABLE test_threshold_curve AS
WITH budgets AS (
    SELECT *
    FROM (
        VALUES (25), (50), (100), (150), (200),
               (250), (300), (400), (500)
    ) AS b (alerts_per_day)
),
totals AS (
    SELECT SUM(is_fraud) AS total_fraud FROM test_ranked
)
SELECT
    alerts_per_day,
    alerts_per_day * 10 AS alerts,
    SUM(
        CASE
            WHEN rules_queue_rank <= alerts_per_day * 10 THEN is_fraud
            ELSE 0
        END
    )::BIGINT AS rules_caught,
    ROUND(
        100.0 * rules_caught / (alerts_per_day * 10),
        2
    ) AS rules_precision_pct,
    ROUND(100.0 * rules_caught / total_fraud, 2) AS rules_recall_pct,
    SUM(
        CASE
            WHEN score_queue_rank <= alerts_per_day * 10 THEN is_fraud
            ELSE 0
        END
    )::BIGINT AS score_caught,
    ROUND(
        100.0 * score_caught / (alerts_per_day * 10),
        2
    ) AS score_precision_pct,
    ROUND(100.0 * score_caught / total_fraud, 2) AS score_recall_pct
FROM test_ranked
CROSS JOIN budgets
CROSS JOIN totals
GROUP BY alerts_per_day, total_fraud
ORDER BY alerts_per_day;

SELECT * FROM test_threshold_curve;

-- Leakage audit: report these separately, never as deployable performance.
WITH test AS (
    SELECT * FROM scored WHERE split = 'test'
),
leakage_rows AS (
    UNPIVOT test
    ON audit_r1_drained, audit_r3_balance_mismatch
    INTO NAME rule VALUE flag
)
SELECT
    rule,
    SUM(flag)::BIGINT AS alerts,
    SUM(flag * is_fraud)::BIGINT AS fraud_caught,
    ROUND(
        100.0 * SUM(flag * is_fraud) / NULLIF(SUM(flag), 0),
        3
    ) AS apparent_precision_pct,
    ROUND(
        100.0 * SUM(flag * is_fraud)
        / (SELECT SUM(is_fraud) FROM test),
        3
    ) AS apparent_recall_pct,
    'EXCLUDED: post-outcome simulator balance fields' AS status
FROM leakage_rows
GROUP BY rule
ORDER BY rule;
