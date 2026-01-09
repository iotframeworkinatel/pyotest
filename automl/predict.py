import h2o

def predict_failure_probability(model, df):
    hf = h2o.H2OFrame(df)
    preds = model.predict(hf)
    return preds.as_data_frame()
