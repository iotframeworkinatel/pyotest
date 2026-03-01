"""
Environment Simulator — the main simulation engine.

Controls the dynamic behavior of Docker containers between training iterations.
All decisions are probability-based Bernoulli trials seeded for reproducibility.

Usage:
    simulator = EnvironmentSimulator(config, docker_client)
    for i in range(1, iterations + 1):
        simulator.prepare_iteration(i)   # Roll dice, apply changes
        run_tests(...)                    # Tests hit modified containers
        simulator.restore_iteration(i)   # Bring outaged devices back online
    simulator.cleanup()                  # Full reset to original state
"""
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Optional

from simulation.config import SimulationConfig
from simulation.actions import (
    IOT_DEVICES,
    PATCHABLE_VULNS,
    ROTATABLE_CREDS,
    stop_container,
    start_container,
    apply_patch,
    apply_unpatch,
    rotate_credentials,
    reset_credentials,
)

logger = logging.getLogger("simulation.environment")

# Default path for state.json (shared volume readable by custom servers)
STATE_JSON_PATH = os.environ.get(
    "SIMULATION_STATE_PATH",
    "/app/simulation/state.json",
)


class EnvironmentSimulator:
    """Probability-driven dynamic environment simulator.

    Between training iterations, this class:
    1. Rolls RNG per device → may stop container (service outage)
    2. Rolls RNG per active vulnerability → may patch via docker exec
    3. Rolls RNG per patched vulnerability → may regress (unpatch)
    4. Rolls RNG per auth-based container → may rotate credentials
    5. Writes state.json for custom Python servers to read

    All random decisions use a deterministic RNG seeded from
    (config.seed + iteration * prime), so the same seed always
    produces the same sequence of events.
    """

    def __init__(self, config: SimulationConfig, docker_client=None):
        """Initialize the simulator.

        Args:
            config: SimulationConfig with probability parameters.
            docker_client: Docker client instance (docker.from_env()).
                           Can be None for dry-run / testing.
        """
        self.config = config
        self.docker = docker_client

        # ── Tracking state ──
        self._stopped_containers: set[str] = set()
        self._patched_vulns: dict[tuple[str, str], int] = {}  # key → patched_at_iteration
        self._rotated_creds: dict[str, str] = {}  # container → current_password
        self._iteration_log: list[dict] = []
        self._start_time: Optional[float] = None

    def prepare_iteration(self, iteration: int) -> list[dict]:
        """Roll the dice for each device/vuln/cred. Apply changes via Docker.

        This is called BEFORE test execution each iteration. The containers
        are physically modified — services may be down, files moved, passwords
        changed, configs altered.

        Args:
            iteration: Current iteration number (1-based).

        Returns:
            List of action dicts describing what happened this iteration.
        """
        if not self.config.is_active():
            return []

        if self._start_time is None:
            self._start_time = time.time()

        # Deterministic RNG for this iteration
        # Using a large prime multiplier ensures independence between iterations
        rng = random.Random(self.config.seed + iteration * 7919)
        actions = []

        logger.info(
            f"[Simulation] ── Iteration {iteration} ── "
            f"mode={self.config.mode} seed={self.config.seed}"
        )

        # 1. Service outages — roll per device
        outage_actions = self._roll_service_outages(rng, iteration)
        actions.extend(outage_actions)

        # 2. Vulnerability patches — roll per active (unpatched) vulnerability
        patch_actions = self._roll_vulnerability_patches(rng, iteration)
        actions.extend(patch_actions)

        # 3. Patch regressions — roll per already-patched vulnerability
        regression_actions = self._roll_patch_regressions(rng, iteration)
        actions.extend(regression_actions)

        # 4. Credential rotations — roll per auth-based container
        cred_actions = self._roll_credential_rotations(rng, iteration)
        actions.extend(cred_actions)

        # 5. Write state.json for custom Python servers
        self._write_state_json(iteration, rng)

        # Log this iteration
        entry = {
            "iteration": iteration,
            "timestamp": datetime.utcnow().isoformat(),
            "actions": actions,
            "state": {
                "stopped_containers": list(self._stopped_containers),
                "patched_vulns": [
                    {"container": k[0], "vuln_id": k[1], "patched_at": v}
                    for k, v in self._patched_vulns.items()
                ],
                "rotated_creds": list(self._rotated_creds.keys()),
            },
        }
        self._iteration_log.append(entry)

        if actions:
            logger.info(
                f"[Simulation] Iteration {iteration}: {len(actions)} actions fired — "
                + ", ".join(f"{a['type']}({a.get('container', a.get('device', '?'))})" for a in actions)
            )
        else:
            logger.info(f"[Simulation] Iteration {iteration}: no random events fired")

        return actions

    def restore_iteration(self, iteration: int) -> None:
        """Restart containers that were stopped for this iteration.

        Called AFTER test execution. Outaged containers are brought back online.
        Patches and credential changes PERSIST across iterations (they are
        cumulative until regression rolls reverse them).

        Args:
            iteration: Current iteration number (1-based).
        """
        if not self.config.is_active():
            return

        if not self._stopped_containers:
            return

        logger.info(
            f"[Simulation] Restoring {len(self._stopped_containers)} "
            f"stopped containers after iteration {iteration}"
        )

        for container_name in list(self._stopped_containers):
            if self.docker:
                start_container(self.docker, container_name)

        self._stopped_containers.clear()

        # Brief pause for services to come back up
        time.sleep(2)

    def cleanup(self) -> None:
        """Full reset — restore ALL containers to original state.

        Call this when the training loop finishes to undo all patches,
        credential rotations, and restart any stopped containers.
        """
        if not self.config.is_active():
            return

        logger.info("[Simulation] Full cleanup — restoring all containers to original state")

        # 1. Restart any stopped containers
        for container_name in list(self._stopped_containers):
            if self.docker:
                start_container(self.docker, container_name)
        self._stopped_containers.clear()

        # 2. Reverse all patches
        for (container_name, vuln_id) in list(self._patched_vulns.keys()):
            if self.docker:
                apply_unpatch(self.docker, container_name, vuln_id)
        self._patched_vulns.clear()

        # 3. Reset all credentials to defaults
        for container_name in list(self._rotated_creds.keys()):
            if self.docker:
                reset_credentials(self.docker, container_name)
        self._rotated_creds.clear()

        # 4. Clean up state.json
        self._remove_state_json()

        logger.info("[Simulation] Cleanup complete — all containers restored")

    def get_log(self) -> list[dict]:
        """Return the full iteration-by-iteration action log."""
        return self._iteration_log

    def get_summary(self) -> dict:
        """Return a summary of the simulation run."""
        total_actions = sum(len(e["actions"]) for e in self._iteration_log)
        action_types = {}
        for entry in self._iteration_log:
            for action in entry["actions"]:
                t = action["type"]
                action_types[t] = action_types.get(t, 0) + 1

        return {
            "mode": self.config.mode,
            "seed": self.config.seed,
            "iterations_completed": len(self._iteration_log),
            "total_actions": total_actions,
            "action_breakdown": action_types,
            "currently_patched": [
                {"container": k[0], "vuln_id": k[1], "since_iteration": v}
                for k, v in self._patched_vulns.items()
            ],
            "currently_rotated": list(self._rotated_creds.keys()),
            "elapsed_seconds": (
                round(time.time() - self._start_time, 1)
                if self._start_time else 0
            ),
        }

    # ── Private: probability roll methods ──

    def _roll_service_outages(self, rng: random.Random, iteration: int) -> list[dict]:
        """Roll per-device probability for service outage."""
        actions = []
        online_count = len(IOT_DEVICES) - len(self._stopped_containers)

        for device in IOT_DEVICES:
            if device in self._stopped_containers:
                continue
            if online_count <= self.config.min_devices_online:
                break
            if rng.random() < self.config.service_outage_prob:
                if self.docker:
                    stop_container(self.docker, device)
                self._stopped_containers.add(device)
                online_count -= 1
                actions.append({
                    "type": "outage",
                    "device": device,
                    "iteration": iteration,
                })
                logger.info(f"[Simulation] 🔴 Service outage: {device}")

        return actions

    def _roll_vulnerability_patches(self, rng: random.Random, iteration: int) -> list[dict]:
        """Roll per-vulnerability probability for patching."""
        actions = []
        patches_this_iter = 0

        for (container, vuln_id) in PATCHABLE_VULNS:
            # Skip already-patched vulns
            if (container, vuln_id) in self._patched_vulns:
                continue
            # Skip if container is currently stopped
            if container in self._stopped_containers:
                continue
            # Respect max patches per iteration
            if patches_this_iter >= self.config.max_patches_per_iter:
                break
            if rng.random() < self.config.vuln_patch_prob:
                if self.docker:
                    apply_patch(self.docker, container, vuln_id)
                self._patched_vulns[(container, vuln_id)] = iteration
                patches_this_iter += 1
                actions.append({
                    "type": "patch",
                    "container": container,
                    "vuln_id": vuln_id,
                    "iteration": iteration,
                    "description": PATCHABLE_VULNS[(container, vuln_id)]["description"],
                })
                logger.info(f"[Simulation] 🩹 Patched: {container}/{vuln_id}")

        return actions

    def _roll_patch_regressions(self, rng: random.Random, iteration: int) -> list[dict]:
        """Roll per-patched-vulnerability probability for regression."""
        actions = []

        for key in list(self._patched_vulns.keys()):
            container, vuln_id = key
            # Skip if container is currently stopped
            if container in self._stopped_containers:
                continue
            if rng.random() < self.config.patch_regression_prob:
                if self.docker:
                    apply_unpatch(self.docker, container, vuln_id)
                del self._patched_vulns[key]
                actions.append({
                    "type": "regression",
                    "container": container,
                    "vuln_id": vuln_id,
                    "iteration": iteration,
                    "description": f"Regression (rollback) of {vuln_id}",
                })
                logger.info(f"[Simulation] 🔄 Regression: {container}/{vuln_id}")

        return actions

    def _roll_credential_rotations(self, rng: random.Random, iteration: int) -> list[dict]:
        """Roll per-container probability for credential rotation."""
        actions = []

        for container_name in ROTATABLE_CREDS:
            # Skip if container is currently stopped
            if container_name in self._stopped_containers:
                continue
            if rng.random() < self.config.credential_rotation_prob:
                new_pass = f"sim_{rng.randint(1000, 9999)}"
                if self.docker:
                    rotate_credentials(self.docker, container_name, new_pass)
                self._rotated_creds[container_name] = new_pass
                actions.append({
                    "type": "cred_rotation",
                    "container": container_name,
                    "iteration": iteration,
                    "description": f"Credentials rotated on {container_name}",
                })
                logger.info(f"[Simulation] 🔑 Credential rotation: {container_name}")

        return actions

    def _write_state_json(self, iteration: int, rng: random.Random) -> None:
        """Write simulation state to state.json for custom servers to read.

        Custom Python servers (http_api_vuln, http_admin_default_creds,
        coap_vuln, modbus_vuln) can optionally read this file to adjust
        their behavior per-request — e.g., toggling probabilistic endpoints,
        overriding register values, etc.
        """
        state = {
            "mode": self.config.mode,
            "seed": self.config.seed,
            "iteration": iteration,
            "false_positive_rate": self.config.false_positive_rate,
            "false_negative_rate": self.config.false_negative_rate,
            "stopped_containers": list(self._stopped_containers),
            "patched_vulns": {
                f"{k[0]}:{k[1]}": v for k, v in self._patched_vulns.items()
            },
            "rotated_creds": {
                k: v for k, v in self._rotated_creds.items()
            },
            # Per-request behavior overrides for custom servers
            "overrides": {
                "http_api_vuln": {
                    "debug_enabled": rng.random() > 0.3,  # 70% chance debug is on
                    "api_key_changed": "http_api_vuln" in self._rotated_creds,
                },
                "http_admin_default_creds": {
                    "admin_enabled": ("http_admin_default_creds", "http_admin_unprotected")
                    not in self._patched_vulns,
                },
                "coap_vuln": {
                    "secret_visible": ("coap_vuln", "coap_hidden_resources")
                    not in self._patched_vulns,
                    "config_writable": ("coap_vuln", "coap_writable_config")
                    not in self._patched_vulns,
                },
                "modbus_vuln": {
                    # Randomize register values each iteration
                    "holding_registers": [
                        rng.randint(0, 999) for _ in range(3)
                    ],
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            state_dir = os.path.dirname(STATE_JSON_PATH)
            if state_dir:
                os.makedirs(state_dir, exist_ok=True)
            with open(STATE_JSON_PATH, "w") as f:
                json.dump(state, f, indent=2)
            logger.debug(f"[Simulation] Wrote state.json for iteration {iteration}")
        except Exception as e:
            logger.warning(f"[Simulation] Could not write state.json: {e}")

    def _remove_state_json(self) -> None:
        """Remove the state.json file during cleanup."""
        try:
            if os.path.exists(STATE_JSON_PATH):
                os.remove(STATE_JSON_PATH)
                logger.debug("[Simulation] Removed state.json")
        except Exception as e:
            logger.warning(f"[Simulation] Could not remove state.json: {e}")
