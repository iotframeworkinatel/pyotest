"""Regenerate every statistic reported in the papers from the published data.

Usage (from any directory):
    python analysis/run_all.py

Each script's console output is saved to analysis/output/<script>.txt, and
compute_hypotheses.py rewrites hypothesis_results.json at the repository root.
Compare both against the committed versions (e.g. `git diff`) to confirm the
results reproduce.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "output"
SCRIPTS = [
    "compute_hypotheses.py",   # H1-H11 statistics -> hypothesis_results.json
    "h9_matched_budget.py",    # matched-budget bootstrap (ML vs baselines)
    "lopo_auc.py",             # leave-one-protocol-out AUC from aggregated CSVs
    "paper_facts.py",          # detection rates, row counts, model metrics
    "paper_facts_extra.py",    # per-protocol and per-iteration figures
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = []
    for name in SCRIPTS:
        start = time.time()
        log = OUT / name.replace(".py", ".txt")
        with log.open("w", encoding="utf-8") as fh:
            rc = subprocess.call([sys.executable, str(ROOT / "analysis" / name)],
                                 cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
        status = "ok" if rc == 0 else f"FAILED (exit {rc})"
        print(f"{name:24s} {status:16s} {time.time() - start:6.1f}s -> {log.relative_to(ROOT)}")
        if rc != 0:
            failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
