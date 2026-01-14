import os
import docker
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ------------------------------------------------------------
# 🚀 Configuração principal
# ------------------------------------------------------------
app = FastAPI(title="IoT Vulnerability Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem (ideal em Docker)
    allow_methods=["*"],
    allow_headers=["*"],
)

docker_client = docker.from_env()

EXPERIMENTS_PATH = "/app/experiments"
SCANNER_CONTAINER_NAME = "scanner"  # nome definido no docker-compose


# ------------------------------------------------------------
# 🧩 Modelos de dados
# ------------------------------------------------------------
class ExperimentRequest(BaseModel):
    mode: str  # "static" ou "automl"
    network: str = "172.20.0.0/27"


# ------------------------------------------------------------
# 🌐 Rotas principais
# ------------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "Dashboard API online"}


@app.get("/experiments")
def list_experiments():
    """Lista os experimentos existentes"""
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"experiments": []}
    exps = [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    return {"experiments": sorted(exps, reverse=True)}


@app.get("/experiments/latest/{file}")
def latest_experiment_file(file: str):
    """Retorna o conteúdo de um arquivo (como metrics_static.json)"""
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"detail": "Nenhum experimento encontrado"}

    exps = sorted(
        [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")],
        reverse=True,
    )
    if not exps:
        return {"detail": "Nenhum experimento encontrado"}

    path = os.path.join(EXPERIMENTS_PATH, exps[0], file)
    if not os.path.exists(path):
        return {"detail": f"{file} não encontrado em {exps[0]}"}

    with open(path, "r") as f:
        return f.read()


# ------------------------------------------------------------
# ⚙️ Execução de experimentos no container scanner
# ------------------------------------------------------------
@app.post("/experiments/run")
def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    """Executa comando dentro do container scanner existente"""
    def _exec():
        try:
            cmd = f"python3 . -n {req.network} -o html"
            if req.mode == "automl":
                cmd += " -aml"

            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            print(f"[API] Executando no container '{SCANNER_CONTAINER_NAME}': {cmd}")
            container.exec_run(cmd, detach=True, workdir="/app")

        except Exception as e:
            print(f"[ERRO] Falha ao executar comando: {e}")

    background_tasks.add_task(_exec)
    return {"status": "started", "mode": req.mode, "network": req.network}


# ------------------------------------------------------------
# 🔍 Logs recentes do container scanner
# ------------------------------------------------------------
@app.get("/logs")
def get_scanner_logs():
    """Mostra os últimos logs do container scanner"""
    try:
        container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
        logs = container.logs(tail=30).decode()
        return {"logs": logs}
    except Exception as e:
        return {"error": str(e)}
