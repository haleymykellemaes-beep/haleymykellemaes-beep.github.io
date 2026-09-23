# Haley Maes — Data Analyst portfolio

Live site: **[haleymykellemaes-beep.github.io](https://haleymykellemaes-beep.github.io/)**

Static HTML/CSS/JS. No build step. Case studies with a question, a method, and a number you can argue with.

## Featured work

- [Accounts receivable tracker](ar-tracker.html) — Excel · dental operations. Collections $388k → $443k (+14%). Public workbook: [`AR-Sample-Ledger.xlsx`](AR-Sample-Ledger.xlsx) (IDs only, aging, pivots, dashboard).
- [Happiness and GDP](happiness-gdp.html) — Python · pandas. [`python/happiness_gdp.py`](python/happiness_gdp.py). r = 0.836 across 1,927 country–years.
- [Late returns pipeline](late-returns.html) — PostgreSQL. [`sql/late_returns.sql`](sql/late_returns.sql).
- [Projection vs the closing line](sports-projections.html) — Super Bowl LIX. SRS PHI −3.5 vs close KC −1. Vegas hold 14.6%.
- [What high-revenue films share](tmdb-revenue.html) — Python EDA. TMDb sample, inflation-adjusted revenue.
- [Nike demand vs inventory](nike.html) — FY2025 10-K analog. Tableau extract: [`data/nike-fy2025-analog.csv`](data/nike-fy2025-analog.csv). Publish steps in [`tableau/README.md`](tableau/README.md).

Also: [3NF normalization](normalization-3nf.html) note.

## Local preview

```bash
python3 -m http.server 8000
# http://localhost:8000/
```
