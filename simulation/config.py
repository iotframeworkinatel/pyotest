"""
Simulation Configuration — probability-based parameters for environment dynamics.

All probabilities are per-iteration, per-entity rolls. No fixed schedules.
Same seed + same iteration = same outcome (fully reproducible).
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class SimulationConfig:
    """Configuration for the environment simulation layer.

    All probabilities are independent Bernoulli trials rolled each iteration:
      - service_outage_prob: P(a given device goes offline this iteration)
      - vuln_patch_prob: P(an active vulnerability gets patched this iteration)
      - credential_rotation_prob: P(credentials rotate on a device this iteration)
      - patch_regression_prob: P(a previously patched vuln reappears this iteration)
      - false_positive_rate: P(a non-vulnerable test falsely reports a vulnerability)
      - false_negative_rate: P(a real vulnerability is missed by the test)
    """

    # ── Mode & reproducibility ──
    mode: str = "deterministic"
    seed: int = 42

    # ── Per-iteration probabilities ──
    service_outage_prob: float = 0.0
    vuln_patch_prob: float = 0.0
    credential_rotation_prob: float = 0.0
    patch_regression_prob: float = 0.0

    # ── Detection noise ──
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0

    # ── Safety constraints ──
    min_devices_online: int = 8       # Never take more than 5 of 13 devices offline
    max_patches_per_iter: int = 2     # Don't patch too many vulns at once

    def is_active(self) -> bool:
        """Return True if simulation is anything other than deterministic baseline."""
        return self.mode != "deterministic"

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationConfig":
        """Create from a dict, ignoring unknown keys."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def load_config(path: str) -> Optional[SimulationConfig]:
    """Load a SimulationConfig from a JSON file. Returns None if file missing."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return SimulationConfig.from_dict(data)


def save_config(config: SimulationConfig, path: str) -> None:
    """Save a SimulationConfig to a JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
