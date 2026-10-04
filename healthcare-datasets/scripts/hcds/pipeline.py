"""End-to-end run: acquire approved open datasets -> integrity/parse checks -> preprocessing validation -> catalogue.

    python -m hcds.pipeline --ids CLN-009          # fetch, validate and rebuild for one dataset
    python -m hcds.pipeline --dry-run              # show what the plan would do, fetch nothing

Preprocessing validation runs for datasets listed in catalog/parse_config.json; its outcome is appended to
logs/validation_log.csv as the ``preprocessing_validated`` stage.
"""
from __future__ import annotations

import argparse
import json
import logging

from . import LOG_DIR, ROOT
from .acquire import MANIFEST_PATH, acquire, read_plan
from .build_catalog import build
from .preprocess import validate_preprocessing
from .records import load_records
from .status import read_csv_rows
from .validate import PARSE_CONFIG, append_validation, read_tabular, validate_manifest


def preprocessing_stage(dataset_ids: set[str] | None = None) -> list[dict]:
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    successes = {r["dataset_id"]: r for r in read_csv_rows(MANIFEST_PATH) if r["download_status"] == "success"}
    results = []
    for dataset_id, cfg in config.items():
        if dataset_ids and dataset_id not in dataset_ids or dataset_id not in successes:
            continue
        frame = read_tabular(ROOT / successes[dataset_id]["local_path"], **cfg.get("read_options", {}))
        outcome = validate_preprocessing(frame, cfg["target"], group=cfg.get("group"), task=cfg.get("task", "classification"))
        entry = {"dataset_id": dataset_id, "stage": "preprocessing_validated", "ok": str(outcome["ok"]).lower(),
                 "details": json.dumps(outcome)}
        append_validation(entry)
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "acquisition.log"), logging.StreamHandler()])
    ids = set(args.ids) if args.ids else None
    acquired = acquire(read_plan(), load_records(), ids=ids, dry_run=args.dry_run)
    if args.dry_run:
        for row in acquired:
            print(row["dataset_id"], row["download_status"], row.get("error_or_reason", ""))
        return 0
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    fresh = {r["dataset_id"] for r in acquired if r["download_status"] == "success"}
    validate_manifest(
        targets={k: v["target"] for k, v in config.items() if k in fresh},
        read_options={k: v.get("read_options", {}) for k, v in config.items()},
        dataset_ids=fresh,
    )
    preprocessing_stage(fresh)
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
