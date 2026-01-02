import h2o
from h2o.automl import H2OAutoML
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


OUT_DIR = Path("generated_tests")
TEMPLATE_DIR = Path("templates")


def generate_tests(iot_devices):
    """
    Gera arquivos de teste Python executáveis a partir dos dispositivos IoT
    e suas vulnerabilidades detectadas, escolhendo o template por protocolo.
    """

    # =========================
    # Inicialização do H2O
    # =========================
    try:
        h2o.init()
    except Exception as e:
        print("[AML] Erro ao iniciar H2O:", e)
        print("[AML] Etapa AutoML abortada")
        return

    # =========================
    # Coleta dos dados
    # =========================
    ips = []
    hostnames = []
    ports = []
    vulns = []

    for dev in iot_devices:
        for vuln in dev.vulnerabilities:
            ips.append(dev.ip)
            hostnames.append(dev.hostname)
            ports.append(",".join(map(str, dev.ports)))
            vulns.append(vuln)

    print("[AML] Dataset size:", len(vulns))

    if not vulns:
        print("[AML] Nenhuma vulnerabilidade encontrada")
        return

    # =========================
    # Criação do H2OFrame
    # =========================
    frame = h2o.H2OFrame({
        "ip": ips,
        "hostname": hostnames,
        "ports": ports,
        "vulnerabilities": vulns
    })

    print("[AML] Frame columns:", frame.col_names)

    frame["vulnerabilities"] = frame["vulnerabilities"].asfactor()

    # =========================
    # AutoML (pipeline base)
    # =========================
    aml = H2OAutoML(
        max_models=5,
        max_runtime_secs=30,
        seed=1
    )

    aml.train(
        y="vulnerabilities",
        training_frame=frame
    )

    # =========================
    # Ambiente de templates
    # =========================
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=False
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # =========================
    # Geração dos testes
    # =========================
    generated_files = []

    for i in range(len(vulns)):
        vuln_text = vulns[i].lower()

        # Seleção do template por protocolo
        if "ftp" in vuln_text:
            template_name = "ftp_test.py.j2"
        elif "http" in vuln_text or "directory" in vuln_text:
            template_name = "http_test.py.j2"
        elif "mqtt" in vuln_text:
            template_name = "mqtt_test.py.j2"
        elif "telnet" in vuln_text:
            template_name = "telnet_test.py.j2"
        elif "ssh" in vuln_text:
            template_name = "ssh_test.py.j2"
        else:
            template_name = "generic_test.py.j2"

        template = env.get_template(template_name)

        filename = (
            f"test_{ips[i]}_{vulns[i]}"
            .lower()
            .replace(" ", "_")
            .replace(".", "_")
        )

        filepath = OUT_DIR / f"{filename}.py"

        code = template.render(v={
            "ip": ips[i],
            "hostname": hostnames[i],
            "ports": ports[i],
            "vulnerabilities": vulns[i]
        })

        try:
            filepath.write_text(code)
            if filepath.exists():
                generated_files.append(filepath)
        except Exception as e:
            print(f"[AML] Falha ao gerar {filepath.name}: {e}")

    # =========================
    # Mensagem final confiável
    # =========================
    if generated_files:
        print(f"[AML] {len(generated_files)} testes gerados com sucesso:")
        for f in generated_files:
            print(f"  - {f}")
    else:
        print("[AML] Nenhum teste foi gerado")
