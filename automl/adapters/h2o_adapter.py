"""
H2O AutoML Adapter — wraps existing H2O integration behind the AutoMLAdapter interface.

This adapter delegates to the existing ``automl.train`` module's H2O-specific
functions (init_h2o, train_automl, extract_model_metrics) and translates their
output into the unified ``AutoMLResult`` format.
"""
import glob
import logging
import os
import time
from typing import Optional

import pandas as pd

from automl.base import AutoMLAdapter, AutoMLResult
from automl.registry import register


H2O_URL = "http://172.20.0.18:54321"


@register
class H2OAdapter(AutoMLAdapter):
    """Adapter for H2O AutoML (Java server at 172.20.0.18:54321)."""

    FRAMEWORK_NAME = "h2o"

    def __init__(self):
        self._leader = None
        self._aml = None

    # ── AutoMLAdapter interface ──────────────────────────────────────────

    def train(
        self,
        df: pd.DataFrame,
        target: str = "vulnerability_found",
        max_runtime_secs: int = 300,
        seed: int = 42,
    ) -> AutoMLResult:
        import h2o
        from h2o.automl import H2OAutoML

        self._init_h2o()

        # Remove all previous frames and models from the H2O server before
        # each training run to prevent K/V store OOM accumulation across
        # iterations. The leader is re-uploaded from disk when needed.
        try:
            h2o.remove_all()
        except Exception as e:
            logging.warning(f"[H2O] Could not clear server state before training: {e}")

        start = time.time()

        hf = h2o.H2OFrame(df)
        hf[target] = hf[target].asfactor()
        x = [c for c in hf.columns if c != target]

        aml = H2OAutoML(
            max_runtime_secs=max_runtime_secs,
            balance_classes=True,
            sort_metric="AUC",
            seed=seed,
        )
        aml.train(x=x, y=target, training_frame=hf)

        elapsed = time.time() - start

        self._leader = aml.leader
        self._aml = aml

        result = self._extract_result(aml, elapsed, len(df))

        # Remove the training frame now that AutoML is done; leader model
        # stays in the K/V store so predict() can use it directly.
        try:
            h2o.remove(hf)
        except Exception:
            pass

        return result

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._leader is None:
            raise RuntimeError("No H2O model loaded — train or load first")

        import h2o

        self._init_h2o()
        hf = h2o.H2OFrame(df)
        try:
            preds = self._leader.predict(hf)
            return preds.as_data_frame()
        finally:
            try:
                h2o.remove(hf)
            except Exception:
                pass

    def save_model(self, directory: str) -> str:
        if self._leader is None:
            raise RuntimeError("No H2O model to save")

        import h2o

        os.makedirs(directory, exist_ok=True)

        # Remove previous saved model files
        for old in glob.glob(os.path.join(directory, "*")):
            try:
                os.remove(old)
            except OSError:
                pass

        saved_path = h2o.download_model(self._leader, path=directory)
        logging.info(f"[H2O] Model binary saved to: {saved_path}")
        return saved_path

    def load_model(self, directory: str) -> bool:
        import h2o

        self._init_h2o()

        # Try to load from disk
        try:
            if os.path.isdir(directory):
                model_files = glob.glob(os.path.join(directory, "*"))
                if model_files:
                    model_path = model_files[0]
                    self._leader = h2o.upload_model(model_path)
                    logging.info(f"[H2O] Re-uploaded model from disk: {model_path}")
                    return True
        except Exception as e:
            logging.warning(f"[H2O] Could not reload model from disk: {e}")

        return False

    def is_available(self) -> bool:
        try:
            import h2o
            self._init_h2o()
            return True
        except Exception:
            return False

    def has_model(self) -> bool:
        return self._leader is not None

    # ── H2O-specific helpers ─────────────────────────────────────────────

    def get_leader(self):
        """Return the raw H2O leader model (for backward compatibility)."""
        return self._leader

    def get_aml(self):
        """Return the raw H2OAutoML object."""
        return self._aml

    def set_leader(self, leader):
        """Set the leader model directly (for backward compatibility with cache)."""
        self._leader = leader

    def try_fetch_from_server(self, model_id: str) -> bool:
        """Try to retrieve a model by ID from the H2O server."""
        import h2o

        try:
            self._init_h2o()
            self._leader = h2o.get_model(model_id)
            logging.info(f"[H2O] Reloaded model from H2O server: {model_id}")
            return True
        except Exception:
            return False

    def _init_h2o(self):
        """Connect to H2O server if not already connected."""
        import h2o

        try:
            conn = h2o.connection()
            if conn and conn.connected:
                return
        except Exception:
            pass
        h2o.connect(url=H2O_URL)

    def _extract_result(self, aml, training_time: float, training_rows: int) -> AutoMLResult:
        """Convert H2O AutoML output into a unified AutoMLResult."""
        leader = aml.leader
        result = AutoMLResult(framework="h2o", training_time_secs=round(training_time, 2))
        result.training_rows = training_rows

        # Leader info
        try:
            result.leader_model_id = str(leader.model_id)
            result.leader_algo = str(leader.algo)
        except Exception:
            pass

        # Training performance
        try:
            perf = leader.model_performance()
            result.auc = round(float(perf.auc()), 4)
            result.logloss = round(float(perf.logloss()), 4)
            result.accuracy = round(float(1 - perf.mean_per_class_error()), 4)

            cm = perf.confusion_matrix()
            if cm is not None:
                result.confusion_matrix = cm.to_list()
        except Exception as e:
            logging.warning(f"[H2O] Could not extract performance metrics: {e}")

        # Feature importance
        try:
            varimp = leader.varimp()
            if varimp:
                result.feature_importance = [
                    {
                        "variable": row[0],
                        "relative_importance": round(float(row[1]), 4),
                        "scaled_importance": round(float(row[2]), 4),
                        "percentage": round(float(row[3]), 4),
                    }
                    for row in varimp
                ]
        except Exception as e:
            logging.warning(f"[H2O] Could not extract feature importance: {e}")

        # Cross-validation metrics
        try:
            cv_perf = leader.model_performance(xval=True)
            if cv_perf is not None:
                result.cv_auc = round(float(cv_perf.auc()), 4)
                result.cv_logloss = round(float(cv_perf.logloss()), 4)
                result.cv_accuracy = round(float(1 - cv_perf.mean_per_class_error()), 4)

                try:
                    cv_cm = cv_perf.confusion_matrix()
                    if cv_cm is not None:
                        result.cv_confusion_matrix = cv_cm.to_list()
                except Exception:
                    pass

                # Precision, Recall, F1 at best F1 threshold
                try:
                    precision_data = cv_perf.precision()
                    recall_data = cv_perf.recall()
                    f1_data = cv_perf.F1()
                    if precision_data and len(precision_data) > 0:
                        best_f1_idx = 0
                        best_f1_val = 0
                        for i, row in enumerate(f1_data):
                            if len(row) >= 2 and row[1] > best_f1_val:
                                best_f1_val = row[1]
                                best_f1_idx = i
                        result.cv_precision = round(float(precision_data[best_f1_idx][1]), 4)
                        result.cv_recall = round(float(recall_data[best_f1_idx][1]), 4)
                        result.cv_f1 = round(float(best_f1_val), 4)
                        result.cv_threshold = round(float(f1_data[best_f1_idx][0]), 4)
                except Exception as e:
                    logging.debug(f"[H2O] Could not extract precision/recall/F1: {e}")

                # ROC curve
                try:
                    fpr_list = cv_perf.fprs
                    tpr_list = cv_perf.tprs
                    if fpr_list and tpr_list:
                        fpr_values = [row[1] for row in fpr_list if len(row) >= 2]
                        tpr_values = [row[1] for row in tpr_list if len(row) >= 2]
                        if len(fpr_values) > 100:
                            step = len(fpr_values) // 100
                            fpr_values = fpr_values[::step]
                            tpr_values = tpr_values[::step]
                        result.roc_curve = {
                            "fpr": [round(float(x), 4) for x in fpr_values],
                            "tpr": [round(float(x), 4) for x in tpr_values],
                            "auc": result.cv_auc or result.auc,
                        }
                except Exception as e:
                    logging.debug(f"[H2O] Could not extract ROC curve: {e}")

                # CV summary table
                try:
                    cv_summary = leader.cross_validation_metrics_summary()
                    if cv_summary is not None:
                        cv_df = cv_summary.as_data_frame()
                        result.cv_summary = cv_df.to_dict(orient="records")
                except Exception:
                    pass

                result.cross_validation = {"available": True}
            else:
                result.cross_validation = {"available": False}
        except Exception as e:
            logging.warning(f"[H2O] Could not extract CV metrics: {e}")
            result.cross_validation = {"available": False}

        # Leaderboard (top 10)
        try:
            lb = aml.leaderboard.as_data_frame()
            lb_records = []
            for _, row in lb.head(10).iterrows():
                record = {}
                for col in lb.columns:
                    val = row[col]
                    try:
                        record[col] = round(float(val), 6)
                    except (ValueError, TypeError):
                        record[col] = str(val)
                lb_records.append(record)
            result.leaderboard = lb_records
            result.total_models_trained = len(lb)
        except Exception as e:
            logging.warning(f"[H2O] Could not extract leaderboard: {e}")

        # Normalize AUC: prefer cv_auc over training auc
        if result.auc is None and result.cv_auc is not None:
            result.auc = result.cv_auc

        return result
