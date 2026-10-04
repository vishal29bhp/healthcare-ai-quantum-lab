"""Responsible, resumable acquisition of openly licensed datasets.

Only rows of ``catalog/acquisition_plan.csv`` that are (a) marked ``approved=yes`` or selected with ``--ids``,
and (b) catalogued with ``access_level == "open"`` are fetched. Registration-, credential-, DUA- or
competition-gated datasets are never downloaded: they get a manifest row with status ``not_attempted``
and the documented next step instead. No credentials are read, stored or logged by this module.

Every attempt appends a row to ``catalog/acquisition_manifest.csv``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import CATALOG_DIR, LOG_DIR, ROOT
from .records import load_records
from .schema import CATEGORIES, MANIFEST_COLUMNS

PLAN_PATH = CATALOG_DIR / "acquisition_plan.csv"
MANIFEST_PATH = CATALOG_DIR / "acquisition_manifest.csv"
RAW_SUBDIR = "raw"  # <category>/<subcategory>/raw/<dataset_id>/ — git-ignored
USER_AGENT = "healthcare-datasets-catalogue/0.1 (research; metadata-first)"
CHUNK = 1 << 16

log = logging.getLogger("hcds.acquire")


@dataclass
class PlanRow:
    dataset_id: str
    url: str
    filename: str
    method: str  # "https" or "sklearn_bundled"
    expected_sha256: str = ""
    expected_md5: str = ""
    approved: bool = False
    notes: str = ""


def read_plan(path: Path = PLAN_PATH) -> list[PlanRow]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            PlanRow(
                dataset_id=row["dataset_id"].strip(),
                url=row["url"].strip(),
                filename=row["filename"].strip(),
                method=row.get("method", "https").strip() or "https",
                expected_sha256=row.get("expected_sha256", "").strip().lower(),
                expected_md5=row.get("expected_md5", "").strip().lower(),
                approved=row.get("approved", "").strip().lower() == "yes",
                notes=row.get("notes", "").strip(),
            )
            for row in csv.DictReader(handle)
        ]


def file_digest(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def target_dir(record: dict) -> Path:
    category_dir = CATEGORIES[record["category"]]
    return ROOT / category_dir / record["subcategory"] / RAW_SUBDIR / record["dataset_id"]


def append_manifest(row: dict, path: Path = MANIFEST_PATH) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in MANIFEST_COLUMNS})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact(url: str) -> str:
    """Drop query strings so tokens passed as parameters can never reach logs or the manifest."""
    return url.split("?", 1)[0] + ("?<redacted>" if "?" in url else "")


class RateLimiter:
    def __init__(self, min_interval_s: float) -> None:
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def wait(self) -> None:
        delay = self._last + self.min_interval_s - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()


def download_https(url: str, dest: Path, limiter: RateLimiter, retries: int = 4, timeout: int = 60) -> None:
    """Download with resume (HTTP Range on a .part file) and exponential-backoff retries."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries + 1):
        limiter.wait()
        offset = part.stat().st_size if part.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if offset:
            request.add_header("Range", f"bytes={offset}-")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                mode = "ab" if offset and response.status == 206 else "wb"
                with part.open(mode) as handle:
                    shutil.copyfileobj(response, handle, CHUNK)
            part.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code in (401, 403, 404, 407, 451):
                raise  # access or policy problem: retrying will not help and must not be worked around
            if attempt == retries:
                raise
            backoff = 2 ** (attempt + 1)
            log.warning("attempt %d for %s failed (%s); retrying in %ss", attempt + 1, _redact(url), error, backoff)
            time.sleep(backoff)


def copy_sklearn_bundled(filename: str, dest: Path) -> str:
    """Copy a file shipped inside the installed scikit-learn package (a redistributed mirror)."""
    import sklearn
    import sklearn.datasets

    source = Path(sklearn.datasets.__file__).parent / "data" / filename
    if not source.exists():
        raise FileNotFoundError(f"{filename} is not bundled with scikit-learn {sklearn.__version__}")
    shutil.copyfile(source, dest)
    return f"scikit-learn {sklearn.__version__} package data"


def acquire(rows: list[PlanRow], records: dict[str, dict], *, ids: set[str] | None = None,
            min_interval_s: float = 2.0, manifest_path: Path = MANIFEST_PATH, dry_run: bool = False) -> list[dict]:
    limiter = RateLimiter(min_interval_s)
    seen_hashes: dict[str, str] = {}
    results = []
    for row in rows:
        if ids is not None and row.dataset_id not in ids:
            continue
        record = records.get(row.dataset_id)
        entry = {
            "dataset_id": row.dataset_id,
            "source_url": _redact(row.url),
            "acquisition_method": row.method,
            "access_prerequisites": (record or {}).get("access_prerequisites", "Not reported"),
            "requested_files": row.filename,
            "version": (record or {}).get("version", "Not reported"),
            "expected_checksum": row.expected_sha256 or (f"md5:{row.expected_md5}" if row.expected_md5 else ""),
            "timestamp_utc": _now(),
        }
        if record is None:
            entry.update(download_status="skipped", error_or_reason="Dataset ID not found in catalogue records")
        elif record.get("access_level") != "open":
            entry.update(
                download_status="not_attempted",
                error_or_reason=f"access_level={record.get('access_level')}: follow access guide; never bypassed",
            )
        elif not (row.approved or (ids is not None and row.dataset_id in ids)):
            entry.update(download_status="not_attempted", error_or_reason="Awaiting user approval (approved != yes)")
        elif dry_run:
            entry.update(download_status="planned", error_or_reason="Dry run")
        else:
            dest_dir = target_dir(record)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / row.filename
            entry["local_path"] = str(dest.relative_to(ROOT))
            try:
                if row.method == "sklearn_bundled":
                    source_name = row.url.rsplit("/", 1)[-1]
                    entry["acquisition_method"] = f"sklearn_bundled ({copy_sklearn_bundled(source_name, dest)})"
                elif dest.exists() and row.expected_sha256 and file_digest(dest) == row.expected_sha256:
                    log.info("%s already present with matching checksum; not re-downloading", dest.name)
                else:
                    download_https(row.url, dest, limiter)
                sha = file_digest(dest)
                entry.update(file_size_bytes=dest.stat().st_size, sha256=sha)
                if row.expected_sha256 and sha != row.expected_sha256:
                    entry.update(download_status="checksum_mismatch", error_or_reason="SHA-256 differs from expected")
                elif row.expected_md5 and file_digest(dest, "md5") != row.expected_md5:
                    entry.update(download_status="checksum_mismatch", error_or_reason="MD5 differs from expected")
                else:
                    entry["download_status"] = "success"
                    if sha in seen_hashes:
                        entry["error_or_reason"] = f"Duplicate content of {seen_hashes[sha]}"
                    seen_hashes[sha] = row.dataset_id
            except Exception as error:  # recorded honestly in the manifest, never swallowed silently
                entry.update(download_status="failed", error_or_reason=f"{type(error).__name__}: {error}"[:300])
        log.info("%s %s %s", row.dataset_id, entry["download_status"], entry.get("error_or_reason", ""))
        if not dry_run:
            append_manifest(entry, manifest_path)
        results.append(entry)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="*", help="Dataset IDs to fetch (counts as approval for these open datasets)")
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--min-interval", type=float, default=2.0, help="Seconds between requests (rate limit)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "acquisition.log"), logging.StreamHandler()],
    )
    for key in ("KAGGLE_KEY", "PHYSIONET_PASSWORD"):
        if os.environ.get(key):
            log.info("%s is set but unused: this tool only fetches open datasets", key)
    results = acquire(read_plan(args.plan), load_records(), ids=set(args.ids) if args.ids else None,
                      min_interval_s=args.min_interval, dry_run=args.dry_run)
    failed = [r for r in results if r["download_status"] in ("failed", "checksum_mismatch")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
