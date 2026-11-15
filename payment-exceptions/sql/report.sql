-- Run after the database is loaded:
--   sqlite3 payment-exceptions/data/billing.db < payment-exceptions/sql/report.sql

.mode column
.headers on

SELECT 'Naive retry exposure (unsuccessful attempts whose key already posted)' AS metric,
       COUNT(*) AS attempts,
       SUM(a.amount_cents) AS cents_at_risk
FROM payment_attempts a
WHERE a.attempt_status IN ('pending', 'failed', 'declined')
  AND EXISTS (
    SELECT 1 FROM posted_payments p
    WHERE p.idempotency_key = a.idempotency_key
      AND TRIM(COALESCE(p.idempotency_key, '')) != ''
  );

SELECT reason,
       COUNT(*) AS issues,
       SUM(amount_cents) AS cents
FROM v_exceptions
GROUP BY reason
ORDER BY cents DESC;

SELECT reason, entity_id, claim_id, amount_cents, action
FROM v_exceptions
ORDER BY reason, claim_id, entity_id;
