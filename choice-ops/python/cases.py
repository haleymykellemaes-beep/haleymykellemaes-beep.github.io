"""Synthetic Choice Digital incidents. No real people, accounts, or amounts from production.

Eight failure types are planted. Safe retries and clean batch rows are planted
beside them so a tool that flags everything still fails the self-check.
"""

from __future__ import annotations

AS_OF = "2026-11-15T17:00:00Z"
PENDING_WINDOW_HOURS = 24
BATCH_CLIENT = "northwind"

CLIENTS = [
    ("peak", "Peak Payroll Services (synthetic)"),
    ("linden", "Linden Claims Admin (synthetic)"),
    ("northwind", "Northwind Benefits (synthetic)"),
]

# Eight planted causes. Dollar totals in the README come from these rows.
INVESTIGATE_EXPECT = {
    "DSP-7001": "status_mismatch",
    "DSP-7002": "ach_r01",
    "DSP-7003": "ach_r03",
    "DSP-7004": "batch_rejected",
    "DSP-7005": "duplicate_trace",
    "DSP-7006": "duplicate_trace",
    "DSP-7007": "idempotency_already_settled",
    "DSP-7009": "return_in_flight",
    "DSP-7010": "amount_mismatch",
}

CAUSE_ORDER = [
    "status_mismatch",
    "ach_r01",
    "ach_r03",
    "batch_rejected",
    "duplicate_trace",
    "idempotency_already_settled",
    "return_in_flight",
    "amount_mismatch",
]

# reason "safe" is allowed onto the plan queue. Every other reason is a block.
REPROCESS_EXPECT = {
    "DSP-7001": "webhook_already_settled",
    "DSP-7002": "return_already_received",
    "DSP-7003": "fix_recipient_data",
    "DSP-7004": "fix_before_retry",
    "DSP-7006": "duplicate_trace",
    "DSP-7007": "idempotency_already_settled",
    "DSP-7009": "return_already_received",
    "DSP-7010": "amount_changed",
    "DSP-7011": "safe",
    "DSP-7012": "safe",
    "DSP-7013": "safe",
    "DSP-7014": "pending_inside_window",
}

RECONCILE_EXPECT = {
    "matched": {"TR-9001", "TR-9002", "TR-9003"},
    "missing_from_batch": {"TR-9101"},
    "in_batch_not_sent": {"TR-9102"},
    "amount_mismatch": {"TR-9103"},
    "duplicate_trace": {"TR-9104"},
}

SQL_EXPECT = {
    "webhook_settled_row_not_settled": {"DSP-7001"},
    "amount_mismatches": {"DSP-7010"},
    "duplicate_traces": {"TR-DUP-55"},
    "duplicate_idempotency_keys": {"idem-shared-7007"},
}


def _row(
    disbursement_id,
    client_id,
    recipient_id,
    method,
    amount_cents,
    status,
    idempotency_key,
    trace_number,
    processor_code,
    created_at,
    updated_at,
    batch_id=None,
):
    return {
        "disbursement_id": disbursement_id,
        "client_id": client_id,
        "recipient_id": recipient_id,
        "method": method,
        "amount_cents": amount_cents,
        "status": status,
        "idempotency_key": idempotency_key,
        "trace_number": trace_number,
        "processor_code": processor_code,
        "created_at": created_at,
        "updated_at": updated_at,
        "batch_id": batch_id,
    }


DISBURSEMENTS = [
    # Webhook settled, ledger still failed. Retrying would pay twice.
    _row("DSP-7001", "peak", "SYN-R-7001", "ACH", 125000, "failed",
         "idem-7001", "TR-7001", None,
         "2026-11-12T15:01:02Z", "2026-11-12T18:22:11Z"),
    # ACH return R01. The return is already on the row.
    _row("DSP-7002", "peak", "SYN-R-7002", "ACH", 48000, "returned",
         "idem-7002", "TR-7002", "R01",
         "2026-11-10T13:00:00Z", "2026-11-12T09:15:00Z"),
    # ACH return R03. Recipient token could not be located. Fix the data.
    _row("DSP-7003", "linden", "SYN-R-7003", "ACH", 91550, "returned",
         "idem-7003", "TR-7003", "R03",
         "2026-11-09T11:00:00Z", "2026-11-11T16:40:00Z"),
    # Check batch row rejected before anything was mailed.
    _row("DSP-7004", "linden", "SYN-R-7004", "check", 22000, "rejected",
         "idem-7004", "CHK-7004", "BATCH_REJECT",
         "2026-11-14T08:00:00Z", "2026-11-14T08:05:00Z", "B-LINDEN-1114"),
    # Same prepaid trace on a settled row and a second submitted row.
    _row("DSP-7005", "peak", "SYN-R-7005", "prepaid", 64000, "settled",
         "idem-7005", "TR-DUP-55", "00",
         "2026-11-08T12:00:00Z", "2026-11-08T12:10:00Z"),
    _row("DSP-7006", "peak", "SYN-R-7005", "prepaid", 64000, "submitted",
         "idem-7006", "TR-DUP-55", "00",
         "2026-11-08T12:20:00Z", "2026-11-08T12:20:04Z"),
    # Timeout row plus a settled row that already used the same idempotency key.
    _row("DSP-7007", "linden", "SYN-R-7007", "instant", 180000, "failed",
         "idem-shared-7007", "TR-7007", "96",
         "2026-11-07T17:00:00Z", "2026-11-07T17:00:21Z"),
    _row("DSP-7008", "linden", "SYN-R-7007", "instant", 180000, "settled",
         "idem-shared-7007", "TR-7008", "00",
         "2026-11-07T17:00:00Z", "2026-11-07T17:01:05Z"),
    # Return webhook arrived. The ledger row has not moved off failed.
    _row("DSP-7009", "peak", "SYN-R-7009", "ACH", 35000, "failed",
         "idem-7009", "TR-7009", None,
         "2026-11-13T14:12:00Z", "2026-11-13T14:12:20Z"),
    # Processor ack is 75500 cents. The ledger row is 75000.
    _row("DSP-7010", "peak", "SYN-R-7010", "ACH", 75000, "failed",
         "idem-7010", "TR-7010", "96",
         "2026-11-11T10:00:00Z", "2026-11-11T10:00:30Z"),
    # Clean timeout. Safe to plan, not safe to invent a second live payment.
    _row("DSP-7011", "peak", "SYN-R-7011", "prepaid", 41000, "failed",
         "idem-7011", "TR-7011", "96",
         "2026-11-14T10:00:00Z", "2026-11-14T10:00:08Z"),
    _row("DSP-7012", "linden", "SYN-R-7012", "check", 12850, "failed",
         "idem-7012", "CHK-7012", "91",
         "2026-11-14T11:30:00Z", "2026-11-14T11:30:06Z"),
    # Pending since Nov 13. As-of is Nov 15 17:00Z, so the 24h window has passed.
    _row("DSP-7013", "peak", "SYN-R-7013", "ACH", 9900, "pending",
         "idem-7013", "TR-7013", "00",
         "2026-11-13T16:00:00Z", "2026-11-13T16:00:00Z"),
    # Pending for 30 minutes. Leave it alone.
    _row("DSP-7014", "linden", "SYN-R-7014", "instant", 50000, "pending",
         "idem-7014", "TR-7014", "00",
         "2026-11-15T16:30:00Z", "2026-11-15T16:30:00Z"),
    # Northwind batch control. Compared to batch_northwind_20261114.csv.
    _row("DSP-9001", "northwind", "SYN-R-9001", "ACH", 20000, "settled",
         "idem-9001", "TR-9001", "00",
         "2026-11-14T09:00:00Z", "2026-11-14T15:00:00Z", "B-20261114"),
    _row("DSP-9002", "northwind", "SYN-R-9002", "prepaid", 45000, "settled",
         "idem-9002", "TR-9002", "00",
         "2026-11-14T09:01:00Z", "2026-11-14T15:01:00Z", "B-20261114"),
    _row("DSP-9003", "northwind", "SYN-R-9003", "check", 100000, "settled",
         "idem-9003", "TR-9003", "00",
         "2026-11-14T09:02:00Z", "2026-11-14T15:02:00Z", "B-20261114"),
    _row("DSP-9101", "northwind", "SYN-R-9101", "ACH", 20000, "settled",
         "idem-9101", "TR-9101", "00",
         "2026-11-14T09:03:00Z", "2026-11-14T15:03:00Z", "B-20261114"),
    _row("DSP-9103", "northwind", "SYN-R-9103", "ACH", 30000, "settled",
         "idem-9103", "TR-9103", "00",
         "2026-11-14T09:04:00Z", "2026-11-14T15:04:00Z", "B-20261114"),
    _row("DSP-9104", "northwind", "SYN-R-9104", "prepaid", 6400, "settled",
         "idem-9104", "TR-9104", "00",
         "2026-11-14T09:05:00Z", "2026-11-14T15:05:00Z", "B-20261114"),
]


def _event(
    event_id,
    disbursement_id,
    event_type,
    event_name,
    at,
    *,
    http_status=200,
    processor_code=None,
    status=None,
    amount_cents=None,
    idempotency_key=None,
    message="",
    parse_error=False,
    action=None,
):
    row = {
        "event_id": event_id,
        "disbursement_id": disbursement_id,
        "type": event_type,
        "event": event_name,
        "at": at,
        "http_status": http_status,
        "processor_code": processor_code,
        "status": status,
        "amount_cents": amount_cents,
        "idempotency_key": idempotency_key,
        "message": message,
        "parse_error": parse_error,
    }
    if action:
        row["action"] = action
    return row


EVENTS = [
    _event("evt-7001-api", "DSP-7001", "api.response", "api.disbursement.create",
           "2026-11-12T15:01:02Z", processor_code="00", status="submitted",
           amount_cents=125000, idempotency_key="idem-7001",
           message="Create call accepted. Status on this response is submitted."),
    _event("evt-7001-wh", "DSP-7001", "webhook", "disbursement.settled",
           "2026-11-12T18:22:10Z", processor_code="00", status="settled",
           amount_cents=125000, idempotency_key="idem-7001",
           message="Settlement webhook. The ledger row was written failed anyway.",
           action="do_not_retry"),
    _event("evt-7002-api", "DSP-7002", "api.response", "api.disbursement.create",
           "2026-11-10T13:00:00Z", processor_code="00", status="submitted",
           amount_cents=48000, idempotency_key="idem-7002",
           message="ACH create accepted."),
    _event("evt-7002-wh", "DSP-7002", "webhook", "disbursement.returned",
           "2026-11-12T09:14:40Z", processor_code="R01", status="returned",
           amount_cents=48000, idempotency_key="idem-7002",
           message="ACH return R01 insufficient funds. Another send today does not clear the return.",
           action="wait_for_return_window"),
    _event("evt-7003-api", "DSP-7003", "api.response", "api.disbursement.create",
           "2026-11-09T11:00:00Z", processor_code="00", status="submitted",
           amount_cents=91550, idempotency_key="idem-7003",
           message="ACH create accepted."),
    _event("evt-7003-wh", "DSP-7003", "webhook", "disbursement.returned",
           "2026-11-11T16:39:10Z", processor_code="R03", status="returned",
           amount_cents=91550, idempotency_key="idem-7003",
           message="ACH return R03 unable to locate account. Recipient token was rejected. No account number is stored in this fixture.",
           action="fix_recipient_data"),
    _event("evt-7004-batch", "DSP-7004", "batch.reject", "batch.row.rejected",
           "2026-11-14T08:05:00Z", http_status=None, processor_code="BATCH_REJECT",
           status="rejected", amount_cents=22000, idempotency_key="idem-7004",
           message="Check batch row rejected: mail-to name missing. Fix the recipient record before the next file.",
           action="fix_recipient_data"),
    _event("evt-7005-api", "DSP-7005", "api.response", "api.disbursement.create",
           "2026-11-08T12:00:00Z", processor_code="00", status="submitted",
           amount_cents=64000, idempotency_key="idem-7005",
           message="Prepaid create accepted."),
    _event("evt-7005-wh", "DSP-7005", "webhook", "disbursement.settled",
           "2026-11-08T12:09:40Z", processor_code="00", status="settled",
           amount_cents=64000, idempotency_key="idem-7005",
           message="Prepaid settled under trace TR-DUP-55.",
           action="do_not_retry"),
    _event("evt-7006-api", "DSP-7006", "api.response", "api.disbursement.create",
           "2026-11-08T12:20:04Z", processor_code="00", status="submitted",
           amount_cents=64000, idempotency_key="idem-7006",
           message="Second prepaid create accepted with the same trace TR-DUP-55."),
    _event("evt-7007-api", "DSP-7007", "api.response", "api.disbursement.create",
           "2026-11-07T17:00:21Z", http_status=504, processor_code="96",
           status="failed", amount_cents=180000, idempotency_key="idem-shared-7007",
           message="Timeout. This row was marked failed. The same idempotency key later settled on DSP-7008."),
    _event("evt-7008-api", "DSP-7008", "api.response", "api.disbursement.create",
           "2026-11-07T17:00:02Z", processor_code="00", status="submitted",
           amount_cents=180000, idempotency_key="idem-shared-7007",
           message="Create accepted on the row that actually settled."),
    _event("evt-7008-wh", "DSP-7008", "webhook", "disbursement.settled",
           "2026-11-07T17:01:05Z", processor_code="00", status="settled",
           amount_cents=180000, idempotency_key="idem-shared-7007",
           message="Settled. Idempotency key idem-shared-7007 is spent.",
           action="do_not_retry"),
    _event("evt-7009-api", "DSP-7009", "api.response", "api.disbursement.create",
           "2026-11-13T14:12:00Z", processor_code="00", status="submitted",
           amount_cents=35000, idempotency_key="idem-7009",
           message="ACH create accepted."),
    _event("evt-7009-wh", "DSP-7009", "webhook", "disbursement.returned",
           "2026-11-14T08:02:00Z", processor_code="R01", status="returned",
           amount_cents=35000, idempotency_key="idem-7009",
           message="Return is on the webhook. The ledger row still says failed.",
           action="wait_for_return_window"),
    _event("evt-7010-api", "DSP-7010", "api.response", "api.disbursement.create",
           "2026-11-11T10:00:04Z", processor_code="00", status="submitted",
           amount_cents=75500, idempotency_key="idem-7010",
           message="Processor acknowledged $755.00. The ledger amount is $750.00."),
    _event("evt-7011-wh", "DSP-7011", "webhook", "disbursement.failed",
           "2026-11-14T10:00:08Z", http_status=504, processor_code="96",
           status="failed", amount_cents=41000, idempotency_key="idem-7011",
           message="Timeout. Amount matches. No return and no settled sibling.",
           action="retry"),
    _event("evt-7012-wh", "DSP-7012", "webhook", "disbursement.failed",
           "2026-11-14T11:30:06Z", http_status=503, processor_code="91",
           status="failed", amount_cents=12850, idempotency_key="idem-7012",
           message="Processor unavailable. Amount matches. No return and no settled sibling.",
           action="retry"),
    _event("evt-7013-api", "DSP-7013", "api.response", "api.disbursement.create",
           "2026-11-13T16:00:00Z", http_status=202, processor_code="00",
           status="pending", amount_cents=9900, idempotency_key="idem-7013",
           message="Accepted and still pending the next morning."),
    _event("evt-7014-api", "DSP-7014", "api.response", "api.disbursement.create",
           "2026-11-15T16:30:00Z", http_status=202, processor_code="00",
           status="pending", amount_cents=50000, idempotency_key="idem-7014",
           message="Accepted 30 minutes before the as-of clock. Still inside the window."),
    _event("evt-9001-wh", "DSP-9001", "webhook", "disbursement.settled",
           "2026-11-14T15:00:00Z", processor_code="00", status="settled",
           amount_cents=20000, idempotency_key="idem-9001",
           message="Northwind batch row settled.", action="do_not_retry"),
    _event("evt-9002-wh", "DSP-9002", "webhook", "disbursement.settled",
           "2026-11-14T15:01:00Z", processor_code="00", status="settled",
           amount_cents=45000, idempotency_key="idem-9002",
           message="Northwind batch row settled.", action="do_not_retry"),
    _event("evt-9003-wh", "DSP-9003", "webhook", "disbursement.settled",
           "2026-11-14T15:02:00Z", processor_code="00", status="settled",
           amount_cents=100000, idempotency_key="idem-9003",
           message="Northwind batch row settled.", action="do_not_retry"),
    _event("evt-9101-wh", "DSP-9101", "webhook", "disbursement.settled",
           "2026-11-14T15:03:00Z", processor_code="00", status="settled",
           amount_cents=20000, idempotency_key="idem-9101",
           message="Settled, then left off the client batch file.",
           action="do_not_retry"),
    _event("evt-9103-wh", "DSP-9103", "webhook", "disbursement.settled",
           "2026-11-14T15:04:00Z", processor_code="00", status="settled",
           amount_cents=30000, idempotency_key="idem-9103",
           message="Settled at 30000 cents. The client file says 28000.",
           action="do_not_retry"),
    _event("evt-9104-wh", "DSP-9104", "webhook", "disbursement.settled",
           "2026-11-14T15:05:00Z", processor_code="00", status="settled",
           amount_cents=6400, idempotency_key="idem-9104",
           message="One settled disbursement. The client file lists the trace twice.",
           action="do_not_retry"),
    _event("evt-escalate-01", "DSP-WH-UNKNOWN", "webhook", "disbursement.update",
           "2026-11-15T12:00:00Z", http_status=200, message="Body was not JSON. Raw gateway bytes are not in this fixture.",
           parse_error=True, action="escalate_to_engineering"),
]

BATCH_ROWS = [
    ("B-20261114", "TR-9001", "SYN-R-9001", "ACH", 20000, "2026-11-14"),
    ("B-20261114", "TR-9002", "SYN-R-9002", "prepaid", 45000, "2026-11-14"),
    ("B-20261114", "TR-9003", "SYN-R-9003", "check", 100000, "2026-11-14"),
    ("B-20261114", "TR-9102", "SYN-R-9102", "ACH", 15000, "2026-11-14"),
    ("B-20261114", "TR-9103", "SYN-R-9103", "ACH", 28000, "2026-11-14"),
    ("B-20261114", "TR-9104", "SYN-R-9104", "prepaid", 6400, "2026-11-14"),
    ("B-20261114", "TR-9104", "SYN-R-9104", "prepaid", 6400, "2026-11-14"),
]

BATCH_HEADER = [
    "client_batch_id",
    "trace_number",
    "recipient_ref",
    "method",
    "amount_cents",
    "requested_date",
]

CAUSE_TEXT = {
    "status_mismatch": (
        "The webhook says settled and the ledger still says failed. "
        "Do not reprocess. Confirm settlement with the processor, then correct this row in place. "
        "Sending it again pays the recipient twice. Ops label: escalate_to_engineering."
    ),
    "ach_r01": (
        "ACH return R01, insufficient funds, is already on the row. "
        "Wait for the return window. A same-day retry will not make the debit good. "
        "Ops label: wait_for_return_window."
    ),
    "ach_r03": (
        "ACH return R03, unable to locate account. The recipient token was rejected. "
        "Fix the recipient record. Another send to the same token fails the same way. "
        "Ops label: fix_recipient_data."
    ),
    "batch_rejected": (
        "The check batch rejected this row before mail. The file said the mail-to name was missing. "
        "Fix the recipient, then include the row in a new file. "
        "Ops label: fix_recipient_data."
    ),
    "duplicate_trace": (
        "Two disbursements share one trace number. One economic event, two records. "
        "Do not retry either row. Confirm which leg the processor actually settled. "
        "Ops label: do_not_retry."
    ),
    "idempotency_already_settled": (
        "This idempotency key is already on a settled disbursement. "
        "The failed row is a second attempt at money that left. Planning a retry would double-pay. "
        "Ops label: do_not_retry."
    ),
    "return_in_flight": (
        "A return webhook is already in the log and the ledger row still says failed. "
        "The return is in flight. Retrying creates a second disbursement. "
        "Ops label: wait_for_return_window."
    ),
    "amount_mismatch": (
        "The processor acknowledgement amount and the ledger amount are different. "
        "Do not retry at the ledger amount until someone explains the difference. "
        "Ops label: do_not_retry."
    ),
    "retryable_failure": (
        "Ledger and log agree: failed, amount unchanged, no return, idempotency key not already settled. "
        "Eligible for a reprocess plan. The plan is not itself a payment. "
        "Ops label: retry."
    ),
    "pending": (
        "Still pending. reprocess.py applies the 24 hour window before it will plan this row. "
        "Ops label depends on that window."
    ),
    "settled_ok": (
        "Ledger status is settled and this row has no planted conflict of its own. "
        "Ops label: do_not_retry."
    ),
    "submitted_ok": (
        "Submitted and not yet terminal. Leave it in flight unless a trace or idempotency conflict says otherwise."
    ),
}
