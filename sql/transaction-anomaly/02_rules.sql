-- Transaction Anomaly Detection — feature engineering and rule candidates
-- Run after 00_load.sql.
--
-- IMPORTANT DATA-GOVERNANCE NOTE
-- The PaySim publisher states that fraudulent transactions are canceled and
-- that the old/new balance fields should not be used for fraud detection.
-- R1 and R3 are therefore audit-only leakage checks. They are never included
-- in the production-style score.

DROP TABLE IF EXISTS train_type_stats;

CREATE TABLE train_type_stats AS
SELECT
    type,
    AVG(amount) AS amount_avg,
    STDDEV_SAMP(amount) AS amount_sd,
    QUANTILE_CONT(amount, 0.99) AS amount_p99
FROM tx
WHERE split = 'train'
GROUP BY type;

-- Count only incoming TRANSFER transactions, matching the proposed mule rule.
-- RANGE uses the step value (one step = one hour), so the frame is 24 hours.
DROP TABLE IF EXISTS transfer_velocity;

CREATE TABLE transfer_velocity AS
SELECT
    tx_id,
    COUNT(*) OVER (
        PARTITION BY name_dest
        ORDER BY step
        RANGE BETWEEN 23 PRECEDING AND CURRENT ROW
    )::INTEGER AS inbound_transfer_24h
FROM tx
WHERE type = 'TRANSFER';

CREATE INDEX idx_transfer_velocity_tx_id ON transfer_velocity (tx_id);

DROP TABLE IF EXISTS tx_features;

CREATE TABLE tx_features AS
SELECT
    t.*,
    COALESCE(v.inbound_transfer_24h, 0)::INTEGER AS inbound_transfer_24h,
    (t.amount - s.amount_avg) / NULLIF(s.amount_sd, 0) AS amount_z,

    -- R0: existing simulator rule.
    (t.is_flagged_fraud = 1)::INTEGER AS r0_baseline,

    -- R1 audit only: post-transaction balance leakage.
    (
        t.type IN ('TRANSFER', 'CASH_OUT')
        AND t.old_balance_orig > 0
        AND t.new_balance_orig = 0
        AND t.amount >= t.old_balance_orig
    )::INTEGER AS audit_r1_drained,

    -- R2: threshold learned only from days 1–20.
    (
        t.type IN ('TRANSFER', 'CASH_OUT')
        AND t.amount > s.amount_p99
    )::INTEGER AS r2_large,

    -- R3 audit only: post-transaction balance leakage and simulator artifact.
    (
        t.type IN ('TRANSFER', 'CASH_OUT')
        AND ABS(
            (t.old_balance_orig - t.amount) - t.new_balance_orig
        ) > 0.01
    )::INTEGER AS audit_r3_balance_mismatch,

    -- R4 candidate: threshold validated on training data below.
    (
        t.type = 'TRANSFER'
        AND COALESCE(v.inbound_transfer_24h, 0) >= 3
    )::INTEGER AS r4_busy_receiver,

    -- R5: restrict the timing rule to the two train-observed fraud types.
    (
        t.type IN ('TRANSFER', 'CASH_OUT')
        AND t.hour BETWEEN 0 AND 5
    )::INTEGER AS r5_off_hours
FROM tx AS t
JOIN train_type_stats AS s USING (type)
LEFT JOIN transfer_velocity AS v USING (tx_id);

-- Training-only rule validation. R4 generated 34,375 alerts and caught one
-- fraud in this run, so it receives zero points in the final score.
WITH training AS (
    SELECT * FROM tx_features WHERE split = 'train'
),
rule_rows AS (
    UNPIVOT training
    ON r0_baseline, r2_large, r4_busy_receiver, r5_off_hours,
       audit_r1_drained, audit_r3_balance_mismatch
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
        / (SELECT SUM(is_fraud) FROM training),
        3
    ) AS recall_pct,
    ROUND(SUM(flag) / 20.0, 1) AS alerts_per_day
FROM rule_rows
GROUP BY rule
ORDER BY rule;
