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
from .validate import PARSE_CONFIG, append_validation, file_config, read_tabular, validate_manifest


def preprocessing_stage(dataset_ids: set[str] | None = None) -> list[dict]:
    """Run the leakage checks on every successfully acquired tabular file that has a target in parse_config."""
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    results = []
    for row in read_csv_rows(MANIFEST_PATH):
        dataset_id = row["dataset_id"]
        if row["download_status"] != "success" or dataset_id not in config:
            continue
        if dataset_ids and dataset_id not in dataset_ids:
            continue
        path = ROOT / row["local_path"]
        cfg = file_config(config, dataset_id, path.name)
        if "target" not in cfg or cfg.get("parse") is False or cfg.get("format"):
            continue
        try:
            frame = read_tabular(path, **cfg.get("read_options", {}))
            frame = frame.drop(columns=[c for c in cfg.get("drop_columns", []) if c in frame.columns])
            outcome = validate_preprocessing(frame, cfg["target"], group=cfg.get("group"),
                                             task=cfg.get("task", "classification"))
            entry = {"dataset_id": dataset_id, "stage": "preprocessing_validated", "ok": str(outcome["ok"]).lower(),
                     "details": json.dumps({"file": path.name, **outcome})}
        except Exception as error:  # logged as a failed stage, never swallowed
            entry = {"dataset_id": dataset_id, "stage": "preprocessing_validated", "ok": "false",
                     "details": f"{path.name}: {type(error).__name__}: {error}"[:2000]}
        append_validation(entry)
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true",
                        help="Skip downloading; re-run integrity, parsing and preprocessing checks on acquired files")
    args = parser.parse_args(argv)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "acquisition.log"), logging.StreamHandler()])
    ids = set(args.ids) if args.ids else None
    config = json.loads(PARSE_CONFIG.read_text()) if PARSE_CONFIG.exists() else {}
    if args.validate_only:
        validate_manifest(config=config, dataset_ids=ids)
        preprocessing_stage(ids)
        return build()
    acquired = acquire(read_plan(), load_records(), ids=ids, dry_run=args.dry_run)
    if args.dry_run:
        for row in acquired:
            print(row["dataset_id"], row["download_status"], row.get("error_or_reason", ""))
        return 0
    fresh = {r["dataset_id"] for r in acquired if r["download_status"] == "success"}
    validate_manifest(config=config, dataset_ids=fresh)
    preprocessing_stage(fresh)
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
