import logging
import h2o
from h2o.automl import H2OAutoML
import pandas as pd
from sklearn.model_selection import train_test_split


def general_automl(devices):
    logging.info("Starting AutoML for device-based test case generation...")

    vuln_data = []

    for device in devices:
        # Caso o device não tenha vulnerabilidades
        if not hasattr(device, "vulnerabilities") or not device.vulnerabilities:
            logging.info(f"Device {device.ip} has no vulnerabilities, generating basic tests...")

            with open("generated_basic_tests.py", "a") as f:
                f.write(f"def test_device_{device.ip.replace('.', '_')}_basic():\n")
                f.write(f"    # Basic connectivity and IoT checks\n")
                f.write(f"    assert check_ip_reachable('{device.ip}')\n")
                f.write(f"    assert check_mac_format('{device.mac}')\n")
                f.write(f"    assert check_ports_open('{device.ip}', {device.ports})\n")
                f.write(f"    assert {device.is_iot} == True  # Device must be IoT\n\n")
            continue

        # Se houver vulnerabilidades → coleta normalmente
        for vuln in device.vulnerabilities:
            vuln_data.append({
                "device_id": getattr(device, "id", device.ip),
                "ip": device.ip,
                "mac": device.mac,
                "ports": ",".join(map(str, device.ports)),
                "vuln_id": vuln.get("id", "unknown"),
                "name": vuln.get("name", "unnamed"),
                "severity": vuln.get("severity", "low"),
                "category": vuln.get("category", "generic"),
                "protocol": vuln.get("protocol", "unknown"),
                "exploit_available": 1 if vuln.get("exploit_available", False) else 0
            })

    # Se não houver vulnerabilidades em nenhum device, para aqui
    if not vuln_data:
        logging.info("No vulnerabilities found. Only basic tests were generated.")
        return

    df = pd.DataFrame(vuln_data)

    # Target
    y = "exploit_available"
    x = [col for col in df.columns if col not in ["device_id", "vuln_id", "name", y]]

    # Encoding
    df_encoded = pd.get_dummies(df[x + [y]], drop_first=True)

    # Split dataset
    train, test = train_test_split(df_encoded, test_size=0.2, random_state=42)

    # H2O init
    h2o.init()
    train_h2o = h2o.H2OFrame(train)
    test_h2o = h2o.H2OFrame(test)

    # Converter target para categórico
    train_h2o[y] = train_h2o[y].asfactor()
    test_h2o[y] = test_h2o[y].asfactor()

    # AutoML
    aml = H2OAutoML(max_runtime_secs=600, seed=1, balance_classes=True)
    aml.train(x=[col for col in train_h2o.columns if col != y], y=y, training_frame=train_h2o)

    # Predição
    preds = aml.leader.predict(test_h2o)
    pred_df = preds.as_data_frame()
    original_test = test.reset_index(drop=True)
    original_test['predicted_exploit_prob'] = pred_df['p1']

    # Selecionar vulnerabilidades críticas
    risky_cases = original_test[original_test['predicted_exploit_prob'] > 0.75]
    if risky_cases.empty:
        risky_cases = original_test.sort_values(by='predicted_exploit_prob', ascending=False).head(1)

    # Gerar testes
    with open("generated_vulnerabilities_tests.py", "w") as f:
        for idx, row in risky_cases.iterrows():
            vuln_row = df.iloc[row.name]  # linha original com dados da vulnerabilidade
            test_name = vuln_row['name'].replace(" ", "_").lower()

            f.write(f"def test_vulnerability_{idx}_{test_name}():\n")
            f.write(f"    # Device: {vuln_row['device_id']}\n")
            f.write(f"    # Vulnerability ID: {vuln_row['vuln_id']}\n")
            f.write(f"    # Severity: {vuln_row['severity']}\n")
            f.write(f"    # Predicted exploit probability: {row['predicted_exploit_prob']:.2f}\n")
            f.write(f"    exploit_vulnerability('{vuln_row['name']}')\n")
            f.write(f"    assert_device_resilient()\n\n")
