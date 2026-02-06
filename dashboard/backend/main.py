import os
import docker
import json
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


class ExperimentRequest(BaseModel):
    mode: str
    network: str = "172.20.0.0/27"
    extra_args: list[str] = []


@app.get("/")
def root():
    return {"status": "ok", "message": "Dashboard API online"}


@app.get("/experiments")
def list_experiments():
    if not os.path.exists(EXPERIMENTS_PATH):
        return {"experiments": []}
    exps = [f for f in os.listdir(EXPERIMENTS_PATH) if f.startswith("exp_")]
    return {"experiments": sorted(exps, reverse=True)}


@app.get("/logs")
def get_logs():
    """
    Retorna os logs recentes de todos os containers Docker ativos
    (para o dashboard exibir em tempo real).
    """
    try:
        containers = docker_client.containers.list()
        logs_data = {}

        for c in containers:
            try:
                logs_data[c.name] = c.logs(tail=40).decode(errors="ignore")
            except Exception as e:
                logs_data[c.name] = f"[Erro ao ler logs: {e}]"

        return {"containers": list(logs_data.keys()), "logs": logs_data}

    except Exception as e:
        return {"error": str(e)}


@app.post("/experiments/run")
def run_experiment(req: ExperimentRequest, background_tasks: BackgroundTasks):
    cmd_parts = ["python3", ".", "-n", req.network]
    if req.mode == "automl":
        cmd_parts.append("-aml")

    extra_args = getattr(req, "extra_args", [])
    if isinstance(extra_args, list):
        cmd_parts.extend(extra_args)

    cmd_str = " ".join(cmd_parts)

    def _exec():
        try:
            container = docker_client.containers.get(SCANNER_CONTAINER_NAME)
            print(f"[API] Executando: {cmd_str}")
            container.exec_run(cmd_str, detach=True, workdir="/app")
        except Exception as e:
            print(f"[ERRO] Falha ao executar experimento: {e}")

    background_tasks.add_task(_exec)
    return {"status": "started", "command": cmd_str}


@app.get("/metrics")
def get_latest_metrics():
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
                    result.append(json.load(f))
                except:
                    pass
    return {"metrics": result}


@app.get("/history")
def get_history():
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
    return {"history": sorted(history, key=lambda x: x.get("exec_time_sec", 0), reverse=True)}
