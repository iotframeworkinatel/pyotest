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

app = FastAPI(title="IoT Vulnerability Dashboard API")

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

    return {"metrics": results, "aggregate": aggregate}


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

    return {"curve": curve}


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

    return {
        "normality": normality,
        "primary": primary,
        "effect_size": {"cohens_d": round(cohens_d, 4), "interpretation": d_interp},
        "confidence_interval": {
            "level": 0.95, "lower": ci_lower, "upper": ci_upper,
            "mean_difference": round(mean_diff, 4), "standard_error": round(se, 4),
        },
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

    # Efficiency = vulns / tests (higher is better — fewer tests to find same vulns)
    static_eff = np.where(static_tests_arr > 0, static_v / static_tests_arr, 0.0)
    automl_eff = np.where(automl_tests_arr > 0, automl_v / automl_tests_arr, 0.0)
    eff_diffs = automl_eff - static_eff

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
    }

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

    # Paired test on efficiency
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
            }

            # Add random data if available
            if not r_df.empty:
                r_vuln = int(r_df["vulnerability_found"].sum())
                r_total = len(r_df)
                row["random_vulns"] = r_vuln
                row["random_tests"] = r_total
                row["random_rate"] = round(r_vuln / r_total, 4) if r_total > 0 else 0

            per_protocol.append(row)

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

        if reject:
            conclusion = {
                "text_pt": (
                    f"Com N={n} experimentos pareados, rejeitamos H₀ (p = {p_str}). "
                    f"O PyoTest+AutoML detecta em média {round(mean_diff, 2)} mais vulnerabilidades "
                    f"por execução (IC 95%: [{ci_lower}, {ci_upper}], d de Cohen = {round(cohens_d, 2)}, "
                    f"efeito {d_interp}).{random_ctx_pt}"
                ),
                "text_en": (
                    f"With N={n} paired experiments, we reject H₀ (p = {p_str}). "
                    f"PyoTest+AutoML detects on average {round(mean_diff, 2)} more vulnerabilities "
                    f"per run (95% CI: [{ci_lower}, {ci_upper}], Cohen's d = {round(cohens_d, 2)}, "
                    f"{d_interp} effect).{random_ctx_en}"
                ),
            }
        else:
            conclusion = {
                "text_pt": (
                    f"Com N={n} experimentos pareados, não rejeitamos H₀ (p = {p_str}). "
                    f"Não há evidência estatística suficiente de que o AutoML detecta mais "
                    f"vulnerabilidades que a suíte estática (diferença média = {round(mean_diff, 2)}, "
                    f"IC 95%: [{ci_lower}, {ci_upper}])."
                ),
                "text_en": (
                    f"With N={n} paired experiments, we fail to reject H₀ (p = {p_str}). "
                    f"There is insufficient statistical evidence that AutoML detects more "
                    f"vulnerabilities than the static suite (mean difference = {round(mean_diff, 2)}, "
                    f"95% CI: [{ci_lower}, {ci_upper}])."
                ),
            }

    return {
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
        "independent_test": independent_test,
        "random_baseline": random_baseline,
        "efficiency": efficiency,
        "per_protocol": per_protocol,
        "execution_time": exec_time,
        "conclusion": conclusion,
        "raw_pairs": paired_data,
    }
