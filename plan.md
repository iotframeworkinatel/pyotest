# Plan: Environment Simulation Layer for Realistic IoT Testing

## Problem
The 13 Docker containers have **fixed, deterministic vulnerabilities**. The ML pipeline memorizes them in 3-5 iterations, making hypothesis validation trivially achievable and not defensible for a PhD thesis in a realistic setting.

## Solution: Container-Level Dynamic Environment Simulation
A simulation layer that **manipulates actual containers** between training loop iterations — stopping/starting services, rotating credentials, patching vulnerabilities via `docker exec`, and modifying custom server behavior via a shared config volume. All events are **probability-driven** (not scheduled at fixed iterations), so the ML model cannot predict when changes happen — it must genuinely adapt.

---

## Architecture Overview

```
dashboard-api (_do_loop):
  ┌─────────────────────────────────────────────────┐
  │ for i in 1..N:                                  │
  │   simulator.prepare_iteration(i)                │
  │     ├─ roll RNG per device → docker stop?       │
  │     ├─ roll RNG per vuln → docker exec patch?   │
  │     ├─ roll RNG per cred → docker exec rotate?  │
  │     ├─ roll RNG per patch → regress (unpatch)?  │
  │     └─ write /simulation/state.json             │
  │                                                 │
  │   _execute_suite_and_retrain(suite)              │
  │     └─ scanner runs pytest against containers   │
  │        (containers are now in modified state)   │
  │                                                 │
  │   simulator.restore_iteration(i)                │
  │     └─ docker start (restore outaged devices)   │
  │     (patches + credential changes PERSIST)      │
  └─────────────────────────────────────────────────┘
```

### How each behavior works at the container level:

| Behavior | Mechanism | Containers | Triggered by |
|----------|-----------|------------|-------------|
| **Service outage** | `docker stop/start` — container is actually unreachable | ALL 13 | Random roll each iteration |
| **Vulnerability patch** | `docker exec` — remove files, change configs, disable endpoints | HTTP, MQTT, FTP, DNS | Random roll each iteration (once patched, stays patched unless regression) |
| **Credential rotation** | `docker exec` — change passwords, disable users | telnet, FTP, HTTP admin | Random roll each iteration |
| **Patch regression** | `docker exec` — reverse a previous patch | Previously patched containers | Random roll each iteration (only for already-patched vulns) |
| **Probabilistic endpoints** | Custom servers read `/simulation/state.json` per-request | HTTP API, CoAP, Modbus, Flask admin | State file updated each iteration with RNG-driven overrides |
| **FP/FN noise** | Thin result-level layer in suite_runner (~15 lines) | All | Per-test RNG roll |

---

## New Files

### `simulation/__init__.py`
Empty init.

### `simulation/config.py`
`SimulationConfig` dataclass — all **probability-based**, no fixed schedules:

```python
@dataclass
class SimulationConfig:
    mode: str = "deterministic"
    seed: int = 42

    # ── Per-iteration probabilities ──
    service_outage_prob: float = 0.0      # P(device goes down this iteration)
    vuln_patch_prob: float = 0.0          # P(an active vuln gets patched this iteration)
    credential_rotation_prob: float = 0.0 # P(credentials rotate on a device this iteration)
    patch_regression_prob: float = 0.0    # P(a patched vuln reappears this iteration)

    # ── Detection noise ──
    false_positive_rate: float = 0.0      # P(non-vuln test reports vuln)
    false_negative_rate: float = 0.0      # P(real vuln test misses it)

    # ── Constraints ──
    min_devices_online: int = 8           # Never take more than 5 of 13 devices offline
    max_patches_per_iter: int = 2         # Don't patch too many vulns at once
```

Also: `load_config(path)` / `save_config(config, path)` for JSON serialization.

### `simulation/profiles.py`
5 named presets, each returns a `SimulationConfig`. All purely probability-driven:

| Profile | Outage | Patch | Cred Rotation | Regression | FP | FN | Purpose |
|---------|--------|-------|---------------|------------|----|----|---------|
| `deterministic` | 0% | 0% | 0% | 0% | 0% | 0% | Baseline (current behavior) |
| `easy` | 5% | 0% | 0% | 0% | 1% | 3% | Minor noise only |
| `medium` | 8% | 3% | 3% | 5% | 1% | 5% | Moderate challenge |
| `hard` | 15% | 8% | 8% | 10% | 3% | 10% | Stress test |
| `realistic` | 8% | 5% | 5% | 10% | 1% | 5% | PhD thesis primary |

**How the `realistic` profile plays out (probabilistically):**
- Each iteration, ~1 of 13 devices may go offline (8% × 13 ≈ 1)
- Each iteration, there's a chance 0-2 vulnerabilities get patched across the lab
- Previously patched vulns have a 10% chance of regressing (firmware rollback)
- Credentials on auth-based containers may randomly rotate
- The exact timing is unpredictable — controlled only by seed
- Over 20 iterations, the environment evolves naturally without any hardcoded schedule

### `simulation/actions.py`
Docker manipulation functions (called by EnvironmentSimulator):

```python
# Container lifecycle
def stop_container(docker_client, container_name) -> bool
def start_container(docker_client, container_name) -> bool
def exec_in_container(docker_client, container_name, cmd) -> str

# Patchable vulnerabilities registry — maps (container, vuln_id) to patch/unpatch commands
PATCHABLE_VULNS = {
    ("http_traversal", "http_sensitive_files"): {
        "patch": "mv /usr/local/apache2/htdocs/.env /usr/local/apache2/htdocs/.env.patched",
        "unpatch": "mv /usr/local/apache2/htdocs/.env.patched /usr/local/apache2/htdocs/.env",
    },
    ("mqtt_no_auth", "mqtt_open_access"): {
        "patch": "sed -i 's/allow_anonymous true/allow_anonymous false/' /mosquitto/config/mosquitto.conf && kill -HUP 1",
        "unpatch": "sed -i 's/allow_anonymous false/allow_anonymous true/' /mosquitto/config/mosquitto.conf && kill -HUP 1",
    },
    ("ftp_anonymous", "ftp_anonymous_login"): {
        "patch": "echo 'anonymous_enable=NO' >> /etc/vsftpd/vsftpd.conf && kill -HUP 1",
        "unpatch": "sed -i '/anonymous_enable=NO/d' /etc/vsftpd/vsftpd.conf && kill -HUP 1",
    },
    # ... more entries for each patchable vulnerability
}

# Rotatable credentials registry
ROTATABLE_CREDS = {
    "telnet_insecure": {
        "rotate": "echo 'admin:{new_pass}' | chpasswd",
        "users": ["admin", "root"],
    },
    "http_admin_default_creds": {
        "rotate": "echo 'ADMIN_PASS={new_pass}' > /app/.sim_override",
    },
    # ...
}
```

### `simulation/environment.py`
Main `EnvironmentSimulator` class — all decisions are probability rolls:

```python
class EnvironmentSimulator:
    def __init__(self, config: SimulationConfig, docker_client):
        self.config = config
        self.docker = docker_client
        self._stopped_containers = set()
        self._patched_vulns = {}       # {(container, vuln_id): patched_at_iter}
        self._rotated_creds = {}       # {container: current_password}
        self._iteration_log = []

    def prepare_iteration(self, iteration: int):
        """Roll the dice for each device/vuln/cred. Apply changes via Docker."""
        if self.config.mode == "deterministic":
            return

        # Deterministic RNG for this iteration (same seed+iter = same outcome)
        rng = random.Random(self.config.seed + iteration * 7919)
        actions = []

        # 1. Service outages — roll per device
        online_count = len(IOT_DEVICES) - len(self._stopped_containers)
        for device in IOT_DEVICES:
            if device in self._stopped_containers:
                continue
            if online_count <= self.config.min_devices_online:
                break
            if rng.random() < self.config.service_outage_prob:
                stop_container(self.docker, device)
                self._stopped_containers.add(device)
                online_count -= 1
                actions.append({"type": "outage", "device": device})

        # 2. Vulnerability patches — roll per active (unpatched) vuln
        patches_this_iter = 0
        for (container, vuln_id), cmds in PATCHABLE_VULNS.items():
            if (container, vuln_id) in self._patched_vulns:
                continue
            if patches_this_iter >= self.config.max_patches_per_iter:
                break
            if rng.random() < self.config.vuln_patch_prob:
                exec_in_container(self.docker, container, cmds["patch"])
                self._patched_vulns[(container, vuln_id)] = iteration
                patches_this_iter += 1
                actions.append({"type": "patch", "container": container, "vuln": vuln_id})

        # 3. Patch regression — roll per patched vuln
        for key in list(self._patched_vulns.keys()):
            if rng.random() < self.config.patch_regression_prob:
                cmds = PATCHABLE_VULNS[key]
                exec_in_container(self.docker, key[0], cmds["unpatch"])
                del self._patched_vulns[key]
                actions.append({"type": "regression", "container": key[0], "vuln": key[1]})

        # 4. Credential rotations — roll per rotatable container
        for container, cred_info in ROTATABLE_CREDS.items():
            if rng.random() < self.config.credential_rotation_prob:
                new_pass = f"sim_{rng.randint(1000,9999)}"
                cmd = cred_info["rotate"].format(new_pass=new_pass)
                exec_in_container(self.docker, container, cmd)
                self._rotated_creds[container] = new_pass
                actions.append({"type": "cred_rotation", "container": container})

        # 5. Write state.json for custom Python servers
        self._write_state_json(iteration, rng)

        self._iteration_log.append({"iteration": iteration, "actions": actions})

    def restore_iteration(self, iteration: int):
        """Restart outaged containers (patches + cred changes persist)."""
        for container in list(self._stopped_containers):
            start_container(self.docker, container)
        self._stopped_containers.clear()
```

---

## Modified Files

### 1. `docker-compose.yml` — Add simulation volume mount
Add `./simulation:/app/simulation` to:
- `scanner` volumes
- `dashboard-api` volumes
- `http_api_vuln` volumes (custom Python server)
- `http_admin_default_creds` volumes (Flask server)
- `coap_vuln` volumes
- `modbus_vuln` volumes

### 2. `dashboard/backend/main.py` — Training loop integration

**`TrainLoopRequest`** model: add `simulation_mode` and `simulation_seed` fields.

**`_do_loop()`**: Create `EnvironmentSimulator` from config. Before each iteration call `simulator.prepare_iteration(i)`, after call `simulator.restore_iteration(i)`.

**New endpoints:**
- `GET /api/simulation/profiles` — list available presets with parameter descriptions
- `GET /api/simulation/active` — current simulation config
- `POST /api/simulation/configure` — set custom JSON config
- `GET /api/simulation/log` — iteration-by-iteration action log (what events fired)

### 3. `utils/suite_runner.py` — Thin FP/FN noise layer
In `_map_results_to_test_cases()`, after `vuln_found = status == "PASSED"` (line 246):
```python
# Apply FP/FN noise from simulation (if active)
sim_state = _load_simulation_state()
if sim_state and sim_state.get("mode") != "deterministic":
    fp_rate = sim_state.get("false_positive_rate", 0)
    fn_rate = sim_state.get("false_negative_rate", 0)
    rng = random.Random(sim_state["seed"] + hash(tc.test_id) + sim_state["iteration"])
    if vuln_found and rng.random() < fn_rate:
        vuln_found = False
    elif not vuln_found and rng.random() < fp_rate:
        vuln_found = True
```
~15 lines of change.

### 4. `history/history_builder.py` — Add simulation columns
Add `"simulation_mode"` and `"simulation_iteration"` to `COLUMNS` list. Backward-compatible.

### 5. `automl/dataset.py` — Blind the ML model
Add `"simulation_mode"` and `"simulation_iteration"` to `DROP_COLS`.

### 6. Custom Python servers — Read simulation state
Modify 4 custom servers to optionally read `/app/simulation/state.json`:
- **`emergence/devices/http-api-vuln/server.py`**: Check overrides for `debug_enabled`, `api_key`
- **`emergence/devices/app-admin-panel/app.py`**: Check for credential overrides, endpoint toggles
- **`emergence/devices/coap/server.py`**: Check for resource visibility/writability
- **`emergence/devices/modbustcp/server.py`**: Check for register value overrides

Each adds ~10 lines to read the state file.

### 7. `dashboard/frontend/src/components/TestSuites.jsx` — Simulation mode selector
Add dropdown and seed input next to Auto-Train controls:
```
Auto-Train: [3] iterations  Mode: [Realistic ▾]  Seed: [42]
```

---

## Implementation Phases

### Phase 1: Core Simulation Engine
1. Create `simulation/__init__.py`, `config.py`, `profiles.py`
2. Create `simulation/actions.py` — PATCHABLE_VULNS and ROTATABLE_CREDS registries + Docker manipulation functions
3. Create `simulation/environment.py` — EnvironmentSimulator with probability-based prepare/restore

### Phase 2: Training Loop Integration
4. Modify `docker-compose.yml` — add simulation volume mounts
5. Modify `main.py` — extend TrainLoopRequest, integrate simulator into `_do_loop()`
6. Add `/api/simulation/*` endpoints
7. Modify `suite_runner.py` — add FP/FN noise layer (~15 lines)
8. Modify `history_builder.py` — add 2 columns
9. Modify `dataset.py` — add 2 columns to DROP_COLS

### Phase 3: Custom Server Modifications
10. Modify `http-api-vuln/server.py` — read simulation state
11. Modify `app-admin-panel/app.py` — read simulation state
12. Modify `coap/server.py` — read simulation state
13. Modify `modbustcp/server.py` — read simulation state

### Phase 4: Frontend UI
14. Modify `TestSuites.jsx` — add simulation mode dropdown and seed input

### Phase 5: Validation
15. Run deterministic baseline (2 iterations) — confirm no regression
16. Run realistic profile (3 iterations) — verify random events fire
17. Compare hypothesis outputs between modes

---

## Academic Defensibility

**Why this approach is valid for thesis:**
1. **Real container changes**: Tests hit real Docker containers whose state has genuinely changed (services down, files removed, passwords changed). No fake results.
2. **Grounded in IoT research**: Service intermittency, firmware patching, credential rotation are all documented real-world IoT phenomena.
3. **Reproducible**: Same seed = identical sequence of random events. Different seed = completely different scenario.
4. **Unpredictable to ML**: All events are probability-driven — no fixed schedule the model could learn. It must genuinely adapt.
5. **Comparable**: Deterministic baseline as control vs realistic as treatment.
6. **Only FP/FN noise is result-level** (~1-5%), standard in security scanner literature.

**Expected behavior with `realistic` profile over 20 iterations:**
- The vulnerability landscape randomly shifts each iteration
- Some iterations several devices go down, others none
- Patches accumulate probabilistically, occasionally regressing
- The ML model must continuously adapt rather than memorize
- Convergence takes 15-20+ iterations vs 3-5 in deterministic mode
- This produces a meaningful, statistically testable learning curve
