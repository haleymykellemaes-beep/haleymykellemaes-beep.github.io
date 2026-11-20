# Transaction anomaly detection

DuckDB case study using the 6,362,620-row PaySim synthetic mobile-money
dataset. The analytical question is operational: which detection logic catches
the most fraud under a fixed investigator capacity?

## Data provenance

- Portfolio dataset:
  [Synthetic Financial Datasets for Fraud Detection](https://www.kaggle.com/datasets/ealaxi/paysim1),
  published on Kaggle by ealaxi under CC BY-SA 4.0.
- Original research: E. A. Lopez-Rojas, A. Elmir, and S. Axelsson,
  “[PaySim: A financial mobile money simulator for fraud detection](https://www.msc-les.org/proceedings/emss/emss2016/emss2016_249.html),”
  28th European Modeling and Simulation Symposium, Larnaca, Cyprus, 2016.
- Simulator repository:
  [EdgarLopezPhD/PaySim](https://github.com/EdgarLopezPhD/PaySim).

PaySim uses aggregated patterns from private mobile-money logs to generate
synthetic transactions and inject fraudulent behavior. It contains no customer
records from the source service. The analyzed CSV has 6,362,620 rows, 11 source
columns, and hourly steps 1–743.

## Reproduce

1. Download
   [Synthetic Financial Datasets for Fraud Detection](https://www.kaggle.com/datasets/ealaxi/paysim1).
2. Save the CSV at
   `data/PS_20174392719_1491204439457_log.csv`.
3. From the repository root, run:

```bash
duckdb paysim.duckdb \
  -c ".read sql/transaction-anomaly/00_load.sql" \
  -c ".read sql/transaction-anomaly/01_profile.sql" \
  -c ".read sql/transaction-anomaly/02_rules.sql" \
  -c ".read sql/transaction-anomaly/03_score.sql" \
  -c ".read sql/transaction-anomaly/04_evaluate.sql"
```

The scripts keep `is_fraud` out of every feature and scoring expression.
Labels are used only to select weights on steps 1–480 and to evaluate the
untouched holdout at steps 481–720.

## Holdout result

At a capacity of 200 alerts per day:

| Method | Fraud caught | Precision | Recall |
| --- | ---: | ---: | ---: |
| Existing rule | 7 | 100.00% | 0.27% |
| Rules, FIFO within tied scores | 531 | 26.55% | 20.49% |
| Rules + amount z-score | 886 | 44.30% | 34.18% |

The statistical score adds **355 fraud cases** and **13.69 percentage points
of recall** without adding investigator workload.

## Controls and limitations

- PaySim is synthetic and has a major regime shift: 6.04 million transactions
  occur in days 1–20, while only 322,905 occur in days 21–30. The holdout fraud
  rate is 0.803%, versus 0.089% in training.
- The source explicitly warns against using old/new balance fields because
  fraudulent transactions are canceled by the simulator. Those fields are
  retained only in a clearly labeled leakage audit.
- Sender IDs almost never repeat (only 9,313 repeat transactions among 6.36
  million), so customer-history features are not credible here.
- Fraud appears only in `TRANSFER` and `CASH_OUT`; that eligibility condition
  is learned from training and must be revalidated in live data.
- The busy-receiver hypothesis did not survive validation and receives zero
  points.
- Off-hours performance may reflect simulator scheduling. A live deployment
  would shadow-test it, monitor drift, and retrain thresholds on rolling data.
