"""Compute all H1-H11 hypothesis statistics from emergence.db for documentation."""
import os
from pathlib import Path

# Run from the repository root so relative data paths resolve on any machine.
os.chdir(Path(__file__).resolve().parents[1])
import duckdb
import json
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from sklearn.metrics import roc_auc_score, brier_score_loss

DB = "experiments/emergence.db"

def load(where_sql: str) -> pd.DataFrame:
    con = duckdb.connect(DB, read_only=True)
    try:
        return con.execute(f"SELECT * FROM history WHERE {where_sql}").df()
    finally:
        con.close()

def heuristic_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Leave-iteration-out empirical base rate with Bayesian smoothing (mimics _heuristic_risk_scores)."""
    df = df.copy()
    if "simulation_iteration" not in df.columns:
        df["simulation_iteration"] = 0
    df["key"] = df["protocol"].astype(str) + "|" + df["test_type"].astype(str)
    # global rate
    g_vulns = df["vulnerability_found"].sum()
    g_total = len(df)
    global_rate = (g_vulns + 5) / (g_total + 10) if g_total else 0.5
    # per-key loo rate
    grp = df.groupby("key")["vulnerability_found"].agg(["sum","count"]).reset_index()
    grp.columns = ["key","k_sum","k_n"]
    df = df.merge(grp, on="key", how="left")
    df["predicted_risk_score"] = (df["k_sum"] - df["vulnerability_found"] + 5) / (df["k_n"] - 1 + 10)
    df.loc[df["k_n"] <= 1, "predicted_risk_score"] = global_rate
    df["_score_method"] = "heuristic"
    return df

def iter_metrics(df: pd.DataFrame) -> list:
    """Per-iteration detection rate, new vulns."""
    seen = set()
    iters = []
    for it, g in df.groupby("simulation_iteration"):
        n = len(g); v = int(g["vulnerability_found"].sum())
        vuln_rows = g[g["vulnerability_found"]==1]
        key_col = "test_id" if "test_id" in g.columns else "test_type"
        uniq = set(vuln_rows[key_col].dropna().unique())
        new_vulns = len(uniq - seen)
        seen |= uniq
        iters.append({
            "iteration": int(it), "n_tests": n, "n_vulns": v,
            "detection_rate": v/n if n else 0,
            "new_vulns": new_vulns,
            "cumulative_unique_vulns": len(seen),
        })
    return iters


def h1_stability(mode: str, tool: str):
    df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{tool}' AND simulation_seed='42'")
    its = iter_metrics(df)
    rates = [it["detection_rate"] for it in its]
    n = len(rates)
    x = list(range(1, n+1))
    sr, sp = scipy_stats.spearmanr(x, rates)
    pr, pp = scipy_stats.pearsonr(x, rates)
    mid = n // 2
    early = np.array(rates[:mid]); late = np.array(rates[mid:])
    u, mp = scipy_stats.mannwhitneyu(late, early, alternative="greater")
    pooled = float(np.sqrt((early.std()**2 + late.std()**2) / 2))
    d = float((late.mean() - early.mean()) / pooled) if pooled else 0
    improvement = float(late.mean() - early.mean())
    se = float(np.sqrt(early.var()/len(early) + late.var()/len(late)))
    return {
        "mode": mode, "tool": tool, "n_iterations": n,
        "spearman_rho": round(float(sr),4), "spearman_p": round(float(sp),6),
        "pearson_r": round(float(pr),4), "pearson_p": round(float(pp),6),
        "mann_whitney_u": round(float(u),2), "mann_whitney_p": round(float(mp),6),
        "early_mean": round(float(early.mean()),4), "late_mean": round(float(late.mean()),4),
        "cohens_d": round(d,4),
        "improvement": round(improvement,4),
        "ci_95": [round(improvement-1.96*se,4), round(improvement+1.96*se,4)],
    }


def h2_recommendation(mode: str, tool: str):
    df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{tool}'")
    df = heuristic_scores(df)
    total = len(df); total_vulns = int(df["vulnerability_found"].sum())
    rec = df[df["predicted_risk_score"] >= 0.5]
    non_rec = df[df["predicted_risk_score"] < 0.5]
    rec_n = len(rec); rec_v = int(rec["vulnerability_found"].sum())
    non_n = len(non_rec); non_v = int(non_rec["vulnerability_found"].sum())
    rec_rate = rec_v/rec_n if rec_n else 0
    non_rate = non_v/non_n if non_n else 0
    overall = total_vulns/total if total else 0
    lift = rec_rate / overall if overall else 0
    table = [[rec_v, rec_n-rec_v],[non_v, non_n-non_v]]
    try:
        _, fp = scipy_stats.fisher_exact(table)
    except Exception:
        fp = None
    return {
        "mode": mode, "tool": tool,
        "total": total, "overall_rate": round(overall,4),
        "rec_n": rec_n, "rec_v": rec_v, "rec_rate": round(rec_rate,4),
        "non_rec_n": non_n, "non_rec_v": non_v, "non_rec_rate": round(non_rate,4),
        "lift": round(lift,4), "fisher_p": float(fp) if fp is not None else None,
    }


def h3_convergence(mode: str, tool: str):
    df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{tool}' AND simulation_seed='42'")
    per = (df.groupby(["simulation_iteration","protocol"])["vulnerability_found"]
             .agg(total="count", vulns="sum").reset_index())
    per["rate"] = per["vulns"]/per["total"]
    protos = sorted(per["protocol"].dropna().unique())
    results = []
    for p in protos:
        pr = per[per["protocol"]==p].sort_values("simulation_iteration")
        ind = pr["simulation_iteration"].tolist()
        rates = pr["rate"].tolist()
        if len(rates) < 3 or np.std(rates)==0:
            results.append({"protocol": p, "slope": None, "p": None, "first": rates[0] if rates else None, "last": rates[-1] if rates else None, "mean": float(np.mean(rates)) if rates else None, "status": "stable"})
            continue
        slope, inter, r, p_v, se = scipy_stats.linregress(ind, rates)
        sr, sp = scipy_stats.spearmanr(ind, rates)
        status = "converging" if slope > 0.001 and p_v < 0.1 else "diverging" if slope < -0.001 and p_v < 0.1 else "stable"
        results.append({"protocol": p, "slope": round(float(slope),6), "p": round(float(p_v),6),
                        "spearman_rho": round(float(sr),4), "spearman_p": round(float(sp),6),
                        "first": round(float(rates[0]),4), "last": round(float(rates[-1]),4),
                        "mean": round(float(np.mean(rates)),4), "status": status})

    # variance reduction
    per_iter_var = per.groupby("simulation_iteration")["rate"].var().dropna()
    n = len(per_iter_var)
    mid = n//2
    early_vars = per_iter_var.iloc[:mid].values
    late_vars = per_iter_var.iloc[mid:].values
    u, p_val = scipy_stats.mannwhitneyu(late_vars, early_vars, alternative="less")
    e_mean = float(np.mean(early_vars)); l_mean = float(np.mean(late_vars))
    var_red = (e_mean - l_mean) / e_mean * 100 if e_mean > 0 else 0
    return {
        "mode": mode, "tool": tool, "protocols": results,
        "n_converging": sum(1 for x in results if x["status"]=="converging"),
        "n_stable": sum(1 for x in results if x["status"]=="stable"),
        "n_diverging": sum(1 for x in results if x["status"]=="diverging"),
        "variance_u": round(float(u),4), "variance_p": round(float(p_val),6),
        "early_var": round(e_mean,6), "late_var": round(l_mean,6),
        "var_reduction_pct": round(var_red,2),
    }


def h4_calibration(mode: str, tool: str):
    df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{tool}'")
    df = heuristic_scores(df)
    total = len(df)
    y_true = df["vulnerability_found"].values.astype(int)
    y_score = df["predicted_risk_score"].values.astype(float)
    bins = np.linspace(0,1,11)
    ece = 0.0; mce = 0.0; curve = []
    for i in range(10):
        lo,hi = bins[i], bins[i+1]
        mask = (y_score >= lo) & (y_score < hi if i<9 else y_score <= hi)
        n = int(mask.sum())
        if n==0:
            curve.append({"bin":[round(lo,1),round(hi,1)], "n":0, "pred":round((lo+hi)/2,4), "obs":0})
            continue
        pm = float(y_score[mask].mean()); om = float(y_true[mask].mean())
        gap = abs(pm - om)
        ece += (n/total) * gap
        mce = max(mce, gap)
        curve.append({"bin":[round(lo,1),round(hi,1)], "n":n, "pred":round(pm,4), "obs":round(om,4)})
    brier = float(brier_score_loss(y_true, y_score))
    return {"mode": mode, "tool": tool, "n": total, "ece": round(ece,4), "mce": round(mce,4),
            "brier": round(brier,4), "curve": curve, "score_method": "heuristic"}


def h5_efficiency(mode: str, tool: str):
    """H5 uses scored df at recommendation threshold 0.5 as proxy for efficiency."""
    df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{tool}' AND simulation_seed='42'")
    df = heuristic_scores(df)
    df["is_rec"] = (df["predicted_risk_score"] >= 0.5).astype(int)
    per_iter = []
    for it, g in df.groupby("simulation_iteration"):
        total = len(g); rec = int(g["is_rec"].sum())
        v_total = int(g["vulnerability_found"].sum())
        v_rec = int(g[g["is_rec"]==1]["vulnerability_found"].sum())
        if rec == 0: continue
        frac = rec/total
        cov = (v_rec/v_total*100) if v_total else 100.0
        eff = (cov/100)/frac if frac>0 else 0
        per_iter.append({"iter": int(it), "rec_frac": frac, "cov_pct": cov, "eff": eff, "reduction": (1-frac)*100})
    eff_ratios = [p["eff"] for p in per_iter]
    coverages = [p["cov_pct"] for p in per_iter]
    reductions = [p["reduction"] for p in per_iter]
    if len(eff_ratios) < 3:
        return {"mode": mode, "tool": tool, "n": len(eff_ratios), "insufficient": True}
    shifted = [r-1.0 for r in eff_ratios]
    try:
        w, wp = scipy_stats.wilcoxon(shifted, alternative="greater")
    except ValueError:
        w, wp = 0.0, 1.0
    shifted_cov = [c-80.0 for c in coverages]
    t, tp = scipy_stats.ttest_1samp(shifted_cov, 0, alternative="greater")
    # rank-biserial
    nz = [s for s in shifted if s != 0]
    trs = len(nz)*(len(nz)+1)/2
    rr = float((w - (trs-w))/trs) if trs>0 else 0
    return {
        "mode": mode, "tool": tool, "n": len(eff_ratios),
        "avg_reduction_pct": round(float(np.mean(reductions)),2),
        "avg_coverage_pct": round(float(np.mean(coverages)),2),
        "avg_efficiency_ratio": round(float(np.mean(eff_ratios)),3),
        "wilcoxon_w": round(float(w),2), "wilcoxon_p": round(float(wp),6),
        "coverage_t": round(float(t),4), "coverage_p": round(float(tp),6),
        "rank_biserial_r": round(rr,4),
    }


def h6_discovery(tool: str):
    modes = ["deterministic","medium","realistic"]
    mode_data = {}
    for m in modes:
        df = load(f"phase='framework' AND simulation_mode='{m}' AND automl_tool='{tool}' AND simulation_seed='42'")
        its = iter_metrics(df)
        nv = [it["new_vulns"] for it in its]
        total_u = its[-1]["cumulative_unique_vulns"] if its else 0
        last = max((i+1 for i,v in enumerate(nv) if v>0), default=0)
        mode_data[m] = {"new_vulns": nv, "total_unique": total_u, "n_iters": len(its),
                        "last_discovery": last, "mean_new": float(np.mean(nv)) if nv else 0}
    baseline = "deterministic"
    base_u = mode_data[baseline]["total_unique"]
    for m in modes:
        if m == baseline:
            mode_data[m]["lift"] = 0
        else:
            mode_data[m]["lift"] = (mode_data[m]["total_unique"] - base_u)/base_u*100 if base_u else 0

    groups = [mode_data[m]["new_vulns"] for m in modes]
    h, kp = scipy_stats.kruskal(*groups)
    pairwise = []
    n_pairs = 3
    for i in range(len(modes)):
        for j in range(i+1, len(modes)):
            a, b = modes[i], modes[j]
            ga = mode_data[a]["new_vulns"]; gb = mode_data[b]["new_vulns"]
            u, p = scipy_stats.mannwhitneyu(gb, ga, alternative="greater")
            pc = min(p*n_pairs, 1.0)
            pairwise.append({"a": a, "b": b, "u": round(float(u),2), "p": round(float(p),6),
                             "p_corrected": round(float(pc),6), "sig": bool(pc<0.05)})
    return {"tool": tool, "modes": {m: {k:v for k,v in d.items() if k!="new_vulns"} for m,d in mode_data.items()},
            "kruskal_h": round(float(h),4), "kruskal_p": round(float(kp),6),
            "pairwise": pairwise}


def h7_cross_framework(mode: str):
    fws = ["h2o","autogluon","pycaret","tpot","autosklearn"]
    seed_filter = "AND simulation_seed='42'" if mode != "realistic" else ""
    fw_data = {}
    for fw in fws:
        df = load(f"phase='framework' AND simulation_mode='{mode}' AND automl_tool='{fw}' {seed_filter}")
        if df.empty: continue
        # per-iteration detection rates
        pe = df.groupby("simulation_iteration")["vulnerability_found"].agg(total="count", vulns="sum").reset_index()
        rates = (pe["vulns"]/pe["total"]).fillna(0).tolist()
        # AUC via heuristic on whole frame
        sdf = heuristic_scores(df)
        yt = sdf["vulnerability_found"].values.astype(int)
        ys = sdf["predicted_risk_score"].values.astype(float)
        auc = float(roc_auc_score(yt, ys)) if len(np.unique(yt))>=2 else None
        fw_data[fw] = {
            "n_iters": len(rates),
            "mean_rate": float(np.mean(rates)),
            "std_rate": float(np.std(rates)),
            "auc": auc,
            "rates": rates,
        }
    groups = [fw_data[fw]["rates"] for fw in fw_data]
    h, p = scipy_stats.kruskal(*groups)
    pairs = []
    fw_names = list(fw_data.keys())
    n_comp = len(fw_names)*(len(fw_names)-1)//2
    for i in range(len(fw_names)):
        for j in range(i+1, len(fw_names)):
            a, b = fw_names[i], fw_names[j]
            ga, gb = fw_data[a]["rates"], fw_data[b]["rates"]
            u, p_ = scipy_stats.mannwhitneyu(ga, gb, alternative="two-sided")
            bp = min(p_*n_comp, 1.0)
            n1,n2 = len(ga), len(gb)
            rb = 1 - (2*u)/(n1*n2) if n1*n2>0 else 0
            pairs.append({"a":a,"b":b,"u":round(float(u),2),"p":round(float(p_),6),
                          "bonf_p":round(float(bp),6),"sig_corr":bool(bp<0.05),
                          "rank_biserial":round(float(rb),4)})
    return {"mode": mode, "frameworks": {fw: {k:v for k,v in d.items() if k!="rates"} for fw,d in fw_data.items()},
            "kruskal_h": round(float(h),4), "kruskal_p": round(float(p),6),
            "pairwise": pairs}


def h7_interaction():
    fws = ["h2o","autogluon","pycaret","tpot","autosklearn"]
    modes = ["deterministic","medium","realistic"]
    rows = []
    for fw in fws:
        for m in modes:
            seed_filter = "AND simulation_seed='42'" if m != "realistic" else ""
            df = load(f"phase='framework' AND simulation_mode='{m}' AND automl_tool='{fw}' {seed_filter}")
            if df.empty: continue
            pe = df.groupby("simulation_iteration")["vulnerability_found"].agg(total="count", vulns="sum").reset_index()
            for _, r in pe.iterrows():
                rows.append({"fw": fw, "mode": m, "it": int(r["simulation_iteration"]),
                             "rate": float(r["vulns"])/float(r["total"]) if r["total"] else 0})
    df_all = pd.DataFrame(rows)
    y = df_all["rate"].values
    gm = float(np.mean(y))
    ss_total = float(np.sum((y-gm)**2))
    fw_means = df_all.groupby("fw")["rate"].mean()
    mode_means = df_all.groupby("mode")["rate"].mean()
    ss_fw = sum(len(df_all[df_all["fw"]==f]) * (fw_means[f]-gm)**2 for f in fw_means.index)
    ss_mode = sum(len(df_all[df_all["mode"]==m]) * (mode_means[m]-gm)**2 for m in mode_means.index)
    cell_means = df_all.groupby(["fw","mode"])["rate"].mean()
    ss_int = 0
    for f in fw_means.index:
        for m in mode_means.index:
            if (f,m) not in cell_means.index: continue
            n = len(df_all[(df_all["fw"]==f)&(df_all["mode"]==m)])
            exp = fw_means[f] + mode_means[m] - gm
            ss_int += n * (cell_means[(f,m)] - exp)**2
    ss_res = max(ss_total - ss_fw - ss_mode - ss_int, 0)
    # Per-mode kruskal
    per_mode = {}
    for m in modes:
        g = [df_all[(df_all["mode"]==m)&(df_all["fw"]==f)]["rate"].values for f in fw_means.index]
        g = [x for x in g if len(x)>=2]
        if len(g)>=2:
            h_, p_ = scipy_stats.kruskal(*g)
            per_mode[m] = {"kruskal_h": round(float(h_),4), "p": round(float(p_),6), "sig": bool(p_<0.05)}
    return {
        "ss_total": round(ss_total,4),
        "eta_fw": round(ss_fw/ss_total,4) if ss_total else 0,
        "eta_mode": round(ss_mode/ss_total,4) if ss_total else 0,
        "eta_interaction": round(ss_int/ss_total,4) if ss_total else 0,
        "eta_residual": round(ss_res/ss_total,4) if ss_total else 0,
        "grand_mean": round(gm,4),
        "per_mode_kruskal": per_mode,
        "n_obs": len(df_all),
    }


def h9_baselines(mode: str):
    seeds = "AND simulation_seed='42'"
    all_df = load(f"simulation_mode='{mode}' {seeds}")
    all_df["baseline_strategy"] = all_df["baseline_strategy"].fillna("ml_guided")
    # ml_guided h2o only to match baseline iteration counts
    ml_filter = (all_df["baseline_strategy"]=="ml_guided") & (all_df["automl_tool"]=="h2o") & (all_df["phase"]=="framework")
    others = all_df["baseline_strategy"].isin(["random","round_robin","cvss_priority","no_ml"])
    dff = all_df[ml_filter | others].copy()
    strategies = {}
    for s in dff["baseline_strategy"].unique():
        sub = dff[dff["baseline_strategy"]==s]
        pe = sub.groupby("simulation_iteration")["vulnerability_found"].agg(total="count",vulns="sum").reset_index()
        rates = (pe["vulns"]/pe["total"]).fillna(0).tolist()
        strategies[s] = {
            "rates": rates,
            "n_iters": len(rates),
            "mean": float(np.mean(rates)) if rates else 0,
            "std": float(np.std(rates)) if rates else 0,
            "total_tests": len(sub),
            "total_vulns": int(sub["vulnerability_found"].sum()),
        }
    ml = strategies.get("ml_guided",{})
    comparisons = {}
    for s, d in strategies.items():
        if s == "ml_guided": continue
        if ml.get("rates") and d["rates"]:
            u, p = scipy_stats.mannwhitneyu(ml["rates"], d["rates"], alternative="greater")
            n1,n2 = len(ml["rates"]), len(d["rates"])
            rb = 1-(2*u)/(n1*n2) if n1*n2 else 0
            lift = (ml["mean"]-d["mean"])/d["mean"]*100 if d["mean"] else 0
            comparisons[s] = {"u":round(float(u),2),"p":round(float(p),6),"sig":bool(p<0.05),
                              "rank_biserial":round(float(rb),4),"lift_pct":round(float(lift),2)}
    return {"mode": mode,
            "strategies": {s:{k:v for k,v in d.items() if k!="rates"} for s,d in strategies.items()},
            "comparisons": comparisons}


def h10_llm(mode: str, tool: str):
    df = load(f"phase='llm' AND simulation_mode='{mode}' AND automl_tool='{tool}'")
    llm_df = df[df["test_strategy"]=="llm_generated"]
    reg_df = df[df["test_strategy"]=="generated"]
    llm_v = int(llm_df["vulnerability_found"].sum()); llm_n = len(llm_df)
    reg_v = int(reg_df["vulnerability_found"].sum()); reg_n = len(reg_df)
    llm_rate = llm_v/llm_n if llm_n else 0
    reg_rate = reg_v/reg_n if reg_n else 0
    a,b = llm_v, llm_n-llm_v; c,d = reg_v, reg_n-reg_v
    table = [[a,b],[c,d]]
    oratio, fp = scipy_stats.fisher_exact(table)
    # CI
    log_or = np.log(oratio) if oratio>0 else None
    ci = None
    if log_or is not None and all(x>0 for x in [a,b,c,d]):
        se = np.sqrt(1/a+1/b+1/c+1/d)
        ci = [round(float(np.exp(log_or-1.96*se)),4), round(float(np.exp(log_or+1.96*se)),4)]
    # per-iteration Mann-Whitney
    llm_pi = llm_df.groupby("simulation_iteration")["vulnerability_found"].mean().dropna().values
    reg_pi = reg_df.groupby("simulation_iteration")["vulnerability_found"].mean().dropna().values
    mw = None
    if len(llm_pi)>=3 and len(reg_pi)>=3:
        u, p = scipy_stats.mannwhitneyu(llm_pi, reg_pi, alternative="two-sided")
        n1,n2 = len(llm_pi), len(reg_pi)
        rb = 1-(2*u)/(n1*n2) if n1*n2 else 0
        mw = {"u":round(float(u),2),"p":round(float(p),6),"sig":bool(p<0.05),"rank_biserial":round(float(rb),4)}
    # unique scenarios
    llm_v_rows = llm_df[llm_df["vulnerability_found"]==1]
    reg_v_rows = reg_df[reg_df["vulnerability_found"]==1]
    llm_ids = set(llm_v_rows["test_id"].unique())
    reg_ids = set(reg_v_rows["test_id"].unique())
    exclusive = llm_ids - reg_ids
    return {"mode": mode, "tool": tool,
            "llm": {"n":llm_n,"v":llm_v,"rate":round(llm_rate,4),"n_unique_scen":len(llm_ids)},
            "reg": {"n":reg_n,"v":reg_v,"rate":round(reg_rate,4),"n_unique_scen":len(reg_ids)},
            "odds_ratio": round(float(oratio),4), "fisher_p": round(float(fp),6),
            "or_ci_95": ci, "exclusive_scenarios": len(exclusive),
            "mann_whitney": mw}


def h_dynamic_2x2(mode: str, tool: str):
    phases = ["framework","llm","phase5","phase6"]
    data = {}
    for ph in phases:
        df = load(f"phase='{ph}' AND simulation_mode='{mode}' AND automl_tool='{tool}'")
        if df.empty:
            data[ph] = None; continue
        mean_det = float(df["vulnerability_found"].mean())
        data[ph] = {"n": len(df), "v": int(df["vulnerability_found"].sum()), "mean": round(mean_det,4)}
    p1 = data["framework"]["mean"] if data["framework"] else None
    p3 = data["llm"]["mean"] if data["llm"] else None
    p5 = data["phase5"]["mean"] if data["phase5"] else None
    p6 = data["phase6"]["mean"] if data["phase6"] else None
    dyn_main = ((p5+p6)/2 - (p1+p3)/2) if all(v is not None for v in [p1,p3,p5,p6]) else None
    llm_main = ((p3+p6)/2 - (p1+p5)/2) if all(v is not None for v in [p1,p3,p5,p6]) else None
    inter = ((p6-p5) - (p3-p1)) if all(v is not None for v in [p1,p3,p5,p6]) else None
    return {"mode":mode,"tool":tool,"phases":data,
            "p1_static_noLLM":p1,"p3_static_LLM":p3,"p5_dyn_noLLM":p5,"p6_dyn_LLM":p6,
            "dynamic_main":round(dyn_main,4) if dyn_main is not None else None,
            "llm_main":round(llm_main,4) if llm_main is not None else None,
            "interaction":round(inter,4) if inter is not None else None}


def ablation(mode: str):
    all_df = load(f"simulation_mode='{mode}' AND simulation_seed='42'")
    all_df["baseline_strategy"] = all_df["baseline_strategy"].fillna("ml_guided")
    # Filter ml_guided to h2o only
    mask = (all_df["baseline_strategy"]=="ml_guided") & (all_df["automl_tool"]!="h2o")
    all_df = all_df[~mask]
    conditions = []
    def add(label, key, df_):
        if df_.empty: return
        pe = df_.groupby("exp_dir_name")["vulnerability_found"].agg(total="count",vulns="sum").reset_index()
        rates = (pe["vulns"]/pe["total"]).tolist()
        n_iters = len(pe)
        n_tests = len(df_)
        n_vulns = int(df_["vulnerability_found"].sum())
        det_rate = n_vulns/n_tests if n_tests else 0
        std = float(np.std(rates)) if rates else 0
        uniq = int(df_[df_["vulnerability_found"]==1]["test_id"].nunique())
        conditions.append({"label":label, "key":key,
                           "n_tests_per_iter":round(n_tests/n_iters),
                           "n_vulns_per_iter":round(n_vulns/n_iters,1),
                           "detection_rate":round(det_rate,4),
                           "std_rate":round(std,4),
                           "n_iterations":n_iters,
                           "unique_vuln_types":uniq})
    add("Random", "random", all_df[all_df["baseline_strategy"]=="random"])
    add("Round-Robin", "round_robin", all_df[all_df["baseline_strategy"]=="round_robin"])
    add("CVSS Priority", "cvss_priority", all_df[all_df["baseline_strategy"]=="cvss_priority"])
    ml_df = all_df[(all_df["baseline_strategy"]=="ml_guided") & (all_df["phase"]=="framework") & (all_df["automl_tool"]=="h2o")]
    add("ML-Guided", "ml_guided", ml_df)
    ml_llm = all_df[(all_df["baseline_strategy"]=="ml_guided") & (all_df["phase"]=="llm") & (all_df["automl_tool"]=="h2o")]
    add("ML + LLM", "ml_llm", ml_llm)
    add("No Prioritisation (All)", "no_ml", all_df[all_df["baseline_strategy"]=="no_ml"])
    p5 = load(f"phase='phase5' AND simulation_mode='{mode}' AND automl_tool='h2o'")
    add("ML-Dynamic (Phase 5)", "phase5", p5)
    p6 = load(f"phase='phase6' AND simulation_mode='{mode}' AND automl_tool='autogluon'")  # Phase 6 = autogluon
    add("ML-Dynamic + LLM (Phase 6)", "phase6", p6)
    for i in range(1, len(conditions)):
        prev = conditions[i-1]["detection_rate"]; curr = conditions[i]["detection_rate"]
        lift = (curr-prev)/prev*100 if prev else 0
        conditions[i]["marginal_lift_pct"] = round(lift,2)
    if conditions: conditions[0]["marginal_lift_pct"] = 0
    return {"mode":mode, "conditions":conditions}


def main():
    results = {}
    for mode in ["deterministic","medium","realistic"]:
        print(f"\n=== Mode: {mode} ===")
        results[mode] = {}
        results[mode]["H1"] = h1_stability(mode, "h2o")
        print("H1:", results[mode]["H1"])
        results[mode]["H2"] = h2_recommendation(mode, "h2o")
        print("H2:", results[mode]["H2"])
        results[mode]["H3"] = h3_convergence(mode, "h2o")
        print("H3:", json.dumps(results[mode]["H3"], indent=1)[:500])
        results[mode]["H4"] = h4_calibration(mode, "h2o")
        print("H4 ECE:", results[mode]["H4"]["ece"], "Brier:", results[mode]["H4"]["brier"])
        results[mode]["H5"] = h5_efficiency(mode, "h2o")
        print("H5:", results[mode]["H5"])
        results[mode]["H7"] = h7_cross_framework(mode)
        print("H7:", json.dumps(results[mode]["H7"], indent=1)[:500])
        try:
            results[mode]["H9"] = h9_baselines(mode)
            print("H9:", json.dumps(results[mode]["H9"], indent=1)[:500])
        except Exception as e:
            print("H9 error", e)
        try:
            results[mode]["H10"] = h10_llm(mode, "h2o")
            print("H10:", json.dumps(results[mode]["H10"], indent=1)[:500])
        except Exception as e:
            print("H10 error", e)
        try:
            results[mode]["DYNAMIC"] = h_dynamic_2x2(mode, "h2o")
            print("Dynamic:", results[mode]["DYNAMIC"])
        except Exception as e:
            print("Dyn error", e)
        try:
            results[mode]["ABLATION"] = ablation(mode)
            print("Ablation n_cond:", len(results[mode]["ABLATION"]["conditions"]))
        except Exception as e:
            print("Ablation error", e)
    results["H6"] = h6_discovery("h2o")
    print("H6:", json.dumps(results["H6"], indent=1)[:500])
    results["H7_interaction"] = h7_interaction()
    print("H7_int:", results["H7_interaction"])

    with open("hypothesis_results.json","w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nWrote hypothesis_results.json")

if __name__ == "__main__":
    main()
