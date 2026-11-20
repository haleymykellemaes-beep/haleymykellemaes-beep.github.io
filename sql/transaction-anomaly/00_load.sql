-- Transaction Anomaly Detection — PaySim load and temporal split
-- Dialect: DuckDB 1.4+
--
-- Download the PaySim CSV from the original Kaggle listing:
-- https://www.kaggle.com/datasets/ealaxi/paysim1
-- Save it as data/PS_20174392719_1491204439457_log.csv.
--
-- The file is intentionally excluded from Git: it is about 494 MB.

DROP TABLE IF EXISTS tx;

CREATE TABLE tx AS
SELECT
    ROW_NUMBER() OVER ()::BIGINT                      AS tx_id,
    step::INTEGER                                     AS step,
    (((step - 1) // 24) + 1)::INTEGER                AS day,
    (step % 24)::INTEGER                              AS hour,
    type::VARCHAR                                     AS type,
    amount::DOUBLE                                    AS amount,
    nameOrig::VARCHAR                                 AS name_orig,
    oldbalanceOrg::DOUBLE                             AS old_balance_orig,
    newbalanceOrig::DOUBLE                            AS new_balance_orig,
    nameDest::VARCHAR                                 AS name_dest,
    oldbalanceDest::DOUBLE                            AS old_balance_dest,
    newbalanceDest::DOUBLE                            AS new_balance_dest,
    isFraud::INTEGER                                  AS is_fraud,
    isFlaggedFraud::INTEGER                           AS is_flagged_fraud,
    CASE
        WHEN step BETWEEN 1 AND 480 THEN 'train'
        WHEN step BETWEEN 481 AND 720 THEN 'test'
        ELSE 'excluded_partial_day_31'
    END                                               AS split
FROM read_csv_auto(
    'data/PS_20174392719_1491204439457_log.csv',
    header = TRUE
);

CREATE INDEX idx_tx_id ON tx (tx_id);
CREATE INDEX idx_tx_step ON tx (step);

-- The holdout is exactly ten complete days. A condition of step > 480 would
-- incorrectly include steps 721–743, which are the partial 31st day.
SELECT
    split,
    MIN(step) AS min_step,
    MAX(step) AS max_step,
    COUNT(*) AS transactions,
    SUM(is_fraud) AS fraud
FROM tx
GROUP BY split
ORDER BY min_step;
