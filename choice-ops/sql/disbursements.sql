-- Outbound disbursement ledger for Choice Digital ops practice.
-- Synthetic only. Apply with: python3 choice-ops/python/seed.py
--
-- Named queries (-- query: name) use bound parameters. investigate_failure.py
-- runs those. Piping this whole file into the sqlite3 shell will fail on the
-- binds. The schema above the first named query is the table layout.

CREATE TABLE settings (
  as_of TEXT NOT NULL,
  pending_window_hours INTEGER NOT NULL
);

CREATE TABLE clients (
  client_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE recipients (
  recipient_id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES clients(client_id),
  label TEXT NOT NULL
);

-- One row per outbound disbursement attempt.
-- idempotency_key is intentionally NOT unique: a second row with a settled
-- key is the duplicate-payment case these tools refuse to retry.
-- trace_number is intentionally NOT unique: a shared trace is a finding.
CREATE TABLE disbursements (
  disbursement_id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL REFERENCES clients(client_id),
  recipient_id TEXT NOT NULL REFERENCES recipients(recipient_id),
  method TEXT NOT NULL CHECK (method IN ('ACH', 'prepaid', 'check', 'instant')),
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  status TEXT NOT NULL CHECK (status IN (
    'pending', 'submitted', 'settled', 'failed', 'returned', 'rejected'
  )),
  idempotency_key TEXT NOT NULL,
  trace_number TEXT,
  processor_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  batch_id TEXT
);

CREATE INDEX idx_disbursements_idempotency ON disbursements(idempotency_key);
CREATE INDEX idx_disbursements_trace ON disbursements(trace_number);
CREATE INDEX idx_disbursements_client_status ON disbursements(client_id, status);

-- Landed copy of the JSONL log so the queries below can join it.
-- investigate_failure.py still reads the JSONL as the evidence file.
CREATE TABLE api_events (
  event_id TEXT PRIMARY KEY,
  disbursement_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_name TEXT,
  occurred_at TEXT NOT NULL,
  http_status INTEGER,
  processor_code TEXT,
  event_status TEXT,
  amount_cents INTEGER,
  idempotency_key TEXT,
  message TEXT,
  parse_error INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_api_events_disbursement ON api_events(disbursement_id, occurred_at);

-- A plan row is not a payment. reprocess.py --execute inserts here only.
-- It does not insert into disbursements.
CREATE TABLE reprocess_queue (
  plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
  disbursement_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL,
  amount_cents INTEGER NOT NULL,
  plan_reason TEXT NOT NULL,
  planned_at TEXT NOT NULL
);

-- query: by_id
SELECT d.disbursement_id,
       d.client_id,
       c.name AS client_name,
       d.recipient_id,
       r.label AS recipient_label,
       d.method,
       d.amount_cents,
       d.status,
       d.idempotency_key,
       d.trace_number,
       d.processor_code,
       d.created_at,
       d.updated_at,
       d.batch_id
FROM disbursements d
JOIN clients c ON c.client_id = d.client_id
JOIN recipients r ON r.recipient_id = d.recipient_id
WHERE d.disbursement_id = :disbursement_id

-- query: same_idempotency
SELECT disbursement_id, status, amount_cents, method, trace_number, updated_at
FROM disbursements
WHERE idempotency_key = :idempotency_key
ORDER BY created_at, disbursement_id

-- query: same_trace
SELECT disbursement_id, status, amount_cents, method, idempotency_key, updated_at
FROM disbursements
WHERE trace_number = :trace_number
ORDER BY created_at, disbursement_id

-- query: events_for_id
SELECT event_id, event_type, event_name, occurred_at, http_status,
       processor_code, event_status, amount_cents, message, parse_error
FROM api_events
WHERE disbursement_id = :disbursement_id
ORDER BY occurred_at, event_id

-- query: webhook_settled_row_not_settled
SELECT d.disbursement_id,
       d.status AS row_status,
       e.event_id,
       e.event_status AS webhook_status
FROM disbursements d
JOIN api_events e ON e.disbursement_id = d.disbursement_id
WHERE e.event_type = 'webhook'
  AND e.event_status = 'settled'
  AND d.status <> 'settled'

-- query: amount_mismatches
SELECT d.disbursement_id,
       d.amount_cents AS row_cents,
       e.event_id,
       e.amount_cents AS event_cents
FROM disbursements d
JOIN api_events e ON e.disbursement_id = d.disbursement_id
WHERE e.amount_cents IS NOT NULL
  AND e.amount_cents <> d.amount_cents

-- query: duplicate_traces
SELECT trace_number,
       COUNT(*) AS n,
       GROUP_CONCAT(disbursement_id) AS disbursement_ids
FROM disbursements
WHERE trace_number IS NOT NULL
GROUP BY trace_number
HAVING COUNT(*) > 1

-- query: duplicate_idempotency_keys
SELECT idempotency_key,
       COUNT(*) AS n,
       GROUP_CONCAT(disbursement_id) AS disbursement_ids,
       GROUP_CONCAT(status) AS statuses
FROM disbursements
GROUP BY idempotency_key
HAVING COUNT(*) > 1
