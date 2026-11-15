-- Payment exception ledger (SQLite).
-- One week of dental claims, attempts, posted cash, and refunds.
-- Idempotency key = ERA trace, EFT/check number, or card/ACH auth.
-- Foreign keys are intentionally off: a missing claim id is a finding,
-- and a constraint would hide it.

CREATE TABLE settings (
  as_of TEXT NOT NULL,
  stuck_days INTEGER NOT NULL
);

CREATE TABLE claims (
  claim_id TEXT PRIMARY KEY,
  patient_id TEXT NOT NULL,
  payer TEXT NOT NULL,
  service_date TEXT NOT NULL,
  billed_cents INTEGER NOT NULL,
  allowed_cents INTEGER NOT NULL,
  patient_resp_cents INTEGER NOT NULL,
  insurance_resp_cents INTEGER NOT NULL,
  claim_status TEXT NOT NULL, -- open, partial, paid, denied, void
  denial_code TEXT
);

CREATE TABLE payment_attempts (
  attempt_id TEXT PRIMARY KEY,
  claim_id TEXT,
  patient_id TEXT NOT NULL,
  method TEXT NOT NULL, -- patient_card, patient_ach, insurance_era, check, carecredit, hsa
  amount_cents INTEGER NOT NULL,
  idempotency_key TEXT,
  requested_at TEXT NOT NULL,
  attempt_status TEXT NOT NULL, -- pending, failed, declined, settled
  processor_code TEXT,
  processor_ref TEXT
);

CREATE TABLE posted_payments (
  payment_id TEXT PRIMARY KEY,
  attempt_id TEXT,
  claim_id TEXT,
  patient_id TEXT NOT NULL,
  method TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  posted_at TEXT NOT NULL,
  idempotency_key TEXT,
  source TEXT NOT NULL -- era, card_webhook, ach, manual
);

CREATE TABLE refunds (
  refund_id TEXT PRIMARY KEY,
  payment_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  refund_status TEXT NOT NULL, -- requested, issued, failed
  reason TEXT
);

-- Present only for the synthetic fixture. Real exports omit this file.
CREATE TABLE scenario_tags (
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  expected_reason TEXT NOT NULL
);

CREATE TABLE exception_actions (
  reason TEXT PRIMARY KEY,
  action TEXT NOT NULL
);

CREATE TABLE reprocess_queue (
  attempt_id TEXT PRIMARY KEY,
  claim_id TEXT,
  patient_id TEXT,
  amount_cents INTEGER NOT NULL,
  idempotency_key TEXT,
  plan_status TEXT NOT NULL, -- planned
  created_at TEXT NOT NULL
);

INSERT INTO exception_actions (reason, action) VALUES
  ('duplicate_post', 'Reverse the extra post. Do not reprocess this key.'),
  ('status_failed_but_settled', 'Mark the attempt settled. Do not send it again.'),
  ('declined_but_posted', 'Processor declined this charge, but cash is posted. Confirm, then reverse it or take a new authorization.'),
  ('misapplied_payment', 'Move the payment to the patient on the claim. Do not collect it again.'),
  ('orphan_payment', 'Apply the cash to an open claim or refund it. It is not attached to a claim.'),
  ('overpayment', 'Refund the amount above the allowed fee. Do not reprocess.'),
  ('refund_exceeds_payment', 'Hold the refund. It is larger than the original payment.'),
  ('denied_with_payment', 'The claim is denied and cash is posted. Confirm which record is wrong before an appeal or a refund.'),
  ('insurance_short_pay', 'Insurance paid less than the contracted responsibility and there is no denial. Appeal or rebill. This is not a card retry.'),
  ('open_patient_balance', 'Patient balance is open and nothing is in flight. Collections follow-up, not a reprocess.'),
  ('source_does_not_tie', 'Allowed amount does not equal patient responsibility plus insurance responsibility. Fix the expected amount before chasing cash.'),
  ('blocked_duplicate_key', 'This idempotency key is already posted. Block the retry so the patient or payer is not charged twice.'),
  ('blocked_refund_in_flight', 'A refund is requested or already issued on this claim. Do not collect again until that refund is resolved.'),
  ('safe_to_reprocess', 'Patient card or ACH is still pending or failed, the key was never posted, and the amount equals the open balance.'),
  ('amount_mismatch', 'The retry amount does not equal the open balance. Review it before anything is sent.');

CREATE INDEX idx_pay_claim ON posted_payments (claim_id);
CREATE INDEX idx_pay_key ON posted_payments (idempotency_key);
CREATE INDEX idx_pay_attempt ON posted_payments (attempt_id);
CREATE INDEX idx_attempt_claim ON payment_attempts (claim_id);
CREATE INDEX idx_attempt_key ON payment_attempts (idempotency_key);
CREATE INDEX idx_refund_payment ON refunds (payment_id);
