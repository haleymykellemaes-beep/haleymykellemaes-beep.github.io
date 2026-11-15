# Payment exception review

A one-week dental payment ledger, a SQL exception queue, and a Python reprocess plan that will not send a payment twice.

This is synthetic. Patient ids are fake. It is shaped like the reconciliation already done on insurance ERAs, patient cards, ACH, checks, CareCredit, HSA, and refunds: find the break, name the cause, and separate a safe retry from a second charge.

## Run

From the portfolio folder:

```bash
python3 payment-exceptions/python/seed.py
python3 payment-exceptions/python/investigate.py
python3 payment-exceptions/python/reprocess_plan.py
```

`seed.py` writes the CSVs and builds `data/billing.db`. `investigate.py` prints the queue and writes `data/out/exception_queue.csv`. The reprocess script is a dry run until you pass `--execute`.

`--execute` records the safe attempts in `reprocess_queue` with status `planned`. It does not insert a payment. The script counts posted payments before and after and stops if that count changes.

Python 3 standard library only. No packages to install. The queries are SQLite. The same joins work in PostgreSQL if `date()` is swapped for an interval.

To read the queue in a SQL client:

```bash
sqlite3 payment-exceptions/data/billing.db < payment-exceptions/sql/report.sql
```

## What the synthetic week shows

As of 15 Nov 2026 the fixture has 159 claims, 279 attempts, and 276 posted payments. 140 of those claims are fully reconciled. The check fails if any of them land on the queue or still have a balance.

Seventeen planted issues remain:

| Reason | What it is | Amount |
| --- | --- | ---: |
| duplicate_post | Same ERA trace or card auth posted twice | $225.00 |
| safe_to_reprocess | Card or ACH still open, key never posted, amount equals the balance | $193.00 |
| misapplied_payment | Cash is on the claim under the wrong patient | $155.00 |
| orphan_payment | Deposit with no claim | $150.00 |
| denied_with_payment | Denial code and a posted payment on the same claim | $100.00 |
| declined_but_posted | Card declined, then posted by hand | $96.00 |
| insurance_short_pay | ERA below the contracted insurance amount, no denial | $90.00 |
| status_failed_but_settled | Attempt says timeout, webhook already settled | $82.00 |
| blocked_duplicate_key | Retry uses a key that is already posted | $80.00 |
| open_patient_balance | Balance owed, nothing in flight | $75.00 |
| amount_mismatch | Retry is $100.00 and the open balance is $40.00 | $60.00 |
| overpayment | Patient paid the billed fee instead of the patient portion | $60.00 |
| blocked_refund_in_flight | Another charge was queued while a refund is still requested | $50.00 |
| refund_exceeds_payment | Refund is larger than the original payment | $25.00 |
| source_does_not_tie | Allowed amount is not patient plus insurance | $10.00 |

A blind retry of the three unsuccessful attempts whose key is already posted would send **$258.00** again. The plan allows **$193.00** across two attempts. It blocks four attempts (**$308.00**): those three, plus a $50.00 charge queued while a refund is still open. The $100.00 retry against a $40.00 balance stays in review.

Controls, in order:

1. Patient card and ACH only. An insurance short pay is an appeal or a rebill, not a card retry.
2. The attempt has been pending or failed for more than 3 days. A charge from yesterday stays off the list.
3. No posted payment already uses that idempotency key (ERA trace, check number, or auth code).
4. No refund is requested or issued on the claim.
5. The attempt amount equals the open balance. Anything else is a review, not a send.
6. The Python script checks the key again before it writes the plan. The SQL filter is not the only lock.

`CLM-2017` is a pending card inside the 3-day window, `CLM-2018` is a denial with no cash, and `CLM-2020` is a void with a matching refund. None of those are exceptions. A clean refund is not an error. A refund that does not match the payment is.

## Use it on a real export

Strip names first. Chart numbers and claim numbers are enough. Put the files in `payment-exceptions/data/inbound/local/` (that folder is gitignored) and load them:

```bash
python3 payment-exceptions/python/load.py \
  --inbound payment-exceptions/data/inbound/local \
  --as-of 2026-11-15
python3 payment-exceptions/python/investigate.py
```

Required files are `claims.csv` and `payments.csv`. `attempts.csv` and `refunds.csv` are optional. Without attempts, the cash checks still run: duplicate trace, short pay, overpayment, misapplied patient, orphan deposit, refund, denial with cash, and a fee schedule that does not tie. The reprocess list stays empty until processor statuses are in the file.

| Column | Where it usually comes from |
| --- | --- |
| claim_id | Claim number |
| patient_id | Chart or responsible-party id, not a name |
| payer | Carrier, or Self-pay |
| billed_cents, allowed_cents | Fee and contracted amount, in cents |
| patient_resp_cents, insurance_resp_cents | Patient portion and insurance portion |
| claim_status | open, partial, paid, denied, void |
| denial_code | CARC such as CO-16 or CO-29, blank if none |
| idempotency_key | ERA/EFT trace, check number, or card/ACH auth |
| attempt_status | pending, failed, declined, settled |
| source | era, card_webhook, ach, manual |

Amounts are integer cents so $10.00 is `1000`, not `10` and not `9.999`.

Do not point this at a live database, and do not commit a real export. `data/*.db`, `data/out/`, and `data/inbound/local/` are gitignored for that reason.

## How to talk about it

At the practice I reconcile insurance payments, patient cards, and refunds across a lot of payment types. The misses are rarely "the claim is open." They are a trace posted twice, a card marked failed after the processor already settled it, cash sitting on the wrong patient, or a short pay with no denial code.

The dangerous step is the retry. If I resend every failed attempt, I also resend the ones that already settled. This ledger treats the auth code or ERA trace as an idempotency key. The queue will plan a retry only when that key has never been posted, no refund is in flight, and the amount matches the open balance. Everything else is a block or a manual review. Running the plan records the decision. It does not create the payment.

That is the same problem as a failed disbursement: find out whether the money moved, fix the status if it did, and reprocess only when a second send cannot duplicate the first one.
