import h2o
from h2o.automl import H2OAutoML
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import json
import time
from utils.metrics import save_metrics
from utils.automl_tester import automl_tester
from utils.junit_parser import parse_junit
from utils.automl_postprocess import apply_automl_results
from reports import html  # ajuste o import
from reports import Report
from utils.junit_to_tests import parse_junit_tests

OUT_DIR = Path("generated_tests")
TEMPLATE_DIR = Path("templates")
HISTORY_FILE = Path("auto_ml_history/history.json")
AUTOML_REPORT_DIR = Path("report/automl")


# =========================
# Histórico
# =========================
def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return []


def save_history(entry):
    HISTORY_FILE.parent.mkdir(exist_ok=True)
    history = load_history()
    history.append(entry)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))

REQUIRED_COLS = [
    "port_count",
    "has_ftp",
    "has_ssh",
    "has_telnet",
    "has_http",
    "has_mqtt",
    "vuln_len",
    "use_test",
]


# =========================
# Feature engineering
# =========================
def build_features(device, vulnerability):
    v = vulnerability.upper()

    return {
        "port_count": len(device.ports),
        "has_ftp": "FTP" in v,
        "has_ssh": "SSH" in v,
        "has_telnet": "TELNET" in v,
        "has_http": "HTTP" in v,
        "has_mqtt": "MQTT" in v,
        "vuln_len": len(v)
    }



# =========================
# AutoML model
# =========================
def train_model(frame):
    aml = H2OAutoML(
        max_models=10,
        max_runtime_secs=60,
        seed=1
    )
    aml.train(y="use_test", training_frame=frame)
    return aml.leader


# =========================
# Decide se gera o teste
# =========================
def should_generate_test(model, features):
    row = [[
        str(features["port_count"]),
        str(features["has_ftp"]),
        str(features["has_ssh"]),
        str(features["has_telnet"]),
        str(features["has_http"]),
        str(features["has_mqtt"]),
        str(features["vuln_len"]),
    ]]

    frame = h2o.H2OFrame(row, column_names=REQUIRED_COLS)
    pred = model.predict(frame).as_data_frame()

    return pred.iloc[0, 0] == "1"


# =========================
# Entry point
# =========================
def generate_tests(iot_devices, args):

    start_time = time.time()

    # ---------- H2O ----------
    try:
        h2o.init()
    except Exception as e:
        print("[AML] H2O indisponível:", e)
        return

    # ---------- Histórico ----------
    history = load_history()

    # ---------- Dataset para treino ----------
    rows = []
    for h in history:
        rows.append(h)

    model = None

    # === Normalização do histórico ===
    normalized = []

    for r in history:
        if "use_test" not in r:
            continue

        row = [
            str(r.get("port_count", 0)),
            str(r.get("has_ftp", False)),
            str(r.get("has_ssh", False)),
            str(r.get("has_telnet", False)),
            str(r.get("has_http", False)),
            str(r.get("has_mqtt", False)),
            str(r.get("vuln_len", 0)),
            str(r.get("use_test")),
        ]

        normalized.append(row)

    print(f"[AML][DEBUG] Histórico normalizado: {len(normalized)} linhas")

    if len({r[-1] for r in normalized}) < 2:
        print("[AML] Bootstrap: rótulos insuficientes")
    else:
        frame = h2o.H2OFrame(normalized, column_names=REQUIRED_COLS)
        frame["use_test"] = frame["use_test"].asfactor()
        model = train_model(frame)
        print("[AML] Modelo AutoML treinado com sucesso")


    # ---------- Templates ----------
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    generated = []

    # ---------- Loop principal ----------
    for dev in iot_devices:
        for vuln in dev.vulnerabilities:

            features = build_features(dev, vuln)

            # AutoML decide
            if model:
                if not should_generate_test(model, features):
                    continue

            # Seleção de template
            v = vuln.lower()
            if "ftp" in v:
                tpl = "ftp_test.py.j2"
            elif "http" in v or "directory" in v:
                tpl = "http_test.py.j2"
            elif "mqtt" in v:
                tpl = "mqtt_test.py.j2"
            elif "telnet" in v:
                tpl = "telnet_test.py.j2"
            elif "ssh" in v:
                tpl = "ssh_test.py.j2"
            else:
                tpl = "generic_test.py.j2"

            template = env.get_template(tpl)

            fname = (
                f"test_{dev.ip}_{vuln}"
                .lower().replace(" ", "_").replace(".", "_")
            )

            path = OUT_DIR / f"{fname}.py"

            path.write_text(template.render(v={
                "ip": dev.ip,
                "hostname": dev.hostname,
                "ports": ",".join(map(str, dev.ports)),
                "vulnerabilities": vuln
            }))

            if path.exists():
                generated.append(path)


    # ---------- Log confiável ----------
    if generated:
        print(f"[AML] {len(generated)} testes gerados (AutoML-guided):")
        for g in generated:
            print(f"  - {g}")
    else:
        print("[AML] Nenhum teste selecionado pelo AutoML")

    result = automl_tester(OUT_DIR, AUTOML_REPORT_DIR)

    # Aplica resultados reais dos testes
    apply_automl_results(
        iot_devices,
        AUTOML_REPORT_DIR / "automl_tests.xml"
    )

    # Gera relatório HTML FINAL (mesma classe do static)
    ext = args.output.lower()
    report = Report(args.network, iot_devices, ext)
    html.report(report, "automl")

    junit_results = parse_junit(
        AUTOML_REPORT_DIR / "automl_tests.xml"
    )

    total_time = time.time() - start_time

    save_metrics({
        "mode": "automl",
        "devices": len(iot_devices),
        "tests_generated": len(generated),
        "tests_executed": junit_results["passed"] + junit_results["failed"],
        "vulns_detected": junit_results["passed"],
        "false_positives": junit_results["failed"],
        "exec_time_sec": total_time,
        "test_exec_time_sec": result["duration_sec"]
    })

    # Aprendizado supervisionado real (pós-execução)
    test_results = parse_junit_tests(AUTOML_REPORT_DIR / "automl_tests.xml")

    for t in test_results:
        # Ignora testes não executáveis
        if t.status == "SKIP":
            continue

        save_history({
            "port_count": 1,  # teste por porta
            "has_ftp": t.vuln_id == "FTP_ANON_LOGIN",
            "has_ssh": t.vuln_id == "SSH_WEAK_CREDS",
            "has_telnet": t.vuln_id == "TELNET_OPEN",
            "has_http": t.vuln_id.startswith("HTTP"),
            "has_mqtt": t.vuln_id == "MQTT_ANON_ACCESS",
            "vuln_len": len(t.vuln_id),
            "use_test": 1 if t.status == "PASS" else 0,
        })

