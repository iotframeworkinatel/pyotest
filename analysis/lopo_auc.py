"""Compute LOPO per-protocol AUC from the aggregated LOPO CSVs.

For each protocol P:
  - train set = rows where protocol != P
  - test set  = rows where protocol == P
Score = per-(protocol,test_id) rolling vulnerability rate on training set.
If a test_id never appeared in training, fall back to global rate.
Then AUC(y=vulnerability_found, score) on the test set.
"""
import os
from pathlib import Path

# Run from the repository root so relative data paths resolve on any machine.
os.chdir(Path(__file__).resolve().parents[1])
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

for mode in ("deterministic", "realistic"):
    path = f"experiments/aggregated_history_lopo_{mode}.csv"
    df = pd.read_csv(path)
    print(f"\n=== {mode} (n={len(df)}) ===")
    protos = sorted(df.protocol.unique())
    print(f"protocols: {protos}")
    rows = []
    for P in protos:
        train = df[df.protocol != P]
        test  = df[df.protocol == P]
        if len(test) == 0 or test.vulnerability_found.nunique() < 2:
            rows.append((P, len(test), int(test.vulnerability_found.sum()), None, "sparse/const"))
            continue
        # protocol-agnostic features: test_type, device_type, auth_required, payload_size bucket
        train_rate_type = train.groupby("test_type")["vulnerability_found"].mean()
        train_rate_dev  = train.groupby("device_type")["vulnerability_found"].mean()
        train_rate_auth = train.groupby("auth_required")["vulnerability_found"].mean()
        global_rate = train.vulnerability_found.mean()
        s_type = test.test_type.map(train_rate_type).fillna(global_rate).values
        s_dev  = test.device_type.map(train_rate_dev).fillna(global_rate).values
        s_auth = test.auth_required.map(train_rate_auth).fillna(global_rate).values
        # linear blend
        score = (s_type + s_dev + s_auth) / 3.0
        y = test.vulnerability_found.astype(int).values
        try:
            auc = roc_auc_score(y, score)
            rows.append((P, len(test), int(y.sum()), auc, "ok"))
        except Exception as e:
            rows.append((P, len(test), int(y.sum()), None, f"err:{e}"))
    from scipy.stats import wilcoxon
    out = pd.DataFrame(rows, columns=["proto","n","vulns","AUC","note"])
    print(out.to_string(index=False))
    ok = out[out.note=="ok"]
    print(f"median AUC (ok cells): {ok.AUC.median():.4f}")
    print(f"mean AUC   (ok cells): {ok.AUC.mean():.4f}")
    if len(ok) >= 3:
        diffs = ok.AUC.values - 0.5
        try:
            w = wilcoxon(diffs, alternative="greater")
            print(f"Wilcoxon (AUC > 0.5) W={w.statistic}, p={w.pvalue:.4f}")
        except Exception as e:
            print(f"Wilcoxon: {e}")
