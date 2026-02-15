import logging
import math
import h2o
from h2o.automl import H2OAutoML

def init_h2o():
    if not h2o.connection():
        h2o.init(max_mem_size="2G")

def train_automl(df, target="vulnerability_found"):
    init_h2o()

    hf = h2o.H2OFrame(df)
    hf[target] = hf[target].asfactor()

    x = [c for c in hf.columns if c != target]

    aml = H2OAutoML(
        max_runtime_secs=300,
        balance_classes=True,
        sort_metric="AUC",
        seed=42
    )

    aml.train(x=x, y=target, training_frame=hf)
    return aml


def extract_model_metrics(aml):
    """
    Extract model performance metrics and leaderboard from H2O AutoML.
    Returns a dict with AUC, feature importance, and top-5 leaderboard.
    """
    leader = aml.leader
    metrics = {}

    # ── Leader model info ──
    try:
        metrics["leader_model_id"] = str(leader.model_id)
        metrics["leader_algo"] = str(leader.algo)
    except Exception:
        metrics["leader_model_id"] = "unknown"
        metrics["leader_algo"] = "unknown"

    # ── Training performance (AUC, logloss, etc.) ──
    try:
        perf = leader.model_performance()
        metrics["auc"] = round(float(perf.auc()), 4)
        metrics["logloss"] = round(float(perf.logloss()), 4)
        metrics["accuracy"] = round(float(1 - perf.mean_per_class_error()), 4)

        # Confusion matrix as simple dict
        cm = perf.confusion_matrix()
        if cm is not None:
            cm_table = cm.to_list()
            metrics["confusion_matrix"] = cm_table
    except Exception as e:
        logging.warning(f"[AutoML] Could not extract performance metrics: {e}")
        metrics["auc"] = None

    # ── Feature importance (from leader model) ──
    try:
        varimp = leader.varimp()
        if varimp:
            metrics["feature_importance"] = [
                {
                    "variable": row[0],
                    "relative_importance": round(float(row[1]), 4),
                    "scaled_importance": round(float(row[2]), 4),
                    "percentage": round(float(row[3]), 4),
                }
                for row in varimp
            ]
        else:
            metrics["feature_importance"] = []
    except Exception as e:
        logging.warning(f"[AutoML] Could not extract feature importance: {e}")
        metrics["feature_importance"] = []

    # ── Cross-validation performance (Phase 3A) ──
    try:
        cv_perf = leader.model_performance(xval=True)
        if cv_perf is not None:
            metrics["cv_auc"] = round(float(cv_perf.auc()), 4)
            metrics["cv_logloss"] = round(float(cv_perf.logloss()), 4)
            metrics["cv_accuracy"] = round(float(1 - cv_perf.mean_per_class_error()), 4)

            # Cross-validation confusion matrix
            try:
                cv_cm = cv_perf.confusion_matrix()
                if cv_cm is not None:
                    metrics["cv_confusion_matrix"] = cv_cm.to_list()
            except Exception:
                pass

            # Precision, Recall, F1 (per threshold — extract at default threshold)
            try:
                # H2O returns list of [threshold, metric] pairs
                precision_data = cv_perf.precision()
                recall_data = cv_perf.recall()
                f1_data = cv_perf.F1()
                if precision_data and len(precision_data) > 0:
                    # Get the value at the max F1 threshold
                    best_f1_idx = 0
                    best_f1_val = 0
                    for i, row in enumerate(f1_data):
                        if len(row) >= 2 and row[1] > best_f1_val:
                            best_f1_val = row[1]
                            best_f1_idx = i
                    metrics["cv_precision"] = round(float(precision_data[best_f1_idx][1]), 4)
                    metrics["cv_recall"] = round(float(recall_data[best_f1_idx][1]), 4)
                    metrics["cv_f1"] = round(float(best_f1_val), 4)
                    metrics["cv_threshold"] = round(float(f1_data[best_f1_idx][0]), 4)
            except Exception as e:
                logging.debug(f"[AutoML] Could not extract precision/recall/F1: {e}")

            # ROC curve data (FPR vs TPR) for visualization
            try:
                fpr_list = cv_perf.fprs
                tpr_list = cv_perf.tprs
                if fpr_list and tpr_list:
                    # fpr_list/tpr_list are lists of [threshold, fpr/tpr] pairs
                    # Extract just the rate values
                    fpr_values = [row[1] for row in fpr_list if len(row) >= 2]
                    tpr_values = [row[1] for row in tpr_list if len(row) >= 2]
                    # Subsample to max 100 points for reasonable JSON size
                    if len(fpr_values) > 100:
                        step = len(fpr_values) // 100
                        fpr_values = fpr_values[::step]
                        tpr_values = tpr_values[::step]
                    metrics["roc_curve"] = {
                        "fpr": [round(float(x), 4) for x in fpr_values],
                        "tpr": [round(float(x), 4) for x in tpr_values],
                        "auc": metrics.get("cv_auc", metrics.get("auc")),
                    }
            except Exception as e:
                logging.debug(f"[AutoML] Could not extract ROC curve: {e}")

            # Cross-validation summary table
            try:
                cv_summary = leader.cross_validation_metrics_summary()
                if cv_summary is not None:
                    cv_df = cv_summary.as_data_frame()
                    metrics["cv_summary"] = cv_df.to_dict(orient="records")
            except Exception:
                pass

            metrics["cross_validation"] = {"available": True}
        else:
            metrics["cross_validation"] = {"available": False}
    except Exception as e:
        logging.warning(f"[AutoML] Could not extract CV metrics: {e}")
        metrics["cross_validation"] = {"available": False}

    # ── Leaderboard (top 10 models) ──
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
        metrics["leaderboard"] = lb_records
        metrics["total_models_trained"] = len(lb)
    except Exception as e:
        logging.warning(f"[AutoML] Could not extract leaderboard: {e}")
        metrics["leaderboard"] = []
        metrics["total_models_trained"] = 0

    return _sanitize_metrics(metrics)


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
