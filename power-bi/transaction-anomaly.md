# Power BI build guide — Transaction Anomaly Detection

The repository contains summary extracts so Power BI never has to import all
6.36 million PaySim rows.

## Import

| File | Use |
| --- | --- |
| `data/paysim-overview.csv` | Volume, fraud rate, train/test split, baseline |
| `data/paysim-type-profile.csv` | Fraud and amount profile by transaction type |
| `data/paysim-rule-scorecard.csv` | Precision, recall, and workload by rule |
| `data/paysim-threshold-curve.csv` | Rules vs. scored queue at each alert budget |
| `data/paysim-hour-profile.csv` | Hourly volume and fraud profile |
| `data/paysim-review-queue-sample.csv` | Sample reason-coded review queue |

No relationships are required; these are purpose-built aggregate tables.

## Page 1 — Overview

- Cards: `transactions`, `fraud`, `fraud_rate_pct`
- Baseline cards: `baseline_alerts`, `baseline_caught`,
  `baseline_recall_pct`
- Clustered bar: fraud count by `type`
- Line and column chart: hourly transactions and `fraud_per_1000`
- Persistent note: “PaySim is synthetic. Holdout = steps 481–720.”

## Page 2 — Rule scorecard

- Table: `rule`, `precision_pct`, `recall_pct`, `alerts_per_day`
- Scatter: X = `alerts_per_day`, Y = `recall_pct`, size =
  `fraud_caught`
- Filter out `leak_r1_drained` and `leak_r3_balance_mismatch` from the
  deployable-control visual.
- Put those two rows in a separate “Leakage audit” table with a warning icon.

## Page 3 — Threshold tradeoff

Use `alerts_per_day` from `paysim-threshold-curve.csv` as a single-select
slicer. Add these measures:

```DAX
Selected Alert Budget =
SELECTEDVALUE('Threshold'[alerts_per_day], 200)

Rules Recall =
VAR Budget = [Selected Alert Budget]
RETURN
    MAXX(
        FILTER('Threshold', 'Threshold'[alerts_per_day] = Budget),
        'Threshold'[rules_recall_pct]
    )

Score Recall =
VAR Budget = [Selected Alert Budget]
RETURN
    MAXX(
        FILTER('Threshold', 'Threshold'[alerts_per_day] = Budget),
        'Threshold'[score_recall_pct]
    )

Recall Added =
[Score Recall] - [Rules Recall]

Score Precision =
VAR Budget = [Selected Alert Budget]
RETURN
    MAXX(
        FILTER('Threshold', 'Threshold'[alerts_per_day] = Budget),
        'Threshold'[score_precision_pct]
    )
```

Recommended visuals:

- Cards: alert budget, score recall, score precision, recall added
- Two-line chart: rules recall vs. score recall by alert budget
- Two-line chart: rules precision vs. score precision by alert budget
- Reference line at 200 alerts/day

## Page 4 — Review queue

Show `queue_rank`, `step`, `day`, `hour`, `type`, `amount`, `nameOrig`,
`nameDest`, reason-code columns, and `risk_score`. Hide `isFraud` on the
working queue: investigators do not know the outcome when they receive an
alert. Keep the label only on an evaluation or quality-assurance page.

Use conditional formatting for:

- `r0_baseline`: dark red
- `r2_large`: amber
- `r5_off_hours`: blue
- `risk_score`: data bar

The committed queue is a 50-row sample for portfolio display. Re-run the SQL
to export the full top-2,000 holdout queue if deeper drill-through is needed.
