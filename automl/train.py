import logging
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

    return metrics
