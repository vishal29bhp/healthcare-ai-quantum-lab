"""Privacy-preserving enrichment from the project owner's own Snowflake account.

The Snowflake data is NOT de-identified, so this module never pulls raw rows:

1. ``inventory`` reads only INFORMATION_SCHEMA metadata (databases, tables, columns, row counts) and classifies
   every column by name and type as a direct identifier, date, age, free text, quasi-identifier or analysable.
2. ``profile`` pulls aggregates only: per-table row counts, value counts of low-cardinality categorical columns
   with cells n < 11 suppressed, numeric summaries (count/mean/std/quartiles), age in 10-year bands capped at 90
   and dates reduced to year. Identifier, free-text and quasi-identifier columns are never selected.

Credentials come from environment variables only and are never printed or logged:
``SNOWFLAKE_ACCOUNT``, ``SNOWFLAKE_USER`` and ``SNOWFLAKE_PRIVATE_KEY`` (a PEM key-pair key, or a programmatic
access token), plus optional ``SNOWFLAKE_ROLE``, ``SNOWFLAKE_WAREHOUSE``, ``SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`` and
``SNOWFLAKE_REGION`` (e.g. ``ap-southeast-1``, appended to a bare account locator outside AWS us-west-2).
A programmatic access token is only accepted when the user has a network policy or an authentication policy with
``PAT_POLICY = (NETWORK_POLICY_EVALUATION = ENFORCED_NOT_REQUIRED)``; otherwise login fails with error 390432.
Outputs are Parquet files under the git-ignored ``snowflake/raw/`` folder, each with a SHA-256 manifest row.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import ROOT
from .acquire import append_manifest, file_digest

OUT_DIR = ROOT / "snowflake" / "raw"  # git-ignored by **/raw/
MIN_CELL = 11  # suppress any aggregate cell describing fewer than 11 patients
MAX_CATEGORIES = 50
AGE_CAP = 90
SKIP_DATABASES = {"SNOWFLAKE"}
SKIP_SCHEMAS = {"INFORMATION_SCHEMA"}

log = logging.getLogger("hcds.snowflake")

DIRECT_ID = re.compile(
    r"(^|_)(first|last|middle|full|given|family|patient|member|mother|father)?_?name($|_)|ssn|social_sec|"
    r"mrn|medical_record|record_num|patient_id|member_id|subscriber|insurance_id|policy_num|account_num|"
    r"phone|fax|e_?mail|address|street|addr_|zip|zcta|postal|postcode|license|licence|vehicle|vin($|_)|"
    r"device_serial|serial_num|url|ip_addr|biometric|photo|image_path|passport|national_id|nhs_num|aadhaar",
    re.I,
)
DATE_LIKE = re.compile(r"(dob|birth|date|_dt$|_ts$|time|admit|discharg|death|dod$|visit_day)", re.I)
AGE_LIKE = re.compile(r"(^|_)age($|_|_years|_yrs)", re.I)
QUASI_ID = re.compile(r"(^|_)(city|county|town|village|lat|lon|latitude|longitude|geo|census_tract|"
                      r"employer|occupation|provider_name|physician|doctor|npi)($|_)", re.I)
FREE_TEXT = re.compile(r"(note|comment|text|narrative|description|remark|free_?text|summary)", re.I)
TEXT_TYPES = {"TEXT", "VARCHAR", "STRING", "CHAR", "CHARACTER"}
NUMERIC_TYPES = {"NUMBER", "DECIMAL", "NUMERIC", "INT", "INTEGER", "BIGINT", "SMALLINT", "FLOAT", "DOUBLE", "REAL"}
DATE_TYPES = {"DATE", "DATETIME", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ", "TIMESTAMP"}


def classify_column(name: str, data_type: str) -> str:
    """Return one of direct_identifier, date, age, quasi_identifier, free_text, numeric, categorical, other."""
    dtype = data_type.upper().split("(")[0]
    if AGE_LIKE.search(name) and dtype in NUMERIC_TYPES:
        return "age"
    if DIRECT_ID.search(name):
        return "direct_identifier"
    if dtype in DATE_TYPES or (DATE_LIKE.search(name) and dtype in TEXT_TYPES):
        return "date"  # DEATHS (NUMBER) is a count, LAST_REPORTED_DATE (BOOLEAN) a flag
    if QUASI_ID.search(name):
        return "quasi_identifier"
    if re.search(r"(^|_)id$|_key$|_uuid$|^uuid$|_guid$", name, re.I):
        return "direct_identifier"  # surrogate keys are linkable; treat as identifiers
    if dtype in TEXT_TYPES and FREE_TEXT.search(name):
        return "free_text"
    if dtype in NUMERIC_TYPES:
        return "numeric"
    if dtype in TEXT_TYPES or dtype == "BOOLEAN":
        return "categorical"
    return "other"


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect():
    import snowflake.connector  # imported lazily so the rest of hcds works without it

    secret = os.environ["SNOWFLAKE_PRIVATE_KEY"].strip()
    account = os.environ["SNOWFLAKE_ACCOUNT"].strip()
    region = os.environ.get("SNOWFLAKE_REGION", "").strip()
    if region and "." not in account and "-" not in account:  # bare locator outside us-west-2
        account = f"{account}.{region}"
    params = {
        "account": account,
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ.get("SNOWFLAKE_ROLE"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
        "client_session_keep_alive": False,
        "session_parameters": {"QUERY_TAG": "hcds-aggregate-enrichment"},
    }
    if secret.startswith("-----BEGIN"):
        from cryptography.hazmat.primitives import serialization

        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        key = serialization.load_pem_private_key(
            secret.replace("\\n", "\n").encode(), password=passphrase.encode() if passphrase else None
        )
        params["private_key"] = key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    else:  # programmatic access token
        params["authenticator"] = "PROGRAMMATIC_ACCESS_TOKEN"
        params["token"] = secret
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v is not None})


def _rows(cur, sql: str, binds=None) -> list[dict]:
    cur.execute(sql, binds)
    names = [d[0].lower() for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def inventory(conn):
    """Metadata only: one row per column with its privacy class. Reads no table rows."""
    import pandas as pd

    cur = conn.cursor()
    databases = [r["name"] for r in _rows(cur, "SHOW DATABASES") if r["name"] not in SKIP_DATABASES]
    frames = []
    for db in databases:
        try:
            cols = _rows(cur, f"""
                select c.table_schema, c.table_name, c.column_name, c.data_type, c.ordinal_position,
                       t.table_type, t.row_count
                from {_q(db)}.information_schema.columns c
                join {_q(db)}.information_schema.tables t
                  on t.table_schema = c.table_schema and t.table_name = c.table_name
                where c.table_schema <> 'INFORMATION_SCHEMA'
                order by 1, 2, c.ordinal_position""")
        except Exception as exc:  # no privilege on this database
            log.warning("skipping database %s: %s", db, type(exc).__name__)
            continue
        if cols:
            frame = pd.DataFrame(cols)
            frame.insert(0, "table_catalog", db)
            frames.append(frame)
    inv = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not inv.empty:
        inv["privacy_class"] = [classify_column(n, t) for n, t in zip(inv.column_name, inv.data_type)]
    return inv


def _fqn(db: str, schema: str, table: str) -> str:
    return ".".join(_q(x) for x in (db, schema, table))


def profile_table(conn, table_cols):
    """Aggregates for one table. Returns a long-format DataFrame of suppressed counts and numeric summaries."""
    import pandas as pd

    db, schema, table = table_cols.iloc[0][["table_catalog", "table_schema", "table_name"]]
    fqn = _fqn(db, schema, table)
    cur = conn.cursor()
    total = _rows(cur, f"select count(*) as n from {fqn}")[0]["n"]
    out = [{"column": "*", "kind": "row_count", "value": None, "n": total if total >= MIN_CELL else None}]
    if total < MIN_CELL:
        return pd.DataFrame(out)
    for col in table_cols.itertuples():
        name, cls = _q(col.column_name), col.privacy_class
        if cls == "age":
            expr = f"least(floor({name} / 10) * 10, {AGE_CAP})::int"
        elif cls == "date":
            expr = f"year(try_to_date({name}::varchar))" if col.data_type.upper() in TEXT_TYPES else f"year({name})"
        elif cls == "categorical":
            distinct = _rows(cur, f"select approx_count_distinct({name}) as d from {fqn}")[0]["d"]
            if distinct > MAX_CATEGORIES:
                continue
            expr = name
        elif cls == "numeric":
            stats = _rows(cur, f"""select count({name}) as n, avg({name}) as mean, stddev({name}) as std,
                    approx_percentile({name}, 0.25) as p25, approx_percentile({name}, 0.5) as p50,
                    approx_percentile({name}, 0.75) as p75 from {fqn}""")[0]
            if stats["n"] >= MIN_CELL:
                for key in ("mean", "std", "p25", "p50", "p75"):
                    out.append({"column": col.column_name, "kind": key, "value": None if stats[key] is None
                                else float(stats[key]), "n": stats["n"]})
            continue
        else:
            continue  # identifiers, quasi-identifiers, free text and unknown types are never read
        for row in _rows(cur, f"select {expr}::varchar as v, count(*) as n from {fqn} group by 1"):
            out.append({"column": col.column_name, "kind": f"count_{cls}", "value": row["v"],
                        "n": row["n"] if row["n"] >= MIN_CELL else None})  # None = suppressed (n < 11)
    frame = pd.DataFrame(out)
    frame["value"] = frame["value"].map(lambda v: None if v is None else str(v))  # mixed labels and stats
    return frame


def _save(frame, path: Path, dataset_id: str, note: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    append_manifest({
        "dataset_id": dataset_id, "source_url": "snowflake://<owner account>", "acquisition_method": "snowflake",
        "access_prerequisites": "owner's Snowflake credentials (env vars)", "requested_files": note,
        "local_path": str(path.relative_to(ROOT)), "download_status": "aggregated",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_size_bytes": path.stat().st_size, "sha256": file_digest(path),
        "error_or_reason": f"aggregates only; cells n<{MIN_CELL} suppressed; ages capped at {AGE_CAP}",
    })


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["inventory", "profile"])
    parser.add_argument("--tables", nargs="*", help="DB.SCHEMA.TABLE names to profile (default: all)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    conn = connect()
    try:
        inv = inventory(conn)
        _save(inv, OUT_DIR / "inventory.parquet", "SNOWFLAKE-INVENTORY", "INFORMATION_SCHEMA metadata")
        summary = inv.groupby(["table_catalog", "table_schema", "table_name"]).agg(
            rows=("row_count", "first"), columns=("column_name", "size"),
            phi_like=("privacy_class", lambda s: int(s.isin(["direct_identifier", "quasi_identifier",
                                                            "free_text"]).sum())))
        print(summary.to_string())
        if args.command == "profile":
            for key, cols in inv.groupby(["table_catalog", "table_schema", "table_name"]):
                fqn = ".".join(key)
                if args.tables and fqn not in args.tables:
                    continue
                log.info("profiling %s", fqn)
                try:
                    frame = profile_table(conn, cols)
                except Exception as exc:  # e.g. a shared view we may not aggregate; keep going
                    log.warning("could not profile %s: %s", fqn, type(exc).__name__)
                    continue
                _save(frame, OUT_DIR / "profiles" / f"{'__'.join(key)}.parquet", f"SNOWFLAKE-{key[2]}", fqn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
