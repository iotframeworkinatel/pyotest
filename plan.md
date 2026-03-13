# Emergence — PhD Experiment Plan

## Status: Experiments in progress (resumed after crash)

**Last updated**: 2026-03-13

---

## Experiment Matrix Overview

42 experiments + 15 LOPO evaluations across 4 phases.
Total: ~4,200 iterations at ~2.5 min/iter = ~174 hours (~7.3 days).

### Phase 1: ML Framework Experiments (15 experiments × 100 iterations)
5 AutoML frameworks × 3 simulation modes. Each trains every 10 iterations with temporal validation.

| Experiment | Framework | Mode | Status |
|---|---|---|---|
| CTRL-DET-100-H2O | H2O | deterministic | DONE (100/100) |
| TREAT-MED-100-H2O | H2O | medium | CRASHED at 78/100 — re-running |
| TREAT-REAL-100-H2O | H2O | realistic | Pending |
| CTRL-DET-100-AUTOGLUON | AutoGluon | deterministic | Pending |
| TREAT-MED-100-AUTOGLUON | AutoGluon | medium | Pending |
| TREAT-REAL-100-AUTOGLUON | AutoGluon | realistic | Pending |
| CTRL-DET-100-PYCARET | PyCaret | deterministic | Pending |
| TREAT-MED-100-PYCARET | PyCaret | medium | Pending |
| TREAT-REAL-100-PYCARET | PyCaret | realistic | Pending |
| CTRL-DET-100-TPOT | TPOT | deterministic | Pending |
| TREAT-MED-100-TPOT | TPOT | medium | Pending |
| TREAT-REAL-100-TPOT | TPOT | realistic | Pending |
| CTRL-DET-100-AUTOSKLEARN | auto-sklearn | deterministic | Pending |
| TREAT-MED-100-AUTOSKLEARN | auto-sklearn | medium | Pending |
| TREAT-REAL-100-AUTOSKLEARN | auto-sklearn | realistic | Pending |

### Phase 2: Baseline Experiments (12 experiments × 100 iterations)
4 non-ML baselines × 3 modes. No training (train_every_n=0).

| Experiment | Strategy | Mode | Status |
|---|---|---|---|
| BASELINE-RANDOM-{DET,MED,REA}-100 | Random selection | all 3 | Pending |
| BASELINE-CVSS-{DET,MED,REA}-100 | CVSS severity priority | all 3 | Pending |
| BASELINE-ROBIN-{DET,MED,REA}-100 | Round-robin | all 3 | Pending |
| BASELINE-NOML-{DET,MED,REA}-100 | No ML (run all tests) | all 3 | Pending |

### Phase 3: LLM Generation Experiments (15 experiments × 100 iterations)
5 frameworks × 3 modes + Claude LLM generation every 25 iterations.

| Experiment | Framework + LLM | Mode | Status |
|---|---|---|---|
| LLM-{DET,MED,REAL}-100-{Framework} | Each framework + Claude | all 3 | Pending |

### Phase 4: LOPO Analysis (post-processing)
15 evaluations (5 frameworks × 3 modes). Reads existing history, no new iterations.

---

## 11 Research Hypotheses

### H1: Detection Rate Stability
- **Question**: Does ML-guided detection rate remain stable despite environmental mutations?
- **Tests**: Spearman/Pearson correlation, Mann-Whitney U (early vs late), Cohen's d
- **Expected**: Supported in deterministic, fragile in realistic (noise masks trend)

### H2: Recommendation Effectiveness
- **Question**: Do ML-recommended tests achieve higher detection rates?
- **Tests**: Fisher's exact test, lift ratio, threshold sweep precision-recall
- **Expected**: Likely supported — even basic classifiers beat random on structured features

### H3: Protocol Convergence Rates
- **Question**: Does cross-protocol variance decrease over time?
- **Tests**: Per-protocol regression slopes, Levene's test, Mann-Whitney on variance
- **Expected**: Supported in deterministic, not supported in realistic (outages add variance)

### H4: Risk Score Calibration
- **Question**: Are predicted risk scores well-calibrated?
- **Tests**: ECE (10 decile bins), MCE, Brier score
- **Known issue**: Heuristic scoring produces near-zero ECE by construction (tautology). Score_method stratification added to expose this.
- **Expected**: Tautology warning for heuristic; model-scored subset may be moderately calibrated

### H5: Execution Efficiency
- **Question**: Does ML-selected subset maintain detection while reducing execution time?
- **Tests**: Wilcoxon signed-rank, one-sample t-test, rank-biserial correlation
- **Expected**: Likely strongest result — practical value of ML prioritization

### H6: Discovery Coverage (Simulation Exposure)
- **Question**: Do dynamic simulation modes expose more unique vulnerability patterns?
- **Tests**: Kruskal-Wallis H, pairwise Mann-Whitney U
- **Expected**: Likely NOT supported — simulation removes services (outages, patches) rather than adding new attack surface

### H7: Cross-Framework Comparison
- **Question**: Does framework choice affect detection rate?
- **Tests**: Kruskal-Wallis H, pairwise Mann-Whitney with Bonferroni, rank-biserial r
- **Expected**: No significant differences in noisy modes; mode effect dominates (high eta-squared). Framework-interaction analysis added to quantify this.

### H8: Temporal Predictive Validity
- **Question**: Does the model predict unseen future iterations?
- **Tests**: Expanding-window AUC trend, mean AUC threshold
- **Expected**: Supported if features carry real signal; trending if just proxying service state

### H9: ML Value Over Baselines
- **Question**: Does ML-guided testing beat non-ML strategies?
- **Tests**: Per-baseline Mann-Whitney U, lift computation
- **Expected**: HIGH RISK — CVSS-priority is a strong IoT heuristic. ML may show only marginal lift.
- **Defense strategy**: If marginal, reframe as "characterizing when ML adds value vs doesn't"

### H10: LLM Generation Effectiveness
- **Question**: Do LLM-generated tests find additional vulnerabilities?
- **Tests**: Fisher's exact test, odds ratio with 95% CI, per-iteration Mann-Whitney
- **Expected**: May be underpowered (few LLM tests vs many registry tests). Wide CI on odds ratio.

### H11: Cross-Protocol Generalization (LOPO)
- **Question**: Does the model generalize to unseen protocols?
- **Tests**: Leave-one-protocol-out AUC, per-protocol breakdown
- **Expected**: Partial generalization (AUC 0.55–0.65). Protocol-specific patterns don't fully transfer.

---

## Analysis Layer Enhancements (completed)

### Backend endpoints added/modified (dashboard/backend/main.py)
1. **H4 score_method stratification**: ECE/Brier computed separately for model-scored vs heuristic-scored rows. Tautology warning when heuristic ECE < 0.03.
2. **H7 framework-interaction**: `GET /api/hypothesis/framework-interaction` — two-way eta-squared decomposition (framework × mode), per-mode significance.
3. **H10 LLM effectiveness**: `GET /api/hypothesis/llm-effectiveness` — Fisher's exact test, odds ratio, 95% CI, per-iteration Mann-Whitney.
4. **Multiple comparison correction**: Holm-Bonferroni applied in synthesis endpoint. Corrected p-values and family-wise alpha reported.
5. **Ablation analysis**: `GET /api/hypothesis/ablation` — classifies experiments into conditions (no_ml, random, cvss, ml, ml+llm), computes marginal lifts. Requires baseline data.
6. **Baseline strategy tagging**: `_execute_suite_and_retrain` now writes `baseline_strategy` to history CSV alongside `automl_tool`.
7. **Score method in iter_metrics**: `score_method` recorded per iteration for temporal analysis.

### Frontend updates (dashboard/frontend/src/components/Hypothesis.jsx)
- H4: Score method comparison panel with tautology warning
- H7: Framework-interaction analysis section
- H10: Dedicated LLM effectiveness section with Fisher's test results
- Synthesis: Corrected p-value column, Holm-Bonferroni footnote
- Ablation: New section with marginal contribution table
- Removed: "Strategy Comparison (H2 Stats)" section (redundant with H2 proper)

---

## Known Issues & Risks

### Critical
- **Thin feature set**: Port, protocol, auth_required, is_common_port — ML may just be memorizing protocol-vulnerability correlations. LOPO AUC will confirm.
- **Closed-world evaluation**: 13 Docker containers with planted vulns. External validity is limited.
- **H9 is the thesis core risk**: If CVSS-priority performs within 10% of ML, the ML complexity argument weakens.

### Methodological
- **H6 structural issue**: Simulation removes services, doesn't add attack surface. Hypothesis may be poorly framed.
- **H10 statistical power**: Few LLM tests relative to registry. Consider increasing `llm_generate_every_n` frequency if results are underpowered.
- **Heuristic tautology in H4**: ECE near-zero by construction for heuristic scoring. Now flagged but still present in data.

### Technical
- **PC crash during experiments**: Runner crashed at H2O/medium iteration 78. `--resume` flag added to `run_experiments.py` to handle this.
- **No partial iteration resume**: API doesn't support `start_iteration`. Incomplete experiments must be deleted and re-run from scratch.

---

## Experiment Runner Features

### CLI flags
```bash
python run_experiments.py              # Full run (clears all data first)
python run_experiments.py --resume     # Resume from last completed experiment
python run_experiments.py --quick      # 5 iterations instead of 100
python run_experiments.py --skip-baselines
python run_experiments.py --skip-llm
python run_experiments.py --skip-lopo
python run_experiments.py --only-baselines
python run_experiments.py --only-llm
```

### --resume behavior
1. Scans `experiments/exp_*/history.csv` to find completed (tool, mode, phase) combos
2. Deletes empty/crashed dirs (0 data rows)
3. Deletes ALL dirs for incomplete combos (re-run from scratch)
4. Resets IoT containers to fresh state
5. Skips completed combos, runs remaining experiments

---

## Defense Preparation

### Strongest arguments
1. **Methodological rigor**: Holm-Bonferroni correction, temporal validation, LOPO, ablation — exceeds most ML-in-security papers
2. **Simulation framework**: Reproducible IoT testbed with environmental dynamics is a standalone contribution
3. **Multi-framework comparison**: 5 AutoML frameworks under identical conditions is valuable empirical work
4. **Clean ablation design**: Random → CVSS → Round-Robin → ML → ML+LLM ladder

### Prepare defense narratives for
- H9 marginal lift: "Rigorous characterization of when ML adds value is itself the contribution"
- H6 not supported: "We tested whether environmental dynamism helps discovery — finding it doesn't informs future testbed design"
- H4 tautology: "We detected and flagged the tautology, demonstrating methodological awareness"
- Thin feature set: "Feature engineering for IoT security testing is inherently constrained; our LOPO analysis quantifies the limitation"

---

## Prior Completed Work

### LLM Integration (completed before experiments)
- Wired `llm_enabled` from dead code to full system integration
- Fixed `test_strategy` derivation (was hardcoded, now derived from `test_origin`)
- Added coverage gap detection + targeted LLM generation
- Multi-framework LLM experiments (was H2O-only)
- Dashboard UI toggle for LLM generation
- See git history for details

### Multi-LLM Provider Architecture (completed)
- Abstract base class + provider registry pattern
- Claude (tool use), OpenAI (function calling), Gemini (JSON mode)
- Provider-agnostic `LLMTestGenerator` with dashboard dropdown selection
