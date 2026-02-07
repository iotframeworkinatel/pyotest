import os
import math
import docker
import json
from typing import Optional

import numpy as np
import pandas as pd
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


class ExperimentRequest(BaseModel):
    mode: str
    network: str = "172.20.0.0/27"
    extra_args: list[str] = []


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
def get_logs():
    """
    Retorna os logs recentes de todos os containers Docker ativos
    (para o dashboard exibir em tempo real).
    """
    try:
        containers = docker_client.containers.list()
        logs_data = {}

        for c in containers:
            try:
                logs_data[c.name] = c.logs(tail=40).decode(errors="ignore")
            except Exception as e:
                logs_data[c.name] = f"[Erro ao ler logs: {e}]"

        return {"containers": list(logs_data.keys()), "logs": logs_data}

    except Exception as e:
        return {"error": str(e)}


@app.post("/experiments/run")
def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    cmd_parts = ["python3", ".", "-n", req.network]
    if req.mode == "automl":
        cmd_parts.append("-aml")

    extra_args = getattr(req, "extra_args", [])
    if isinstance(extra_args, list):
        cmd_parts.extend(extra_args)

    cmd_str = " ".join(cmd_parts)

    def _exec():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            print(f"[API] Executando: {cmd_str}")
            container.exec_run(cmd_str, detach=True, workdir="/app")
        except Exception as e:
            print(f"[ERRO] Falha ao executar experimento: {e}")

    background_tasks.add_task(_exec)
    return {"status": "started", "command": cmd_str}


@app.get("/metrics")
def get_latest_metrics():
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"metrics": []}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )
    if not exps:
        return {"metrics": []}

    latest = os.path.join(EXPERIMENTS_PATH, exps[0])
    result = []
    for file in ["metrics_static.json", "metrics_automl.json"]:
        path = os.path.join(latest, file)
        if os.path.exists(path):
            with open(path) as f:
                try:
                    result.append(json.load(f))
                except:
                    pass
    return {"metrics": result}


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
        for file in ["metrics_static.json", "metrics_automl.json"]:
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

    return {"data": grouped.to_dict(orient="records")}


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

    return {"data": grouped.to_dict(orient="records")}


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

    return {"data": grouped.to_dict(orient="records")}


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

    return {"data": combined.head(100).to_dict(orient="records")}


@app.get("/history/detail")
def get_history_detail(experiment: Optional[str] = None, limit: int = 5000):
    df = _load_history_csv(experiment)
    if df.empty:
        return {"rows": [], "total": 0}

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["execution_time_ms"] = pd.to_numeric(df["execution_time_ms"], errors="coerce").fillna(0).astype(int)
    df["open_port"] = pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)

    rows = df.head(limit).to_dict(orient="records")
    return {"rows": rows, "total": len(df)}
