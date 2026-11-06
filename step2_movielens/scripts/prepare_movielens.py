from __future__ import annotations

import json
import math
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

DATA_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"


def download_and_extract(project_root: Path) -> Path:
    raw_dir = project_root / "data" / "raw"
    extracted_dir = raw_dir / "ml-latest-small"
    zip_path = raw_dir / "ml-latest-small.zip"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if not extracted_dir.exists():
        if not zip_path.exists():
            print("Downloading MovieLens ml-latest-small from GroupLens...")
            urllib.request.urlretrieve(DATA_URL, zip_path)

        print("Extracting dataset...")
        with zipfile.ZipFile(zip_path, "r") as archive:
            # Guard against unexpected paths inside an archive.
            root = raw_dir.resolve()
            for member in archive.infolist():
                target = (raw_dir / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise ValueError(f"Unsafe archive path: {member.filename}")
            archive.extractall(raw_dir)

    if not (extracted_dir / "ratings.csv").exists():
        raise FileNotFoundError("ratings.csv was not found after extraction.")
    return extracted_dir


def prepare_movielens(project_root: Path) -> dict:
    source_dir = download_and_extract(project_root)
    output_dir = project_root / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    ratings = pd.read_csv(source_dir / "ratings.csv")
    movies = pd.read_csv(source_dir / "movies.csv")

    required_ratings = {"userId", "movieId", "rating", "timestamp"}
    required_movies = {"movieId", "title", "genres"}
    if not required_ratings.issubset(ratings.columns):
        raise ValueError(f"ratings.csv must contain: {sorted(required_ratings)}")
    if not required_movies.issubset(movies.columns):
        raise ValueError(f"movies.csv must contain: {sorted(required_movies)}")

    raw_rating_rows = len(ratings)
    raw_movie_rows = len(movies)

    # Convert numeric fields and remove incomplete rows.
    for col in ["userId", "movieId", "rating", "timestamp"]:
        ratings[col] = pd.to_numeric(ratings[col], errors="coerce")
    ratings = ratings.dropna(subset=["userId", "movieId", "rating", "timestamp"]).copy()
    ratings[["userId", "movieId", "timestamp"]] = ratings[
        ["userId", "movieId", "timestamp"]
    ].astype("int64")

    # The source defines ratings on a 0.5-to-5 scale in half-star increments.
    valid_rating = ratings["rating"].between(0.5, 5.0) & (
        (ratings["rating"] * 2).round() == ratings["rating"] * 2
    )
    invalid_rating_rows = int((~valid_rating).sum())
    ratings = ratings.loc[valid_rating].copy()

    # Keep the most recent rating if a user/movie pair appears more than once.
    duplicate_pair_rows = int(ratings.duplicated(["userId", "movieId"], keep=False).sum())
    ratings = (
        ratings.sort_values(["timestamp"])
        .drop_duplicates(["userId", "movieId"], keep="last")
        .sort_values(["userId", "timestamp", "movieId"])
        .reset_index(drop=True)
    )

    # Clean movie metadata and retain only ratings with a matching movie.
    movies["movieId"] = pd.to_numeric(movies["movieId"], errors="coerce")
    movies = movies.dropna(subset=["movieId", "title"]).copy()
    movies["movieId"] = movies["movieId"].astype("int64")
    movies["title"] = movies["title"].astype(str).str.strip()
    movies["genres"] = movies["genres"].fillna("(no genres listed)").astype(str)
    movies = movies[movies["title"].ne("")]
    movies = movies.drop_duplicates("movieId", keep="first").reset_index(drop=True)

    movie_ids = set(movies["movieId"])
    orphan_rows = int((~ratings["movieId"].isin(movie_ids)).sum())
    ratings = ratings[ratings["movieId"].isin(movie_ids)].copy()

    # Per-user chronological split: older 80% for training, newest 20% for test.
    train_parts = []
    test_parts = []
    users_with_too_few_rows = 0

    for _, group in ratings.groupby("userId", sort=False):
        group = group.sort_values(["timestamp", "movieId"]).reset_index(drop=True)
        if len(group) < 2:
            users_with_too_few_rows += 1
            train_parts.append(group)
            continue
        n_test = max(1, math.ceil(len(group) * 0.20))
        n_test = min(n_test, len(group) - 1)
        train_parts.append(group.iloc[:-n_test])
        test_parts.append(group.iloc[-n_test:])

    train = pd.concat(train_parts, ignore_index=True) if train_parts else ratings.iloc[0:0].copy()
    test = pd.concat(test_parts, ignore_index=True) if test_parts else ratings.iloc[0:0].copy()

    # Add movie metadata to rating records for easier inspection and later modeling.
    train_enriched = train.merge(movies, on="movieId", how="left", validate="many_to_one")
    test_enriched = test.merge(movies, on="movieId", how="left", validate="many_to_one")

    ratings.to_csv(output_dir / "ratings_clean.csv", index=False)
    movies.to_csv(output_dir / "movies_clean.csv", index=False)
    train_enriched.to_csv(output_dir / "train.csv", index=False)
    test_enriched.to_csv(output_dir / "test.csv", index=False)

    train_movie_ids = set(train["movieId"])
    cold_start_test_rows = int((~test["movieId"].isin(train_movie_ids)).sum())

    summary = {
        "source": "MovieLens ml-latest-small (GroupLens)",
        "download_url": DATA_URL,
        "raw_rating_rows": raw_rating_rows,
        "raw_movie_rows": raw_movie_rows,
        "clean_rating_rows": int(len(ratings)),
        "clean_movie_rows": int(len(movies)),
        "users": int(ratings["userId"].nunique()),
        "movies_with_metadata": int(movies["movieId"].nunique()),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_fraction": round(len(train) / len(ratings), 4) if len(ratings) else None,
        "test_fraction": round(len(test) / len(ratings), 4) if len(ratings) else None,
        "invalid_rating_rows_removed": invalid_rating_rows,
        "duplicate_user_movie_rows_detected": duplicate_pair_rows,
        "orphan_rating_rows_removed": orphan_rows,
        "test_rows_for_movies_absent_from_train": cold_start_test_rows,
        "users_with_fewer_than_two_ratings_after_cleaning": users_with_too_few_rows,
        "split_method": "per-user chronological split; newest 20% held out for test",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nSaved processed files to: {output_dir}")
    return summary


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    prepare_movielens(root)
