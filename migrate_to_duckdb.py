#!/usr/bin/env python3
"""
One-time migration: load all existing history.csv files into DuckDB.

Run this from the project root BEFORE resuming experiments:
    python migrate_to_duckdb.py

The database file is created at experiments/emergence.db, which is on the
same volume mounted into the dashboard-api container at /app/experiments/.
"""
import os
import glob
import duckdb
import pandas as pd

DB_PATH = os.path.join("experiments", "emergence.db")

_BASELINE_DIR_MAP = {
    "BASELINE-RANDOM": "random",
    "BASELINE-CVSS": "cvss_priority",
    "BASELINE-ROBIN": "round_robin",
    "BASELINE-NOML": "no_ml",
}


def infer_baseline_strategy(exp_dir_name: str) -> str:
    upper = exp_dir_name.upper()
    for prefix, strategy in _BASELINE_DIR_MAP.items():
        if prefix in upper:
            return strategy
    return "ml_guided"


def main():
    os.makedirs("experiments", exist_ok=True)

    files = sorted(glob.glob(os.path.join("experiments", "exp_*", "history.csv")))
    if not files:
        print("No history files found in experiments/ — nothing to migrate.")
        return

    print(f"Found {len(files)} history files. Loading...")

    dfs = []
    errors = 0
    for i, f in enumerate(files, 1):
        try:
            df = pd.read_csv(f)
            if df.empty:
                continue
            exp_dir_name = os.path.basename(os.path.dirname(f))
            df["exp_dir_name"] = exp_dir_name

            # Backfill columns that may be missing in older CSV files
            if "baseline_strategy" not in df.columns:
                df["baseline_strategy"] = infer_baseline_strategy(exp_dir_name)
            else:
                df["baseline_strategy"] = df["baseline_strategy"].fillna(
                    infer_baseline_strategy(exp_dir_name)
                )

            if "automl_tool" not in df.columns:
                df["automl_tool"] = "h2o"
            else:
                df["automl_tool"] = df["automl_tool"].fillna("h2o")

            dfs.append(df)
        except Exception as e:
            print(f"  Warning: could not read {f}: {e}")
            errors += 1

        if i % 100 == 0:
            print(f"  Loaded {i}/{len(files)} files...")

    if not dfs:
        print("No valid DataFrames found — nothing to migrate.")
        return

    print(f"Concatenating {len(dfs)} DataFrames...")
    combined = pd.concat(dfs, ignore_index=True)

    if "vulnerability_found" in combined.columns:
        combined["vulnerability_found"] = pd.to_numeric(
            combined["vulnerability_found"], errors="coerce"
        ).fillna(0).astype(int)

    print(f"Writing {len(combined):,} rows to {DB_PATH}...")
    con = duckdb.connect(DB_PATH)
    try:
        # Drop and recreate to ensure schema is fresh
        con.execute("DROP TABLE IF EXISTS history")
        con.execute("CREATE TABLE history AS SELECT * FROM combined")
        # Indexes for common query patterns
        con.execute("CREATE INDEX IF NOT EXISTS idx_sim_mode ON history (simulation_mode)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_automl ON history (automl_tool)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_exp_dir ON history (exp_dir_name)")
        count = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        print(f"\nDone. Migrated {count:,} rows from {len(dfs)} files to {DB_PATH}")
        if errors:
            print(f"  ({errors} files could not be read and were skipped)")
    finally:
        con.close()


if __name__ == "__main__":
    main()
