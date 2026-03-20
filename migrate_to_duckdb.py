#!/usr/bin/env python3
"""
Rebuild DuckDB from all existing history.csv files.

Run this from the project root after experiments complete to produce a
self-contained, fully-tagged database that can be shared for verification:

    python migrate_to_duckdb.py

The database is written to experiments/emergence.db (same path mounted into
the dashboard-api container at /app/experiments/).

All tagging columns (phase, test_origin, score_method, automl_tool,
baseline_strategy) are backfilled so the DB is usable without the raw CSVs.
Row counts per (automl_tool, simulation_mode, simulation_seed, phase) are
printed at the end so the recipient can verify completeness.
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
_NON_ML_BS = {"random", "cvss_priority", "round_robin", "no_ml"}


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

            # ── automl_tool ──────────────────────────────────────────────
            if "automl_tool" not in df.columns:
                df["automl_tool"] = "h2o"
            else:
                df["automl_tool"] = df["automl_tool"].fillna("h2o")

            # ── baseline_strategy ────────────────────────────────────────
            if "baseline_strategy" not in df.columns:
                df["baseline_strategy"] = infer_baseline_strategy(exp_dir_name)
            else:
                df["baseline_strategy"] = df["baseline_strategy"].fillna(
                    infer_baseline_strategy(exp_dir_name)
                )

            # ── phase ────────────────────────────────────────────────────
            # Rows written by the live API already carry an explicit phase tag.
            # For older rows that predate the column, derive it heuristically.
            if "phase" not in df.columns:
                df["phase"] = df["baseline_strategy"].apply(
                    lambda x: "baseline" if x in _NON_ML_BS else "framework"
                )
            else:
                null_mask = df["phase"].isna()
                df.loc[null_mask, "phase"] = df.loc[null_mask, "baseline_strategy"].apply(
                    lambda x: "baseline" if x in _NON_ML_BS else "framework"
                )

            # ── test_origin ──────────────────────────────────────────────
            if "test_origin" not in df.columns:
                if "test_strategy" in df.columns:
                    df["test_origin"] = df["test_strategy"].apply(
                        lambda x: "llm" if x == "llm_generated" else "registry"
                    )
                else:
                    df["test_origin"] = "registry"
            else:
                df["test_origin"] = df["test_origin"].fillna("registry")

            # ── score_method ─────────────────────────────────────────────
            if "score_method" not in df.columns:
                df["score_method"] = df["baseline_strategy"].apply(
                    lambda x: "heuristic" if x in _NON_ML_BS else "ml"
                )
            else:
                null_mask = df["score_method"].isna()
                df.loc[null_mask, "score_method"] = df.loc[null_mask, "baseline_strategy"].apply(
                    lambda x: "heuristic" if x in _NON_ML_BS else "ml"
                )

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
        # Drop and recreate to ensure schema is fresh and consistent
        con.execute("DROP TABLE IF EXISTS history")
        con.execute("CREATE TABLE history AS SELECT * FROM combined")
        # Indexes for the four isolation dimensions used during analysis
        con.execute("CREATE INDEX IF NOT EXISTS idx_sim_mode   ON history (simulation_mode)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_automl     ON history (automl_tool)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_seed       ON history (simulation_seed)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_phase      ON history (phase)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_exp_dir    ON history (exp_dir_name)")
        count = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        print(f"\nDone. Migrated {count:,} rows from {len(dfs)} files to {DB_PATH}")
        if errors:
            print(f"  ({errors} files could not be read and were skipped)")

        # ── Completeness report ──────────────────────────────────────────
        # Lets the recipient verify no experiment group is missing data.
        print("\nRow counts per experiment group (automl_tool / simulation_mode / simulation_seed / phase):")
        summary = con.execute("""
            SELECT
                automl_tool,
                simulation_mode,
                simulation_seed,
                phase,
                COUNT(*)            AS rows,
                COUNT(DISTINCT exp_dir_name) AS iterations
            FROM history
            GROUP BY automl_tool, simulation_mode, simulation_seed, phase
            ORDER BY automl_tool, simulation_mode, simulation_seed, phase
        """).df()
        print(summary.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
