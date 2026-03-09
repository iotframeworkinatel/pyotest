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

API = "http://localhost:8000"
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

# AutoML frameworks to evaluate
AUTOML_FRAMEWORKS = ["h2o", "autogluon", "pycaret", "tpot", "autosklearn"]

# Simulation mode definitions: (base_name, simulation_mode, seed, iterations, train_every_n)
SIM_MODES = [
    ("CTRL-DET-100",   "deterministic", 42, 100, 10),
    ("TREAT-MED-100",  "medium",        42, 100, 10),
    ("TREAT-REAL-100", "realistic",     42, 100, 10),
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

def clear_experiment_data():
    """Remove all old experiment data for a clean start."""
    log("Clearing old experiment data...")

    # Clear experiment directories (but keep backups)
    for d in glob.glob(os.path.join(EXPERIMENTS_DIR, "exp_*")):
        shutil.rmtree(d, ignore_errors=True)
        log(f"  Removed {os.path.basename(d)}")

    # Clear aggregated history files
    for agg_name in glob.glob(os.path.join(EXPERIMENTS_DIR, "aggregated_history*.csv")):
        os.remove(agg_name)
        log(f"  Removed {os.path.basename(agg_name)}")

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

def run_experiment(suite_id, name, mode, seed, iterations, train_every_n, automl_tool="h2o"):
    """
    Start a train-loop experiment and poll until completion.
    Returns a dict of final metrics.
    """
    fw_label = FRAMEWORK_LABELS.get(automl_tool, automl_tool)
    log(f"{'=' * 70}")
    log(f"STARTING EXPERIMENT: {name}")
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
        status = api_get(f"/api/suites/{suite_id}/train-loop/status")
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

    # Restart all IoT containers via docker compose
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "compose", "restart"] + IOT_CONTAINERS,
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log(f"  Restarted {len(IOT_CONTAINERS)} IoT containers")
        else:
            log(f"  docker compose restart failed: {result.stderr[:200]}", "WARN")
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
    """
    src = os.path.join(MODELS_DIR, automl_tool)
    if not os.path.exists(src):
        log(f"  No model to archive for {automl_tool} ({sim_mode})")
        return

    dest = os.path.join(MODELS_ARCHIVE_DIR, f"{automl_tool}_{sim_mode}")
    os.makedirs(MODELS_ARCHIVE_DIR, exist_ok=True)

    # Remove previous archive for this combo (re-run safety)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)

    shutil.copytree(src, dest)
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
# Main
# ----------------------------------------------------------------------

def main():
    total_start = time.time()

    total_experiments = len(AUTOML_FRAMEWORKS) * len(SIM_MODES)
    est_hours = total_experiments * 100 * 2.5 / 60 / 60  # rough: ~2.5 min per iteration

    print(f"""
    ==============================================================
      Emergence - Multi-Framework PhD Experiment Runner

      {len(AUTOML_FRAMEWORKS)} frameworks x {len(SIM_MODES)} modes x 100 iterations = {total_experiments} experiments
      Frameworks: {', '.join(FRAMEWORK_LABELS[fw] for fw in AUTOML_FRAMEWORKS)}
      Modes: deterministic -> medium -> realistic
      Estimated duration: ~{est_hours:.0f} hours
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

    # Step 1: Clear everything
    clear_experiment_data()

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
    for fw in AUTOML_FRAMEWORKS:
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

        for mode_idx, (base_name, mode, seed, iters, train_n) in enumerate(SIM_MODES):
            experiment_num += 1
            experiment_name = f"{base_name}-{fw.upper()}"

            log(f"\n{'=' * 70}")
            log(f"EXPERIMENT {experiment_num}/{total_experiments}: {experiment_name}")
            log(f"  Framework: {fw_label} | Mode: {mode}")
            log(f"{'=' * 70}")

            result = run_experiment(suite_id, experiment_name, mode, seed, iters, train_n, automl_tool=fw)
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

    # -- Summary ---------------------------------------------------
    total_duration = time.time() - total_start
    log(f"\nAll experiments completed in {format_duration(total_duration)}")
    print_summary(all_results)

    # Fetch cross-framework statistical comparison
    log("\nFetching cross-framework statistical comparison...")
    comparison = api_get("/api/automl/comparison")
    if comparison:
        log("Cross-framework comparison data available in dashboard")

    print(f"""
    ==============================================================
      All data saved in experiments/exp_* directories.

      Open the dashboard to view hypothesis charts:
        http://localhost:5173

      Use the Hypothesis tab filters to compare:
        - Simulation Mode: deterministic / medium / realistic
        - AutoML Framework: H2O / AutoGluon / PyCaret / TPOT / auto-sklearn

      Each framework × mode combination is fully isolated.
      Total experiments: {len(all_results)}
      Completed: {sum(1 for r in all_results if r.get('status') == 'completed')}
      Skipped:   {sum(1 for r in all_results if r.get('status') == 'skipped')}
      Failed:    {sum(1 for r in all_results if r.get('status') in ('error', 'cancelled'))}
    ==============================================================
    """)


if __name__ == "__main__":
    main()
