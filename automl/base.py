"""
AutoML Framework Abstraction Layer — Strategy pattern for multi-framework support.

Defines the AutoMLAdapter abstract base class and AutoMLResult unified container
that all framework adapters must implement. This enables Emergence to swap between
H2O, AutoGluon, PyCaret, TPOT, and auto-sklearn without changing the pipeline logic.
"""
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class AutoMLResult:
    """Unified output container from any AutoML framework.

    Every adapter's ``train()`` method must return an instance of this class
    so that the rest of the pipeline (scoring, metrics, dashboard) can work
    framework-agnostically.
    """

    # ── Core identifiers ────────────────────────────────────────────────
    framework: str                          # e.g. "h2o", "autogluon", "pycaret"
    leader_model_id: str = "unknown"        # framework-specific model identifier
    leader_algo: str = "unknown"            # algorithm name of the best model

    # ── Performance metrics ─────────────────────────────────────────────
    auc: Optional[float] = None             # area under the ROC curve
    logloss: Optional[float] = None
    accuracy: Optional[float] = None

    # ── Feature importance ──────────────────────────────────────────────
    feature_importance: list[dict] = field(default_factory=list)
    # Each dict: {"variable": str, "relative_importance": float,
    #             "scaled_importance": float, "percentage": float}

    # ── Leaderboard ─────────────────────────────────────────────────────
    leaderboard: list[dict] = field(default_factory=list)
    total_models_trained: int = 0

    # ── ROC curve data ──────────────────────────────────────────────────
    roc_curve: Optional[dict] = None        # {"fpr": [...], "tpr": [...], "auc": float}

    # ── Cross-validation metrics ────────────────────────────────────────
    cv_auc: Optional[float] = None
    cv_logloss: Optional[float] = None
    cv_accuracy: Optional[float] = None
    cv_precision: Optional[float] = None
    cv_recall: Optional[float] = None
    cv_f1: Optional[float] = None
    cv_threshold: Optional[float] = None
    cv_summary: Optional[list[dict]] = None
    cross_validation: dict = field(default_factory=lambda: {"available": False})

    # ── Confusion matrices ──────────────────────────────────────────────
    confusion_matrix: Optional[list] = None
    cv_confusion_matrix: Optional[list] = None

    # ── Training metadata ───────────────────────────────────────────────
    training_time_secs: float = 0.0
    training_rows: int = 0
    status: str = "trained"

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary (matches existing metrics format)."""
        d = {
            "framework": self.framework,
            "leader_model_id": self.leader_model_id,
            "leader_algo": self.leader_algo,
            "auc": self.auc,
            "logloss": self.logloss,
            "accuracy": self.accuracy,
            "feature_importance": self.feature_importance,
            "leaderboard": self.leaderboard,
            "total_models_trained": self.total_models_trained,
            "roc_curve": self.roc_curve,
            "cv_auc": self.cv_auc,
            "cv_logloss": self.cv_logloss,
            "cv_accuracy": self.cv_accuracy,
            "cv_precision": self.cv_precision,
            "cv_recall": self.cv_recall,
            "cv_f1": self.cv_f1,
            "cv_threshold": self.cv_threshold,
            "cv_summary": self.cv_summary,
            "cross_validation": self.cross_validation,
            "confusion_matrix": self.confusion_matrix,
            "cv_confusion_matrix": self.cv_confusion_matrix,
            "training_time_secs": self.training_time_secs,
            "training_rows": self.training_rows,
            "status": self.status,
        }
        return _sanitize_metrics(d)


class AutoMLAdapter(ABC):
    """Abstract base class for all AutoML framework adapters.

    Each concrete adapter wraps a specific framework (H2O, AutoGluon, etc.)
    and exposes a uniform interface for training, prediction, and model
    persistence.
    """

    # Subclasses must set this to their framework name (e.g. "h2o", "autogluon")
    FRAMEWORK_NAME: str = "unknown"

    @abstractmethod
    def train(
        self,
        df: pd.DataFrame,
        target: str = "vulnerability_found",
        max_runtime_secs: int = 300,
        seed: int = 42,
    ) -> AutoMLResult:
        """Train an AutoML model on the given DataFrame.

        Args:
            df: Training data with features and target column.
            target: Name of the binary target column.
            max_runtime_secs: Maximum training time budget.
            seed: Random seed for reproducibility.

        Returns:
            AutoMLResult with metrics, leaderboard, and feature importance.
        """
        ...

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate predictions for the given feature DataFrame.

        Args:
            df: Feature DataFrame (same schema as training, minus target).

        Returns:
            DataFrame with at minimum a ``p1`` column containing the
            probability of vulnerability_found=1.
        """
        ...

    @abstractmethod
    def save_model(self, directory: str) -> str:
        """Persist the trained model to disk.

        Args:
            directory: Directory to save model artifacts into.

        Returns:
            Path to the saved model file/directory.
        """
        ...

    @abstractmethod
    def load_model(self, directory: str) -> bool:
        """Load a previously saved model from disk.

        Args:
            directory: Directory containing model artifacts.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this framework is reachable and operational.

        Returns:
            True if the framework can be used for training/prediction.
        """
        ...

    def get_name(self) -> str:
        """Return the framework name."""
        return self.FRAMEWORK_NAME

    def has_model(self) -> bool:
        """Check whether a trained model is currently loaded.

        Default implementation returns False; adapters override as needed.
        """
        return False


# ── Utilities ────────────────────────────────────────────────────────────

def _sanitize_metrics(obj):
    """Recursively replace NaN/inf with None to ensure JSON-safe output."""
    if isinstance(obj, dict):
        return {k: _sanitize_metrics(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_metrics(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj
