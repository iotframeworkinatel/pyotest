# Emergence - IoT Network Vulnerability Scanner

**Emergence** is a Python-based framework for **scanning and testing IoT device vulnerabilities** across local networks.  
It supports scanning library (Nmap), tests insecure protocols, and helps map vulnerabilities against the **OWASP IoT Top 10**.

---

# 1. System Overview

### Functional overview
Emergence scans local networks for IoT devices, identifies open ports, and performs vulnerability tests.

- **IoT Security Testing**: Detect weak authentication, insecure APIs, open ports, and missing encryption.
- **Multi-Protocol Support**: MQTT, HTTP, Telnet, SSH, etc.
- **Test Automation**: Integration with CI/CD pipelines (GitHub Actions, Jenkins).
- **Containerized Execution**: Run tests in isolated Docker environments.
- **Detailed Reporting**: Export results in HTML, JSON, and CSV format.
- **Possible to use AutoML for anomaly detection and test case generation for high risk scenarios** (future feature).

### Non-Functional overview

- **Modularity**: Plugin-based architecture for easy extensibility.
- **Ease of Use**: Simple for developers to add new test cases.
- **Scalability**: Support for scanning multiple devices simultaneously.
- **Open Source**: Available on GitHub for public collaboration.

---

# 2. Core Libraries

- [`python-nmap`](https://pypi.org/project/python-nmap/): Nmap port scanning wrapper.
- [`requests`](https://requests.readthedocs.io/): API testing.
- [`paramiko`](http://www.paramiko.org/): SSH connections.
- [`h2o`](https://h2o.ai/platform/h2o-automl/): h2o AutoML library for anomaly detection (future feature).
- [`pandas`](https://pandas.pydata.org/): pandas data analysis library.
- [`scikit-learn`](https://scikit-learn.org/stable/): scikit-learn machine learning library (future feature).

You can install all dependencies with:

```bash
pip install -r requirements.txt
```

Make sure you also have **Nmap** installed on your system if using Nmap scans:

```bash
# Ubuntu/Debian
sudo apt install nmap

# macOS (Homebrew)
brew install nmap
```

Install on windows using the installer from the official Nmap website: [Nmap Download](https://nmap.org/download.html).

---

Make sure you also have **h2o** installed on your system if using h2o automl feature:

```bash
# Ubuntu/Debian
sudo apt install h2o

# macOS (Homebrew)
brew install h2o
```
---

# 3. How to Run the Scanner

Navigate to the project root and execute:

```bash
python . [OPTIONS]
```

### Available Options

| Option             | Description                                                            | Default                   |
|--------------------|------------------------------------------------------------------------|---------------------------|
| `-v`, `--verbose`  | Enable verbose logging                                                 | Off                       |
| `-n`, `--network`  | Network CIDR block to scan (e.g., `192.168.0.0/24`, `192.168.0.0-255`) | `192.168.0.0/24`          |
| `-o`, `--output`   | Output file format (e.g., `html`,`json`,`csv`)                         | None                      |
| `-p`, `--ports`    | Extra ports to scan (comma-separated, e.g., `80,443,8080`)             | None                      |
| `-t`, `--test`     | Run vulnerability tests on discovered devices                          | Off                       |
| `-aml`, `--automl` | Run AutoML to generate test cases for high risk scenarios              | Off                       |

---

# 4. Usage Examples

**Run a full scan without testing**:

```bash
# The scanner will scan the network for devices and open ports and show the results in the terminal.
python . -n 192.168.15.0/24
```

**Run a full scan with vulnerability testing**:

```bash
# The scanner will scan the network for devices, open ports, and run vulnerability tests on discovered devices.
python . -n 192.168.15.0/24 -t
```

**Run a full scan with vulnerability testing and save results in HTML format**:

```bash
# The scanner will scan the network for devices, open ports, run vulnerability tests, and save the results in HTML format.
python . -n 192.168.15.0/24 -t -o html
```

**Run a full scan with vulnerability testing and specify extra ports**:

```bash
# The scanner will scan the network for devices with additional specified ports.
python . -n 192.168.15.0/24 -p 123,456,7890
```

**Enable verbose mode (debugging output)**:

```bash
# The scanner will run in verbose mode, providing detailed output in the terminal.
python . -n 192.168.15.0/24 -v 
```

## 5. Running with Docker - Simulation

**Run a simulation with Docker**:

You must have Docker installed on your system.

Docker Installation instructions can be found here: [Docker Installation](https://docs.docker.com/get-docker/).

```bash
docker-compose up --build 
```

- The scanner will run a simulated environment with a mock IoT device and perform vulnerability tests.
- The results will be saved in the `reports` folder in the project root.
---


## 6. Reproducing the Published Results

Every statistic reported in the Emergence papers can be regenerated from the
data committed in this repository. There are two paths: a quick one that
recomputes the results from the published data in under a minute, and a full
one that reruns the experimental campaign from scratch.

### 6.1 Published data

| File | Contents |
|------|----------|
| `experiments/emergence.db` | DuckDB database with the full execution history (one row per test execution), tagged by `phase`, `simulation_mode`, `simulation_seed`, `automl_tool` and `baseline_strategy` |
| `experiments/aggregated_history_lopo_{deterministic,realistic}.csv` | Aggregated histories used for the leave-one-protocol-out (LOPO) and per-protocol analyses |
| `experiments/aggregated_history_medium_autogluon{,_phase6}_s42.csv` | Aggregated histories for the AutoGluon medium-mode runs (Phases 1 and 6) |
| `models/archive/<framework>_<mode>[_phaseN]/model_metrics.json` | Validation metrics (AUC, log-loss, calibration, cross-validation, leaderboard) of every trained model. Model binaries are not included |
| `hypothesis_results.json` | Output of `analysis/compute_hypotheses.py` (hypotheses H1–H11) |
| `lopo_results.json` | LOPO results written by `run_experiments.py` (Phase 4) |

### 6.2 Quick path: recompute the results from the published data

Requires Python 3.11 or later (tested with Python 3.14.0). Docker is not needed.

```bash
git clone https://github.com/iotframeworkinatel/pyotest.git
cd pyotest
python -m venv .venv-analysis
# Windows: .venv-analysis\Scripts\activate   Linux/macOS: source .venv-analysis/bin/activate
pip install -r analysis/requirements.txt
python analysis/run_all.py
git diff --stat hypothesis_results.json analysis/output/   # no changes = results reproduced
```

`run_all.py` runs the scripts below. Each script's console output is saved in
`analysis/output/`, and the committed copies of those files are the reference
output.

| Script | Produces |
|--------|----------|
| `analysis/compute_hypotheses.py` | H1–H11 statistics (detection stability, ML discrimination and recommended vs non-recommended lift, calibration ECE/Brier, efficiency ratio, protocol convergence, baseline comparison) → `hypothesis_results.json` |
| `analysis/h9_matched_budget.py` | Matched-budget bootstrap of ML vs the four baselines (seed 42) |
| `analysis/lopo_auc.py` | Per-protocol LOPO AUC computed from the aggregated CSVs |
| `analysis/paper_facts.py` | Row counts, detection rates per strategy and mode, model AUCs from `models/archive` |
| `analysis/paper_facts_extra.py` | Per-protocol counts, unique-combination counts and discovery velocity |

### 6.3 Full path: rerun the experimental campaign

The campaign drives 13 emulated devices through the simulation profiles and
trains five AutoML frameworks. It requires Docker (with Docker Compose) and
takes several days: about 35 hours for the 1,500 core framework iterations
alone.

1. Copy `.env.example` to `.env`. API keys are needed only for the LLM
   test-generation phase; skip it with `--skip-llm`.
2. Start the stack: `docker compose up -d --build`
3. Run the campaign: `python run_experiments.py`

> **Warning:** without `--resume`, `run_experiments.py` deletes the existing
> `experiments/exp_*` directories and aggregated histories before starting.
> Work on a fresh clone.

Useful flags: `--quick` (5 iterations per run, as a smoke test), `--resume`
(continue after a crash; incomplete runs are restarted from scratch),
`--skip-baselines`, `--skip-llm`, `--skip-lopo`, `--skip-phase5`,
`--skip-phase6`, and `--rebuild-db` (rebuild `experiments/emergence.db` from
the run directories).

Simulation profiles and seeds (`run_experiments.py`, `simulation/profiles.py`):
deterministic, medium and realistic with seed 42, plus realistic with seeds
123 and 777 for seed robustness; 100 iterations per run, retraining every 10
iterations.

Software versions: the AutoML containers are pinned to the versions used in
the experiments, as recorded in the saved models (AutoGluon 1.5.0, PyCaret
3.3.2 with scikit-learn 1.4.2, auto-sklearn 0.15.0 with scikit-learn 0.24.2,
H2O 3.46.0.9). Each AutoML training call uses seed 42 and a 300-second time
budget (`max_runtime_secs`; 60 seconds for the LOPO retraining in Phase 4).
Because a time-budgeted search explores a different number of models on
different hardware, a full rerun reproduces the results statistically rather
than bit-for-bit. The quick path above reproduces them exactly.

<!-- TODO(author): add the hardware used for the campaign (CPU, cores, RAM, OS)
     and the total wall-clock time. -->

---

## 7. Contributing
We welcome contributions! Please follow these steps:

1. Fork the repository.
2. Create a new branch: `git checkout -b my-branch`.
3. Make your changes.
4. Commit your changes: `git commit -am "Add my changes"`.
5. Push your branch: `git push origin my-branch`.
6. Create a pull request.