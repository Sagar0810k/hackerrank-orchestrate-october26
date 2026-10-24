"""Evidence extraction (Part C6).

Turns raw evidence files + system_activity into a flat list of facts:
  Fact(system_id, resource_id, category, kind, state, identifiers_exposed,
       evidence_id, observed_at)
kind in {RECORD, FLOW, RESTORE_PATH}; state in {PRESENT, ABSENT, ACTIVE}.

For a given case we resolve the subject's identifiers (identity.py), then scan
every participant-visible evidence source for those identifiers.  A match emits
a fact tagged with the file_id/activity_id that proves it.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .loader import DATASET, read_csv, parse_timestamp

TABLE_CATEGORY = {
    "customer_profiles": ("USER_PROFILE", "account_service"),
    "customer_profiles_primary": ("USER_PROFILE", "account_service"),
    "customer_profiles_failover_replica": ("USER_PROFILE", "account_service"),
    "customer_profiles_read_replica": ("USER_PROFILE", "account_service"),
    "customer_profiles_regional_replica": ("USER_PROFILE", "account_service"),
    "customer_profiles_reporting_replica": ("USER_PROFILE", "account_service"),
    "customer_profiles_inventory": ("USER_PROFILE", "account_service"),
    "customer_search_documents": ("SEARCH_INDEX_ENTRY", "search_service"),
    "customer_analytics_profiles": ("ANALYTICS_PROFILE", "analytics_platform"),
    "customer_analytics_reports": ("ANALYTICS_PROFILE", "analytics_platform"),
    "support_records": ("SUPPORT_MESSAGE", "support_platform"),
    "support_conversations": ("SUPPORT_MESSAGE", "support_platform"),
    "customer_exports": ("USER_EXPORT", "export_service"),
    "connector_subscriptions": ("CONNECTOR_SUBSCRIPTION", "integration_service"),
    "backup_restore_entries": ("BACKUP_ARCHIVE", "backup_service"),
    "security_audit_records": ("SECURITY_AUDIT_LOG", "security_service"),
}

COLLECTION_CATEGORY = {
    "customer_profiles": ("USER_PROFILE", "account_service"),
    "customer_search_documents": ("SEARCH_INDEX_ENTRY", "search_service"),
    "customer_analytics_reports": ("ANALYTICS_PROFILE", "analytics_platform"),
    "customer_analytics_profiles": ("ANALYTICS_PROFILE", "analytics_platform"),
    "support_conversations": ("SUPPORT_MESSAGE", "support_platform"),
    "support_records": ("SUPPORT_MESSAGE", "support_platform"),
    "customer_exports": ("USER_EXPORT", "export_service"),
    "connector_subscriptions": ("CONNECTOR_SUBSCRIPTION", "integration_service"),
    "security_audit_records": ("SECURITY_AUDIT_LOG", "security_service"),
}

IDENTIFIER_COLUMNS = {
    "email", "phone", "email_hash", "user_id", "customer_reference",
    "subject_reference", "owner_email", "customer_email", "requester_email",
    "requester_phone", "match_key", "subject_key", "correlation_key",
}


@dataclass
class Fact:
    system_id: str
    resource_id: str
    category: str
    kind: str
    state: str
    identifiers_exposed: List[str] = field(default_factory=list)
    evidence_id: str = ""
    observed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "category": self.category,
            "kind": self.kind,
            "state": self.state,
            "identifiers_exposed": self.identifiers_exposed,
            "evidence_id": self.evidence_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
        }


def _norm(v: Any) -> str:
    return (v or "").strip().lower()


def _match_identifiers(row: Dict[str, Any], needles: set) -> List[str]:
    hits: List[str] = []
    for k, v in row.items():
        if v is None:
            continue
        sv = str(v)
        for n in needles:
            if n and n in sv:
                hits.append(n)
    return hits


# ---------------------------------------------------------------------------
# SQL snapshots
# ---------------------------------------------------------------------------
def extract_sql_facts(path: Path, file_id: str, needles: set) -> List[Fact]:
    facts: List[Fact] = []
    try:
        con = sqlite3.connect(":memory:")
        con.executescript(open(path, encoding="utf-8").read())
    except Exception:
        return facts

    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    captured_at: Optional[datetime] = None
    origin_system: Optional[str] = None
    try:
        rows = con.execute("select origin_system, captured_at from snapshot_scope").fetchall()
        if rows:
            origin_system = rows[0][0]
            try:
                captured_at = parse_timestamp(rows[0][1])
            except Exception:
                captured_at = None
    except Exception:
        pass

    for t in tables:
        category, system = TABLE_CATEGORY.get(t, (None, origin_system or "unknown"))
        if category is None:
            continue
        try:
            cols = [c[1] for c in con.execute(f"pragma table_info({t})")]
        except Exception:
            continue
        id_cols = [c for c in cols if c in IDENTIFIER_COLUMNS]
        rid_col = "resource_id" if "resource_id" in cols else (cols[0] if cols else None)
        if not id_cols or not rid_col:
            continue
        try:
            rows = con.execute(f"select * from {t}").fetchall()
        except Exception:
            continue
        for row in rows:
            d = dict(zip(cols, row))
            hits = _match_identifiers(d, needles)
            if not hits:
                continue
            rid = str(d.get(rid_col) or "")
            if not rid:
                continue
            facts.append(Fact(
                system_id=system,
                resource_id=rid,
                category=category,
                kind="RECORD",
                state="PRESENT",
                identifiers_exposed=sorted(set(hits)),
                evidence_id=file_id,
                observed_at=captured_at,
            ))
    return facts



# ---------------------------------------------------------------------------
# JSON bundles / records
# ---------------------------------------------------------------------------
def extract_json_facts(path: Path, file_id: str, needles: set) -> List[Fact]:
    facts: List[Fact] = []
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return facts

    snapshots = data.get("snapshots", []) if isinstance(data, dict) else []
    for snap in snapshots:
        data_store = snap.get("data_store") or "unknown"
        collection = snap.get("collection") or ""
        captured_at = None
        try:
            captured_at = parse_timestamp(snap.get("captured_at", ""))
        except Exception:
            pass
        category, system = COLLECTION_CATEGORY.get(collection, (None, data_store))
        if category is None:
            continue
        for rec in snap.get("records", []):
            hits = _match_identifiers(rec, needles)
            if not hits:
                continue
            rid = str(rec.get("resource_id") or "")
            if not rid:
                continue
            doc = rec.get("document")
            if isinstance(doc, dict):
                doc_hits = _match_identifiers(doc, needles)
                if doc_hits:
                    hits = list(set(hits) | set(doc_hits))
            facts.append(Fact(
                system_id=system,
                resource_id=rid,
                category=category,
                kind="RECORD",
                state="PRESENT",
                identifiers_exposed=sorted(set(hits)),
                evidence_id=file_id,
                observed_at=captured_at,
            ))




# ---------------------------------------------------------------------------
# Log / text files
# ---------------------------------------------------------------------------
def extract_log_facts(path: Path, file_id: str, needles: set) -> List[Fact]:
    facts: List[Fact] = []
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        return facts

    service_re = re.compile(r"service=([\w\-]+)")
    resource_re = re.compile(r"resource_id=([\w\-]+)")
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")

    for line in lines:
        hits = [n for n in needles if n and n in line]
        if not hits:
            continue
        sm = service_re.search(line)
        rm = resource_re.search(line)
        tm = ts_re.search(line)
        system = sm.group(1) if sm else "unknown"
        rid = rm.group(1) if rm else ""
        observed_at = None
        if tm:
            try:
                observed_at = parse_timestamp(tm.group(1))
            except Exception:
                pass

        state = "PRESENT"
        kind = "RECORD"
        low = line.lower()
        if "rows=0" in low or "http_status=404" in low or "result=miss" in low:
            state = "ABSENT"
        if "connector_heartbeat" in low and "enabled=true" in low:
            kind = "FLOW"
            state = "ACTIVE"
            rid = rid or "data_flow"
        if "restore_candidate_evaluated" in low and "eligible=true" in low:
            kind = "RESTORE_PATH"
            state = "ACTIVE"
        if "index_query_completed" in low and "result=hit" in low:
            kind = "RECORD"
            state = "PRESENT"

        if not rid:
            continue
        facts.append(Fact(
            system_id=system,
            resource_id=rid,
            category=_category_for_system(system),
            kind=kind,
            state=state,
            identifiers_exposed=sorted(set(hits)),
            evidence_id=file_id,
            observed_at=observed_at,
        ))
    return facts


def _category_for_system(system: str) -> str:
    mapping = {
        "account_service": "USER_PROFILE",
        "search_service": "SEARCH_INDEX_ENTRY",
        "analytics_platform": "ANALYTICS_PROFILE",
        "support_platform": "SUPPORT_MESSAGE",
        "export_service": "USER_EXPORT",
        "integration_service": "CONNECTOR_SUBSCRIPTION",
        "backup_service": "BACKUP_ARCHIVE",
        "security_service": "SECURITY_AUDIT_LOG",
        "identity_service": "ACCOUNT_TOMBSTONE",
    }
    return mapping.get(system, "USER_PROFILE")


# ---------------------------------------------------------------------------
# system_activity.csv
# ---------------------------------------------------------------------------
FLOW_EVENTS = {"SYNC_RECORD", "INDEX_RECORD", "UPDATE_RECORD"}
RESTORE_EVENTS = {"RESTORE_BACKUP"}


def extract_activity_facts(activity_rows: List[Dict[str, str]], needles: set) -> List[Fact]:
    facts: List[Fact] = []
    for row in activity_rows:
        details = row.get("details", "") or ""
        resource_id = row.get("resource_id") or ""
        hits = [n for n in needles if n and (n in details or n in resource_id)]
        if not hits:
            continue
        event_type = row.get("event_type", "")
        system = row.get("source_system") or row.get("target_system") or "unknown"
        observed_at = None
        try:
            observed_at = parse_timestamp(row.get("event_time", ""))
        except Exception:
            pass
        if event_type in RESTORE_EVENTS:
            facts.append(Fact(
                system_id=system, resource_id=resource_id or "restore_path",
                category="BACKUP_ARCHIVE", kind="RESTORE_PATH", state="ACTIVE",
                identifiers_exposed=sorted(set(hits)),
                evidence_id=row.get("activity_id", ""), observed_at=observed_at,
            ))
        elif event_type in FLOW_EVENTS and row.get("reported_result", "").upper() == "SUCCESS":
            facts.append(Fact(
                system_id=system, resource_id=resource_id or "data_flow",
                category="CONNECTOR_SUBSCRIPTION", kind="FLOW", state="ACTIVE",
                identifiers_exposed=sorted(set(hits)),
                evidence_id=row.get("activity_id", ""), observed_at=observed_at,
            ))
    return facts


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------
def extract_facts(
    identifiers: List[str],
    evidence_rows: List[Dict[str, str]],
    activity_rows: List[Dict[str, str]],
    audit_at: Optional[datetime] = None,
) -> List[Fact]:
    """Extract all facts matching any of the identifiers from all evidence."""
    needles = {n for n in identifiers if n}
    facts: List[Fact] = []
    for row in evidence_rows:
        path = DATASET / row["file_path"]
        file_id = row["file_id"]
        ext = path.suffix.lower()
        if ext == ".sql":
            facts.extend(extract_sql_facts(path, file_id, needles))
        elif ext == ".json":
            facts.extend(extract_json_facts(path, file_id, needles))
        elif ext in (".log", ".txt"):
            facts.extend(extract_log_facts(path, file_id, needles))
    facts.extend(extract_activity_facts(activity_rows, needles))

    if audit_at is not None:
        facts = [f for f in facts if f.observed_at is None or f.observed_at <= audit_at]
    return facts

            hits = _match_identifiers(rec, needles)
            if not hits:
                continue
            rid = str(rec.get("resource_id") or "")
            if not rid:
                continue
            doc = rec.get("document")
            if isinstance(doc, dict):
                doc_hits = _match_identifiers(doc, needles)
                if doc_hits:
                    hits = list(set(hits) | set(doc_hits))
            facts.append(Fact(
                system_id=system,
                resource_id=rid,
                category=category,
                kind="RECORD",
                state="PRESENT",
                identifiers_exposed=sorted(set(hits)),
                evidence_id=file_id,
                observed_at=captured_at,
            ))
    return facts

