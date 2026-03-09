"""
REST-based AutoML Adapter Base — shared client logic for containerized frameworks.

AutoGluon, PyCaret, TPOT, and auto-sklearn all run in separate Docker containers
and expose a unified REST API. This base class implements the HTTP client logic
so that each concrete adapter only needs to specify its URL and framework name.
"""
import io
import logging
import time
from typing import Optional

import pandas as pd
import requests

from automl.base import AutoMLAdapter, AutoMLResult


class RESTAutoMLAdapter(AutoMLAdapter):
    """Base adapter for AutoML frameworks running as REST services in Docker.

    Each framework container exposes:
        POST /train    — body: CSV data + config JSON → returns metrics JSON
        POST /predict  — body: CSV features → returns JSON with p1 probabilities
        GET  /status   — returns {ready: bool, model_loaded: bool}
        GET  /metrics  — returns saved model metrics
        POST /save     — persist model to shared volume
        POST /load     — load model from shared volume
    """

    # Subclasses must set these
    FRAMEWORK_NAME: str = "unknown"
    BASE_URL: str = "http://localhost:8080"
    TIMEOUT_TRAIN: int = 600    # seconds
    TIMEOUT_PREDICT: int = 120  # seconds

    def __init__(self):
        self._model_loaded = False

    def train(
        self,
        df: pd.DataFrame,
        target: str = "vulnerability_found",
        max_runtime_secs: int = 300,
        seed: int = 42,
    ) -> AutoMLResult:
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()

        start = time.time()

        response = requests.post(
            f"{self.BASE_URL}/train",
            json={
                "csv_data": csv_data,
                "target": target,
                "max_runtime_secs": max_runtime_secs,
                "seed": seed,
            },
            timeout=self.TIMEOUT_TRAIN,
        )
        response.raise_for_status()
        metrics = response.json()

        elapsed = time.time() - start
        self._model_loaded = True

        return AutoMLResult(
            framework=self.FRAMEWORK_NAME,
            leader_model_id=metrics.get("leader_model_id", "unknown"),
            leader_algo=metrics.get("leader_algo", "unknown"),
            auc=metrics.get("auc"),
            logloss=metrics.get("logloss"),
            accuracy=metrics.get("accuracy"),
            feature_importance=metrics.get("feature_importance", []),
            leaderboard=metrics.get("leaderboard", []),
            total_models_trained=metrics.get("total_models_trained", 0),
            roc_curve=metrics.get("roc_curve"),
            cv_auc=metrics.get("cv_auc"),
            cv_logloss=metrics.get("cv_logloss"),
            cv_accuracy=metrics.get("cv_accuracy"),
            cv_precision=metrics.get("cv_precision"),
            cv_recall=metrics.get("cv_recall"),
            cv_f1=metrics.get("cv_f1"),
            cv_threshold=metrics.get("cv_threshold"),
            cv_summary=metrics.get("cv_summary"),
            cross_validation=metrics.get("cross_validation", {"available": False}),
            confusion_matrix=metrics.get("confusion_matrix"),
            cv_confusion_matrix=metrics.get("cv_confusion_matrix"),
            training_time_secs=round(elapsed, 2),
            training_rows=len(df),
            status="trained",
        )

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()

        response = requests.post(
            f"{self.BASE_URL}/predict",
            json={"csv_data": csv_data},
            timeout=self.TIMEOUT_PREDICT,
        )
        response.raise_for_status()
        result = response.json()

        # Result should contain a "predictions" list with p1 values
        predictions = result.get("predictions", [])
        return pd.DataFrame({"p1": predictions})

    def save_model(self, directory: str) -> str:
        response = requests.post(
            f"{self.BASE_URL}/save",
            json={"directory": directory},
            timeout=60,
        )
        response.raise_for_status()
        return response.json().get("path", directory)

    def load_model(self, directory: str) -> bool:
        try:
            response = requests.post(
                f"{self.BASE_URL}/load",
                json={"directory": directory},
                timeout=60,
            )
            response.raise_for_status()
            self._model_loaded = response.json().get("loaded", False)
            return self._model_loaded
        except Exception as e:
            logging.warning(f"[{self.FRAMEWORK_NAME}] Could not load model: {e}")
            return False

    def is_available(self) -> bool:
        try:
            response = requests.get(
                f"{self.BASE_URL}/status",
                timeout=5,
            )
            return response.status_code == 200 and response.json().get("ready", False)
        except Exception:
            return False

    def has_model(self) -> bool:
        if self._model_loaded:
            return True
        try:
            response = requests.get(
                f"{self.BASE_URL}/status",
                timeout=5,
            )
            return response.status_code == 200 and response.json().get("model_loaded", False)
        except Exception:
            return False
