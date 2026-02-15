import os
import math
import docker
import json
import time
import threading
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Emergence - IoT Vulnerability Dashboard API")

# CORS liberado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_client = docker.from_env()

EXPERIMENTS_PATH = "/app/experiments"
SCANNER_CONTAINER_NAME = "scanner"

# ---------------------------------------------------------------------------
# In-memory experiment state tracking
# ---------------------------------------------------------------------------
_experiment_state = {
    "status": "idle",        # idle | running | completed | error
    "command": "",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "experiment_id": None,
}
_state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory batch experiment state tracking
# ---------------------------------------------------------------------------
_batch_state = {
    "status": "idle",           # idle | running | completed | error
    "total_runs": 0,
    "completed_runs": 0,
    "current_run": 0,
    "mode": "automl",
    "network": "172.20.0.0/27",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "experiment_ids": [],
}
_batch_lock = threading.Lock()


class ExperimentRequest(BaseModel):
    mode: str
    network: str = "172.20.0.0/27"
    extra_args: list[str] = []


class BatchRequest(BaseModel):
    mode: str = "automl"
    network: str = "172.20.0.0/27"
    runs: int = 30


@app.get("/")
def root():
    return {"status": "ok", "message": "Dashboard API online"}


@app.get("/experiments")
def list_experiments():
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"experiments": []}
    exps = [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    return {"experiments": sorted(exps, reverse=True)}


@app.get("/logs")
def get_logs(tail: int = 80, filter: Optional[str] = None):
    """
    Retorna os logs recentes de todos os containers Docker ativos
    (para o dashboard exibir em tempo real).
    Accepts optional `tail` (number of lines) and `filter` (container name substring).
    """
    try:
        containers = docker_client.containers.list()
        logs_data = {}
        container_info = []

        for c in containers:
            name = c.name
            if filter and filter.lower() not in name.lower():
                continue
            try:
                raw = c.logs(tail=tail, timestamps=True).decode(errors="ignore")
                logs_data[name] = raw
            except Exception as e:
                logs_data[name] = f"[Erro ao ler logs: {e}]"

            # Gather container metadata
            try:
                container_info.append({
                    "name": name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
                })
            except Exception:
                container_info.append({"name": name, "status": "unknown", "image": ""})

        return {
            "containers": sorted([ci["name"] for ci in container_info]),
            "container_info": sorted(container_info, key=lambda x: x["name"]),
            "logs": logs_data,
        }

    except Exception as e:
        return {"error": str(e)}


@app.post("/experiments/run")
def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    # Prevent concurrent experiments
    with _state_lock:
        if _experiment_state["status"] == "running":
            return {"status": "error", "message": "Um experimento já está em execução."}

    cmd_parts = ["python3", ".", "-n", req.network]
    if req.mode == "automl":
        cmd_parts.append("-aml")

    extra_args = getattr(req, "extra_args", [])
    if isinstance(extra_args, list):
        cmd_parts.extend(extra_args)

    cmd_str = " ".join(cmd_parts)

    with _state_lock:
        _experiment_state["status"] = "running"
        _experiment_state["command"] = cmd_str
        _experiment_state["started_at"] = datetime.now().isoformat()
        _experiment_state["finished_at"] = None
        _experiment_state["error"] = None
        _experiment_state["experiment_id"] = None

    def _exec():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            print(f"[API] Executando: {cmd_str}")
            # Run synchronously (not detached) so we know when it finishes
            exit_code, output = container.exec_run(cmd_str, detach=False, workdir="/app")
            with _state_lock:
                if exit_code == 0:
                    _experiment_state["status"] = "completed"
                else:
                    _experiment_state["status"] = "error"
                    _experiment_state["error"] = f"Exit code {exit_code}"
                _experiment_state["finished_at"] = datetime.now().isoformat()
                # Try to detect the experiment ID from directory listing
                try:
                    exps = sorted(
                        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
                        reverse=True,
                    )
                    if exps:
                        _experiment_state["experiment_id"] = exps[0]
                except Exception:
                    pass
        except Exception as e:
            print(f"[ERRO] Falha ao executar experimento: {e}")
            with _state_lock:
                _experiment_state["status"] = "error"
                _experiment_state["error"] = str(e)
                _experiment_state["finished_at"] = datetime.now().isoformat()

    background_tasks.add_task(_exec)
    return {"status": "started", "command": cmd_str}


@app.get("/experiments/status")
def experiment_status():
    """Return current experiment execution state for the dashboard to poll."""
    with _state_lock:
        state = dict(_experiment_state)

    # Calculate elapsed time if running
    if state["status"] == "running" and state["started_at"]:
        started = datetime.fromisoformat(state["started_at"])
        elapsed = (datetime.now() - started).total_seconds()
        state["elapsed_seconds"] = round(elapsed, 1)
    else:
        state["elapsed_seconds"] = 0

    # If running, try to get the scanner container's latest log lines for progress
    if state["status"] == "running":
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            raw = container.logs(tail=10).decode(errors="ignore")
            state["scanner_output"] = raw
        except Exception:
            state["scanner_output"] = ""
    else:
        state["scanner_output"] = ""

    return state



@app.get("/history")
def get_history():
    history = []
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"history": []}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )

    for exp in exps:
        exp_path = os.path.join(EXPERIMENTS_PATH, exp)
        for file in ["metrics_static.json", "metrics_random.json", "metrics_automl.json"]:
            path = os.path.join(exp_path, file)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                        data["experiment"] = exp
                        history.append(data)
                except:
                    pass
    return {"history": sorted(history, key=lambda x: x.get("exec_time_sec", 0), reverse=True)}


# ---------------------------------------------------------------------------
# Helper: load history.csv from one or all experiments
# ---------------------------------------------------------------------------

def _load_history_csv(experiment: Optional[str] = None) -> pd.DataFrame:
    if not os.path.exists(EXPERIMENTS_PATH):
        return pd.DataFrame()

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )
    if experiment:
        exps = [e for e in exps if e == experiment]

    frames = []
    for exp in exps:
        csv_path = os.path.join(EXPERIMENTS_PATH, exp, "history.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                df["experiment"] = exp
                frames.append(df)
            except Exception:
                pass

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of dicts, replacing NaN/inf with 0."""
    df = df.copy()
    # Convert categorical columns to strings before fillna
    for col in df.select_dtypes(include=["category"]).columns:
        df[col] = df[col].astype(str)
    df = df.fillna(0)
    df = df.replace([np.inf, -np.inf], 0)
    return df.to_dict(orient="records")


def _sanitize(obj):
    """Recursively sanitize a nested dict/list, replacing NaN/inf floats with None.
    Prevents 'Out of range float values are not JSON compliant' errors."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, (np.floating,)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return _sanitize(obj.tolist())
    return obj


# ---------------------------------------------------------------------------
# New analytics endpoints
# ---------------------------------------------------------------------------

@app.get("/history/summary")
def history_summary(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"summary": {}}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0)

    most_vuln = "N/A"
    if df["vulnerability_found"].sum() > 0:
        mode_series = df[df["vulnerability_found"] == 1]["protocol"].mode()
        if len(mode_series) > 0:
            most_vuln = mode_series.iloc[0]

    return {"summary": {
        "total_experiments": int(df["experiment"].nunique()) if "experiment" in df.columns else 0,
        "total_tests": len(df),
        "total_vulns": int(df["vulnerability_found"].sum()),
        "total_devices": int(df["container_id"].nunique()),
        "total_protocols": int(df["protocol"].nunique()),
        "detection_rate": round(float(df["vulnerability_found"].mean() * 100), 1),
        "avg_exec_time_ms": int(df["execution_time_ms"].mean()),
        "most_vulnerable_protocol": most_vuln,
    }}


@app.get("/history/vulns-by-protocol")
def vulns_by_protocol(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)

    grouped = df.groupby(["protocol", "test_strategy"]).agg(
        total_tests=("test_id", "count"),
        vulns_found=("vulnerability_found", "sum"),
    ).reset_index()

    return {"data": _safe_records(grouped)}


@app.get("/history/vulns-by-type")
def vulns_by_type(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)

    grouped = df.groupby("test_type").agg(
        total_tests=("test_id", "count"),
        vulns_found=("vulnerability_found", "sum"),
    ).reset_index()
    grouped["detection_rate"] = (grouped["vulns_found"] / grouped["total_tests"] * 100).round(1)

    return {"data": _safe_records(grouped)}


@app.get("/history/vulns-by-device")
def vulns_by_device(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0)

    grouped = df.groupby(["container_id", "protocol"]).agg(
        total_tests=("test_id", "count"),
        vulns_found=("vulnerability_found", "sum"),
        avg_exec_time=("execution_time_ms", "mean"),
    ).reset_index()
    grouped["avg_exec_time"] = grouped["avg_exec_time"].round(0).astype(int)

    return {"data": _safe_records(grouped)}


@app.get("/history/exec-time-distribution")
def exec_time_distribution(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0)

    bins = [0, 100, 500, 1000, 5000, 10000, float("inf")]
    labels = ["<100ms", "100-500ms", "500ms-1s", "1-5s", "5-10s", ">10s"]
    df["time_bucket"] = pd.cut(df["execution_time_ms"], bins=bins, labels=labels, right=False)

    grouped = df.groupby(["time_bucket", "test_strategy"], observed=True).size().reset_index(name="count")

    return {"data": _safe_records(grouped)}


@app.get("/history/cumulative-vulns")
def cumulative_vulns(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("timestamp")

    result = []
    for strategy in df["test_strategy"].unique():
        subset = df[df["test_strategy"] == strategy].reset_index(drop=True)
        subset["cumulative"] = subset["vulnerability_found"].cumsum()
        subset["test_index"] = range(1, len(subset) + 1)
        for _, row in subset.iterrows():
            result.append({
                "test_strategy": strategy,
                "test_index": int(row["test_index"]),
                "cumulative_vulns": int(row["cumulative"]),
            })

    return {"data": result}


@app.get("/history/strategy-comparison")
def strategy_comparison(experiment: Optional[str] = None):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"data": []}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0)

    grouped = df.groupby("test_strategy").agg(
        total_tests=("test_id", "count"),
        vulns_found=("vulnerability_found", "sum"),
        avg_exec_time=("execution_time_ms", "mean"),
        total_exec_time=("execution_time_ms", "sum"),
        unique_devices=("container_id", "nunique"),
        unique_protocols=("protocol", "nunique"),
    ).reset_index()

    grouped["detection_rate"] = (grouped["vulns_found"] / grouped["total_tests"] * 100).round(1)
    grouped["avg_exec_time"] = grouped["avg_exec_time"].round(0).astype(int)
    grouped["efficiency"] = (grouped["vulns_found"] / grouped["total_tests"]).round(3)

    return {"data": _safe_records(grouped)}


@app.get("/history/automl-scores")
def automl_scores(experiment: Optional[str] = None):
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"data": []}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )
    if experiment:
        exps = [e for e in exps if e == experiment]

    frames = []
    for exp in exps:
        csv_path = os.path.join(EXPERIMENTS_PATH, exp, "automl_tests.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                df["experiment"] = exp
                frames.append(df)
            except Exception:
                pass

    if not frames:
        return {"data": []}

    combined = pd.concat(frames, ignore_index=True)
    if "risk_score" in combined.columns:
        combined["risk_score"] = pd.to_numeric(combined["risk_score"], errors="coerce").fillna(0.0).round(4)
        combined = combined.sort_values("risk_score", ascending=False)

    return {"data": _safe_records(combined.head(100))}


@app.get("/history/detail")
def get_history_detail(experiment: Optional[str] = None, limit: int = 5000):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"rows": [], "total": 0}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0).astype(int)
    df["open_port"] = pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)

    rows = _safe_records(df.head(limit))
    return {"rows": rows, "total": len(df)}


# ---------------------------------------------------------------------------
# Model metrics endpoint
# ---------------------------------------------------------------------------

@app.get("/experiments/model-metrics")
def get_model_metrics():
    """Return H2O AutoML model performance metrics from all experiments."""
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"metrics": [], "aggregate": None}

    all_exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    )

    results = []
    for exp in all_exps:
        path = os.path.join(EXPERIMENTS_PATH, exp, "model_metrics.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                    data["experiment"] = exp
                    results.append(data)
            except Exception:
                pass

    # Aggregate stats across experiments
    aggregate = None
    if results:
        aucs = [r["auc"] for r in results if r.get("auc") is not None]
        if aucs:
            aggregate = {
                "n_experiments": len(results),
                "auc_mean": round(float(np.mean(aucs)), 4),
                "auc_std": round(float(np.std(aucs, ddof=1)), 4) if len(aucs) > 1 else 0.0,
                "auc_min": round(float(np.min(aucs)), 4),
                "auc_max": round(float(np.max(aucs)), 4),
            }

            # Aggregate feature importance (average across experiments)
            all_varimp = {}
            for r in results:
                for fi in r.get("feature_importance", []):
                    var = fi["variable"]
                    if var not in all_varimp:
                        all_varimp[var] = []
                    all_varimp[var].append(fi["percentage"])

            aggregate["feature_importance"] = sorted(
                [
                    {
                        "variable": var,
                        "mean_percentage": round(float(np.mean(vals)), 4),
                        "std_percentage": round(float(np.std(vals, ddof=1)), 4) if len(vals) > 1 else 0.0,
                    }
                    for var, vals in all_varimp.items()
                ],
                key=lambda x: x["mean_percentage"],
                reverse=True,
            )

            # Most common leader algorithm
            algos = [r.get("leader_algo", "unknown") for r in results]
            from collections import Counter
            algo_counts = Counter(algos)
            aggregate["most_common_algo"] = algo_counts.most_common(1)[0][0] if algo_counts else "unknown"
            aggregate["algo_distribution"] = dict(algo_counts)

            # Per-algorithm AUC comparison across ALL leaderboard entries
            algo_aucs = {}
            for r in results:
                for model in r.get("leaderboard", []):
                    model_id = model.get("model_id", "")
                    # Extract algorithm from model_id (e.g., "GBM_1_AutoML_..." → "GBM")
                    algo = model_id.split("_")[0] if model_id else "unknown"
                    if algo == "StackedEnsemble":
                        algo = "Stacked Ensemble"
                    auc_val = model.get("auc")
                    if auc_val is not None:
                        if algo not in algo_aucs:
                            algo_aucs[algo] = []
                        algo_aucs[algo].append(float(auc_val))

            aggregate["model_comparison"] = sorted(
                [
                    {
                        "algorithm": algo,
                        "n_models": len(vals),
                        "auc_mean": round(float(np.mean(vals)), 4),
                        "auc_std": round(float(np.std(vals, ddof=1)), 4) if len(vals) > 1 else 0.0,
                        "auc_min": round(float(np.min(vals)), 4),
                        "auc_max": round(float(np.max(vals)), 4),
                    }
                    for algo, vals in algo_aucs.items()
                ],
                key=lambda x: x["auc_mean"],
                reverse=True,
            )

    # Aggregate CV classification metrics across experiments
    if aggregate and results:
        cv_metrics_agg = {}
        for metric_name in ["cv_auc", "cv_precision", "cv_recall", "cv_f1"]:
            vals = [r[metric_name] for r in results if r.get(metric_name) is not None]
            if vals:
                cv_metrics_agg[metric_name] = {
                    "mean": round(float(np.mean(vals)), 4),
                    "std": round(float(np.std(vals, ddof=1)), 4) if len(vals) > 1 else 0.0,
                    "min": round(float(np.min(vals)), 4),
                    "max": round(float(np.max(vals)), 4),
                    "n": len(vals),
                }
        if cv_metrics_agg:
            aggregate["cv_classification_metrics"] = cv_metrics_agg

        # Include latest ROC curve data for visualization
        latest_roc = None
        for r in reversed(results):
            if r.get("roc_curve"):
                latest_roc = r["roc_curve"]
                break
        if latest_roc:
            aggregate["latest_roc_curve"] = latest_roc

    return _sanitize({"metrics": results, "aggregate": aggregate})


# ---------------------------------------------------------------------------
# Learning curve endpoint
# ---------------------------------------------------------------------------

@app.get("/experiments/learning-curve")
def learning_curve():
    """
    Compute cumulative statistical metrics as N experiments grow.
    Shows how p-value, effect size, and mean difference evolve over time.
    """
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"curve": []}

    all_exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    )

    # Collect all paired observations in chronological order
    pairs = []
    for exp in all_exps:
        exp_path = os.path.join(EXPERIMENTS_PATH, exp)
        static_path = os.path.join(exp_path, "metrics_static.json")
        automl_path = os.path.join(exp_path, "metrics_automl.json")
        random_path = os.path.join(exp_path, "metrics_random.json")

        if os.path.exists(static_path) and os.path.exists(automl_path):
            try:
                with open(static_path) as f:
                    s = json.load(f)
                with open(automl_path) as f:
                    a = json.load(f)
                row = {
                    "experiment": exp,
                    "static_vulns": int(s.get("vulns_detected", 0)),
                    "automl_vulns": int(a.get("vulns_detected", 0)),
                    "static_tests": int(s.get("tests_executed", 0)),
                    "automl_tests": int(a.get("tests_executed", 0)),
                    "random_vulns": None,
                }
                if os.path.exists(random_path):
                    try:
                        with open(random_path) as f:
                            r = json.load(f)
                        row["random_vulns"] = int(r.get("vulns_detected", 0))
                    except Exception:
                        pass
                pairs.append(row)
            except Exception:
                continue

    if len(pairs) < 2:
        return {"curve": []}

    # Build cumulative curve: at each N (2..len), compute stats
    curve = []
    for n in range(2, len(pairs) + 1):
        subset = pairs[:n]
        sv = np.array([p["static_vulns"] for p in subset], dtype=float)
        av = np.array([p["automl_vulns"] for p in subset], dtype=float)
        diffs = av - sv

        mean_diff = float(np.mean(diffs))
        std_diff = float(np.std(diffs, ddof=1)) if n > 1 else 0.0

        # Cohen's d
        cohens_d = mean_diff / std_diff if std_diff > 0 else 0.0

        # P-value (use appropriate test)
        p_value = 1.0
        if std_diff > 0:
            try:
                _, sw_p = scipy_stats.shapiro(diffs)
                if sw_p > 0.05:
                    _, p_two = scipy_stats.ttest_rel(av, sv)
                    t_stat = float(np.mean(diffs)) / (std_diff / np.sqrt(n))
                    p_value = float(p_two / 2) if t_stat > 0 else float(1 - p_two / 2)
                else:
                    nonzero = diffs[diffs != 0]
                    if len(nonzero) > 0:
                        _, p_value = scipy_stats.wilcoxon(nonzero, alternative="greater")
                        p_value = float(p_value)
            except Exception:
                p_value = 1.0

        # Efficiency
        st_arr = np.array([p["static_tests"] for p in subset], dtype=float)
        at_arr = np.array([p["automl_tests"] for p in subset], dtype=float)
        static_eff = float(np.mean(np.where(st_arr > 0, sv / st_arr, 0)))
        automl_eff = float(np.mean(np.where(at_arr > 0, av / at_arr, 0)))

        # AUC from model metrics if available
        auc = None
        exp_name = subset[-1]["experiment"]
        metrics_path = os.path.join(EXPERIMENTS_PATH, exp_name, "model_metrics.json")
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path) as f:
                    mm = json.load(f)
                auc = mm.get("auc")
            except Exception:
                pass

        point = {
            "n": n,
            "experiment": exp_name,
            "mean_diff": round(mean_diff, 4),
            "cohens_d": round(cohens_d, 4),
            "p_value": round(p_value, 8),
            "significant": bool(p_value < 0.05),
            "static_mean": round(float(np.mean(sv)), 2),
            "automl_mean": round(float(np.mean(av)), 2),
            "static_efficiency": round(static_eff, 4),
            "automl_efficiency": round(automl_eff, 4),
        }
        if auc is not None:
            point["model_auc"] = round(float(auc), 4)

        # Random if available
        random_subset = [p for p in subset if p["random_vulns"] is not None]
        if len(random_subset) >= 2:
            rv = np.array([p["random_vulns"] for p in random_subset], dtype=float)
            point["random_mean"] = round(float(np.mean(rv)), 2)

        curve.append(point)

    # ------- Phase 2D: Convergence Stability Analysis -------
    stability = None
    if len(curve) >= 5:
        last_5_p = [c["p_value"] for c in curve[-5:]]
        last_5_sig = [c["significant"] for c in curve[-5:]]
        last_5_d = [c["cohens_d"] for c in curve[-5:]]

        # Find first N where significance became stable (5 consecutive same direction)
        min_n_stable = None
        for i in range(4, len(curve)):
            window = [curve[j]["significant"] for j in range(i - 4, i + 1)]
            if len(set(window)) == 1:
                min_n_stable = curve[i - 4]["n"]
                break

        stability = {
            "converged": all(last_5_sig) or not any(last_5_sig),
            "last_5_p_values": [round(p, 6) for p in last_5_p],
            "p_value_range": round(max(last_5_p) - min(last_5_p), 6),
            "direction_consistent": len(set(last_5_sig)) == 1,
            "cohens_d_range": round(max(last_5_d) - min(last_5_d), 4),
            "minimum_n_for_stability": min_n_stable,
            "interpretation": (
                "Resultados convergidos e estáveis" if (all(last_5_sig) or not any(last_5_sig))
                else "Resultados ainda oscilando — mais experimentos recomendados"
            ),
            "interpretation_en": (
                "Results converged and stable" if (all(last_5_sig) or not any(last_5_sig))
                else "Results still oscillating — more experiments recommended"
            ),
        }

    return _sanitize({"curve": curve, "stability": stability})


# ---------------------------------------------------------------------------
# Batch experiment runner
# ---------------------------------------------------------------------------

@app.post("/experiments/batch")
def start_batch(req: BatchRequest, background_tasks: BackgroundTasks):
    """Run N experiments sequentially for statistical analysis."""
    with _batch_lock:
        if _batch_state["status"] == "running":
            return {"status": "error", "message": "Um lote já está em execução."}

    if req.runs < 2:
        return {"status": "error", "message": "Mínimo de 2 execuções."}

    cmd_parts = ["python3", ".", "-n", req.network]
    if req.mode == "automl":
        cmd_parts.append("-aml")
    else:
        cmd_parts.append("-t")
    cmd_str = " ".join(cmd_parts)

    with _batch_lock:
        _batch_state["status"] = "running"
        _batch_state["total_runs"] = req.runs
        _batch_state["completed_runs"] = 0
        _batch_state["current_run"] = 0
        _batch_state["mode"] = req.mode
        _batch_state["network"] = req.network
        _batch_state["started_at"] = datetime.now().isoformat()
        _batch_state["finished_at"] = None
        _batch_state["error"] = None
        _batch_state["experiment_ids"] = []

    def _exec_batch():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            # Snapshot existing experiment dirs before starting
            existing_exps = set()
            if os.path.exists(EXPERIMENTS_PATH):
                existing_exps = set(
                    f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")
                )

            for i in range(req.runs):
                with _batch_lock:
                    _batch_state["current_run"] = i + 1

                print(f"[BATCH] Executando {i + 1}/{req.runs}: {cmd_str}")
                exit_code, output = container.exec_run(
                    cmd_str, detach=False, workdir="/app"
                )

                # Detect new experiment folder
                if os.path.exists(EXPERIMENTS_PATH):
                    current_exps = set(
                        f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")
                    )
                    new_exps = current_exps - existing_exps
                    existing_exps = current_exps
                    with _batch_lock:
                        for exp_id in sorted(new_exps):
                            if exp_id not in _batch_state["experiment_ids"]:
                                _batch_state["experiment_ids"].append(exp_id)
                        _batch_state["completed_runs"] = i + 1

                if exit_code != 0:
                    print(f"[BATCH] Run {i + 1} exit code {exit_code}, continuing...")

                # Brief pause between runs
                if i < req.runs - 1:
                    time.sleep(2)

            with _batch_lock:
                _batch_state["status"] = "completed"
                _batch_state["finished_at"] = datetime.now().isoformat()

        except Exception as e:
            print(f"[BATCH ERRO] {e}")
            with _batch_lock:
                _batch_state["status"] = "error"
                _batch_state["error"] = str(e)
                _batch_state["finished_at"] = datetime.now().isoformat()

    background_tasks.add_task(_exec_batch)
    return {"status": "started", "total_runs": req.runs, "command": cmd_str}


@app.get("/experiments/batch/status")
def batch_status():
    """Return current batch execution state."""
    with _batch_lock:
        state = dict(_batch_state)
        state["experiment_ids"] = list(_batch_state["experiment_ids"])

    # Calculate elapsed time
    if state["status"] == "running" and state["started_at"]:
        started = datetime.fromisoformat(state["started_at"])
        state["elapsed_seconds"] = round(
            (datetime.now() - started).total_seconds(), 1
        )
    else:
        state["elapsed_seconds"] = 0

    # Get scanner output if currently running
    if state["status"] == "running":
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            state["scanner_output"] = container.logs(tail=8).decode(errors="ignore")
        except Exception:
            state["scanner_output"] = ""
    else:
        state["scanner_output"] = ""

    return state


# ---------------------------------------------------------------------------
# Statistical hypothesis testing analysis
# ---------------------------------------------------------------------------

def _describe(arr):
    """Descriptive statistics for a numeric array."""
    a = np.array(arr, dtype=float)
    if len(a) == 0:
        return {"n": 0, "mean": 0, "std": 0, "median": 0, "min": 0, "max": 0}
    return {
        "n": int(len(a)),
        "mean": round(float(np.mean(a)), 4),
        "std": round(float(np.std(a, ddof=1)), 4) if len(a) > 1 else 0,
        "median": round(float(np.median(a)), 4),
        "min": round(float(np.min(a)), 4),
        "max": round(float(np.max(a)), 4),
    }


# ---------------------------------------------------------------------------
# Phase 1A: Multiple Comparison Correction (Holm-Bonferroni & Benjamini-Hochberg)
# ---------------------------------------------------------------------------

def _holm_bonferroni(p_values):
    """
    Holm-Bonferroni step-down correction for multiple comparisons.
    Controls familywise error rate (FWER). More powerful than Bonferroni.
    Returns adjusted p-values in the original order.
    """
    k = len(p_values)
    if k == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * k
    cumulative_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        adj_p = min(p * (k - rank), 1.0)
        cumulative_max = max(cumulative_max, adj_p)
        adjusted[orig_idx] = round(cumulative_max, 8)
    return adjusted


def _benjamini_hochberg(p_values):
    """
    Benjamini-Hochberg procedure for controlling False Discovery Rate (FDR).
    Less conservative than Holm; useful for exploratory per-protocol analysis.
    Returns adjusted p-values in the original order.
    """
    k = len(p_values)
    if k == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda x: x[1], reverse=True)
    adjusted = [0.0] * k
    cumulative_min = 1.0
    for rank_from_end, (orig_idx, p) in enumerate(indexed):
        rank_asc = k - rank_from_end
        adj_p = min(p * k / rank_asc, 1.0)
        cumulative_min = min(cumulative_min, adj_p)
        adjusted[orig_idx] = round(cumulative_min, 8)
    return adjusted


# ---------------------------------------------------------------------------
# Phase 1B: Bootstrap Confidence Intervals
# ---------------------------------------------------------------------------

def _bootstrap_ci(diffs, n_bootstrap=10000, ci_level=0.95, seed=42):
    """
    Non-parametric bootstrap confidence interval for mean difference.
    Distribution-free; robust with small N or skewed distributions.
    """
    rng = np.random.RandomState(seed)
    n = len(diffs)
    if n < 2:
        return {
            "level": ci_level,
            "lower": round(float(np.min(diffs)), 4) if n > 0 else 0,
            "upper": round(float(np.max(diffs)), 4) if n > 0 else 0,
            "mean_difference": round(float(np.mean(diffs)), 4) if n > 0 else 0,
            "n_bootstrap": 0,
            "method": "insufficient_data",
        }
    boot_means = np.array([
        np.mean(rng.choice(diffs, size=n, replace=True))
        for _ in range(n_bootstrap)
    ])
    alpha = 1 - ci_level
    lower = float(np.percentile(boot_means, 100 * alpha / 2))
    upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return {
        "level": ci_level,
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "mean_difference": round(float(np.mean(diffs)), 4),
        "n_bootstrap": n_bootstrap,
        "method": "percentile_bootstrap",
    }


# ---------------------------------------------------------------------------
# Phase 1C: Post-Hoc Power Analysis
# ---------------------------------------------------------------------------

def _compute_power(n, cohens_d, alpha=0.05):
    """
    Post-hoc statistical power for a one-sided paired t-test.
    Uses the non-central t-distribution.
    """
    from scipy.stats import t as t_dist, nct
    if n < 2 or cohens_d == 0:
        return 0.0
    df = n - 1
    t_crit = t_dist.ppf(1 - alpha, df)
    ncp = abs(cohens_d) * np.sqrt(n)
    power = 1 - nct.cdf(t_crit, df, ncp)
    return round(float(power), 4)


def _required_n(cohens_d, alpha=0.05, power_target=0.80):
    """
    Minimum sample size N to achieve target power for a paired t-test
    with the observed Cohen's d effect size.
    """
    if abs(cohens_d) < 0.001:
        return None  # Effect too small to estimate
    for n in range(2, 1000):
        if _compute_power(n, cohens_d, alpha) >= power_target:
            return n
    return 1000  # Upper bound


# ---------------------------------------------------------------------------
# Phase 2A: Permutation Test for Robustness Validation
# ---------------------------------------------------------------------------

def _permutation_test(arr_a, arr_b, n_permutations=10000, seed=42):
    """
    Permutation test for paired data (one-sided: arr_a > arr_b).
    Distribution-free p-value that validates parametric results.
    """
    rng = np.random.RandomState(seed)
    diffs = arr_a - arr_b
    observed_mean = float(np.mean(diffs))
    count = 0
    for _ in range(n_permutations):
        signs = rng.choice([-1, 1], size=len(diffs))
        perm_mean = float(np.mean(diffs * signs))
        if perm_mean >= observed_mean:
            count += 1
    p_value = count / n_permutations
    return {
        "test_name": "Permutation test (paired, one-sided)",
        "observed_mean_diff": round(observed_mean, 4),
        "p_value": round(float(p_value), 6),
        "n_permutations": n_permutations,
        "reject_h0": bool(p_value < 0.05),
    }


def _paired_test(arr_a, arr_b, label_a, label_b, n):
    """Run paired hypothesis test (t-test or Wilcoxon) and return results dict."""
    diffs = arr_a - arr_b

    # Normality
    normality = {"test": "Shapiro-Wilk", "statistic": None, "p_value": None, "is_normal": None}
    if n >= 3:
        try:
            sw_stat, sw_p = scipy_stats.shapiro(diffs)
            normality["statistic"] = round(float(sw_stat), 6)
            normality["p_value"] = round(float(sw_p), 6)
            normality["is_normal"] = bool(sw_p > 0.05)
        except Exception:
            normality["is_normal"] = True
    else:
        normality["is_normal"] = True

    primary = {
        "test_name": None, "statistic": None, "p_value": None,
        "df": None, "reject_h0": None, "significance_level": 0.05,
    }

    if np.std(diffs, ddof=1) == 0:
        primary["test_name"] = "N/A — variância zero"
        primary["statistic"] = 0
        primary["p_value"] = 1.0
        primary["reject_h0"] = False
    elif normality["is_normal"]:
        t_stat, t_p_two = scipy_stats.ttest_rel(arr_a, arr_b)
        t_p_one = t_p_two / 2 if t_stat > 0 else 1 - t_p_two / 2
        primary["test_name"] = f"Paired t-test ({label_a} > {label_b})"
        primary["statistic"] = round(float(t_stat), 6)
        primary["p_value"] = round(float(t_p_one), 8)
        primary["df"] = int(n - 1)
        primary["reject_h0"] = bool(t_p_one < 0.05)
    else:
        try:
            w_stat, w_p = scipy_stats.wilcoxon(diffs[diffs != 0], alternative="greater")
            primary["test_name"] = f"Wilcoxon ({label_a} > {label_b})"
            primary["statistic"] = round(float(w_stat), 6)
            primary["p_value"] = round(float(w_p), 8)
            primary["reject_h0"] = bool(w_p < 0.05)
        except Exception as e:
            primary["test_name"] = f"Wilcoxon failed: {e}"
            primary["p_value"] = 1.0
            primary["reject_h0"] = False

    # Effect size
    d_std = float(np.std(diffs, ddof=1)) if n > 1 else 1.0
    cohens_d = float(np.mean(diffs)) / d_std if d_std > 0 else 0.0
    abs_d = abs(cohens_d)
    d_interp = "grande" if abs_d >= 0.8 else "médio" if abs_d >= 0.5 else "pequeno" if abs_d >= 0.2 else "negligenciável"

    # CI
    mean_diff = float(np.mean(diffs))
    se = d_std / math.sqrt(n) if n > 0 else 0
    t_crit = float(scipy_stats.t.ppf(0.975, df=n - 1)) if n > 1 else 1.96
    ci_lower = round(mean_diff - t_crit * se, 4)
    ci_upper = round(mean_diff + t_crit * se, 4)

    # Bootstrap CI (Phase 1B)
    bootstrap_ci = _bootstrap_ci(diffs)

    return {
        "normality": normality,
        "primary": primary,
        "effect_size": {"cohens_d": round(cohens_d, 4), "interpretation": d_interp},
        "confidence_interval": {
            "level": 0.95, "lower": ci_lower, "upper": ci_upper,
            "mean_difference": round(mean_diff, 4), "standard_error": round(se, 4),
            "method": "parametric_t",
        },
        "confidence_interval_bootstrap": bootstrap_ci,
    }


@app.get("/experiments/analysis")
def statistical_analysis(experiments: Optional[str] = None):
    """
    Full statistical hypothesis testing — 3-way comparison:
      H₁: AutoML > Static  (primary)
      H₂: AutoML > Random  (proves model intelligence, not just more tests)
      H₃: Random > Static  (sanity check)
    """
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"error": "Nenhum experimento encontrado.", "sample_size": 0}

    all_exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    )

    if experiments:
        requested = set(experiments.split(","))
        all_exps = [e for e in all_exps if e in requested]

    # Collect paired observations (static + automl + optional random)
    paired_data = []
    static_only_vulns = []

    for exp in all_exps:
        exp_path = os.path.join(EXPERIMENTS_PATH, exp)
        static_path = os.path.join(exp_path, "metrics_static.json")
        automl_path = os.path.join(exp_path, "metrics_automl.json")
        random_path = os.path.join(exp_path, "metrics_random.json")

        has_static = os.path.exists(static_path)
        has_automl = os.path.exists(automl_path)
        has_random = os.path.exists(random_path)

        if has_static:
            try:
                with open(static_path) as f:
                    s = json.load(f)
            except Exception:
                continue

            if has_automl:
                try:
                    with open(automl_path) as f:
                        a = json.load(f)
                    row = {
                        "experiment": exp,
                        "static_vulns": int(s.get("vulns_detected", 0)),
                        "automl_vulns": int(a.get("vulns_detected", 0)),
                        "static_tests": int(s.get("tests_executed", 0)),
                        "automl_tests": int(a.get("tests_executed", 0)),
                        "static_time": float(s.get("exec_time_sec", 0)),
                        "automl_time": float(a.get("exec_time_sec", 0)),
                        "random_vulns": None,
                        "random_tests": None,
                        "random_time": None,
                    }
                    if has_random:
                        try:
                            with open(random_path) as f:
                                r = json.load(f)
                            row["random_vulns"] = int(r.get("vulns_detected", 0))
                            row["random_tests"] = int(r.get("tests_executed", 0))
                            row["random_time"] = float(r.get("exec_time_sec", 0))
                        except Exception:
                            pass
                    paired_data.append(row)
                except Exception:
                    continue
            else:
                static_only_vulns.append(int(s.get("vulns_detected", 0)))

    n = len(paired_data)
    # Check how many have random data
    n_with_random = sum(1 for p in paired_data if p["random_vulns"] is not None)

    if n < 2:
        return {
            "error": None,
            "sample_size": n,
            "paired_experiments": n,
            "static_only_experiments": len(static_only_vulns),
            "experiments_with_random": n_with_random,
            "experiments_used": [p["experiment"] for p in paired_data],
            "message": f"Necessário pelo menos 2 experimentos pareados. Encontrado(s): {n}.",
            "descriptive": None,
            "normality_test": None,
            "primary_test": None,
            "effect_size": None,
            "confidence_interval": None,
            "independent_test": None,
            "random_baseline": None,
            "per_protocol": [],
            "execution_time": None,
            "conclusion": None,
            "raw_pairs": paired_data,
        }

    # ------- Arrays -------
    static_v = np.array([p["static_vulns"] for p in paired_data], dtype=float)
    automl_v = np.array([p["automl_vulns"] for p in paired_data], dtype=float)
    diffs = automl_v - static_v

    static_t = np.array([p["static_time"] for p in paired_data], dtype=float)
    automl_t = np.array([p["automl_time"] for p in paired_data], dtype=float)
    time_diffs = automl_t - static_t

    # ------- Descriptive statistics -------
    descriptive = {
        "static": _describe(static_v),
        "automl": _describe(automl_v),
        "difference": _describe(diffs),
    }

    # Add random descriptive stats if available
    if n_with_random >= 2:
        random_v = np.array(
            [p["random_vulns"] for p in paired_data if p["random_vulns"] is not None],
            dtype=float,
        )
        descriptive["random"] = _describe(random_v)

    # ------- Primary test: AutoML > Static -------
    result_primary = _paired_test(automl_v, static_v, "AutoML", "Static", n)
    normality = result_primary["normality"]
    primary = result_primary["primary"]
    effect_size = result_primary["effect_size"]
    confidence_interval = result_primary["confidence_interval"]
    cohens_d = effect_size["cohens_d"]
    d_interp = effect_size["interpretation"]
    mean_diff = confidence_interval["mean_difference"]
    ci_lower = confidence_interval["lower"]
    ci_upper = confidence_interval["upper"]

    # ------- Random baseline analysis -------
    random_baseline = None
    if n_with_random >= 2:
        random_pairs = [p for p in paired_data if p["random_vulns"] is not None]
        n_r = len(random_pairs)
        random_v = np.array([p["random_vulns"] for p in random_pairs], dtype=float)
        automl_v_r = np.array([p["automl_vulns"] for p in random_pairs], dtype=float)
        static_v_r = np.array([p["static_vulns"] for p in random_pairs], dtype=float)

        # AutoML vs Random (proves model intelligence)
        automl_vs_random = _paired_test(automl_v_r, random_v, "AutoML", "Random", n_r)
        # Random vs Static (sanity check)
        random_vs_static = _paired_test(random_v, static_v_r, "Random", "Static", n_r)

        random_baseline = {
            "n": n_r,
            "descriptive": _describe(random_v),
            "automl_vs_random": {
                "primary": automl_vs_random["primary"],
                "effect_size": automl_vs_random["effect_size"],
                "confidence_interval": automl_vs_random["confidence_interval"],
            },
            "random_vs_static": {
                "primary": random_vs_static["primary"],
                "effect_size": random_vs_static["effect_size"],
                "confidence_interval": random_vs_static["confidence_interval"],
            },
        }

    # ------- Efficiency metric: vulns per test -------
    static_tests_arr = np.array([p["static_tests"] for p in paired_data], dtype=float)
    automl_tests_arr = np.array([p["automl_tests"] for p in paired_data], dtype=float)

    # Overall Efficiency = vulns / tests
    static_eff = np.where(static_tests_arr > 0, static_v / static_tests_arr, 0.0)
    automl_eff = np.where(automl_tests_arr > 0, automl_v / automl_tests_arr, 0.0)
    eff_diffs = automl_eff - static_eff

    # Marginal Efficiency = extra vulns found / extra tests run (by AutoML beyond static)
    marginal_vulns = automl_v - static_v
    marginal_tests = automl_tests_arr - static_tests_arr
    marginal_eff = np.where(marginal_tests > 0, marginal_vulns / marginal_tests, 0.0)

    efficiency = {
        "static": {
            "mean": round(float(np.mean(static_eff)), 4),
            "std": round(float(np.std(static_eff, ddof=1)), 4) if n > 1 else 0.0,
        },
        "automl": {
            "mean": round(float(np.mean(automl_eff)), 4),
            "std": round(float(np.std(automl_eff, ddof=1)), 4) if n > 1 else 0.0,
        },
        "difference_mean": round(float(np.mean(eff_diffs)), 4),
        "automl_improvement_pct": round(
            float((np.mean(automl_eff) - np.mean(static_eff)) / np.mean(static_eff) * 100), 1
        ) if np.mean(static_eff) > 0 else 0.0,
        "marginal": {
            "mean": round(float(np.mean(marginal_eff)), 4),
            "std": round(float(np.std(marginal_eff, ddof=1)), 4) if n > 1 else 0.0,
            "extra_vulns_mean": round(float(np.mean(marginal_vulns)), 2),
            "extra_tests_mean": round(float(np.mean(marginal_tests)), 2),
        },
    }

    # Marginal efficiency test: is it significantly > 0?
    if n >= 2 and float(np.std(marginal_eff, ddof=1)) > 0:
        if np.mean(marginal_eff) > 0:
            try:
                _, sw_p_marg = scipy_stats.shapiro(marginal_eff)
            except Exception:
                sw_p_marg = 1.0
            if sw_p_marg > 0.05:
                t_stat_m, t_p_m = scipy_stats.ttest_1samp(marginal_eff, 0)
                t_p_one_m = float(t_p_m / 2) if t_stat_m > 0 else float(1 - t_p_m / 2)
                efficiency["marginal"]["test"] = {
                    "test_name": "One-sample t-test (marginal eff > 0)",
                    "statistic": round(float(t_stat_m), 6),
                    "p_value": round(t_p_one_m, 8),
                    "reject_h0": bool(t_p_one_m < 0.05),
                }
            else:
                try:
                    w_stat_m, w_p_m = scipy_stats.wilcoxon(marginal_eff[marginal_eff != 0], alternative="greater")
                    efficiency["marginal"]["test"] = {
                        "test_name": "Wilcoxon (marginal eff > 0)",
                        "statistic": round(float(w_stat_m), 6),
                        "p_value": round(float(w_p_m), 8),
                        "reject_h0": bool(w_p_m < 0.05),
                    }
                except Exception:
                    pass

    # Add random efficiency if available
    if n_with_random >= 2:
        random_tests_arr = np.array(
            [p["random_tests"] for p in paired_data if p["random_tests"] is not None],
            dtype=float,
        )
        random_v_eff = np.array(
            [p["random_vulns"] for p in paired_data if p["random_vulns"] is not None],
            dtype=float,
        )
        random_eff = np.where(random_tests_arr > 0, random_v_eff / random_tests_arr, 0.0)
        efficiency["random"] = {
            "mean": round(float(np.mean(random_eff)), 4),
            "std": round(float(np.std(random_eff, ddof=1)), 4) if len(random_eff) > 1 else 0.0,
        }

    # Paired test on overall efficiency
    if n >= 2 and np.std(eff_diffs, ddof=1) > 0:
        eff_result = _paired_test(automl_eff, static_eff, "AutoML", "Static", n)
        efficiency["test"] = eff_result["primary"]
        efficiency["effect_size"] = eff_result["effect_size"]

    # ------- Independent test (Mann-Whitney) -------
    independent_test = None
    if len(static_only_vulns) >= 2 and n >= 2:
        try:
            u_stat, u_p = scipy_stats.mannwhitneyu(
                automl_v, np.array(static_only_vulns, dtype=float),
                alternative="greater",
            )
            independent_test = {
                "test_name": "Mann-Whitney U (one-sided, greater)",
                "automl_n": int(n),
                "static_only_n": len(static_only_vulns),
                "statistic": round(float(u_stat), 6),
                "p_value": round(float(u_p), 8),
                "reject_h0": bool(u_p < 0.05),
            }
        except Exception:
            pass

    # ------- Per-protocol breakdown (Fisher's exact) -------
    per_protocol = []
    paired_exp_ids = [p["experiment"] for p in paired_data]
    frames = []
    for exp_id in paired_exp_ids:
        csv_path = os.path.join(EXPERIMENTS_PATH, exp_id, "history.csv")
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                frames.append(df)
            except Exception:
                pass

    if frames:
        all_df = pd.concat(frames, ignore_index=True)
        all_df["vulnerability_found"] = (
            pd.to_numeric(all_df["vulnerability_found"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        for proto in sorted(all_df["protocol"].unique()):
            pdf = all_df[all_df["protocol"] == proto]

            s_df = pdf[pdf["test_strategy"] == "static"]
            a_df = pdf[pdf["test_strategy"] == "automl"]
            r_df = pdf[pdf["test_strategy"] == "random"]

            if s_df.empty or a_df.empty:
                continue

            s_vuln = int(s_df["vulnerability_found"].sum())
            s_total = len(s_df)
            a_vuln = int(a_df["vulnerability_found"].sum())
            a_total = len(a_df)

            table = [[s_vuln, s_total - s_vuln], [a_vuln, a_total - a_vuln]]
            try:
                _, fisher_p = scipy_stats.fisher_exact(table, alternative="two-sided")
            except Exception:
                fisher_p = 1.0

            # Phase 2B: Cramer's V for categorical effect size
            n_table = s_total + a_total
            cramers_v = 0.0
            if n_table > 0:
                try:
                    chi2_val = scipy_stats.chi2_contingency(table, correction=False)[0]
                    cramers_v = float(np.sqrt(chi2_val / n_table))
                except Exception:
                    cramers_v = 0.0
            cramers_v_interp = (
                "grande" if cramers_v >= 0.5 else
                "medio" if cramers_v >= 0.3 else
                "pequeno" if cramers_v >= 0.1 else
                "negligenciavel"
            )

            row = {
                "protocol": proto,
                "static_vulns": s_vuln,
                "static_tests": s_total,
                "static_rate": round(s_vuln / s_total, 4) if s_total > 0 else 0,
                "automl_vulns": a_vuln,
                "automl_tests": a_total,
                "automl_rate": round(a_vuln / a_total, 4) if a_total > 0 else 0,
                "fisher_p": round(float(fisher_p), 6),
                "significant": bool(fisher_p < 0.05),
                "cramers_v": round(cramers_v, 4),
                "cramers_v_interpretation": cramers_v_interp,
            }

            # Add random data if available
            if not r_df.empty:
                r_vuln = int(r_df["vulnerability_found"].sum())
                r_total = len(r_df)
                row["random_vulns"] = r_vuln
                row["random_tests"] = r_total
                row["random_rate"] = round(r_vuln / r_total, 4) if r_total > 0 else 0

            per_protocol.append(row)

    # ------- Phase 1A: Multiple comparison correction -------
    if len(per_protocol) > 1:
        raw_pvals = [row["fisher_p"] for row in per_protocol]
        holm_adjusted = _holm_bonferroni(raw_pvals)
        bh_adjusted = _benjamini_hochberg(raw_pvals)
        bonf_adjusted = [round(min(p * len(raw_pvals), 1.0), 8) for p in raw_pvals]

        for i, row in enumerate(per_protocol):
            row["fisher_p_holm"] = holm_adjusted[i]
            row["fisher_p_bh"] = bh_adjusted[i]
            row["fisher_p_bonferroni"] = bonf_adjusted[i]
            row["significant_holm"] = bool(holm_adjusted[i] < 0.05)
            row["significant_bh"] = bool(bh_adjusted[i] < 0.05)
            row["n_comparisons"] = len(per_protocol)

    multiple_comparison_correction = {
        "n_comparisons": len(per_protocol),
        "methods": ["holm", "benjamini-hochberg", "bonferroni"],
        "recommended": "holm",
        "note": "Holm controls FWER (familywise error); B-H controls FDR (less conservative)",
    } if len(per_protocol) > 1 else None

    # ------- Execution time comparison -------
    exec_time = None
    if n >= 2 and np.std(time_diffs, ddof=1) > 0:
        try:
            _, time_sw_p = scipy_stats.shapiro(time_diffs)
        except Exception:
            time_sw_p = 1.0

        if time_sw_p > 0.05:
            t_stat_t, t_p_t = scipy_stats.ttest_rel(automl_t, static_t)
            exec_time = {
                "static_mean_sec": round(float(np.mean(static_t)), 2),
                "automl_mean_sec": round(float(np.mean(automl_t)), 2),
                "test_name": "Paired t-test",
                "statistic": round(float(t_stat_t), 6),
                "p_value": round(float(t_p_t), 8),
                "significant": bool(t_p_t < 0.05),
            }
        else:
            try:
                w_stat_t, w_p_t = scipy_stats.wilcoxon(time_diffs)
                exec_time = {
                    "static_mean_sec": round(float(np.mean(static_t)), 2),
                    "automl_mean_sec": round(float(np.mean(automl_t)), 2),
                    "test_name": "Wilcoxon signed-rank",
                    "statistic": round(float(w_stat_t), 6),
                    "p_value": round(float(w_p_t), 8),
                    "significant": bool(w_p_t < 0.05),
                }
            except Exception:
                pass

        # Add random time if available
        if exec_time and n_with_random >= 2:
            random_t = np.array(
                [p["random_time"] for p in paired_data if p["random_time"] is not None],
                dtype=float,
            )
            exec_time["random_mean_sec"] = round(float(np.mean(random_t)), 2)

    # ------- Phase 1C: Power Analysis -------
    power_analysis = None
    if n >= 2 and cohens_d != 0:
        observed_power = _compute_power(n, cohens_d)
        req_n_80 = _required_n(cohens_d, power_target=0.80)
        req_n_90 = _required_n(cohens_d, power_target=0.90)
        power_analysis = {
            "observed_power": observed_power,
            "required_n_80": req_n_80,
            "required_n_90": req_n_90,
            "observed_n": n,
            "observed_cohens_d": round(cohens_d, 4),
            "interpretation": "Adequado" if observed_power >= 0.80 else (
                "Marginal" if observed_power >= 0.60 else "Insuficiente (risco de erro Tipo II)"
            ),
            "interpretation_en": "Adequate" if observed_power >= 0.80 else (
                "Marginal" if observed_power >= 0.60 else "Insufficient (Type II error risk)"
            ),
            "note": "Post-hoc power analysis; prospective power analysis is preferred",
        }

    # ------- Phase 2A: Permutation Test -------
    permutation_test = None
    if n >= 2 and float(np.std(diffs, ddof=1)) > 0:
        permutation_test = _permutation_test(automl_v, static_v)

    # ------- Phase 2C: Levene's Test (variance homogeneity) -------
    variance_homogeneity = None
    if n_with_random >= 2 and n >= 2:
        try:
            random_v_lev = np.array(
                [p["random_vulns"] for p in paired_data if p["random_vulns"] is not None],
                dtype=float,
            )
            levene_stat, levene_p = scipy_stats.levene(static_v, automl_v, random_v_lev)
            equal_var = bool(levene_p > 0.05)

            # Compute per-group variances for contextual explanation
            static_var = round(float(np.var(static_v, ddof=1)), 4) if n > 1 else 0.0
            automl_var = round(float(np.var(automl_v, ddof=1)), 4) if n > 1 else 0.0
            random_var = round(float(np.var(random_v_lev, ddof=1)), 4) if len(random_v_lev) > 1 else 0.0

            # Determine if heterogeneity is due to deterministic static baseline
            static_is_deterministic = static_var < 0.01

            if equal_var:
                interp_pt = "Variâncias homogêneas"
                interp_en = "Homogeneous variances"
                note_pt = "As variâncias dos três grupos são estatisticamente iguais."
                note_en = "The variances of the three groups are statistically equal."
            elif static_is_deterministic:
                interp_pt = "Heterogeneidade esperada"
                interp_en = "Expected heterogeneity"
                note_pt = (
                    "A suíte estática é determinística (variância ≈ 0), enquanto AutoML e Random "
                    "variam adaptativamente. Isso é esperado pelo design experimental e não invalida "
                    "os testes pareados (t-test/Wilcoxon), que operam sobre diferenças, não grupos."
                )
                note_en = (
                    "The static suite is deterministic (variance ≈ 0), while AutoML and Random "
                    "vary adaptively. This is expected by experimental design and does not invalidate "
                    "the paired tests (t-test/Wilcoxon), which operate on differences, not groups."
                )
            else:
                interp_pt = "Variâncias heterogêneas"
                interp_en = "Heterogeneous variances"
                note_pt = (
                    "As variâncias dos grupos diferem significativamente. Considere testes robustos "
                    "a heterocedasticidade (ex.: Welch) se usar comparações não pareadas."
                )
                note_en = (
                    "Group variances differ significantly. Consider heteroscedasticity-robust tests "
                    "(e.g., Welch) if using unpaired comparisons."
                )

            variance_homogeneity = {
                "test_name": "Levene's test",
                "statistic": round(float(levene_stat), 6),
                "p_value": round(float(levene_p), 6),
                "equal_variance": equal_var,
                "static_is_deterministic": static_is_deterministic,
                "group_variances": {
                    "static": static_var,
                    "automl": automl_var,
                    "random": random_var,
                },
                "interpretation": interp_pt,
                "interpretation_en": interp_en,
                "note": note_pt,
                "note_en": note_en,
                "affects_primary_test": False if static_is_deterministic else (not equal_var),
            }
        except Exception:
            pass

    # ------- Conclusion text -------
    conclusion = None
    if primary["p_value"] is not None:
        p_str = f"{primary['p_value']:.6f}" if primary["p_value"] >= 0.000001 else f"{primary['p_value']:.2e}"
        reject = primary["reject_h0"]

        # Build random baseline context for conclusion
        random_ctx_pt = ""
        random_ctx_en = ""
        if random_baseline and random_baseline["automl_vs_random"]["primary"]["reject_h0"]:
            avr_p = random_baseline["automl_vs_random"]["primary"]["p_value"]
            avr_d = random_baseline["automl_vs_random"]["effect_size"]["cohens_d"]
            random_ctx_pt = (
                f" Além disso, AutoML supera significativamente a seleção aleatória "
                f"(p = {avr_p:.6f}, d = {avr_d:.2f}), comprovando que a inteligência do modelo importa."
            )
            random_ctx_en = (
                f" Furthermore, AutoML significantly outperforms random selection "
                f"(p = {avr_p:.6f}, d = {avr_d:.2f}), proving that model intelligence matters."
            )

        # Power context for conclusion
        power_ctx_pt = ""
        power_ctx_en = ""
        if power_analysis:
            pw = power_analysis["observed_power"]
            power_ctx_pt = f" Poder estatístico observado: {pw:.1%}."
            power_ctx_en = f" Observed statistical power: {pw:.1%}."

        # Permutation context for conclusion
        perm_ctx_pt = ""
        perm_ctx_en = ""
        if permutation_test:
            perm_p = permutation_test["p_value"]
            perm_ctx_pt = f" Teste de permutação confirma: p = {perm_p:.6f}."
            perm_ctx_en = f" Permutation test confirms: p = {perm_p:.6f}."

        if reject:
            conclusion = {
                "text_pt": (
                    f"Com N={n} experimentos pareados, rejeitamos H₀ (p = {p_str}). "
                    f"O Emergence+AutoML detecta em média {round(mean_diff, 2)} mais vulnerabilidades "
                    f"por execução (IC 95%: [{ci_lower}, {ci_upper}], d de Cohen = {round(cohens_d, 2)}, "
                    f"efeito {d_interp}).{power_ctx_pt}{perm_ctx_pt}{random_ctx_pt}"
                ),
                "text_en": (
                    f"With N={n} paired experiments, we reject H₀ (p = {p_str}). "
                    f"Emergence+AutoML detects on average {round(mean_diff, 2)} more vulnerabilities "
                    f"per run (95% CI: [{ci_lower}, {ci_upper}], Cohen's d = {round(cohens_d, 2)}, "
                    f"{d_interp} effect).{power_ctx_en}{perm_ctx_en}{random_ctx_en}"
                ),
            }
        else:
            conclusion = {
                "text_pt": (
                    f"Com N={n} experimentos pareados, não rejeitamos H₀ (p = {p_str}). "
                    f"Não há evidência estatística suficiente de que o AutoML detecta mais "
                    f"vulnerabilidades que a suíte estática (diferença média = {round(mean_diff, 2)}, "
                    f"IC 95%: [{ci_lower}, {ci_upper}]).{power_ctx_pt}"
                ),
                "text_en": (
                    f"With N={n} paired experiments, we fail to reject H₀ (p = {p_str}). "
                    f"There is insufficient statistical evidence that AutoML detects more "
                    f"vulnerabilities than the static suite (mean difference = {round(mean_diff, 2)}, "
                    f"95% CI: [{ci_lower}, {ci_upper}]).{power_ctx_en}"
                ),
            }

    return _sanitize({
        "error": None,
        "sample_size": n,
        "paired_experiments": n,
        "static_only_experiments": len(static_only_vulns),
        "experiments_with_random": n_with_random,
        "experiments_used": [p["experiment"] for p in paired_data],
        "descriptive": descriptive,
        "normality_test": normality,
        "primary_test": primary,
        "effect_size": effect_size,
        "confidence_interval": confidence_interval,
        "confidence_interval_bootstrap": _bootstrap_ci(diffs),
        "independent_test": independent_test,
        "random_baseline": random_baseline,
        "power_analysis": power_analysis,
        "permutation_test": permutation_test,
        "variance_homogeneity": variance_homogeneity,
        "multiple_comparison_correction": multiple_comparison_correction,
        "efficiency": efficiency,
        "per_protocol": per_protocol,
        "execution_time": exec_time,
        "conclusion": conclusion,
        "raw_pairs": paired_data,
    })


# ---------------------------------------------------------------------------
# Architecture metadata endpoint
# ---------------------------------------------------------------------------

@app.get("/architecture/metadata")
def get_architecture_metadata():
    """Return comprehensive architecture metadata for the Architecture tab."""
    return {
        "api_endpoints": [
            {
                "method": "GET",
                "path": "/",
                "summary": "Health check",
                "description": "Returns API status. Use to verify the backend is online.",
                "category": "Health",
                "parameters": [],
                "request_body": None,
                "response_example": {"status": "ok", "message": "Dashboard API online"},
            },
            {
                "method": "GET",
                "path": "/experiments",
                "summary": "List all experiments",
                "description": "Returns a reverse-chronologically sorted list of experiment folder names (e.g. exp_2025-02-15_10-43-22).",
                "category": "Experiments",
                "parameters": [],
                "request_body": None,
                "response_example": {"experiments": ["exp_2025-02-15_10-43-22", "exp_2025-02-14_09-20-11"]},
            },
            {
                "method": "GET",
                "path": "/logs",
                "summary": "Docker container logs",
                "description": "Returns recent logs from all running Docker containers. Use the filter parameter to narrow down to a specific container.",
                "category": "Logs",
                "parameters": [
                    {"name": "tail", "type": "int", "default": 80, "description": "Number of log lines to return per container"},
                    {"name": "filter", "type": "string", "default": None, "description": "Container name substring filter (e.g. 'scanner')"},
                ],
                "request_body": None,
                "response_example": {"logs": {"scanner": "...", "mqtt_no_auth": "..."}},
            },
            {
                "method": "POST",
                "path": "/experiments/run",
                "summary": "Run a single experiment",
                "description": "Starts a single experiment execution in the scanner container. The experiment runs in the background; poll /experiments/status for progress.",
                "category": "Experiments",
                "parameters": [],
                "request_body": {
                    "mode": {"type": "string", "enum": ["static", "automl"], "description": "Testing strategy"},
                    "network": {"type": "string", "default": "172.20.0.0/27", "description": "Target network CIDR"},
                    "extra_args": {"type": "array", "default": [], "description": "Additional CLI arguments"},
                },
                "response_example": {"status": "started", "command": "python3 . -n 172.20.0.0/27 -aml"},
            },
            {
                "method": "GET",
                "path": "/experiments/status",
                "summary": "Poll experiment status",
                "description": "Returns the current experiment execution state. Poll every 2s while status is 'running'.",
                "category": "Experiments",
                "parameters": [],
                "request_body": None,
                "response_example": {"status": "running", "elapsed_seconds": 42.5, "command": "python3 . -n 172.20.0.0/27 -aml"},
            },
            {
                "method": "POST",
                "path": "/experiments/batch",
                "summary": "Run batch experiments",
                "description": "Starts N sequential experiment runs for statistical significance. Poll /experiments/batch/status for progress.",
                "category": "Experiments",
                "parameters": [],
                "request_body": {
                    "mode": {"type": "string", "default": "automl", "description": "Testing strategy for all runs"},
                    "network": {"type": "string", "default": "172.20.0.0/27", "description": "Target network CIDR"},
                    "runs": {"type": "int", "default": 30, "description": "Number of sequential experiments (2-30)"},
                },
                "response_example": {"status": "started", "total_runs": 30},
            },
            {
                "method": "GET",
                "path": "/experiments/batch/status",
                "summary": "Poll batch execution status",
                "description": "Returns current batch execution state including completed/total runs and experiment IDs.",
                "category": "Experiments",
                "parameters": [],
                "request_body": None,
                "response_example": {"status": "running", "completed_runs": 5, "total_runs": 30, "current_run": 6},
            },
            {
                "method": "GET",
                "path": "/history",
                "summary": "All experiment metrics",
                "description": "Returns metrics JSON data from all experiment folders (metrics_static.json, metrics_automl.json, metrics_random.json).",
                "category": "History",
                "parameters": [],
                "request_body": None,
                "response_example": {"history": [{"experiment": "exp_...", "metrics": {}}]},
            },
            {
                "method": "GET",
                "path": "/history/summary",
                "summary": "Aggregate KPIs",
                "description": "Returns summary statistics: total tests, vulnerabilities found, detection rate, most vulnerable protocol, etc.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment folder"},
                ],
                "request_body": None,
                "response_example": {"summary": {"total_tests": 84, "total_vulns": 48, "detection_rate": 57.1}},
            },
            {
                "method": "GET",
                "path": "/history/vulns-by-protocol",
                "summary": "Vulnerabilities grouped by protocol",
                "description": "Returns vulnerability counts grouped by protocol and test strategy. Used for the protocol bar chart.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"protocol": "http", "test_strategy": "automl", "vulns_found": 12}]},
            },
            {
                "method": "GET",
                "path": "/history/vulns-by-type",
                "summary": "Vulnerabilities grouped by type",
                "description": "Returns vulnerability counts grouped by test type (auth, misconfiguration, info_disclosure, etc.).",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"test_type": "auth", "vulns_found": 15, "detection_rate": 62.5}]},
            },
            {
                "method": "GET",
                "path": "/history/vulns-by-device",
                "summary": "Vulnerabilities grouped by device",
                "description": "Returns vulnerability counts grouped by container ID and protocol, with average execution time.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"container_id": "mqtt_no_auth", "protocol": "mqtt", "vulns_found": 4}]},
            },
            {
                "method": "GET",
                "path": "/history/exec-time-distribution",
                "summary": "Execution time distribution",
                "description": "Returns test counts bucketed by execution time ranges (<100ms, 100-500ms, 500ms-1s, 1-5s, 5-10s, >10s).",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"time_bucket": "<100ms", "test_strategy": "static", "count": 12}]},
            },
            {
                "method": "GET",
                "path": "/history/cumulative-vulns",
                "summary": "Cumulative vulnerability discovery curve",
                "description": "Returns time-series cumulative vulnerability count per strategy. Shows discovery rate over test iterations.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"test_strategy": "automl", "test_index": 5, "cumulative_vulns": 8}]},
            },
            {
                "method": "GET",
                "path": "/history/strategy-comparison",
                "summary": "Strategy comparison metrics",
                "description": "Returns aggregated metrics per strategy: total tests, vulns found, detection rate, efficiency, execution time.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"test_strategy": "automl", "total_tests": 43, "vulns_found": 48, "efficiency": 1.116}]},
            },
            {
                "method": "GET",
                "path": "/history/automl-scores",
                "summary": "AutoML risk scores",
                "description": "Returns the top 100 test candidates ranked by model-predicted risk score from automl_tests.csv.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                ],
                "request_body": None,
                "response_example": {"data": [{"test_id": "http_sqli_probe", "risk_score": 0.9234, "selected": True}]},
            },
            {
                "method": "GET",
                "path": "/history/detail",
                "summary": "Raw test execution data",
                "description": "Returns raw CSV rows from history.csv with all 16 columns. Supports pagination via limit parameter.",
                "category": "History",
                "parameters": [
                    {"name": "experiment", "type": "string", "default": None, "description": "Filter to specific experiment"},
                    {"name": "limit", "type": "int", "default": 5000, "description": "Maximum number of rows to return"},
                ],
                "request_body": None,
                "response_example": {"rows": [{"test_id": "http_directory_listing", "vulnerability_found": 1}], "total": 84},
            },
            {
                "method": "GET",
                "path": "/experiments/model-metrics",
                "summary": "H2O AutoML model performance",
                "description": "Returns the leader model metrics from the most recent experiment: AUC, logloss, feature importance, leaderboard, and ROC curve data.",
                "category": "Analysis",
                "parameters": [],
                "request_body": None,
                "response_example": {"auc": 0.92, "logloss": 0.31, "feature_importance": [], "leaderboard": []},
            },
            {
                "method": "GET",
                "path": "/experiments/learning-curve",
                "summary": "Statistical learning curve",
                "description": "Returns cumulative statistical metrics (p-value, Cohen's d, power) as experiments accumulate. Shows convergence to significance.",
                "category": "Analysis",
                "parameters": [],
                "request_body": None,
                "response_example": {"data": [{"n": 5, "p_value": 0.12, "cohens_d": 0.8, "power": 0.65}]},
            },
            {
                "method": "GET",
                "path": "/experiments/analysis",
                "summary": "Full statistical hypothesis testing",
                "description": "Performs comprehensive statistical analysis: normality tests, paired t-test/Wilcoxon, effect size (Cohen's d), confidence intervals, power analysis, permutation test, per-protocol Fisher's exact test, multiple comparison corrections, and efficiency metrics.",
                "category": "Analysis",
                "parameters": [
                    {"name": "experiments", "type": "string", "default": None, "description": "Comma-separated list of experiment IDs to analyze"},
                ],
                "request_body": None,
                "response_example": {"descriptive": {}, "primary_test": {"p_value": 0.003}, "effect_size": {"cohens_d": 1.24}},
            },
            {
                "method": "GET",
                "path": "/architecture/metadata",
                "summary": "Architecture metadata",
                "description": "Returns comprehensive architecture metadata including API endpoints, Docker containers, protocols, experiment phases, and tech stack.",
                "category": "Architecture",
                "parameters": [],
                "request_body": None,
                "response_example": {"api_endpoints": [], "containers": [], "protocols": {}, "tech_stack": {}},
            },
        ],
        "containers": [
            {"name": "ftp_anonymous", "ip": "172.20.0.10", "ports": [21], "role": "vulnerable_device", "protocol": "FTP", "tech": "fauria/vsftpd", "description": "FTP server with anonymous access enabled"},
            {"name": "ftp_credentials_vuln", "ip": "172.20.0.20", "ports": [21], "role": "vulnerable_device", "protocol": "FTP", "tech": "stilliard/pure-ftpd", "description": "FTP server with weak credentials (admin/admin)"},
            {"name": "ftp_banner", "ip": "172.20.0.13", "ports": [21], "role": "vulnerable_device", "protocol": "FTP", "tech": "stilliard/pure-ftpd:hardened", "description": "FTP server exposing banner information"},
            {"name": "http_traversal", "ip": "172.20.0.11", "ports": [80], "role": "vulnerable_device", "protocol": "HTTP", "tech": "Custom (Flask)", "description": "HTTP server vulnerable to directory traversal"},
            {"name": "http_admin_default_creds", "ip": "172.20.0.14", "ports": [80], "role": "vulnerable_device", "protocol": "HTTP", "tech": "Custom (Flask)", "description": "Admin panel with default credentials"},
            {"name": "http_directory_listing", "ip": "172.20.0.15", "ports": [80], "role": "vulnerable_device", "protocol": "HTTP", "tech": "httpd:2.4 (Apache)", "description": "HTTP server with directory listing enabled"},
            {"name": "http_api_vuln", "ip": "172.20.0.23", "ports": [80], "role": "vulnerable_device", "protocol": "HTTP", "tech": "Custom (Flask)", "description": "HTTP API with various vulnerabilities"},
            {"name": "telnet_insecure", "ip": "172.20.0.12", "ports": [23], "role": "vulnerable_device", "protocol": "Telnet", "tech": "Custom (telnetd)", "description": "Insecure telnet service with no encryption"},
            {"name": "mqtt_no_auth", "ip": "172.20.0.16", "ports": [1883], "role": "vulnerable_device", "protocol": "MQTT", "tech": "Custom (Mosquitto)", "description": "MQTT broker without authentication"},
            {"name": "ssh_old_banner", "ip": "172.20.0.17", "ports": [22], "role": "vulnerable_device", "protocol": "SSH", "tech": "rastasheep/ubuntu-sshd", "description": "SSH server with old version and weak configuration"},
            {"name": "coap_vuln", "ip": "172.20.0.21", "ports": [5683], "role": "vulnerable_device", "protocol": "CoAP", "tech": "Custom (aiocoap)", "description": "CoAP server with exposed resources"},
            {"name": "modbus_vuln", "ip": "172.20.0.22", "ports": [502], "role": "vulnerable_device", "protocol": "Modbus", "tech": "Custom (pymodbus)", "description": "Modbus TCP device with unauthenticated access"},
            {"name": "dns_vuln", "ip": "172.20.0.24", "ports": [53], "role": "vulnerable_device", "protocol": "DNS", "tech": "Custom (dnslib)", "description": "DNS server configured as open resolver"},
            {"name": "h2o-automl", "ip": "172.20.0.18", "ports": [54321], "role": "infrastructure", "protocol": "HTTP", "tech": "h2oai/h2o-open-source-k8s-minimal", "description": "H2O AutoML server for model training and prediction"},
            {"name": "scanner", "ip": "172.20.0.19", "ports": [], "role": "infrastructure", "protocol": None, "tech": "Python 3.10 + nmap", "description": "Main scanner container that runs vulnerability tests and AutoML pipeline"},
            {"name": "dashboard_api", "ip": None, "ports": [8000], "role": "infrastructure", "protocol": "HTTP", "tech": "Python 3.10 + FastAPI", "description": "REST API backend for the dashboard UI"},
            {"name": "dashboard_ui", "ip": None, "ports": [5173], "role": "infrastructure", "protocol": "HTTP", "tech": "React 18 + Vite + Nginx", "description": "Single-page application dashboard frontend"},
        ],
        "protocols": {
            "FTP": {
                "port": 21,
                "static_tests": 1,
                "adaptive_tests": 2,
                "static_test_ids": ["ftp_anonymous_login"],
                "adaptive_test_ids": ["ftp_anonymous_real", "ftp_weak_creds_ext"],
                "description": "File Transfer Protocol - tests for anonymous access and weak credentials",
            },
            "HTTP": {
                "port": 80,
                "static_tests": 9,
                "adaptive_tests": 8,
                "static_test_ids": ["http_default_credentials", "http_directory_listing", "http_directory_traversal", "http_dangerous_methods", "http_missing_sec_headers", "http_sensitive_files", "http_open_admin", "http_verbose_server", "http_no_auth"],
                "adaptive_test_ids": ["http_sensitive_files_ext", "http_open_admin_ext", "http_cors_misconfig", "http_insecure_cookies", "http_trace_method", "http_default_creds_ext", "http_traversal_encoded", "http_sqli_probe"],
                "description": "Hypertext Transfer Protocol - comprehensive web vulnerability testing",
            },
            "SSH": {
                "port": 22,
                "static_tests": 6,
                "adaptive_tests": 2,
                "static_test_ids": ["ssh_weak_auth", "ssh_root_login", "ssh_password_auth", "ssh_old_version", "ssh_weak_crypto", "ssh_no_auth_limit"],
                "adaptive_test_ids": ["ssh_weak_auth_ext", "ssh_weak_kex"],
                "description": "Secure Shell - tests for weak authentication, crypto, and configuration",
            },
            "Telnet": {
                "port": 23,
                "static_tests": 1,
                "adaptive_tests": 3,
                "static_test_ids": ["telnet_open"],
                "adaptive_test_ids": ["telnet_default_creds", "telnet_banner_leak", "telnet_no_encryption"],
                "description": "Telnet Protocol - tests for open service, default credentials, and info leaks",
            },
            "MQTT": {
                "port": 1883,
                "static_tests": 4,
                "adaptive_tests": 3,
                "static_test_ids": ["mqtt_open_access", "mqtt_anon_publish", "mqtt_acl_bypass", "mqtt_topic_enum"],
                "adaptive_test_ids": ["mqtt_retained_messages", "mqtt_wildcard_sub", "mqtt_sensitive_topics"],
                "description": "Message Queuing Telemetry Transport - IoT messaging protocol vulnerability tests",
            },
            "RTSP": {
                "port": 554,
                "static_tests": 1,
                "adaptive_tests": 3,
                "static_test_ids": ["rtsp_open"],
                "adaptive_test_ids": ["rtsp_default_creds", "rtsp_unauth_describe", "rtsp_path_traversal"],
                "description": "Real-Time Streaming Protocol - tests for unauthorized media access",
            },
            "CoAP": {
                "port": 5683,
                "static_tests": 3,
                "adaptive_tests": 3,
                "static_test_ids": ["coap_core_discovery", "coap_open_resource", "coap_get"],
                "adaptive_test_ids": ["coap_hidden_resource", "coap_put_allowed", "coap_delete_allowed"],
                "description": "Constrained Application Protocol - lightweight IoT protocol vulnerability tests",
            },
            "Modbus": {
                "port": 502,
                "static_tests": 2,
                "adaptive_tests": 5,
                "static_test_ids": ["modbus_read_register", "modbus_device_id"],
                "adaptive_test_ids": ["modbus_write_coil", "modbus_read_input_reg", "modbus_read_discrete", "modbus_read_coils", "modbus_write_register"],
                "description": "Modbus TCP - industrial protocol tests for unauthorized register access",
            },
            "DNS": {
                "port": 53,
                "static_tests": 2,
                "adaptive_tests": 3,
                "static_test_ids": ["dns_open_resolver", "dns_internal_disclosure"],
                "adaptive_test_ids": ["dns_cache_snoop", "dns_any_query", "dns_version_disclosure"],
                "description": "Domain Name System - tests for open resolver, cache snooping, and info disclosure",
            },
        },
        "experiment_phases": [
            {
                "id": 1,
                "name": "Network Discovery",
                "icon": "Radar",
                "color": "blue",
                "description": "Nmap scans the target network (default 172.20.0.0/27) to discover active IoT devices, open ports, services, and OS fingerprints.",
                "inputs": ["Target network CIDR"],
                "outputs": ["List of discovered devices with open ports and services"],
                "module": "scanners/nmap_scanner.py",
                "details": "Uses python-nmap with -sV (service detection) and -O (OS detection) flags. Discovers all 13 vulnerable devices on the Docker bridge network.",
            },
            {
                "id": 2,
                "name": "Static Baseline Testing",
                "icon": "Shield",
                "color": "green",
                "description": "Executes all 28 static vulnerability tests from PROTOCOL_TESTS against every discovered device matching the test's protocol.",
                "inputs": ["Discovered devices", "PROTOCOL_TESTS registry (28 tests)"],
                "outputs": ["history.csv (28+ rows)", "metrics_static.json"],
                "module": "utils/tester.py",
                "details": "Each test runs against every device that exposes the matching port/protocol. Results logged to history.csv with 16 columns including vulnerability_found (0/1) and execution_time_ms.",
            },
            {
                "id": 3,
                "name": "AutoML Model Training",
                "icon": "Brain",
                "color": "purple",
                "description": "H2O AutoML trains a binary classifier on history.csv to predict which tests will find vulnerabilities. Training runs for up to 5 minutes with balanced classes.",
                "inputs": ["history.csv from Phase 1"],
                "outputs": ["Leader model", "model_metrics.json (AUC, feature importance, leaderboard)"],
                "module": "automl/train.py",
                "details": "Features: device_type, firmware, port, protocol, service, auth_required, test_type, port_count, protocol_diversity, is_common_port. Target: vulnerability_found. Algorithms: GBM, GLM, XGBoost, DeepLearning, StackedEnsemble.",
            },
            {
                "id": 4,
                "name": "Candidate Generation & Risk Scoring",
                "icon": "ListChecks",
                "color": "purple",
                "description": "Generates 58 test candidates (28 static + 30 adaptive) and scores each with the trained model's predicted probability of finding a vulnerability.",
                "inputs": ["Trained leader model", "PROTOCOL_TESTS (28)", "ADAPTIVE_TESTS (30)"],
                "outputs": ["automl_tests.csv (58 rows with risk_score and selected flag)"],
                "module": "automl/candidates.py + automl/adaptive_generator.py",
                "details": "Static tests: always selected (source='static'). Adaptive tests: selected only if risk_score >= 0.3 (source='adaptive'). This ensures the AutoML strategy includes the full baseline plus model-chosen extras.",
            },
            {
                "id": 5,
                "name": "Adaptive Test Execution",
                "icon": "Zap",
                "color": "amber",
                "description": "Executes only the selected tests (all 28 static + high-risk adaptive tests). Typically runs ~43 tests total.",
                "inputs": ["automl_tests.csv (selected=True rows)", "Discovered devices"],
                "outputs": ["history.csv (appended)", "metrics_automl.json"],
                "module": "utils/run_adaptive_tests.py",
                "details": "The adaptive strategy runs MORE tests than static (28 + ~15 adaptive = ~43) but focuses on tests the model predicts are most likely to find vulnerabilities. Expected result: ~48 vulnerabilities found (~71% improvement over static).",
            },
            {
                "id": 6,
                "name": "Random Baseline",
                "icon": "Shuffle",
                "color": "gray",
                "description": "Control group: runs the same NUMBER of adaptive tests as AutoML chose, but selected randomly instead of by model prediction.",
                "inputs": ["Count of adaptive tests selected by AutoML", "ADAPTIVE_TESTS pool"],
                "outputs": ["history.csv (appended)", "metrics_random.json"],
                "module": "utils/run_random_tests.py",
                "details": "Proves that AutoML's predictions are better than chance. If AutoML chose 15 adaptive tests, random also runs 15 (randomly chosen). Expected result: ~35 vulnerabilities — better than static but worse than AutoML.",
            },
            {
                "id": 7,
                "name": "Results & Analysis",
                "icon": "BarChart3",
                "color": "blue",
                "description": "Generates comparison plots and statistical analysis. Results available in the Dashboard History and Statistical Analysis tabs.",
                "inputs": ["metrics_static.json", "metrics_automl.json", "metrics_random.json", "history.csv"],
                "outputs": ["Comparison charts", "Statistical hypothesis tests"],
                "module": "analysis/generate_plots.py",
                "details": "Hypothesis: AutoML > Random > Static. Validated with paired t-test/Wilcoxon, Cohen's d effect size, bootstrap confidence intervals, and permutation tests.",
            },
        ],
        "tech_stack": {
            "frontend": {
                "label": "Frontend (Dashboard UI)",
                "color": "blue",
                "technologies": [
                    {"name": "React", "version": "18.2.0", "role": "UI framework"},
                    {"name": "Vite", "version": "5.1.0", "role": "Build tool & dev server"},
                    {"name": "Tailwind CSS", "version": "3.3.3", "role": "Utility-first CSS framework"},
                    {"name": "Recharts", "version": "2.10.0", "role": "Chart library for data visualization"},
                    {"name": "Lucide React", "version": "0.290.0", "role": "Icon library"},
                    {"name": "Axios", "version": "1.6.7", "role": "HTTP client"},
                ],
                "files": ["dashboard/frontend/src/pages/Home.jsx", "dashboard/frontend/src/components/", "dashboard/frontend/src/hooks/", "dashboard/frontend/src/api/"],
                "description": "Single-page application with 4 tabs: Dashboard (experiment runner), History (charts), Statistical Analysis, and Architecture.",
            },
            "backend": {
                "label": "Backend (Dashboard API)",
                "color": "purple",
                "technologies": [
                    {"name": "Python", "version": "3.10", "role": "Programming language"},
                    {"name": "FastAPI", "version": "latest", "role": "REST API framework"},
                    {"name": "Docker SDK", "version": "latest", "role": "Docker container management"},
                    {"name": "Pandas", "version": "latest", "role": "Data analysis & CSV processing"},
                    {"name": "NumPy", "version": "latest", "role": "Numerical computing"},
                    {"name": "SciPy", "version": "latest", "role": "Statistical hypothesis testing"},
                    {"name": "Pydantic", "version": "latest", "role": "Request/response validation"},
                ],
                "files": ["dashboard/backend/main.py", "dashboard/backend/Dockerfile"],
                "description": "REST API serving 23 endpoints for experiment management, historical analytics, statistical analysis, and architecture metadata.",
            },
            "scanner": {
                "label": "Scanner Engine",
                "color": "green",
                "technologies": [
                    {"name": "Python", "version": "3.10", "role": "Programming language"},
                    {"name": "python-nmap", "version": "0.7.1", "role": "Network scanner wrapper"},
                    {"name": "requests", "version": "2.31.0", "role": "HTTP testing"},
                    {"name": "paramiko", "version": "latest", "role": "SSH protocol testing"},
                    {"name": "paho-mqtt", "version": ">=1.6", "role": "MQTT protocol testing"},
                    {"name": "aiocoap", "version": "latest", "role": "CoAP protocol testing"},
                    {"name": "pymodbus", "version": "2.5.3", "role": "Modbus TCP testing"},
                ],
                "files": ["__main__.py", "scanners/nmap_scanner.py", "vulnerability_tester/", "utils/protocol_test_map.py", "utils/adaptive_test_map.py", "utils/tester.py"],
                "description": "Core scanning engine with 58 vulnerability tests across 9 IoT protocols. Orchestrates static, adaptive, and random testing strategies.",
            },
            "automl": {
                "label": "AutoML Pipeline",
                "color": "amber",
                "technologies": [
                    {"name": "H2O-3", "version": "latest", "role": "AutoML platform (Java-based)"},
                    {"name": "H2O Python Client", "version": "latest", "role": "Python API for H2O"},
                    {"name": "scikit-learn", "version": "latest", "role": "ML utilities & metrics"},
                ],
                "files": ["automl/pipeline.py", "automl/train.py", "automl/dataset.py", "automl/candidates.py", "automl/adaptive_generator.py", "automl/predict.py"],
                "description": "Machine learning pipeline that trains binary classifiers to predict which vulnerability tests will succeed, enabling intelligent test prioritization.",
            },
            "devices": {
                "label": "IoT Test Devices",
                "color": "red",
                "technologies": [
                    {"name": "Docker", "version": "latest", "role": "Container runtime"},
                    {"name": "Docker Compose", "version": "latest", "role": "Multi-container orchestration"},
                    {"name": "vsftpd", "version": "latest", "role": "FTP server"},
                    {"name": "Apache httpd", "version": "2.4", "role": "HTTP server"},
                    {"name": "Mosquitto", "version": "latest", "role": "MQTT broker"},
                    {"name": "OpenSSH", "version": "old", "role": "SSH server"},
                    {"name": "Flask", "version": "latest", "role": "Custom HTTP apps"},
                ],
                "files": ["docker-compose.yml", "emergence/devices/"],
                "description": "13 intentionally vulnerable Docker containers simulating real IoT devices across 9 protocols, deployed on a bridge network (172.20.0.0/24).",
            },
            "infrastructure": {
                "label": "Infrastructure",
                "color": "gray",
                "technologies": [
                    {"name": "Docker Compose", "version": "latest", "role": "Service orchestration"},
                    {"name": "Docker Bridge Network", "version": "N/A", "role": "Container networking (172.20.0.0/24)"},
                    {"name": "Nginx", "version": "latest", "role": "Frontend static file server"},
                    {"name": "OpenJDK", "version": "21", "role": "Java runtime for H2O"},
                ],
                "files": ["docker-compose.yml", "Dockerfile", "dashboard/frontend/Dockerfile", "dashboard/backend/Dockerfile"],
                "description": "Docker Compose orchestration of 17 containers: 13 vulnerable devices + H2O AutoML + Scanner + Dashboard API + Dashboard UI.",
            },
        },
    }
