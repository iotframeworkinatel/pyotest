"""Additional per-protocol and per-iteration statistics quoted in the Emergence papers."""
import os
from pathlib import Path

# Run from the repository root so relative data paths resolve on any machine.
os.chdir(Path(__file__).resolve().parents[1])
import duckdb, numpy as np, pandas as pd
from scipy import stats
from math import log, exp, sqrt

con = duckdb.connect("experiments/emergence.db", read_only=True)

print("=" * 72)
print("A. Article 1: per-protocol counts for Table 5 (deterministic vs realistic, LOPO CSVs)")
print("=" * 72)
for mode in ["deterministic","realistic"]:
    f=f"experiments/aggregated_history_lopo_{mode}.csv"
    d=pd.read_csv(f)
    g = d.groupby('protocol').agg(n=('vulnerability_found','size'),
                                   vuln=('vulnerability_found','sum'))
    g['rate'] = g['vuln']/g['n']
    g['unique'] = d[d.vulnerability_found==1].drop_duplicates(subset=['container_id','open_port','protocol','test_id']).groupby('protocol').size().reindex(g.index, fill_value=0)
    g = g.sort_values('rate', ascending=False)
    print(f"\n--- {mode} ---")
    print(g.to_string())
    vuln_rows = d[d.vulnerability_found == 1]
    n_quad = len(vuln_rows.drop_duplicates(subset=['container_id','open_port','protocol','test_id']))
    n_pair = len(vuln_rows.drop_duplicates(subset=['protocol','test_id']))
    print(f"TOTAL unique (container, port, protocol, test) = {n_quad}; "
          f"unique (protocol, test) pairs = {n_pair}")

print()
print("=" * 72)
print("B. Article 1: per-iteration unique-new discovery velocity (realistic, LOPO)")
print("=" * 72)
d=pd.read_csv("experiments/aggregated_history_lopo_realistic.csv")
# unique combos up to iteration k
key = d[['container_id','open_port','protocol','test_id','vulnerability_found','simulation_iteration']].copy()
key = key[key.vulnerability_found==1].copy()
key['combo'] = key.apply(lambda r: (r.container_id,r.open_port,r.protocol,r.test_id), axis=1)
# sort by iter, pick earliest iter per combo, then count per iter
first_seen = key.groupby('combo')['simulation_iteration'].min()
new_per_iter = first_seen.value_counts().sort_index()
print("iterations with new combos:", len(new_per_iter))
print(f"mean new/iter: {new_per_iter.mean():.3f}, sd: {new_per_iter.std():.3f}")
print(f"median new/iter: {new_per_iter.median():.3f}")
print()

print("=" * 72)
print("C. Article 1/5: Kruskal-Wallis of per-iteration unique-combo deltas across modes")
print("=" * 72)
# per-iteration unique detection count (fresh, not cumulative) per mode from DB
# easier: per-iteration vulnerability_found sum per mode, across framework phase
q = """
SELECT simulation_mode, simulation_iteration,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate,
       COUNT(*) AS n
FROM history
WHERE phase='framework'
GROUP BY simulation_mode, simulation_iteration
ORDER BY simulation_mode, simulation_iteration
"""
df = con.execute(q).fetchdf()
print(df.groupby('simulation_mode')['rate'].describe())
print()
groups = [df[df.simulation_mode==m]['rate'].values for m in ['deterministic','medium','realistic']]
H, p = stats.kruskal(*groups)
print(f"Kruskal-Wallis across modes (per-iter detection rate): H={H:.3f}, p={p:.6g}")
# pairwise Mann-Whitney with Holm
from itertools import combinations
modes = ['deterministic','medium','realistic']
raw_p = []
for a,b in combinations(modes,2):
    u, pm = stats.mannwhitneyu(df[df.simulation_mode==a]['rate'], df[df.simulation_mode==b]['rate'])
    # rank-biserial
    n1 = (df.simulation_mode==a).sum()
    n2 = (df.simulation_mode==b).sum()
    rb = 2*u/(n1*n2)-1
    raw_p.append((a,b,u,pm,rb))
# Holm-Bonferroni
raw_p_sorted = sorted(raw_p, key=lambda x:x[3])
m_tests = len(raw_p)
for i,(a,b,u,pm,rb) in enumerate(raw_p_sorted):
    holm = min(pm*(m_tests-i), 1.0)
    print(f"  {a} vs {b}: U={u:.0f}, raw p={pm:.6g}, Holm p={holm:.6g}, rb r={rb:.3f}")
print()

print("=" * 72)
print("D. Article 2: H1 in-phase detection-rate stability — Spearman rank over iter")
print("=" * 72)
q = """
SELECT simulation_iteration, 1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase='framework' AND simulation_mode='realistic' AND baseline_strategy='ml_guided'
GROUP BY simulation_iteration ORDER BY simulation_iteration
"""
d = con.execute(q).fetchdf()
rho, p_spear = stats.spearmanr(d['simulation_iteration'], d['rate'])
print(f"Spearman over 100 iters: rho={rho:.4f}, p={p_spear:.4f}")
# early vs late halves
early = d.iloc[:50]['rate'].values; late = d.iloc[50:]['rate'].values
u, pm = stats.mannwhitneyu(early, late)
# cohen's d
m1,m2 = early.mean(), late.mean()
s1,s2 = early.std(ddof=1), late.std(ddof=1)
pooled = sqrt(((len(early)-1)*s1*s1 + (len(late)-1)*s2*s2)/(len(early)+len(late)-2))
d_cohen = (m1-m2)/pooled if pooled>0 else float('nan')
print(f"early-vs-late Mann-Whitney: U={u:.0f}, p={pm:.4f}, Cohen's d={d_cohen:.3f}")
print(f"early mean={m1:.4f} sd={s1:.4f}; late mean={m2:.4f} sd={s2:.4f}")
print()

print("=" * 72)
print("E. Article 2: per-protocol Spearman slope + variance ratio (H3)")
print("=" * 72)
q = """
SELECT protocol, simulation_iteration, 1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase='framework' AND simulation_mode='realistic' AND baseline_strategy='ml_guided'
GROUP BY protocol, simulation_iteration
ORDER BY protocol, simulation_iteration
"""
df = con.execute(q).fetchdf()
for p in df.protocol.unique():
    sub = df[df.protocol==p].sort_values('simulation_iteration')
    if len(sub)>=10:
        rho, pv = stats.spearmanr(sub['simulation_iteration'], sub['rate'])
        early = sub.iloc[:50]['rate'].var()
        late  = sub.iloc[50:]['rate'].var()
        ratio = (early/late) if late>0 else float('inf')
        print(f"  {p:8s} rho={rho:+.4f} p={pv:.4f}   early/late var ratio={ratio:.3f}  mean rate={sub['rate'].mean():.4f}")
print()

print("=" * 72)
print("F. Article 2: H5 efficiency — compare ML (ml_guided) vs baselines on coverage per test")
print("=" * 72)
# per-iteration unique discoveries / tests executed
q = """
SELECT baseline_strategy, simulation_iteration,
       COUNT(*) AS n_tests,
       COUNT(DISTINCT CASE WHEN vulnerability_found=1
             THEN container_id || '|' || CAST(open_port AS VARCHAR) || '|' || protocol || '|' || test_id END) AS uniq
FROM history
WHERE simulation_mode='deterministic' AND phase IN ('framework','baseline')
GROUP BY baseline_strategy, simulation_iteration
"""
df = con.execute(q).fetchdf()
for strat in ['ml_guided','random','round_robin','no_ml','cvss_priority']:
    s = df[df.baseline_strategy==strat]
    if len(s):
        eff = (s['uniq']/s['n_tests']).values
        print(f"  {strat:15s} n={len(s):4d}  mean uniq/test = {eff.mean():.4f}  sd={eff.std():.4f}")
print()
# Wilcoxon signed-rank (paired by iteration) ML vs round_robin
ml = df[df.baseline_strategy=='ml_guided'].set_index('simulation_iteration')['uniq']
rr = df[df.baseline_strategy=='round_robin'].set_index('simulation_iteration')['uniq']
common = ml.index.intersection(rr.index)
if len(common):
    s, pv = stats.wilcoxon(ml.loc[common].values, rr.loc[common].values)
    print(f"  Wilcoxon ML vs round_robin uniq-per-iter: W={s:.1f}, p={pv:.4f}")
print()

print("=" * 72)
print("G. Article 4b / 5: phase6 LLM contribution — rows and detection per mode")
print("=" * 72)
q = """
SELECT simulation_mode, test_origin,
       COUNT(*) AS n, SUM(vulnerability_found) AS vuln,
       1.0*SUM(vulnerability_found)/COUNT(*) AS rate
FROM history
WHERE phase='phase6'
GROUP BY simulation_mode, test_origin
ORDER BY simulation_mode, test_origin
"""
print(con.execute(q).fetchdf().to_string(index=False))
print()

print("=" * 72)
print("H. H7 cross-framework: use the 16 archived AUCs grouped by framework")
print("=" * 72)
import json, glob, os
fw_aucs = {}
for path in sorted(glob.glob("models/archive/*/model_metrics.json")):
    with open(path) as f:
        m = json.load(f)
    name = os.path.basename(os.path.dirname(path))
    fw = name.split('_')[0]
    auc = m.get('auc') or m.get('roc_auc')
    fw_aucs.setdefault(fw, []).append(auc)
print("Framework -> AUC list:")
for fw, aucs in fw_aucs.items():
    print(f"  {fw:15s} {sorted(aucs)}  mean={np.mean(aucs):.4f}")
print()
groups = [fw_aucs[fw] for fw in ['autogluon','h2o','pycaret','autosklearn']]
try:
    H, p = stats.kruskal(*groups)
    print(f"Kruskal-Wallis 4 frameworks: H={H:.3f}, p={p:.6g}")
except Exception as e:
    print("KW err", e)
# Pairwise
for a,b in combinations(['autogluon','h2o','pycaret','autosklearn'],2):
    try:
        u, pm = stats.mannwhitneyu(fw_aucs[a], fw_aucs[b])
        print(f"  {a} vs {b}: U={u:.0f}, p={pm:.4f}")
    except Exception as e:
        print(f"  {a} vs {b}: err", e)
print()

print("=" * 72)
print("I. Framework × mode interaction Kruskal (mode factor only)")
print("=" * 72)
# Group AUCs by mode
mode_aucs = {}
for path in sorted(glob.glob("models/archive/*/model_metrics.json")):
    with open(path) as f:
        m = json.load(f)
    name = os.path.basename(os.path.dirname(path))
    parts = name.split('_')
    fw = parts[0]
    mode = parts[1]
    phase = '_'.join(parts[2:]) or 'phase1'
    auc = m.get('auc') or m.get('roc_auc')
    mode_aucs.setdefault(mode, []).append(auc)
for mode, aucs in mode_aucs.items():
    print(f"  {mode:15s} {sorted(aucs)}  mean={np.mean(aucs):.4f}")
groups = [mode_aucs[m] for m in ['deterministic','medium','realistic']]
try:
    H, p = stats.kruskal(*groups)
    print(f"Kruskal-Wallis mode factor: H={H:.3f}, p={p:.6g}")
except Exception as e:
    print("err", e)
print()

print("=" * 72)
print("J. ECE from temporal_metrics (cross-framework/mode means)")
print("=" * 72)
exp_paths = [
    ("pycaret","det","experiments/exp_TEMPORAL_P5-CTRL-DET-100-PYCARET_2026-04-13T20-56-58/temporal_metrics.csv"),
    ("pycaret","med","experiments/exp_TEMPORAL_P5-TREAT-MED-100-PYCARET_2026-04-14T01-30-12/temporal_metrics.csv"),
    ("pycaret","real","experiments/exp_TEMPORAL_P5-TREAT-REAL-100-PYCARET_2026-04-14T06-00-23/temporal_metrics.csv"),
    ("autogluon","det","experiments/exp_TEMPORAL_P6-CTRL-DET-100-AUTOGLUON_2026-04-14T08-58-13/temporal_metrics.csv"),
    ("autogluon","med","experiments/exp_TEMPORAL_P6-TREAT-MED-100-AUTOGLUON_2026-04-14T19-29-46/temporal_metrics.csv"),
]
for fw, mode, f in exp_paths:
    d = pd.read_csv(f)
    print(f"  {fw} {mode}: ECE mean={d['ece'].mean():.4f} sd={d['ece'].std():.4f}  Brier mean={d['brier_score'].mean():.4f}")
print()
