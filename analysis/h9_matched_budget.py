"""Matched-budget H9 bootstrap across simulation modes."""
import os
from pathlib import Path

# Run from the repository root so relative data paths resolve on any machine.
os.chdir(Path(__file__).resolve().parents[1])
import numpy as np
import duckdb
from scipy.stats import mannwhitneyu, fisher_exact

np.random.seed(42)
con = duckdb.connect("experiments/emergence.db", read_only=True)

MODES = ["deterministic", "medium", "realistic"]
STRATS = ["random", "round_robin", "cvss_priority", "no_ml"]

def fetch(mode, strat):
    q = f"""
        SELECT vulnerability_found FROM history
        WHERE simulation_mode='{mode}' AND baseline_strategy='{strat}'
          AND phase='baseline'
    """
    return con.execute(q).fetchdf()["vulnerability_found"].astype(int).values

def fetch_ml(mode):
    q = f"""
        SELECT vulnerability_found FROM history
        WHERE simulation_mode='{mode}' AND baseline_strategy='ml_guided'
          AND phase='framework' AND test_origin='registry'
    """
    return con.execute(q).fetchdf()["vulnerability_found"].astype(int).values

BOOT = 2000
for mode in MODES:
    ml_full = fetch_ml(mode)
    print(f"\n=== {mode} (ml_full n={len(ml_full)}, rate={ml_full.mean():.4f}) ===")
    for strat in STRATS:
        base = fetch(mode, strat)
        n_b = len(base)
        r_b = base.mean()

        # Bootstrap: subsample ML to n_b, compute rate, repeat BOOT times
        idx = np.random.choice(len(ml_full), size=(BOOT, n_b), replace=True)
        ml_sub_rates = ml_full[idx].mean(axis=1)
        diffs = ml_sub_rates - r_b
        lo, hi = np.quantile(diffs, [0.025, 0.975])
        frac_ml_wins = (diffs > 0).mean()

        # Fisher exact on full contingency (sanity)
        m_v = int(ml_full.sum()); m_n = len(ml_full) - m_v
        b_v = int(base.sum()); b_n = n_b - b_v
        # OR direction: ml vs baseline
        try:
            odds, pval = fisher_exact([[m_v, m_n],[b_v, b_n]], alternative="greater")
        except Exception:
            odds, pval = float("nan"), float("nan")

        print(f"  {strat:14s}  base n={n_b} r={r_b:.4f}  "
              f"ML-base CI95=[{lo:+.4f},{hi:+.4f}]  "
              f"P(ML>base)={frac_ml_wins:.3f}  Fisher-greater p={pval:.3g}")
