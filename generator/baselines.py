"""
Baseline Test Selection Strategies

Non-ML baselines for quantifying ML value-add in test case prioritization.
Each baseline implements a different selection strategy:

- RandomBaseline: Randomly select k tests (seeded for reproducibility)
- CVSSPriorityBaseline: Prioritize by severity (critical → high → medium → low → info)
- RoundRobinBaseline: Equal allocation per protocol, then cycle
- NoMLBaseline: Run ALL tests without any scoring/prioritization

These baselines run during experiments alongside ML-guided selection to
produce comparison data for H9 (ML Value Over Baselines).
"""
import random
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Optional

from models.test_case import TestCase, TestSuite


class BaselineStrategy(ABC):
    """Abstract base for non-ML test selection strategies."""

    name: str = "base"

    @abstractmethod
    def select_tests(self, suite: TestSuite, k: int) -> list[TestCase]:
        """Select k tests from suite according to strategy.

        Args:
            suite: The full test suite to select from.
            k: Number of tests to select (ignored by NoMLBaseline).

        Returns:
            List of selected TestCase objects.
        """

    def apply(self, suite: TestSuite, k: Optional[int] = None) -> TestSuite:
        """Apply selection strategy and return a new TestSuite with selected tests.

        Args:
            suite: Original test suite.
            k: Number of tests to select. If None, uses half the suite size.

        Returns:
            New TestSuite with selected test cases marked as is_recommended=True.
        """
        if k is None:
            k = max(1, len(suite.test_cases) // 2)

        selected = self.select_tests(suite, k)

        # Mark selected tests
        selected_ids = {tc.test_id for tc in selected}
        new_cases = []
        for tc in suite.test_cases:
            # Create a copy with is_recommended flag
            new_tc = TestCase.from_dict(tc.to_dict())
            new_tc.is_recommended = tc.test_id in selected_ids
            new_tc.risk_score = 1.0 if tc.test_id in selected_ids else 0.0
            new_cases.append(new_tc)

        new_suite = TestSuite(
            suite_id=suite.suite_id,
            name=suite.name,
            created_at=suite.created_at,
            devices=suite.devices,
            test_cases=new_cases,
            metadata={**suite.metadata, "baseline_strategy": self.name},
        )
        logging.info(
            f"[Baseline:{self.name}] Selected {len(selected)}/{len(suite.test_cases)} tests"
        )
        return new_suite


class RandomBaseline(BaselineStrategy):
    """Randomly select k tests (seeded for reproducibility)."""

    name = "random"

    def __init__(self, seed: int = 42):
        self.seed = seed

    def select_tests(self, suite: TestSuite, k: int) -> list[TestCase]:
        rng = random.Random(self.seed)
        return rng.sample(suite.test_cases, min(k, len(suite.test_cases)))


class CVSSPriorityBaseline(BaselineStrategy):
    """Prioritize by severity: critical -> high -> medium -> low -> info.

    Since the registry uses severity strings rather than numeric CVSS scores,
    this maps severity levels to a numeric priority for sorting.
    """

    name = "cvss_priority"

    SEVERITY_ORDER = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "info": 1,
    }

    def select_tests(self, suite: TestSuite, k: int) -> list[TestCase]:
        sorted_tests = sorted(
            suite.test_cases,
            key=lambda tc: self.SEVERITY_ORDER.get(tc.severity.lower(), 0),
            reverse=True,
        )
        return sorted_tests[:min(k, len(sorted_tests))]


class RoundRobinBaseline(BaselineStrategy):
    """Equal allocation per protocol, then cycle.

    Distributes test selections evenly across protocols to ensure
    coverage breadth rather than depth in any single protocol.
    """

    name = "round_robin"

    def select_tests(self, suite: TestSuite, k: int) -> list[TestCase]:
        by_proto = defaultdict(list)
        for tc in suite.test_cases:
            by_proto[tc.protocol].append(tc)

        # Interleave: 1 from each protocol, repeat
        selected = []
        while len(selected) < k:
            added_any = False
            for proto in sorted(by_proto.keys()):
                if by_proto[proto] and len(selected) < k:
                    selected.append(by_proto[proto].pop(0))
                    added_any = True
            if not added_any:
                break  # All protocols exhausted

        return selected


class NoMLBaseline(BaselineStrategy):
    """Run ALL tests without any scoring/prioritization.

    This serves as the upper bound for detection — if running all tests
    can't find a vulnerability, nothing will. Used to compute the true
    detection ceiling and the cost of exhaustive testing.
    """

    name = "no_ml"

    def select_tests(self, suite: TestSuite, k: int = None) -> list[TestCase]:
        return list(suite.test_cases)

    def apply(self, suite: TestSuite, k: Optional[int] = None) -> TestSuite:
        """Override apply to mark ALL tests as recommended."""
        new_cases = []
        for tc in suite.test_cases:
            new_tc = TestCase.from_dict(tc.to_dict())
            new_tc.is_recommended = True
            new_tc.risk_score = 0.5  # Neutral score for all
            new_cases.append(new_tc)

        return TestSuite(
            suite_id=suite.suite_id,
            name=suite.name,
            created_at=suite.created_at,
            devices=suite.devices,
            test_cases=new_cases,
            metadata={**suite.metadata, "baseline_strategy": self.name},
        )


# ── Factory ──────────────────────────────────────────────────────────

BASELINE_REGISTRY = {
    "random": RandomBaseline,
    "cvss_priority": CVSSPriorityBaseline,
    "round_robin": RoundRobinBaseline,
    "no_ml": NoMLBaseline,
}


def get_baseline(name: str, **kwargs) -> BaselineStrategy:
    """Get a baseline strategy by name.

    Args:
        name: One of "random", "cvss_priority", "round_robin", "no_ml".
        **kwargs: Extra arguments passed to the strategy constructor.

    Returns:
        BaselineStrategy instance.

    Raises:
        ValueError: If name is not recognized.
    """
    cls = BASELINE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown baseline strategy: {name}. "
            f"Available: {list(BASELINE_REGISTRY.keys())}"
        )
    return cls(**kwargs)


def list_baselines() -> list[str]:
    """List available baseline strategy names."""
    return list(BASELINE_REGISTRY.keys())
