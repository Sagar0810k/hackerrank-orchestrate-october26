"""Loader: read dataset CSVs into lists of dicts with parsed timestamps."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

DATASET = Path("dataset")


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    value = (value or "").strip()
    if not value:
        raise ValueError("empty timestamp")
    # Accept trailing Z or explicit offset.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_deletion_requests(path: Path = DATASET / "deletion_requests.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_sample_requests(path: Path = DATASET / "sample_deletion_requests.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_sample_output(path: Path = DATASET / "sample_output.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_user_identities(path: Path = DATASET / "user_identities.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_user_audit_log(path: Path = DATASET / "user_audit_log.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_system_activity(path: Path = DATASET / "system_activity.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_deletion_rules(path: Path = DATASET / "deletion_rules.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_evidence_files(path: Path = DATASET / "evidence_files.csv") -> List[Dict[str, str]]:
    return read_csv(path)


def load_all() -> Dict[str, List[Dict[str, str]]]:
    return {
        "deletion_requests": load_deletion_requests(),
        "sample_requests": load_sample_requests(),
        "sample_output": load_sample_output(),
        "user_identities": load_user_identities(),
        "user_audit_log": load_user_audit_log(),
        "system_activity": load_system_activity(),
        "deletion_rules": load_deletion_rules(),
        "evidence_files": load_evidence_files(),
    }
