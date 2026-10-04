# Experiments

- `classical_ml/`, `quantum_ml/`, `hybrid_models/` hold experiment-specific notebooks or configs as they are added.
- `results/` holds measured outputs: `<name>_folds.csv` (per fold; `_runs.csv` for E7), `<name>_summary.csv` (mean ± SD), `<name>_tests.csv` (Nadeau–Bengio corrected t-tests, E2–E4) and `<name>_run.json` (data notes, seeds and environment).
- Runners: `scripts/hcds/benchmark.py` (E1), `scripts/hcds/experiments.py` (E2–E4) and `scripts/hcds/ecg.py` (E7). The plan and all results are in `documentation/experiment_plan.md`.
