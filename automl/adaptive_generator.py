import h2o

def rank_tests(test_candidates_df, model, top_k=5):
    hf = h2o.H2OFrame(test_candidates_df)
    preds = model.predict(hf).as_data_frame()

    test_candidates_df["risk_score"] = preds["p1"]
    ranked = test_candidates_df.sort_values(
        by="risk_score", ascending=False
    )

    return ranked.head(top_k)
