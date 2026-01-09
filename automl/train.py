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
