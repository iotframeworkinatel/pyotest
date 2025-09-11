import h2o
from h2o.automl import H2OAutoML
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split


def simulate_smart_home_logs(n=2500, seed=42):
    np.random.seed(seed)
    commands = ['turn_on_light', 'turn_off_light', 'lock_door', 'unlock_door', 'set_temp']
    connectivity = ['wifi', 'zigbee', 'bluetooth']
    logs = []

    for _ in range(n):
        cmd = np.random.choice(commands)
        latency = np.random.normal(loc=200, scale=100)
        latency = max(10, latency)
        concurrent_devices = np.random.randint(1, 5)
        conn = np.random.choice(connectivity)
        sync_fail = 1 if (latency > 300 and concurrent_devices >= 3) else 0

        logs.append({
            'command': cmd,
            'latency_ms': latency,
            'concurrent_devices': concurrent_devices,
            'connectivity': conn,
            'sync_failure': sync_fail
        })

    return pd.DataFrame(logs)


# Simulate and preprocess
def general_automl(devices):
    df = simulate_smart_home_logs()
    df_encoded = pd.get_dummies(df, columns=['command', 'connectivity'])
    train, test = train_test_split(df_encoded, test_size=0.2, random_state=42)

    # H2O
    h2o.init()
    train_h2o = h2o.H2OFrame(train)
    test_h2o = h2o.H2OFrame(test)
    y = "sync_failure"
    x = train_h2o.columns
    x.remove(y)
    train_h2o[y] = train_h2o[y].asfactor()
    test_h2o[y] = test_h2o[y].asfactor()

    # AutoML training
    aml = H2OAutoML(max_runtime_secs=600, seed=1, balance_classes=True)
    aml.train(x=x, y=y, training_frame=train_h2o)

    # Prediction and test generation
    preds = aml.leader.predict(test_h2o)
    pred_df = preds.as_data_frame()
    original_test = test.reset_index(drop=True)
    original_test['predicted_failure_prob'] = pred_df['p1']
    risky_cases = original_test[original_test['predicted_failure_prob'] > 0.85]

    if risky_cases.empty:
        print("No high risk scenario found!")
        risky_cases = original_test.sort_values(by='predicted_failure_prob', ascending=False).head(1)

    # Save test functions
    with open("generated_tests.py", "w") as f:
        for idx, row in risky_cases.iterrows():
            command_cols = row.filter(like='command_').fillna(0).astype(float)

            if command_cols.sum() == 0:
                command_name = "unknown_command"
            else:
                command_name = command_cols.idxmax().replace('command_', '')

            f.write(f"def test_generated_case_{idx}():\n")
            f.write(f"    # Predicted failure probability: {row['predicted_failure_prob']:.2f}\n")
            f.write(f"    send_command('{command_name}')\n")
            f.write(f"    simulate_network_latency({int(row['latency_ms'])})\n")
            f.write(f"    assert_device_sync(timeout=3000)\n\n")
