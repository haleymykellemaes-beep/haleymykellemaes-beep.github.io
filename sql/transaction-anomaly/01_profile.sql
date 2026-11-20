-- Transaction Anomaly Detection — data profile
-- Run after 00_load.sql.

-- 1. Overall prevalence and the simulator's built-in rule.
SELECT
    COUNT(*) AS transactions,
    SUM(is_fraud) AS fraud,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 4) AS fraud_rate_pct,
    SUM(is_flagged_fraud) AS baseline_alerts,
    SUM(is_flagged_fraud * is_fraud) AS baseline_fraud_caught,
    ROUND(
        100.0 * SUM(is_flagged_fraud * is_fraud) / SUM(is_fraud),
        3
    ) AS baseline_recall_pct
FROM tx;

-- 2. Fraud appears only in TRANSFER and CASH_OUT.
SELECT
    type,
    COUNT(*) AS transactions,
    SUM(is_fraud) AS fraud,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 4) AS fraud_rate_pct,
    ROUND(AVG(amount), 2) AS average_amount,
    ROUND(MEDIAN(amount), 2) AS median_amount,
    ROUND(AVG(amount) FILTER (WHERE is_fraud = 1), 2)
        AS fraud_average_amount,
    ROUND(MEDIAN(amount) FILTER (WHERE is_fraud = 1), 2)
        AS fraud_median_amount,
    ROUND(QUANTILE_CONT(amount, 0.99), 2) AS amount_p99
FROM tx
GROUP BY type
ORDER BY transactions DESC;

-- 3. Hour-of-day profile. PaySim's overnight volume is unusually low, while
-- fraud injection is comparatively steady; treat the resulting lift as a
-- simulator pattern until it is validated against real operating data.
SELECT
    hour,
    COUNT(*) AS transactions,
    SUM(is_fraud) AS fraud,
    ROUND(1000.0 * SUM(is_fraud) / COUNT(*), 3) AS fraud_per_1000
FROM tx
GROUP BY hour
ORDER BY hour;

-- 4. Sender IDs are nearly one-time IDs, so customer-history rules are not
-- supportable in this dataset.
WITH sender_counts AS (
    SELECT name_orig, COUNT(*) AS transactions
    FROM tx
    GROUP BY name_orig
)
SELECT
    SUM(transactions) AS transactions,
    COUNT(*) AS unique_senders,
    SUM(transactions) - COUNT(*) AS repeat_transactions,
    ROUND(
        100.0 * (SUM(transactions) - COUNT(*)) / SUM(transactions),
        3
    ) AS repeat_transaction_pct
FROM sender_counts;

-- 5. Verify the time split before any tuning or evaluation.
SELECT
    split,
    COUNT(*) AS transactions,
    SUM(is_fraud) AS fraud,
    ROUND(100.0 * SUM(is_fraud) / COUNT(*), 4) AS fraud_rate_pct
FROM tx
GROUP BY split
ORDER BY MIN(step);
