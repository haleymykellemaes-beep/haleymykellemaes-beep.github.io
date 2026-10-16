"""TMDb high-revenue films.

Inflation-adjusted revenue against budget, popularity, genre, and release year.
Frequency is not revenue. These are associations in the sample, not a recipe
for a hit and not a causal claim.

Haley Maes.

The CSV is the TMDb movies extract (columns include budget, revenue,
budget_adj, revenue_adj, popularity, vote_average, runtime, genres,
release_year, imdb_id). It is not in this repo; point the path at your copy.
Requires: pandas, numpy
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path("data_wrangling/raw/tmdb-movies.csv")
MIN_FILMS = 50
MONEY = ("budget", "revenue", "budget_adj", "revenue_adj")


def load_movies(path: Path = CSV) -> pd.DataFrame:
    movies = pd.read_csv(path)
    # The extract repeats one title (TEKKEN). Ten rows have no IMDb id;
    # the case page's 2014 count (699) is after those rows are set aside.
    movies = movies.drop_duplicates()
    movies = movies.dropna(subset=["imdb_id"])
    for col in MONEY:
        movies[col] = movies[col].replace(0, np.nan)
    return movies


def with_revenue(movies: pd.DataFrame) -> pd.DataFrame:
    """Complete cases on inflation-adjusted revenue. Zeros are already missing."""
    return movies.dropna(subset=["revenue_adj"]).copy()


def associations(revenue: pd.DataFrame) -> pd.Series:
    """Pearson r with revenue_adj. Budget and popularity are the stronger pair."""
    cols = ["budget_adj", "popularity", "vote_average", "runtime", "revenue_adj"]
    return revenue[cols].corr()["revenue_adj"].drop("revenue_adj")


def genre_frequency(movies: pd.DataFrame) -> pd.Series:
    genres = movies["genres"].dropna().str.split("|").explode()
    return genres.value_counts()


def genre_median_revenue(revenue: pd.DataFrame, min_films: int = MIN_FILMS) -> pd.DataFrame:
    """Multi-label genres: a film can sit in more than one median."""
    expanded = (
        revenue.dropna(subset=["genres"])
        .assign(genre=lambda frame: frame["genres"].str.split("|"))
        .explode("genre")
    )
    summary = expanded.groupby("genre")["revenue_adj"].agg(n="count", median="median")
    summary = summary[summary["n"] >= min_films].sort_values("median", ascending=False)
    summary["median_millions_2010"] = summary["median"] / 1e6
    return summary


def year_pattern(movies: pd.DataFrame, revenue: pd.DataFrame) -> dict:
    counts = movies["release_year"].value_counts()
    return {
        "peak_year": int(counts.idxmax()),
        "peak_titles": int(counts.max()),
        "year_vs_popularity": float(movies["release_year"].corr(movies["popularity"])),
        "year_vs_revenue_adj": float(revenue["release_year"].corr(revenue["revenue_adj"])),
    }


def main(path: Path = CSV) -> None:
    movies = load_movies(path)
    revenue = with_revenue(movies)
    medians = genre_median_revenue(revenue)
    years = year_pattern(movies, revenue)

    print(f"titles={len(movies)}")
    print(f"budget missing or zero={movies['budget'].isna().mean():.0%}")
    print(f"revenue missing or zero={movies['revenue'].isna().mean():.0%}")
    print(associations(revenue).round(3).to_string())
    print(genre_frequency(movies).head(4).to_string())
    shown = medians.loc[
        ["Animation", "Adventure", "Comedy"],
        ["n", "median_millions_2010"],
    ]
    print(shown.round(1).to_string())
    print(
        f"peak={years['peak_year']} n={years['peak_titles']}  "
        f"year~popularity={years['year_vs_popularity']:.2f}  "
        f"year~revenue_adj={years['year_vs_revenue_adj']:.2f}"
    )


if __name__ == "__main__":
    csv = Path(sys.argv[1]) if len(sys.argv) > 1 else CSV
    main(csv)
