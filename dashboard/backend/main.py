import os
import docker
import json
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra

app = FastAPI(title="IoT Vulnerability Dashboard API")

# CORS liberado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_client = docker.from_env()

EXPERIMENTS_PATH = "/app/experiments"
SCANNER_CONTAINER_NAME = "scanner"


# =============================
# 🔧 MODELO DE REQUISIÇÃO
# =============================
class ExperimentRequest(BaseModel, extra=Extra.allow):
    mode: str  # "static" ou "automl"
    network: str = "172.20.0.0/27"
    output: str = "html"
    ports: str = ""
    verbose: bool = False
    test: bool = False
    automl: bool = False


# =============================
# 🔹 ROTAS BÁSICAS
# =============================
@app.get("/")
def root():
    return {"status": "ok", "message": "Dashboard API online"}


@app.get("/experiments")
def list_experiments():
    """Lista experimentos existentes"""
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"experiments": []}
    exps = [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    return {"experiments": sorted(exps, reverse=True)}


# =============================
# 🔹 LOGS UNIFICADOS DE TODOS OS CONTAINERS
# =============================
@app.get("/logs")
def get_all_logs():
    """
    Junta logs do scanner e de todos os containers de teste em execução.
    """
    try:
        all_containers = docker_client.containers.list()
        logs_summary = ""

        for c in all_containers:
            name = c.name
            # inclui scanner + containers de testes com prefixos comuns
            if name.startswith(
                (
                    "scanner",
                    "http_",
                    "ftp_",
                    "mqtt_",
                    "telnet_",
                    "modbus_",
                    "coap_",
                    "dashboard_ui",
                    "h2o_"
                )
            ):
                try:
                    logs = c.logs(tail=15).decode(errors="ignore")
                    if logs.strip():
                        logs_summary += f"\n=== [{name}] ===\n{logs}\n"
                except Exception as e:
                    logs_summary += f"\n[{name}] Erro ao ler logs: {e}\n"

        return {"logs": logs_summary or "Nenhum log disponível no momento."}

    except Exception as e:
        return {"error": str(e)}


# =============================
# 🔹 EXECUTAR EXPERIMENTO
# =============================
@app.post("/experiments/run")
def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    """Executa comando dentro do container scanner já em execução"""

    cmd_parts = ["python3", ".", "-n", req.network]

    # parâmetros opcionais
    if req.verbose:
        cmd_parts.append("-v")
    if req.test:
        cmd_parts.append("-t")
    if req.output:
        cmd_parts += ["-o", req.output]
    if req.ports:
        cmd_parts += ["-p", req.ports]
    if req.automl or req.mode == "automl":
        cmd_parts.append("-aml")

    cmd_str = " ".join(cmd_parts)

    def _exec():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            print(f"[API] Executando no container '{SCANNER_CONTAINER_NAME}': {cmd_str}")
            container.exec_run(cmd_str, detach=True, workdir="/app")
        except Exception as e:
            print(f"[ERRO] Falha ao executar experimento: {e}")

    background_tasks.add_task(_exec)

    return {
        "status": "started",
        "mode": req.mode,
        "network": req.network,
        "command": cmd_str,
    }


# =============================
# 🔹 MÉTRICAS
# =============================
@app.get("/metrics")
def get_latest_metrics():
    """Lê métricas do último experimento"""
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"metrics": []}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )
    if not exps:
        return {"metrics": []}

    latest = os.path.join(EXPERIMENTS_PATH, exps[0])
    result = []
    for file in ["metrics_static.json", "metrics_automl.json"]:
        path = os.path.join(latest, file)
        if os.path.exists(path):
            with open(path) as f:
                try:
                    data = json.load(f)
                    result.append(data)
                except:
                    pass
    return {"metrics": result}


# =============================
# 🔹 HISTÓRICO DE EXPERIMENTOS
# =============================
@app.get("/history")
def get_history():
    """Retorna histórico de todos os experimentos"""
    history = []
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"history": []}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )

    for exp in exps:
        exp_path = os.path.join(EXPERIMENTS_PATH, exp)
        for file in ["metrics_static.json", "metrics_automl.json"]:
            path = os.path.join(exp_path, file)
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                        data["experiment"] = exp
                        history.append(data)
                except:
                    pass

    return {
        "history": sorted(
            history, key=lambda x: x.get("exec_time_sec", 0), reverse=True
        )
    }
