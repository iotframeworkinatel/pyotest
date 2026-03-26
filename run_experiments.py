#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emergence - Multi-Framework Controlled Experiment Runner
=========================================================
Runs 15 experiments (5 AutoML frameworks × 3 simulation modes) with
incremental training (train every 10 iterations):

  Frameworks: H2O, AutoGluon, PyCaret, TPOT, auto-sklearn
  Modes:      deterministic (baseline) → medium → realistic

  Framework-first loop: keeps the framework container warm while
  switching simulation modes.  Model is cleared between mode switches
  to prevent cross-contamination.

  Total: 5 × 3 × 100 = 1,500 iterations (~35 hours)

Usage:
    docker compose up -d          # ensure all containers are running
    python run_experiments.py     # run full pipeline

All data is saved in experiments/exp_* directories, accessible via dashboard.
"""

import requests
import time
import shutil
import os
import glob
import json
import sys
from datetime import datetime, timedelta

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

API = "http://localhost:8080"
POLL_INTERVAL = 15  # seconds between status polls
SCAN_POLL_INTERVAL = 5  # seconds between scan status polls
NETWORK = "172.20.0.0/27"

# Paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS_DIR = os.path.join(PROJECT_ROOT, "experiments")
MODELS_DIR = os.path.join(PROJECT_ROOT, "models", "saved")
MODELS_ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "models", "archive")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
SUITES_DIR = os.path.join(PROJECT_ROOT, "suites")

# Sentinel file written as the last step of archive_model().
# If this file is absent from an archive directory the archive is incomplete.
ARCHIVE_SENTINEL = ".archive_complete"

# AutoML frameworks to evaluate
AUTOML_FRAMEWORKS = ["h2o", "autogluon", "pycaret", "tpot", "autosklearn"]

# Simulation mode definitions: (base_name, simulation_mode, seed, iterations, train_every_n)
# Two additional seeds for realistic mode provide seed-robustness evidence for the thesis.
# Each seed is isolated at training time via the simulation_seed column in history.csv.
SIM_MODES = [
    ("CTRL-DET-100",      "deterministic", 42,  100, 10),
    ("TREAT-MED-100",     "medium",        42,  100, 10),
    ("TREAT-REAL-100",    "realistic",     42,  100, 10),
    ("TREAT-REAL-S2-100", "realistic",     123, 100, 10),  # robustness seed 2
    ("TREAT-REAL-S3-100", "realistic",     777, 100, 10),  # robustness seed 3
]

# Pretty names for display
FRAMEWORK_LABELS = {
    "h2o": "H2O",
    "autogluon": "AutoGluon",
    "pycaret": "PyCaret",
    "tpot": "TPOT",
    "autosklearn": "auto-sklearn",
}


# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def api_get(path, timeout=30):
    """GET request with error handling."""
    try:
        r = requests.get(f"{API}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        log(f"API GET {path} failed: {e}", "ERROR")
        return None


def api_post(path, data=None, timeout=30):
    """POST request with error handling."""
    try:
        r = requests.post(f"{API}{path}", json=data or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        log(f"API POST {path} failed: {e}", "ERROR")
        return None


def format_duration(seconds):
    """Format seconds as HH:MM:SS."""
    return str(timedelta(seconds=int(seconds)))


# ----------------------------------------------------------------------
# Step 1: Clear experiment data
# ----------------------------------------------------------------------

def clear_experiment_data(only_llm=False):
    """Remove old experiment data for a clean start.

    If only_llm=True, only remove LLM experiment directories (exp_LLM-*)
    and preserve all other experiment data.
    """
    if only_llm:
        log("Clearing only LLM experiment data (preserving core experiments)...")
        for d in glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_LLM-*")):
            shutil.rmtree(d, ignore_errors=True)
            log(f"  Removed {os.path.basename(d)}")
        # Clear aggregated history (will be rebuilt from remaining exp_* dirs)
        for agg_name in glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv")):
            os.remove(agg_name)
            log(f"  Removed {os.path.basename(agg_name)}")
        log("LLM experiment data cleared (core experiments preserved).")
        return

    log("Clearing old experiment data...")

    # Clear experiment directories (but keep backups)
    for d in glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_*")):
        shutil.rmtree(d, ignore_errors=True)
        log(f"  Removed {os.path.basename(d)}")

    # Clear aggregated history files
    for agg_name in glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv")):
        os.remove(agg_name)
        log(f"  Removed {os.path.basename(agg_name)}")

    # Truncate DuckDB history table — exp_dirs are gone so the DB must also
    # be cleared, otherwise a subsequent run accumulates duplicate rows on top
    # of the previous run's data (simulation_iteration 1-100 overlaps).
    db_path = os.path.join(EXPERIMENTS_DIR, "emergence.db")
    if os.path.exists(db_path):
        try:
            import duckdb
            con = duckdb.connect(db_path)
            con.execute("DELETE FROM history")
            con.close()
            log("  Truncated DuckDB history table")
        except Exception as e:
            log(f"  Warning: could not truncate DuckDB ({e})")

    # Clear saved models (all frameworks)
    if os.path.exists(MODELS_DIR):
        shutil.rmtree(MODELS_DIR, ignore_errors=True)
        os.makedirs(MODELS_DIR, exist_ok=True)
        log("  Cleared models/saved/")

    # Clear archived models from previous runs
    if os.path.exists(MODELS_ARCHIVE_DIR):
        shutil.rmtree(MODELS_ARCHIVE_DIR, ignore_errors=True)
        os.makedirs(MODELS_ARCHIVE_DIR, exist_ok=True)
        log("  Cleared models/archive/")

    # Clear results
    if os.path.exists(RESULTS_DIR):
        for f in glob.glob(os.path.join(RESULTS_DIR, "*.json")):
            os.remove(f)
        log("  Cleared results/")

    # Clear suites
    if os.path.exists(SUITES_DIR):
        for f in glob.glob(os.path.join(SUITES_DIR, "*.json")):
            os.remove(f)
        log("  Cleared suites/")

    # Reset IoT containers to guarantee clean starting state
    reset_iot_containers()

    log("Experiment data cleared.")


# ----------------------------------------------------------------------
# Step 1b: Discover completed experiments (for --resume)
# ----------------------------------------------------------------------

def discover_completed_experiments(expected_iters):
    """Scan existing experiment dirs and return set of completed (tool, mode, seed, phase) tuples.

    - Groups experiment dirs by (automl_tool, simulation_mode, simulation_seed, phase)
    - Counts total iterations per group (each exp dir = 1 iteration)
    - Complete = total iterations >= expected_iters
    - Deletes empty/crashed dirs (0 data rows)
    - Deletes ALL dirs for incomplete combos so they can be re-run from scratch

    Seed is included in the key so that realistic seed=42 and seed=123 are tracked
    independently and don't interfere with each other's resume logic.
    """
    import csv
    from collections import defaultdict

    # Map (tool, mode, seed, phase) -> list of (dir_path, iteration_count)
    combo_dirs = defaultdict(list)

    exp_dirs = sorted(glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_*")))
    for exp_dir in exp_dirs:
        history_csv = os.path.join(exp_dir, "history.csv")
        if not os.path.exists(history_csv):
            # No history file at all — remove
            log(f"  Removing empty dir (no history.csv): {os.path.basename(exp_dir)}")
            shutil.rmtree(exp_dir, ignore_errors=True)
            continue

        # Read first data row to classify
        tool = mode = baseline = ""
        has_llm = False
        tagged_phase = ""
        seed_val = 42  # default for backward compat with pre-seed-column dirs
        n_rows = 0
        try:
            with open(history_csv, newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    n_rows += 1
                    if n_rows == 1:
                        tool = row.get("automl_tool", "")
                        mode = row.get("simulation_mode", "")
                        baseline = row.get("baseline_strategy", "")
                        tagged_phase = row.get("phase", "")
                        try:
                            seed_val = int(row.get("simulation_seed", 42) or 42)
                        except (ValueError, TypeError):
                            seed_val = 42
                    if row.get("test_strategy") == "llm_generated" or row.get("test_origin") == "llm":
                        has_llm = True
        except Exception as e:
            log(f"  Error reading {os.path.basename(exp_dir)}/history.csv: {e}", "WARN")
            continue

        if n_rows == 0:
            log(f"  Removing crashed dir (0 data rows): {os.path.basename(exp_dir)}")
            shutil.rmtree(exp_dir, ignore_errors=True)
            continue

        # Classify phase — prefer the tagged phase column written at run time,
        # fall back to heuristic detection for older dirs that predate the column.
        if baseline and baseline != "ml_guided":
            phase = "baseline"
            key = (baseline, mode, seed_val, phase)
        elif tagged_phase in ("phase5", "phase6"):
            # Dynamic feature phases — explicit tag takes priority over all heuristics.
            # Phase 6 has has_llm=True and would be misclassified without this guard.
            phase = tagged_phase
            key = (tool, mode, seed_val, phase)
        elif tagged_phase == "llm" or has_llm:
            phase = "llm"
            key = (tool, mode, seed_val, phase)
        else:
            phase = "framework"
            key = (tool, mode, seed_val, phase)

        combo_dirs[key].append((exp_dir, n_rows))

    # Determine completed vs incomplete
    completed = set()
    for key, dirs_and_counts in combo_dirs.items():
        total_iters = len(dirs_and_counts)  # each exp dir = 1 iteration
        if total_iters >= expected_iters:
            completed.add(key)
            log(f"  Complete: {key} ({total_iters} iterations)")
        else:
            # Incomplete — delete all dirs for this combo so it can re-run cleanly
            log(f"  Incomplete: {key} ({total_iters}/{expected_iters} iterations) — removing for re-run")
            for dir_path, _ in dirs_and_counts:
                shutil.rmtree(dir_path, ignore_errors=True)

    # Also clean up aggregated history CSVs (will be rebuilt)
    for agg in glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv")):
        os.remove(agg)

    return completed


# ----------------------------------------------------------------------
# Step 1c: Validate model archives (for --resume)
# ----------------------------------------------------------------------

def validate_archives() -> tuple:
    """Scan models/archive/ and delete any incomplete archives.

    An archive is considered complete only when ARCHIVE_SENTINEL exists inside
    it.  If the server crashed mid-copytree the sentinel will be absent, the
    directory will be in an unknown state, and select_best_phase1_framework()
    could read a corrupt model_metrics.json.  We delete such directories so
    the combo re-archives cleanly when the experiment re-runs.

    Returns:
        (valid_count, deleted_count)
    """
    if not os.path.exists(MODELS_ARCHIVE_DIR):
        log("  models/archive/ does not exist — nothing to validate")
        return 0, 0

    valid = 0
    deleted = 0

    for entry in os.scandir(MODELS_ARCHIVE_DIR):
        if not entry.is_dir():
            continue
        sentinel_path = os.path.join(entry.path, ARCHIVE_SENTINEL)
        metrics_path  = os.path.join(entry.path, "model_metrics.json")

        sentinel_ok = os.path.exists(sentinel_path)
        metrics_ok  = os.path.exists(metrics_path)

        if sentinel_ok and metrics_ok:
            valid += 1
        else:
            reasons = []
            if not sentinel_ok:
                reasons.append("missing sentinel (mid-copy crash?)")
            if not metrics_ok:
                reasons.append("missing model_metrics.json")
            log(f"  Archive CORRUPT ({', '.join(reasons)}): {entry.name} — deleting", "WARN")
            shutil.rmtree(entry.path, ignore_errors=True)
            deleted += 1

    log(f"  Archives validated: {valid} intact, {deleted} corrupt/deleted")
    return valid, deleted


# ----------------------------------------------------------------------
# Step 1d: Purge orphaned DuckDB rows (for --resume)
# ----------------------------------------------------------------------

def purge_orphaned_db_rows() -> int:
    """Remove DuckDB history rows whose experiment directory no longer exists.

    After discover_completed_experiments() deletes incomplete combo dirs the
    DB still contains rows those dirs wrote.  This function cross-references
    the exp_dir_name column against directories actually present on disk and
    deletes any orphaned rows.

    Two-pass strategy:
      1. Targeted pass: dirs that were just deleted (fastest).
      2. Consistency pass: any other exp_dir_name not present on disk
         (handles rows left by manual deletions or previous bad resumes).

    Returns total rows deleted.
    """
    db_path = os.path.join(EXPERIMENTS_DIR, "emergence.db")
    if not os.path.exists(db_path):
        log("  DuckDB not found — skipping orphan purge")
        return 0

    # Build the set of directories currently on disk
    surviving_dirs = {
        os.path.basename(d)
        for d in glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_*"))
    }

    total_deleted = 0
    try:
        import duckdb
        con = duckdb.connect(db_path)
        try:
            # Guard: table or column might not exist (very first run)
            tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
            if "history" not in tables:
                log("  DuckDB: history table not found — skipping purge")
                return 0

            cols = {r[1] for r in con.execute("DESCRIBE history").fetchall()}
            if "exp_dir_name" not in cols:
                log("  DuckDB: exp_dir_name column missing — skipping orphan purge", "WARN")
                return 0

            # Find all exp_dir_names present in the DB
            db_dir_names = {
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT exp_dir_name FROM history "
                    "WHERE exp_dir_name IS NOT NULL"
                ).fetchall()
            }

            orphans = db_dir_names - surviving_dirs
            if not orphans:
                log("  DuckDB: no orphaned rows found — DB is consistent")
                return 0

            before = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]

            # Build a safe IN clause using parameterised literals
            placeholders = ", ".join(f"'{n.replace(chr(39), chr(39)*2)}'" for n in orphans)
            con.execute(f"DELETE FROM history WHERE exp_dir_name IN ({placeholders})")

            after = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            total_deleted = before - after

            sample = sorted(orphans)[:5]
            ellipsis = "..." if len(orphans) > 5 else ""
            log(
                f"  DuckDB: purged {total_deleted} orphaned rows from "
                f"{len(orphans)} missing dirs "
                f"({', '.join(sample)}{ellipsis})"
            )
        finally:
            con.close()
    except Exception as e:
        log(f"  Warning: DuckDB orphan purge failed: {e}", "WARN")

    return total_deleted


# ----------------------------------------------------------------------
# Step 1e: Pre-resume state audit
# ----------------------------------------------------------------------

def audit_state_on_resume():
    """Print a human-readable state audit before resume cleanup proceeds.

    Shows counts for experiment dirs, aggregated CSVs, DuckDB rows,
    saved models, and archives — including how many archives are missing
    their sentinel (i.e. potentially corrupt).  This gives visibility
    into what a server crash actually corrupted before any cleanup runs.
    """
    log("=" * 70)
    log("RESUME STATE AUDIT — snapshot before cleanup")
    log("=" * 70)

    # ── Experiment directories ────────────────────────────────────────
    exp_dirs = glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_*"))
    log(f"  Experiment dirs   : {len(exp_dirs)}")

    # ── Aggregated CSVs ───────────────────────────────────────────────
    agg_csvs = glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv"))
    log(f"  Aggregated CSVs   : {len(agg_csvs)} (will be removed during cleanup)")

    # ── DuckDB ───────────────────────────────────────────────────────
    db_path = os.path.join(EXPERIMENTS_DIR, "emergence.db")
    if os.path.exists(db_path):
        try:
            import duckdb
            con = duckdb.connect(db_path, read_only=True)
            try:
                tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
                if "history" in tables:
                    row_count = con.execute("SELECT COUNT(*) FROM history").fetchone()[0]
                    # Count rows whose directory no longer exists
                    surviving = {os.path.basename(d) for d in exp_dirs}
                    cols = {r[1] for r in con.execute("DESCRIBE history").fetchall()}
                    if "exp_dir_name" in cols:
                        db_dirs = {
                            r[0]
                            for r in con.execute(
                                "SELECT DISTINCT exp_dir_name FROM history "
                                "WHERE exp_dir_name IS NOT NULL"
                            ).fetchall()
                        }
                        orphan_dirs = db_dirs - surviving
                        log(f"  DuckDB rows       : {row_count} total, "
                            f"{len(orphan_dirs)} dir(s) already missing from disk")
                    else:
                        log(f"  DuckDB rows       : {row_count} (exp_dir_name col absent — "
                            f"orphan check skipped)")
                else:
                    log("  DuckDB            : history table not yet created")
            finally:
                con.close()
        except Exception as e:
            log(f"  DuckDB            : could not read ({e})", "WARN")
    else:
        log("  DuckDB            : file not found")

    # ── models/saved ─────────────────────────────────────────────────
    if os.path.exists(MODELS_DIR):
        fw_dirs = [
            d for d in os.listdir(MODELS_DIR)
            if os.path.isdir(os.path.join(MODELS_DIR, d))
        ]
        if fw_dirs:
            log(f"  models/saved      : {len(fw_dirs)} framework dir(s): {fw_dirs} "
                f"(will be cleared)")
        else:
            log("  models/saved      : empty")
    else:
        log("  models/saved      : directory absent")

    # ── models/archive ───────────────────────────────────────────────
    if os.path.exists(MODELS_ARCHIVE_DIR):
        archive_dirs = [
            d for d in os.listdir(MODELS_ARCHIVE_DIR)
            if os.path.isdir(os.path.join(MODELS_ARCHIVE_DIR, d))
        ]
        sentinel_ok  = sum(
            1 for d in archive_dirs
            if os.path.exists(os.path.join(MODELS_ARCHIVE_DIR, d, ARCHIVE_SENTINEL))
        )
        corrupt = len(archive_dirs) - sentinel_ok
        log(f"  models/archive    : {len(archive_dirs)} archive(s), "
            f"{sentinel_ok} intact, {corrupt} missing sentinel")
        if corrupt:
            bad = [
                d for d in archive_dirs
                if not os.path.exists(
                    os.path.join(MODELS_ARCHIVE_DIR, d, ARCHIVE_SENTINEL)
                )
            ]
            log(f"    Corrupt archives : {', '.join(bad)}", "WARN")
    else:
        log("  models/archive    : directory absent")

    log("=" * 70)


# ----------------------------------------------------------------------
# Step 2: Scan devices
# ----------------------------------------------------------------------

def scan_devices():
    """Scan the Docker IoT network and return discovered devices."""
    log(f"Scanning network {NETWORK}...")

    resp = api_post("/api/scan", {"network": NETWORK})
    if not resp or resp.get("status") == "error":
        log("Scan failed to start!", "ERROR")
        sys.exit(1)

    # Poll until scan completes
    while True:
        time.sleep(SCAN_POLL_INTERVAL)
        status = api_get("/api/scan/status")
        if not status:
            continue

        if status["status"] == "completed":
            devices = status.get("devices", [])
            log(f"Scan complete: {len(devices)} devices found")
            for d in devices:
                protocols = d.get("protocols", [])
                log(f"  {d['ip']}  - ports {d.get('ports', [])}  - {', '.join(protocols)}")
            return devices

        elif status["status"] == "error":
            log(f"Scan failed: {status.get('error')}", "ERROR")
            sys.exit(1)

        # Still running...


# ----------------------------------------------------------------------
# Step 3: Generate suite
# ----------------------------------------------------------------------

def generate_suite(devices, automl_tool="h2o"):
    """Generate a fresh test suite from discovered devices."""
    log(f"Generating test suite (framework: {FRAMEWORK_LABELS.get(automl_tool, automl_tool)})...")

    device_list = [{"ip": d["ip"], "ports": d.get("ports", [])} for d in devices]

    resp = api_post("/api/generate", {
        "devices": device_list,
        "include_uncommon": True,
        "force_new": True,
        "name": "PhD Experiment Suite",
        "automl_tool": automl_tool,
    })

    if not resp or "suite_id" not in resp:
        log("Suite generation failed!", "ERROR")
        sys.exit(1)

    suite_id = resp["suite_id"]
    total_tests = resp.get("total_tests", 0)
    protocols = resp.get("protocols", [])
    log(f"Suite generated: {suite_id} ({total_tests} tests across {', '.join(protocols)})")

    return suite_id


# ----------------------------------------------------------------------
# Step 4: Run a single experiment
# ----------------------------------------------------------------------

def run_experiment(suite_id, name, mode, seed, iterations, train_every_n, automl_tool="h2o",
                   temporal_training=False, baseline_strategy=None, llm_enabled=False,
                   llm_generate_every_n=10, phase_tag=None, dynamic_features=False):
    """
    Start a train-loop experiment and poll until completion.
    Returns a dict of final metrics.
    """
    fw_label = FRAMEWORK_LABELS.get(automl_tool, automl_tool)
    extra_info = []
    if temporal_training:
        extra_info.append("temporal")
    if baseline_strategy:
        extra_info.append(f"baseline={baseline_strategy}")
    if llm_enabled:
        extra_info.append("LLM")
    if phase_tag:
        extra_info.append(phase_tag)
    if dynamic_features:
        extra_info.append("dynamic")
    extra_str = f" [{', '.join(extra_info)}]" if extra_info else ""

    log(f"{'=' * 70}")
    log(f"STARTING EXPERIMENT: {name}{extra_str}")
    log(f"  Mode: {mode} | Framework: {fw_label} | Seed: {seed}")
    log(f"  Iterations: {iterations} | Train every: {train_every_n}")
    log(f"{'=' * 70}")

    start_time = time.time()

    # Start the train loop
    body = {
        "iterations": iterations,
        "simulation_mode": mode,
        "simulation_seed": seed,
        "train_every_n": train_every_n,
        "automl_tool": automl_tool,
        "temporal_training": temporal_training,
        "baseline_strategy": baseline_strategy,
        "llm_enabled": llm_enabled,
        "llm_generate_every_n": llm_generate_every_n,
        "phase_tag": phase_tag,
        "dynamic_features": dynamic_features,
    }
    resp = api_post(f"/api/suites/{suite_id}/train-loop", body, timeout=60)

    if not resp:
        log(f"Failed to start experiment {name}!", "ERROR")
        return {"name": name, "status": "error", "error": "Failed to start",
                "automl_tool": automl_tool, "mode": mode}

    if resp.get("status") == "error":
        log(f"Failed to start: {resp.get('message', 'unknown')}", "ERROR")
        return {"name": name, "status": "error", "error": resp.get("message"),
                "automl_tool": automl_tool, "mode": mode}

    log(f"Train loop started for {name}")

    # Poll until completion
    last_iter = 0
    while True:
        time.sleep(POLL_INTERVAL)
        status = api_get(f"/api/suites/{suite_id}/train-loop/status", timeout=120)
        if not status:
            continue

        current = status.get("current_iteration", 0)
        total = status.get("total_iterations", iterations)
        phase = status.get("phase", "unknown")
        loop_status = status.get("status", "unknown")

        # Show progress when iteration changes
        if current != last_iter:
            elapsed = format_duration(time.time() - start_time)
            iter_metrics = status.get("iterations", [])
            det_rate = ""
            if iter_metrics:
                last_metric = iter_metrics[-1]
                dr = last_metric.get("detection_rate", 0)
                det_rate = f" | Det. rate: {dr * 100:.1f}%"
                trained = last_metric.get("trained", False)
                if trained:
                    auc = last_metric.get("auc")
                    det_rate += f" | AUC: {auc:.4f}" if auc else ""

            log(f"[{name}] Iter {current}/{total} | Phase: {phase}{det_rate} | Elapsed: {elapsed}")
            last_iter = current

        # Check for completion
        if loop_status == "completed":
            duration = time.time() - start_time
            iter_metrics = status.get("iterations", [])

            # Extract final metrics
            final_auc = None
            avg_detection = 0
            total_vulns = 0
            if iter_metrics:
                # Get AUC from last trained iteration
                for m in reversed(iter_metrics):
                    if m.get("auc") is not None:
                        final_auc = m["auc"]
                        break
                avg_detection = sum(m.get("detection_rate", 0) for m in iter_metrics) / len(iter_metrics)
                total_vulns = sum(m.get("vulnerabilities_found", 0) for m in iter_metrics)

            result = {
                "name": name,
                "status": "completed",
                "mode": mode,
                "seed": seed,
                "iterations": iterations,
                "train_every_n": train_every_n,
                "automl_tool": automl_tool,
                "duration_seconds": duration,
                "duration_formatted": format_duration(duration),
                "final_auc": final_auc,
                "avg_detection_rate": avg_detection,
                "total_vulnerabilities": total_vulns,
                "iteration_metrics": iter_metrics,
            }

            log(f"[{name}] COMPLETED in {format_duration(duration)}")
            log(f"  Framework: {fw_label}")
            log(f"  Final AUC: {final_auc:.4f}" if final_auc else "  Final AUC: N/A")
            log(f"  Avg detection rate: {avg_detection * 100:.1f}%")
            log(f"  Total vulnerabilities: {total_vulns}")
            return result

        elif loop_status in ("error", "cancelled"):
            duration = time.time() - start_time
            error_msg = status.get("error", "Unknown error")
            log(f"[{name}] FAILED after {format_duration(duration)}: {error_msg}", "ERROR")
            return {
                "name": name,
                "status": loop_status,
                "error": error_msg,
                "duration_seconds": duration,
                "mode": mode,
                "automl_tool": automl_tool,
            }


# ----------------------------------------------------------------------
# Step 5: Clear model between experiments
# ----------------------------------------------------------------------

IOT_CONTAINERS = [
    "ftp_anonymous",
    "http_traversal",
    "telnet_insecure",
    "ftp_banner",
    "http_admin_default_creds",
    "http_directory_listing",
    "mqtt_no_auth",
    "ssh_old_banner",
    "ftp_credentials_vuln",
    "coap_vuln",
    "modbus_vuln",
    "http_api_vuln",
    "dns_vuln",
]


def reset_iot_containers():
    """Hard-reset all IoT device containers to their default state.

    docker compose restart recreates the container process from the
    image, discarding any in-container filesystem changes (sed edits,
    moved files, changed passwords).  This is the nuclear option that
    guarantees no state leaks between experiments, even if the
    backend's simulator.cleanup() failed or was skipped.

    Also removes simulation/state.json to prevent custom servers
    from reading stale overrides on startup.
    """
    log("Resetting all IoT containers to default state...")

    # Remove stale state.json
    state_json = os.path.join(PROJECT_ROOT, "simulation", "state.json")
    if os.path.exists(state_json):
        os.remove(state_json)
        log("  Removed simulation/state.json")

    # Recreate all IoT containers from their images to discard any
    # in-container filesystem changes (sed edits, patched configs, etc.).
    # NOTE: "docker compose restart" only restarts the process and does
    # NOT reset the filesystem — we need --force-recreate for that.
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--force-recreate"] + IOT_CONTAINERS,
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            log(f"  Recreated {len(IOT_CONTAINERS)} IoT containers")
        else:
            log(f"  docker compose up --force-recreate failed: {result.stderr[:200]}", "WARN")
    except Exception as e:
        log(f"  Failed to restart containers: {e}", "WARN")

    # Wait for services to stabilize
    log("  Waiting 15s for services to come back up...")
    time.sleep(15)
    log("IoT containers reset complete.")


def clear_between_experiments(automl_tool=None):
    """Clear ML model and aggregated history between experiments.

    Experiment directories (exp_*) are kept so all data remains
    accessible to the dashboard.  Only the saved model and aggregated
    CSVs are removed to prevent the next experiment from inheriting
    a model trained on a different simulation mode.

    If *automl_tool* is specified, only that framework's model directory
    is cleared.  Otherwise all framework models are cleared.
    """
    log("Clearing model and aggregated history between experiments...")

    # Clear aggregated history CSVs (will be regenerated with mode filter)
    for agg_name in glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv")):
        os.remove(agg_name)
        log(f"  Removed {os.path.basename(agg_name)}")

    # Clear saved model(s)
    if automl_tool:
        fw_dir = os.path.join(MODELS_DIR, automl_tool)
        if os.path.exists(fw_dir):
            shutil.rmtree(fw_dir, ignore_errors=True)
            log(f"  Cleared model for {automl_tool}")
    else:
        if os.path.exists(MODELS_DIR):
            shutil.rmtree(MODELS_DIR, ignore_errors=True)
            os.makedirs(MODELS_DIR, exist_ok=True)
            log("  Cleared all saved models")

    log("Ready for next experiment (exp_* dirs preserved).")


def clear_framework_model_on_server(automl_tool):
    """Tell the REST framework server to drop its in-memory model.

    For H2O this is a no-op (the adapter checks server state each time).
    For REST-based frameworks, POST /load with an empty directory forces
    the server to report model_loaded=False.
    """
    if automl_tool == "h2o":
        return  # H2O checks its Java server each time

    framework_urls = {
        "autogluon":  "http://localhost:8082",
        "pycaret":    "http://localhost:8083",
        "tpot":       "http://localhost:8084",
        "autosklearn": "http://localhost:8085",
    }

    url = framework_urls.get(automl_tool)
    if not url:
        return

    try:
        # Loading from a non-existent directory clears the model
        r = requests.post(f"{url}/load", json={"directory": "/app/models/empty"}, timeout=10)
        log(f"  Cleared in-memory model on {automl_tool} server")
    except Exception as e:
        log(f"  Warning: could not clear {automl_tool} server model: {e}", "WARN")


def archive_model(automl_tool, sim_mode):
    """Archive the current trained model before clearing.

    Copies models/saved/{framework}/ → models/archive/{framework}_{mode}/
    so every experiment's final model is preserved for later comparison
    or reload.  The active path (models/saved/) is NOT touched — the
    caller is expected to clear it afterwards.

    Writes ARCHIVE_SENTINEL as the very last step so that validate_archives()
    can detect incomplete copies caused by a mid-archive crash.
    """
    src = os.path.join(MODELS_DIR, automl_tool)
    if not os.path.exists(src):
        log(f"  No model to archive for {automl_tool} ({sim_mode})")
        return

    dest = os.path.join(MODELS_ARCHIVE_DIR, f"{automl_tool}_{sim_mode}")
    os.makedirs(MODELS_ARCHIVE_DIR, exist_ok=True)

    # Remove previous archive for this combo (re-run safety).
    # Also removes any leftover sentinel so the directory is never
    # seen as "valid" while the copy is in progress.
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)

    shutil.copytree(src, dest)

    # Write sentinel LAST — absence means the archive is incomplete.
    sentinel_path = os.path.join(dest, ARCHIVE_SENTINEL)
    with open(sentinel_path, "w") as f:
        json.dump({
            "automl_tool": automl_tool,
            "sim_mode": sim_mode,
            "archived_at": datetime.utcnow().isoformat() + "Z",
        }, f, indent=2)

    log(f"  Archived model: {automl_tool}/{sim_mode} -> models/archive/{automl_tool}_{sim_mode}/")


# ----------------------------------------------------------------------
# Step 6: Print summary
# ----------------------------------------------------------------------

def print_summary(all_results):
    """Print a comparison table of all experiment results."""
    print("\n")
    print("=" * 120)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 120)
    print(f"{'Name':<30} {'Framework':<12} {'Mode':<15} {'Train':<8} {'Status':<12} {'Duration':<10} {'AUC':<10} {'Avg Det%':<10} {'Vulns':<8}")
    print("-" * 120)

    for r in all_results:
        name = r.get("name", "?")
        fw = FRAMEWORK_LABELS.get(r.get("automl_tool", "?"), r.get("automl_tool", "?"))
        mode = r.get("mode", "?")
        ten = r.get("train_every_n", "?")
        status = r.get("status", "?")
        duration = r.get("duration_formatted", "?")
        auc = r.get("final_auc")
        auc_str = f"{auc:.4f}" if auc else "N/A"
        avg_det = r.get("avg_detection_rate", 0)
        avg_det_str = f"{avg_det * 100:.1f}%"
        vulns = r.get("total_vulnerabilities", 0)

        train_label = f"every {ten}"

        print(f"{name:<30} {fw:<12} {mode:<15} {train_label:<8} {status:<12} {duration:<10} {auc_str:<10} {avg_det_str:<10} {vulns:<8}")

    print("=" * 120)

    # Print cross-framework comparison matrix
    print_cross_framework_matrix(all_results)

    # Save summary to file
    summary_path = os.path.join(EXPERIMENTS_DIR, "experiment_summary.json")
    save_data = []
    for r in all_results:
        save_data.append({k: v for k, v in r.items() if k != "iteration_metrics"})
    with open(summary_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\nFull summary saved to: {summary_path}")


def print_cross_framework_matrix(all_results):
    """Print AUC comparison matrix: frameworks × simulation modes."""
    completed = [r for r in all_results if r.get("status") == "completed"]
    if not completed:
        return

    # Collect unique modes and frameworks
    modes = []
    for _, mode, _, _, _ in SIM_MODES:
        modes.append(mode)
    frameworks = AUTOML_FRAMEWORKS

    # Build AUC matrix
    auc_map = {}
    for r in completed:
        key = (r.get("automl_tool"), r.get("mode"))
        auc_map[key] = r.get("final_auc")

    print(f"\n{'CROSS-FRAMEWORK AUC COMPARISON':^80}")
    print("=" * 80)

    # Header
    header = f"{'Framework':<15}"
    for mode in modes:
        header += f" {mode:<20}"
    print(header)
    print("-" * 80)

    # Rows
    for fw in frameworks:
        label = FRAMEWORK_LABELS.get(fw, fw)
        row = f"{label:<15}"
        for mode in modes:
            auc = auc_map.get((fw, mode))
            if auc is not None:
                row += f" {auc:<20.4f}"
            else:
                row += f" {'N/A':<20}"
        print(row)

    print("=" * 80)


# ----------------------------------------------------------------------
# Baseline experiment configurations
# ----------------------------------------------------------------------

BASELINES = [
    ("BASELINE-RANDOM", "random"),
    ("BASELINE-CVSS", "cvss_priority"),
    ("BASELINE-ROBIN", "round_robin"),
    ("BASELINE-NOML", "no_ml"),
]

# LLM experiment configurations (single framework + LLM generation)
LLM_EXPERIMENTS = [
    ("LLM-DET-100", "deterministic", 42, 100, 10),
    ("LLM-MED-100", "medium", 42, 100, 10),
    ("LLM-REAL-100", "realistic", 42, 100, 10),
]

# Phase 5: Dynamic rolling features, all 5 frameworks — mirrors Phase 1 structure
PHASE5_FRAMEWORKS = ["h2o", "autogluon", "pycaret", "tpot", "autosklearn"]
PHASE5_MODES = [
    ("P5-CTRL-DET-100",   "deterministic", 42, 100, 10),
    ("P5-TREAT-MED-100",  "medium",        42, 100, 10),
    ("P5-TREAT-REAL-100", "realistic",     42, 100, 10),
]

# Phase 6: Dynamic + LLM — framework auto-selected at runtime from Phase 1 archived AUC.
# PHASE6_FRAMEWORKS is populated dynamically in main() via select_best_phase1_framework().
PHASE6_FRAMEWORKS = ["h2o"]  # default fallback; overwritten at runtime
PHASE6_MODES = [
    ("P6-CTRL-DET-100",   "deterministic", 42, 100, 10),
    ("P6-TREAT-MED-100",  "medium",        42, 100, 10),
    ("P6-TREAT-REAL-100", "realistic",     42, 100, 10),
]


def select_best_phase1_framework(sim_mode="realistic"):
    """Read Phase 1 archived model_metrics.json files and return the best-AUC framework.

    Compares all frameworks archived under models/archive/{fw}_{sim_mode}/model_metrics.json
    and returns the one with the highest valid AUC (> 0.5).  Falls back to "h2o" when no
    valid archived models exist (e.g. Phase 1 was skipped or all frameworks failed).

    Args:
        sim_mode: Simulation mode to compare (default: "realistic", the thesis-critical mode).

    Returns:
        Framework name string (e.g. "h2o", "autogluon").
    """
    best_fw = None
    best_auc = -1.0

    for fw in AUTOML_FRAMEWORKS:
        metrics_path = os.path.join(MODELS_ARCHIVE_DIR, f"{fw}_{sim_mode}", "model_metrics.json")
        if not os.path.exists(metrics_path):
            log(f"  {FRAMEWORK_LABELS.get(fw, fw)}: no archive found at {metrics_path}", "WARN")
            continue
        try:
            with open(metrics_path) as f:
                metrics = json.load(f)
            auc = metrics.get("auc")
            if auc is None:
                log(f"  {FRAMEWORK_LABELS.get(fw, fw)}: AUC=null (skipped)")
                continue
            auc = float(auc)
            log(f"  {FRAMEWORK_LABELS.get(fw, fw)}: AUC={auc:.4f}")
            if auc > best_auc:
                best_auc = auc
                best_fw = fw
        except Exception as e:
            log(f"  {FRAMEWORK_LABELS.get(fw, fw)}: could not read metrics: {e}", "WARN")

    if best_fw is None or best_auc <= 0.5:
        log(f"  No valid Phase 1 {sim_mode} models found (threshold > 0.5) — defaulting Phase 6 to h2o")
        return "h2o"

    log(f"  Phase 6 auto-selected: {FRAMEWORK_LABELS.get(best_fw, best_fw)} (AUC={best_auc:.4f})")
    return best_fw


def run_baseline_experiments(suite_id, devices, all_results, completed=None):
    """Run baseline experiments: 4 baselines × 3 modes × 100 iterations = 1,200 iterations."""
    log(f"\n{'#' * 70}")
    log(f"  BASELINE EXPERIMENTS")
    log(f"  {len(BASELINES)} baselines × {len(SIM_MODES)} modes")
    log(f"{'#' * 70}")

    for baseline_name, strategy in BASELINES:
        for base_name, mode, seed, iters, train_n in SIM_MODES:
            experiment_name = f"{baseline_name}-{mode.upper()[:3]}-{iters}"

            if completed and (strategy, mode, seed, "baseline") in completed:
                log(f"  SKIP (already completed): {experiment_name} [{strategy}/{mode}/s{seed}]")
                all_results.append({"name": experiment_name, "status": "skipped_resume",
                                    "mode": mode, "automl_tool": "h2o",
                                    "baseline_strategy": strategy})
                continue

            log(f"\n  Baseline: {strategy} | Mode: {mode}")

            reset_iot_containers()

            result = run_experiment(
                suite_id, experiment_name, mode, seed, iters,
                train_every_n=0,  # Baselines don't train
                automl_tool="h2o",  # Placeholder (not used for baselines)
                baseline_strategy=strategy,
            )
            all_results.append(result)


LLM_FRAMEWORKS = AUTOML_FRAMEWORKS  # LLM experiments run across all AutoML frameworks


def run_llm_experiments(suite_id, devices, all_results, completed=None):
    """Run LLM experiments: N frameworks × 3 modes × 100 iterations."""
    log(f"\n{'#' * 70}")
    log(f"  LLM GENERATION EXPERIMENTS")
    log(f"  {len(LLM_EXPERIMENTS)} modes × {len(LLM_FRAMEWORKS)} frameworks + LLM")
    log(f"{'#' * 70}")

    for fw in LLM_FRAMEWORKS:
        fw_label = FRAMEWORK_LABELS.get(fw, fw)
        for base_name, mode, seed, iters, train_n in LLM_EXPERIMENTS:
            experiment_name = f"{base_name}-{fw_label}"

            if completed and (fw, mode, 42, "llm") in completed:
                log(f"  SKIP (already completed): {experiment_name} [{fw}/{mode}/llm]")
                all_results.append({"name": experiment_name, "status": "skipped_resume",
                                    "mode": mode, "automl_tool": fw})
                continue

            log(f"\n  LLM + {fw_label} | Mode: {mode}")

            reset_iot_containers()
            clear_between_experiments(automl_tool=fw)

            result = run_experiment(
                suite_id, experiment_name, mode, seed, iters, train_n,
                automl_tool=fw,
                temporal_training=True,
                llm_enabled=True,
                llm_generate_every_n=25,
            )
            all_results.append(result)


def run_phase5_experiments(suite_id, devices, all_results, completed=None):
    """Run Phase 5: dynamic rolling features, all 5 frameworks × 3 modes × 100 iters."""
    log(f"\n{'#' * 70}")
    log(f"  PHASE 5: DYNAMIC ROLLING FEATURES")
    log(f"  {len(PHASE5_FRAMEWORKS)} frameworks × {len(PHASE5_MODES)} modes")
    log(f"{'#' * 70}")

    for fw in PHASE5_FRAMEWORKS:
        fw_label = FRAMEWORK_LABELS.get(fw, fw)
        for base_name, mode, seed, iters, train_n in PHASE5_MODES:
            experiment_name = f"{base_name}-{fw.upper()}"

            if completed and (fw, mode, 42, "phase5") in completed:
                log(f"  SKIP (already completed): {experiment_name} [{fw}/{mode}/phase5]")
                all_results.append({"name": experiment_name, "status": "skipped_resume",
                                    "mode": mode, "automl_tool": fw})
                continue

            log(f"\n  Phase5 + {fw_label} | Mode: {mode}")
            reset_iot_containers()
            clear_between_experiments(automl_tool=fw)
            clear_framework_model_on_server(fw)

            result = run_experiment(
                suite_id, experiment_name, mode, seed, iters, train_n,
                automl_tool=fw,
                temporal_training=True,
                phase_tag="phase5",
                dynamic_features=True,
            )
            all_results.append(result)

            if result.get("status") == "completed":
                archive_model(fw, f"{mode}_phase5")


def run_phase6_experiments(suite_id, devices, all_results, completed=None, frameworks=None):
    """Run Phase 6: dynamic features + LLM — best Phase 1 framework × 3 modes × 100 iters."""
    _frameworks = frameworks if frameworks is not None else PHASE6_FRAMEWORKS
    fw_names = ", ".join(FRAMEWORK_LABELS.get(fw, fw) for fw in _frameworks)
    log(f"\n{'#' * 70}")
    log(f"  PHASE 6: DYNAMIC FEATURES + LLM ({fw_names})")
    log(f"  {len(_frameworks)} framework × {len(PHASE6_MODES)} modes")
    log(f"{'#' * 70}")

    for fw in _frameworks:
        fw_label = FRAMEWORK_LABELS.get(fw, fw)
        for base_name, mode, seed, iters, train_n in PHASE6_MODES:
            experiment_name = f"{base_name}-{fw.upper()}"

            if completed and (fw, mode, 42, "phase6") in completed:
                log(f"  SKIP (already completed): {experiment_name} [{fw}/{mode}/phase6]")
                all_results.append({"name": experiment_name, "status": "skipped_resume",
                                    "mode": mode, "automl_tool": fw})
                continue

            log(f"\n  Phase6 + {fw_label} + LLM | Mode: {mode}")
            reset_iot_containers()
            clear_between_experiments(automl_tool=fw)
            clear_framework_model_on_server(fw)

            result = run_experiment(
                suite_id, experiment_name, mode, seed, iters, train_n,
                automl_tool=fw,
                temporal_training=True,
                llm_enabled=True,
                llm_generate_every_n=25,
                phase_tag="phase6",
                dynamic_features=True,
            )
            all_results.append(result)

            if result.get("status") == "completed":
                archive_model(fw, f"{mode}_phase6")


def run_lopo_analysis(phase=None):
    """Run leave-one-protocol-out analysis as post-processing."""
    log(f"\n{'#' * 70}")
    log(f"  LOPO GENERALIZATION ANALYSIS")
    log(f"{'#' * 70}")

    lopo_results = []
    for fw in AUTOML_FRAMEWORKS:
        fw_label = FRAMEWORK_LABELS.get(fw, fw)
        log(f"\n  LOPO for {fw_label}...")

        for _, mode, _, _, _ in SIM_MODES:
            phase_param = f"&phase={phase}" if phase else ""
            resp = api_get(f"/api/hypothesis/generalization?automl_tool={fw}&simulation_mode={mode}{phase_param}", timeout=300)
            if resp and resp.get("status") == "ok":
                summary = resp.get("summary", {})
                log(f"    {mode}: LOPO AUC={summary.get('mean_auc', 'N/A')}, "
                    f"evaluated={summary.get('n_evaluated', 0)}/{summary.get('n_protocols', 0)}")
                lopo_results.append({
                    "framework": fw,
                    "mode": mode,
                    "mean_auc": summary.get("mean_auc"),
                    "verdict": summary.get("verdict"),
                })
            else:
                log(f"    {mode}: LOPO failed or insufficient data")

    # Print LOPO summary
    if lopo_results:
        print(f"\n{'LOPO GENERALIZATION RESULTS':^80}")
        print("=" * 80)
        print(f"{'Framework':<15} {'Mode':<15} {'Mean LOPO AUC':<15} {'Verdict':<20}")
        print("-" * 80)
        for r in lopo_results:
            fw = FRAMEWORK_LABELS.get(r["framework"], r["framework"])
            auc = f"{r['mean_auc']:.4f}" if r.get("mean_auc") is not None else "N/A"
            print(f"{fw:<15} {r['mode']:<15} {auc:<15} {r.get('verdict', 'N/A'):<20}")
        print("=" * 80)

    return lopo_results


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    global PHASE6_FRAMEWORKS
    total_start = time.time()

    # Parse CLI arguments
    quick_mode = "--quick" in sys.argv  # 5 iterations instead of 100 for smoke testing
    skip_baselines = "--skip-baselines" in sys.argv
    skip_llm = "--skip-llm" in sys.argv
    skip_lopo = "--skip-lopo" in sys.argv
    only_baselines = "--only-baselines" in sys.argv
    only_llm = "--only-llm" in sys.argv
    only_phase5 = "--only-phase5" in sys.argv
    only_phase6 = "--only-phase6" in sys.argv
    skip_phase5 = "--skip-phase5" in sys.argv
    skip_phase6 = "--skip-phase6" in sys.argv
    resume_mode = "--resume" in sys.argv
    rebuild_db = "--rebuild-db" in sys.argv  # rebuild DuckDB from CSVs after run

    if quick_mode:
        # Override iteration counts for quick testing
        for i, (name, mode, seed, _, train_n) in enumerate(SIM_MODES):
            SIM_MODES[i] = (name, mode, seed, 5, 5)
        for i, (name, mode, seed, _, train_n) in enumerate(LLM_EXPERIMENTS):
            LLM_EXPERIMENTS[i] = (name, mode, seed, 5, 5)
        for i, (name, mode, seed, _, train_n) in enumerate(PHASE5_MODES):
            PHASE5_MODES[i] = (name, mode, seed, 5, 5)
        for i, (name, mode, seed, _, train_n) in enumerate(PHASE6_MODES):
            PHASE6_MODES[i] = (name, mode, seed, 5, 5)
        log("QUICK MODE: Using 5 iterations instead of 100")

    n_framework_exps = len(AUTOML_FRAMEWORKS) * len(SIM_MODES)
    n_baseline_exps = len(BASELINES) * len(SIM_MODES)
    n_llm_exps = len(LLM_FRAMEWORKS) * len(LLM_EXPERIMENTS)  # all frameworks × all LLM modes
    n_phase5_exps = len(PHASE5_FRAMEWORKS) * len(PHASE5_MODES)
    n_phase6_exps = len(PHASE6_FRAMEWORKS) * len(PHASE6_MODES)  # actual count; fw auto-selected later
    total_experiments = n_framework_exps + n_baseline_exps + n_llm_exps + n_phase5_exps + n_phase6_exps

    iters_per_exp = 5 if quick_mode else 100
    est_hours = total_experiments * iters_per_exp * 2.5 / 60 / 60  # rough: ~2.5 min per iteration

    n_realistic_seeds = sum(1 for _, mode, _, _, _ in SIM_MODES if mode == "realistic")

    print(f"""
    ==============================================================
      Emergence - Multi-Framework PhD Experiment Runner v2

      Phase 1 (ML):   {n_framework_exps} experiments ({len(AUTOML_FRAMEWORKS)} fw × {len(SIM_MODES)} modes, incl. {n_realistic_seeds} realistic seeds)
      Phase 2 (Base): {n_baseline_exps} experiments ({len(BASELINES)} baselines × {len(SIM_MODES)} modes)
      Phase 3 (LLM):  {n_llm_exps} experiments ({len(LLM_FRAMEWORKS)} fw × {len(LLM_EXPERIMENTS)} modes)
      Phase 5 (Dyn):  {n_phase5_exps} experiments ({len(PHASE5_FRAMEWORKS)} fw × {len(PHASE5_MODES)} modes)
      Phase 6 (D+L):  {n_phase6_exps} experiments (best fw × {len(PHASE6_MODES)} modes, auto-selected)
      LOPO Analysis:  post-processing (Phases 1, 5)

      Frameworks: {', '.join(FRAMEWORK_LABELS[fw] for fw in AUTOML_FRAMEWORKS)}
      Baselines:  {', '.join(name for _, name in BASELINES)}
      Modes:      deterministic → medium → realistic (×{n_realistic_seeds} seeds)

      Total: {total_experiments} experiments × {iters_per_exp} iterations
      Estimated duration: ~{est_hours:.0f} hours
      {'QUICK MODE: 5 iterations' if quick_mode else 'Full mode: 100 iterations'}
      {'RESUME MODE: Skipping completed experiments' if resume_mode else ''}
    ==============================================================
    """)

    # Verify API is reachable
    log("Checking API connectivity...")
    try:
        r = requests.get(f"{API}/api/devices", timeout=5)
        r.raise_for_status()
        log("API is reachable.")
    except Exception as e:
        log(f"Cannot reach API at {API}: {e}", "ERROR")
        log("Make sure containers are running: docker compose up -d")
        sys.exit(1)

    # Verify AutoML framework availability
    log("Checking AutoML framework availability...")
    fw_status = api_get("/api/automl/frameworks")
    if fw_status:
        for fw in fw_status.get("frameworks", []):
            status_icon = "✓" if fw["available"] else "✗"
            log(f"  {status_icon} {FRAMEWORK_LABELS.get(fw['name'], fw['name'])}: "
                f"available={fw['available']}, has_model={fw.get('has_model', False)}")

        unavailable = [
            fw["name"] for fw in fw_status.get("frameworks", [])
            if fw["name"] in AUTOML_FRAMEWORKS and not fw["available"]
        ]
        if unavailable:
            labels = [FRAMEWORK_LABELS.get(fw, fw) for fw in unavailable]
            log(f"WARNING: These frameworks are unavailable and will be skipped: {', '.join(labels)}", "WARN")
    else:
        log("Could not check framework status — proceeding anyway", "WARN")

    # Step 1: Clear experiment data (preserve core results when running --only-llm)
    completed = set()
    if resume_mode:
        expected_iters = 5 if quick_mode else 100

        # ── Pre-cleanup audit ─────────────────────────────────────────
        # Print a snapshot of what exists before we touch anything so the
        # operator can see what the crash actually corrupted.
        audit_state_on_resume()

        log("RESUME MODE: Preserving completed experiment data")

        # ── Discover & delete incomplete combos ───────────────────────
        # discover_completed_experiments() deletes exp_* dirs for any
        # combo that didn't reach expected_iters AND removes all
        # aggregated_history*.csv files (they're cheap to regenerate).
        completed = discover_completed_experiments(expected_iters)

        # ── DuckDB consistency ────────────────────────────────────────
        # Remove rows whose experiment directory was just deleted (or was
        # already gone from a previous bad resume).  Must run AFTER
        # discover_completed_experiments() so the disk state is final.
        purge_orphaned_db_rows()

        # ── Archive integrity ─────────────────────────────────────────
        # Delete any archive directory missing its sentinel file; those
        # archives were written by a crash mid-copytree and may contain
        # a partial model binary or stale model_metrics.json.
        validate_archives()

        # ── Clear models/saved ────────────────────────────────────────
        # models/saved/ is transient working state.  On a clean run it is
        # populated by training and then copied to models/archive/ after
        # each mode.  A crash may leave it holding a model that is:
        #   - mid-training (partially fitted),
        #   - trained on the wrong seed / mode, or
        #   - trained on more iterations than the experiment will replay.
        # Always wipe it so the resumed run starts each combo from a blank
        # slate; models/archive/ (now sentinel-validated) is untouched.
        if os.path.exists(MODELS_DIR):
            shutil.rmtree(MODELS_DIR, ignore_errors=True)
            os.makedirs(MODELS_DIR, exist_ok=True)
            log("  Cleared models/saved/ — will retrain from scratch per combo")

        log(f"  {len(completed)} fully completed experiment combos found")
        for key in sorted(completed):
            log(f"    {key}")

        # Reset IoT containers to a known-good state before resuming
        reset_iot_containers()
    else:
        clear_experiment_data(only_llm=only_llm)

    # Step 2: Scan devices
    devices = scan_devices()
    if not devices:
        log("No devices found! Check Docker containers.", "ERROR")
        sys.exit(1)

    # Step 3: Generate fresh suite (using h2o as default — will be re-scored per framework)
    suite_id = generate_suite(devices, automl_tool="h2o")

    all_results = []
    experiment_num = 0

    # ── Framework-first loop ──────────────────────────────────────────
    # Keeps each framework container warm while cycling through modes.
    # Model is cleared between mode switches to prevent contamination.
    if only_llm or only_baselines or only_phase5 or only_phase6:
        log(f"\nSkipping ML framework experiments (mode flag active)")
    for fw in ([] if only_llm or only_baselines or only_phase5 or only_phase6 else AUTOML_FRAMEWORKS):
        fw_label = FRAMEWORK_LABELS.get(fw, fw)

        # Check if framework is available
        if fw_status:
            fw_info = next((f for f in fw_status.get("frameworks", []) if f["name"] == fw), None)
            if fw_info and not fw_info["available"]:
                log(f"\nSkipping {fw_label} — container not available")
                for base_name, mode, seed, iters, train_n in SIM_MODES:
                    experiment_name = f"{base_name}-{fw.upper()}"
                    all_results.append({
                        "name": experiment_name,
                        "status": "skipped",
                        "mode": mode,
                        "automl_tool": fw,
                        "error": "Framework container not available",
                    })
                continue

        log(f"\n{'#' * 70}")
        log(f"  FRAMEWORK BLOCK: {fw_label}")
        log(f"  Running {len(SIM_MODES)} simulation modes")
        log(f"{'#' * 70}")

        first_run_in_block = True
        for mode_idx, (base_name, mode, seed, iters, train_n) in enumerate(SIM_MODES):
            experiment_num += 1
            experiment_name = f"{base_name}-{fw.upper()}"

            # Resume: skip already-completed experiments (key includes seed for multi-seed isolation)
            if resume_mode and (fw, mode, seed, "framework") in completed:
                log(f"  SKIP (already completed): {experiment_name} [{fw}/{mode}/s{seed}]")
                all_results.append({"name": experiment_name, "status": "skipped_resume",
                                    "mode": mode, "automl_tool": fw})
                continue

            # First non-skipped mode in this block — ensure clean state
            if first_run_in_block:
                first_run_in_block = False
                if resume_mode:
                    log(f"  Preparing fresh state for {fw_label}/{mode}...")
                    reset_iot_containers()
                    clear_between_experiments(automl_tool=fw)
                    clear_framework_model_on_server(fw)

            log(f"\n{'=' * 70}")
            log(f"EXPERIMENT {experiment_num}/{total_experiments}: {experiment_name}")
            log(f"  Framework: {fw_label} | Mode: {mode}")
            log(f"{'=' * 70}")

            result = run_experiment(
                suite_id, experiment_name, mode, seed, iters, train_n,
                automl_tool=fw, temporal_training=True,  # Enable temporal splits for all ML experiments
            )
            all_results.append(result)

            # Archive model, then clear between simulation modes
            if result.get("status") == "completed":
                archive_model(fw, mode)

            if mode_idx < len(SIM_MODES) - 1:
                if result.get("status") == "completed":
                    log("Cooling down for 10 seconds...")
                    time.sleep(10)
                reset_iot_containers()  # Hard-reset containers to prevent state leaks
                clear_between_experiments(automl_tool=fw)
                clear_framework_model_on_server(fw)

        # Archive the last mode's model, then clear between framework blocks
        if fw != AUTOML_FRAMEWORKS[-1]:
            log(f"\nFinished {fw_label} block. Clearing all models before next framework...")
            time.sleep(10)
            reset_iot_containers()  # Hard-reset containers to prevent state leaks
            clear_between_experiments()  # Clear all models
            clear_framework_model_on_server(fw)  # Clear the server-side model too

    # ── Phase 2: Baseline experiments ────────────────────────────────
    if not skip_baselines and not only_llm and not only_phase5 and not only_phase6:
        run_baseline_experiments(suite_id, devices, all_results, completed=completed)
    elif skip_baselines:
        log("\nSkipping baseline experiments (--skip-baselines)")

    # ── Phase 3: LLM generation experiments ──────────────────────────
    if not skip_llm and not only_baselines and not only_phase5 and not only_phase6:
        run_llm_experiments(suite_id, devices, all_results, completed=completed)
    elif skip_llm:
        log("\nSkipping LLM experiments (--skip-llm)")

    # ── Phase 4: LOPO generalization analysis ────────────────────────
    lopo_results = []
    if not skip_lopo and not only_baselines and not only_llm and not only_phase5 and not only_phase6:
        lopo_results = run_lopo_analysis()
    elif skip_lopo:
        log("\nSkipping LOPO analysis (--skip-lopo)")

    # ── Phase 5: Dynamic features (all 5 frameworks × 3 modes) ───────
    if not skip_phase5 and not only_llm and not only_baselines and not only_phase6:
        run_phase5_experiments(suite_id, devices, all_results, completed=completed)
        if not skip_lopo:
            run_lopo_analysis(phase="phase5")
    elif only_phase5:
        run_phase5_experiments(suite_id, devices, all_results, completed=completed)
        if not skip_lopo:
            run_lopo_analysis(phase="phase5")

    # ── Phase 6: Dynamic + LLM — auto-select best Phase 1 framework ──
    # Read archived Phase 1 realistic-mode AUC values and pick the winner.
    # This runs after Phase 1 completes so the archives are always populated.
    log(f"\n{'#' * 70}")
    log(f"  Selecting best Phase 1 framework for Phase 6...")
    log(f"{'#' * 70}")
    phase6_best_fw = select_best_phase1_framework(sim_mode="realistic")
    PHASE6_FRAMEWORKS = [phase6_best_fw]

    if not skip_phase6 and not only_baselines and not only_phase5:
        if only_phase6 or (not only_llm):
            run_phase6_experiments(suite_id, devices, all_results, completed=completed,
                                   frameworks=PHASE6_FRAMEWORKS)

    # -- Rebuild DuckDB from CSVs (optional) -----------------------
    # Pass --rebuild-db to rebuild from authoritative CSVs after the
    # run and print a completeness report suitable for sharing the DB.
    if rebuild_db:
        log("\nRebuilding DuckDB from experiment CSVs for verification...")
        try:
            import importlib.util
            _spec = importlib.util.spec_from_file_location(
                "migrate_to_duckdb",
                os.path.join(PROJECT_ROOT, "migrate_to_duckdb.py"),
            )
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.main()
            log("DuckDB rebuild complete. See row counts above for completeness verification.")
        except Exception as _e:
            log(f"Warning: DuckDB rebuild failed ({_e}). "
                f"Run 'python migrate_to_duckdb.py' manually before sharing the DB.")

    # -- Summary ---------------------------------------------------
    total_duration = time.time() - total_start
    log(f"\nAll experiments completed in {format_duration(total_duration)}")
    print_summary(all_results)

    # Fetch cross-framework statistical comparison
    log("\nFetching cross-framework statistical comparison...")
    comparison = api_get("/api/automl/comparison")
    if comparison:
        log("Cross-framework comparison data available in dashboard")

    n_completed = sum(1 for r in all_results if r.get('status') == 'completed')
    n_skipped = sum(1 for r in all_results if r.get('status') == 'skipped')
    n_resumed = sum(1 for r in all_results if r.get('status') == 'skipped_resume')
    n_failed = sum(1 for r in all_results if r.get('status') in ('error', 'cancelled'))

    print(f"""
    ==============================================================
      All data saved in experiments/exp_* directories.

      Open the dashboard to view hypothesis charts:
        http://localhost:5173

      Use the Hypothesis tab filters to compare:
        - Simulation Mode: deterministic / medium / realistic
        - AutoML Framework: H2O / AutoGluon / PyCaret / TPOT / auto-sklearn

      Experiment Summary:
        ML Framework experiments: {n_framework_exps}
        Baseline experiments:     {n_baseline_exps if not skip_baselines else 'skipped'}
        LLM experiments:          {n_llm_exps if not skip_llm else 'skipped'}
        LOPO evaluations:         {len(lopo_results)} completed

      Results:
        Total: {len(all_results)} | Completed: {n_completed} | Previously done: {n_resumed} | Skipped: {n_skipped} | Failed: {n_failed}

      New Hypotheses Available:
        H8: Temporal Predictive Validity
        H9: ML Value Over Baselines
        H10: LLM Generation Effectiveness
        H11: Cross-Protocol Generalization (LOPO)
    ==============================================================
    """)


if __name__ == "__main__":
    main()
