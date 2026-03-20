"""
Emergence — IoT Test Case Generator API
FastAPI backend for device discovery, test generation, and execution.
"""
import os
import json
import time
import copy
import hashlib
import threading
import logging
from typing import Optional
from datetime import datetime
from pathlib import Path

import docker
import pandas as pd
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# ─── Generator imports (add parent to path for module resolution) ───
import sys
sys.path.insert(0, "/app")

from generator.registry import get_all_protocols, get_test_count, get_total_test_count
from generator.engine import generate_test_suite
from generator.exporter import export_json, export_yaml, export_python
from generator.scorer import score_test_suite
from generator.owasp_mapping import OWASP_IOT_MAP
from models.test_case import TestSuite, TestCase

# ─── Simulation imports ───
from simulation.config import SimulationConfig
from simulation.profiles import get_profile, list_profiles, PROFILES
from simulation.environment import EnvironmentSimulator

app = FastAPI(title="Emergence — IoT Test Case Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_client = docker.from_env(timeout=300)

EXPERIMENTS_PATH = "/app/experiments"
SUITES_PATH = "/app/suites"
RESULTS_PATH = "/app/results"
SCANNER_CONTAINER_NAME = "scanner"

os.makedirs(SUITES_PATH, exist_ok=True)
os.makedirs(RESULTS_PATH, exist_ok=True)


# ─── In-memory TTL cache for hypothesis endpoints ───────────────────
class _TTLCache:
    """Simple thread-safe TTL cache for DataFrames and dicts."""

    def __init__(self, default_ttl: int = 60):
        self._store: dict = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str):
        with self._lock:
            if key in self._store:
                ts, val = self._store[key]
                if time.time() - ts < self._default_ttl:
                    if isinstance(val, pd.DataFrame):
                        return val.copy()
                    return copy.deepcopy(val)
                else:
                    del self._store[key]
        return None

    def set(self, key: str, value):
        with self._lock:
            if isinstance(value, pd.DataFrame):
                self._store[key] = (time.time(), value.copy())
            else:
                self._store[key] = (time.time(), copy.deepcopy(value))

    def clear(self):
        with self._lock:
            self._store.clear()


_history_cache = _TTLCache(default_ttl=60)
_iteration_cache = _TTLCache(default_ttl=60)
_prediction_cache = _TTLCache(default_ttl=120)


# ─── DuckDB integration ──────────────────────────────────────────────
import duckdb as _duckdb

DB_PATH = os.path.join(EXPERIMENTS_PATH, "emergence.db")
_db_lock = threading.Lock()

_BASELINE_DIR_MAP_DB = {
    "BASELINE-RANDOM": "random",
    "BASELINE-CVSS": "cvss_priority",
    "BASELINE-ROBIN": "round_robin",
    "BASELINE-NOML": "no_ml",
}


def _db_available() -> bool:
    return os.path.exists(DB_PATH)


def _db_insert_history(df: pd.DataFrame, exp_dir_name: str) -> None:
    """Append rows from one experiment iteration into DuckDB."""
    try:
        df = df.copy()
        df["exp_dir_name"] = exp_dir_name
        with _db_lock:
            con = _duckdb.connect(DB_PATH)
            try:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS history AS SELECT * FROM df WHERE 1=0"
                )
                # Add exp_dir_name column if this is an older DB without it
                existing = {
                    row[0]
                    for row in con.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'history'"
                    ).fetchall()
                }
                for col in df.columns:
                    if col not in existing:
                        con.execute(
                            f"ALTER TABLE history ADD COLUMN \"{col}\" VARCHAR"
                        )
                con.execute("INSERT INTO history BY NAME SELECT * FROM df")
            finally:
                con.close()
    except Exception as e:
        logging.warning(f"[DuckDB] Failed to insert history: {e}")


def _db_load_all(
    simulation_mode: str = None, automl_tool: str = None, phase: str = None
) -> "pd.DataFrame | None":
    """Load history from DuckDB, returning a DataFrame or None on failure."""
    if not _db_available():
        return None
    try:
        conditions = []
        params = []
        if simulation_mode and simulation_mode != "all":
            conditions.append("simulation_mode = ?")
            params.append(simulation_mode)
        if automl_tool and automl_tool != "all":
            conditions.append("automl_tool = ?")
            params.append(automl_tool)
        query = "SELECT * FROM history"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        with _db_lock:
            con = _duckdb.connect(DB_PATH, read_only=True)
            try:
                result = con.execute(query, params).df()
            finally:
                con.close()
        if result.empty:
            return None
        # Backfill columns for rows that predate the tagged writes
        if "automl_tool" not in result.columns:
            result["automl_tool"] = "h2o"
        else:
            result["automl_tool"] = result["automl_tool"].fillna("h2o")
        if "baseline_strategy" not in result.columns:
            result["baseline_strategy"] = "ml_guided"
        else:
            result["baseline_strategy"] = result["baseline_strategy"].fillna("ml_guided")
        # Backfill phase/test_origin/score_method for rows that predate the tagged writes
        _NON_ML_BF = {"random", "cvss_priority", "round_robin", "no_ml"}
        if "phase" not in result.columns:
            result["phase"] = result["baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_BF else "framework"
            )
        else:
            _null_phase = result["phase"].isna()
            result.loc[_null_phase, "phase"] = result.loc[_null_phase, "baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_BF else "framework"
            )
        if "test_origin" not in result.columns:
            if "test_strategy" in result.columns:
                result["test_origin"] = result["test_strategy"].apply(
                    lambda x: "llm" if x == "llm_generated" else "registry"
                )
            else:
                result["test_origin"] = "registry"
        else:
            result["test_origin"] = result["test_origin"].fillna("registry")
        if "score_method" not in result.columns:
            result["score_method"] = result["baseline_strategy"].apply(
                lambda x: "heuristic" if x in _NON_ML_BF else "ml"
            )
        else:
            _null_sm = result["score_method"].isna()
            result.loc[_null_sm, "score_method"] = result.loc[_null_sm, "baseline_strategy"].apply(
                lambda x: "heuristic" if x in _NON_ML_BF else "ml"
            )
        # Apply phase filter after backfill (phase column may be derived above)
        if phase and "phase" in result.columns:
            result = result[result["phase"] == phase]
            if result.empty:
                return None
        if "vulnerability_found" in result.columns:
            result["vulnerability_found"] = pd.to_numeric(
                result["vulnerability_found"], errors="coerce"
            ).fillna(0).astype(int)
        return result
    except Exception as e:
        logging.warning(f"[DuckDB] Load failed: {e}")
        return None


# ─── JSON-safe float helper (NaN / Inf → None) ──────────────────────
import math

def _safe_float(v, decimals=4):
    """Round a numeric value, converting NaN/Inf to None for JSON safety."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, decimals)

# ─── In-memory state tracking ───

_scan_state = {
    "status": "idle",  # idle | running | completed | error
    "started_at": None,
    "devices": [],
    "error": None,
}
_scan_lock = threading.Lock()

_run_state = {
    "status": "idle",  # idle | running | completed | error
    "suite_id": None,
    "started_at": None,
    "finished_at": None,
    "progress": 0,
    "total_tests": 0,
    "error": None,
}
_run_lock = threading.Lock()

# Manual devices (persisted in memory)
_manual_devices = []
_devices_lock = threading.Lock()


# ─── Suite score validation ─────────────────────────────────────────────

def _get_ever_trained_frameworks() -> set:
    """Return set of framework names that have been trained at least once.

    Uses saved model metrics on disk — a framework is considered 'trained'
    if its metrics JSON exists and has status != 'untrained'.
    """
    from automl.pipeline import get_model_metrics
    from automl.registry import list_all

    trained = set()
    for name in list_all():
        try:
            metrics = get_model_metrics(name)
            if metrics.get("status") != "untrained":
                trained.add(name)
        except Exception:
            pass
    return trained


def _validate_suite_scores(suite_data: dict) -> dict:
    """Clear stale ML scores from a suite if its framework was never trained.

    Suites generated before the scorer fix may carry risk scores from the
    wrong framework.  This function checks whether the suite's
    ``automl_tool`` was ever trained and, if not, zeros out the scores in
    the returned dict (without touching the file on disk).
    """
    automl_tool = suite_data.get("metadata", {}).get("automl_tool") or "h2o"

    # Suites labelled "h2o" or with no label are assumed valid (legacy)
    if automl_tool == "h2o":
        return suite_data

    trained = _get_ever_trained_frameworks()
    if automl_tool in trained:
        return suite_data

    # Framework was never trained — clear stale scores
    for tc in suite_data.get("test_cases", []):
        tc["risk_score"] = None
        tc["is_recommended"] = False

    # Recompute recommended_count
    suite_data["recommended_count"] = 0

    return suite_data


# ─── Request/Response Models ───

class ScanRequest(BaseModel):
    network: str = "172.20.0.0/27"
    extra_ports: Optional[str] = None


class DeviceInput(BaseModel):
    ip: str
    ports: list[int]


class GenerateRequest(BaseModel):
    devices: list[dict]  # [{ip, ports}]
    protocols: Optional[list[str]] = None
    include_uncommon: bool = True
    severity_filter: Optional[list[str]] = None
    name: str = ""
    force_new: bool = False
    automl_tool: str = "h2o"  # Framework for ML scoring
    llm_enabled: bool = False  # Generate LLM tests alongside registry
    llm_provider: str = "claude"  # LLM provider: "claude", "openai", "gemini"


class RunRequest(BaseModel):
    pass  # No body needed, suite_id comes from URL


class TrainLoopRequest(BaseModel):
    iterations: int = 3
    simulation_mode: str = "deterministic"   # profile name or "custom"
    simulation_seed: int = 42
    simulation_config: Optional[dict] = None  # custom overrides (only if mode="custom")
    train_every_n: int = 0  # 0 = train only after last iteration, 1 = every iter, N = every Nth + last
    automl_tool: str = "h2o"  # Framework for ML training/scoring
    temporal_training: bool = False  # Use expanding-window temporal train/test splits
    baseline_strategy: Optional[str] = None  # "random"|"cvss_priority"|"round_robin"|"no_ml"
    llm_enabled: bool = False  # Enable LLM-based test generation
    llm_generate_every_n: int = 10  # Generate new LLM tests every N iterations
    llm_provider: str = "claude"  # LLM provider: "claude", "openai", "gemini"
    phase_tag: Optional[str] = None  # "phase5" | "phase6" | None
    dynamic_features: bool = False  # Use rolling temporal features (Phase 5/6)


# ═══════════════════════════════════════════════════════════════════════
# HEALTH & INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "ok", "service": "Emergence IoT Test Case Generator API"}


@app.get("/api/logs")
def get_logs(tail: int = 80, filter: Optional[str] = None):
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
                logs_data[name] = f"[Error reading logs: {e}]"

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


@app.get("/api/docker-ps")
def docker_ps():
    try:
        containers = docker_client.containers.list()
        return {
            "containers": [
                {
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else str(c.image.id)[:12],
                }
                for c in containers
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/protocols")
def list_protocols():
    return {
        "protocols": get_all_protocols(),
        "test_counts": get_test_count(),
        "total_tests": get_total_test_count(),
        "owasp_categories": OWASP_IOT_MAP,
    }


@app.get("/architecture/metadata")
def architecture_metadata():
    """Return architecture metadata for the Architecture dashboard tab."""
    from generator.registry import TEST_REGISTRY
    from utils.protocols import PORT_PROTOCOL_MAP

    # Build protocol info
    protocols = {}
    proto_port_map = {v: k for k, v in PORT_PROTOCOL_MAP.items()}
    for proto in get_all_protocols():
        tests = TEST_REGISTRY.get(proto, [])
        test_ids = [t["test_id"] for t in tests]
        protocols[proto.upper()] = {
            "port": proto_port_map.get(proto, 0),
            "tests": len(tests),
            "test_ids": test_ids,
            "description": f"Vulnerability tests for {proto.upper()} protocol",
        }
    # Banner grabbing special case
    if "banner_grabbing" in TEST_REGISTRY:
        tests = TEST_REGISTRY["banner_grabbing"]
        protocols["Banner Grabbing"] = {
            "port": "any",
            "tests": len(tests),
            "test_ids": [t["test_id"] for t in tests],
            "description": "Service fingerprinting via banner grabbing",
        }

    # Docker containers
    containers = []
    try:
        for c in docker_client.containers.list():
            info = {
                "name": c.name,
                "ip": None,
                "ports": [],
                "protocol": None,
                "tech": c.image.tags[0] if c.image.tags else "unknown",
                "description": f"Docker container: {c.name}",
                "role": "infrastructure",
            }

            # Try to get IP from network settings
            try:
                networks = c.attrs.get("NetworkSettings", {}).get("Networks", {})
                for net_name, net_info in networks.items():
                    if net_info.get("IPAddress"):
                        info["ip"] = net_info["IPAddress"]
                        break
            except Exception:
                pass

            # Classify container role
            infra_names = {"dashboard_ui", "dashboard_api", "scanner", "h2o-automl"}
            if c.name not in infra_names:
                info["role"] = "vulnerable_device"
                # Guess protocol from container name
                for proto_name in ["ftp", "http", "ssh", "telnet", "mqtt", "rtsp", "coap", "modbus", "dns"]:
                    if proto_name in c.name.lower():
                        info["protocol"] = proto_name.upper()
                        info["ports"] = [proto_port_map.get(proto_name, 0)]
                        break

            containers.append(info)
    except Exception:
        pass

    # API endpoints
    api_endpoints = [
        {
            "method": "GET", "path": "/", "summary": "Health check",
            "description": "Returns service status and name.",
            "category": "Health",
            "response_example": {"status": "ok", "service": "Emergence IoT Test Case Generator API"},
        },
        {
            "method": "POST", "path": "/api/scan", "summary": "Start network scan",
            "description": "Triggers an Nmap scan on the specified network via the scanner Docker container.",
            "category": "Scanning",
            "request_body": {
                "network": {"type": "string", "default": "172.20.0.0/27", "description": "CIDR network range to scan"},
                "extra_ports": {"type": "string", "default": None, "description": "Comma-separated extra ports"},
            },
            "response_example": {"status": "started", "network": "172.20.0.0/27"},
        },
        {
            "method": "GET", "path": "/api/scan/status", "summary": "Scan progress",
            "description": "Returns the current scan status (idle, running, completed, error).",
            "category": "Scanning",
            "response_example": {"status": "completed", "devices": []},
        },
        {
            "method": "GET", "path": "/api/scan/results", "summary": "Scan results",
            "description": "Returns discovered devices from the last scan.",
            "category": "Scanning",
        },
        {
            "method": "POST", "path": "/api/devices", "summary": "Add device manually",
            "description": "Adds a device to the inventory with specified IP and ports.",
            "category": "Devices",
            "request_body": {
                "ip": {"type": "string", "description": "Device IP address"},
                "ports": {"type": "array", "description": "List of open port numbers"},
            },
        },
        {
            "method": "GET", "path": "/api/devices", "summary": "List all devices",
            "description": "Returns merged list of scanned and manually-added devices.",
            "category": "Devices",
        },
        {
            "method": "DELETE", "path": "/api/devices/{ip}", "summary": "Remove a device",
            "description": "Removes a manually-added device by IP address.",
            "category": "Devices",
        },
        {
            "method": "POST", "path": "/api/generate", "summary": "Generate test suite",
            "description": "Generates a test suite for selected devices and protocols. Uses static registry and ML risk scoring.",
            "category": "Generation",
            "request_body": {
                "devices": {"type": "array", "description": "List of {ip, ports} objects"},
                "protocols": {"type": "array", "default": None, "description": "Protocols to test (null = all detected)"},
                "include_uncommon": {"type": "boolean", "default": True, "description": "Include uncommon tests"},
                "severity_filter": {"type": "array", "default": None, "description": "Filter by severity levels"},
                "name": {"type": "string", "default": "", "description": "Suite name"},
            },
        },
        {
            "method": "GET", "path": "/api/suites", "summary": "List test suites",
            "description": "Returns all generated test suites with summary metadata.",
            "category": "Generation",
        },
        {
            "method": "GET", "path": "/api/suites/{id}", "summary": "Get suite detail",
            "description": "Returns full test suite with all test cases.",
            "category": "Generation",
        },
        {
            "method": "GET", "path": "/api/suites/{id}/export", "summary": "Export suite",
            "description": "Export test suite in JSON, YAML, or Python (pytest) format.",
            "category": "Generation",
            "parameters": [
                {"name": "format", "type": "string", "default": "json", "description": "Export format: json, yaml, or python"},
            ],
        },
        {
            "method": "DELETE", "path": "/api/suites/{id}", "summary": "Delete suite",
            "description": "Permanently deletes a generated test suite.",
            "category": "Generation",
        },
        {
            "method": "POST", "path": "/api/suites/{id}/run", "summary": "Run test suite",
            "description": "Executes test suite against target devices via the scanner container.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/suites/{id}/run/status", "summary": "Run progress",
            "description": "Returns execution progress for the currently running suite.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/results", "summary": "List results",
            "description": "Returns all past execution results.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/results/{filename}", "summary": "Get result detail",
            "description": "Returns detailed execution result by filename.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/ml/status", "summary": "ML model status",
            "description": "Returns whether the selected AutoML model is trained and its metrics. Query param: automl_tool (h2o, autogluon, pycaret, tpot, autosklearn).",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/ml/metrics", "summary": "ML metrics",
            "description": "Returns model performance metrics (AUC, feature importance, etc.) for the selected framework. Query param: automl_tool.",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/ml/metrics/all", "summary": "All framework metrics",
            "description": "Returns model metrics for ALL trained frameworks in a single response.",
            "category": "ML",
        },
        {
            "method": "POST", "path": "/api/ml/retrain", "summary": "Retrain model",
            "description": "Triggers AutoML model retraining. Query param: automl_tool selects which framework to train.",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/automl/frameworks", "summary": "List AutoML frameworks",
            "description": "Returns all registered AutoML frameworks with availability and model status.",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/automl/frameworks/available", "summary": "Available frameworks",
            "description": "Returns only the frameworks that are currently reachable (Docker containers running).",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/automl/comparison", "summary": "Framework comparison",
            "description": "Compare AUC, accuracy, training time across all trained frameworks.",
            "category": "ML",
        },
        {
            "method": "POST", "path": "/api/automl/train-all", "summary": "Train all frameworks",
            "description": "Train all available AutoML frameworks on aggregated history data.",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/history/summary", "summary": "History KPIs",
            "description": "Aggregate KPIs (total tests, vulns, detection rate, protocols tested).",
            "category": "History",
        },
        {
            "method": "GET", "path": "/api/history/vulns-by-protocol", "summary": "Vulns by protocol",
            "description": "Vulnerability counts grouped by protocol.",
            "category": "History",
        },
        {
            "method": "GET", "path": "/api/history/vulns-by-type", "summary": "Vulns by type",
            "description": "Vulnerability counts grouped by test type.",
            "category": "History",
        },
        {
            "method": "GET", "path": "/api/history/vulns-by-device", "summary": "Vulns by device",
            "description": "Vulnerability counts grouped by device IP.",
            "category": "History",
        },
        {
            "method": "GET", "path": "/api/logs", "summary": "Docker logs",
            "description": "Returns logs from all Docker containers.",
            "category": "Logs",
            "parameters": [
                {"name": "tail", "type": "int", "default": 80, "description": "Number of log lines"},
                {"name": "filter", "type": "string", "default": None, "description": "Container name filter"},
            ],
        },
        {
            "method": "GET", "path": "/api/docker-ps", "summary": "Container list",
            "description": "Returns running Docker containers and their status.",
            "category": "Logs",
        },
        {
            "method": "GET", "path": "/api/protocols", "summary": "Available protocols",
            "description": "Returns all supported protocols, test counts, and OWASP mappings.",
            "category": "Architecture",
        },
        # ── Train-Loop endpoints ──
        {
            "method": "POST", "path": "/api/suites/{id}/train-loop",
            "summary": "Start auto-train loop",
            "description": "Starts an iterative execute-retrain loop: runs the test suite, optionally retrains the ML model, and repeats. Supports environment simulation profiles and configurable training frequency.",
            "category": "Execution",
            "request_body": {
                "iterations": {"type": "integer", "default": 3, "description": "Number of execute cycles (1–100)"},
                "train_every_n": {"type": "integer", "default": 0, "description": "Train every Nth iteration (0 = only after last, 1 = every iter, N = every Nth + last)"},
                "simulation_mode": {"type": "string", "default": "deterministic", "description": "Simulation profile: deterministic, easy, medium, hard, realistic, or custom"},
                "simulation_seed": {"type": "integer", "default": 42, "description": "RNG seed for reproducible simulation events"},
                "simulation_config": {"type": "object", "default": None, "description": "Custom probability overrides (only when mode=custom)"},
            },
            "response_example": {"status": "started", "suite_id": "abc123", "total_iterations": 3, "train_every_n": 0},
        },
        {
            "method": "GET", "path": "/api/suites/{id}/train-loop/status",
            "summary": "Train loop status",
            "description": "Returns current train loop progress including iteration count, phase, per-iteration metrics, and simulation events.",
            "category": "Execution",
        },
        {
            "method": "POST", "path": "/api/suites/{id}/train-loop/cancel",
            "summary": "Cancel train loop",
            "description": "Gracefully cancels a running train loop after the current iteration completes. Restores simulation environment to original state.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/run/active",
            "summary": "Active run status",
            "description": "Global run status without suite_id. Used to resume UI polling after tab switches.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/loop/active",
            "summary": "Active loop status",
            "description": "Global train loop status without suite_id. Used to resume UI polling after tab switches.",
            "category": "Execution",
        },
        {
            "method": "GET", "path": "/api/ml/retrain/status",
            "summary": "Retrain status",
            "description": "Returns the current status of an in-progress ML model retrain operation.",
            "category": "ML",
        },
        # ── Hypothesis endpoints ──
        {
            "method": "GET", "path": "/api/hypothesis/iteration-metrics",
            "summary": "Iteration metrics (H1/H3)",
            "description": "Per-experiment detection rates and metrics over time for hypothesis validation. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode: deterministic, realistic, or null for all"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/model-evolution",
            "summary": "Model evolution",
            "description": "ML model performance snapshot (AUC, feature importance, ROC curve).",
            "category": "Hypothesis",
        },
        {
            "method": "GET", "path": "/api/hypothesis/composition-analysis",
            "summary": "Composition analysis",
            "description": "Effectiveness of test strategies and composition rules.",
            "category": "Hypothesis",
        },
        {
            "method": "GET", "path": "/api/hypothesis/statistical-tests",
            "summary": "Detection rate stability (H1)",
            "description": "Spearman, Mann-Whitney U, Cohen's d for H1 detection-rate stability hypothesis. Tests whether detection rates remain stable over iterations. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/recommendation-effectiveness",
            "summary": "Recommendation effectiveness (H2)",
            "description": "Compares ML-recommended vs non-recommended test detection rates using Fisher's exact test and threshold sweep analysis. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/protocol-convergence",
            "summary": "Protocol convergence (H3)",
            "description": "Analyses per-protocol detection rate convergence across iterations using Spearman rank correlation and slope estimation. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/risk-calibration",
            "summary": "Risk calibration (H4)",
            "description": "Analyses calibration of ML-predicted risk scores vs observed vulnerability rates using calibration curves and Brier score. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/execution-efficiency",
            "summary": "Execution efficiency (H5)",
            "description": "Compares detection coverage of ML-recommended subset vs full suite, computing efficiency ratio and theoretical time savings. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/discovery-coverage",
            "summary": "Discovery coverage (H6)",
            "description": "Compares unique vulnerability discovery across simulation modes using Kruskal-Wallis and pairwise Mann-Whitney U tests. Tests whether dynamic modes expose more unique patterns. Supports simulation_mode filter.",
            "category": "Hypothesis",
            "parameters": [
                {"name": "simulation_mode", "type": "string", "default": None, "description": "Filter by simulation mode"},
            ],
        },
        {
            "method": "GET", "path": "/api/hypothesis/available-simulation-modes",
            "summary": "Available simulation modes",
            "description": "Returns distinct simulation_mode values found in history data. Used by Hypothesis tab to populate filter dropdown.",
            "category": "Hypothesis",
        },
        {
            "method": "GET", "path": "/api/hypothesis/debug-experiments",
            "summary": "Debug experiments",
            "description": "Debug endpoint to inspect experiment directories, history files, and data integrity.",
            "category": "Hypothesis",
        },
        # ── Simulation endpoints ──
        {
            "method": "GET", "path": "/api/simulation/profiles",
            "summary": "List simulation profiles",
            "description": "Returns all available simulation profiles (deterministic, easy, medium, hard, realistic) with descriptions and probability parameters.",
            "category": "Simulation",
            "response_example": {"profiles": [{"name": "realistic", "description": "PhD thesis primary simulation"}]},
        },
        {
            "method": "GET", "path": "/api/simulation/profiles/{name}",
            "summary": "Get simulation profile",
            "description": "Returns a specific simulation profile by name with full configuration including probabilities and academic use case.",
            "category": "Simulation",
        },
        {
            "method": "POST", "path": "/api/simulation/preview",
            "summary": "Preview simulation (dry-run)",
            "description": "Dry-run a simulation to preview what events (outages, patches, credential rotations, regressions) would fire across iterations without touching any containers. Useful to verify seed reproducibility and probability distributions.",
            "category": "Simulation",
            "request_body": {
                "mode": {"type": "string", "default": "realistic", "description": "Simulation profile name or 'custom'"},
                "seed": {"type": "integer", "default": 42, "description": "RNG seed for deterministic event generation"},
                "iterations": {"type": "integer", "default": 10, "description": "Number of iterations to preview"},
                "config": {"type": "object", "default": None, "description": "Custom probability config (only when mode=custom)"},
            },
            "response_example": {"mode": "realistic", "seed": 42, "iterations": 10, "log": [], "summary": {}},
        },
    ]

    # Tech stack
    tech_stack = {
        "frontend": {
            "label": "Frontend Dashboard",
            "description": "React-based SPA for device management, test generation, and results visualization",
            "color": "blue",
            "technologies": [
                {"name": "React", "version": "18", "role": "UI framework"},
                {"name": "Vite", "version": "5", "role": "Build tool and dev server"},
                {"name": "Tailwind CSS", "version": "3", "role": "Utility-first CSS framework"},
                {"name": "Recharts", "version": "2", "role": "Data visualization charts"},
                {"name": "Lucide React", "version": "latest", "role": "Icon library"},
                {"name": "Axios", "version": "latest", "role": "HTTP client"},
            ],
            "files": ["dashboard/frontend/src/", "dashboard/frontend/vite.config.js"],
        },
        "backend": {
            "label": "Backend API",
            "description": "REST API for device scanning, test generation, suite management, and ML integration",
            "color": "purple",
            "technologies": [
                {"name": "FastAPI", "version": "latest", "role": "Web framework"},
                {"name": "Docker SDK", "version": "latest", "role": "Container orchestration"},
                {"name": "Pandas", "version": "latest", "role": "Data analysis for history aggregation"},
                {"name": "Pydantic", "version": "2", "role": "Request/response validation"},
                {"name": "Jinja2", "version": "latest", "role": "Test template rendering"},
                {"name": "PyYAML", "version": "latest", "role": "YAML export format"},
            ],
            "files": ["dashboard/backend/main.py"],
        },
        "scanner": {
            "label": "Scanner & Test Engine",
            "description": "Nmap-based network scanner and vulnerability test execution engine with 10 protocol testers",
            "color": "green",
            "technologies": [
                {"name": "python-nmap", "version": "latest", "role": "Network port scanning"},
                {"name": "requests", "version": "latest", "role": "HTTP vulnerability testing"},
                {"name": "paramiko", "version": "latest", "role": "SSH testing"},
                {"name": "paho-mqtt", "version": "latest", "role": "MQTT testing"},
                {"name": "aiocoap", "version": "latest", "role": "CoAP testing"},
                {"name": "pymodbus", "version": "latest", "role": "Modbus TCP testing"},
            ],
            "files": ["scanners/", "vulnerability_tester/", "utils/", "templates/"],
        },
        "automl": {
            "label": "ML Intelligence Engine",
            "description": "H2O AutoML for risk scoring and live model retraining",
            "color": "amber",
            "technologies": [
                {"name": "H2O-3", "version": "latest", "role": "AutoML model training and prediction"},
                {"name": "GBM/XGBoost", "version": "N/A", "role": "Gradient boosting classifiers"},
                {"name": "Pandas", "version": "latest", "role": "Feature engineering and data prep"},
            ],
            "files": ["automl/", "generator/scorer.py", "generator/retrain.py"],
        },
        "devices": {
            "label": "Vulnerable IoT Lab",
            "description": "Docker-based lab with intentionally vulnerable IoT devices for testing and demos",
            "color": "red",
            "technologies": [
                {"name": "Docker Compose", "version": "latest", "role": "Multi-container orchestration"},
                {"name": "vsftpd", "version": "2.3.4", "role": "FTP with backdoor vulnerability"},
                {"name": "OpenSSH", "version": "various", "role": "SSH with weak configurations"},
                {"name": "Mosquitto", "version": "latest", "role": "MQTT broker (open access)"},
                {"name": "lighttpd", "version": "latest", "role": "HTTP with misconfigurations"},
                {"name": "BIND9", "version": "latest", "role": "DNS with open resolver"},
            ],
            "files": ["docker-compose.yml", "Dockerfile.*"],
        },
        "simulation": {
            "label": "Environment Simulation Layer",
            "description": "Probability-based IoT lab mutation for realistic train-loop testing with reproducible RNG",
            "color": "teal",
            "technologies": [
                {"name": "EnvironmentSimulator", "version": "N/A", "role": "Orchestrates per-iteration Docker container manipulation (outages, patches, cred rotations)"},
                {"name": "SimulationConfig", "version": "N/A", "role": "Dataclass with 6 probability parameters and safety constraints"},
                {"name": "Simulation Profiles", "version": "N/A", "role": "5 named presets (deterministic, easy, medium, hard, realistic) for academic experiments"},
                {"name": "PATCHABLE_VULNS", "version": "N/A", "role": "Registry of 15 vulnerability patches across 10 containers with Docker exec commands"},
                {"name": "ROTATABLE_CREDS", "version": "N/A", "role": "Registry of 3 credential rotation targets (Telnet, HTTP, FTP)"},
                {"name": "FP/FN Noise Layer", "version": "N/A", "role": "Post-execution noise injection in suite_runner for false positives/negatives"},
            ],
            "files": ["simulation/", "simulation/config.py", "simulation/profiles.py", "simulation/actions.py", "simulation/environment.py"],
        },
        "infrastructure": {
            "label": "Generator Framework",
            "description": "Core test case generation pipeline: registry, engine, scorer, exporter",
            "color": "gray",
            "technologies": [
                {"name": "Test Registry", "version": "N/A", "role": f"Unified registry with {get_total_test_count()} vulnerability tests"},
                {"name": "Generation Engine", "version": "N/A", "role": "Matches devices to relevant tests from registry"},
                {"name": "ML Composer", "version": "N/A", "role": "Generates new test variants using composition rules"},
                {"name": "Risk Scorer", "version": "N/A", "role": "Scores tests by ML-predicted vulnerability probability"},
                {"name": "Exporter", "version": "N/A", "role": "Exports to JSON, YAML, and executable Python (pytest)"},
            ],
            "files": ["generator/", "models/", "templates/"],
        },
    }

    # Pipeline phases (replaces old experiment flow)
    pipeline_phases = [
        {
            "id": 1, "name": "Network Discovery", "icon": "Radar", "color": "blue",
            "description": "Scan the target network or manually add IoT devices.",
            "details": "Uses Nmap via Docker to scan a CIDR range and discover live hosts with open ports. Devices can also be added manually with IP and port specification. Each discovered device gets protocol classification based on its open ports.",
            "inputs": ["CIDR network range", "Manual device entries"],
            "outputs": ["Device inventory with IPs, ports, protocols"],
            "module": "scanners/nmap_scanner.py",
        },
        {
            "id": 2, "name": "Protocol Selection", "icon": "Shield", "color": "green",
            "description": "Select which protocols and severity levels to test.",
            "details": "Users choose which protocols to generate tests for (auto-suggested based on discovered ports). Options include severity filtering, common/uncommon test inclusion, and ML generation mode (conservative/balanced/aggressive).",
            "inputs": ["Device inventory", "User protocol selection"],
            "outputs": ["Generation parameters"],
            "module": "dashboard/frontend/src/components/TestGenerator.jsx",
        },
        {
            "id": 3, "name": "Static Test Generation", "icon": "ListChecks", "color": "green",
            "description": "Generate test cases from the unified test registry.",
            "details": f"The test registry contains {get_total_test_count()} vulnerability tests across {len(get_all_protocols())} protocols. For each selected device and protocol, relevant tests are instantiated as TestCase objects with target IP, port, description, OWASP mapping, and severity.",
            "inputs": ["Generation parameters", "Test Registry"],
            "outputs": ["Base test suite (static tests)"],
            "module": "generator/engine.py",
        },
        {
            "id": 4, "name": "Risk Scoring", "icon": "Zap", "color": "amber",
            "description": "Score all tests by ML-predicted vulnerability probability.",
            "details": "Uses a trained H2O AutoML model to predict the likelihood of each test finding a vulnerability. Features include port count, protocol diversity, authentication requirements, and test type. Tests are sorted by risk score and high-confidence ones marked as 'recommended'.",
            "inputs": ["Complete test suite", "Trained H2O model"],
            "outputs": ["Risk-scored and ranked test suite"],
            "module": "generator/scorer.py",
        },
        {
            "id": 5, "name": "Export & Execute", "icon": "ListChecks", "color": "blue",
            "description": "View, export, or execute the generated test suite.",
            "details": "Test suites can be exported as structured JSON, YAML specs, or executable Python pytest scripts (rendered via Jinja2 templates). Suites can also be executed directly against target devices, with results logged for ML model improvement.",
            "inputs": ["Scored test suite"],
            "outputs": ["Exported files (JSON/YAML/Python)", "Execution results"],
            "module": "generator/exporter.py",
        },
        {
            "id": 6, "name": "Environment Simulation", "icon": "Dices", "color": "teal",
            "description": "Mutate the IoT lab between train-loop iterations for realistic testing.",
            "details": "The simulation layer wraps each train-loop iteration with probabilistic environment changes. Before execution, Bernoulli trials decide which containers go offline (service outages), which vulnerabilities get patched, and which credentials are rotated. After execution, changes are restored. A separate FP/FN noise layer in the test runner injects measurement error. All events are deterministic via seeded RNG (seed + iteration × prime) for full reproducibility. Five named profiles (deterministic, easy, medium, hard, realistic) provide preset probability configurations for academic experiments.",
            "inputs": ["Simulation profile", "RNG seed", "IoT lab containers"],
            "outputs": ["Mutated environment state", "Simulation event log", "FP/FN noise annotations"],
            "module": "simulation/environment.py",
        },
        {
            "id": 7, "name": "Learn & Improve", "icon": "Shuffle", "color": "purple",
            "description": "Retrain the ML model with new execution data for smarter future generation.",
            "details": "After test execution, results are logged to history with simulation metadata (mode, iteration). The H2O AutoML model retrains on accumulated data, with simulation columns excluded from features to keep the model blind to simulation state. The system gets smarter with every execution cycle. Hypothesis validation endpoints support filtering by simulation mode.",
            "inputs": ["Execution results", "Accumulated history.csv"],
            "outputs": ["Updated ML model", "Improved risk scores"],
            "module": "generator/retrain.py",
        },
    ]

    return {
        "containers": containers,
        "api_endpoints": api_endpoints,
        "protocols": protocols,
        "tech_stack": tech_stack,
        "pipeline_phases": pipeline_phases,
    }


# ═══════════════════════════════════════════════════════════════════════
# SCANNING & DEVICES
# ═══════════════════════════════════════════════════════════════════════

@app.post("/api/scan")
def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    with _scan_lock:
        if _scan_state["status"] == "running":
            return {"status": "error", "message": "Scan already running"}

        _scan_state["status"] = "running"
        _scan_state["started_at"] = datetime.now().isoformat()
        _scan_state["devices"] = []
        _scan_state["error"] = None

    def _do_scan():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            cmd = f"python3 -c \"from scanners.nmap_scanner import explore; import argparse; args=argparse.Namespace(network='{req.network}', ports='{req.extra_ports or ''}', verbose=False); devices=explore(args); import json; print(json.dumps([{{'ip':d.ip,'mac':d.mac,'hostname':d.hostname,'ports':d.ports,'is_iot':d.is_iot,'os':d.os,'device_type':d.device_type}} for d in devices]))\""

            exit_code, output = container.exec_run(cmd, demux=False)
            output_str = output.decode(errors="ignore").strip()

            # Parse JSON output from the last line
            lines = output_str.split("\n")
            json_line = ""
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("["):
                    json_line = line
                    break

            if json_line:
                devices = json.loads(json_line)
            else:
                devices = []

            with _scan_lock:
                _scan_state["status"] = "completed"
                _scan_state["devices"] = devices

        except Exception as e:
            with _scan_lock:
                _scan_state["status"] = "error"
                _scan_state["error"] = str(e)

    background_tasks.add_task(_do_scan)
    return {"status": "started", "network": req.network}


@app.get("/api/scan/status")
def scan_status():
    with _scan_lock:
        return dict(_scan_state)


@app.get("/api/scan/results")
def scan_results():
    with _scan_lock:
        return {"devices": _scan_state.get("devices", []), "status": _scan_state["status"]}


@app.post("/api/devices")
def add_device(device: DeviceInput):
    from utils.protocols import PORT_PROTOCOL_MAP

    protocols = sorted(set(
        PORT_PROTOCOL_MAP.get(p, "generic")
        for p in device.ports
        if PORT_PROTOCOL_MAP.get(p) is not None
    ))

    dev = {
        "ip": device.ip,
        "mac": None,
        "hostname": None,
        "ports": device.ports,
        "is_iot": True,
        "os": None,
        "device_type": "manual",
        "protocols": protocols,
    }

    with _devices_lock:
        # Replace if same IP exists
        _manual_devices[:] = [d for d in _manual_devices if d["ip"] != device.ip]
        _manual_devices.append(dev)

    return {"status": "ok", "device": dev}


@app.get("/api/devices")
def list_devices():
    with _scan_lock:
        scanned = _scan_state.get("devices", [])
    with _devices_lock:
        manual = list(_manual_devices)

    # Merge: scanned + manual (manual overrides same IP)
    all_ips = set()
    merged = []
    for d in manual:
        all_ips.add(d["ip"])
        merged.append({**d, "source": "manual"})
    for d in scanned:
        if d["ip"] not in all_ips:
            merged.append({**d, "source": "scanned"})

    return {"devices": merged, "total": len(merged)}


@app.delete("/api/devices/{ip}")
def remove_device(ip: str):
    with _devices_lock:
        before = len(_manual_devices)
        _manual_devices[:] = [d for d in _manual_devices if d["ip"] != ip]
        removed = before - len(_manual_devices)
    return {"status": "ok", "removed": removed}


# ═══════════════════════════════════════════════════════════════════════
# TEST GENERATION
# ═══════════════════════════════════════════════════════════════════════

_PROTOCOL_DEFAULT_PORTS_GEN = {
    "http": 80, "https": 443, "ftp": 21, "ssh": 22, "telnet": 23,
    "mqtt": 1883, "coap": 5683, "modbus": 502, "dnp3": 20000,
    "bacnet": 47808, "upnp": 1900, "rtsp": 554, "snmp": 161,
    "amqp": 5672, "opcua": 4840, "zigbee": 0, "ble": 0,
    "banner_grabbing": 0,
}


def _llm_dict_to_testcase_gen(llm_test: dict, target_ip: str = "127.0.0.1") -> TestCase:
    """Convert LLM generator output dict to a TestCase object (for /api/generate)."""
    tid = llm_test.get("test_id", "")
    parts = tid.replace("llm_", "", 1).split("_")
    protocol = parts[0] if parts and parts[0] in _PROTOCOL_DEFAULT_PORTS_GEN else "unknown"
    if protocol == "unknown":
        code = llm_test.get("pytest_code", "").lower()
        for proto in _PROTOCOL_DEFAULT_PORTS_GEN:
            if proto in code:
                protocol = proto
                break
    port = _PROTOCOL_DEFAULT_PORTS_GEN.get(protocol, 0)
    return TestCase(
        test_id=llm_test["test_id"],
        test_name=llm_test.get("test_name", llm_test["test_id"]),
        protocol=protocol,
        target_ip=target_ip,
        port=port,
        description=llm_test.get("description", "LLM-generated test"),
        severity=llm_test.get("severity", "medium"),
        vulnerability_type=llm_test.get("vulnerability_type", "unknown"),
        owasp_iot_category=llm_test.get("owasp_iot_category", "I1: Insecure Web Interface"),
        test_origin="llm",
        pytest_code=llm_test.get("pytest_code"),
    )


def _generate_llm_tests_for_suite(suite: TestSuite, devices: list[dict], provider: str = "claude") -> int:
    """Generate LLM tests and append to suite. Returns count of tests added."""
    try:
        from generator.llm_generator import LLMTestGenerator
        llm_gen = LLMTestGenerator(provider=provider)
        if not llm_gen.is_available():
            logging.info("[API] LLM generator not available (no API key)")
            return 0

        existing_ids = [tc.test_id for tc in suite.test_cases]
        added = 0
        for dev in devices:
            ip = dev.get("ip", "127.0.0.1")
            ports = dev.get("ports", [])
            # Infer protocols from existing test cases for this device
            protos = list({
                tc.protocol for tc in suite.test_cases
                if tc.target_ip == ip and tc.protocol != "unknown"
            })
            if not protos:
                protos = ["http"]
            new_tests = llm_gen.generate_tests_for_device(
                device_ip=ip,
                open_ports=ports,
                protocols=protos,
                existing_tests=existing_ids,
                max_tests=5,
            )
            for lt in new_tests:
                tc = _llm_dict_to_testcase_gen(lt, target_ip=ip)
                suite.test_cases.append(tc)
                existing_ids.append(tc.test_id)
                added += 1
        logging.info(f"[API] LLM generation added {added} tests across {len(devices)} devices")
        return added
    except Exception as e:
        logging.warning(f"[API] LLM generation failed (non-fatal): {e}")
        return 0


@app.post("/api/generate")
def generate_tests(req: GenerateRequest):
    """Generate or enhance a test suite for the selected devices and protocols."""
    if not req.devices:
        raise HTTPException(400, "No devices provided")

    # Step 1: Compute fingerprint for this configuration (includes automl_tool
    # so switching frameworks always creates a fresh suite).
    fingerprint = _compute_suite_fingerprint(
        req.devices, req.protocols, req.severity_filter, req.include_uncommon,
        automl_tool=req.automl_tool,
    )

    # Step 2: Check for existing matching suite (unless force_new)
    existing = None
    if not req.force_new:
        existing = _find_matching_suite(fingerprint)

    if existing:
        # ── ENHANCE existing suite ──────────────────────────────────────
        suite = TestSuite.from_dict(existing)

        # Update name if user provided a new one
        if req.name:
            suite.name = req.name

        # Detect new tests from registry that aren't in the suite yet
        fresh_suite = generate_test_suite(
            devices=req.devices,
            selected_protocols=req.protocols,
            severity_filter=req.severity_filter,
            include_uncommon=req.include_uncommon,
            name="",
        )
        existing_keys = {
            (tc.test_id, tc.target_ip, tc.port) for tc in suite.test_cases
        }
        new_tests = [
            tc for tc in fresh_suite.test_cases
            if (tc.test_id, tc.target_ip, tc.port) not in existing_keys
        ]
        if new_tests:
            suite.test_cases.extend(new_tests)

        # ── LLM test generation (enhance path) ──
        llm_added = 0
        if req.llm_enabled:
            llm_added = _generate_llm_tests_for_suite(suite, req.devices, provider=req.llm_provider)

        # Re-score ALL tests with the latest ML model
        try:
            suite = score_test_suite(suite, automl_tool=req.automl_tool)
        except Exception as e:
            logging.warning(f"[API] Scorer error during enhancement (non-fatal): {e}")

        # Update metadata
        enhancement_count = suite.metadata.get("enhancement_count", 0) + 1
        suite.metadata["enhancement_count"] = enhancement_count
        suite.metadata["last_enhanced_at"] = datetime.utcnow().isoformat()
        suite.metadata["tests_added_on_enhance"] = len(new_tests) + llm_added
        suite.metadata["llm_tests_added"] = llm_added
        suite.metadata["fingerprint"] = fingerprint
        suite.metadata["automl_tool"] = req.automl_tool

        _save_suite(suite)

        result = suite.to_dict()
        result["action"] = "enhanced"
        result["tests_added"] = len(new_tests)
        return result
    else:
        # ── CREATE new suite ────────────────────────────────────────────
        suite = generate_test_suite(
            devices=req.devices,
            selected_protocols=req.protocols,
            severity_filter=req.severity_filter,
            include_uncommon=req.include_uncommon,
            name=req.name,
        )

        # ── LLM test generation (create path) ──
        llm_added = 0
        if req.llm_enabled:
            llm_added = _generate_llm_tests_for_suite(suite, req.devices, provider=req.llm_provider)

        try:
            suite = score_test_suite(suite, automl_tool=req.automl_tool)
        except Exception as e:
            logging.warning(f"[API] Scorer error (non-fatal): {e}")

        # Set fingerprint and initial metadata
        suite.metadata["fingerprint"] = fingerprint
        suite.metadata["enhancement_count"] = 0
        suite.metadata["last_enhanced_at"] = None
        suite.metadata["tests_added_on_enhance"] = 0
        suite.metadata["llm_tests_added"] = llm_added
        suite.metadata["automl_tool"] = req.automl_tool

        _save_suite(suite)

        result = suite.to_dict()
        result["action"] = "created"
        result["tests_added"] = 0
        return result


@app.get("/api/suites")
def list_suites():
    suites = []
    trained = _get_ever_trained_frameworks()
    if os.path.exists(SUITES_PATH):
        for fname in sorted(os.listdir(SUITES_PATH), reverse=True):
            if fname.endswith(".json"):
                fpath = os.path.join(SUITES_PATH, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    meta = data.get("metadata", {})

                    # Clear stale recommended_count for untrained frameworks
                    automl = meta.get("automl_tool") or "h2o"
                    rec_count = data.get("recommended_count", 0)
                    if automl != "h2o" and automl not in trained:
                        rec_count = 0

                    suites.append({
                        "suite_id": data.get("suite_id"),
                        "name": data.get("name"),
                        "created_at": data.get("created_at"),
                        "total_tests": data.get("total_tests", 0),
                        "protocols": data.get("protocols", []),
                        "recommended_count": rec_count,
                        "device_count": len(data.get("devices", [])),
                        "enhancement_count": meta.get("enhancement_count", 0),
                        "last_enhanced_at": meta.get("last_enhanced_at"),
                        "fingerprint": meta.get("fingerprint"),
                        "automl_tool": automl,
                    })
                except Exception:
                    continue

    return {"suites": suites}


@app.get("/api/suites/{suite_id}")
def get_suite(suite_id: str):
    suite_data = _load_suite(suite_id)
    if not suite_data:
        raise HTTPException(404, f"Suite {suite_id} not found")
    return _validate_suite_scores(suite_data)


@app.get("/api/suites/{suite_id}/export")
def export_suite(suite_id: str, format: str = "json"):
    suite_data = _load_suite(suite_id)
    if not suite_data:
        raise HTTPException(404, f"Suite {suite_id} not found")

    suite = TestSuite.from_dict(suite_data)

    if format == "json":
        return PlainTextResponse(export_json(suite), media_type="application/json")
    elif format == "yaml":
        return PlainTextResponse(export_yaml(suite), media_type="text/yaml")
    elif format == "python":
        return PlainTextResponse(export_python(suite), media_type="text/x-python")
    else:
        raise HTTPException(400, f"Unsupported format: {format}. Use json, yaml, or python.")


@app.delete("/api/suites/{suite_id}")
def delete_suite(suite_id: str):
    fpath = os.path.join(SUITES_PATH, f"suite_{suite_id}.json")
    if os.path.exists(fpath):
        os.remove(fpath)
        return {"status": "ok", "deleted": suite_id}
    raise HTTPException(404, f"Suite {suite_id} not found")


# ═══════════════════════════════════════════════════════════════════════
# TEST EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def _execute_suite_and_retrain(
    suite_id: str,
    suite: "TestSuite",
    on_phase: "Optional[callable]" = None,
    simulation_context: "Optional[dict]" = None,
    skip_training: bool = False,
    automl_tool: str = "h2o",
    temporal_training: bool = False,
    baseline_strategy: Optional[str] = None,
    llm_enabled: bool = False,
    phase_tag: Optional[str] = None,
    dynamic_features: bool = False,
) -> dict:
    """Core run + retrain logic shared by single-run and auto-train loop.

    *on_phase* is an optional ``(phase: str) -> None`` callback so the
    caller (e.g. the loop) can track the current phase ("running" →
    "training").

    *simulation_context* is an optional dict with simulation parameters
    (mode, seed, iteration, false_positive_rate, false_negative_rate)
    that gets passed to the suite runner for FP/FN noise injection.

    *skip_training* when True skips Phase 2 (retrain) and Phase 3
    (re-score), only executing the suite. Used by train_every_n to
    batch executions before training.

    Returns ``{"run_result": dict, "retrain_result": dict | None}``.
    """
    retrain_result = None

    try:
        # ── Phase 1: Execute suite via Docker ──────────────────────────
        if on_phase:
            on_phase("running")

        with _run_lock:
            _run_state["status"] = "running"
            _run_state["suite_id"] = suite_id
            _run_state["started_at"] = datetime.now().isoformat()
            _run_state["finished_at"] = None
            _run_state["progress"] = 0
            _run_state["total_tests"] = suite.total_tests
            _run_state["error"] = None

        container = docker_client.containers.get(SCANNER_CONTAINER_NAME)

        # Write simulation context to shared volume for the scanner to pick up
        _sim_context_path = os.path.join("/app", "simulation", "runner_context.json")
        try:
            os.makedirs(os.path.dirname(_sim_context_path), exist_ok=True)
            if simulation_context:
                with open(_sim_context_path, "w") as _sf:
                    json.dump(simulation_context, _sf)
            elif os.path.exists(_sim_context_path):
                os.remove(_sim_context_path)
        except Exception as e:
            logging.warning(f"[API] Could not write simulation context: {e}")

        cmd = (
            f"python3 -c \""
            f"import json, sys; "
            f"sys.path.insert(0, '/app'); "
            f"from utils.suite_runner import run_suite_from_json; "
            f"result = run_suite_from_json('{os.path.join(SUITES_PATH, f'suite_{suite_id}.json')}'); "
            f"print(json.dumps(result))"
            f"\""
        )

        # Retry up to 3 times: Docker Desktop on Windows occasionally returns
        # exit_code=None when the socket is busy (e.g. during container restarts).
        _max_exec_retries = 3
        for _exec_attempt in range(_max_exec_retries):
            exit_code, output = container.exec_run(cmd, demux=False)
            if exit_code is not None:
                break
            if _exec_attempt < _max_exec_retries - 1:
                logging.warning(
                    f"[API] exec_run returned None exit code (attempt {_exec_attempt + 1}), retrying in 10s..."
                )
                time.sleep(10)
        output_str = output.decode(errors="ignore").strip()

        if exit_code != 0:
            logging.error(f"[API] Scanner exited with code {exit_code}")
            result = {
                "status": "error",
                "error": f"Scanner exited with code {exit_code}",
                "output": output_str[-2000:] if len(output_str) > 2000 else output_str,
                "tests_executed": 0,
                "vulns_detected": 0,
            }
        else:
            result = {"status": "completed", "output": output_str}
            try:
                lines = output_str.split("\n")
                for line in reversed(lines):
                    if line.strip().startswith("{"):
                        result = json.loads(line.strip())
                        break
            except Exception:
                pass

        # Save result
        result["suite_id"] = suite_id
        result["finished_at"] = datetime.now().isoformat()
        result["automl_tool"] = automl_tool
        if simulation_context:
            result["simulation_mode"] = simulation_context.get("mode")
            result["simulation_seed"] = simulation_context.get("seed")
            result["simulation_iteration"] = simulation_context.get("iteration")
        result_path = os.path.join(RESULTS_PATH, f"result_{suite_id}_{int(time.time())}.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        # Tag the history CSV with automl_tool so hypothesis endpoints can
        # filter by framework. Old files without this column are treated as h2o.
        exp_dir = result.get("experiment_dir")
        history_csv = result.get("history_csv")
        if history_csv and os.path.exists(str(history_csv)):
            try:
                _hdf = pd.read_csv(history_csv)
                _hdf["automl_tool"] = automl_tool
                # Tag baseline_strategy so H9 can distinguish ML vs baseline experiments
                _bs = baseline_strategy if baseline_strategy else "ml_guided"
                _hdf["baseline_strategy"] = _bs
                # Tag phase, test_origin, score_method so H9/H10/synthesis can filter
                _NON_ML_BS = {"random", "cvss_priority", "round_robin", "no_ml"}
                if _bs in _NON_ML_BS:
                    _phase = "baseline"
                elif phase_tag:
                    # Phase 5/6 explicit label takes priority — Phase 6 has
                    # llm_enabled=True and would otherwise be misclassified.
                    _phase = phase_tag
                elif llm_enabled:
                    # Tag ALL iterations of an LLM experiment as "llm" — even
                    # early iterations before the first LLM generation fires,
                    # so they don't leak into H1-H8 framework-phase analysis.
                    _phase = "llm"
                else:
                    _phase = "framework"
                _hdf["phase"] = _phase
                _hdf["test_origin"] = _hdf["test_strategy"].apply(
                    lambda x: "llm" if x == "llm_generated" else "registry"
                )
                _hdf["score_method"] = "heuristic" if _bs in _NON_ML_BS else "ml"
                _hdf.to_csv(history_csv, index=False)
                # Mirror to DuckDB for fast dashboard queries
                if exp_dir:
                    _exp_dir_name = os.path.basename(str(exp_dir))
                    _db_insert_history(_hdf, _exp_dir_name)
                    # Invalidate caches so dashboard reflects new data immediately
                    _history_cache.clear()
                    _iteration_cache.clear()
            except Exception as e:
                logging.warning(f"[API] Could not tag history with automl_tool: {e}")

        # Log experiment directory info for debugging hypothesis data
        logging.info(f"[API] Run completed. experiment_dir={exp_dir}, history_csv={history_csv}")
        if history_csv:
            logging.info(f"[API] history_csv exists: {os.path.exists(str(history_csv))}")
        # Verify experiment files are visible to dashboard-api
        import glob as _glob
        _exp_files = _glob.glob(os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv"))
        logging.info(f"[API] Total experiment history files visible: {len(_exp_files)}")

        with _run_lock:
            _run_state["status"] = result.get("status", "completed")
            _run_state["finished_at"] = datetime.now().isoformat()
            _run_state["progress"] = suite.total_tests
            if result.get("status") == "error":
                _run_state["error"] = result.get("error", "Unknown execution error")

        # ── Phase 2: Retrain ML model (skipped when skip_training=True) ─
        if skip_training:
            logging.info(f"[API] Skipping training for suite {suite_id} (skip_training=True)")
        else:
            if on_phase:
                on_phase("training")

            try:
                from generator.retrain import (
                    retrain_model_after_execution,
                    retrain_model_temporal,
                    aggregate_history,
                )

                with _train_lock:
                    _train_state["status"] = "training"
                    _train_state["started_at"] = datetime.now().isoformat()
                    _train_state["finished_at"] = None
                    _train_state["error"] = None
                    _train_state["auc"] = None
                    _train_state["training_rows"] = None

                # Only aggregate rows from the current simulation mode, framework,
                # AND seed to avoid cross-contamination between experiments
                _sim_mode = simulation_context.get("mode") if simulation_context else None
                _sim_seed = simulation_context.get("seed") if simulation_context else None
                agg_path = aggregate_history(EXPERIMENTS_PATH, simulation_mode=_sim_mode,
                                             automl_tool=automl_tool,
                                             phase_tag=phase_tag,
                                             seed=_sim_seed)
                if not agg_path:
                    retrain_result = {"status": "error", "message": "No history data to train on"}
                    with _train_lock:
                        _train_state["status"] = "error"
                        _train_state["finished_at"] = datetime.now().isoformat()
                        _train_state["error"] = "No history data to train on"
                else:
                    _current_iter = simulation_context.get("iteration", 1) if simulation_context else 1

                    if temporal_training and _current_iter > 1:
                        # Temporal: train on iterations 1..(current-1), evaluate on current
                        retrain_result = retrain_model_temporal(
                            agg_path,
                            current_iteration=_current_iter,
                            train_iterations=range(1, _current_iter),
                            automl_tool=automl_tool,
                            dynamic=dynamic_features,
                        )
                    else:
                        # Standard: train on all accumulated data
                        retrain_result = retrain_model_after_execution(
                            agg_path, automl_tool=automl_tool,
                            dynamic=dynamic_features,
                        )

                    with _train_lock:
                        if retrain_result.get("status") in ("error", "insufficient_data"):
                            _train_state["status"] = "error"
                            _train_state["error"] = retrain_result.get("message", "Training failed")
                        else:
                            _train_state["status"] = "completed"
                            _train_state["auc"] = retrain_result.get("auc")
                            _train_state["training_rows"] = retrain_result.get("training_rows")
                        _train_state["finished_at"] = datetime.now().isoformat()
                        _train_state["automl_tool"] = automl_tool
            except Exception as e:
                logging.warning(f"[API] Retrain error (non-fatal): {e}")
                retrain_result = {"status": "error", "message": str(e)}
                with _train_lock:
                    _train_state["status"] = "error"
                    _train_state["finished_at"] = datetime.now().isoformat()
                    _train_state["error"] = str(e)

        # ── Phase 3: Re-score suite with updated model ─────────────────
        score_result = None
        if not skip_training and retrain_result and retrain_result.get("status") not in ("error", "insufficient_data"):
            if on_phase:
                on_phase("scoring")
            try:
                # Reload suite from disk (may have changed) and re-score
                suite_data = _load_suite(suite_id)
                if suite_data:
                    from generator.scorer import score_test_suite as _score

                    fresh_suite = TestSuite.from_dict(suite_data)
                    if dynamic_features and agg_path and os.path.exists(str(agg_path)):
                        import pandas as _pd
                        _hist_for_scoring = _pd.read_csv(agg_path)
                        _current_iter_for_scoring = simulation_context.get("iteration", 0) if simulation_context else 0
                        fresh_suite = _score(
                            fresh_suite, automl_tool=automl_tool,
                            history_df=_hist_for_scoring,
                            current_iter=_current_iter_for_scoring,
                        )
                    else:
                        fresh_suite = _score(fresh_suite, automl_tool=automl_tool)

                    # Update metadata to reflect auto-scoring
                    fresh_suite.metadata["last_scored_at"] = datetime.utcnow().isoformat()
                    fresh_suite.metadata["scored_with_auc"] = retrain_result.get("auc")

                    _save_suite(fresh_suite)

                    scored = sum(1 for tc in fresh_suite.test_cases if tc.risk_score is not None)
                    recommended = sum(1 for tc in fresh_suite.test_cases if tc.is_recommended)
                    score_result = {
                        "status": "scored",
                        "scored_tests": scored,
                        "recommended_tests": recommended,
                    }
                    logging.info(
                        f"[API] Suite {suite_id} auto-scored after training: "
                        f"{scored} scored, {recommended} recommended"
                    )
            except Exception as e:
                logging.warning(f"[API] Auto-score after retrain failed (non-fatal): {e}")
                score_result = {"status": "error", "message": str(e)}

        # ── Phase 4: Temporal held-out evaluation (when temporal mode is on) ─
        temporal_eval_result = None
        if temporal_training and not skip_training and retrain_result and \
                retrain_result.get("status") not in ("error", "insufficient_data"):
            try:
                from utils.temporal_eval import compute_temporal_eval
                _current_iter = simulation_context.get("iteration", 1) if simulation_context else 1
                _sim_mode = simulation_context.get("mode") if simulation_context else None

                # Load the current iteration's history data
                history_csv = result.get("history_csv")
                if history_csv and os.path.exists(str(history_csv)):
                    iter_df = pd.read_csv(history_csv)
                    iter_df["vulnerability_found"] = pd.to_numeric(
                        iter_df["vulnerability_found"], errors="coerce"
                    ).fillna(0).astype(int)

                    # Predict on held-out iteration using the model trained on past data
                    scored_iter = _predict_risk_scores_on_history(iter_df)
                    if scored_iter is not None and "predicted_risk_score" in scored_iter.columns:
                        temporal_eval_result = compute_temporal_eval(
                            scored_iter,
                            train_window_size=_current_iter - 1,
                        )
                        temporal_eval_result["iteration"] = _current_iter
                        # Track which scoring method was used for this iteration
                        if "_score_method" in scored_iter.columns:
                            temporal_eval_result["score_method"] = scored_iter["_score_method"].iloc[0]
                        logging.info(
                            f"[API] Temporal eval iter={_current_iter}: "
                            f"AUC={temporal_eval_result.get('auc_roc', '?')}, "
                            f"Brier={temporal_eval_result.get('brier_score', '?')}, "
                            f"ECE={temporal_eval_result.get('ece', '?')}, "
                            f"method={temporal_eval_result.get('score_method', '?')}"
                        )
            except Exception as e:
                logging.warning(f"[API] Temporal evaluation failed (non-fatal): {e}")

        return {
            "run_result": result,
            "retrain_result": retrain_result,
            "score_result": score_result,
            "temporal_eval": temporal_eval_result,
        }

    except Exception as e:
        with _run_lock:
            _run_state["status"] = "error"
            _run_state["error"] = str(e)
            _run_state["finished_at"] = datetime.now().isoformat()
        return {
            "run_result": {"status": "error", "error": str(e), "tests_executed": 0, "vulns_detected": 0},
            "retrain_result": None,
            "score_result": None,
        }


@app.post("/api/suites/{suite_id}/run")
def run_suite(suite_id: str, background_tasks: BackgroundTasks):
    with _run_lock:
        if _run_state["status"] == "running":
            return {"status": "error", "message": "A test suite is already running"}

    suite_data = _load_suite(suite_id)
    if not suite_data:
        raise HTTPException(404, f"Suite {suite_id} not found")

    suite = TestSuite.from_dict(suite_data)

    def _do_run():
        _execute_suite_and_retrain(suite_id, suite)

    background_tasks.add_task(_do_run)
    return {"status": "started", "suite_id": suite_id, "total_tests": suite.total_tests}


@app.get("/api/suites/{suite_id}/run/status")
def run_status(suite_id: str):
    with _run_lock:
        return dict(_run_state)


@app.get("/api/run/active")
def run_active():
    """Global run status (no suite_id needed). Used to resume UI polling after tab switch."""
    with _run_lock:
        return dict(_run_state)


@app.get("/api/loop/active")
def loop_active():
    """Global loop status (no suite_id needed). Used to resume UI polling after tab switch."""
    with _loop_lock:
        return dict(_loop_state)


# ═══════════════════════════════════════════════════════════════════════
# AUTO-TRAIN LOOP
# ═══════════════════════════════════════════════════════════════════════

_loop_lock = threading.Lock()
_loop_state = {
    "status": "idle",           # idle | running | completed | error | cancelled
    "suite_id": None,
    "current_iteration": 0,
    "total_iterations": 0,
    "phase": "idle",            # idle | running | training | between_iterations
    "started_at": None,
    "finished_at": None,
    "error": None,
    "cancelled": False,
    "iterations": [],           # per-iteration metrics
    "train_every_n": 0,         # 0 = train only last, N = every Nth + last
    "automl_tool": "h2o",       # which framework is being used
}


@app.post("/api/suites/{suite_id}/train-loop")
def start_train_loop(suite_id: str, req: TrainLoopRequest, background_tasks: BackgroundTasks):
    if req.iterations < 1 or req.iterations > 100:
        raise HTTPException(400, "Iterations must be between 1 and 100")
    if req.train_every_n < 0 or req.train_every_n > req.iterations:
        raise HTTPException(400, f"train_every_n must be between 0 and {req.iterations}")

    with _run_lock:
        if _run_state["status"] == "running":
            return {"status": "error", "message": "A test suite is already running"}
    with _loop_lock:
        if _loop_state["status"] == "running":
            return {"status": "error", "message": "An auto-train loop is already running"}

    suite_data = _load_suite(suite_id)
    if not suite_data:
        raise HTTPException(404, f"Suite {suite_id} not found")

    suite = TestSuite.from_dict(suite_data)

    # ── Build simulation config ──
    if req.simulation_mode == "custom" and req.simulation_config:
        sim_config = SimulationConfig.from_dict({
            **req.simulation_config,
            "mode": "custom",
            "seed": req.simulation_seed,
        })
    else:
        try:
            sim_config = get_profile(req.simulation_mode)
            sim_config.seed = req.simulation_seed
        except ValueError:
            raise HTTPException(400, f"Unknown simulation mode: {req.simulation_mode}")

    with _loop_lock:
        _loop_state["status"] = "running"
        _loop_state["suite_id"] = suite_id
        _loop_state["current_iteration"] = 0
        _loop_state["total_iterations"] = req.iterations
        _loop_state["phase"] = "idle"
        _loop_state["started_at"] = datetime.now().isoformat()
        _loop_state["finished_at"] = None
        _loop_state["error"] = None
        _loop_state["cancelled"] = False
        _loop_state["iterations"] = []
        _loop_state["simulation_mode"] = req.simulation_mode
        _loop_state["simulation_seed"] = req.simulation_seed
        _loop_state["train_every_n"] = req.train_every_n
        _loop_state["automl_tool"] = req.automl_tool

    # ── LLM helpers ──────────────────────────────────────────────────
    _PROTOCOL_DEFAULT_PORTS = {
        "http": 80, "https": 443, "ftp": 21, "ssh": 22, "telnet": 23,
        "mqtt": 1883, "coap": 5683, "modbus": 502, "dnp3": 20000,
        "bacnet": 47808, "upnp": 1900, "rtsp": 554, "snmp": 161,
        "amqp": 5672, "opcua": 4840, "zigbee": 0, "ble": 0,
        "banner_grabbing": 0,
    }

    def _infer_protocol(llm_test: dict) -> str:
        """Infer protocol from LLM test dict (test_id or pytest_code)."""
        tid = llm_test.get("test_id", "")
        # test_id format: llm_<protocol>_<vuln>
        parts = tid.replace("llm_", "", 1).split("_")
        if parts and parts[0] in _PROTOCOL_DEFAULT_PORTS:
            return parts[0]
        # Fallback: scan pytest_code for known protocol keywords
        code = llm_test.get("pytest_code", "").lower()
        for proto in _PROTOCOL_DEFAULT_PORTS:
            if proto in code:
                return proto
        return "unknown"

    def _infer_port(protocol: str) -> int:
        return _PROTOCOL_DEFAULT_PORTS.get(protocol, 0)

    def _llm_dict_to_testcase(llm_test: dict, target_ip: str = "127.0.0.1") -> TestCase:
        """Convert LLM generator output dict to a TestCase object."""
        protocol = _infer_protocol(llm_test)
        port = _infer_port(protocol)
        return TestCase(
            test_id=llm_test["test_id"],
            test_name=llm_test.get("test_name", llm_test["test_id"]),
            protocol=protocol,
            target_ip=target_ip,
            port=port,
            description=llm_test.get("description", "LLM-generated test"),
            severity=llm_test.get("severity", "medium"),
            vulnerability_type=llm_test.get("vulnerability_type", "unknown"),
            owasp_iot_category=llm_test.get("owasp_iot_category", "I1: Insecure Web Interface"),
            test_origin="llm",
            pytest_code=llm_test.get("pytest_code"),
        )

    def _do_loop():
        # Create simulator (uses dashboard-api's Docker socket)
        simulator = EnvironmentSimulator(
            config=sim_config,
            docker_client=docker_client if sim_config.is_active() else None,
        )

        try:
            for i in range(1, req.iterations + 1):
                # Check cancellation between iterations
                with _loop_lock:
                    if _loop_state["cancelled"]:
                        _loop_state["status"] = "cancelled"
                        _loop_state["phase"] = "idle"
                        _loop_state["finished_at"] = datetime.now().isoformat()
                        simulator.cleanup()
                        return
                    _loop_state["current_iteration"] = i

                iter_start = datetime.now().isoformat()

                # ── Simulation: prepare environment before test execution ──
                with _loop_lock:
                    _loop_state["phase"] = "simulation_prepare"
                sim_actions = simulator.prepare_iteration(i)

                # Phase callback so _loop_state reflects current activity
                def _on_phase(phase: str):
                    with _loop_lock:
                        _loop_state["phase"] = phase

                # Pass simulation context to the suite runner (always,
                # so that even deterministic runs get tagged with the
                # correct simulation_mode and iteration number).
                sim_context = {
                    "mode": sim_config.mode,
                    "seed": sim_config.seed,
                    "iteration": i,
                    "false_positive_rate": sim_config.false_positive_rate,
                    "false_negative_rate": sim_config.false_negative_rate,
                }

                # Decide whether to train on this iteration
                _ten = req.train_every_n
                if req.baseline_strategy:
                    should_train = False  # Baselines never train
                elif _ten == 0:
                    should_train = (i == req.iterations)  # only last
                else:
                    should_train = (i % _ten == 0) or (i == req.iterations)  # every Nth + last

                outcome = _execute_suite_and_retrain(
                    suite_id, suite, on_phase=_on_phase,
                    simulation_context=sim_context,
                    skip_training=not should_train,
                    automl_tool=req.automl_tool,
                    temporal_training=req.temporal_training,
                    baseline_strategy=req.baseline_strategy,
                    llm_enabled=req.llm_enabled,
                    phase_tag=req.phase_tag,
                    dynamic_features=req.dynamic_features,
                )

                # ── Simulation: restore outaged containers after tests ──
                with _loop_lock:
                    _loop_state["phase"] = "simulation_restore"
                simulator.restore_iteration(i)

                # Check cancellation after iteration
                with _loop_lock:
                    if _loop_state["cancelled"]:
                        _loop_state["status"] = "cancelled"
                        _loop_state["phase"] = "idle"
                        _loop_state["finished_at"] = datetime.now().isoformat()
                        simulator.cleanup()
                        return

                # Record per-iteration metrics
                run_result = outcome.get("run_result", {})
                retrain_result = outcome.get("retrain_result") or {}
                score_result = outcome.get("score_result") or {}
                temporal_eval = outcome.get("temporal_eval") or {}
                te = run_result.get("tests_executed", 0)
                vd = run_result.get("vulns_detected", 0)

                iter_metrics = {
                    "iteration": i,
                    "trained": should_train,
                    "tests_executed": te,
                    "vulns_detected": vd,
                    "detection_rate": round(vd / te, 4) if te > 0 else 0,
                    "execution_time_ms": run_result.get("execution_time_ms", 0),
                    "retrain_auc": retrain_result.get("auc"),
                    "retrain_rows": retrain_result.get("training_rows"),
                    "retrain_status": retrain_result.get("status", "unknown"),
                    "scored_tests": score_result.get("scored_tests"),
                    "recommended_tests": score_result.get("recommended_tests"),
                    "started_at": iter_start,
                    "finished_at": datetime.now().isoformat(),
                    "simulation_actions": len(sim_actions),
                    "simulation_details": sim_actions,
                    # Temporal validation metrics (when temporal_training=True)
                    "temporal_auc": temporal_eval.get("auc_roc"),
                    "temporal_brier": temporal_eval.get("brier_score"),
                    "temporal_ece": temporal_eval.get("ece"),
                    "train_window_size": temporal_eval.get("train_window_size"),
                    # Track which scoring method was used (model vs heuristic)
                    "score_method": temporal_eval.get("score_method",
                        "model" if score_result and score_result.get("status") == "scored" else "heuristic"),
                    "llm_tests_generated": 0,
                    "llm_gaps_detected": 0,
                }

                # ── Adaptive LLM generation (every N iterations) ──
                if req.llm_enabled and i > 1 and i % req.llm_generate_every_n == 0:
                    try:
                        from generator.llm_generator import LLMTestGenerator, detect_coverage_gaps
                        llm_gen = LLMTestGenerator(provider=req.llm_provider)
                        if llm_gen.is_available():
                            from generator.retrain import aggregate_history
                            _sim_mode_for_llm = sim_config.mode if sim_config else None
                            _sim_seed_for_llm = sim_config.seed if sim_config else None
                            agg_path = aggregate_history(EXPERIMENTS_PATH, simulation_mode=_sim_mode_for_llm,
                                                         automl_tool=req.automl_tool,
                                                         seed=_sim_seed_for_llm)
                            if agg_path:
                                _llm_hist = pd.read_csv(agg_path)
                                _existing_ids = [tc.test_id for tc in suite.test_cases]
                                gaps = detect_coverage_gaps(_llm_hist, _existing_ids)
                                if gaps.get("low_detection_protocols") or gaps.get("underrepresented_protocols"):
                                    new_llm = llm_gen.generate_tests_for_gaps(
                                        gaps=gaps,
                                        devices=suite.devices,
                                        existing_test_ids=_existing_ids,
                                        execution_context=(
                                            f"Iteration {i}/{req.iterations}, "
                                            f"detection rate: {iter_metrics.get('detection_rate', 0):.3f}"
                                        ),
                                    )
                                    _default_ip = suite.devices[0]["ip"] if suite.devices else "127.0.0.1"
                                    for lt in new_llm:
                                        suite.test_cases.append(_llm_dict_to_testcase(lt, target_ip=_default_ip))
                                    _save_suite(suite)
                                    iter_metrics["llm_tests_generated"] = len(new_llm)
                                    iter_metrics["llm_gaps_detected"] = len(
                                        gaps.get("low_detection_protocols", [])
                                    )
                                    logging.info(
                                        f"[API] Iteration {i}: Added {len(new_llm)} "
                                        f"LLM tests for {len(gaps.get('low_detection_protocols', []))} gap protocols"
                                    )
                    except Exception as e:
                        logging.warning(f"[API] LLM adaptive generation failed (non-fatal): {e}")

                with _loop_lock:
                    _loop_state["iterations"].append(iter_metrics)
                    _loop_state["phase"] = "between_iterations"

                # Stop on run error
                if run_result.get("status") == "error":
                    with _loop_lock:
                        _loop_state["status"] = "error"
                        _loop_state["error"] = f"Iteration {i} failed: {run_result.get('error', 'unknown')}"
                        _loop_state["finished_at"] = datetime.now().isoformat()
                    simulator.cleanup()
                    return

            # All iterations completed — cleanup simulation
            simulator.cleanup()

            with _loop_lock:
                _loop_state["status"] = "completed"
                _loop_state["phase"] = "idle"
                _loop_state["finished_at"] = datetime.now().isoformat()
                _loop_state["simulation_summary"] = simulator.get_summary()

        except Exception as e:
            simulator.cleanup()
            with _loop_lock:
                _loop_state["status"] = "error"
                _loop_state["error"] = str(e)
                _loop_state["finished_at"] = datetime.now().isoformat()

    background_tasks.add_task(_do_loop)
    return {"status": "started", "suite_id": suite_id, "total_iterations": req.iterations, "train_every_n": req.train_every_n}


@app.get("/api/suites/{suite_id}/train-loop/status")
def train_loop_status(suite_id: str):
    with _loop_lock:
        return dict(_loop_state)


@app.post("/api/suites/{suite_id}/train-loop/cancel")
def cancel_train_loop(suite_id: str):
    with _loop_lock:
        if _loop_state["status"] != "running":
            return {"status": "not_running", "message": "No active loop to cancel"}
        _loop_state["cancelled"] = True
    return {"status": "cancelling", "message": "Loop will stop after current iteration completes"}


# ═══════════════════════════════════════════════════════════════════════
# MULTI-FRAMEWORK COMPARISON
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/automl/comparison")
def automl_comparison():
    """Compare model metrics across all trained frameworks.

    Returns a unified view of AUC, accuracy, training time, leader algorithm,
    and feature importance for each framework that has been trained.
    """
    try:
        from automl.pipeline import get_all_model_metrics
        all_metrics = get_all_model_metrics()

        comparison = []
        for name, metrics in sorted(all_metrics.items()):
            comparison.append({
                "framework": name,
                "auc": metrics.get("auc"),
                "cv_auc": metrics.get("cv_auc"),
                "accuracy": metrics.get("accuracy"),
                "logloss": metrics.get("logloss"),
                "leader_algo": metrics.get("leader_algo", "unknown"),
                "total_models_trained": metrics.get("total_models_trained", 0),
                "training_time_secs": metrics.get("training_time_secs", 0),
                "training_rows": metrics.get("training_rows", 0),
                "status": metrics.get("status", "unknown"),
            })

        return {"comparison": comparison, "frameworks_trained": len(comparison)}
    except Exception as e:
        return {"comparison": [], "frameworks_trained": 0, "error": str(e)}


@app.post("/api/automl/train-all")
def train_all_frameworks(background_tasks: BackgroundTasks):
    """Train all available AutoML frameworks on aggregated history data.

    Runs each framework sequentially in the background.
    """
    with _train_lock:
        if _train_state["status"] == "training":
            return {
                "status": "already_training",
                "message": "A training job is already running.",
            }
        _train_state["status"] = "training"
        _train_state["started_at"] = datetime.now().isoformat()
        _train_state["finished_at"] = None
        _train_state["error"] = None
        _train_state["automl_tool"] = "all"

    def _do_train_all():
        try:
            from generator.retrain import retrain_all_frameworks, aggregate_history
            from automl.registry import list_available

            agg_path = aggregate_history(EXPERIMENTS_PATH)
            if not agg_path:
                with _train_lock:
                    _train_state["status"] = "error"
                    _train_state["finished_at"] = datetime.now().isoformat()
                    _train_state["error"] = "No history data found."
                return

            available = list_available()
            logging.info(f"[API] Training all available frameworks: {available}")

            results = retrain_all_frameworks(agg_path, frameworks=available)

            with _train_lock:
                # Report success if at least one framework trained
                any_success = any(
                    r.get("status") not in ("error", "insufficient_data")
                    for r in results.values()
                )
                if any_success:
                    _train_state["status"] = "completed"
                    # Use best AUC among all frameworks
                    best_auc = max(
                        (r.get("auc", 0) or 0 for r in results.values()),
                        default=None,
                    )
                    _train_state["auc"] = best_auc
                else:
                    _train_state["status"] = "error"
                    _train_state["error"] = "All frameworks failed to train"
                _train_state["finished_at"] = datetime.now().isoformat()

        except Exception as e:
            logging.error(f"[API] Train-all failed: {e}")
            with _train_lock:
                _train_state["status"] = "error"
                _train_state["finished_at"] = datetime.now().isoformat()
                _train_state["error"] = str(e)

    background_tasks.add_task(_do_train_all)
    return {"status": "training", "message": "Training all available frameworks"}


# ═══════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/results")
def list_results():
    results = []
    if os.path.exists(RESULTS_PATH):
        for fname in sorted(os.listdir(RESULTS_PATH), reverse=True):
            if fname.endswith(".json"):
                fpath = os.path.join(RESULTS_PATH, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    # Derive devices & protocols from per-test results
                    detail = data.get("results", [])
                    device_protos = {}  # ip -> set of protocols
                    severity_counts = {}
                    for r in detail:
                        ip = r.get("target", "")
                        proto = r.get("protocol", "")
                        if ip:
                            device_protos.setdefault(ip, set()).add(proto)
                        sev = r.get("severity", "info")
                        if r.get("vulnerability_found"):
                            severity_counts[sev] = severity_counts.get(sev, 0) + 1

                    devices_summary = [
                        {"ip": ip, "protocols": sorted(protos)}
                        for ip, protos in sorted(device_protos.items())
                    ]
                    all_protocols = sorted(
                        set(p for ps in device_protos.values() for p in ps)
                    )
                    te = data.get("tests_executed", 0)
                    vd = data.get("vulns_detected", 0)

                    results.append({
                        "file": fname,
                        "suite_id": data.get("suite_id"),
                        "suite_name": data.get("suite_name", ""),
                        "status": data.get("status"),
                        "finished_at": data.get("finished_at"),
                        "tests_executed": te,
                        "vulns_detected": vd,
                        "detection_rate": round(vd / te, 4) if te > 0 else 0,
                        "execution_time_ms": data.get("execution_time_ms", 0),
                        "devices": devices_summary,
                        "protocols": all_protocols,
                        "severity_breakdown": severity_counts,
                    })
                except Exception:
                    continue

    return {"results": results}


@app.get("/api/results/{filename}")
def get_result(filename: str):
    fpath = os.path.join(RESULTS_PATH, filename)
    if not os.path.exists(fpath):
        raise HTTPException(404, f"Result {filename} not found")
    with open(fpath) as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# ML INSIGHTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/ml/status")
def ml_status(automl_tool: str = "h2o"):
    try:
        from automl.pipeline import get_model_metrics
        metrics = get_model_metrics(automl_tool)
        return metrics
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


@app.get("/api/ml/metrics")
def ml_metrics(automl_tool: str = "h2o"):
    try:
        from automl.pipeline import get_model_metrics
        return get_model_metrics(automl_tool)
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


@app.get("/api/ml/metrics/all")
def ml_metrics_all():
    """Get model metrics for ALL trained frameworks."""
    try:
        from automl.pipeline import get_all_model_metrics
        return get_all_model_metrics()
    except Exception as e:
        return {"error": str(e)}


# ── AutoML Framework Management ─────────────────────────────────────────

@app.get("/api/automl/frameworks")
def automl_frameworks():
    """List all registered AutoML frameworks and their status."""
    try:
        from automl.registry import get_framework_status
        return {"frameworks": get_framework_status()}
    except Exception as e:
        return {"frameworks": [], "error": str(e)}


@app.get("/api/automl/frameworks/available")
def automl_frameworks_available():
    """List only frameworks that are currently reachable."""
    try:
        from automl.registry import list_available
        return {"available": list_available()}
    except Exception as e:
        return {"available": ["h2o"], "error": str(e)}


# ── LLM Provider Management ─────────────────────────────────────────────

@app.get("/api/llm/providers")
def llm_providers():
    """List all registered LLM providers and their availability."""
    try:
        from generator.llm_providers.registry import list_available
        return {"providers": list_available()}
    except Exception as e:
        return {"providers": [], "error": str(e)}


_train_lock = threading.Lock()
_train_state = {
    "status": "idle",        # idle | training | completed | error
    "started_at": None,
    "finished_at": None,
    "error": None,
    "auc": None,
    "training_rows": None,
    "automl_tool": None,
}


@app.post("/api/ml/retrain")
def ml_retrain(background_tasks: BackgroundTasks, automl_tool: str = "h2o",
               suite_id: str = None):
    with _train_lock:
        if _train_state["status"] == "training":
            return {
                "status": "already_training",
                "started_at": _train_state["started_at"],
                "automl_tool": _train_state.get("automl_tool"),
                "message": "Model training is already in progress.",
            }
        _train_state["status"] = "training"
        _train_state["started_at"] = datetime.now().isoformat()
        _train_state["finished_at"] = None
        _train_state["error"] = None
        _train_state["auc"] = None
        _train_state["training_rows"] = None
        _train_state["automl_tool"] = automl_tool

    def _do_retrain():
        try:
            from generator.retrain import retrain_model_after_execution, aggregate_history

            # Filter by automl_tool to prevent cross-framework contamination
            # (matches the train-loop behaviour at line ~1420)
            agg_path = aggregate_history(EXPERIMENTS_PATH, automl_tool=automl_tool)
            if not agg_path:
                with _train_lock:
                    _train_state["status"] = "error"
                    _train_state["finished_at"] = datetime.now().isoformat()
                    _train_state["error"] = "No history data found. Run test suites first."
                return

            result = retrain_model_after_execution(agg_path, automl_tool=automl_tool)

            with _train_lock:
                if result.get("status") == "error":
                    _train_state["status"] = "error"
                    _train_state["error"] = result.get("message", "Training failed")
                elif result.get("status") == "insufficient_data":
                    _train_state["status"] = "error"
                    _train_state["error"] = f"Not enough data to train (need ≥10 rows, have {result.get('rows', 0)})"
                else:
                    _train_state["status"] = "completed"
                    _train_state["auc"] = result.get("auc")
                    _train_state["training_rows"] = result.get("training_rows")
                _train_state["finished_at"] = datetime.now().isoformat()

            # Re-score the active suite and update its automl_tool metadata
            # so the suite card badge reflects the framework actually used
            if suite_id and result.get("status") not in ("error", "insufficient_data"):
                try:
                    from generator.scorer import score_test_suite as _score
                    suite_data = _load_suite(suite_id)
                    if suite_data:
                        fresh_suite = TestSuite.from_dict(suite_data)
                        fresh_suite = _score(fresh_suite, automl_tool=automl_tool)
                        fresh_suite.metadata["automl_tool"] = automl_tool
                        fresh_suite.metadata["last_scored_at"] = datetime.utcnow().isoformat()
                        fresh_suite.metadata["scored_with_auc"] = result.get("auc")
                        _save_suite(fresh_suite)
                        logging.info(
                            f"[API] Suite {suite_id} re-scored after manual retrain "
                            f"(framework={automl_tool})"
                        )
                except Exception as e:
                    logging.warning(f"[API] Suite re-score after manual retrain failed (non-fatal): {e}")

        except Exception as e:
            logging.error(f"[API] Manual retrain ({automl_tool}) failed: {e}")
            with _train_lock:
                _train_state["status"] = "error"
                _train_state["finished_at"] = datetime.now().isoformat()
                _train_state["error"] = str(e)

    background_tasks.add_task(_do_retrain)
    return {
        "status": "training",
        "started_at": _train_state["started_at"],
        "automl_tool": automl_tool,
    }


@app.get("/api/ml/retrain/status")
def ml_retrain_status():
    with _train_lock:
        return dict(_train_state)


# ═══════════════════════════════════════════════════════════════════════
# HISTORY & ANALYTICS (kept for results visualization)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/history/summary")
def history_summary():
    """Aggregate KPIs across all experiment history (deduplicated)."""
    df = _load_aggregated_history()
    if df is None or df.empty:
        return {
            "total_tests": 0, "total_vulns": 0, "detection_rate": 0,
            "protocols_tested": 0, "total_runs": 0, "severity_breakdown": {},
        }

    total_runs = len(df)  # Raw row count (includes duplicates)

    # Deduplicate to unique test combinations
    udf = _deduplicate_history(df)
    total_tests = len(udf)
    vulns = int(udf["vulnerability_found"].sum()) if "vulnerability_found" in udf.columns else 0
    rate = round(vulns / total_tests, 4) if total_tests > 0 else 0
    protocols = udf["protocol"].nunique() if "protocol" in udf.columns else 0

    # Severity breakdown from result files (history.csv doesn't have severity)
    # We compute from vulns-by-type as a proxy or leave empty
    severity_breakdown = {}

    return {
        "total_tests": total_tests,
        "total_vulns": vulns,
        "detection_rate": rate,
        "protocols_tested": protocols,
        "total_runs": total_runs,
        "severity_breakdown": severity_breakdown,
    }


@app.get("/api/history/vulns-by-protocol")
def vulns_by_protocol():
    df = _load_aggregated_history()
    if df is None or df.empty:
        return {"data": []}

    udf = _deduplicate_history(df)
    grouped = udf.groupby("protocol").agg(
        tests=("vulnerability_found", "count"),
        vulns=("vulnerability_found", "sum"),
    ).reset_index()
    grouped["vulns"] = grouped["vulns"].astype(int)

    return {"data": grouped.to_dict(orient="records")}


@app.get("/api/history/vulns-by-type")
def vulns_by_type():
    df = _load_aggregated_history()
    if df is None or df.empty:
        return {"data": []}

    if "test_type" not in df.columns:
        return {"data": []}

    udf = _deduplicate_history(df)
    grouped = udf.groupby("test_type").agg(
        tests=("vulnerability_found", "count"),
        vulns=("vulnerability_found", "sum"),
    ).reset_index()
    grouped["vulns"] = grouped["vulns"].astype(int)

    return {"data": grouped.to_dict(orient="records")}


@app.get("/api/history/vulns-by-device")
def vulns_by_device():
    df = _load_aggregated_history()
    if df is None or df.empty:
        return {"data": []}

    udf = _deduplicate_history(df)
    grouped = udf.groupby("container_id").agg(
        tests=("vulnerability_found", "count"),
        vulns=("vulnerability_found", "sum"),
        protocols=("protocol", "nunique"),
    ).reset_index()
    grouped["vulns"] = grouped["vulns"].astype(int)

    return {"data": grouped.to_dict(orient="records")}


# ═══════════════════════════════════════════════════════════════════════
# HYPOTHESIS VALIDATION
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/hypothesis/debug-experiments")
def debug_experiments():
    """Debug endpoint to inspect experiment directories and history files."""
    import glob as glob_mod

    result = {
        "experiments_path": EXPERIMENTS_PATH,
        "path_exists": os.path.exists(EXPERIMENTS_PATH),
        "path_is_dir": os.path.isdir(EXPERIMENTS_PATH),
        "contents": [],
        "history_files": [],
        "exp_dirs": [],
    }

    if os.path.isdir(EXPERIMENTS_PATH):
        try:
            result["contents"] = sorted(os.listdir(EXPERIMENTS_PATH))
        except Exception as e:
            result["contents_error"] = str(e)

        pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
        result["glob_pattern"] = pattern
        result["history_files"] = sorted(glob_mod.glob(pattern))

        # List exp_ directories
        exp_pattern = os.path.join(EXPERIMENTS_PATH, "exp_*")
        exp_dirs = sorted(glob_mod.glob(exp_pattern))
        result["exp_dirs"] = exp_dirs

        # Check each exp dir for its contents
        for exp_dir in exp_dirs[:10]:  # limit to 10
            try:
                files = os.listdir(exp_dir)
                result.setdefault("exp_details", []).append({
                    "dir": os.path.basename(exp_dir),
                    "files": files,
                })
            except Exception as e:
                result.setdefault("exp_details", []).append({
                    "dir": os.path.basename(exp_dir),
                    "error": str(e),
                })

    return result


@app.post("/api/hypothesis/invalidate-cache")
def invalidate_hypothesis_cache():
    """Clear all in-memory hypothesis caches. Call after adding new experiments."""
    _history_cache.clear()
    _iteration_cache.clear()
    _prediction_cache.clear()
    _synthesis_cache.clear()
    return {"status": "ok", "message": "All hypothesis caches cleared"}


@app.get("/api/hypothesis/available-simulation-modes")
def available_simulation_modes():
    """Return distinct simulation_mode values found in history data, with per-mode metadata.

    Response:
        modes: list of mode names (sorted, deterministic first)
        mode_metadata: dict mapping mode -> {rows, seeds, iterations, experiments}
    """
    cached = _history_cache.get("__sim_modes__")
    if cached is not None:
        return cached

    import glob as glob_mod

    modes = set()
    mode_meta: dict[str, dict] = {}

    # ── Fast path: query DuckDB ───────────────────────────────────────
    if _db_available():
        try:
            with _db_lock:
                con = _duckdb.connect(DB_PATH, read_only=True)
                try:
                    rows = con.execute(
                        "SELECT simulation_mode, simulation_iteration, exp_dir_name "
                        "FROM history WHERE simulation_mode IS NOT NULL"
                    ).fetchall()
                finally:
                    con.close()
            for sim_mode, sim_iter, exp_dir_nm in rows:
                if not sim_mode:
                    continue
                modes.add(sim_mode)
                if sim_mode not in mode_meta:
                    mode_meta[sim_mode] = {"rows": 0, "iterations": set(), "experiments": set()}
                mode_meta[sim_mode]["rows"] += 1
                mode_meta[sim_mode]["experiments"].add(exp_dir_nm or "")
                if sim_iter is not None:
                    try:
                        mode_meta[sim_mode]["iterations"].add(int(sim_iter))
                    except (ValueError, TypeError):
                        pass
        except Exception as e:
            logging.warning(f"[SimModes] DuckDB query failed, falling back to CSV: {e}")
            modes.clear()
            mode_meta.clear()

    if not modes:
        # ── Fallback: CSV scanning ────────────────────────────────────
        pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
        files = glob_mod.glob(pattern)
        _usecols = ["simulation_mode", "simulation_iteration"]
        for f in files:
            try:
                df = pd.read_csv(f, usecols=lambda c: c in _usecols or c == "simulation_mode")
                if "simulation_mode" not in df.columns:
                    continue
                for mode in df["simulation_mode"].dropna().unique():
                    modes.add(mode)
                    if mode not in mode_meta:
                        mode_meta[mode] = {"rows": 0, "iterations": set(), "experiments": set()}
                    mode_df = df[df["simulation_mode"] == mode]
                    mode_meta[mode]["rows"] += len(mode_df)
                    mode_meta[mode]["experiments"].add(os.path.basename(os.path.dirname(f)))
                    if "simulation_iteration" in mode_df.columns:
                        mode_meta[mode]["iterations"].update(
                            mode_df["simulation_iteration"].dropna().astype(int).unique().tolist()
                        )
            except Exception:
                continue

    # Also scan result JSON files for seed info
    mode_seeds: dict[str, set] = {}
    result_pattern = os.path.join(RESULTS_PATH, "*.json")
    for rf in glob_mod.glob(result_pattern):
        try:
            with open(rf) as _f:
                rdata = json.load(_f)
            rm = rdata.get("simulation_mode")
            rs = rdata.get("simulation_seed")
            if rm and rs is not None:
                mode_seeds.setdefault(rm, set()).add(rs)
        except Exception:
            continue

    # Ensure "deterministic" is always present as the baseline
    modes.add("deterministic")
    sorted_modes = sorted(modes, key=lambda m: (m != "deterministic", m))

    # Build serialisable metadata
    metadata = {}
    for m in sorted_modes:
        meta = mode_meta.get(m, {})
        _exps = meta.get("experiments", set())
        metadata[m] = {
            "rows": meta.get("rows", 0),
            "iterations": sorted(meta["iterations"]) if isinstance(meta.get("iterations"), set) else [],
            "experiments": len(_exps) if isinstance(_exps, set) else _exps,
            "seeds": sorted(mode_seeds.get(m, [])),
        }

    result = {"modes": sorted_modes, "mode_metadata": metadata}
    _history_cache.set("__sim_modes__", result)
    return result


@app.get("/api/hypothesis/iteration-metrics")
def hypothesis_iteration_metrics(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None, phase: Optional[str] = "framework"):
    """Per-experiment-run metrics over time for hypothesis validation."""
    # Check cache first
    cache_key = f"iter_{simulation_mode or 'all'}_{automl_tool or 'all'}_{phase or 'all'}"
    cached = _iteration_cache.get(cache_key)
    if cached is not None:
        return cached

    iterations = []
    parse_errors = []
    # Track unique vulnerabilities across iterations for discovery velocity
    seen_vuln_keys = set()
    dedup_cols = list(_DEDUP_COLS)

    # ── Load all rows at once (DuckDB fast path) ─────────────────────
    df_all = _db_load_all(simulation_mode=simulation_mode, automl_tool=automl_tool, phase=phase)

    if df_all is None:
        # DuckDB not available — fall back to CSV scanning
        import glob as glob_mod
        pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
        files = sorted(glob_mod.glob(pattern))
        logging.info(f"[Hypothesis] DuckDB unavailable, scanning {len(files)} CSV files")
        if not files:
            logging.warning(f"[Hypothesis] No history files found. EXPERIMENTS_PATH={EXPERIMENTS_PATH}")
            return {"iterations": [], "total_iterations": 0, "available_protocols": []}
        raw_dfs = []
        for f in files:
            try:
                df_f = pd.read_csv(f)
                if df_f.empty:
                    continue
                if simulation_mode and simulation_mode != "all" and "simulation_mode" in df_f.columns:
                    df_f = df_f[df_f["simulation_mode"] == simulation_mode]
                    if df_f.empty:
                        continue
                if automl_tool and automl_tool != "all":
                    if "automl_tool" in df_f.columns:
                        df_f = df_f[df_f["automl_tool"] == automl_tool]
                    elif automl_tool != "h2o":
                        continue
                    if df_f.empty:
                        continue
                df_f["exp_dir_name"] = os.path.basename(os.path.dirname(f))
                raw_dfs.append(df_f)
            except Exception as exc:
                parse_errors.append(f"Error reading {f}: {exc}")
        if not raw_dfs:
            return {"iterations": [], "total_iterations": 0, "available_protocols": []}
        df_all = pd.concat(raw_dfs, ignore_index=True)

    # Apply phase filter (CSV fallback path — phase column derived from baseline_strategy)
    if phase is not None and df_all is not None and not df_all.empty:
        _NON_ML_P = {"random", "cvss_priority", "round_robin", "no_ml"}
        if "phase" not in df_all.columns and "baseline_strategy" in df_all.columns:
            df_all["phase"] = df_all["baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_P else "framework"
            )
        elif "phase" in df_all.columns and "baseline_strategy" in df_all.columns:
            # Also fix NULLs in existing phase column (rows pre-dating tagging)
            _null_p = df_all["phase"].isna()
            df_all.loc[_null_p, "phase"] = df_all.loc[_null_p, "baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_P else "framework"
            )
        if "phase" in df_all.columns:
            df_all = df_all[df_all["phase"] == phase]

    if df_all is None or df_all.empty:
        return {"iterations": [], "total_iterations": 0, "available_protocols": []}

    # Ensure exp_dir_name column exists (DuckDB path always has it; CSV path adds it above)
    if "exp_dir_name" not in df_all.columns:
        df_all["exp_dir_name"] = "unknown"

    if "vulnerability_found" in df_all.columns:
        df_all["vulnerability_found"] = pd.to_numeric(
            df_all["vulnerability_found"], errors="coerce"
        ).fillna(0).astype(int)

    # Process per-experiment-iteration (sorted chronologically by dir name)
    for exp_dir_name, df in sorted(df_all.groupby("exp_dir_name"), key=lambda x: x[0]):
        try:
            raw_ts = exp_dir_name.replace("exp_", "")
            parts = raw_ts.split("_", 2)
            timestamp = f"{parts[0]} {parts[1]}" if len(parts) >= 2 else raw_ts

            total_tests = len(df)
            total_vulns = int(df["vulnerability_found"].sum()) if "vulnerability_found" in df.columns else 0
            detection_rate = round(total_vulns / total_tests, 4) if total_tests > 0 else 0
            avg_exec_time = (_safe_float(df["execution_time_ms"].mean(), 2) or 0) if "execution_time_ms" in df.columns else 0
            unique_protocols = int(df["protocol"].nunique()) if "protocol" in df.columns else 0

            # Track new vs already-seen vulnerabilities
            new_vulns = 0
            cols_present = [c for c in dedup_cols if c in df.columns]
            if cols_present and "vulnerability_found" in df.columns:
                vuln_rows = df[df["vulnerability_found"] == 1]
                for _, row in vuln_rows.iterrows():
                    key = tuple(str(row.get(c, "")) for c in cols_present)
                    if key not in seen_vuln_keys:
                        seen_vuln_keys.add(key)
                        new_vulns += 1

            # Per-protocol breakdown
            by_protocol = {}
            if "protocol" in df.columns:
                for proto, group in df.groupby("protocol"):
                    proto_total = len(group)
                    proto_vulns = int(group["vulnerability_found"].sum()) if "vulnerability_found" in group.columns else 0
                    proto_rate = round(proto_vulns / proto_total, 4) if proto_total > 0 else 0
                    proto_avg_time = (_safe_float(group["execution_time_ms"].mean(), 2) or 0) if "execution_time_ms" in group.columns else 0
                    by_protocol[str(proto)] = {
                        "total_tests": proto_total,
                        "total_vulns": proto_vulns,
                        "detection_rate": proto_rate,
                        "avg_execution_time_ms": proto_avg_time,
                    }

            iterations.append({
                "experiment_id": exp_dir_name,
                "timestamp": timestamp,
                "total_tests": total_tests,
                "total_vulns": total_vulns,
                "detection_rate": detection_rate,
                "unique_protocols": unique_protocols,
                "avg_execution_time_ms": avg_exec_time,
                "by_protocol": by_protocol,
                "new_vulns": new_vulns,
                "cumulative_unique_vulns": len(seen_vuln_keys),
            })
        except Exception as exc:
            err_msg = f"Error processing {exp_dir_name}: {exc}"
            logging.error(f"[Hypothesis] {err_msg}", exc_info=True)
            parse_errors.append(err_msg)

    iterations.sort(key=lambda x: x["timestamp"])

    # Collect all protocols seen across all experiments
    available_protocols = sorted({
        proto
        for it in iterations
        for proto in it.get("by_protocol", {}).keys()
    })

    result = {
        "iterations": iterations,
        "total_iterations": len(iterations),
        "available_protocols": available_protocols,
        "_debug": {
            "source": "duckdb" if _db_available() else "csv",
            "iterations_parsed": len(iterations),
            "parse_errors": parse_errors,
        },
    }
    if parse_errors:
        logging.warning(f"[Hypothesis] {len(parse_errors)} files failed to parse: {parse_errors}")
    _iteration_cache.set(cache_key, result)
    return result


@app.get("/api/hypothesis/model-evolution")
def hypothesis_model_evolution(automl_tool: str = "h2o"):
    """ML model metrics snapshot (AUC, feature importance, etc.)."""
    try:
        from automl.pipeline import get_model_metrics
        metrics = get_model_metrics(automl_tool)
        return {"model": metrics, "automl_tool": automl_tool}
    except Exception as e:
        return {"model": {"status": "unavailable", "error": str(e)}}


@app.get("/api/hypothesis/composition-analysis")
def hypothesis_composition_analysis(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """H2: Strategy effectiveness analysis with statistical tests.

    Tests whether ML-composed test strategies achieve significantly
    different detection rates than other strategies using Chi-squared
    and effect size measures.
    """
    from scipy import stats as scipy_stats
    import numpy as np

    df = _load_aggregated_history(simulation_mode=simulation_mode, automl_tool=automl_tool)
    if df is None or df.empty:
        return {"strategies": [], "rules": [], "stats": None, "verdict": None}

    strategies = []
    if "test_strategy" in df.columns:
        df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
        for strategy, group in df.groupby("test_strategy"):
            total = len(group)
            vulns = int(group["vulnerability_found"].sum())
            avg_time = (_safe_float(group["execution_time_ms"].mean(), 2) or 0) if "execution_time_ms" in group.columns else 0
            strategies.append({
                "strategy": strategy,
                "total_tests": total,
                "vulns_found": vulns,
                "detection_rate": round(vulns / total, 4) if total > 0 else 0,
                "avg_execution_time_ms": avg_time,
            })

    # ─── Statistical tests across strategies ───
    stats_result = None
    verdict = None

    if len(strategies) >= 2 and "test_strategy" in df.columns:
        # Chi-squared test on contingency table: strategy × outcome
        try:
            contingency = pd.crosstab(
                df["test_strategy"],
                df["vulnerability_found"],
            )
            if contingency.shape[0] >= 2 and contingency.shape[1] >= 2:
                chi2, chi2_p, chi2_dof, _ = scipy_stats.chi2_contingency(contingency)

                # Cramér's V effect size
                n_obs = contingency.values.sum()
                min_dim = min(contingency.shape[0], contingency.shape[1]) - 1
                cramers_v = float(np.sqrt(chi2 / (n_obs * min_dim))) if (n_obs * min_dim) > 0 else 0

                cramers_interp = (
                    "large" if cramers_v >= 0.5
                    else "medium" if cramers_v >= 0.3
                    else "small" if cramers_v >= 0.1
                    else "negligible"
                )

                chi2_sig = bool(chi2_p < 0.05)

                # Best vs worst strategy detection rate
                sorted_strats = sorted(strategies, key=lambda s: s["detection_rate"], reverse=True)
                best = sorted_strats[0]
                worst = sorted_strats[-1]

                stats_result = {
                    "chi2": _safe_float(chi2, 4),
                    "chi2_p": _safe_float(chi2_p, 6),
                    "chi2_dof": int(chi2_dof),
                    "chi2_significant": chi2_sig,
                    "cramers_v": _safe_float(cramers_v, 4),
                    "cramers_v_interpretation": cramers_interp,
                    "n_strategies": len(strategies),
                    "n_observations": int(n_obs),
                    "best_strategy": best["strategy"],
                    "best_rate": best["detection_rate"],
                    "worst_strategy": worst["strategy"],
                    "worst_rate": worst["detection_rate"],
                }

                if chi2_sig and cramers_v >= 0.1:
                    verdict = "supported"
                elif chi2_sig or cramers_v >= 0.1:
                    verdict = "trending"
                else:
                    verdict = "not_supported"
        except Exception as e:
            logging.warning(f"[Hypothesis] Composition chi2 test failed: {e}")

    return {"strategies": strategies, "rules": [], "stats": stats_result, "verdict": verdict}


@app.get("/api/hypothesis/statistical-tests")
def hypothesis_statistical_tests(protocol: Optional[str] = None, simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Statistical analysis for H1: Detection Rate Stability.

    Tests whether the system maintains stable detection rates over
    successive iterations — i.e., the pipeline does not degrade despite
    environmental dynamics (simulation mutations) or repeated testing.

    Optional protocol param filters to per-protocol detection rates.
    Optional simulation_mode filters history data by simulation profile.
    Response keys are flattened for frontend compatibility.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    iter_data = hypothesis_iteration_metrics(simulation_mode=simulation_mode, automl_tool=automl_tool, phase="framework")
    iterations = iter_data.get("iterations", [])

    # Extract detection rates — global or per-protocol
    if protocol:
        detection_rates = []
        for it in iterations:
            proto_data = it.get("by_protocol", {}).get(protocol)
            if proto_data:
                detection_rates.append(proto_data["detection_rate"])
    else:
        detection_rates = [it["detection_rate"] for it in iterations]

    if len(detection_rates) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need at least 2 iterations{f' with protocol {protocol}' if protocol else ''}, have {len(detection_rates)}",
            "n_iterations": len(detection_rates),
            "protocol": protocol,
        }

    iteration_numbers = list(range(1, len(detection_rates) + 1))

    # ─── Compute all statistical tests ───
    spearman_rho = spearman_p = None
    pearson_r = pearson_p = None
    mann_whitney_u = mann_whitney_p = early_mean = late_mean = None
    cohens_d_val = cohens_d_interp = None
    improvement = ci_low = ci_high = None

    # Spearman rank correlation (monotonic trend)
    try:
        sr, sp = scipy_stats.spearmanr(iteration_numbers, detection_rates)
        if not np.isnan(sr):
            spearman_rho = round(float(sr), 4)
            spearman_p = round(float(sp), 6)
    except Exception:
        pass

    # Pearson correlation (linear trend)
    try:
        pr, pp = scipy_stats.pearsonr(iteration_numbers, detection_rates)
        if not np.isnan(pr):
            pearson_r = round(float(pr), 4)
            pearson_p = round(float(pp), 6)
    except Exception:
        pass

    # Mann-Whitney U: early vs. late iterations
    try:
        mid = len(detection_rates) // 2
        early_arr = detection_rates[:mid]
        late_arr = detection_rates[mid:]
        if len(early_arr) >= 1 and len(late_arr) >= 1:
            u_stat, mw_p = scipy_stats.mannwhitneyu(late_arr, early_arr, alternative="greater")
            mann_whitney_u = _safe_float(u_stat, 4)
            mann_whitney_p = _safe_float(mw_p, 6)
            early_mean = _safe_float(np.mean(early_arr), 4)
            late_mean = _safe_float(np.mean(late_arr), 4)
    except Exception:
        pass

    # Cohen's d effect size
    try:
        mid = len(detection_rates) // 2
        early_np = np.array(detection_rates[:mid], dtype=float)
        late_np = np.array(detection_rates[mid:], dtype=float)
        pooled_std = np.sqrt((early_np.std() ** 2 + late_np.std() ** 2) / 2)
        if pooled_std > 0:
            cd = float((late_np.mean() - early_np.mean()) / pooled_std)
            cohens_d_val = _safe_float(cd, 4)
            if cohens_d_val is not None:
                cohens_d_interp = (
                    "large" if abs(cohens_d_val) >= 0.8
                    else "medium" if abs(cohens_d_val) >= 0.5
                    else "small" if abs(cohens_d_val) >= 0.2
                    else "negligible"
                )
            else:
                cohens_d_interp = None
        else:
            cohens_d_val = 0.0
            cohens_d_interp = "negligible"
    except Exception:
        pass

    # 95% Confidence interval for detection rate improvement
    try:
        mid = len(detection_rates) // 2
        early_np = np.array(detection_rates[:mid], dtype=float)
        late_np = np.array(detection_rates[mid:], dtype=float)
        improvement = _safe_float(late_np.mean() - early_np.mean(), 4)
        se = float(np.sqrt(early_np.var() / len(early_np) + late_np.var() / len(late_np))) if len(early_np) > 1 and len(late_np) > 1 else 0
        se = _safe_float(se, 6)
        if improvement is not None and se is not None:
            ci_low = round(improvement - 1.96 * se, 4)
            ci_high = round(improvement + 1.96 * se, 4)
    except Exception:
        pass

    # Overall hypothesis verdict — H1: Detection Rate Stability
    # "Supported" = detection rates remain stable (no significant decline,
    # negligible or small effect size).  The system maintains effectiveness.
    spearman_sig = spearman_p is not None and spearman_p < 0.05
    mw_sig = mann_whitney_p is not None and mann_whitney_p < 0.05
    abs_d = abs(cohens_d_val) if cohens_d_val is not None else 0
    spearman_neg = (spearman_rho or 0) < 0

    if not spearman_sig and abs_d < 0.5:
        # No significant trend AND negligible/small effect → stable
        verdict = "supported"
    elif spearman_sig and not spearman_neg and abs_d < 0.5:
        # Significant positive trend but small effect → still stable
        verdict = "supported"
    elif not spearman_sig and abs_d >= 0.5:
        # Not significant but medium/large effect → inconclusive
        verdict = "trending"
    else:
        # Significant decline or large effect size → unstable
        verdict = "not_supported"

    # ─── Flat response for frontend ───
    return {
        "status": "ok",
        "protocol": protocol,
        "n_iterations": len(detection_rates),
        "spearman_rho": spearman_rho,
        "spearman_p": spearman_p,
        "spearman_significant": spearman_sig,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "pearson_significant": pearson_p is not None and pearson_p < 0.05,
        "mann_whitney_u": mann_whitney_u,
        "mann_whitney_p": mann_whitney_p,
        "mann_whitney_significant": mw_sig,
        "early_mean": early_mean,
        "late_mean": late_mean,
        "cohens_d": cohens_d_val,
        "cohens_d_interpretation": cohens_d_interp,
        "improvement": improvement,
        "ci_95": [ci_low, ci_high] if ci_low is not None else None,
        "verdict": verdict,
    }


# ── H2 — Recommendation Effectiveness ────────────────────────────────

@app.get("/api/hypothesis/recommendation-effectiveness")
def hypothesis_recommendation_effectiveness(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Compare ML-recommended vs non-recommended test detection rates."""
    df = _load_aggregated_history(simulation_mode=simulation_mode, automl_tool=automl_tool, phase="framework")
    if df is None or df.empty:
        return {"error": "No history data available", "model_available": False}

    pred_cache_key = f"pred_{simulation_mode or 'all'}_{automl_tool or 'all'}"
    scored_df = _prediction_cache.get(pred_cache_key)
    if scored_df is None:
        scored_df = _predict_risk_scores_on_history(df)
        if scored_df is not None:
            _prediction_cache.set(pred_cache_key, scored_df)

    import numpy as np
    from scipy import stats as scipy_stats

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)

    # If scoring succeeded (ML model or heuristic), use predicted risk scores;
    # otherwise fall back to test_strategy comparison (generated vs static)
    use_model = scored_df is not None
    score_method = "none"
    if use_model:
        df = scored_df
        score_method = scored_df["_score_method"].iloc[0] if "_score_method" in scored_df.columns else "model"
    total = len(df)
    total_vulns = int(df["vulnerability_found"].sum())
    overall_rate = total_vulns / total if total > 0 else 0

    if use_model:
        # Split at 0.5 threshold
        rec = df[df["predicted_risk_score"] >= 0.5]
        non_rec = df[df["predicted_risk_score"] < 0.5]
    else:
        # Fallback: use test_strategy column
        rec = df[df["test_strategy"] == "generated"] if "test_strategy" in df.columns else pd.DataFrame()
        non_rec = df[df["test_strategy"] != "generated"] if "test_strategy" in df.columns else df

    rec_count = len(rec)
    rec_vulns = int(rec["vulnerability_found"].sum()) if rec_count > 0 else 0
    rec_rate = rec_vulns / rec_count if rec_count > 0 else 0

    non_rec_count = len(non_rec)
    non_rec_vulns = int(non_rec["vulnerability_found"].sum()) if non_rec_count > 0 else 0
    non_rec_rate = non_rec_vulns / non_rec_count if non_rec_count > 0 else 0

    lift = rec_rate / overall_rate if overall_rate > 0 else 0

    # Fisher's exact test on 2x2 contingency table
    fisher_p = None
    try:
        table = [
            [rec_vulns, rec_count - rec_vulns],
            [non_rec_vulns, non_rec_count - non_rec_vulns],
        ]
        _, fp = scipy_stats.fisher_exact(table)
        fisher_p = _safe_float(fp, 6)
    except Exception:
        pass

    # Threshold sweep (only meaningful when model scores are available)
    threshold_sweep = []
    if use_model:
        for thresh_int in range(1, 10):
            thresh = thresh_int / 10.0
            above = df[df["predicted_risk_score"] >= thresh]
            above_count = len(above)
            above_vulns = int(above["vulnerability_found"].sum()) if above_count > 0 else 0
            precision = above_vulns / above_count if above_count > 0 else 0
            recall = above_vulns / total_vulns if total_vulns > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            threshold_sweep.append({
                "threshold": thresh,
                "above_count": above_count,
                "above_vulns": above_vulns,
                "precision": _safe_float(precision, 4) or 0,
                "recall": _safe_float(recall, 4) or 0,
                "f1": _safe_float(f1, 4) or 0,
            })

    safe_lift = _safe_float(lift, 4) or 0

    # Verdict
    significant = fisher_p is not None and fisher_p < 0.05
    verdict = "supported" if significant and safe_lift > 1.0 else "trending" if safe_lift > 1.0 else "not_supported"

    return {
        "model_available": use_model,
        "score_method": score_method if use_model else "strategy_fallback",
        "mode": "model_scored" if use_model else "strategy_fallback",
        "total_predictions": total,
        "overall": {
            "recommended_count": rec_count,
            "recommended_vulns": rec_vulns,
            "recommended_rate": _safe_float(rec_rate, 4) or 0,
            "non_recommended_count": non_rec_count,
            "non_recommended_vulns": non_rec_vulns,
            "non_recommended_rate": _safe_float(non_rec_rate, 4) or 0,
            "lift": safe_lift,
            "fisher_p": fisher_p,
        },
        "threshold_sweep": threshold_sweep,
        "verdict": verdict,
    }


# ── H3 — Protocol Convergence Rates ──────────────────────────────────

@app.get("/api/hypothesis/protocol-convergence")
def hypothesis_protocol_convergence(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Analyse per-protocol detection rate convergence across iterations."""
    import numpy as np
    from scipy import stats as scipy_stats

    # Reuse the iteration metrics logic
    iter_result = hypothesis_iteration_metrics(simulation_mode=simulation_mode, automl_tool=automl_tool, phase="framework")
    iterations = iter_result.get("iterations", [])
    if len(iterations) < 2:
        return {"error": "Need at least 2 iterations", "protocols": []}

    # Collect per-protocol time series
    proto_series = {}  # protocol -> [(iter_idx, detection_rate)]
    for idx, it in enumerate(iterations):
        bp = it.get("by_protocol", {})
        for proto, metrics in bp.items():
            if metrics.get("detection_rate") is not None:
                proto_series.setdefault(proto, []).append(
                    (idx + 1, float(metrics["detection_rate"]))
                )

    protocols = []
    for proto, series in sorted(proto_series.items()):
        n = len(series)
        if n < 2:
            protocols.append({
                "protocol": proto,
                "n_iterations": n,
                "slope": None, "slope_p": None,
                "spearman_rho": None, "spearman_p": None,
                "first_rate": round(series[0][1], 4) if series else None,
                "last_rate": round(series[-1][1], 4) if series else None,
                "mean_rate": round(sum(r for _, r in series) / n, 4) if series else None,
                "status": "insufficient_data",
            })
            continue

        indices = [s[0] for s in series]
        rates = [s[1] for s in series]

        # Check for zero variance (all rates identical) — stats are meaningless
        if np.std(rates) == 0:
            protocols.append({
                "protocol": proto,
                "n_iterations": n,
                "slope": 0.0, "slope_p": None,
                "spearman_rho": None, "spearman_p": None,
                "first_rate": round(rates[0], 4),
                "last_rate": round(rates[-1], 4),
                "mean_rate": round(sum(rates) / n, 4),
                "status": "stable",
            })
            continue

        # Linear regression
        slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(indices, rates)

        # Spearman (need >= 3 for meaningful result)
        sp_rho, sp_p = (None, None)
        if n >= 3:
            try:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    rho, pval = scipy_stats.spearmanr(indices, rates)
                if not np.isnan(rho):
                    sp_rho, sp_p = rho, pval
            except Exception:
                pass

        # Classify (use _safe_float values; treat None p_value as non-significant)
        safe_slope = _safe_float(slope, 6)
        safe_p = _safe_float(p_value, 6)
        if safe_slope is not None and safe_p is not None and safe_slope > 0.001 and safe_p < 0.1:
            status = "converging"
        elif safe_slope is not None and safe_p is not None and safe_slope < -0.001 and safe_p < 0.1:
            status = "diverging"
        else:
            status = "stable"

        protocols.append({
            "protocol": proto,
            "n_iterations": n,
            "slope": safe_slope,
            "slope_p": safe_p,
            "spearman_rho": _safe_float(sp_rho, 4),
            "spearman_p": _safe_float(sp_p, 6),
            "first_rate": round(rates[0], 4),
            "last_rate": round(rates[-1], 4),
            "mean_rate": round(sum(rates) / n, 4),
            "status": status,
        })

    # Summaries
    converging = [p for p in protocols if p["status"] == "converging"]
    stable = [p for p in protocols if p["status"] in ("converging", "stable", "diverging")]

    fastest = max(converging, key=lambda p: p["slope"] or 0) if converging else None
    most_stable_proto = min(stable, key=lambda p: abs(p["slope"] or 0)) if stable else None

    # ─── Overall convergence verdict ───
    # Levene's test: do late iterations have lower cross-protocol variance?
    stats_result = None
    verdict = None
    try:
        if len(iterations) >= 6:
            mid = len(iterations) // 2
            early_vars = []
            late_vars = []
            for idx, it in enumerate(iterations):
                bp = it.get("by_protocol", {})
                rates_at_iter = [float(m["detection_rate"]) for m in bp.values() if m.get("detection_rate") is not None]
                if len(rates_at_iter) >= 2:
                    var = float(np.var(rates_at_iter))
                    if idx < mid:
                        early_vars.append(var)
                    else:
                        late_vars.append(var)

            if len(early_vars) >= 2 and len(late_vars) >= 2:
                # Mann-Whitney on variance: late < early means convergence
                u_stat, mw_p = scipy_stats.mannwhitneyu(late_vars, early_vars, alternative="less")
                variance_sig = bool(mw_p < 0.05)

                early_mean_var = float(np.mean(early_vars))
                late_mean_var = float(np.mean(late_vars))
                variance_reduction = ((early_mean_var - late_mean_var) / early_mean_var * 100) if early_mean_var > 0 else 0

                # Count converging vs diverging vs stable
                n_converging = sum(1 for p in protocols if p["status"] == "converging")
                n_stable = sum(1 for p in protocols if p["status"] == "stable")
                n_diverging = sum(1 for p in protocols if p["status"] == "diverging")

                stats_result = {
                    "variance_u": _safe_float(u_stat, 4),
                    "variance_p": _safe_float(mw_p, 6),
                    "variance_significant": variance_sig,
                    "early_mean_variance": _safe_float(early_mean_var, 6),
                    "late_mean_variance": _safe_float(late_mean_var, 6),
                    "variance_reduction_pct": _safe_float(variance_reduction, 2),
                    "n_converging": n_converging,
                    "n_stable": n_stable,
                    "n_diverging": n_diverging,
                    "n_protocols": len(protocols),
                }

                if variance_sig and n_diverging == 0:
                    verdict = "supported"
                elif n_converging > n_diverging:
                    verdict = "trending"
                else:
                    verdict = "not_supported"
    except Exception as e:
        logging.warning(f"[Hypothesis] Convergence stats failed: {e}")

    return {
        "protocols": protocols,
        "fastest_converging": fastest["protocol"] if fastest else None,
        "most_stable": most_stable_proto["protocol"] if most_stable_proto else None,
        "stats": stats_result,
        "verdict": verdict,
    }


# ── H4 — Risk Score Calibration ──────────────────────────────────────

@app.get("/api/hypothesis/risk-calibration")
def hypothesis_risk_calibration(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Analyse calibration of predicted risk scores vs observed vulnerability rates."""
    import numpy as np

    df = _load_aggregated_history(simulation_mode=simulation_mode, automl_tool=automl_tool, phase="framework")
    if df is None or df.empty:
        return {"error": "No history data available", "model_available": False}

    pred_cache_key = f"pred_{simulation_mode or 'all'}_{automl_tool or 'all'}"
    scored_df = _prediction_cache.get(pred_cache_key)
    if scored_df is None:
        scored_df = _predict_risk_scores_on_history(df)
        if scored_df is not None:
            _prediction_cache.set(pred_cache_key, scored_df)
    if scored_df is None:
        return {"error": "Insufficient data for calibration analysis", "model_available": False}

    score_method = scored_df["_score_method"].iloc[0] if "_score_method" in scored_df.columns else "unknown"

    df = scored_df
    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    total = len(df)

    # Bin into 10 deciles
    bin_edges = [i / 10.0 for i in range(11)]  # [0.0, 0.1, ..., 1.0]
    calibration_curve = []
    ece_sum = 0.0
    mce = 0.0

    for i in range(10):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        if i == 9:
            mask = (df["predicted_risk_score"] >= lo) & (df["predicted_risk_score"] <= hi)
        else:
            mask = (df["predicted_risk_score"] >= lo) & (df["predicted_risk_score"] < hi)
        bin_df = df[mask]
        count = len(bin_df)
        predicted_mean = _safe_float(bin_df["predicted_risk_score"].mean(), 4) if count > 0 else round((lo + hi) / 2, 4)
        observed_rate = _safe_float(bin_df["vulnerability_found"].mean(), 4) if count > 0 else 0

        # Fallback if _safe_float returned None (all-NaN bin)
        if predicted_mean is None:
            predicted_mean = round((lo + hi) / 2, 4)
        if observed_rate is None:
            observed_rate = 0

        calibration_curve.append({
            "bin_start": round(lo, 1),
            "bin_end": round(hi, 1),
            "predicted_mean": predicted_mean,
            "observed_rate": observed_rate,
            "count": count,
        })

        if count > 0:
            gap = abs(predicted_mean - observed_rate)
            ece_sum += (count / total) * gap
            mce = max(mce, gap)

    # Brier score
    brier = _safe_float(np.mean(
        (df["predicted_risk_score"].values - df["vulnerability_found"].values) ** 2
    ), 4) or 0

    # Verdict
    if ece_sum < 0.05:
        verdict = "well_calibrated"
    elif ece_sum < 0.15:
        verdict = "moderately_calibrated"
    else:
        verdict = "poorly_calibrated"

    # ─── Score-method stratification ────────────────────────────────
    # Separate calibration metrics by scoring method to expose the
    # heuristic tautology: heuristic ECE ≈ 0 by construction because
    # predicted values ARE the empirical base rates with smoothing.
    score_method_comparison = {}
    if "_score_method" in df.columns:
        for method in df["_score_method"].dropna().unique():
            method_df = df[df["_score_method"] == method]
            n_method = len(method_df)
            if n_method < 5:
                continue
            y_true_m = method_df["vulnerability_found"].values.astype(int)
            y_score_m = method_df["predicted_risk_score"].values.astype(float)
            # ECE/MCE
            m_ece, m_mce = 0.0, 0.0
            m_bin_edges = [j / 10.0 for j in range(11)]
            for bi in range(10):
                lo_m, hi_m = m_bin_edges[bi], m_bin_edges[bi + 1]
                if bi == 9:
                    m_mask = (y_score_m >= lo_m) & (y_score_m <= hi_m)
                else:
                    m_mask = (y_score_m >= lo_m) & (y_score_m < hi_m)
                n_bin_m = int(m_mask.sum())
                if n_bin_m == 0:
                    continue
                gap_m = abs(float(y_score_m[m_mask].mean()) - float(y_true_m[m_mask].mean()))
                m_ece += (n_bin_m / n_method) * gap_m
                m_mce = max(m_mce, gap_m)
            m_brier = float(np.mean((y_score_m - y_true_m) ** 2))
            score_method_comparison[method] = {
                "ece": _safe_float(m_ece, 4) or 0,
                "mce": _safe_float(m_mce, 4) or 0,
                "brier": _safe_float(m_brier, 4) or 0,
                "n": n_method,
            }

    # Tautology detection: heuristic ECE near zero is expected by construction
    heuristic_data = score_method_comparison.get("heuristic") or score_method_comparison.get("heuristic_global")
    model_data = score_method_comparison.get("model")
    tautology_warning = False
    tautology_explanation = None
    if heuristic_data and heuristic_data["ece"] < 0.03:
        tautology_warning = True
        tautology_explanation = (
            "Heuristic ECE ≈ 0 is a mathematical artefact, not evidence of ML calibration. "
            "The heuristic predicts the leave-iteration-out empirical base rate with Bayesian "
            "smoothing — so predicted ≈ observed by construction. Only the 'model' ECE "
            "reflects genuine predictive calibration."
        )

    return {
        "model_available": True,
        "score_method": score_method,
        "total_predictions": total,
        "calibration_curve": calibration_curve,
        "brier_score": _safe_float(brier, 4) or 0,
        "ece": _safe_float(ece_sum, 4) or 0,
        "mce": _safe_float(mce, 4) or 0,
        "verdict": verdict,
        "score_method_comparison": score_method_comparison,
        "tautology_warning": tautology_warning,
        "tautology_explanation": tautology_explanation,
    }


# ── H5 — Execution Efficiency ────────────────────────────────────────
@app.get("/api/hypothesis/execution-efficiency")
def hypothesis_execution_efficiency(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Compare ML-recommended subset vs full suite for detection efficiency."""
    iterations = []
    if not os.path.exists(RESULTS_PATH):
        return {"iterations": [], "summary": None, "verdict": "not_efficient"}

    for fname in sorted(os.listdir(RESULTS_PATH)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(RESULTS_PATH, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
        except Exception:
            continue

        results = data.get("results", [])
        if not results:
            continue

        # Filter by automl_tool — use the field stored in result JSON
        if automl_tool and automl_tool != "all":
            result_tool = data.get("automl_tool", "h2o")  # default h2o for old data
            if result_tool != automl_tool:
                continue

        # Filter by simulation mode — use the direct field stored in result JSON
        if simulation_mode and simulation_mode != "all":
            result_mode = data.get("simulation_mode")
            if result_mode and result_mode != simulation_mode:
                continue
            # Fallback for older results without the direct field: check history CSV
            if not result_mode:
                hist_csv = data.get("history_csv")
                if hist_csv:
                    hist_path = os.path.join("/app", hist_csv) if not os.path.isabs(hist_csv) else hist_csv
                    if os.path.exists(hist_path):
                        try:
                            hdf = pd.read_csv(hist_path)
                            if "simulation_mode" in hdf.columns:
                                modes = hdf["simulation_mode"].dropna().unique()
                                if simulation_mode not in modes:
                                    continue
                        except Exception:
                            pass

        total_tests = len(results)
        rec_tests = sum(1 for r in results if r.get("is_recommended"))
        non_rec_tests = total_tests - rec_tests
        total_vulns = sum(1 for r in results if r.get("vulnerability_found"))
        rec_vulns = sum(1 for r in results if r.get("is_recommended") and r.get("vulnerability_found"))
        non_rec_vulns = total_vulns - rec_vulns
        exec_time = data.get("execution_time_ms", 0) or 0

        # Skip results with no recommendations (early runs before ML scoring)
        if rec_tests == 0:
            continue

        rec_fraction = rec_tests / total_tests if total_tests > 0 else 0
        test_reduction_pct = (1 - rec_fraction) * 100
        detection_coverage_pct = (rec_vulns / total_vulns * 100) if total_vulns > 0 else 100.0
        efficiency_ratio = (detection_coverage_pct / 100) / rec_fraction if rec_fraction > 0 else 0
        est_rec_time = exec_time * rec_fraction
        time_saved = exec_time - est_rec_time
        time_saved_pct = (time_saved / exec_time * 100) if exec_time > 0 else 0

        iterations.append({
            "suite_id": data.get("suite_id"),
            "suite_name": data.get("suite_name", ""),
            "timestamp": data.get("finished_at"),
            "total_tests": total_tests,
            "recommended_tests": rec_tests,
            "non_recommended_tests": non_rec_tests,
            "total_vulns": total_vulns,
            "recommended_vulns": rec_vulns,
            "non_recommended_vulns": non_rec_vulns,
            "test_reduction_pct": _safe_float(test_reduction_pct, 2),
            "detection_coverage_pct": _safe_float(detection_coverage_pct, 2),
            "efficiency_ratio": _safe_float(efficiency_ratio, 3),
            "execution_time_ms": exec_time,
            "estimated_recommended_time_ms": _safe_float(est_rec_time, 1),
            "time_saved_ms": _safe_float(time_saved, 1),
            "time_saved_pct": _safe_float(time_saved_pct, 2),
        })

    if not iterations:
        return {"iterations": [], "summary": {"has_recommendations": False, "total_executions": 0}, "verdict": "not_efficient"}

    # Aggregate summary
    n = len(iterations)
    avg_reduction = sum(it["test_reduction_pct"] for it in iterations) / n
    avg_coverage = sum(it["detection_coverage_pct"] for it in iterations) / n
    avg_efficiency = sum(it["efficiency_ratio"] for it in iterations) / n
    avg_time_saved = sum(it["time_saved_pct"] for it in iterations) / n
    total_time_saved = sum(it["time_saved_ms"] for it in iterations)

    # ─── Statistical tests for efficiency ───
    import numpy as np
    from scipy import stats as scipy_stats

    stats_result = None
    try:
        eff_ratios = [it["efficiency_ratio"] for it in iterations if it["efficiency_ratio"] is not None]
        coverages = [it["detection_coverage_pct"] for it in iterations if it["detection_coverage_pct"] is not None]

        if len(eff_ratios) >= 3:
            # Wilcoxon signed-rank: is efficiency ratio significantly > 1.0?
            shifted = [r - 1.0 for r in eff_ratios]
            try:
                w_stat, w_p = scipy_stats.wilcoxon(shifted, alternative="greater")
            except ValueError:
                # All zeros — perfectly efficient at 1.0
                w_stat, w_p = 0.0, 1.0
            wilcoxon_sig = bool(w_p < 0.05)

            # One-sample t-test: is detection coverage significantly > 80%?
            shifted_cov = [c - 80.0 for c in coverages]
            t_stat, t_p = scipy_stats.ttest_1samp(shifted_cov, 0, alternative="greater")
            coverage_sig = bool(t_p < 0.05)

            # Effect size: rank-biserial r from Wilcoxon signed-rank test
            # r_rb = (W+ - W-) / (W+ + W-), where W+ + W- = n*(n+1)/2
            # Replaces Cohen's d which explodes when std ≈ 0 (d = 77-88)
            n_nonzero = len([s for s in shifted if s != 0])
            total_rank_sum = n_nonzero * (n_nonzero + 1) / 2
            if total_rank_sum > 0:
                # w_stat from wilcoxon is W+ (sum of positive ranks)
                w_minus = total_rank_sum - w_stat
                rank_biserial_r = float((w_stat - w_minus) / total_rank_sum)
            else:
                rank_biserial_r = 0.0
            rank_biserial_interp = (
                "large" if abs(rank_biserial_r) >= 0.5
                else "medium" if abs(rank_biserial_r) >= 0.3
                else "small" if abs(rank_biserial_r) >= 0.1
                else "negligible"
            )

            # 95% bootstrap CI for rank-biserial r
            ci_low_rb = ci_high_rb = None
            try:
                rng = np.random.RandomState(42)
                boot_rs = []
                for _ in range(2000):
                    sample = rng.choice(shifted, size=len(shifted), replace=True)
                    nonzero = [s for s in sample if s != 0]
                    if len(nonzero) < 2:
                        continue
                    try:
                        w_b, _ = scipy_stats.wilcoxon(nonzero, alternative="greater")
                        n_b = len(nonzero)
                        total_b = n_b * (n_b + 1) / 2
                        w_minus_b = total_b - w_b
                        boot_rs.append((w_b - w_minus_b) / total_b)
                    except (ValueError, ZeroDivisionError):
                        continue
                if len(boot_rs) >= 100:
                    ci_low_rb = float(np.percentile(boot_rs, 2.5))
                    ci_high_rb = float(np.percentile(boot_rs, 97.5))
            except Exception:
                pass

            stats_result = {
                "wilcoxon_w": _safe_float(w_stat, 4),
                "wilcoxon_p": _safe_float(w_p, 6),
                "wilcoxon_significant": wilcoxon_sig,
                "coverage_t": _safe_float(t_stat, 4),
                "coverage_p": _safe_float(t_p, 6),
                "coverage_significant": coverage_sig,
                "rank_biserial_r": _safe_float(rank_biserial_r, 4),
                "rank_biserial_interpretation": rank_biserial_interp,
                "rank_biserial_ci_low": _safe_float(ci_low_rb, 4),
                "rank_biserial_ci_high": _safe_float(ci_high_rb, 4),
                "n_iterations": len(eff_ratios),
            }
    except Exception as e:
        logging.warning(f"[Hypothesis] Efficiency stats failed: {e}")

    # Verdict
    if avg_efficiency > 1.5 and avg_coverage > 80:
        verdict = "efficient"
    elif avg_efficiency > 1.0 and avg_coverage > 60:
        verdict = "comparable"
    else:
        verdict = "not_efficient"

    return {
        "iterations": iterations,
        "summary": {
            "avg_test_reduction_pct": _safe_float(avg_reduction, 2),
            "avg_detection_coverage_pct": _safe_float(avg_coverage, 2),
            "avg_efficiency_ratio": _safe_float(avg_efficiency, 3),
            "avg_time_saved_pct": _safe_float(avg_time_saved, 2),
            "total_time_saved_ms": _safe_float(total_time_saved, 1),
            "total_executions": n,
            "has_recommendations": True,
        },
        "stats": stats_result,
        "verdict": verdict,
    }


# ── H6 — Discovery Coverage ──────────────────────────────────────────

@app.get("/api/hypothesis/discovery-coverage")
def hypothesis_discovery_coverage(automl_tool: Optional[str] = None):
    """H6: Do dynamic simulation modes expose more unique vulnerability patterns?

    Compares per-iteration new-vulnerability counts across all available
    simulation modes using Kruskal-Wallis and pairwise Mann-Whitney U tests.
    Returns discovery metrics and statistical results for each mode.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    # Get available modes from data
    modes_resp = available_simulation_modes()
    available_modes = [m for m in modes_resp.get("modes", []) if m and m != "unknown"]

    if len(available_modes) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need at least 2 simulation modes, found: {available_modes}",
            "modes": available_modes,
        }

    # Gather per-iteration new_vulns for each mode
    mode_data = {}
    for mode in available_modes:
        iter_data = hypothesis_iteration_metrics(simulation_mode=mode, automl_tool=automl_tool, phase="framework")
        iterations = iter_data.get("iterations", [])
        if not iterations:
            continue

        new_vulns_per_iter = [it.get("new_vulns", 0) for it in iterations]
        cumulative = [it.get("cumulative_unique_vulns", 0) for it in iterations]
        total_unique = cumulative[-1] if cumulative else 0

        # Last iteration with a new discovery
        last_discovery_iter = 0
        for i, nv in enumerate(new_vulns_per_iter):
            if nv > 0:
                last_discovery_iter = i + 1  # 1-indexed

        mode_data[mode] = {
            "new_vulns_per_iter": new_vulns_per_iter,
            "total_unique_vulns": total_unique,
            "total_iterations": len(iterations),
            "last_discovery_iteration": last_discovery_iter,
            "mean_new_vulns": _safe_float(np.mean(new_vulns_per_iter), 4),
            "median_new_vulns": _safe_float(np.median(new_vulns_per_iter), 4),
        }

    if len(mode_data) < 2:
        return {
            "status": "insufficient_data",
            "message": "Not enough modes with data for comparison",
            "modes": list(mode_data.keys()),
        }

    # ─── Cross-mode comparison ───
    # Baseline is deterministic (or first mode alphabetically)
    baseline_mode = "deterministic" if "deterministic" in mode_data else sorted(mode_data.keys())[0]
    baseline_unique = mode_data[baseline_mode]["total_unique_vulns"]

    # Add lift vs baseline
    for mode, data in mode_data.items():
        if mode == baseline_mode:
            data["lift_pct"] = 0.0
        else:
            data["lift_pct"] = _safe_float(
                ((data["total_unique_vulns"] - baseline_unique) / baseline_unique * 100)
                if baseline_unique > 0 else 0, 1
            )

    # ─── Kruskal-Wallis test (non-parametric ANOVA) ───
    groups = [mode_data[m]["new_vulns_per_iter"] for m in sorted(mode_data.keys())]
    kruskal_h = kruskal_p = None
    try:
        if len(groups) >= 2 and all(len(g) > 0 for g in groups):
            h_stat, kw_p = scipy_stats.kruskal(*groups)
            kruskal_h = _safe_float(h_stat, 4)
            kruskal_p = _safe_float(kw_p, 6)
    except Exception:
        pass

    # ─── Pairwise Mann-Whitney U tests ───
    pairwise = []
    sorted_modes = sorted(mode_data.keys())
    for i in range(len(sorted_modes)):
        for j in range(i + 1, len(sorted_modes)):
            m1, m2 = sorted_modes[i], sorted_modes[j]
            g1 = mode_data[m1]["new_vulns_per_iter"]
            g2 = mode_data[m2]["new_vulns_per_iter"]
            try:
                u_stat, mw_p = scipy_stats.mannwhitneyu(g2, g1, alternative="greater")
                is_sig = bool(mw_p < 0.05)
                pairwise.append({
                    "mode_a": m1,
                    "mode_b": m2,
                    "mann_whitney_u": _safe_float(u_stat, 4),
                    "p_value": _safe_float(mw_p, 6),
                    "significant": is_sig,
                    "direction": f"{m2} > {m1}" if is_sig else "no difference",
                })
            except Exception:
                pairwise.append({
                    "mode_a": m1,
                    "mode_b": m2,
                    "mann_whitney_u": None,
                    "p_value": None,
                    "significant": False,
                    "direction": "error",
                })

    # ─── Verdict ───
    # H6 supported if at least one dynamic mode has significantly more
    # new vulns than deterministic AND discovers >20% more unique vulns
    any_significant = any(
        p["significant"] and p["mode_a"] == baseline_mode
        for p in pairwise
    )
    any_large_lift = any(
        mode_data[m]["lift_pct"] > 20
        for m in mode_data if m != baseline_mode
    )

    if any_significant and any_large_lift:
        verdict = "supported"
    elif any_large_lift:
        verdict = "trending"
    else:
        verdict = "not_supported"

    # Build clean response (strip per-iter arrays from mode_data)
    modes_summary = {}
    for mode, data in mode_data.items():
        modes_summary[mode] = {
            "total_unique_vulns": data["total_unique_vulns"],
            "total_iterations": data["total_iterations"],
            "last_discovery_iteration": data["last_discovery_iteration"],
            "mean_new_vulns_per_iter": data["mean_new_vulns"],
            "median_new_vulns_per_iter": data["median_new_vulns"],
            "lift_pct": data["lift_pct"],
        }

    return {
        "status": "ok",
        "baseline_mode": baseline_mode,
        "modes": modes_summary,
        "kruskal_wallis_h": kruskal_h,
        "kruskal_wallis_p": kruskal_p,
        "kruskal_wallis_significant": bool(kruskal_p is not None and kruskal_p < 0.05),
        "pairwise_tests": pairwise,
        "verdict": verdict,
    }


# ── Experiment Timing ───────────────────────────────────────────────

@app.get("/api/hypothesis/experiment-timing")
def hypothesis_experiment_timing():
    """Per-experiment timing data, grouped by automl_tool and simulation mode.

    Reads experiment_summary.json for total experiment durations, and
    also scans individual experiment directories to compute per-iteration
    execution times even when the summary is unavailable.
    """
    import glob as _glob
    from datetime import datetime as _dt

    timing_data = []

    # ── Source 1: experiment_summary.json (has total durations) ───
    summary_path = os.path.join(EXPERIMENTS_PATH, "experiment_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path) as f:
                summary = json.load(f)
            for entry in summary:
                timing_data.append({
                    "name": entry.get("name", ""),
                    "automl_tool": entry.get("automl_tool", "h2o"),
                    "simulation_mode": entry.get("mode", "unknown"),
                    "status": entry.get("status", "unknown"),
                    "iterations": entry.get("iterations", 0),
                    "duration_seconds": entry.get("duration_seconds"),
                    "duration_formatted": entry.get("duration_formatted", ""),
                    "final_auc": entry.get("final_auc"),
                    "avg_detection_rate": entry.get("avg_detection_rate"),
                    "total_vulnerabilities": entry.get("total_vulnerabilities", 0),
                    "source": "experiment_summary",
                })
        except Exception as e:
            logging.warning(f"[Timing] Failed to read experiment_summary.json: {e}")

    # ── Source 2: scan individual exp_ directories ───
    # This catches experiments not yet in the summary (e.g. still running)
    if not timing_data:
        exp_dirs = sorted(_glob.glob(os.path.join(EXPERIMENTS_PATH, "exp_*")))
        fw_mode_groups = {}  # (automl_tool, sim_mode) → list of per-iteration data

        for exp_dir in exp_dirs:
            hist_path = os.path.join(exp_dir, "history.csv")
            if not os.path.exists(hist_path):
                continue
            try:
                df = pd.read_csv(hist_path)
                if df.empty:
                    continue

                automl_tool = "h2o"
                if "automl_tool" in df.columns:
                    automl_tool = df["automl_tool"].dropna().iloc[0] if not df["automl_tool"].dropna().empty else "h2o"

                # Skip Phase 2 baseline experiments — they use automl_tool="h2o"
                # as a placeholder but are not actual framework runs, so
                # including them inflates h2o's timing numbers.
                _NON_ML_TIMING = {"random", "cvss_priority", "round_robin", "no_ml"}
                if "baseline_strategy" in df.columns:
                    _bs_val = df["baseline_strategy"].dropna()
                    if not _bs_val.empty and _bs_val.iloc[0] in _NON_ML_TIMING:
                        continue

                sim_mode = "unknown"
                if "simulation_mode" in df.columns:
                    sim_mode = df["simulation_mode"].dropna().iloc[0] if not df["simulation_mode"].dropna().empty else "unknown"

                key = (automl_tool, sim_mode)
                if key not in fw_mode_groups:
                    fw_mode_groups[key] = {
                        "total_exec_time_ms": 0,
                        "iterations": 0,
                        "timestamps": [],
                    }

                exec_time = df["execution_time_ms"].sum() if "execution_time_ms" in df.columns else 0
                fw_mode_groups[key]["total_exec_time_ms"] += exec_time
                fw_mode_groups[key]["iterations"] += 1

                if "timestamp" in df.columns:
                    timestamps = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
                    if not timestamps.empty:
                        fw_mode_groups[key]["timestamps"].extend([
                            timestamps.min(), timestamps.max(),
                        ])
            except Exception:
                continue

        for (fw, mode), data in fw_mode_groups.items():
            duration_secs = None
            if data["timestamps"]:
                ts_min = min(data["timestamps"])
                ts_max = max(data["timestamps"])
                duration_secs = (ts_max - ts_min).total_seconds()

            timing_data.append({
                "name": f"{fw}_{mode}",
                "automl_tool": fw,
                "simulation_mode": mode,
                "status": "derived",
                "iterations": data["iterations"],
                "duration_seconds": duration_secs,
                "duration_formatted": _format_duration_secs(duration_secs) if duration_secs else None,
                "total_exec_time_ms": int(data["total_exec_time_ms"]),
                "source": "derived_from_history",
            })

    # ── Build framework summary ───
    fw_summary = {}
    for entry in timing_data:
        # Skip Phase 2 baseline experiments — they use automl_tool="h2o" as a
        # placeholder but are not actual H2O runs, so excluding them prevents
        # inflating H2O's total duration.
        if entry.get("name", "").startswith("BASELINE-") or entry.get("baseline_strategy"):
            continue

        fw = entry.get("automl_tool", "h2o")
        mode = entry.get("simulation_mode", "unknown")
        dur = entry.get("duration_seconds")

        if fw not in fw_summary:
            fw_summary[fw] = {
                "total_duration_seconds": 0,
                "total_experiments": 0,
                "modes": {},
            }

        fw_summary[fw]["total_experiments"] += 1
        if dur:
            fw_summary[fw]["total_duration_seconds"] += dur

        fw_summary[fw]["modes"][mode] = {
            "duration_seconds": dur,
            "duration_formatted": entry.get("duration_formatted"),
            "final_auc": entry.get("final_auc"),
            "avg_detection_rate": entry.get("avg_detection_rate"),
            "iterations": entry.get("iterations"),
        }

    # Total formatted
    for fw in fw_summary:
        fw_summary[fw]["total_duration_formatted"] = _format_duration_secs(
            fw_summary[fw]["total_duration_seconds"]
        )

    # ── Training time from model metrics ───
    training_times = {}
    try:
        from automl.pipeline import get_all_model_metrics
        all_metrics = get_all_model_metrics()
        for fw, metrics in all_metrics.items():
            training_times[fw] = {
                "training_time_secs": metrics.get("training_time_secs"),
                "auc": metrics.get("auc"),
                "training_rows": metrics.get("training_rows"),
            }
    except Exception:
        pass

    return {
        "experiments": timing_data,
        "by_framework": fw_summary,
        "training_times": training_times,
    }


def _format_duration_secs(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    if seconds is None:
        return None
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ── H7 — Cross-Framework Comparison ─────────────────────────────────

@app.get("/api/hypothesis/cross-framework")
def hypothesis_cross_framework(simulation_mode: Optional[str] = None):
    """H7: Do different AutoML frameworks produce significantly different results?

    Compares AUC, detection rate, and training time across all frameworks
    that have experiment data. Uses Kruskal-Wallis for omnibus test and
    pairwise Mann-Whitney U for post-hoc comparisons.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    # Load all experiment history once (cached) to avoid reading 1500 files per framework
    # phase="framework" excludes Phase 2 baseline rows so h2o is not inflated vs other frameworks
    all_df = _load_aggregated_history(simulation_mode=simulation_mode, phase="framework")

    if all_df is None or all_df.empty:
        return {
            "status": "insufficient_data",
            "message": "No experiment history data available.",
            "frameworks": {},
        }

    # Normalise columns
    all_df = all_df.copy()
    all_df["vulnerability_found"] = pd.to_numeric(
        all_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)
    if "automl_tool" not in all_df.columns:
        all_df["automl_tool"] = "h2o"
    else:
        all_df["automl_tool"] = all_df["automl_tool"].fillna("h2o")

    # Determine the grouping column for "per-experiment" detection rates
    exp_group_col = None
    for col in ("simulation_iteration", "experiment_id"):
        if col in all_df.columns:
            exp_group_col = col
            break

    frameworks_with_data = {}
    all_frameworks = ["h2o", "autogluon", "pycaret", "tpot", "autosklearn"]

    for fw in all_frameworks:
        fw_df = all_df[all_df["automl_tool"] == fw]
        if fw_df.empty:
            continue

        # Per-experiment detection rates (avoid reading files per framework)
        if exp_group_col:
            per_exp = (
                fw_df.groupby(exp_group_col)["vulnerability_found"]
                .agg(total_tests="count", total_vulns="sum")
                .reset_index()
            )
            detection_rates = (
                (per_exp["total_vulns"] / per_exp["total_tests"])
                .fillna(0)
                .round(4)
                .tolist()
            )
            vuln_counts = per_exp["total_vulns"].tolist()
        else:
            total_tests = len(fw_df)
            total_vulns = int(fw_df["vulnerability_found"].sum())
            detection_rates = [round(total_vulns / total_tests, 4)] if total_tests > 0 else [0]
            vuln_counts = [total_vulns]

        # Compute in-sample AUC from heuristic risk scores
        # Uses sklearn roc_auc_score for standard computation.
        # NOTE: This is in-sample AUC (heuristic trained on same data).
        # Temporal held-out AUC is computed separately in Phase 1.
        auc = None
        brier = None
        try:
            from sklearn.metrics import roc_auc_score, brier_score_loss
            scored_df = _heuristic_risk_scores(fw_df)
            if scored_df is not None and "predicted_risk_score" in scored_df.columns:
                y_true = scored_df["vulnerability_found"].values.astype(int)
                y_score = scored_df["predicted_risk_score"].values.astype(float)
                # Need both classes present
                if len(np.unique(y_true)) >= 2 and len(y_true) >= 10:
                    auc = float(roc_auc_score(y_true, y_score))
                    brier = float(brier_score_loss(y_true, y_score))
        except Exception as _auc_err:
            logging.debug(f"[Hypothesis] AUC computation failed for {fw}: {_auc_err}")

        frameworks_with_data[fw] = {
            "detection_rates": detection_rates,
            "vuln_counts": vuln_counts,
            "auc": _safe_float(auc, 4) if auc is not None else None,
            "brier_score": _safe_float(brier, 4) if brier is not None else None,
            "auc_type": "in_sample_heuristic",
            "n_iterations": len(detection_rates),
            "mean_detection_rate": _safe_float(np.mean(detection_rates), 4),
            "std_detection_rate": _safe_float(np.std(detection_rates), 4),
            "median_detection_rate": _safe_float(np.median(detection_rates), 4),
            "mean_vulns": _safe_float(np.mean(vuln_counts), 2),
        }

    if len(frameworks_with_data) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need data from at least 2 frameworks. Found: {list(frameworks_with_data.keys())}",
            "frameworks": {
                fw: {k: v for k, v in data.items() if k != "detection_rates" and k != "vuln_counts"}
                for fw, data in frameworks_with_data.items()
            },
        }

    # ─── Kruskal-Wallis omnibus test on detection rates ───
    fw_names = sorted(frameworks_with_data.keys())
    groups = [frameworks_with_data[fw]["detection_rates"] for fw in fw_names]
    kruskal_result = None
    try:
        if all(len(g) >= 2 for g in groups):
            h_stat, kw_p = scipy_stats.kruskal(*groups)
            kruskal_result = {
                "h_statistic": _safe_float(h_stat, 4),
                "p_value": _safe_float(kw_p, 6),
                "significant": bool(kw_p < 0.05),
                "test": "Kruskal-Wallis H",
                "measure": "detection_rate",
                "n_groups": len(groups),
            }
    except Exception as e:
        logging.warning(f"[Hypothesis] Cross-framework Kruskal-Wallis failed: {e}")

    # ─── Pairwise Mann-Whitney U post-hoc tests ───
    pairwise = []
    for i in range(len(fw_names)):
        for j in range(i + 1, len(fw_names)):
            fw_a, fw_b = fw_names[i], fw_names[j]
            g_a = frameworks_with_data[fw_a]["detection_rates"]
            g_b = frameworks_with_data[fw_b]["detection_rates"]
            try:
                u_stat, mw_p = scipy_stats.mannwhitneyu(g_a, g_b, alternative="two-sided")
                # Effect size: rank-biserial correlation r = 1 - (2U)/(n1*n2)
                n1, n2 = len(g_a), len(g_b)
                rank_biserial = 1 - (2 * u_stat) / (n1 * n2) if (n1 * n2) > 0 else 0
                effect_interp = (
                    "large" if abs(rank_biserial) >= 0.5
                    else "medium" if abs(rank_biserial) >= 0.3
                    else "small" if abs(rank_biserial) >= 0.1
                    else "negligible"
                )

                # Bonferroni correction for multiple comparisons
                n_comparisons = len(fw_names) * (len(fw_names) - 1) // 2
                bonferroni_p = min(mw_p * n_comparisons, 1.0)

                pairwise.append({
                    "framework_a": fw_a,
                    "framework_b": fw_b,
                    "mann_whitney_u": _safe_float(u_stat, 4),
                    "p_value": _safe_float(mw_p, 6),
                    "bonferroni_p": _safe_float(bonferroni_p, 6),
                    "significant_raw": bool(mw_p < 0.05),
                    "significant_corrected": bool(bonferroni_p < 0.05),
                    "rank_biserial_r": _safe_float(rank_biserial, 4),
                    "effect_size": effect_interp,
                    "mean_a": _safe_float(np.mean(g_a), 4),
                    "mean_b": _safe_float(np.mean(g_b), 4),
                    "better": fw_a if np.mean(g_a) > np.mean(g_b) else fw_b,
                })
            except Exception as e:
                logging.debug(f"[Hypothesis] Mann-Whitney {fw_a} vs {fw_b}: {e}")
                pairwise.append({
                    "framework_a": fw_a,
                    "framework_b": fw_b,
                    "mann_whitney_u": None,
                    "p_value": None,
                    "significant_raw": False,
                    "significant_corrected": False,
                    "error": str(e),
                })

    # ─── Framework ranking ───
    ranking = sorted(
        [
            {
                "framework": fw,
                "mean_detection_rate": data["mean_detection_rate"],
                "auc": data["auc"],
                "n_iterations": data["n_iterations"],
            }
            for fw, data in frameworks_with_data.items()
        ],
        key=lambda x: (x["auc"] or 0, x["mean_detection_rate"] or 0),
        reverse=True,
    )
    for rank_idx, entry in enumerate(ranking):
        entry["rank"] = rank_idx + 1

    # ─── Verdict ───
    any_sig_corrected = any(p.get("significant_corrected") for p in pairwise)
    any_sig_raw = any(p.get("significant_raw") for p in pairwise)

    if any_sig_corrected:
        verdict = "significant_differences"
    elif any_sig_raw:
        verdict = "trending_differences"
    else:
        verdict = "no_significant_differences"

    # Build clean framework summary (strip raw arrays)
    fw_summary = {}
    for fw, data in frameworks_with_data.items():
        fw_summary[fw] = {
            k: v for k, v in data.items()
            if k not in ("detection_rates", "vuln_counts")
        }

    # ─── Enrich with timing data ───
    timing = None
    try:
        timing_resp = hypothesis_experiment_timing()
        timing = timing_resp.get("by_framework", {})
        training_times = timing_resp.get("training_times", {})

        # Merge timing into framework summary and ranking
        for fw in fw_summary:
            if fw in timing:
                fw_summary[fw]["total_duration_seconds"] = timing[fw].get("total_duration_seconds")
                fw_summary[fw]["total_duration_formatted"] = timing[fw].get("total_duration_formatted")
                fw_summary[fw]["modes_timing"] = timing[fw].get("modes", {})
            if fw in training_times:
                fw_summary[fw]["training_time_secs"] = training_times[fw].get("training_time_secs")

        for entry in ranking:
            fw = entry["framework"]
            if fw in timing:
                entry["total_duration_seconds"] = timing[fw].get("total_duration_seconds")
                entry["total_duration_formatted"] = timing[fw].get("total_duration_formatted")
            if fw in training_times:
                entry["training_time_secs"] = training_times[fw].get("training_time_secs")
    except Exception as e:
        logging.warning(f"[Hypothesis] Failed to enrich H7 with timing: {e}")

    # Note when framework differences vanish under simulation noise
    noise_dominance_note = None
    _mode = simulation_mode or "all"
    if verdict == "no_significant_differences" and _mode in ("realistic", "medium"):
        noise_dominance_note = (
            f"No significant framework differences in {_mode} mode. This likely "
            f"reflects environment noise (service outages, patch regressions, FP/FN "
            f"injection) dominating framework-specific scoring differences rather "
            f"than true framework equivalence. See /api/hypothesis/framework-interaction "
            f"for a cross-mode variance decomposition."
        )

    return {
        "status": "ok",
        "frameworks": fw_summary,
        "ranking": ranking,
        "kruskal_wallis": kruskal_result,
        "pairwise_tests": pairwise,
        "n_frameworks": len(frameworks_with_data),
        "simulation_mode": simulation_mode or "all",
        "verdict": verdict,
        "timing": timing,
        "noise_dominance_note": noise_dominance_note,
    }


# ── H7+ — Framework × Mode Interaction Analysis ───────────────────

@app.get("/api/hypothesis/framework-interaction")
def hypothesis_framework_interaction():
    """Analyse framework × simulation-mode interaction effects.

    Answers: "Does framework choice matter equally across simulation modes,
    or does environment noise dominate in realistic mode?"

    Uses two-way sum-of-squares decomposition (Type I) and per-mode
    Kruskal-Wallis tests to separate framework, mode, and interaction
    variance contributions.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    # Load ALL history (no mode filter) — phase="framework" excludes Phase 2 baselines
    all_df = _load_aggregated_history(simulation_mode=None, phase="framework")
    if all_df is None or all_df.empty:
        return {"status": "insufficient_data", "message": "No experiment data available."}

    all_df = all_df.copy()
    all_df["vulnerability_found"] = pd.to_numeric(
        all_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    if "automl_tool" not in all_df.columns or "simulation_mode" not in all_df.columns:
        return {"status": "insufficient_data", "message": "Missing automl_tool or simulation_mode columns."}

    # Need simulation_iteration for per-iteration detection rates
    iter_col = None
    for col in ("simulation_iteration", "experiment_id"):
        if col in all_df.columns:
            iter_col = col
            break
    if iter_col is None:
        return {"status": "insufficient_data", "message": "No iteration column available."}

    # Filter to ML-guided experiments only (exclude baselines)
    if "baseline_strategy" in all_df.columns:
        all_df = all_df[all_df["baseline_strategy"].isin(["ml_guided", None, ""])]
        all_df = all_df[all_df["baseline_strategy"].fillna("ml_guided") == "ml_guided"]

    # Compute per-(framework, mode, iteration) detection rates
    grouped = (
        all_df.groupby(["automl_tool", "simulation_mode", iter_col])["vulnerability_found"]
        .agg(total="count", vulns="sum")
        .reset_index()
    )
    grouped["detection_rate"] = (grouped["vulns"] / grouped["total"]).fillna(0)

    frameworks = sorted(grouped["automl_tool"].unique().tolist())
    modes = sorted(grouped["simulation_mode"].unique().tolist())

    if len(frameworks) < 2 or len(modes) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need ≥2 frameworks and ≥2 modes. Found {len(frameworks)} frameworks, {len(modes)} modes.",
        }

    # ─── Two-way variance decomposition (Type I SS) ───
    y = grouped["detection_rate"].values
    grand_mean = float(np.mean(y))
    ss_total = float(np.sum((y - grand_mean) ** 2))

    # SS for framework (main effect A)
    fw_means = grouped.groupby("automl_tool")["detection_rate"].mean()
    ss_framework = 0.0
    for fw in frameworks:
        fw_rows = grouped[grouped["automl_tool"] == fw]
        ss_framework += len(fw_rows) * (float(fw_means[fw]) - grand_mean) ** 2

    # SS for mode (main effect B)
    mode_means = grouped.groupby("simulation_mode")["detection_rate"].mean()
    ss_mode = 0.0
    for mode in modes:
        mode_rows = grouped[grouped["simulation_mode"] == mode]
        ss_mode += len(mode_rows) * (float(mode_means[mode]) - grand_mean) ** 2

    # SS for interaction (cell means - marginal means - grand mean)
    cell_means = grouped.groupby(["automl_tool", "simulation_mode"])["detection_rate"].mean()
    ss_interaction = 0.0
    for fw in frameworks:
        for mode in modes:
            cell_key = (fw, mode)
            if cell_key in cell_means.index:
                cell_rows = grouped[(grouped["automl_tool"] == fw) & (grouped["simulation_mode"] == mode)]
                cell_mean = float(cell_means[cell_key])
                expected = float(fw_means[fw]) + float(mode_means[mode]) - grand_mean
                ss_interaction += len(cell_rows) * (cell_mean - expected) ** 2

    ss_residual = max(ss_total - ss_framework - ss_mode - ss_interaction, 0)

    # Eta-squared (proportion of variance explained)
    def _eta_sq(ss_effect, ss_tot):
        return float(ss_effect / ss_tot) if ss_tot > 0 else 0.0

    def _eta_interp(eta):
        if eta >= 0.14:
            return "large"
        elif eta >= 0.06:
            return "medium"
        elif eta >= 0.01:
            return "small"
        return "negligible"

    eta_fw = _eta_sq(ss_framework, ss_total)
    eta_mode = _eta_sq(ss_mode, ss_total)
    eta_interaction = _eta_sq(ss_interaction, ss_total)
    eta_residual = _eta_sq(ss_residual, ss_total)

    variance_decomposition = {
        "framework": {
            "ss": _safe_float(ss_framework, 4),
            "eta_squared": _safe_float(eta_fw, 4),
            "interpretation": _eta_interp(eta_fw),
        },
        "simulation_mode": {
            "ss": _safe_float(ss_mode, 4),
            "eta_squared": _safe_float(eta_mode, 4),
            "interpretation": _eta_interp(eta_mode),
        },
        "interaction": {
            "ss": _safe_float(ss_interaction, 4),
            "eta_squared": _safe_float(eta_interaction, 4),
            "interpretation": _eta_interp(eta_interaction),
        },
        "residual": {
            "ss": _safe_float(ss_residual, 4),
            "eta_squared": _safe_float(eta_residual, 4),
        },
        "total_ss": _safe_float(ss_total, 4),
        "n_observations": len(grouped),
    }

    # ─── Per-mode Kruskal-Wallis (framework differences within each mode) ───
    per_mode_significance = {}
    for mode in modes:
        mode_df = grouped[grouped["simulation_mode"] == mode]
        fw_groups = []
        fw_names_in_mode = []
        for fw in frameworks:
            fw_rates = mode_df[mode_df["automl_tool"] == fw]["detection_rate"].values
            if len(fw_rates) >= 2:
                fw_groups.append(fw_rates)
                fw_names_in_mode.append(fw)

        if len(fw_groups) >= 2:
            try:
                h_stat, kw_p = scipy_stats.kruskal(*fw_groups)
                per_mode_significance[mode] = {
                    "kruskal_h": _safe_float(h_stat, 4),
                    "p_value": _safe_float(kw_p, 6),
                    "significant": bool(kw_p < 0.05),
                    "n_frameworks": len(fw_groups),
                    "mean_rates": {
                        fw: _safe_float(float(np.mean(g)), 4)
                        for fw, g in zip(fw_names_in_mode, fw_groups)
                    },
                }
            except Exception:
                per_mode_significance[mode] = {"error": "Kruskal-Wallis failed"}
        else:
            per_mode_significance[mode] = {"error": "Insufficient framework data"}

    # ─── Conclusion ───
    sig_modes = [m for m, d in per_mode_significance.items() if d.get("significant")]
    nonsig_modes = [m for m, d in per_mode_significance.items()
                    if d.get("significant") is not None and not d.get("significant")]

    if sig_modes and nonsig_modes:
        conclusion = (
            f"Framework choice significantly affects detection rates in "
            f"{', '.join(sig_modes)} mode(s) but environment noise dominates in "
            f"{', '.join(nonsig_modes)} mode(s). "
            f"Mode effect (η²={eta_mode:.3f}) "
            f"{'>' if eta_mode > eta_fw else '<'} "
            f"framework effect (η²={eta_fw:.3f})."
        )
    elif sig_modes:
        conclusion = (
            f"Framework choice matters across all tested modes: {', '.join(sig_modes)}. "
            f"Framework η²={eta_fw:.3f}, mode η²={eta_mode:.3f}."
        )
    else:
        conclusion = (
            f"No significant framework differences in any mode. "
            f"Environment noise dominates (mode η²={eta_mode:.3f} >> framework η²={eta_fw:.3f})."
        )

    return {
        "status": "ok",
        "variance_decomposition": variance_decomposition,
        "per_mode_framework_significance": per_mode_significance,
        "frameworks": frameworks,
        "modes": modes,
        "grand_mean_detection_rate": _safe_float(grand_mean, 4),
        "conclusion": conclusion,
    }


# ── H8 — Temporal Predictive Validity ──────────────────────────────

@app.get("/api/hypothesis/temporal-validation")
def hypothesis_temporal_validation(
    simulation_mode: Optional[str] = None,
    automl_tool: Optional[str] = None,
):
    """H8: Does the model genuinely predict unseen iterations?

    Reads temporal_metrics.csv files from experiment directories to show
    held-out AUC/Brier/ECE progression as the training window expands.
    Only available when experiments are run with temporal_training=True.
    """
    from utils.temporal_eval import load_temporal_metrics
    import numpy as np

    sim = simulation_mode or "deterministic"
    aml = automl_tool or "h2o"

    # Collect temporal metrics from experiment dirs
    all_metrics = []
    if os.path.exists(EXPERIMENTS_PATH):
        for exp_dir in sorted(os.listdir(EXPERIMENTS_PATH)):
            if not exp_dir.startswith("exp_"):
                continue
            csv_path = os.path.join(EXPERIMENTS_PATH, exp_dir, "temporal_metrics.csv")
            df = load_temporal_metrics(csv_path)
            if df is not None and not df.empty:
                all_metrics.append(df)

    # Also check loop state for in-memory temporal data
    with _loop_lock:
        loop_iters = _loop_state.get("iterations", [])
        temporal_from_loop = [
            it for it in loop_iters
            if it.get("temporal_auc") is not None
        ]

    if not all_metrics and not temporal_from_loop:
        return {
            "status": "no_temporal_data",
            "message": "No temporal validation data found. Run experiments with temporal_training=True.",
            "iterations": [],
            "summary": None,
            "verdict": "insufficient_data",
        }

    # Combine from CSV files
    if all_metrics:
        combined = pd.concat(all_metrics, ignore_index=True)
    else:
        combined = pd.DataFrame()

    # Add from loop state if available
    if temporal_from_loop:
        loop_df = pd.DataFrame([{
            "iteration": it["iteration"],
            "auc_roc": it.get("temporal_auc"),
            "brier_score": it.get("temporal_brier"),
            "ece": it.get("temporal_ece"),
            "train_window_size": it.get("train_window_size"),
            "score_method": it.get("score_method", "unknown"),
        } for it in temporal_from_loop])
        combined = pd.concat([combined, loop_df], ignore_index=True) if not combined.empty else loop_df

    if combined.empty:
        return {
            "status": "no_temporal_data",
            "iterations": [],
            "summary": None,
            "verdict": "insufficient_data",
        }

    # Build per-iteration response
    iterations = []
    for _, row in combined.iterrows():
        iterations.append({
            "iteration": int(row.get("iteration", 0)),
            "auc_roc": float(row["auc_roc"]) if pd.notna(row.get("auc_roc")) else None,
            "brier_score": float(row["brier_score"]) if pd.notna(row.get("brier_score")) else None,
            "ece": float(row["ece"]) if pd.notna(row.get("ece")) else None,
            "train_window_size": int(row.get("train_window_size", 0)),
            "score_method": str(row.get("score_method", "unknown")) if pd.notna(row.get("score_method")) else "unknown",
        })

    # Sort by iteration
    iterations.sort(key=lambda x: x["iteration"])

    # Summary statistics
    aucs = [it["auc_roc"] for it in iterations if it["auc_roc"] is not None]
    briers = [it["brier_score"] for it in iterations if it["brier_score"] is not None]
    eces = [it["ece"] for it in iterations if it["ece"] is not None]

    summary = {
        "n_evaluations": len(iterations),
        "mean_auc": float(np.mean(aucs)) if aucs else None,
        "std_auc": float(np.std(aucs)) if aucs else None,
        "mean_brier": float(np.mean(briers)) if briers else None,
        "mean_ece": float(np.mean(eces)) if eces else None,
        "auc_trend": None,  # Computed below
    }

    # Check if AUC improves over time (Spearman correlation)
    if len(aucs) >= 5:
        from scipy import stats as scipy_stats
        iters_for_trend = [it["iteration"] for it in iterations if it["auc_roc"] is not None]
        rho, p = scipy_stats.spearmanr(iters_for_trend, aucs)
        summary["auc_trend"] = {
            "spearman_rho": float(rho) if not np.isnan(rho) else None,
            "p_value": float(p) if not np.isnan(p) else None,
            "direction": "improving" if rho > 0 and p < 0.05 else "stable" if p >= 0.05 else "declining",
        }

    # Verdict
    mean_auc = summary.get("mean_auc")
    mean_brier = summary.get("mean_brier")
    if mean_auc is not None and mean_auc > 0.65 and mean_brier is not None and mean_brier < 0.25:
        verdict = "supported"
    elif mean_auc is not None and mean_auc > 0.55:
        verdict = "trending"
    elif mean_auc is not None:
        verdict = "not_supported"
    else:
        verdict = "insufficient_data"

    return {
        "status": "ok",
        "iterations": iterations,
        "summary": summary,
        "verdict": verdict,
    }


# ── H9 — ML Value Over Baselines ──────────────────────────────────

@app.get("/api/hypothesis/baseline-comparison")
def hypothesis_baseline_comparison(
    simulation_mode: Optional[str] = None,
):
    """H9: Does ML-guided testing beat non-ML baselines?

    Compares detection rates between ML-guided experiments and baseline
    experiments (random, CVSS-priority, round-robin, no-ML).
    Data comes from history.csv files tagged with baseline_strategy column.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    sim = simulation_mode or "deterministic"

    # Load aggregated history
    all_df = _load_aggregated_history(simulation_mode=sim)
    if all_df is None or all_df.empty:
        return {
            "status": "insufficient_data",
            "message": "No experiment data available.",
            "strategies": {},
        }

    all_df = all_df.copy()
    all_df["vulnerability_found"] = pd.to_numeric(
        all_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    # Determine strategy column
    if "baseline_strategy" not in all_df.columns:
        all_df["baseline_strategy"] = "ml_guided"  # Default: ML experiments

    all_df["baseline_strategy"] = all_df["baseline_strategy"].fillna("ml_guided")

    # Grouping column for per-iteration rates
    exp_group_col = None
    for col in ("simulation_iteration", "experiment_id"):
        if col in all_df.columns:
            exp_group_col = col
            break

    strategies = {}
    for strategy in all_df["baseline_strategy"].unique():
        strat_df = all_df[all_df["baseline_strategy"] == strategy]
        if strat_df.empty:
            continue

        if exp_group_col:
            per_iter = (
                strat_df.groupby(exp_group_col)["vulnerability_found"]
                .agg(total="count", vulns="sum")
                .reset_index()
            )
            rates = (per_iter["vulns"] / per_iter["total"]).fillna(0).tolist()
        else:
            total = len(strat_df)
            vulns = int(strat_df["vulnerability_found"].sum())
            rates = [vulns / total] if total > 0 else [0]

        strategies[strategy] = {
            "detection_rates": rates,
            "mean_rate": float(np.mean(rates)),
            "std_rate": float(np.std(rates)),
            "n_iterations": len(rates),
            "total_tests": len(strat_df),
            "total_vulns": int(strat_df["vulnerability_found"].sum()),
        }

    # Compute ML advantage over each baseline
    ml_data = strategies.get("ml_guided")
    if ml_data:
        for name, data in strategies.items():
            if name == "ml_guided":
                data["lift_vs_random"] = None
                continue
            if data["mean_rate"] > 0:
                data["lift_vs_ml"] = float(
                    (ml_data["mean_rate"] - data["mean_rate"]) / data["mean_rate"] * 100
                )
            else:
                data["lift_vs_ml"] = None

            # Mann-Whitney U test: ML vs baseline
            if len(ml_data["detection_rates"]) >= 2 and len(data["detection_rates"]) >= 2:
                try:
                    u_stat, p_val = scipy_stats.mannwhitneyu(
                        ml_data["detection_rates"],
                        data["detection_rates"],
                        alternative="greater",
                    )
                    n1, n2 = len(ml_data["detection_rates"]), len(data["detection_rates"])
                    rank_biserial = 1 - (2 * u_stat) / (n1 * n2) if (n1 * n2) > 0 else 0
                    data["vs_ml_test"] = {
                        "u_statistic": float(u_stat),
                        "p_value": float(p_val),
                        "significant": bool(p_val < 0.05),
                        "rank_biserial_r": float(rank_biserial),
                    }
                except Exception:
                    data["vs_ml_test"] = None

    # Strip raw rates from response
    strategy_summary = {}
    for name, data in strategies.items():
        strategy_summary[name] = {k: v for k, v in data.items() if k != "detection_rates"}

    # Verdict
    if ml_data and len(strategies) >= 2:
        ml_rate = ml_data["mean_rate"]
        baseline_rates = [d["mean_rate"] for n, d in strategies.items() if n != "ml_guided"]
        best_baseline = max(baseline_rates) if baseline_rates else 0
        if ml_rate > best_baseline * 1.1:  # >10% better than best baseline
            verdict = "supported"
        elif ml_rate > best_baseline:
            verdict = "trending"
        else:
            verdict = "not_supported"
    else:
        verdict = "insufficient_data"

    return {
        "status": "ok" if len(strategies) >= 2 else "insufficient_data",
        "strategies": strategy_summary,
        "simulation_mode": sim,
        "verdict": verdict,
    }


# ── H10 — LLM Generation Effectiveness ─────────────────────────────

@app.get("/api/hypothesis/llm-effectiveness")
def hypothesis_llm_effectiveness(
    simulation_mode: Optional[str] = None,
    automl_tool: Optional[str] = None,
):
    """H10: Do LLM-generated tests find additional vulnerabilities beyond the registry?

    Compares detection rates between LLM-generated (test_strategy='llm_generated')
    and registry-generated (test_strategy='generated') tests using Fisher's exact
    test, odds ratio, and per-iteration Mann-Whitney U.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    sim = simulation_mode or "deterministic"
    # H10 compares LLM vs registry tests — LLM tests only exist in Phase 3.
    # Load Phase 3 data only so registry counts aren't inflated by Phases 1 & 2.
    all_df = _load_aggregated_history(simulation_mode=sim, automl_tool=automl_tool, phase="llm")
    if all_df is None or all_df.empty:
        return {"status": "insufficient_data", "message": "No experiment data available."}

    all_df = all_df.copy()
    all_df["vulnerability_found"] = pd.to_numeric(
        all_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    if "test_strategy" not in all_df.columns:
        return {"status": "insufficient_data", "message": "No test_strategy column in history data."}

    llm_df = all_df[all_df["test_strategy"] == "llm_generated"]
    reg_df = all_df[all_df["test_strategy"] == "generated"]

    if len(llm_df) < 10 or len(reg_df) < 10:
        return {
            "status": "insufficient_data",
            "message": f"Need ≥10 tests per strategy. LLM: {len(llm_df)}, Registry: {len(reg_df)}.",
            "llm_count": len(llm_df),
            "registry_count": len(reg_df),
        }

    llm_vulns = int(llm_df["vulnerability_found"].sum())
    llm_total = len(llm_df)
    reg_vulns = int(reg_df["vulnerability_found"].sum())
    reg_total = len(reg_df)

    llm_rate = llm_vulns / llm_total
    reg_rate = reg_vulns / reg_total

    # ─── Fisher's exact test (2×2 contingency table) ───
    #                  vuln_found  vuln_not_found
    # llm_generated      a             b
    # generated          c             d
    a, b = llm_vulns, llm_total - llm_vulns
    c, d = reg_vulns, reg_total - reg_vulns
    contingency = [[a, b], [c, d]]

    fisher_p = None
    odds_ratio = None
    try:
        odds_ratio_val, fisher_p_val = scipy_stats.fisher_exact(contingency)
        fisher_p = float(fisher_p_val)
        odds_ratio = float(odds_ratio_val)
    except Exception as e:
        logging.warning(f"[Hypothesis] Fisher's exact test failed for H10: {e}")

    # ─── 95% CI for odds ratio (Woolf logit method) ───
    odds_ratio_ci = None
    if odds_ratio is not None and all(x > 0 for x in [a, b, c, d]):
        try:
            log_or = np.log(odds_ratio)
            se_log_or = np.sqrt(1/a + 1/b + 1/c + 1/d)
            ci_low = np.exp(log_or - 1.96 * se_log_or)
            ci_high = np.exp(log_or + 1.96 * se_log_or)
            odds_ratio_ci = [_safe_float(ci_low, 4), _safe_float(ci_high, 4)]
        except Exception:
            pass

    # ─── Per-iteration Mann-Whitney U (if both strategies exist per iteration) ───
    mann_whitney_result = None
    iter_col = None
    for col in ("simulation_iteration", "experiment_id"):
        if col in all_df.columns:
            iter_col = col
            break

    if iter_col:
        llm_per_iter = (
            llm_df.groupby(iter_col)["vulnerability_found"]
            .mean().dropna().values
        )
        reg_per_iter = (
            reg_df.groupby(iter_col)["vulnerability_found"]
            .mean().dropna().values
        )
        if len(llm_per_iter) >= 3 and len(reg_per_iter) >= 3:
            try:
                u_stat, mw_p = scipy_stats.mannwhitneyu(
                    llm_per_iter, reg_per_iter, alternative="two-sided"
                )
                n1, n2 = len(llm_per_iter), len(reg_per_iter)
                rank_biserial = 1 - (2 * u_stat) / (n1 * n2) if (n1 * n2) > 0 else 0
                mann_whitney_result = {
                    "u_statistic": _safe_float(u_stat, 4),
                    "p_value": _safe_float(mw_p, 6),
                    "significant": bool(mw_p < 0.05),
                    "rank_biserial_r": _safe_float(rank_biserial, 4),
                    "n_llm_iterations": int(n1),
                    "n_registry_iterations": int(n2),
                }
            except Exception as e:
                logging.debug(f"[Hypothesis] Mann-Whitney U failed for H10: {e}")

    # ─── Unique vulnerability types ───
    # Use test_id (specific attack scenario) as primary uniqueness key.
    # All LLM test_ids are prefixed "llm_" so they will never collide with
    # registry test_ids — llm_exclusive correctly captures genuinely novel
    # attack scenarios introduced by the LLM (e.g. llm_ftp_bounce_attack).
    llm_vuln_rows = llm_df[llm_df["vulnerability_found"] == 1]
    reg_vuln_rows = reg_df[reg_df["vulnerability_found"] == 1]

    unique_llm_ids = set(llm_vuln_rows["test_id"].unique()) if "test_id" in all_df.columns else set()
    unique_reg_ids = set(reg_vuln_rows["test_id"].unique()) if "test_id" in all_df.columns else set()
    llm_exclusive = unique_llm_ids - unique_reg_ids

    # Also compute category-level overlap using test_type for richer context.
    unique_llm_types = set(llm_vuln_rows["test_type"].unique()) if "test_type" in all_df.columns else set()
    unique_reg_types = set(reg_vuln_rows["test_type"].unique()) if "test_type" in all_df.columns else set()
    llm_exclusive_types = unique_llm_types - unique_reg_types

    # ─── Verdict ───
    # H10: "LLM tests find *additional* vulnerabilities beyond the static registry."
    # A lower overall detection rate does NOT refute H10 — LLM tests probe novel
    # scenarios where vulnerabilities are rarer.  The key signal is whether LLM
    # discovers attack vectors not present in the registry at all.
    has_exclusive = len(llm_exclusive) > 0 and llm_vulns > 0
    if fisher_p is not None and fisher_p < 0.05 and llm_rate > reg_rate:
        verdict = "supported"
    elif has_exclusive:
        # LLM found vulnerabilities via test scenarios absent from the registry.
        verdict = "supported"
    elif llm_rate > reg_rate:
        verdict = "trending"
    else:
        verdict = "not_supported"

    return {
        "status": "ok",
        "llm": {
            "n_tests": llm_total,
            "n_vulns": llm_vulns,
            "detection_rate": _safe_float(llm_rate, 4),
            "unique_vuln_types": len(unique_llm_types),
            "unique_test_scenarios": len(unique_llm_ids),
        },
        "registry": {
            "n_tests": reg_total,
            "n_vulns": reg_vulns,
            "detection_rate": _safe_float(reg_rate, 4),
            "unique_vuln_types": len(unique_reg_types),
            "unique_test_scenarios": len(unique_reg_ids),
        },
        "fisher_exact": {
            "odds_ratio": _safe_float(odds_ratio, 4),
            "odds_ratio_ci_95": odds_ratio_ci,
            "p_value": _safe_float(fisher_p, 6),
            # Directional flag: significant only when LLM rate > registry rate.
            "significant": bool(fisher_p < 0.05 and llm_rate > reg_rate) if fisher_p is not None else None,
            "contingency_table": contingency,
        },
        "mann_whitney": mann_whitney_result,
        "llm_exclusive_vulns": len(llm_exclusive),
        "llm_exclusive_types": len(llm_exclusive_types),
        "rate_difference": _safe_float(llm_rate - reg_rate, 4),
        "simulation_mode": sim,
        "verdict": verdict,
    }


# ── H11 — Cross-Protocol Generalization ────────────────────────────

@app.get("/api/hypothesis/generalization")
def hypothesis_generalization(
    automl_tool: Optional[str] = None,
    simulation_mode: Optional[str] = None,
    phase: Optional[str] = None,
):
    """H11: Does the model generalize to unseen protocols?

    Leave-one-protocol-out (LOPO) evaluation: train on all protocols
    except one, predict on the held-out protocol. Tests OOD generalization.
    """
    from utils.lopo_eval import run_all_lopo, lopo_summary
    from generator.retrain import aggregate_history

    sim = simulation_mode or "deterministic"
    aml = automl_tool or "h2o"

    # Aggregate history for the specified mode and optional phase
    agg_path = aggregate_history(EXPERIMENTS_PATH, simulation_mode=sim,
                                 automl_tool=aml if phase else None,
                                 phase_tag=phase)
    if not agg_path:
        return {
            "status": "insufficient_data",
            "message": "No experiment data available for LOPO evaluation.",
            "protocols": [],
            "summary": None,
            "verdict": "insufficient_data",
        }

    # Run LOPO for all protocols
    results = run_all_lopo(agg_path, automl_tool=aml, max_runtime_secs=120)
    summary = lopo_summary(results)

    # Clean results for API response (remove detailed error messages)
    protocol_results = []
    for r in results:
        protocol_results.append({
            "protocol": r.get("held_out"),
            "auc_roc": r.get("auc_roc"),
            "brier_score": r.get("brier_score"),
            "ece": r.get("ece"),
            "n_train": r.get("n_train"),
            "n_test": r.get("n_test"),
            "status": r.get("status"),
        })

    return {
        "status": "ok" if summary.get("n_evaluated", 0) > 0 else "insufficient_data",
        "protocols": protocol_results,
        "summary": summary,
        "automl_tool": aml,
        "simulation_mode": sim,
        "verdict": summary.get("verdict", "insufficient_data"),
    }


# ── Dynamic Features Comparison (Phase 5/6) ────────────────────────

@app.get("/api/hypothesis/dynamic-features-comparison")
def hypothesis_dynamic_features_comparison(
    simulation_mode: Optional[str] = None,
    automl_tool: Optional[str] = "h2o",
):
    """2×2 factorial comparison: Static vs Dynamic features × No-LLM vs LLM.

    Phases:
      - framework (Phase 1): static features, no LLM
      - llm       (Phase 3): static features, with LLM
      - phase5    (Phase 5): dynamic rolling features, no LLM
      - phase6    (Phase 6): dynamic rolling features, with LLM

    Returns per-phase detection rate, learning curve, and factorial interaction term.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    sim = simulation_mode or "deterministic"
    aml = automl_tool or "h2o"

    phase_labels = ["framework", "llm", "phase5", "phase6"]
    phase_data = {}
    for ph in phase_labels:
        df = _load_aggregated_history(simulation_mode=sim, automl_tool=aml, phase=ph)
        phase_data[ph] = df

    def _phase_stats(df):
        if df is None or df.empty:
            return {"mean_detection": None, "n_tests": 0, "n_vulns": 0, "curve": []}
        df = df.copy()
        df["vulnerability_found"] = pd.to_numeric(
            df["vulnerability_found"], errors="coerce"
        ).fillna(0).astype(int)
        n_tests = len(df)
        n_vulns = int(df["vulnerability_found"].sum())
        mean_det = float(df["vulnerability_found"].mean())

        curve = []
        if "simulation_iteration" in df.columns:
            per_iter = (
                df.groupby("simulation_iteration")["vulnerability_found"]
                .agg(total="count", vulns="sum")
                .reset_index()
                .sort_values("simulation_iteration")
            )
            curve = [
                {
                    "iteration": int(r["simulation_iteration"]),
                    "detection_rate": float(r["vulns"] / r["total"]) if r["total"] > 0 else 0.0,
                }
                for _, r in per_iter.iterrows()
            ]
        return {"mean_detection": round(mean_det, 4), "n_tests": n_tests,
                "n_vulns": n_vulns, "curve": curve}

    phases_out = {ph: _phase_stats(phase_data[ph]) for ph in phase_labels}

    # 2×2 factorial table
    p1 = phases_out["framework"]["mean_detection"]
    p3 = phases_out["llm"]["mean_detection"]
    p5 = phases_out["phase5"]["mean_detection"]
    p6 = phases_out["phase6"]["mean_detection"]

    dynamic_main = (
        round(((p5 or 0) + (p6 or 0)) / 2 - ((p1 or 0) + (p3 or 0)) / 2, 4)
        if p5 is not None and p6 is not None else None
    )
    llm_main = (
        round(((p3 or 0) + (p6 or 0)) / 2 - ((p1 or 0) + (p5 or 0)) / 2, 4)
        if p3 is not None and p6 is not None and p5 is not None else None
    )
    interaction = (
        round(((p6 or 0) - (p5 or 0)) - ((p3 or 0) - (p1 or 0)), 4)
        if all(v is not None for v in [p1, p3, p5, p6]) else None
    )

    # Statistical tests (Mann-Whitney U) — only when both phases have data
    def _mw_test(df_a, df_b):
        if df_a is None or df_b is None or df_a.empty or df_b.empty:
            return None
        a = pd.to_numeric(df_a["vulnerability_found"], errors="coerce").dropna()
        b = pd.to_numeric(df_b["vulnerability_found"], errors="coerce").dropna()
        if len(a) < 5 or len(b) < 5:
            return None
        try:
            stat, p = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
            return {"statistic": round(float(stat), 2), "p_value": round(float(p), 6)}
        except Exception:
            return None

    stat_tests = {
        "p1_vs_p5": _mw_test(phase_data["framework"], phase_data["phase5"]),
        "p3_vs_p6": _mw_test(phase_data["llm"], phase_data["phase6"]),
    }

    # Verdict
    p5_has_data = phase_data["phase5"] is not None and not phase_data["phase5"].empty
    p6_has_data = phase_data["phase6"] is not None and not phase_data["phase6"].empty
    if not p5_has_data:
        verdict = "insufficient_data"
    elif dynamic_main is not None and dynamic_main > 0.02:
        verdict = "dynamic_improves"
    else:
        verdict = "no_improvement"

    return {
        "phases": phases_out,
        "factorial_table": {
            "static_no_llm": p1,
            "static_llm": p3,
            "dynamic_no_llm": p5,
            "dynamic_llm": p6,
            "dynamic_main_effect": dynamic_main,
            "llm_main_effect": llm_main,
            "interaction": interaction,
        },
        "statistical_tests": stat_tests,
        "simulation_mode": sim,
        "automl_tool": aml,
        "verdict": verdict,
    }


# ── Ablation Analysis ──────────────────────────────────────────────

@app.get("/api/hypothesis/ablation")
def hypothesis_ablation(simulation_mode: Optional[str] = None):
    """Ablation analysis: marginal contribution of each system component.

    Uses existing experiment variants to compute an ablation table:
    - No prioritisation (baseline=no_ml): run ALL tests, detection ceiling
    - Random selection (baseline=random): random subset, chance baseline
    - CVSS heuristic (baseline=cvss_priority): non-ML intelligent baseline
    - Round-robin (baseline=round_robin): coverage-based baseline
    - ML-guided (ml_guided, no LLM): ML scoring only
    - ML+LLM (ml_guided + llm_generated tests): full system

    Reports per-condition detection rate, efficiency, and marginal lift.
    """
    import numpy as np

    sim = simulation_mode or "deterministic"
    all_df = _load_aggregated_history(simulation_mode=sim)
    if all_df is None or all_df.empty:
        return {"status": "insufficient_data", "message": "No experiment data available."}

    all_df = all_df.copy()
    all_df["vulnerability_found"] = pd.to_numeric(
        all_df["vulnerability_found"], errors="coerce"
    ).fillna(0).astype(int)

    if "baseline_strategy" not in all_df.columns:
        all_df["baseline_strategy"] = "ml_guided"
    else:
        all_df["baseline_strategy"] = all_df["baseline_strategy"].fillna("ml_guided")

    # For fair comparison, restrict ml_guided rows to h2o only.
    # h2o is the only framework that also ran Phase 2 baselines, so without
    # this filter ml_guided accumulates 5 frameworks × 100 iters = 500 dirs
    # while each baseline condition only has h2o's 100 dirs (140 rows each).
    if "automl_tool" in all_df.columns:
        _ml_mask = all_df["baseline_strategy"] == "ml_guided"
        _non_h2o = all_df["automl_tool"] != "h2o"
        all_df = all_df[~(_ml_mask & _non_h2o)]

    # Determine if LLM tests exist
    has_llm = (
        "test_strategy" in all_df.columns
        and (all_df["test_strategy"] == "llm_generated").any()
    )

    # Define ablation conditions in order of complexity
    conditions = []

    # 1. Random baseline
    random_df = all_df[all_df["baseline_strategy"] == "random"]
    if not random_df.empty:
        conditions.append(("Random Selection", "random", random_df))

    # 2. Round-robin
    rr_df = all_df[all_df["baseline_strategy"] == "round_robin"]
    if not rr_df.empty:
        conditions.append(("Round-Robin", "round_robin", rr_df))

    # 3. CVSS priority
    cvss_df = all_df[all_df["baseline_strategy"] == "cvss_priority"]
    if not cvss_df.empty:
        conditions.append(("CVSS Priority", "cvss_priority", cvss_df))

    # 4. ML-guided (no LLM)
    # Use Phase 1 ("framework") h2o-only rows so the iteration pool matches
    # the baseline conditions (100 iters each, no LLM tests).  Including
    # Phase 3 rows would double-count iteration numbers 1-100 and inflate
    # per-iteration averages.
    _ml_base = all_df[all_df["baseline_strategy"] == "ml_guided"]
    if "automl_tool" in _ml_base.columns:
        _ml_base = _ml_base[_ml_base["automl_tool"] == "h2o"]
    if "phase" in _ml_base.columns:
        ml_no_llm = _ml_base[_ml_base["phase"] == "framework"]
    else:
        ml_no_llm = _ml_base[_ml_base["test_strategy"] != "llm_generated"] if "test_strategy" in _ml_base.columns else _ml_base
    if not ml_no_llm.empty:
        conditions.append(("ML-Guided", "ml_guided", ml_no_llm))

    # 5. ML+LLM (full system) — Phase 3 only, where LLM tests actually ran
    if has_llm:
        if "phase" in _ml_base.columns:
            ml_with_llm = _ml_base[_ml_base["phase"] == "llm"]
        else:
            ml_with_llm = _ml_base
        if not ml_with_llm.empty and (all_df["test_strategy"] == "llm_generated").any():
            conditions.append(("ML + LLM", "ml_llm", ml_with_llm))

    # 6. No-ML (all tests)
    noml_df = all_df[all_df["baseline_strategy"] == "no_ml"]
    if not noml_df.empty:
        conditions.append(("No Prioritisation (All Tests)", "no_ml", noml_df))

    # 7. ML-Dynamic (Phase 5, H2O) — added when Phase 5 data exists
    _p5 = _load_aggregated_history(simulation_mode=sim, automl_tool="h2o", phase="phase5")
    if _p5 is not None and not _p5.empty:
        conditions.append(("ML-Dynamic (Phase 5)", "phase5", _p5))

    # 8. ML-Dynamic + LLM (Phase 6, H2O) — added when Phase 6 data exists
    _p6 = _load_aggregated_history(simulation_mode=sim, automl_tool="h2o", phase="phase6")
    if _p6 is not None and not _p6.empty:
        conditions.append(("ML-Dynamic + LLM (Phase 6)", "phase6", _p6))

    if len(conditions) < 2:
        return {
            "status": "insufficient_data",
            "message": f"Need ≥2 ablation conditions. Found: {[c[0] for c in conditions]}. "
                       f"Baseline experiments may not have run yet.",
        }

    # Compute metrics per condition.
    # Prefer exp_dir_name as the grouper: it's unique per experiment run and
    # correctly handles cases where the same simulation_iteration numbers appear
    # across multiple experiment runs (e.g. if Phase 3 ran twice due to a
    # DuckDB not being cleared between full re-runs).
    iter_col = None
    for col in ("exp_dir_name", "simulation_iteration", "experiment_id"):
        if col in all_df.columns:
            iter_col = col
            break

    ablation_table = []
    for label, key, cond_df in conditions:
        n_tests = len(cond_df)
        n_vulns = int(cond_df["vulnerability_found"].sum())
        det_rate = n_vulns / n_tests if n_tests > 0 else 0

        # Per-iteration stats for variance
        if iter_col and iter_col in cond_df.columns:
            per_iter = (
                cond_df.groupby(iter_col)["vulnerability_found"]
                .agg(total="count", vulns="sum")
                .reset_index()
            )
            iter_rates = (per_iter["vulns"] / per_iter["total"]).fillna(0)
            std_rate = float(np.std(iter_rates))
            n_iterations = len(per_iter)
        else:
            std_rate = 0
            n_iterations = 1

        # Unique vulnerability types — count across all data (not per-iteration);
        # all conditions now come from a single phase so iteration counts are
        # comparable and this is a fair cross-condition measure.
        unique_vulns = 0
        for id_col in ("test_id", "test_type"):
            if id_col in cond_df.columns:
                unique_vulns = int(cond_df[cond_df["vulnerability_found"] == 1][id_col].nunique())
                break

        # Normalise to per-iteration averages so conditions from different
        # phases (with different iteration counts) are directly comparable.
        n_tests_per_iter = n_tests / n_iterations if n_iterations > 0 else n_tests
        n_vulns_per_iter = n_vulns / n_iterations if n_iterations > 0 else n_vulns

        ablation_table.append({
            "condition": label,
            "key": key,
            "n_tests": round(n_tests_per_iter),
            "n_vulns": round(n_vulns_per_iter),
            "detection_rate": _safe_float(det_rate, 4),
            "std_rate": _safe_float(std_rate, 4),
            "n_iterations": n_iterations,
            "unique_vuln_types": unique_vulns,
            "efficiency": _safe_float(n_vulns / n_tests, 4) if n_tests > 0 else 0,
        })

    # Compute marginal efficiency lift (each condition vs previous, detection rate)
    for i in range(1, len(ablation_table)):
        prev_rate = ablation_table[i - 1]["detection_rate"]
        curr_rate = ablation_table[i]["detection_rate"]
        if prev_rate > 0:
            lift_pct = ((curr_rate - prev_rate) / prev_rate) * 100
        else:
            lift_pct = 100 if curr_rate > 0 else 0
        ablation_table[i]["marginal_lift_pct"] = _safe_float(lift_pct, 1)
        ablation_table[i]["marginal_lift_vs"] = ablation_table[i - 1]["condition"]
    if ablation_table:
        ablation_table[0]["marginal_lift_pct"] = 0
        ablation_table[0]["marginal_lift_vs"] = "(baseline)"

    # Compute coverage lift: sequential (vs previous) and absolute (vs first condition / random)
    baseline_types = ablation_table[0]["unique_vuln_types"] if ablation_table else 0
    for i, row in enumerate(ablation_table):
        # Sequential coverage lift vs previous condition
        if i == 0:
            row["coverage_lift_pct"] = 0
            row["coverage_lift_vs"] = "(baseline)"
        else:
            prev_types = ablation_table[i - 1]["unique_vuln_types"]
            curr_types = row["unique_vuln_types"]
            if prev_types > 0:
                row["coverage_lift_pct"] = _safe_float(((curr_types - prev_types) / prev_types) * 100, 1)
            else:
                row["coverage_lift_pct"] = 100.0 if curr_types > 0 else 0.0
            row["coverage_lift_vs"] = ablation_table[i - 1]["condition"]
        # Absolute coverage lift vs random baseline (first condition)
        if baseline_types > 0:
            row["coverage_lift_vs_baseline_pct"] = _safe_float(
                ((row["unique_vuln_types"] - baseline_types) / baseline_types) * 100, 1
            )
        else:
            row["coverage_lift_vs_baseline_pct"] = 0.0

    return {
        "status": "ok",
        "conditions": ablation_table,
        "simulation_mode": sim,
        "n_conditions": len(ablation_table),
    }


# ── Hypothesis Synthesis Summary ────────────────────────────────────

_synthesis_cache = _TTLCache(default_ttl=120)


@app.get("/api/hypothesis/synthesis")
def hypothesis_synthesis(simulation_mode: Optional[str] = None, automl_tool: Optional[str] = None):
    """Aggregate all hypothesis verdicts into a single summary table.

    Calls each hypothesis endpoint and collects their verdict + key metric,
    producing a synthesis suitable for a thesis results table.
    """
    sim = simulation_mode or "deterministic"
    aml = automl_tool or "h2o"

    cache_key = f"synth_{sim}_{aml}"
    cached = _synthesis_cache.get(cache_key)
    if cached is not None:
        return cached

    hypotheses = []

    # H1 — Detection Rate Stability
    try:
        h1 = hypothesis_statistical_tests(simulation_mode=sim, automl_tool=aml)
        hypotheses.append({
            "id": "H1",
            "name": "Detection Rate Stability",
            "description": "ML-guided detection rate improves or remains stable across iterations",
            "verdict": h1.get("verdict", "insufficient_data"),
            "key_metric": f"ρ={_safe_num(h1.get('spearman_rho', '--')):.3f}" if h1.get("spearman_rho") is not None else None,
            "p_value": h1.get("spearman_p"),
            "effect_size": h1.get("cohens_d"),
            "effect_interpretation": h1.get("cohens_d_interpretation"),
            "n": h1.get("n_iterations"),
            "test_used": "Spearman ρ + Mann-Whitney U + Cohen's d",
        })
    except Exception as e:
        hypotheses.append({"id": "H1", "name": "Detection Rate Stability", "verdict": "error", "error": str(e)})

    # H2 — Recommendation Effectiveness
    try:
        h2 = hypothesis_recommendation_effectiveness(simulation_mode=sim, automl_tool=aml)
        hypotheses.append({
            "id": "H2",
            "name": "Recommendation Effectiveness",
            "description": "ML-recommended tests have higher detection rates than non-recommended",
            "verdict": h2.get("verdict", "insufficient_data"),
            "key_metric": f"lift={_safe_num(h2.get('summary', {}).get('detection_rate_lift', '--')):.1f}×" if h2.get("summary", {}).get("detection_rate_lift") is not None else None,
            "p_value": None,
            "effect_size": h2.get("summary", {}).get("detection_rate_lift"),
            "effect_interpretation": "lift ratio (recommended/non-recommended)",
            "n": h2.get("summary", {}).get("total_scored_iterations"),
            "test_used": "Detection rate lift comparison",
        })
    except Exception as e:
        hypotheses.append({"id": "H2", "name": "Recommendation Effectiveness", "verdict": "error", "error": str(e)})

    # H3 — Protocol Convergence
    try:
        h3 = hypothesis_protocol_convergence(simulation_mode=sim, automl_tool=aml)
        h3_stats = h3.get("stats") or {}
        hypotheses.append({
            "id": "H3",
            "name": "Protocol Convergence",
            "description": "Detection rates across protocols converge over iterations",
            "verdict": h3.get("verdict", "insufficient_data"),
            "key_metric": f"var_reduction={_safe_num(h3_stats.get('variance_reduction_pct', '--')):.1f}%" if h3_stats.get("variance_reduction_pct") is not None else None,
            "p_value": h3_stats.get("variance_p"),
            "effect_size": h3_stats.get("variance_reduction_pct"),
            "effect_interpretation": "variance reduction (early→late)",
            "n": h3_stats.get("n_converging", 0) + h3_stats.get("n_stable", 0) + h3_stats.get("n_diverging", 0),
            "test_used": "Mann-Whitney U on cross-protocol variance",
        })
    except Exception as e:
        hypotheses.append({"id": "H3", "name": "Protocol Convergence", "verdict": "error", "error": str(e)})

    # H4 — Risk Score Calibration
    try:
        h4 = hypothesis_risk_calibration(simulation_mode=sim, automl_tool=aml)
        hypotheses.append({
            "id": "H4",
            "name": "Risk Score Calibration",
            "description": "Predicted risk scores are well-calibrated against actual outcomes",
            "verdict": h4.get("verdict", "insufficient_data"),
            "key_metric": f"Brier={_safe_num(h4.get('brier_score', '--')):.4f}" if h4.get("brier_score") is not None else None,
            "p_value": None,
            "effect_size": h4.get("brier_score"),
            "effect_interpretation": "Brier score (lower = better calibrated)",
            "n": h4.get("total_predictions"),
            "test_used": "Brier score + calibration curve",
        })
    except Exception as e:
        hypotheses.append({"id": "H4", "name": "Risk Score Calibration", "verdict": "error", "error": str(e)})

    # H5 — Execution Efficiency
    try:
        h5 = hypothesis_execution_efficiency(simulation_mode=sim, automl_tool=aml)
        stats5 = h5.get("stats")
        hypotheses.append({
            "id": "H5",
            "name": "Execution Efficiency",
            "description": "ML-selected test subsets achieve comparable coverage with fewer tests",
            "verdict": h5.get("verdict", "insufficient_data"),
            "key_metric": f"ratio={_safe_num(h5.get('summary', {}).get('avg_efficiency_ratio', '--')):.2f}×" if h5.get("summary", {}).get("avg_efficiency_ratio") is not None else None,
            "p_value": stats5.get("wilcoxon_p") if stats5 else None,
            "effect_size": stats5.get("rank_biserial_r") if stats5 else None,
            "effect_interpretation": stats5.get("rank_biserial_interpretation") if stats5 else None,
            "n": stats5.get("n_iterations") if stats5 else h5.get("summary", {}).get("total_executions"),
            "test_used": "Wilcoxon signed-rank + rank-biserial r",
        })
    except Exception as e:
        hypotheses.append({"id": "H5", "name": "Execution Efficiency", "verdict": "error", "error": str(e)})

    # H6 — Discovery Coverage
    try:
        h6 = hypothesis_discovery_coverage(automl_tool=aml)
        hypotheses.append({
            "id": "H6",
            "name": "Discovery Coverage",
            "description": "Dynamic simulation modes expose more unique vulnerability patterns",
            "verdict": h6.get("verdict", "insufficient_data"),
            "key_metric": f"H={_safe_num(h6.get('kruskal_wallis_h', '--')):.2f}" if h6.get("kruskal_wallis_h") is not None else None,
            "p_value": h6.get("kruskal_wallis_p"),
            "effect_size": None,
            "effect_interpretation": None,
            "n": sum(h6.get("modes", {}).get(m, {}).get("total_iterations", 0) for m in h6.get("modes", {})),
            "test_used": "Kruskal-Wallis + pairwise Mann-Whitney U",
        })
    except Exception as e:
        hypotheses.append({"id": "H6", "name": "Discovery Coverage", "verdict": "error", "error": str(e)})

    # H7 — Cross-Framework Comparison (only if multiple frameworks)
    try:
        h7 = hypothesis_cross_framework(simulation_mode=sim)
        if h7.get("status") == "ok":
            kw = h7.get("kruskal_wallis")
            hypotheses.append({
                "id": "H7",
                "name": "Cross-Framework Comparison",
                "description": "Different AutoML frameworks produce significantly different detection outcomes",
                "verdict": h7.get("verdict", "insufficient_data"),
                "key_metric": f"H={_safe_num(kw.get('h_statistic', '--')):.2f}" if kw and kw.get("h_statistic") is not None else None,
                "p_value": kw.get("p_value") if kw else None,
                "effect_size": None,
                "effect_interpretation": None,
                "n": h7.get("n_frameworks"),
                "test_used": "Kruskal-Wallis + pairwise Mann-Whitney U (Bonferroni)",
            })
    except Exception as e:
        hypotheses.append({"id": "H7", "name": "Cross-Framework Comparison", "verdict": "error", "error": str(e)})

    # H8 — Temporal Predictive Validity
    try:
        h8 = hypothesis_temporal_validation(simulation_mode=sim, automl_tool=aml)
        if h8.get("status") != "no_temporal_data":
            s8 = h8.get("summary") or {}
            hypotheses.append({
                "id": "H8",
                "name": "Temporal Predictive Validity",
                "description": "The model genuinely predicts unseen iterations (held-out AUC)",
                "verdict": h8.get("verdict", "insufficient_data"),
                "key_metric": f"AUC={s8.get('mean_auc', '--'):.3f}" if s8.get("mean_auc") is not None else None,
                "p_value": s8.get("auc_trend", {}).get("p_value") if s8.get("auc_trend") else None,
                "effect_size": s8.get("mean_auc"),
                "effect_interpretation": "held-out AUC-ROC",
                "n": s8.get("n_evaluations"),
                "test_used": "Temporal expanding-window validation",
            })
    except Exception as e:
        hypotheses.append({"id": "H8", "name": "Temporal Predictive Validity", "verdict": "error", "error": str(e)})

    # H9 — ML Value Over Baselines
    try:
        h9 = hypothesis_baseline_comparison(simulation_mode=sim)
        if h9.get("status") == "ok":
            ml_strat = h9.get("strategies", {}).get("ml_guided", {})
            hypotheses.append({
                "id": "H9",
                "name": "ML Value Over Baselines",
                "description": "ML-guided testing beats non-ML baseline strategies",
                "verdict": h9.get("verdict", "insufficient_data"),
                "key_metric": f"ML rate={ml_strat.get('mean_rate', '--'):.3f}" if ml_strat.get("mean_rate") is not None else None,
                "p_value": None,
                "effect_size": ml_strat.get("mean_rate"),
                "effect_interpretation": "ML detection rate",
                "n": ml_strat.get("n_iterations"),
                "test_used": "Mann-Whitney U (ML vs each baseline)",
            })
    except Exception as e:
        hypotheses.append({"id": "H9", "name": "ML Value Over Baselines", "verdict": "error", "error": str(e)})

    # H10 — LLM Generation Effectiveness (uses dedicated endpoint with Fisher's exact)
    try:
        h10 = hypothesis_llm_effectiveness(simulation_mode=sim, automl_tool=aml)
        if h10.get("status") == "ok":
            llm_data = h10.get("llm", {})
            reg_data = h10.get("registry", {})
            fisher = h10.get("fisher_exact", {})
            hypotheses.append({
                "id": "H10",
                "name": "LLM Generation Effectiveness",
                "description": "LLM-generated tests find additional vulnerabilities beyond the static registry",
                "verdict": h10.get("verdict", "insufficient_data"),
                "key_metric": f"LLM={llm_data.get('detection_rate', '--'):.3f} vs Reg={reg_data.get('detection_rate', '--'):.3f}" if llm_data.get("detection_rate") is not None else None,
                "p_value": fisher.get("p_value"),
                "effect_size": fisher.get("odds_ratio"),
                "effect_interpretation": "odds ratio (LLM vs registry)",
                "n": llm_data.get("n_tests"),
                "test_used": "Fisher's exact test + odds ratio",
            })
    except Exception as e:
        hypotheses.append({"id": "H10", "name": "LLM Generation Effectiveness", "verdict": "error", "error": str(e)})

    # H11 — Cross-Protocol Generalization
    try:
        h11 = hypothesis_generalization(automl_tool=aml, simulation_mode=sim)
        if h11.get("status") == "ok":
            s11 = h11.get("summary") or {}
            hypotheses.append({
                "id": "H11",
                "name": "Cross-Protocol Generalization",
                "description": "The model generalizes to unseen protocols (LOPO evaluation)",
                "verdict": h11.get("verdict", "insufficient_data"),
                "key_metric": f"LOPO AUC={s11.get('mean_auc', '--'):.3f}" if s11.get("mean_auc") is not None else None,
                "p_value": None,
                "effect_size": s11.get("mean_auc"),
                "effect_interpretation": "mean held-out AUC across protocols",
                "n": s11.get("n_evaluated"),
                "test_used": "Leave-one-protocol-out (LOPO)",
            })
    except Exception as e:
        hypotheses.append({"id": "H11", "name": "Cross-Protocol Generalization", "verdict": "error", "error": str(e)})

    # ─── Aggregate summary ───
    total = len(hypotheses)
    supported = sum(1 for h in hypotheses if h.get("verdict") in (
        "supported", "efficient", "significant_differences", "well_calibrated", "generalizes",
    ))
    trending = sum(1 for h in hypotheses if h.get("verdict") in (
        "trending", "trending_differences", "comparable", "moderately_calibrated", "partial_generalization",
    ))
    not_supported = sum(1 for h in hypotheses if h.get("verdict") in (
        "not_supported", "not_efficient", "no_significant_differences", "poorly_calibrated", "does_not_generalize",
    ))
    errors = sum(1 for h in hypotheses if h.get("verdict") in ("error", "insufficient_data"))

    overall_strength = (
        "strong" if supported >= total * 0.7
        else "moderate" if (supported + trending) >= total * 0.5
        else "weak" if supported > 0
        else "insufficient"
    )

    # ─── Holm-Bonferroni multiple comparison correction ───
    # Collect all hypotheses with p-values for correction
    hyp_with_p = [(i, h) for i, h in enumerate(hypotheses) if h.get("p_value") is not None]
    n_tests_corrected = len(hyp_with_p)

    if n_tests_corrected >= 2:
        # Sort by p-value ascending
        hyp_with_p.sort(key=lambda x: x[1]["p_value"])
        alpha = 0.05
        for rank, (idx, h) in enumerate(hyp_with_p):
            # Holm threshold: α / (m + 1 - rank)  where rank is 1-indexed
            holm_threshold = alpha / (n_tests_corrected + 1 - (rank + 1))
            corrected_p = min(h["p_value"] * (n_tests_corrected - rank), 1.0)
            hypotheses[idx]["corrected_p_value"] = _safe_float(corrected_p, 6)
            hypotheses[idx]["significant_after_correction"] = bool(h["p_value"] <= holm_threshold)
            hypotheses[idx]["holm_threshold"] = _safe_float(holm_threshold, 6)
    elif n_tests_corrected == 1:
        idx, h = hyp_with_p[0]
        hypotheses[idx]["corrected_p_value"] = h["p_value"]
        hypotheses[idx]["significant_after_correction"] = bool(h["p_value"] < 0.05)

    # Count corrected verdicts
    corrected_supported = sum(
        1 for h in hypotheses
        if h.get("significant_after_correction") is True
    )
    corrected_not_significant = sum(
        1 for h in hypotheses
        if h.get("significant_after_correction") is False
    )

    result = {
        "hypotheses": hypotheses,
        "summary": {
            "total_hypotheses": total,
            "supported": supported,
            "trending": trending,
            "not_supported": not_supported,
            "errors_or_insufficient": errors,
            "overall_strength": overall_strength,
            # Multiple comparison correction metadata
            "correction_method": "holm_bonferroni",
            "family_wise_alpha": 0.05,
            "n_tests_corrected": n_tests_corrected,
            "corrected_significant": corrected_supported,
            "corrected_not_significant": corrected_not_significant,
        },
        "simulation_mode": sim,
        "automl_tool": aml,
    }
    _synthesis_cache.set(cache_key, result)
    return result


# Helper for synthesis
def _safe_num(v):
    """Safe numeric conversion for f-string formatting."""
    try:
        n = float(v)
        return n if not (math.isnan(n) or math.isinf(n)) else 0
    except (TypeError, ValueError):
        return 0


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _save_suite(suite: TestSuite):
    fpath = os.path.join(SUITES_PATH, f"suite_{suite.suite_id}.json")
    with open(fpath, "w") as f:
        json.dump(suite.to_dict(), f, indent=2, default=str)


def _load_suite(suite_id: str) -> Optional[dict]:
    fpath = os.path.join(SUITES_PATH, f"suite_{suite_id}.json")
    if os.path.exists(fpath):
        with open(fpath) as f:
            return json.load(f)
    return None


def _compute_suite_fingerprint(devices, protocols, severity_filter, include_uncommon, automl_tool: str = "h2o"):
    """Compute a content-based fingerprint for a suite configuration.

    Includes ``automl_tool`` so that switching frameworks always creates a
    fresh suite instead of returning a cached one scored by a different model.
    """
    canonical_devices = sorted(
        (d["ip"], sorted(int(p) for p in d.get("ports", [])))
        for d in devices
    )
    canonical = json.dumps({
        "devices": canonical_devices,
        "protocols": sorted(protocols) if protocols else "all",
        "severity": sorted(severity_filter) if severity_filter else "all",
        "include_uncommon": include_uncommon,
        "automl_tool": automl_tool,
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _find_matching_suite(fingerprint: str) -> Optional[dict]:
    """Find an existing suite whose fingerprint matches. Returns suite dict or None."""
    if not os.path.exists(SUITES_PATH):
        return None
    for fname in sorted(os.listdir(SUITES_PATH), reverse=True):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(SUITES_PATH, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            if data.get("metadata", {}).get("fingerprint") == fingerprint:
                return data
        except Exception:
            continue
    return None


# Common IoT ports (matches scorer.py and automl/dataset.py)
_COMMON_PORTS = {21, 22, 23, 53, 80, 443, 502, 554, 1883, 5683}


def _heuristic_risk_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute heuristic risk scores from historical vulnerability rates.

    Uses leave-iteration-out cross-validation of empirical base rates so each
    row's predicted score is derived from *other* iterations only, avoiding
    data leakage.  Groups are formed by (protocol, open_port, test_strategy)
    which are the strongest predictors of vulnerability likelihood.

    The resulting ``predicted_risk_score`` column is a float in [0, 1].
    """
    import numpy as np

    df = df.copy()
    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)
    df["open_port"] = pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)

    # Ensure iteration column exists for leave-one-out
    if "simulation_iteration" not in df.columns:
        df["simulation_iteration"] = 0

    group_cols = ["protocol", "open_port", "test_strategy"]
    # Verify columns exist; fall back gracefully
    group_cols = [c for c in group_cols if c in df.columns]
    if not group_cols:
        # Ultimate fallback: global vulnerability rate
        global_rate = df["vulnerability_found"].mean()
        df["predicted_risk_score"] = round(float(global_rate), 4)
        df["_score_method"] = "heuristic_global"
        return df

    # Global prior (Bayesian smoothing to handle small groups)
    global_mean = df["vulnerability_found"].mean()
    smoothing_weight = 10  # pseudo-count for prior

    # For each unique iteration, compute base rates from all OTHER iterations
    iterations = df["simulation_iteration"].unique()

    if len(iterations) <= 1:
        # Only one iteration: use group means with Bayesian smoothing
        grouped = df.groupby(group_cols)["vulnerability_found"]
        group_sum = grouped.transform("sum")
        group_count = grouped.transform("count")
        # Bayesian smoothed estimate: (sum + prior*weight) / (count + weight)
        df["predicted_risk_score"] = np.round(
            (group_sum + global_mean * smoothing_weight) / (group_count + smoothing_weight), 4
        )
    else:
        # Leave-iteration-out: for each row, score = rate in same group
        # across all other iterations.  Vectorised via merge for speed.
        df["grp_key"] = df[group_cols].astype(str).agg("|".join, axis=1)

        # Per-(group, iteration) stats
        grp_iter = (
            df.groupby(["grp_key", "simulation_iteration"])["vulnerability_found"]
            .agg(iter_sum="sum", iter_count="count")
            .reset_index()
        )

        # Total stats per group (across all iterations)
        grp_totals = (
            df.groupby("grp_key")["vulnerability_found"]
            .agg(total_sum="sum", total_count="count")
            .reset_index()
        )

        # Merge totals and per-iteration stats back onto dataframe
        df = df.merge(grp_totals, on="grp_key", how="left")
        df = df.merge(grp_iter, on=["grp_key", "simulation_iteration"], how="left")
        df["iter_sum"] = df["iter_sum"].fillna(0)
        df["iter_count"] = df["iter_count"].fillna(0)

        # Leave-iteration-out: subtract current iteration's contribution
        loo_sum = df["total_sum"] - df["iter_sum"]
        loo_count = df["total_count"] - df["iter_count"]

        # Bayesian smoothed estimate
        df["predicted_risk_score"] = np.round(
            (loo_sum + global_mean * smoothing_weight) / (loo_count + smoothing_weight), 4
        )

        df.drop(columns=["grp_key", "total_sum", "total_count", "iter_sum", "iter_count"], inplace=True)

    df["_score_method"] = "heuristic"
    return df


def _predict_risk_scores_on_history(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Add 'predicted_risk_score' column to history DataFrame.

    Tries the trained ML model first (H2O or framework-specific).  If no model
    is available, falls back to ``_heuristic_risk_scores()`` which computes
    leave-iteration-out empirical base rates.

    Returns the augmented DataFrame, or None only if the data itself is
    insufficient (should not normally happen).
    """
    # ── Attempt 1: trained ML model ──────────────────────────────────
    try:
        from automl.pipeline import get_model
        import h2o

        model = get_model()
        if model is not None:
            scored = df.copy()
            scored["open_port"] = pd.to_numeric(scored["open_port"], errors="coerce").fillna(0).astype(int)
            scored["vulnerability_found"] = pd.to_numeric(scored["vulnerability_found"], errors="coerce").fillna(0).astype(int)

            if "container_id" in scored.columns:
                scored["port_count"] = scored.groupby("container_id")["open_port"].transform("nunique")
                scored["protocol_diversity"] = scored.groupby("container_id")["protocol"].transform("nunique")
            else:
                scored["port_count"] = 1
                scored["protocol_diversity"] = 1
            scored["is_common_port"] = scored["open_port"].isin(_COMMON_PORTS).astype(int)

            feature_cols = [
                "test_strategy", "device_type", "firmware_version",
                "open_port", "protocol", "service", "auth_required",
                "port_count", "protocol_diversity", "is_common_port",
            ]
            missing = [c for c in feature_cols if c not in scored.columns]
            if not missing:
                features_df = scored[feature_cols].copy()
                for col in ["test_strategy", "device_type", "firmware_version", "protocol", "service"]:
                    features_df[col] = features_df[col].astype(str)

                hf = h2o.H2OFrame(features_df)
                preds = model.predict(hf)
                pred_df = preds.as_data_frame()

                if "p1" in pred_df.columns:
                    scores = pred_df["p1"].tolist()
                elif len(pred_df.columns) >= 3:
                    scores = pred_df.iloc[:, 2].tolist()
                else:
                    scores = pred_df.iloc[:, 0].tolist()

                scored["predicted_risk_score"] = [_safe_float(s, 4) or 0.0 for s in scores]
                scored["_score_method"] = "model"
                return scored

    except Exception as e:
        logging.warning(f"[Prediction] ML model scoring failed: {e}")

    # ── Attempt 2: heuristic from historical base rates ──────────────
    try:
        return _heuristic_risk_scores(df)
    except Exception as e:
        logging.warning(f"[Prediction] Heuristic scoring failed: {e}")
        return None


def _load_aggregated_history(simulation_mode: str = None, automl_tool: str = None, phase: str = None) -> Optional[pd.DataFrame]:
    """Load and aggregate all history.csv files from experiments (cached).

    The full unfiltered DataFrame is cached with a 60-second TTL.
    Filters are applied on the cached copy, avoiding repeated disk I/O.

    Args:
        simulation_mode: Optional filter. None or "all" = no filter,
            "deterministic" = only deterministic rows, "realistic" etc. = that profile.
        automl_tool: Optional filter. None or "all" = no filter.
            Filters by the ``automl_tool`` column in history data.
            Old files without this column are treated as ``"h2o"``.
    """
    import glob

    # Try cache first (returns a copy)
    combined = _history_cache.get("__all__")

    if combined is None:
        # Cache miss -- try DuckDB first (fast), fall back to CSV scanning
        if _db_available():
            combined = _db_load_all()
            if combined is not None:
                logging.info(f"[LoadHistory] Loaded {len(combined)} rows from DuckDB")

        if combined is None:
            # Fallback: legacy CSV scanning (for data not yet migrated to DuckDB)
            pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
            files = glob.glob(pattern)
            if not files:
                return None

            dfs = []
            for f in files:
                try:
                    df = pd.read_csv(f)
                    # Infer baseline_strategy from experiment directory name if column
                    # is missing.  Baseline experiment dirs are named like
                    # "exp_..._BASELINE-RANDOM-DET-100" (from run_experiments.py).
                    if "baseline_strategy" not in df.columns:
                        _dir_name = os.path.basename(os.path.dirname(f)).upper()
                        _BASELINE_DIR_MAP = {
                            "BASELINE-RANDOM": "random",
                            "BASELINE-CVSS": "cvss_priority",
                            "BASELINE-ROBIN": "round_robin",
                            "BASELINE-NOML": "no_ml",
                        }
                        _inferred = "ml_guided"
                        for _prefix, _strategy in _BASELINE_DIR_MAP.items():
                            if _prefix in _dir_name:
                                _inferred = _strategy
                                break
                        df["baseline_strategy"] = _inferred
                    dfs.append(df)
                except Exception as e:
                    logging.warning(f"[LoadHistory] Error reading {f}: {e}")
                    continue

            if not dfs:
                logging.warning(f"[LoadHistory] No valid DataFrames from {len(files)} files")
                return None

            combined = pd.concat(dfs, ignore_index=True)
            if "vulnerability_found" in combined.columns:
                combined["vulnerability_found"] = pd.to_numeric(
                    combined["vulnerability_found"], errors="coerce"
                ).fillna(0).astype(int)

        # Backfill missing automl_tool as "h2o" for older experiment data
        if "automl_tool" not in combined.columns:
            combined["automl_tool"] = "h2o"
        else:
            combined["automl_tool"] = combined["automl_tool"].fillna("h2o")

        # Backfill missing baseline_strategy as "ml_guided"
        if "baseline_strategy" not in combined.columns:
            combined["baseline_strategy"] = "ml_guided"
        else:
            combined["baseline_strategy"] = combined["baseline_strategy"].fillna("ml_guided")

        # Backfill phase/test_origin/score_method for rows that predate the tagged writes
        _NON_ML_BF2 = {"random", "cvss_priority", "round_robin", "no_ml"}
        if "phase" not in combined.columns:
            combined["phase"] = combined["baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_BF2 else "framework"
            )
        else:
            _null_phase2 = combined["phase"].isna()
            combined.loc[_null_phase2, "phase"] = combined.loc[_null_phase2, "baseline_strategy"].apply(
                lambda x: "baseline" if x in _NON_ML_BF2 else "framework"
            )
        if "test_origin" not in combined.columns:
            if "test_strategy" in combined.columns:
                combined["test_origin"] = combined["test_strategy"].apply(
                    lambda x: "llm" if x == "llm_generated" else "registry"
                )
            else:
                combined["test_origin"] = "registry"
        else:
            combined["test_origin"] = combined["test_origin"].fillna("registry")
        if "score_method" not in combined.columns:
            combined["score_method"] = combined["baseline_strategy"].apply(
                lambda x: "heuristic" if x in _NON_ML_BF2 else "ml"
            )
        else:
            _null_sm2 = combined["score_method"].isna()
            combined.loc[_null_sm2, "score_method"] = combined.loc[_null_sm2, "baseline_strategy"].apply(
                lambda x: "heuristic" if x in _NON_ML_BF2 else "ml"
            )

        # Store the full unfiltered DataFrame in cache
        _history_cache.set("__all__", combined)
        logging.info(f"[LoadHistory] Cached {len(combined)} rows")

    # Apply filters on the (copy of) cached data
    if simulation_mode and simulation_mode != "all" and "simulation_mode" in combined.columns:
        combined = combined[combined["simulation_mode"] == simulation_mode]
        if combined.empty:
            return None

    # Filter by automl_tool if requested
    if automl_tool and automl_tool != "all":
        combined = combined[combined["automl_tool"] == automl_tool]
        if combined.empty:
            return None

    # Filter by phase if requested (applied after backfill ensures column always exists)
    if phase and "phase" in combined.columns:
        combined = combined[combined["phase"] == phase]
        if combined.empty:
            return None

    return combined


# Deduplication key: a unique test is identified by device + port + protocol + test_id
_DEDUP_COLS = ["container_id", "open_port", "protocol", "test_id"]


def _deduplicate_history(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate history to unique test combinations.

    Keeps the **last** occurrence of each (container_id, open_port, protocol,
    test_id) tuple, since history CSVs are loaded in chronological order —
    so the last row reflects the most recent result for that test.
    """
    cols_present = [c for c in _DEDUP_COLS if c in df.columns]
    if not cols_present:
        return df
    return df.drop_duplicates(subset=cols_present, keep="last").reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# SIMULATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/simulation/profiles")
def get_simulation_profiles():
    """List all available simulation profiles with descriptions and parameters."""
    return {"profiles": list_profiles()}


@app.get("/api/simulation/profiles/{profile_name}")
def get_simulation_profile(profile_name: str):
    """Get a specific simulation profile by name."""
    if profile_name not in PROFILES:
        raise HTTPException(404, f"Unknown profile: {profile_name}")
    profile = PROFILES[profile_name]
    return {
        "name": profile_name,
        "description": profile["description"],
        "academic_use": profile["academic_use"],
        "config": profile["config"],
    }


class SimulationPreviewRequest(BaseModel):
    mode: str = "realistic"
    seed: int = 42
    iterations: int = 10
    config: Optional[dict] = None


@app.post("/api/simulation/preview")
def preview_simulation(req: SimulationPreviewRequest):
    """Dry-run a simulation to preview what events would fire.

    Runs the RNG without touching any containers — useful to preview
    the effects of different seeds and probabilities.
    """
    if req.mode == "custom" and req.config:
        sim_config = SimulationConfig.from_dict({
            **req.config,
            "mode": "custom",
            "seed": req.seed,
        })
    else:
        try:
            sim_config = get_profile(req.mode)
            sim_config.seed = req.seed
        except ValueError:
            raise HTTPException(400, f"Unknown simulation mode: {req.mode}")

    # Dry run — no Docker client, so no containers are touched
    simulator = EnvironmentSimulator(config=sim_config, docker_client=None)

    for i in range(1, req.iterations + 1):
        simulator.prepare_iteration(i)
        simulator.restore_iteration(i)

    return {
        "mode": sim_config.mode,
        "seed": sim_config.seed,
        "iterations": req.iterations,
        "log": simulator.get_log(),
        "summary": simulator.get_summary(),
    }
