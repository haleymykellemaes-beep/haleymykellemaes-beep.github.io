-- Transaction Anomaly Detection — training-only weight selection and scoring
-- Run after 02_rules.sql.
--
-- Alert capacity is fixed before evaluation:
--   training: 200 alerts/day × 20 days = 4,000 alerts
--   holdout:  200 alerts/day × 10 days = 2,000 alerts

DROP TABLE IF EXISTS candidate_weights;

CREATE TABLE candidate_weights AS
SELECT *
FROM (
    VALUES
        (1, 1, 0.25),
        (1, 2, 0.50),
        (1, 3, 0.50),
        (1, 4, 1.00),
        (1, 5, 1.00),
        (2, 3, 0.50),
        (2, 4, 1.00),
        (2, 5, 1.00),
        (3, 4, 0.50),
        (3, 5, 1.00),
        (4, 5, 1.00)
) AS w (r2_weight, r5_weight, z_weight);

DROP TABLE IF EXISTS weight_validation;

CREATE TABLE weight_validation AS
WITH ranked AS (
    SELECT
        w.r2_weight,
        w.r5_weight,
        w.z_weight,
        f.is_fraud,
        ROW_NUMBER() OVER (
            PARTITION BY w.r2_weight, w.r5_weight, w.z_weight
            ORDER BY
                (
                    10 * f.r0_baseline
                    + w.r2_weight * f.r2_large
                    + w.r5_weight * f.r5_off_hours
                    + w.z_weight * f.amount_z
                ) DESC,
                f.step,
                f.tx_id
        ) AS queue_rank
    FROM tx_features AS f
    CROSS JOIN candidate_weights AS w
    WHERE f.split = 'train'
      AND f.type IN ('TRANSFER', 'CASH_OUT')
)
SELECT
    r2_weight,
    r5_weight,
    z_weight,
    SUM(is_fraud) FILTER (WHERE queue_rank <= 4000)::BIGINT
        AS train_fraud_caught
FROM ranked
GROUP BY r2_weight, r5_weight, z_weight;

DROP TABLE IF EXISTS selected_weights;

CREATE TABLE selected_weights AS
SELECT r2_weight, r5_weight, z_weight, train_fraud_caught
FROM weight_validation
ORDER BY
    train_fraud_caught DESC,
    (r2_weight + r5_weight + z_weight) ASC,
    r2_weight ASC,
    r5_weight ASC,
    z_weight ASC
LIMIT 1;

-- Expected selection on the published PaySim file:
-- R0 +10, R2 +1, R5 +4, amount z-score +1.
SELECT * FROM selected_weights;

DROP TABLE IF EXISTS scored;

CREATE TABLE scored AS
SELECT
    f.*,
    (
        10 * f.r0_baseline
        + w.r2_weight * f.r2_large
        + w.r5_weight * f.r5_off_hours
    ) AS rule_score,
    (
        10 * f.r0_baseline
        + w.r2_weight * f.r2_large
        + w.r5_weight * f.r5_off_hours
        + w.z_weight * f.amount_z
    ) AS risk_score,
    (f.type IN ('TRANSFER', 'CASH_OUT'))::INTEGER AS queue_eligible
FROM tx_features AS f
CROSS JOIN selected_weights AS w;

-- is_fraud is intentionally absent from every rule and score expression.
-- It appears only in the training objective above and holdout evaluation.
