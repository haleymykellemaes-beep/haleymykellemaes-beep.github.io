"""Build one synthetic week of dental payments with known discrepancies.

Patient identifiers are fake. Nothing here came from a practice management system.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from common import AS_OF, INBOUND
from load import (
    ATTEMPT_FIELDS,
    CLAIM_FIELDS,
    PAYMENT_FIELDS,
    REFUND_FIELDS,
    TAG_FIELDS,
    load,
    write_csv,
)

AS_OF_DATE = date.fromisoformat(AS_OF)
PACKAGES = [
    # billed, allowed, patient responsibility. Insurance = allowed - patient.
    (18600, 14000, 2800),
    (22000, 16500, 0),
    (14500, 14500, 14500),  # self-pay hygiene
    (41000, 30800, 6160),
    (52000, 39000, 11700),
    (27500, 20600, 4120),
    (89000, 62300, 12460),
    (34000, 25500, 5100),
    (125000, 87500, 17500),
    (16800, 12600, 2520),
]
PAYERS = [
    "Delta Dental of Colorado",
    "MetLife",
    "Cigna",
    "Aetna",
    "Guardian",
    "Medicaid",
]
PATIENT_METHODS = [
    ("patient_card", "card_webhook", 55),
    ("patient_ach", "ach", 15),
    ("check", "manual", 12),
    ("carecredit", "manual", 10),
    ("hsa", "card_webhook", 8),
]


def _method(rng: random.Random) -> tuple[str, str]:
    roll = rng.randrange(100)
    cursor = 0
    for method, source, weight in PATIENT_METHODS:
        cursor += weight
        if roll < cursor:
            return method, source
    return "patient_card", "card_webhook"


def _blank_tables() -> dict[str, list[dict]]:
    return {"claims": [], "attempts": [], "payments": [], "refunds": [], "tags": []}


def add_claim(tables: dict, **kwargs) -> None:
    kwargs.setdefault("denial_code", None)
    tables["claims"].append(kwargs)


def add_attempt(tables: dict, **kwargs) -> None:
    kwargs.setdefault("processor_code", None)
    kwargs.setdefault("processor_ref", None)
    tables["attempts"].append(kwargs)


def add_payment(tables: dict, **kwargs) -> None:
    kwargs.setdefault("attempt_id", None)
    kwargs.setdefault("claim_id", None)
    kwargs.setdefault("idempotency_key", None)
    tables["payments"].append(kwargs)


def add_refund(tables: dict, **kwargs) -> None:
    kwargs.setdefault("reason", None)
    tables["refunds"].append(kwargs)


def tag(tables: dict, entity_type: str, entity_id: str, expected_reason: str) -> None:
    tables["tags"].append(
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "expected_reason": expected_reason,
        }
    )


def build_clean(tables: dict, n: int = 140) -> None:
    """Fully reconciled claims. These should produce no exception rows."""
    rng = random.Random(20261115)
    pay_n = 1000
    att_n = 1000
    for i in range(1, n + 1):
        billed, allowed, patient = PACKAGES[(i - 1) % len(PACKAGES)]
        insurance = allowed - patient
        claim_id = f"CLM-{1000 + i}"
        patient_id = f"P-{1000 + i}"
        payer = "Self-pay" if insurance == 0 else PAYERS[(i - 1) % len(PAYERS)]
        service = AS_OF_DATE - timedelta(days=rng.randint(10, 40))
        add_claim(
            tables,
            claim_id=claim_id,
            patient_id=patient_id,
            payer=payer,
            service_date=service.isoformat(),
            billed_cents=billed,
            allowed_cents=allowed,
            patient_resp_cents=patient,
            insurance_resp_cents=insurance,
            claim_status="paid",
        )
        if insurance:
            att_n += 1
            pay_n += 1
            key = f"ERA-{claim_id}"
            attempt_id = f"ATT-{att_n}"
            add_attempt(
                tables,
                attempt_id=attempt_id,
                claim_id=claim_id,
                patient_id=patient_id,
                method="insurance_era",
                amount_cents=insurance,
                idempotency_key=key,
                requested_at=(service + timedelta(days=14)).isoformat(),
                attempt_status="settled",
                processor_code="era_paid",
                processor_ref=key,
            )
            add_payment(
                tables,
                payment_id=f"PAY-{pay_n}",
                attempt_id=attempt_id,
                claim_id=claim_id,
                patient_id=patient_id,
                method="insurance_era",
                amount_cents=insurance,
                posted_at=(service + timedelta(days=16)).isoformat(),
                idempotency_key=key,
                source="era",
            )
        if patient:
            att_n += 1
            pay_n += 1
            method, source = _method(rng)
            key = f"AUTH-{claim_id}"
            attempt_id = f"ATT-{att_n}"
            posted = service + timedelta(days=1)
            add_attempt(
                tables,
                attempt_id=attempt_id,
                claim_id=claim_id,
                patient_id=patient_id,
                method=method,
                amount_cents=patient,
                idempotency_key=key,
                requested_at=posted.isoformat(),
                attempt_status="settled",
                processor_code="approved",
                processor_ref=f"REF-{claim_id}",
            )
            add_payment(
                tables,
                payment_id=f"PAY-{pay_n}",
                attempt_id=attempt_id,
                claim_id=claim_id,
                patient_id=patient_id,
                method=method,
                amount_cents=patient,
                posted_at=posted.isoformat(),
                idempotency_key=key,
                source=source,
            )


def build_scenarios(tables: dict) -> None:
    # 1. Same ERA trace posted twice.
    add_claim(
        tables,
        claim_id="CLM-2001",
        patient_id="P-2001",
        payer="Delta Dental of Colorado",
        service_date="2026-10-20",
        billed_cents=24000,
        allowed_cents=18000,
        patient_resp_cents=0,
        insurance_resp_cents=18000,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2001",
        claim_id="CLM-2001",
        patient_id="P-2001",
        method="insurance_era",
        amount_cents=18000,
        idempotency_key="ERA-TRACE-2001",
        requested_at="2026-11-03",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2001",
    )
    add_payment(
        tables,
        payment_id="PAY-2001",
        attempt_id="ATT-2001",
        claim_id="CLM-2001",
        patient_id="P-2001",
        method="insurance_era",
        amount_cents=18000,
        posted_at="2026-11-04",
        idempotency_key="ERA-TRACE-2001",
        source="era",
    )
    add_payment(
        tables,
        payment_id="PAY-2001B",
        attempt_id="ATT-2001",
        claim_id="CLM-2001",
        patient_id="P-2001",
        method="insurance_era",
        amount_cents=18000,
        posted_at="2026-11-05",
        idempotency_key="ERA-TRACE-2001",
        source="era",
    )
    tag(tables, "payment", "PAY-2001B", "duplicate_post")

    # 2. Card webhook posted twice.
    add_claim(
        tables,
        claim_id="CLM-2002",
        patient_id="P-2002",
        payer="Self-pay",
        service_date="2026-10-28",
        billed_cents=4500,
        allowed_cents=4500,
        patient_resp_cents=4500,
        insurance_resp_cents=0,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2002",
        claim_id="CLM-2002",
        patient_id="P-2002",
        method="patient_card",
        amount_cents=4500,
        idempotency_key="CARD-AUTH-2002",
        requested_at="2026-10-28",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2002",
    )
    for payment_id, posted_at in (("PAY-2002", "2026-10-28"), ("PAY-2002B", "2026-10-29")):
        add_payment(
            tables,
            payment_id=payment_id,
            attempt_id="ATT-2002",
            claim_id="CLM-2002",
            patient_id="P-2002",
            method="patient_card",
            amount_cents=4500,
            posted_at=posted_at,
            idempotency_key="CARD-AUTH-2002",
            source="card_webhook",
        )
    tag(tables, "payment", "PAY-2002B", "duplicate_post")

    # 3. Patient paid the full fee instead of the patient portion.
    add_claim(
        tables,
        claim_id="CLM-2003",
        patient_id="P-2003",
        payer="Cigna",
        service_date="2026-10-18",
        billed_cents=28000,
        allowed_cents=20000,
        patient_resp_cents=6000,
        insurance_resp_cents=14000,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2003E",
        claim_id="CLM-2003",
        patient_id="P-2003",
        method="insurance_era",
        amount_cents=14000,
        idempotency_key="ERA-TRACE-2003",
        requested_at="2026-11-01",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2003",
    )
    add_payment(
        tables,
        payment_id="PAY-2003E",
        attempt_id="ATT-2003E",
        claim_id="CLM-2003",
        patient_id="P-2003",
        method="insurance_era",
        amount_cents=14000,
        posted_at="2026-11-02",
        idempotency_key="ERA-TRACE-2003",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2003P",
        claim_id="CLM-2003",
        patient_id="P-2003",
        method="patient_card",
        amount_cents=12000,
        idempotency_key="CARD-AUTH-2003",
        requested_at="2026-10-18",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2003",
    )
    add_payment(
        tables,
        payment_id="PAY-2003P",
        attempt_id="ATT-2003P",
        claim_id="CLM-2003",
        patient_id="P-2003",
        method="patient_card",
        amount_cents=12000,
        posted_at="2026-10-18",
        idempotency_key="CARD-AUTH-2003",
        source="card_webhook",
    )
    tag(tables, "claim", "CLM-2003", "overpayment")

    # 4. Silent insurance short pay. Patient portion is already collected.
    add_claim(
        tables,
        claim_id="CLM-2004",
        patient_id="P-2004",
        payer="MetLife",
        service_date="2026-10-12",
        billed_cents=52000,
        allowed_cents=40000,
        patient_resp_cents=10000,
        insurance_resp_cents=30000,
        claim_status="partial",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2004E",
        claim_id="CLM-2004",
        patient_id="P-2004",
        method="insurance_era",
        amount_cents=21000,
        idempotency_key="ERA-TRACE-2004",
        requested_at="2026-10-30",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2004",
    )
    add_payment(
        tables,
        payment_id="PAY-2004E",
        attempt_id="ATT-2004E",
        claim_id="CLM-2004",
        patient_id="P-2004",
        method="insurance_era",
        amount_cents=21000,
        posted_at="2026-11-01",
        idempotency_key="ERA-TRACE-2004",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2004P",
        claim_id="CLM-2004",
        patient_id="P-2004",
        method="hsa",
        amount_cents=10000,
        idempotency_key="HSA-2004",
        requested_at="2026-10-12",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2004",
    )
    add_payment(
        tables,
        payment_id="PAY-2004P",
        attempt_id="ATT-2004P",
        claim_id="CLM-2004",
        patient_id="P-2004",
        method="hsa",
        amount_cents=10000,
        posted_at="2026-10-12",
        idempotency_key="HSA-2004",
        source="card_webhook",
    )
    tag(tables, "claim", "CLM-2004", "insurance_short_pay")

    # 5. Cash posted to the claim, but under the wrong patient.
    add_claim(
        tables,
        claim_id="CLM-2005",
        patient_id="P-2005",
        payer="Self-pay",
        service_date="2026-10-22",
        billed_cents=15500,
        allowed_cents=15500,
        patient_resp_cents=15500,
        insurance_resp_cents=0,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2005",
        claim_id="CLM-2005",
        patient_id="P-2005",
        method="check",
        amount_cents=15500,
        idempotency_key="CHECK-88421",
        requested_at="2026-10-24",
        attempt_status="settled",
        processor_code="check_posted",
        processor_ref="CHECK-88421",
    )
    add_payment(
        tables,
        payment_id="PAY-2005",
        attempt_id="ATT-2005",
        claim_id="CLM-2005",
        patient_id="P-2099",
        method="check",
        amount_cents=15500,
        posted_at="2026-10-24",
        idempotency_key="CHECK-88421",
        source="manual",
    )
    tag(tables, "payment", "PAY-2005", "misapplied_payment")

    # 6. Ops marked the card failed. The webhook had already settled it.
    add_claim(
        tables,
        claim_id="CLM-2006",
        patient_id="P-2006",
        payer="Aetna",
        service_date="2026-10-15",
        billed_cents=24600,
        allowed_cents=18400,
        patient_resp_cents=8200,
        insurance_resp_cents=10200,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2006E",
        claim_id="CLM-2006",
        patient_id="P-2006",
        method="insurance_era",
        amount_cents=10200,
        idempotency_key="ERA-TRACE-2006",
        requested_at="2026-11-02",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2006",
    )
    add_payment(
        tables,
        payment_id="PAY-2006E",
        attempt_id="ATT-2006E",
        claim_id="CLM-2006",
        patient_id="P-2006",
        method="insurance_era",
        amount_cents=10200,
        posted_at="2026-11-03",
        idempotency_key="ERA-TRACE-2006",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2006",
        claim_id="CLM-2006",
        patient_id="P-2006",
        method="patient_card",
        amount_cents=8200,
        idempotency_key="CARD-AUTH-2006",
        requested_at="2026-10-15",
        attempt_status="failed",
        processor_code="timeout",
        processor_ref="SETL-2006",
    )
    add_payment(
        tables,
        payment_id="PAY-2006",
        attempt_id="ATT-2006",
        claim_id="CLM-2006",
        patient_id="P-2006",
        method="patient_card",
        amount_cents=8200,
        posted_at="2026-10-15",
        idempotency_key="CARD-AUTH-2006",
        source="card_webhook",
    )
    tag(tables, "attempt", "ATT-2006", "status_failed_but_settled")

    # 7. Decline was posted manually as if it had been approved.
    add_claim(
        tables,
        claim_id="CLM-2007",
        patient_id="P-2007",
        payer="Self-pay",
        service_date="2026-11-02",
        billed_cents=9600,
        allowed_cents=9600,
        patient_resp_cents=9600,
        insurance_resp_cents=0,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2007",
        claim_id="CLM-2007",
        patient_id="P-2007",
        method="patient_card",
        amount_cents=9600,
        idempotency_key="CARD-AUTH-2007",
        requested_at="2026-11-02",
        attempt_status="declined",
        processor_code="insufficient_funds",
        processor_ref=None,
    )
    add_payment(
        tables,
        payment_id="PAY-2007",
        attempt_id="ATT-2007",
        claim_id="CLM-2007",
        patient_id="P-2007",
        method="patient_card",
        amount_cents=9600,
        posted_at="2026-11-02",
        idempotency_key="CARD-AUTH-2007",
        source="manual",
    )
    tag(tables, "attempt", "ATT-2007", "declined_but_posted")

    # 8. Check in the deposit with no claim.
    add_payment(
        tables,
        payment_id="PAY-2008",
        patient_id="P-2008",
        method="check",
        amount_cents=15000,
        posted_at="2026-11-06",
        idempotency_key="CHECK-19004",
        source="manual",
    )
    tag(tables, "payment", "PAY-2008", "orphan_payment")

    # 9. Refund larger than the payment it reverses.
    add_claim(
        tables,
        claim_id="CLM-2009",
        patient_id="P-2009",
        payer="Self-pay",
        service_date="2026-10-08",
        billed_cents=5000,
        allowed_cents=5000,
        patient_resp_cents=5000,
        insurance_resp_cents=0,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2009",
        claim_id="CLM-2009",
        patient_id="P-2009",
        method="patient_card",
        amount_cents=5000,
        idempotency_key="CARD-AUTH-2009",
        requested_at="2026-10-08",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2009",
    )
    add_payment(
        tables,
        payment_id="PAY-2009",
        attempt_id="ATT-2009",
        claim_id="CLM-2009",
        patient_id="P-2009",
        method="patient_card",
        amount_cents=5000,
        posted_at="2026-10-08",
        idempotency_key="CARD-AUTH-2009",
        source="card_webhook",
    )
    add_refund(
        tables,
        refund_id="REF-2009",
        payment_id="PAY-2009",
        amount_cents=7500,
        refund_status="issued",
        reason="front desk refunded the billed fee instead of the amount collected",
    )
    tag(tables, "refund", "REF-2009", "refund_exceeds_payment")

    # 10. Denial and a payment on the same claim.
    add_claim(
        tables,
        claim_id="CLM-2010",
        patient_id="P-2010",
        payer="Guardian",
        service_date="2026-10-05",
        billed_cents=14000,
        allowed_cents=10000,
        patient_resp_cents=0,
        insurance_resp_cents=10000,
        claim_status="denied",
        denial_code="CO-16",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2010",
        claim_id="CLM-2010",
        patient_id="P-2010",
        method="insurance_era",
        amount_cents=10000,
        idempotency_key="ERA-TRACE-2010",
        requested_at="2026-10-28",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2010",
    )
    add_payment(
        tables,
        payment_id="PAY-2010",
        attempt_id="ATT-2010",
        claim_id="CLM-2010",
        patient_id="P-2010",
        method="insurance_era",
        amount_cents=10000,
        posted_at="2026-10-29",
        idempotency_key="ERA-TRACE-2010",
        source="era",
    )
    tag(tables, "claim", "CLM-2010", "denied_with_payment")

    # 11. Card still pending, amount matches the open balance. Safe to reprocess.
    add_claim(
        tables,
        claim_id="CLM-2011",
        patient_id="P-2011",
        payer="Delta Dental of Colorado",
        service_date="2026-10-19",
        billed_cents=40000,
        allowed_cents=30000,
        patient_resp_cents=6500,
        insurance_resp_cents=23500,
        claim_status="partial",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2011E",
        claim_id="CLM-2011",
        patient_id="P-2011",
        method="insurance_era",
        amount_cents=23500,
        idempotency_key="ERA-TRACE-2011",
        requested_at="2026-11-04",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2011",
    )
    add_payment(
        tables,
        payment_id="PAY-2011E",
        attempt_id="ATT-2011E",
        claim_id="CLM-2011",
        patient_id="P-2011",
        method="insurance_era",
        amount_cents=23500,
        posted_at="2026-11-05",
        idempotency_key="ERA-TRACE-2011",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2011",
        claim_id="CLM-2011",
        patient_id="P-2011",
        method="patient_card",
        amount_cents=6500,
        idempotency_key="CARD-AUTH-2011",
        requested_at="2026-11-01",
        attempt_status="pending",
        processor_code="no_webhook",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2011", "safe_to_reprocess")

    # 12. ACH past the review window. Safe to reprocess.
    add_claim(
        tables,
        claim_id="CLM-2012",
        patient_id="P-2012",
        payer="Self-pay",
        service_date="2026-11-06",
        billed_cents=12800,
        allowed_cents=12800,
        patient_resp_cents=12800,
        insurance_resp_cents=0,
        claim_status="open",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2012",
        claim_id="CLM-2012",
        patient_id="P-2012",
        method="patient_ach",
        amount_cents=12800,
        idempotency_key="ACH-2012",
        requested_at="2026-11-08",
        attempt_status="failed",
        processor_code="returned_r01",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2012", "safe_to_reprocess")

    # 13. A failed retry uses a key that already settled. Block it.
    add_claim(
        tables,
        claim_id="CLM-2013",
        patient_id="P-2013",
        payer="Cigna",
        service_date="2026-10-21",
        billed_cents=26000,
        allowed_cents=20000,
        patient_resp_cents=8000,
        insurance_resp_cents=12000,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2013E",
        claim_id="CLM-2013",
        patient_id="P-2013",
        method="insurance_era",
        amount_cents=12000,
        idempotency_key="ERA-TRACE-2013",
        requested_at="2026-11-06",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2013",
    )
    add_payment(
        tables,
        payment_id="PAY-2013E",
        attempt_id="ATT-2013E",
        claim_id="CLM-2013",
        patient_id="P-2013",
        method="insurance_era",
        amount_cents=12000,
        posted_at="2026-11-07",
        idempotency_key="ERA-TRACE-2013",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2013S",
        claim_id="CLM-2013",
        patient_id="P-2013",
        method="patient_card",
        amount_cents=8000,
        idempotency_key="CARD-AUTH-2013",
        requested_at="2026-10-21",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2013",
    )
    add_payment(
        tables,
        payment_id="PAY-2013",
        attempt_id="ATT-2013S",
        claim_id="CLM-2013",
        patient_id="P-2013",
        method="patient_card",
        amount_cents=8000,
        posted_at="2026-10-21",
        idempotency_key="CARD-AUTH-2013",
        source="card_webhook",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2013B",
        claim_id="CLM-2013",
        patient_id="P-2013",
        method="patient_card",
        amount_cents=8000,
        idempotency_key="CARD-AUTH-2013",
        requested_at="2026-11-02",
        attempt_status="failed",
        processor_code="timeout",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2013B", "blocked_duplicate_key")

    # 14. Failed attempt is for the original patient portion, but part of it was already paid.
    add_claim(
        tables,
        claim_id="CLM-2014",
        patient_id="P-2014",
        payer="Aetna",
        service_date="2026-10-16",
        billed_cents=36000,
        allowed_cents=25000,
        patient_resp_cents=10000,
        insurance_resp_cents=15000,
        claim_status="partial",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2014E",
        claim_id="CLM-2014",
        patient_id="P-2014",
        method="insurance_era",
        amount_cents=15000,
        idempotency_key="ERA-TRACE-2014",
        requested_at="2026-11-01",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2014",
    )
    add_payment(
        tables,
        payment_id="PAY-2014E",
        attempt_id="ATT-2014E",
        claim_id="CLM-2014",
        patient_id="P-2014",
        method="insurance_era",
        amount_cents=15000,
        posted_at="2026-11-02",
        idempotency_key="ERA-TRACE-2014",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2014P",
        claim_id="CLM-2014",
        patient_id="P-2014",
        method="patient_card",
        amount_cents=6000,
        idempotency_key="CARD-AUTH-2014A",
        requested_at="2026-10-16",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2014A",
    )
    add_payment(
        tables,
        payment_id="PAY-2014P",
        attempt_id="ATT-2014P",
        claim_id="CLM-2014",
        patient_id="P-2014",
        method="patient_card",
        amount_cents=6000,
        posted_at="2026-10-16",
        idempotency_key="CARD-AUTH-2014A",
        source="card_webhook",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2014F",
        claim_id="CLM-2014",
        patient_id="P-2014",
        method="patient_card",
        amount_cents=10000,
        idempotency_key="CARD-AUTH-2014B",
        requested_at="2026-11-03",
        attempt_status="failed",
        processor_code="timeout",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2014F", "amount_mismatch")

    # 15. Refund requested, and someone queued another collection.
    add_claim(
        tables,
        claim_id="CLM-2015",
        patient_id="P-2015",
        payer="Self-pay",
        service_date="2026-10-25",
        billed_cents=5000,
        allowed_cents=5000,
        patient_resp_cents=5000,
        insurance_resp_cents=0,
        claim_status="paid",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2015S",
        claim_id="CLM-2015",
        patient_id="P-2015",
        method="patient_card",
        amount_cents=5000,
        idempotency_key="CARD-AUTH-2015",
        requested_at="2026-10-25",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2015",
    )
    add_payment(
        tables,
        payment_id="PAY-2015",
        attempt_id="ATT-2015S",
        claim_id="CLM-2015",
        patient_id="P-2015",
        method="patient_card",
        amount_cents=5000,
        posted_at="2026-10-25",
        idempotency_key="CARD-AUTH-2015",
        source="card_webhook",
    )
    add_refund(
        tables,
        refund_id="REF-2015",
        payment_id="PAY-2015",
        amount_cents=5000,
        refund_status="requested",
        reason="patient reported a duplicate charge",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2015F",
        claim_id="CLM-2015",
        patient_id="P-2015",
        method="patient_card",
        amount_cents=5000,
        idempotency_key="CARD-AUTH-2015-R",
        requested_at="2026-11-04",
        attempt_status="failed",
        processor_code="timeout",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2015F", "blocked_refund_in_flight")

    # 16. Ordinary open balance. No attempt to retry.
    add_claim(
        tables,
        claim_id="CLM-2016",
        patient_id="P-2016",
        payer="Medicaid",
        service_date="2026-10-11",
        billed_cents=22000,
        allowed_cents=16000,
        patient_resp_cents=7500,
        insurance_resp_cents=8500,
        claim_status="partial",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2016E",
        claim_id="CLM-2016",
        patient_id="P-2016",
        method="insurance_era",
        amount_cents=8500,
        idempotency_key="ERA-TRACE-2016",
        requested_at="2026-10-27",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2016",
    )
    add_payment(
        tables,
        payment_id="PAY-2016E",
        attempt_id="ATT-2016E",
        claim_id="CLM-2016",
        patient_id="P-2016",
        method="insurance_era",
        amount_cents=8500,
        posted_at="2026-10-28",
        idempotency_key="ERA-TRACE-2016",
        source="era",
    )
    tag(tables, "claim", "CLM-2016", "open_patient_balance")

    # 17. Pending card inside the review window. Must stay off the queue.
    add_claim(
        tables,
        claim_id="CLM-2017",
        patient_id="P-2017",
        payer="Guardian",
        service_date="2026-11-10",
        billed_cents=18000,
        allowed_cents=14000,
        patient_resp_cents=4000,
        insurance_resp_cents=10000,
        claim_status="partial",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2017E",
        claim_id="CLM-2017",
        patient_id="P-2017",
        method="insurance_era",
        amount_cents=10000,
        idempotency_key="ERA-TRACE-2017",
        requested_at="2026-11-13",
        attempt_status="settled",
        processor_code="era_paid",
        processor_ref="ERA-TRACE-2017",
    )
    add_payment(
        tables,
        payment_id="PAY-2017E",
        attempt_id="ATT-2017E",
        claim_id="CLM-2017",
        patient_id="P-2017",
        method="insurance_era",
        amount_cents=10000,
        posted_at="2026-11-14",
        idempotency_key="ERA-TRACE-2017",
        source="era",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2017",
        claim_id="CLM-2017",
        patient_id="P-2017",
        method="patient_card",
        amount_cents=4000,
        idempotency_key="CARD-AUTH-2017",
        requested_at="2026-11-14",
        attempt_status="pending",
        processor_code="awaiting_webhook",
        processor_ref=None,
    )
    tag(tables, "attempt", "ATT-2017", "NONE")
    tag(tables, "claim", "CLM-2017", "NONE")

    # 18. Clean denial. No cash, so it is not a payment discrepancy.
    add_claim(
        tables,
        claim_id="CLM-2018",
        patient_id="P-2018",
        payer="MetLife",
        service_date="2026-09-01",
        billed_cents=30000,
        allowed_cents=22000,
        patient_resp_cents=0,
        insurance_resp_cents=22000,
        claim_status="denied",
        denial_code="CO-29",
    )
    tag(tables, "claim", "CLM-2018", "NONE")

    # 19. Expected amounts do not tie out. Do not chase cash until they do.
    add_claim(
        tables,
        claim_id="CLM-2019",
        patient_id="P-2019",
        payer="Delta Dental of Colorado",
        service_date="2026-10-09",
        billed_cents=15000,
        allowed_cents=10000,
        patient_resp_cents=4000,
        insurance_resp_cents=5000,
        claim_status="open",
    )
    tag(tables, "claim", "CLM-2019", "source_does_not_tie")

    # 20. Full refund on a voided claim. Matched, so it stays off the queue.
    add_claim(
        tables,
        claim_id="CLM-2020",
        patient_id="P-2020",
        payer="Self-pay",
        service_date="2026-10-03",
        billed_cents=8000,
        allowed_cents=8000,
        patient_resp_cents=8000,
        insurance_resp_cents=0,
        claim_status="void",
    )
    add_attempt(
        tables,
        attempt_id="ATT-2020",
        claim_id="CLM-2020",
        patient_id="P-2020",
        method="patient_card",
        amount_cents=8000,
        idempotency_key="CARD-AUTH-2020",
        requested_at="2026-10-03",
        attempt_status="settled",
        processor_code="approved",
        processor_ref="SETL-2020",
    )
    add_payment(
        tables,
        payment_id="PAY-2020",
        attempt_id="ATT-2020",
        claim_id="CLM-2020",
        patient_id="P-2020",
        method="patient_card",
        amount_cents=8000,
        posted_at="2026-10-03",
        idempotency_key="CARD-AUTH-2020",
        source="card_webhook",
    )
    add_refund(
        tables,
        refund_id="REF-2020",
        payment_id="PAY-2020",
        amount_cents=8000,
        refund_status="issued",
        reason="service voided before it was completed",
    )
    tag(tables, "claim", "CLM-2020", "NONE")
    tag(tables, "refund", "REF-2020", "NONE")


def main() -> None:
    tables = _blank_tables()
    build_clean(tables)
    build_scenarios(tables)
    write_csv(INBOUND / "claims.csv", CLAIM_FIELDS, tables["claims"])
    write_csv(INBOUND / "attempts.csv", ATTEMPT_FIELDS, tables["attempts"])
    write_csv(INBOUND / "payments.csv", PAYMENT_FIELDS, tables["payments"])
    write_csv(INBOUND / "refunds.csv", REFUND_FIELDS, tables["refunds"])
    write_csv(INBOUND / "scenario_tags.csv", TAG_FIELDS, tables["tags"])
    print(f"Wrote synthetic CSVs to {INBOUND}")
    load(INBOUND, DB, AS_OF, STUCK_DAYS)


if __name__ == "__main__":
    from common import DB, STUCK_DAYS

    main()
