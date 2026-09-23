"""Happiness Report × World Bank GDP per capita.

Melt wide GDP, fix country aliases, inner-join, then the thumbnail number
(r of life evaluation vs log GDP). Raw CSVs are not in this repo; point
data_wrangling/raw/ at your local extracts.

Requires: pandas, numpy
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ALIASES = {
    "Czechia": "Czech Republic",
    "Korea, Rep.": "South Korea",
    "Russian Federation": "Russia",
    "Egypt, Arab Rep.": "Egypt",
    "Iran, Islamic Rep.": "Iran",
    "Slovak Republic": "Slovakia",
    "Turkiye": "Turkey",
    "Viet Nam": "Vietnam",
    "Hong Kong SAR, China": "Hong Kong",
    "Kyrgyz Republic": "Kyrgyzstan",
    "Lao PDR": "Laos",
    "Congo, Dem. Rep.": "Congo (Kinshasa)",
    "Congo, Rep.": "Congo (Brazzaville)",
}


def tidy_panel(happy: pd.DataFrame, gdp: pd.DataFrame) -> pd.DataFrame:
    gdp_long = gdp.melt(
        id_vars=["Country Name", "Country Code"],
        value_vars=[str(y) for y in range(2011, 2025)],
        var_name="year",
        value_name="gdp_per_capita",
    )
    gdp_long["year"] = gdp_long["year"].astype(int)
    gdp_long["country"] = gdp_long["Country Name"].replace(ALIASES)

    happy = happy.copy()
    happy["country"] = happy["country"].replace(ALIASES)

    panel = happy.merge(
        gdp_long[["country", "year", "gdp_per_capita"]],
        on=["country", "year"],
        how="inner",
    )
    panel = panel.dropna(subset=["life_evaluation", "gdp_per_capita"])
    panel = panel[panel["gdp_per_capita"] > 0]
    return panel


def thumbnail_stats(panel: pd.DataFrame) -> dict:
    panel = panel.copy()
    panel["log_gdp"] = np.log(panel["gdp_per_capita"])
    r = float(panel["life_evaluation"].corr(panel["log_gdp"]))
    panel["gdp_quartile"] = pd.qcut(
        panel["gdp_per_capita"], 4, labels=["Q1", "Q2", "Q3", "Q4"]
    )
    by_year = (
        panel.groupby("year")["life_evaluation"]
        .agg(mean_life="mean", n_countries="count")
        .round(2)
    )
    heat = panel.pivot_table(
        index="gdp_quartile",
        columns="year",
        values="life_evaluation",
        aggfunc="mean",
    )
    return {"r": r, "n": len(panel), "by_year": by_year, "heat": heat}


if __name__ == "__main__":
    happy = pd.read_csv("data_wrangling/raw/happiness_2011_2025.csv")
    gdp = pd.read_csv("data_wrangling/raw/gdp_per_capita.csv")
    panel = tidy_panel(happy, gdp)
    panel[["country", "year", "life_evaluation", "gdp_per_capita"]].to_csv(
        "cleaned_happiness_gdp_by_country_year.csv",
        index=False,
    )
    stats = thumbnail_stats(panel)
    print(f"rows={stats['n']}  r={stats['r']:.3f}")  # expected ~1927, 0.836
