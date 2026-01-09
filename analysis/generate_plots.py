import json
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


EXPERIMENTS_DIR = Path("experiments")


def get_latest_experiment():
    exps = sorted(
        [d for d in EXPERIMENTS_DIR.iterdir() if d.is_dir() and d.name.startswith("exp_")]
    )

    if not exps:
        raise RuntimeError("No experiments found")

    return exps[-1]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def plot_efficiency(static, automl, outdir):
    labels = ["Static", "AutoML"]
    values = [
        static["vulns_detected"] / static["tests_executed"],
        automl["vulns_detected"] / automl["tests_executed"],
    ]

    plt.figure()
    plt.bar(labels, values)
    plt.ylabel("Vulnerabilities per Test")
    plt.title("Efficiency Comparison")
    plt.savefig(outdir / "efficiency.png")
    plt.close()


def plot_execution_time(static, automl, outdir):
    labels = ["Static", "AutoML"]
    values = [
        static["exec_time_sec"],
        automl["exec_time_sec"],
    ]

    plt.figure()
    plt.bar(labels, values)
    plt.ylabel("Execution Time (ms)")
    plt.title("Execution Time Comparison")
    plt.savefig(outdir / "execution_time.png")
    plt.close()


def plot_vulns_by_protocol(history, outdir):
    df = history[history["vulnerability_found"] == 1]
    grouped = df.groupby(["test_strategy", "protocol"]).size().unstack(fill_value=0)

    grouped.plot(kind="bar", stacked=True)
    plt.ylabel("Vulnerabilities Found")
    plt.title("Vulnerabilities by Protocol")
    plt.tight_layout()
    plt.savefig(outdir / "vulns_by_protocol.png")
    plt.close()


def plot_cumulative_vulns(history, outdir):
    history = history.sort_values("timestamp")
    history["cum_vulns"] = history.groupby("test_strategy")["vulnerability_found"].cumsum()

    plt.figure()
    for strategy in history["test_strategy"].unique():
        subset = history[history["test_strategy"] == strategy]
        plt.plot(subset.index, subset["cum_vulns"], label=strategy)

    plt.xlabel("Test Execution Order")
    plt.ylabel("Cumulative Vulnerabilities")
    plt.title("Cumulative Vulnerabilities Over Time")
    plt.legend()
    plt.savefig(outdir / "cumulative_vulns.png")
    plt.close()


def generate_plots():
    exp = get_latest_experiment()
    print(f"Using latest experiment: {exp.name}")

    static_metrics = load_json(exp / "metrics_static.json")
    automl_metrics = load_json(exp / "metrics_automl.json")
    history = pd.read_csv(exp / "history.csv")

    plots_dir = exp / "plots"
    plots_dir.mkdir(exist_ok=True)

    plot_efficiency(static_metrics, automl_metrics, plots_dir)
    plot_execution_time(static_metrics, automl_metrics, plots_dir)
    plot_vulns_by_protocol(history, plots_dir)
    plot_cumulative_vulns(history, plots_dir)

    print(f"Plots generated in: {plots_dir.resolve()}")
