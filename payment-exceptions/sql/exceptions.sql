-- Exception queue. One row per issue. A claim can have more than one.
-- Amounts are cents. as_of and stuck_days live in settings.
--
-- Reprocess rule (see safe_to_reprocess):
--   patient card or ACH only
--   attempt is pending or failed, and older than stuck_days
--   no posted payment uses that idempotency key
--   no refund is requested or issued on the claim
--   attempt amount equals the open balance
-- Anything else is a block or a human review. Insurance short-pays are appeals.

DROP VIEW IF EXISTS v_exceptions;
DROP VIEW IF EXISTS v_attempt_exceptions;
DROP VIEW IF EXISTS v_duplicate_posts;
DROP VIEW IF EXISTS v_claim_net;

CREATE VIEW v_claim_net AS
SELECT
  c.claim_id,
  c.patient_id,
  c.payer,
  c.claim_status,
  c.denial_code,
  c.billed_cents,
  c.allowed_cents,
  c.patient_resp_cents,
  c.insurance_resp_cents,
  CASE
    WHEN ABS(c.allowed_cents - c.patient_resp_cents - c.insurance_resp_cents) <= 1 THEN 1
    ELSE 0
  END AS ties_out,
  COALESCE(p.posted_cents, 0) AS posted_cents,
  COALESCE(p.era_cents, 0) AS era_cents,
  COALESCE(p.patient_cents, 0) AS patient_paid_cents,
  COALESCE(r.refunded_cents, 0) AS refunded_cents,
  COALESCE(r.patient_refund_cents, 0) AS patient_refund_cents,
  COALESCE(p.posted_cents, 0) - COALESCE(r.refunded_cents, 0) AS net_cents,
  c.allowed_cents - (COALESCE(p.posted_cents, 0) - COALESCE(r.refunded_cents, 0)) AS remaining_cents,
  COALESCE(p.patient_cents, 0) - COALESCE(r.patient_refund_cents, 0) AS patient_net_cents
FROM claims c
LEFT JOIN (
  SELECT
    claim_id,
    SUM(amount_cents) AS posted_cents,
    SUM(CASE WHEN method = 'insurance_era' THEN amount_cents ELSE 0 END) AS era_cents,
    SUM(CASE WHEN method != 'insurance_era' THEN amount_cents ELSE 0 END) AS patient_cents
  FROM posted_payments
  WHERE claim_id IS NOT NULL AND TRIM(claim_id) != ''
  GROUP BY claim_id
) p ON p.claim_id = c.claim_id
LEFT JOIN (
  SELECT
    pp.claim_id,
    SUM(rf.amount_cents) AS refunded_cents,
    SUM(CASE WHEN pp.method != 'insurance_era' THEN rf.amount_cents ELSE 0 END) AS patient_refund_cents
  FROM refunds rf
  JOIN posted_payments pp ON pp.payment_id = rf.payment_id
  WHERE rf.refund_status = 'issued'
  GROUP BY pp.claim_id
) r ON r.claim_id = c.claim_id;

CREATE VIEW v_duplicate_posts AS
SELECT
  payment_id,
  claim_id,
  patient_id,
  idempotency_key,
  amount_cents,
  posted_at,
  key_count
FROM (
  SELECT
    payment_id,
    claim_id,
    patient_id,
    idempotency_key,
    amount_cents,
    posted_at,
    ROW_NUMBER() OVER (
      PARTITION BY idempotency_key
      ORDER BY posted_at, payment_id
    ) AS n,
    COUNT(*) OVER (PARTITION BY idempotency_key) AS key_count
  FROM posted_payments
  WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) != ''
)
WHERE n > 1;

CREATE VIEW v_attempt_exceptions AS
SELECT
  reason,
  'attempt' AS entity_type,
  attempt_id AS entity_id,
  claim_id,
  patient_id,
  amount_cents,
  detail
FROM (
  SELECT
    a.attempt_id,
    a.claim_id,
    a.patient_id,
    a.amount_cents,
    a.idempotency_key,
    a.attempt_status,
    a.requested_at,
    a.processor_code,
    n.remaining_cents,
    CASE
      WHEN a.attempt_status = 'failed' AND posted.attempt_id IS NOT NULL
        THEN 'status_failed_but_settled'
      WHEN a.attempt_status = 'declined' AND posted.attempt_id IS NOT NULL
        THEN 'declined_but_posted'
      WHEN a.attempt_status IN ('pending', 'failed')
        AND a.requested_at < date(
          (SELECT as_of FROM settings),
          '-' || (SELECT stuck_days FROM settings) || ' days'
        )
        AND EXISTS (
          SELECT 1 FROM posted_payments p
          WHERE p.idempotency_key = a.idempotency_key
            AND TRIM(COALESCE(a.idempotency_key, '')) != ''
        )
        THEN 'blocked_duplicate_key'
      WHEN a.attempt_status IN ('pending', 'failed')
        AND a.requested_at < date(
          (SELECT as_of FROM settings),
          '-' || (SELECT stuck_days FROM settings) || ' days'
        )
        AND EXISTS (
          SELECT 1
          FROM refunds rf
          JOIN posted_payments pp ON pp.payment_id = rf.payment_id
          WHERE pp.claim_id = a.claim_id
            AND rf.refund_status IN ('requested', 'issued')
        )
        THEN 'blocked_refund_in_flight'
      WHEN a.attempt_status IN ('pending', 'failed')
        AND a.method IN ('patient_card', 'patient_ach')
        AND a.requested_at < date(
          (SELECT as_of FROM settings),
          '-' || (SELECT stuck_days FROM settings) || ' days'
        )
        AND c.claim_status IN ('open', 'partial')
        AND n.ties_out = 1
        AND a.amount_cents = n.remaining_cents
        AND n.remaining_cents > 0
        THEN 'safe_to_reprocess'
      WHEN a.attempt_status IN ('pending', 'failed')
        AND a.requested_at < date(
          (SELECT as_of FROM settings),
          '-' || (SELECT stuck_days FROM settings) || ' days'
        )
        AND c.claim_id IS NOT NULL
        AND n.ties_out = 1
        AND a.amount_cents != n.remaining_cents
        THEN 'amount_mismatch'
      ELSE NULL
    END AS reason,
    CASE
      WHEN a.attempt_status = 'failed' AND posted.attempt_id IS NOT NULL
        THEN printf(
          'Attempt %s is failed (%s) but payment %s posted on %s.',
          a.attempt_id, COALESCE(a.processor_code, 'no code'),
          posted.payment_id, posted.posted_at
        )
      WHEN a.attempt_status = 'declined' AND posted.attempt_id IS NOT NULL
        THEN printf(
          'Attempt %s declined (%s) and payment %s was still posted from %s.',
          a.attempt_id, COALESCE(a.processor_code, 'no code'),
          posted.payment_id, posted.source
        )
      WHEN EXISTS (
          SELECT 1 FROM posted_payments p
          WHERE p.idempotency_key = a.idempotency_key
            AND TRIM(COALESCE(a.idempotency_key, '')) != ''
        )
        THEN printf(
          'Key %s is already posted. Retrying attempt %s would send another $%.2f.',
          a.idempotency_key, a.attempt_id, a.amount_cents / 100.0
        )
      WHEN EXISTS (
          SELECT 1
          FROM refunds rf
          JOIN posted_payments pp ON pp.payment_id = rf.payment_id
          WHERE pp.claim_id = a.claim_id
            AND rf.refund_status IN ('requested', 'issued')
        )
        THEN printf(
          'Attempt %s cannot be retried. Claim %s has a refund in flight.',
          a.attempt_id, a.claim_id
        )
      WHEN a.amount_cents = n.remaining_cents
        THEN printf(
          'Attempt %s has been %s since %s for the open balance.',
          a.attempt_id, a.attempt_status, a.requested_at
        )
      ELSE printf(
        'Attempt %s is $%.2f; open balance on %s is $%.2f.',
        a.attempt_id, a.amount_cents / 100.0, a.claim_id,
        COALESCE(n.remaining_cents, 0) / 100.0
      )
    END AS detail
  FROM payment_attempts a
  LEFT JOIN claims c ON c.claim_id = a.claim_id
  LEFT JOIN v_claim_net n ON n.claim_id = a.claim_id
  LEFT JOIN (
    SELECT attempt_id, MIN(payment_id) AS payment_id, MIN(posted_at) AS posted_at, MIN(source) AS source
    FROM posted_payments
    WHERE attempt_id IS NOT NULL AND TRIM(attempt_id) != ''
    GROUP BY attempt_id
  ) posted ON posted.attempt_id = a.attempt_id
)
WHERE reason IS NOT NULL;

CREATE VIEW v_exceptions AS
SELECT
  e.reason,
  a.action,
  e.entity_type,
  e.entity_id,
  e.claim_id,
  e.patient_id,
  e.amount_cents,
  e.detail
FROM (
  SELECT
    'duplicate_post' AS reason,
    'payment' AS entity_type,
    d.payment_id AS entity_id,
    d.claim_id,
    d.patient_id,
    d.amount_cents,
    printf(
      'Key %s is on %d posted payments. %s on %s is an extra $%.2f.',
      d.idempotency_key, d.key_count, d.payment_id, d.posted_at, d.amount_cents / 100.0
    ) AS detail
  FROM v_duplicate_posts d

  UNION ALL

  SELECT
    reason,
    entity_type,
    entity_id,
    claim_id,
    patient_id,
    CASE
      WHEN reason = 'amount_mismatch' THEN ABS(amount_cents - (
        SELECT remaining_cents FROM v_claim_net n WHERE n.claim_id = v.claim_id
      ))
      ELSE amount_cents
    END AS amount_cents,
    detail
  FROM v_attempt_exceptions v

  UNION ALL

  SELECT
    'misapplied_payment',
    'payment',
    p.payment_id,
    p.claim_id,
    p.patient_id,
    p.amount_cents,
    printf(
      'Payment %s is on patient %s; claim %s belongs to %s.',
      p.payment_id, p.patient_id, c.claim_id, c.patient_id
    )
  FROM posted_payments p
  JOIN claims c ON c.claim_id = p.claim_id
  WHERE p.patient_id != c.patient_id

  UNION ALL

  SELECT
    'orphan_payment',
    'payment',
    p.payment_id,
    p.claim_id,
    p.patient_id,
    p.amount_cents,
    printf(
      'Payment %s for $%.2f has no matching claim.',
      p.payment_id, p.amount_cents / 100.0
    )
  FROM posted_payments p
  LEFT JOIN claims c ON c.claim_id = p.claim_id
  WHERE c.claim_id IS NULL

  UNION ALL

  SELECT
    'overpayment',
    'claim',
    n.claim_id,
    n.claim_id,
    n.patient_id,
    n.net_cents - n.allowed_cents,
    printf(
      'Claim %s net posted is $%.2f; allowed is $%.2f.',
      n.claim_id, n.net_cents / 100.0, n.allowed_cents / 100.0
    )
  FROM v_claim_net n
  WHERE n.ties_out = 1
    AND n.claim_status != 'void'
    AND n.net_cents - n.allowed_cents > 1
    AND n.claim_id NOT IN (
      SELECT claim_id FROM v_duplicate_posts WHERE claim_id IS NOT NULL
    )

  UNION ALL

  SELECT
    'refund_exceeds_payment',
    'refund',
    rf.refund_id,
    pp.claim_id,
    pp.patient_id,
    rf.amount_cents - pp.amount_cents,
    printf(
      'Refund %s is $%.2f against payment %s of $%.2f (%s).',
      rf.refund_id, rf.amount_cents / 100.0, pp.payment_id, pp.amount_cents / 100.0, rf.refund_status
    )
  FROM refunds rf
  JOIN posted_payments pp ON pp.payment_id = rf.payment_id
  WHERE rf.refund_status IN ('requested', 'issued')
    AND rf.amount_cents > pp.amount_cents

  UNION ALL

  SELECT
    'denied_with_payment',
    'claim',
    n.claim_id,
    n.claim_id,
    n.patient_id,
    n.net_cents,
    printf(
      'Claim %s is denied %s and still has $%.2f net posted.',
      n.claim_id, COALESCE(n.denial_code, '(no code)'), n.net_cents / 100.0
    )
  FROM v_claim_net n
  WHERE n.claim_status = 'denied'
    AND n.net_cents > 1

  UNION ALL

  SELECT
    'insurance_short_pay',
    'claim',
    n.claim_id,
    n.claim_id,
    n.patient_id,
    n.insurance_resp_cents - n.era_cents,
    printf(
      'Claim %s ERA is $%.2f; insurance responsibility is $%.2f. No denial code.',
      n.claim_id, n.era_cents / 100.0, n.insurance_resp_cents / 100.0
    )
  FROM v_claim_net n
  WHERE n.ties_out = 1
    AND n.claim_status NOT IN ('denied', 'void')
    AND n.insurance_resp_cents - n.era_cents > 1
    AND n.claim_id NOT IN (
      SELECT claim_id FROM v_duplicate_posts WHERE claim_id IS NOT NULL
    )

  UNION ALL

  SELECT
    'open_patient_balance',
    'claim',
    n.claim_id,
    n.claim_id,
    n.patient_id,
    n.patient_resp_cents - n.patient_net_cents,
    printf(
      'Claim %s still has $%.2f of patient responsibility and no payment in flight.',
      n.claim_id, (n.patient_resp_cents - n.patient_net_cents) / 100.0
    )
  FROM v_claim_net n
  WHERE n.ties_out = 1
    AND n.claim_status IN ('open', 'partial')
    AND n.patient_resp_cents - n.patient_net_cents > 1
    AND n.claim_id NOT IN (
      SELECT claim_id FROM v_duplicate_posts WHERE claim_id IS NOT NULL
    )
    AND NOT EXISTS (
      SELECT 1 FROM payment_attempts a
      WHERE a.claim_id = n.claim_id
        AND a.attempt_status IN ('pending', 'failed')
        AND a.method IN ('patient_card', 'patient_ach', 'check', 'carecredit', 'hsa')
    )

  UNION ALL

  SELECT
    'source_does_not_tie',
    'claim',
    n.claim_id,
    n.claim_id,
    n.patient_id,
    ABS(n.allowed_cents - n.patient_resp_cents - n.insurance_resp_cents),
    printf(
      'Claim %s allowed $%.2f, but patient $%.2f + insurance $%.2f = $%.2f.',
      n.claim_id, n.allowed_cents / 100.0, n.patient_resp_cents / 100.0,
      n.insurance_resp_cents / 100.0,
      (n.patient_resp_cents + n.insurance_resp_cents) / 100.0
    )
  FROM v_claim_net n
  WHERE n.ties_out = 0
) e
JOIN exception_actions a ON a.reason = e.reason;
