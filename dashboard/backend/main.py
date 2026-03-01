"""
Emergence — IoT Test Case Generator API
FastAPI backend for device discovery, test generation, and execution.
"""
import os
import json
import time
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

docker_client = docker.from_env()

EXPERIMENTS_PATH = "/app/experiments"
SUITES_PATH = "/app/suites"
RESULTS_PATH = "/app/results"
SCANNER_CONTAINER_NAME = "scanner"

os.makedirs(SUITES_PATH, exist_ok=True)
os.makedirs(RESULTS_PATH, exist_ok=True)


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


class RunRequest(BaseModel):
    pass  # No body needed, suite_id comes from URL


class TrainLoopRequest(BaseModel):
    iterations: int = 3
    simulation_mode: str = "deterministic"   # profile name or "custom"
    simulation_seed: int = 42
    simulation_config: Optional[dict] = None  # custom overrides (only if mode="custom")
    train_every_n: int = 0  # 0 = train only after last iteration, 1 = every iter, N = every Nth + last


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
            "description": "Returns whether the H2O AutoML model is trained and its metrics.",
            "category": "ML",
        },
        {
            "method": "GET", "path": "/api/ml/metrics", "summary": "ML metrics",
            "description": "Returns model performance metrics (AUC, feature importance, etc.).",
            "category": "ML",
        },
        {
            "method": "POST", "path": "/api/ml/retrain", "summary": "Retrain model",
            "description": "Manually triggers H2O AutoML model retraining from accumulated test history.",
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
            "summary": "Statistical tests (H1)",
            "description": "Spearman, Mann-Whitney U, Cohen's d for detection-rate convergence hypothesis. Supports simulation_mode filter.",
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

@app.post("/api/generate")
def generate_tests(req: GenerateRequest):
    """Generate or enhance a test suite for the selected devices and protocols."""
    if not req.devices:
        raise HTTPException(400, "No devices provided")

    # Step 1: Compute fingerprint for this configuration
    fingerprint = _compute_suite_fingerprint(
        req.devices, req.protocols, req.severity_filter, req.include_uncommon
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

        # Re-score ALL tests with the latest ML model
        try:
            suite = score_test_suite(suite)
        except Exception as e:
            logging.warning(f"[API] Scorer error during enhancement (non-fatal): {e}")

        # Update metadata
        enhancement_count = suite.metadata.get("enhancement_count", 0) + 1
        suite.metadata["enhancement_count"] = enhancement_count
        suite.metadata["last_enhanced_at"] = datetime.utcnow().isoformat()
        suite.metadata["tests_added_on_enhance"] = len(new_tests)
        suite.metadata["fingerprint"] = fingerprint

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

        try:
            suite = score_test_suite(suite)
        except Exception as e:
            logging.warning(f"[API] Scorer error (non-fatal): {e}")

        # Set fingerprint and initial metadata
        suite.metadata["fingerprint"] = fingerprint
        suite.metadata["enhancement_count"] = 0
        suite.metadata["last_enhanced_at"] = None
        suite.metadata["tests_added_on_enhance"] = 0

        _save_suite(suite)

        result = suite.to_dict()
        result["action"] = "created"
        result["tests_added"] = 0
        return result


@app.get("/api/suites")
def list_suites():
    suites = []
    if os.path.exists(SUITES_PATH):
        for fname in sorted(os.listdir(SUITES_PATH), reverse=True):
            if fname.endswith(".json"):
                fpath = os.path.join(SUITES_PATH, fname)
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    meta = data.get("metadata", {})
                    suites.append({
                        "suite_id": data.get("suite_id"),
                        "name": data.get("name"),
                        "created_at": data.get("created_at"),
                        "total_tests": data.get("total_tests", 0),
                        "protocols": data.get("protocols", []),
                        "recommended_count": data.get("recommended_count", 0),
                        "device_count": len(data.get("devices", [])),
                        "enhancement_count": meta.get("enhancement_count", 0),
                        "last_enhanced_at": meta.get("last_enhanced_at"),
                        "fingerprint": meta.get("fingerprint"),
                    })
                except Exception:
                    continue

    return {"suites": suites}


@app.get("/api/suites/{suite_id}")
def get_suite(suite_id: str):
    suite_data = _load_suite(suite_id)
    if not suite_data:
        raise HTTPException(404, f"Suite {suite_id} not found")
    return suite_data


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

        exit_code, output = container.exec_run(cmd, demux=False)
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
        result_path = os.path.join(RESULTS_PATH, f"result_{suite_id}_{int(time.time())}.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        # Log experiment directory info for debugging hypothesis data
        exp_dir = result.get("experiment_dir")
        history_csv = result.get("history_csv")
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
                from generator.retrain import retrain_model_after_execution, aggregate_history

                with _train_lock:
                    _train_state["status"] = "training"
                    _train_state["started_at"] = datetime.now().isoformat()
                    _train_state["finished_at"] = None
                    _train_state["error"] = None
                    _train_state["auc"] = None
                    _train_state["training_rows"] = None

                agg_path = aggregate_history(EXPERIMENTS_PATH)
                if not agg_path:
                    retrain_result = {"status": "error", "message": "No history data to train on"}
                    with _train_lock:
                        _train_state["status"] = "error"
                        _train_state["finished_at"] = datetime.now().isoformat()
                        _train_state["error"] = "No history data to train on"
                else:
                    retrain_result = retrain_model_after_execution(agg_path)
                    with _train_lock:
                        if retrain_result.get("status") in ("error", "insufficient_data"):
                            _train_state["status"] = "error"
                            _train_state["error"] = retrain_result.get("message", "Training failed")
                        else:
                            _train_state["status"] = "completed"
                            _train_state["auc"] = retrain_result.get("auc")
                            _train_state["training_rows"] = retrain_result.get("training_rows")
                        _train_state["finished_at"] = datetime.now().isoformat()
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
                    fresh_suite = _score(fresh_suite)

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

        return {"run_result": result, "retrain_result": retrain_result, "score_result": score_result}

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

                # Pass simulation context to the suite runner
                sim_context = {
                    "mode": sim_config.mode,
                    "seed": sim_config.seed,
                    "iteration": i,
                    "false_positive_rate": sim_config.false_positive_rate,
                    "false_negative_rate": sim_config.false_negative_rate,
                } if sim_config.is_active() else None

                # Decide whether to train on this iteration
                _ten = req.train_every_n
                if _ten == 0:
                    should_train = (i == req.iterations)  # only last
                else:
                    should_train = (i % _ten == 0) or (i == req.iterations)  # every Nth + last

                outcome = _execute_suite_and_retrain(
                    suite_id, suite, on_phase=_on_phase,
                    simulation_context=sim_context,
                    skip_training=not should_train,
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
                }

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
def ml_status():
    try:
        from automl.pipeline import get_model_metrics
        metrics = get_model_metrics()
        return metrics
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


@app.get("/api/ml/metrics")
def ml_metrics():
    try:
        from automl.pipeline import get_model_metrics
        return get_model_metrics()
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


_train_lock = threading.Lock()
_train_state = {
    "status": "idle",        # idle | training | completed | error
    "started_at": None,
    "finished_at": None,
    "error": None,
    "auc": None,
    "training_rows": None,
}


@app.post("/api/ml/retrain")
def ml_retrain(background_tasks: BackgroundTasks):
    with _train_lock:
        if _train_state["status"] == "training":
            return {
                "status": "already_training",
                "started_at": _train_state["started_at"],
                "message": "Model training is already in progress.",
            }
        _train_state["status"] = "training"
        _train_state["started_at"] = datetime.now().isoformat()
        _train_state["finished_at"] = None
        _train_state["error"] = None
        _train_state["auc"] = None
        _train_state["training_rows"] = None

    def _do_retrain():
        try:
            from generator.retrain import retrain_model_after_execution, aggregate_history
            agg_path = aggregate_history(EXPERIMENTS_PATH)
            if not agg_path:
                with _train_lock:
                    _train_state["status"] = "error"
                    _train_state["finished_at"] = datetime.now().isoformat()
                    _train_state["error"] = "No history data found. Run test suites first."
                return

            result = retrain_model_after_execution(agg_path)

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

        except Exception as e:
            logging.error(f"[API] Manual retrain failed: {e}")
            with _train_lock:
                _train_state["status"] = "error"
                _train_state["finished_at"] = datetime.now().isoformat()
                _train_state["error"] = str(e)

    background_tasks.add_task(_do_retrain)
    return {"status": "training", "started_at": _train_state["started_at"]}


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


@app.get("/api/hypothesis/available-simulation-modes")
def available_simulation_modes():
    """Return distinct simulation_mode values found in history data."""
    import glob as glob_mod

    pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
    files = glob_mod.glob(pattern)
    modes = set()

    for f in files:
        try:
            df = pd.read_csv(f, usecols=["simulation_mode"])
            if "simulation_mode" in df.columns:
                modes.update(df["simulation_mode"].dropna().unique().tolist())
        except Exception:
            # Column may not exist in older history files — skip
            continue

    # Ensure "deterministic" is always present as the baseline
    modes.add("deterministic")
    sorted_modes = sorted(modes, key=lambda m: (m != "deterministic", m))

    return {"modes": sorted_modes}


@app.get("/api/hypothesis/iteration-metrics")
def hypothesis_iteration_metrics(simulation_mode: Optional[str] = None):
    """Per-experiment-run metrics over time for hypothesis validation."""
    import glob as glob_mod

    pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
    files = sorted(glob_mod.glob(pattern))

    logging.info(f"[Hypothesis] Looking for history files with pattern: {pattern}")
    logging.info(f"[Hypothesis] Found {len(files)} history files: {files}")

    if not files:
        logging.warning(f"[Hypothesis] No history files found. EXPERIMENTS_PATH={EXPERIMENTS_PATH}, exists={os.path.exists(EXPERIMENTS_PATH)}")
        if os.path.isdir(EXPERIMENTS_PATH):
            try:
                contents = os.listdir(EXPERIMENTS_PATH)
                logging.info(f"[Hypothesis] Experiments dir contents: {contents}")
            except Exception as e:
                logging.warning(f"[Hypothesis] Cannot list experiments dir: {e}")
        return {"iterations": [], "total_iterations": 0, "available_protocols": []}

    iterations = []
    parse_errors = []
    # Track unique vulnerabilities across iterations for discovery velocity
    seen_vuln_keys = set()
    dedup_cols = list(_DEDUP_COLS)

    for f in files:
        try:
            df = pd.read_csv(f)
            if df.empty:
                logging.info(f"[Hypothesis] Skipping empty file: {f}")
                continue

            # Filter by simulation mode if requested
            if simulation_mode and simulation_mode != "all" and "simulation_mode" in df.columns:
                df = df[df["simulation_mode"] == simulation_mode]
                if df.empty:
                    continue

            exp_dir = os.path.basename(os.path.dirname(f))
            # Handle both old format (exp_2026-02-25_14-30-00) and
            # new UUID format (exp_2026-02-25_14-30-00_a1b2c3)
            raw_ts = exp_dir.replace("exp_", "")
            parts = raw_ts.split("_", 2)  # [date, time, maybe-uuid]
            timestamp = f"{parts[0]} {parts[1]}" if len(parts) >= 2 else raw_ts

            if "vulnerability_found" in df.columns:
                df["vulnerability_found"] = pd.to_numeric(
                    df["vulnerability_found"], errors="coerce"
                ).fillna(0).astype(int)

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
                "experiment_id": exp_dir,
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
            err_msg = f"Error parsing {f}: {exc}"
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
            "files_found": len(files),
            "files_parsed_ok": len(iterations),
            "parse_errors": parse_errors,
        },
    }
    if parse_errors:
        logging.warning(f"[Hypothesis] {len(parse_errors)} files failed to parse: {parse_errors}")
    return result


@app.get("/api/hypothesis/model-evolution")
def hypothesis_model_evolution():
    """ML model metrics snapshot (AUC, feature importance, etc.)."""
    try:
        from automl.pipeline import get_model_metrics
        metrics = get_model_metrics()
        return {"model": metrics}
    except Exception as e:
        return {"model": {"status": "unavailable", "error": str(e)}}


@app.get("/api/hypothesis/composition-analysis")
def hypothesis_composition_analysis():
    """Strategy effectiveness analysis."""
    df = _load_aggregated_history()
    if df is None or df.empty:
        return {"strategies": [], "rules": []}

    strategies = []
    if "test_strategy" in df.columns:
        for strategy, group in df.groupby("test_strategy"):
            total = len(group)
            vulns = int(group["vulnerability_found"].sum()) if "vulnerability_found" in group.columns else 0
            avg_time = (_safe_float(group["execution_time_ms"].mean(), 2) or 0) if "execution_time_ms" in group.columns else 0
            strategies.append({
                "strategy": strategy,
                "total_tests": total,
                "vulns_found": vulns,
                "detection_rate": round(vulns / total, 4) if total > 0 else 0,
                "avg_execution_time_ms": avg_time,
            })

    return {"strategies": strategies, "rules": []}


@app.get("/api/hypothesis/statistical-tests")
def hypothesis_statistical_tests(protocol: Optional[str] = None, simulation_mode: Optional[str] = None):
    """Statistical significance analysis for the convergence hypothesis.

    Optional protocol param filters to per-protocol detection rates.
    Optional simulation_mode filters history data by simulation profile.
    Response keys are flattened for frontend compatibility.
    """
    import numpy as np
    from scipy import stats as scipy_stats

    iter_data = hypothesis_iteration_metrics(simulation_mode=simulation_mode)
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

    # Overall hypothesis verdict
    spearman_sig = spearman_p is not None and spearman_p < 0.05
    spearman_pos = (spearman_rho or 0) > 0
    mw_sig = mann_whitney_p is not None and mann_whitney_p < 0.05
    improvement_pos = (improvement or 0) > 0

    if spearman_sig and spearman_pos and mw_sig:
        verdict = "supported"
    elif spearman_pos and improvement_pos:
        verdict = "trending"
    else:
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
def hypothesis_recommendation_effectiveness(simulation_mode: Optional[str] = None):
    """Compare ML-recommended vs non-recommended test detection rates."""
    df = _load_aggregated_history(simulation_mode=simulation_mode)
    if df is None or df.empty:
        return {"error": "No history data available", "model_available": False}

    scored_df = _predict_risk_scores_on_history(df)

    import numpy as np
    from scipy import stats as scipy_stats

    df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)

    # If model scoring succeeded, use predicted risk scores; otherwise
    # fall back to test_strategy comparison (generated=ML-driven vs static)
    use_model = scored_df is not None
    if use_model:
        df = scored_df
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
def hypothesis_protocol_convergence(simulation_mode: Optional[str] = None):
    """Analyse per-protocol detection rate convergence across iterations."""
    import numpy as np
    from scipy import stats as scipy_stats

    # Reuse the iteration metrics logic
    iter_result = hypothesis_iteration_metrics(simulation_mode=simulation_mode)
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

    return {
        "protocols": protocols,
        "fastest_converging": fastest["protocol"] if fastest else None,
        "most_stable": most_stable_proto["protocol"] if most_stable_proto else None,
    }


# ── H4 — Risk Score Calibration ──────────────────────────────────────

@app.get("/api/hypothesis/risk-calibration")
def hypothesis_risk_calibration(simulation_mode: Optional[str] = None):
    """Analyse calibration of predicted risk scores vs observed vulnerability rates."""
    import numpy as np

    df = _load_aggregated_history(simulation_mode=simulation_mode)
    if df is None or df.empty:
        return {"error": "No history data available", "model_available": False}

    scored_df = _predict_risk_scores_on_history(df)
    if scored_df is None:
        return {"error": "Model unavailable — retrain to enable calibration analysis", "model_available": False}

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

    return {
        "model_available": True,
        "total_predictions": total,
        "calibration_curve": calibration_curve,
        "brier_score": _safe_float(brier, 4) or 0,
        "ece": _safe_float(ece_sum, 4) or 0,
        "mce": _safe_float(mce, 4) or 0,
        "verdict": verdict,
    }


# ── H5 — Execution Efficiency ────────────────────────────────────────
@app.get("/api/hypothesis/execution-efficiency")
def hypothesis_execution_efficiency(simulation_mode: Optional[str] = None):
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

        # Optional simulation_mode filter: check linked history CSV
        if simulation_mode and simulation_mode != "all":
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
        "verdict": verdict,
    }


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


def _compute_suite_fingerprint(devices, protocols, severity_filter, include_uncommon):
    """Compute a content-based fingerprint for a suite configuration."""
    canonical_devices = sorted(
        (d["ip"], sorted(int(p) for p in d.get("ports", [])))
        for d in devices
    )
    canonical = json.dumps({
        "devices": canonical_devices,
        "protocols": sorted(protocols) if protocols else "all",
        "severity": sorted(severity_filter) if severity_filter else "all",
        "include_uncommon": include_uncommon,
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


def _predict_risk_scores_on_history(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Add 'predicted_risk_score' column to history DataFrame using H2O model.

    Constructs feature columns matching the scorer/dataset pattern and runs
    model.predict() to get vulnerability probability for each historical test.
    Returns the augmented DataFrame, or None if the model is unavailable.
    """
    try:
        from automl.pipeline import get_model
        import h2o

        model = get_model()
        if model is None:
            return None

        df = df.copy()

        # Ensure numeric columns
        df["open_port"] = pd.to_numeric(df["open_port"], errors="coerce").fillna(0).astype(int)
        df["vulnerability_found"] = pd.to_numeric(df["vulnerability_found"], errors="coerce").fillna(0).astype(int)

        # Derive aggregate features (matching automl/dataset.py)
        if "container_id" in df.columns:
            df["port_count"] = df.groupby("container_id")["open_port"].transform("nunique")
            df["protocol_diversity"] = df.groupby("container_id")["protocol"].transform("nunique")
        else:
            df["port_count"] = 1
            df["protocol_diversity"] = 1
        df["is_common_port"] = df["open_port"].isin(_COMMON_PORTS).astype(int)

        # Feature columns (matching scorer.py)
        feature_cols = [
            "test_strategy", "device_type", "firmware_version",
            "open_port", "protocol", "service", "auth_required",
            "port_count", "protocol_diversity", "is_common_port",
        ]
        missing = [c for c in feature_cols if c not in df.columns]
        if missing:
            logging.warning(f"[Prediction] Missing feature columns: {missing}")
            return None

        features_df = df[feature_cols].copy()
        for col in ["test_strategy", "device_type", "firmware_version", "protocol", "service"]:
            features_df[col] = features_df[col].astype(str)

        hf = h2o.H2OFrame(features_df)
        preds = model.predict(hf)
        pred_df = preds.as_data_frame()

        # Extract p1 (probability of vulnerability_found=1)
        if "p1" in pred_df.columns:
            scores = pred_df["p1"].tolist()
        elif len(pred_df.columns) >= 3:
            scores = pred_df.iloc[:, 2].tolist()
        else:
            scores = pred_df.iloc[:, 0].tolist()

        df["predicted_risk_score"] = [_safe_float(s, 4) or 0.0 for s in scores]
        return df

    except Exception as e:
        logging.warning(f"[Prediction] Failed to predict risk scores on history: {e}")
        return None


def _load_aggregated_history(simulation_mode: str = None) -> Optional[pd.DataFrame]:
    """Load and aggregate all history.csv files from experiments.

    Args:
        simulation_mode: Optional filter. None or "all" = no filter,
            "deterministic" = only deterministic rows, "realistic" etc. = that profile.
    """
    import glob

    pattern = os.path.join(EXPERIMENTS_PATH, "exp_*", "history.csv")
    files = glob.glob(pattern)
    if not files:
        return None

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
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

    # Filter by simulation mode if requested
    if simulation_mode and simulation_mode != "all" and "simulation_mode" in combined.columns:
        combined = combined[combined["simulation_mode"] == simulation_mode]
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
