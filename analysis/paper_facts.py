"""
Paper-fact extraction script.
Prints the descriptive statistics (row counts, detection rates per strategy,
per-protocol figures) quoted in the Emergence papers.
"""
import os
from pathlib import Path

# Run from the repository root so relative data paths resolve on any machine.
os.chdir(Path(__file__).resolve().parents[1])
import duckdb
import numpy as np
import pandas as pd
from scipy import stats

con = duckdb.connect("experiments/emergence.db", read_only=True)

print("=" * 72)
print("1. OVERALL DETECTION RATE + ROW COUNTS PER STRATEGY")
print("=" * 72)

# Per (phase, strategy) detection rate
q = """
SELECT
  phase,
  simulation_mode,
  COALESCE(baseline_strategy, automl_tool) AS strat,
  test_origin,
  COUNT(*) AS n_tests,
  SUM(vulnerability_found) AS n_vuln,
  1.0 * SUM(vulnerability_found) / COUNT(*) AS det_rate
FROM history
GROUP BY phase, simulation_mode, strat, test_origin
ORDER BY phase, simulation_mode, strat, test_origin
"""
df = con.execute(q).fetchdf()
print(df.to_string(index=False))
print()

print("=" * 72)
print("2. H1 STABILITY: per-iteration detection rate SD in realistic ML-guided")
print("=" * 72)
q = """
SELECT
  simulation_iteration,
  COUNT(*) AS n,
  SUM(vulnerability_found) AS vuln,
  1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase='framework' AND simulation_mode='realistic'
  AND baseline_strategy='ml_guided' AND test_origin='registry'
GROUP BY simulation_iteration
ORDER BY simulation_iteration
"""
df = con.execute(q).fetchdf()
print(f"iterations: {len(df)}, mean={df['rate'].mean():.4f}, sd={df['rate'].std():.4f}")
print(f"min={df['rate'].min():.4f}, max={df['rate'].max():.4f}")
print()

print("=" * 72)
print("3. H6 UNIQUE DEDUP COMBOS PER MODE")
print("=" * 72)
q = """
SELECT simulation_mode,
       COUNT(DISTINCT (container_id,open_port,protocol,test_id))
         FILTER (WHERE vulnerability_found=1) AS unique_combos
FROM history
WHERE phase='framework'
GROUP BY simulation_mode
ORDER BY simulation_mode
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("3b. PER-PROTOCOL UNIQUE COMBOS")
print("=" * 72)
q = """
SELECT simulation_mode, protocol,
       COUNT(DISTINCT (container_id,open_port,test_id))
         FILTER (WHERE vulnerability_found=1) AS unique_combos
FROM history
WHERE phase='framework'
GROUP BY simulation_mode, protocol
ORDER BY simulation_mode, protocol
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("4. H10a LLM EFFECTIVENESS: Fisher exact")
print("=" * 72)

for mode in ["deterministic", "medium", "realistic"]:
    q = f"""
    SELECT test_origin,
           SUM(CASE WHEN vulnerability_found=1 THEN 1 ELSE 0 END) AS vuln,
           SUM(CASE WHEN vulnerability_found=0 THEN 1 ELSE 0 END) AS safe,
           COUNT(*) AS n
    FROM history
    WHERE phase='llm' AND simulation_mode='{mode}'
    GROUP BY test_origin
    ORDER BY test_origin
    """
    df = con.execute(q).fetchdf()
    print(f"MODE={mode}")
    print(df.to_string(index=False))
    try:
        llm_vuln = int(df.loc[df.test_origin=='llm','vuln'].iloc[0])
        llm_safe = int(df.loc[df.test_origin=='llm','safe'].iloc[0])
        reg_vuln = int(df.loc[df.test_origin=='registry','vuln'].iloc[0])
        reg_safe = int(df.loc[df.test_origin=='registry','safe'].iloc[0])
        table = [[llm_vuln, llm_safe],[reg_vuln, reg_safe]]
        odds, p = stats.fisher_exact(table)
        # Woolf logit 95% CI on OR
        import math
        a,b,c,d = llm_vuln, llm_safe, reg_vuln, reg_safe
        ln_or = math.log((a*d)/(b*c)) if a>0 and b>0 and c>0 and d>0 else float('nan')
        se = math.sqrt(1/a + 1/b + 1/c + 1/d) if all(x>0 for x in [a,b,c,d]) else float('nan')
        lo, hi = math.exp(ln_or-1.96*se), math.exp(ln_or+1.96*se)
        print(f"  Fisher p={p:.6g}, OR={odds:.4f} [95% CI {lo:.4f}-{hi:.4f}]")
    except Exception as e:
        print("  ", e)
    print()

print("=" * 72)
print("5. H9: ML vs baselines detection rates — deterministic")
print("=" * 72)
q = """
SELECT baseline_strategy,
       COUNT(*) AS n,
       SUM(vulnerability_found) AS vuln,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE (phase='baseline' OR phase='framework')
  AND simulation_mode='deterministic'
GROUP BY baseline_strategy
ORDER BY baseline_strategy NULLS LAST
"""
df = con.execute(q).fetchdf()
print(df.to_string(index=False))
print()

# Pairwise Mann-Whitney by iteration
print("--- pairwise per-iteration Mann-Whitney (deterministic) ---")
iter_rates = {}
for strat in ["ml_guided","random","round_robin","no_ml","cvss_priority"]:
    q = f"""
    SELECT simulation_iteration,
           1.0*SUM(vulnerability_found)/COUNT(*) AS rate
    FROM history
    WHERE simulation_mode='deterministic' AND baseline_strategy='{strat}'
    GROUP BY simulation_iteration
    """
    df = con.execute(q).fetchdf()
    iter_rates[strat] = df['rate'].values
    print(f"  {strat}: n_iters={len(df)}, mean={df['rate'].mean():.4f}")
print()
for b in ["random","round_robin","no_ml","cvss_priority"]:
    if len(iter_rates['ml_guided']) and len(iter_rates[b]):
        u, p = stats.mannwhitneyu(iter_rates['ml_guided'], iter_rates[b], alternative='greater')
        print(f"  ML > {b}: U={u:.0f}, p={p:.4f}")
print()

print("=" * 72)
print("6. H7: AUCs per framework per mode (from temporal_metrics / archives)")
print("=" * 72)
# We have archived model_metrics.json files; read them.
import json, glob, os
for path in sorted(glob.glob("models/archive/*/model_metrics.json")):
    try:
        with open(path) as f:
            m = json.load(f)
        fw = os.path.basename(os.path.dirname(path))
        print(f"{fw:45s} AUC={m.get('auc', m.get('roc_auc','?'))}  brier={m.get('brier','?')}  ece={m.get('ece','?')}  train_s={m.get('training_time_sec',m.get('train_time_sec','?'))}  models={m.get('ensemble_size', m.get('n_models','?'))}")
    except Exception as e:
        print(f"err {path}: {e}")
print()

print("=" * 72)
print("7. H8 temporal metrics: Wilcoxon signed-rank AUC vs 0.5")
print("=" * 72)
for f in [
    "experiments/exp_TEMPORAL_P5-CTRL-DET-100-PYCARET_2026-04-13T20-56-58/temporal_metrics.csv",
    "experiments/exp_TEMPORAL_P5-TREAT-MED-100-PYCARET_2026-04-14T01-30-12/temporal_metrics.csv",
    "experiments/exp_TEMPORAL_P5-TREAT-REAL-100-PYCARET_2026-04-14T06-00-23/temporal_metrics.csv",
    "experiments/exp_TEMPORAL_P6-CTRL-DET-100-AUTOGLUON_2026-04-14T08-58-13/temporal_metrics.csv",
    "experiments/exp_TEMPORAL_P6-TREAT-MED-100-AUTOGLUON_2026-04-14T19-29-46/temporal_metrics.csv",
]:
    try:
        d = pd.read_csv(f)
        aucs = d['auc_roc'].values
        # one-sided test H1: median > 0.5
        stat, p = stats.wilcoxon(aucs - 0.5, alternative='greater')
        print(f"{os.path.basename(os.path.dirname(f))[:60]:60s}  mean AUC={aucs.mean():.4f}  min={aucs.min():.4f}  max={aucs.max():.4f}  Wilcoxon W={stat:.1f} p={p:.6g}")
    except Exception as e:
        print(f"  err {f}: {e}")
print()

print("=" * 72)
print("8. PER-PROTOCOL DETECTION RATES (deterministic framework)")
print("=" * 72)
q = """
SELECT protocol,
       COUNT(*) AS n,
       SUM(vulnerability_found) AS vuln,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase='framework' AND simulation_mode='deterministic'
GROUP BY protocol ORDER BY rate DESC, protocol
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("9. H10b LLM GENERATION: protocols where LLM tests were produced")
print("=" * 72)
q = """
SELECT protocol, COUNT(*) AS n_llm_tests,
       SUM(vulnerability_found) AS vuln,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE test_origin='llm' AND phase IN ('llm','phase6')
GROUP BY protocol
ORDER BY n_llm_tests DESC
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("10. LLM vs REGISTRY per protocol (realistic)")
print("=" * 72)
q = """
SELECT protocol, test_origin,
       COUNT(*) AS n,
       SUM(vulnerability_found) AS vuln,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase IN ('llm','phase6') AND simulation_mode='realistic'
GROUP BY protocol, test_origin
ORDER BY protocol, test_origin
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("11. FRAMEWORK × MODE per-experiment AUCs from archives  (H7 Kruskal)")
print("=" * 72)
# We only have single-AUC per archive, so KW is limited. Use per-iteration AUC from temporal_metrics
# We have iteration-level AUCs for Phase5 PyCaret + Phase6 AutoGluon; that's 2 frameworks per mode.
# For Phase 1 (framework phase) we only have the single metric from model_metrics.json.
# Construct the best approximation: we use the single-point AUC per (framework, mode) across archives.
rows = []
for path in sorted(glob.glob("models/archive/*/model_metrics.json")):
    with open(path) as f:
        m = json.load(f)
    fw_mode = os.path.basename(os.path.dirname(path))
    auc = m.get('auc') or m.get('roc_auc')
    rows.append((fw_mode, auc))
print("archived metrics:")
for r in rows:
    print(f"  {r[0]:40s} AUC={r[1]}")
print()
