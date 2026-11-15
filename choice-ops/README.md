# Choice Digital ops drills

Synthetic payment-operations drills for a Technical Operations Manager interview. I can run these from the portfolio folder and talk through the output. They use made-up clients, recipient tokens, and trace numbers.

**Synthetic data only. I do not point these scripts at production, a real SFTP drop, or a live processor. There is no API key, no account number, and no call out to the network.**

The clock is frozen at `2026-11-15T17:00:00Z` so the pending window stays put between now and the interview.

## How I run them

From `/Users/haley/WGU/portfolio`:

```bash
python3 choice-ops/python/seed.py
python3 choice-ops/python/investigate_failure.py
python3 choice-ops/python/investigate_failure.py DSP-7001
python3 choice-ops/python/reprocess.py
python3 choice-ops/python/reprocess.py --execute
python3 choice-ops/python/reconcile_batch.py
python3 choice-ops/python/classify_webhook.py
```

`seed.py` rebuilds `choice-ops/data/choice_ops.db`, `events.jsonl`, and `batch_northwind_20261114.csv`. Each other script exits non-zero if a planted case is missing or mislabeled. `seed.py` leaves `reprocess_queue` empty.

Python 3 standard library and `sqlite3` only. No packages to install.

## What each one shows

**`investigate_failure.py`** — Hand them a payment id and I can put the API log next to the ledger row. The SQL lives in `sql/disbursements.sql` (the script runs the named queries; the timeline itself is read from the JSONL, because the log is the evidence). Eight planted causes:

| Cause | Rows | Dollars | What I would do |
| --- | ---: | ---: | --- |
| status_mismatch | 1 | $1,250.00 | Webhook says settled, row says failed. Escalate. Do not send again. |
| ach_r01 | 1 | $480.00 | Insufficient funds. Wait out the return. |
| ach_r03 | 1 | $915.50 | Account could not be located. Fix the recipient token. |
| batch_rejected | 1 | $220.00 | Check file rejected the row. Fix the mail-to name, then a new file. |
| duplicate_trace | 2 | $1,280.00 | `TR-DUP-55` is on a settled prepaid and a second submitted row. |
| idempotency_already_settled | 1 | $1,800.00 | Failed row `DSP-7007` reused the key that already settled on `DSP-7008`. |
| return_in_flight | 1 | $350.00 | Return webhook is in the log. The row still says failed. |
| amount_mismatch | 1 | $750.00 | Ledger is $750.00. The ack says $755.00. |
| **Involved** | **9** | **$7,045.50** | |

Useful single ids if they want me to narrate one: `DSP-7001`, `DSP-7003`, `DSP-7006`, `DSP-7009`.

**`reprocess.py`** — Dry-run is the default. It selects failed rows, and pending rows older than 24 hours, then refuses anything that would pay twice.

| | Count | Dollars |
| --- | ---: | ---: |
| Safe to plan | 3 | $637.50 |
| Blocked | 9 | $6,905.50 |

Safe rows are `DSP-7011` (timeout 96, $410.00), `DSP-7012` (processor unavailable 91, $128.50), and `DSP-7013` (pending since Nov 13, $99.00).

Blocked, so I can say the rule out loud:

| Reason | Count | Dollars |
| --- | ---: | ---: |
| webhook_already_settled | 1 | $1,250.00 |
| return_already_received | 2 | $830.00 |
| fix_recipient_data | 1 | $915.50 |
| fix_before_retry | 1 | $220.00 |
| duplicate_trace | 1 | $640.00 |
| idempotency_already_settled | 1 | $1,800.00 |
| amount_changed | 1 | $750.00 |
| pending_inside_window | 1 | $500.00 |

The duplicate-trace block is only the in-flight leg. The settled twin is not a retry candidate, which is why this dollar figure is $640 and the investigate total for that cause is $1,280.

`--execute` inserts those three safe ids into `reprocess_queue`. It does not insert a disbursement. Running it twice does not double the queue. I say that sentence in the interview: a plan row is not a payment.

**`reconcile_batch.py`** — Northwind's batch file against settled disbursements. This is the control.

| Break | Count | Dollars |
| --- | ---: | --- |
| Matched | 3 | $1,650.00 |
| Missing from batch | 1 | $200.00 settled, absent from the file (`TR-9101`) |
| In batch, not sent | 1 | $150.00 in the file, never settled (`TR-9102`) |
| Amount mismatch | 1 | Ledger $300.00, file $280.00 (`TR-9103`) |
| Duplicate trace | 1 | File lists `TR-9104` twice ($64.00 + $64.00). One settled row, $64.00. |

**`classify_webhook.py`** — Reads the JSONL and turns a processor code into a label: `retry`, `do_not_retry`, `fix_recipient_data`, `wait_for_return_window`, `escalate_to_engineering`. A `96` means retry only as a label. `reprocess.py` still has to agree that the amount, the trace, and the idempotency key are clean. Bad JSON escalates. Nothing is sent.

## Sixty seconds

At the practice I already chase the same four breaks, just on money coming in. A duplicate post is a duplicate trace: two records, one payment, and a blind retry pays the person twice. A payment that bounced because the account was wrong is an R03: I fix the recipient, I do not resend. A refund that is already in flight is a return the network has accepted while our row still says failed. Sending it again is a second disbursement. A silent short-pay is this batch reconcile: their file and our settled ledger disagree, and nobody pages you. I pull the timeline, I refuse anything that would double-pay, and I only write a plan row. I do not create a second live payment.

## What I leave alone

I do not put real member data in this folder. I do not reuse these idempotency keys against a real client. If a self-check fails, I run `seed.py` again before I trust the numbers.
