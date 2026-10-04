# Experiments

- `classical_ml/`, `quantum_ml/`, `hybrid_models/` hold experiment-specific notebooks or configs as they are added.
- `results/` holds measured outputs: `<name>_folds.csv` (per fold), `<name>_summary.csv` (mean ± SD) and `<name>_run.json` (data size, seeds and environment).
- The runner is `scripts/hcds/benchmark.py`; the plan and the E1 results are in `documentation/experiment_plan.md`.
