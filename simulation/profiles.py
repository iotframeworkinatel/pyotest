"""
Simulation Profiles — named presets for common experiment scenarios.

Each profile returns a SimulationConfig with probability-based parameters.
No fixed schedules — all events are Bernoulli trials per iteration.
"""
from simulation.config import SimulationConfig


# ── Profile definitions ──

PROFILES = {
    "deterministic": {
        "description": "Baseline — no simulation. Containers stay exactly as built.",
        "academic_use": "Control group for hypothesis comparison.",
        "config": {
            "mode": "deterministic",
            "service_outage_prob": 0.0,
            "vuln_patch_prob": 0.0,
            "credential_rotation_prob": 0.0,
            "patch_regression_prob": 0.0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
        },
    },
    "easy": {
        "description": "Minor noise — occasional outages and slight detection error.",
        "academic_use": "Sensitivity analysis: does the pipeline degrade with minimal noise?",
        "config": {
            "mode": "easy",
            "service_outage_prob": 0.05,
            "vuln_patch_prob": 0.0,
            "credential_rotation_prob": 0.0,
            "patch_regression_prob": 0.0,
            "false_positive_rate": 0.01,
            "false_negative_rate": 0.03,
        },
    },
    "medium": {
        "description": "Moderate challenge — patches, rotations, and outages all active.",
        "academic_use": "Mid-range difficulty for learning curve comparison.",
        "config": {
            "mode": "medium",
            "service_outage_prob": 0.08,
            "vuln_patch_prob": 0.03,
            "credential_rotation_prob": 0.03,
            "patch_regression_prob": 0.05,
            "false_positive_rate": 0.01,
            "false_negative_rate": 0.05,
        },
    },
    "hard": {
        "description": "Stress test — high churn, frequent patches and rotations.",
        "academic_use": "Upper bound testing: at what noise level does the pipeline break down?",
        "config": {
            "mode": "hard",
            "service_outage_prob": 0.15,
            "vuln_patch_prob": 0.08,
            "credential_rotation_prob": 0.08,
            "patch_regression_prob": 0.10,
            "false_positive_rate": 0.03,
            "false_negative_rate": 0.10,
        },
    },
    "realistic": {
        "description": (
            "PhD thesis primary profile — models real-world IoT lab dynamics. "
            "~1 device may go offline per iteration, vulnerabilities are occasionally "
            "patched with possible regression (firmware rollback), credentials rotate "
            "on auth-based services. Detection noise at literature-standard levels."
        ),
        "academic_use": (
            "Primary treatment group. Produces a meaningful, statistically testable "
            "learning curve over 15-20+ iterations."
        ),
        "config": {
            "mode": "realistic",
            "service_outage_prob": 0.08,
            "vuln_patch_prob": 0.05,
            "credential_rotation_prob": 0.05,
            "patch_regression_prob": 0.10,
            "false_positive_rate": 0.01,
            "false_negative_rate": 0.05,
        },
    },
}


def get_profile(name: str) -> SimulationConfig:
    """Get a SimulationConfig from a named profile.

    Args:
        name: Profile name (deterministic, easy, medium, hard, realistic).

    Returns:
        SimulationConfig with the preset parameters.

    Raises:
        ValueError: If the profile name is unknown.
    """
    if name not in PROFILES:
        valid = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown profile '{name}'. Valid profiles: {valid}")

    profile = PROFILES[name]
    return SimulationConfig(**profile["config"])


def list_profiles() -> list[dict]:
    """List all available profiles with their descriptions and parameters.

    Returns:
        List of dicts with name, description, academic_use, and config for each profile.
    """
    result = []
    for name, profile in PROFILES.items():
        result.append({
            "name": name,
            "description": profile["description"],
            "academic_use": profile["academic_use"],
            "config": profile["config"],
        })
    return result
