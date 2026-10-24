"""Evidence extraction (Part C6).

Every participant-visible evidence item (SQL snapshot, JSON export, log, text
record, PDF/image extraction and system_activity row) is turned into a flat
list of ``Observation`` objects.  An observation says: "at ``observed_at``,
evidence ``evidence_id`` showed resource ``resource_id`` in ``system_id`` in
this state, and these identifier ``keys`` were attached to it".

Nothing here knows about cases.  Linking observations to a subject happens in
``linker.py``; deciding the state at ``audit_at`` happens in ``state.py``.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .loader import DATASET, parse_timestamp, read_csv
from .normalize import (
    collect_keys,
    has_direct_identifier,
    is_null,
    norm_key,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Observation:
    evidence_id: str
    available_at: datetime          # when the evidence item existed (cut-off check)
    observed_at: datetime           # when the state was observed (latest wins)
    system_id: str
    resource_id: str
    category: Optional[str]
    present: Optional[bool] = None  # record exists?
    exposed: Optional[bool] = None  # direct identifiers (name/email/phone/hash) visible?
    linkable: Optional[bool] = None # any identifier incl. stable user reference?
    active: Optional[bool] = None   # data flow enabled / restore allowed
    keys: frozenset = field(default_factory=frozenset)
    origin: str = ""                # parser that produced it (debugging)
    refs: frozenset = field(default_factory=frozenset)  # other resource ids the record points to

    @property
    def kind(self) -> str:
        if self.category == "DATA_FLOW":
            return "FLOW"
        if self.category == "BACKUP_ARCHIVE":
            return "RESTORE_PATH"
        return "RECORD"


# ---------------------------------------------------------------------------
# Resource naming helpers
# ---------------------------------------------------------------------------
# Resource-id prefix -> (system_id, category).  Longest prefix wins.
PREFIX_INFO: List[Tuple[str, str, str]] = [
    ("audit_record_", "security_service", "SECURITY_AUDIT_LOG"),
    ("email_delivery_", "email_delivery_service", "EMAIL_DELIVERY_LOG"),
    ("data_flow_", "integration_service", "DATA_FLOW"),
    ("tombstone_", "identity_service", "ACCOUNT_TOMBSTONE"),
    ("analytics_", "analytics_platform", "ANALYTICS_PROFILE"),
    ("marketing_", "marketing_platform", "MARKETING_PROFILE"),
    ("telemetry_", "analytics_platform", "PRODUCT_TELEMETRY"),
    ("account_", "account_service", "USER_PROFILE"),
    ("search_", "search_service", "SEARCH_INDEX_ENTRY"),
    ("support_", "support_platform", "SUPPORT_MESSAGE"),
    ("export_", "export_service", "USER_EXPORT"),
    ("backup_", "backup_service", "BACKUP_ARCHIVE"),
    ("cache_", "cache_service", "CACHE_ENTRY"),
    ("legal_", "legal_service", "LEGAL_HOLD_RECORD"),
    ("object_", "object_storage", "SUPPORT_ATTACHMENT"),
]

RESOURCE_RE = re.compile(
    r"\b(?:audit_record|email_delivery|data_flow|tombstone|analytics|marketing|"
    r"telemetry|account|search|support|export|backup|cache|legal|object)_\d+\b"
)

COLLECTION_CATEGORY = {
    "customer_profiles": "USER_PROFILE",
    "profile_lookups": "USER_PROFILE",
    "customer_search_documents": "SEARCH_INDEX_ENTRY",
    "index_queries": "SEARCH_INDEX_ENTRY",
    "customer_analytics_reports": "ANALYTICS_PROFILE",
    "customer_analytics_profiles": "ANALYTICS_PROFILE",
    "profiles": "ANALYTICS_PROFILE",
    "support_conversations": "SUPPORT_MESSAGE",
    "support_records": "SUPPORT_MESSAGE",
    "tickets": "SUPPORT_MESSAGE",
    "ticket_attachments": "SUPPORT_ATTACHMENT",
    "customer_export_jobs": "USER_EXPORT",
    "customer_exports": "USER_EXPORT",
    "exports": "USER_EXPORT",
    "connector_configurations": "DATA_FLOW",
    "connector_subscriptions": "DATA_FLOW",
    "connectors": "DATA_FLOW",
    "backup_catalog": "BACKUP_ARCHIVE",
    "backup_restore_entries": "BACKUP_ARCHIVE",
    "restore_entries": "BACKUP_ARCHIVE",
    "security_audit_events": "SECURITY_AUDIT_LOG",
    "security_audit_records": "SECURITY_AUDIT_LOG",
    "audit_records": "SECURITY_AUDIT_LOG",
    "deleted_customer_references": "ACCOUNT_TOMBSTONE",
    "retained_order_records": "LEGAL_HOLD_RECORD",
}


def resource_info(resource_id: str) -> Tuple[Optional[str], Optional[str]]:
    for prefix, system, category in PREFIX_INFO:
        if resource_id.startswith(prefix):
            return system, category
    return None, None


def canonical_system(resource_id: str, fallback: Optional[str]) -> str:
    system, _ = resource_info(resource_id)
    return system or (fallback or "unknown")


def _ts(value: Any) -> Optional[datetime]:
    if is_null(value):
        return None
    try:
        return parse_timestamp(str(value))
    except ValueError:
        return None


def _truthy(value: Any) -> Optional[bool]:
    if is_null(value):
        return None
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "allow", "allowed", "enabled"):
        return True
    if s in ("0", "false", "no", "deny", "denied", "disabled"):
        return False
    return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Generic record -> observation (snapshot style: record exists)
# ---------------------------------------------------------------------------
def record_observation(
    rec: Dict[str, Any],
    *,
    evidence_id: str,
    available_at: datetime,
    observed_at: datetime,
    system_hint: Optional[str],
    category_hint: Optional[str],
    origin: str,
) -> Optional[Observation]:
    """A record that exists in a snapshot.  Its fields decide exposure/flags."""
    rid = rec.get("resource_id")
    if is_null(rid):
        return None
    rid = str(rid)
    _, prefix_cat = resource_info(rid)
    category = category_hint or prefix_cat
    keys = collect_keys(rec)
    exposed = has_direct_identifier(rec)
    linkable = exposed or any(k.startswith("user_") for k in keys)
    refs = {str(v) for k, v in rec.items()
            if k != "resource_id" and isinstance(v, str) and RESOURCE_RE.fullmatch(v)}
    obs = Observation(
        refs=frozenset(refs),
        evidence_id=evidence_id,
        available_at=available_at,
        observed_at=observed_at,
        system_id=canonical_system(rid, system_hint),
        resource_id=rid,
        category=category,
        present=True,
        exposed=exposed,
        linkable=linkable,
        keys=frozenset(keys),
        origin=origin,
    )
    if category == "DATA_FLOW":
        obs.active = _truthy(rec.get("enabled"))
    elif category == "BACKUP_ARCHIVE":
        obs.active = _truthy(rec.get("restore_allowed"))
    elif category == "USER_EXPORT" and "download_available" in rec:
        # An export whose package is no longer downloadable is still a stored record.
        pass
    return obs


# ---------------------------------------------------------------------------
# Status-list style records (record_type + result + subject_reference)
# ---------------------------------------------------------------------------
RESULT_STATE = {
    "FOUND": dict(present=True),
    "NOT_FOUND": dict(present=False),
    "IDENTIFIABLE": dict(present=True, exposed=True, linkable=True),
    "ANONYMIZED": dict(present=True, exposed=False, linkable=False),
    "REDACTED": dict(present=True, exposed=False),
    "ACTIVE": dict(present=True, active=True),
    "BLOCKED": dict(present=True, active=False),
    "DISABLED": dict(present=True, active=False),
}


def status_observation(
    *,
    system: str,
    resource_id: str,
    record_type: str,
    result: str,
    subject: Any,
    evidence_id: str,
    available_at: datetime,
    observed_at: datetime,
    origin: str,
) -> Optional[Observation]:
    state = RESULT_STATE.get((result or "").upper())
    if state is None:
        return None
    category = (record_type or "").upper() or resource_info(resource_id)[1]
    keys = set()
    k = norm_key(subject)
    if k:
        keys.add(k)
    obs = Observation(
        evidence_id=evidence_id,
        available_at=available_at,
        observed_at=observed_at,
        system_id=canonical_system(resource_id, system),
        resource_id=resource_id,
        category=category,
        keys=frozenset(keys),
        origin=origin,
        **state,
    )
    if obs.present and obs.exposed is None and category in ("SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE",
                                                            "EMAIL_DELIVERY_LOG", "ANALYTICS_PROFILE"):
        # FOUND on a redact/anonymize category means the subject value was matched.
        obs.exposed = bool(keys) and not all(x.startswith("user_") for x in keys)
    return obs


# ---------------------------------------------------------------------------
# SQL snapshots
# ---------------------------------------------------------------------------
def extract_sql(path: Path, evidence_id: str, available_at: datetime) -> List[Observation]:
    out: List[Observation] = []
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(path.read_text(encoding="utf-8"))
    except sqlite3.Error:
        return out
    tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    # capture time: "-- Captured at:" header, else the snapshot_scope table, else the manifest
    header_time = available_at
    m = re.search(r"Captured at:\s*(\S+)", path.read_text(encoding="utf-8")[:400])
    if m and _ts(m.group(1)):
        header_time = _ts(m.group(1))
    elif "snapshot_scope" in tables:
        times = [_ts(c) for (c,) in con.execute("select captured_at from snapshot_scope")]
        times = [t for t in times if t]
        if times:
            header_time = max(times)

    for table in tables:
        if table == "snapshot_scope":
            continue
        cols = [c[1] for c in con.execute(f'pragma table_info("{table}")')]
        rows = [dict(zip(cols, r)) for r in con.execute(f'select * from "{table}"')]
        for row in rows:
            if "record_json" in row:
                try:
                    rec = json.loads(row["record_json"])
                except json.JSONDecodeError:
                    continue
                system_hint = row.get("origin_system")
                category = COLLECTION_CATEGORY.get(row.get("collection_name") or "")
            else:
                rec = dict(row)
                system_hint = None
                category = COLLECTION_CATEGORY.get(table)
                if category is None:
                    for coll, cat in COLLECTION_CATEGORY.items():
                        if table.startswith(coll):
                            category = cat
                            break
            # every row of a point-in-time snapshot describes the state at capture time
            obs = record_observation(
                rec,
                evidence_id=evidence_id,
                available_at=available_at,
                observed_at=header_time,
                system_hint=system_hint,
                category_hint=category,
                origin=f"sql:{table}",
            )
            if obs:
                out.append(obs)
    return out


# ---------------------------------------------------------------------------
# JSON evidence
# ---------------------------------------------------------------------------
def extract_json(path: Path, evidence_id: str, available_at: datetime) -> List[Observation]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[Observation] = []

    # 1. Snapshot bundles: {"snapshots": [{captured_at, data_store, collection, records}]}
    if isinstance(data, dict) and isinstance(data.get("snapshots"), list):
        for snap in data["snapshots"]:
            cap = _ts(snap.get("captured_at")) or available_at
            store = snap.get("data_store")
            coll = snap.get("collection") or ""
            for rec in snap.get("records", []):
                if coll == "operational_record_history":
                    obs = status_observation(
                        system=rec.get("system"), resource_id=str(rec.get("resource_id")),
                        record_type=rec.get("record_type"), result=rec.get("result"),
                        subject=rec.get("lookup_value"), evidence_id=evidence_id,
                        available_at=available_at,
                        observed_at=_ts(rec.get("recorded_at")) or cap,
                        origin=f"bundle:{store}:{coll}",
                    )
                else:
                    obs = record_observation(
                        rec, evidence_id=evidence_id, available_at=available_at,
                        observed_at=cap, system_hint=store,
                        category_hint=COLLECTION_CATEGORY.get(coll),
                        origin=f"bundle:{store}:{coll}",
                    )
                if obs:
                    out.append(obs)
        return out

    # 2. Status lists: {"records": [{recorded_at, system, resource_id, record_type, result, subject_reference}]}
    if isinstance(data, dict) and isinstance(data.get("records"), list) and data["records"] \
            and "record_type" in data["records"][0]:
        for rec in data["records"]:
            obs = status_observation(
                system=rec.get("system"), resource_id=str(rec.get("resource_id")),
                record_type=rec.get("record_type"), result=rec.get("result"),
                subject=rec.get("subject_reference"), evidence_id=evidence_id,
                available_at=available_at,
                observed_at=_ts(rec.get("recorded_at")) or available_at,
                origin=f"status:{path.name}",
            )
            if obs:
                out.append(obs)
        return out

    # 3. Single-collection captures: {"captured_at", "collection", "records": [...]}
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        cap = _ts(data.get("captured_at")) or available_at
        coll = data.get("collection") or ""
        for rec in data["records"]:
            obs = record_observation(
                rec, evidence_id=evidence_id, available_at=available_at, observed_at=cap,
                system_hint=None, category_hint=COLLECTION_CATEGORY.get(coll),
                origin=f"capture:{coll}",
            )
            if obs:
                out.append(obs)
        return out

    # 4. Service read-back exports: {"service_exports": {service: {collection: [...]}}}
    if isinstance(data, dict) and isinstance(data.get("service_exports"), dict):
        for service, blocks in data["service_exports"].items():
            for coll, recs in blocks.items():
                for rec in recs:
                    out.extend(_service_export_obs(service, coll, rec, evidence_id, available_at))
        return out
    return out


def _service_export_obs(service: str, coll: str, rec: Dict[str, Any], evidence_id: str,
                        available_at: datetime) -> List[Observation]:
    rid = str(rec.get("resource_id"))
    observed = _ts(rec.get("observed_at")) or available_at
    category = COLLECTION_CATEGORY.get(coll) or resource_info(rid)[1]
    base = dict(evidence_id=evidence_id, available_at=available_at, observed_at=observed,
                system_id=canonical_system(rid, service), resource_id=rid,
                category=category, origin=f"service_export:{service}:{coll}")
    if coll == "profile_lookups":
        profile = rec.get("profile")
        status = _int(rec.get("status_code"))
        if profile is None or status == 404:
            return [Observation(present=False, **base)]
        keys = collect_keys(profile)
        return [Observation(present=True, exposed=has_direct_identifier(profile),
                            linkable=True, keys=frozenset(keys), **base)]
    if coll == "index_queries":
        hits = rec.get("hits") or {}
        docs = hits.get("documents") or []
        query_keys = collect_keys({"query": rec.get("query")})
        if not docs or _int(hits.get("total")) == 0:
            return [Observation(present=False, keys=frozenset(query_keys), **base)]
        keys = set(query_keys)
        for d in docs:
            keys |= collect_keys(d)
        return [Observation(present=True, exposed=True, linkable=True,
                            keys=frozenset(keys), **base)]
    obs = record_observation(rec, evidence_id=evidence_id, available_at=available_at,
                             observed_at=observed, system_hint=service,
                             category_hint=category, origin=base["origin"])
    return [obs] if obs else []


# ---------------------------------------------------------------------------
# Logs and text records
# ---------------------------------------------------------------------------
KV_RE = re.compile(r'([A-Za-z_][\w\.]*)=("(?:[^"\\]|\\.)*"|\S+)')
PIPE_RE = re.compile(r"^\|?\s*(\w+)\s*\|\s*([\w_]+)\s*\|\s*([^|]+?)\s*\|\s*(\w+)\s*\|")
BRACKET_RE = re.compile(r"^\[(\w+)\] \[([\w_]+)\] \[([^\]]+)\] (\w+):")
SYSLOG_RE = re.compile(r"^<\d+>1 \S+ (\S+) (\S+)")
HANDOVER_RE = re.compile(
    r"^-\s*(\S+)\s*\|\s*(\w+)\s*\|\s*(\S+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(.+?)\s*$")

LOOKUP_FIELDS = ("lookup_key", "match_key", "scan_key", "subject_key", "subject_ref",
                 "owner_key", "correlation_key")


def parse_log_line(line: str) -> Optional[Tuple[datetime, Dict[str, Any]]]:
    line = line.rstrip("\n")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+(.*)$", line)
    if not m:
        return None
    ts = parse_timestamp(m.group(1))
    rest = m.group(2)
    fields: Dict[str, Any] = {}
    if rest.startswith("{"):
        try:
            fields = json.loads(rest)
        except json.JSONDecodeError:
            return None
    else:
        if 'message="' in rest:
            inner = re.search(r'message="(.*)"$', rest)
            if inner:
                rest = rest + " " + inner.group(1).replace('\\"', '"')
        for k, v in KV_RE.findall(rest):
            fields[k] = v[1:-1] if v.startswith('"') and v.endswith('"') else v
        for regex, svc_i, trace_i, event_i in ((PIPE_RE, 2, 3, 4), (BRACKET_RE, 2, 3, 4)):
            mm = regex.match(rest)
            if mm:
                fields.setdefault("service", mm.group(svc_i))
                fields.setdefault("trace_id", mm.group(trace_i))
                fields.setdefault("event", mm.group(event_i))
        mm = SYSLOG_RE.match(rest)
        if mm:
            fields.setdefault("service", mm.group(1))
            fields.setdefault("trace_id", mm.group(2))
        if "function" in fields:
            fields.setdefault("service", fields["function"])
        if "requestId" in fields:
            fields.setdefault("trace_id", fields["requestId"])
    fields = {k: (None if is_null(v) else v) for k, v in fields.items()}
    return ts, fields


def _log_event_obs(ts: datetime, f: Dict[str, Any], trace_keys: set, evidence_id: str,
                   available_at: datetime) -> List[Observation]:
    event = f.get("event") or ""
    rid = f.get("resource_id")
    if not rid:
        return []
    rid = str(rid)
    keys = set(trace_keys)
    for fld in LOOKUP_FIELDS:
        k = norm_key(f.get(fld))
        if k:
            keys.add(k)
    keys |= collect_keys({k: v for k, v in f.items()
                          if k in ("email", "phone", "customer_reference", "subject_reference",
                                   "requester_email", "requester_phone", "requester_name",
                                   "customer_email", "owner_email", "matched_value",
                                   "email_hash", "message_text")})
    _, cat = resource_info(rid)
    base = dict(evidence_id=evidence_id, available_at=available_at, observed_at=ts,
                system_id=canonical_system(rid, f.get("service")), resource_id=rid,
                category=cat, keys=frozenset(keys), origin=f"log:{event}")

    rows = _int(f.get("rows"))
    http = _int(f.get("http_status"))
    direct = has_direct_identifier({k: f.get(k) for k in (
        "email", "phone", "email_hash", "requester_email", "requester_phone", "requester_name",
        "customer_email", "owner_email", "matched_value", "message_text", "full_name")})

    if event == "profile_lookup_completed":
        if rows == 0 or http == 404:
            return [Observation(present=False, **base)]
        if rows or http == 200:
            return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event == "index_query_completed":
        result = (f.get("result") or "").lower()
        total = _int(f.get("total_hits"))
        if result == "miss" or total == 0:
            return [Observation(present=False, **base)]
        if result == "hit" or (total or 0) > 0:
            return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event in ("message_pii_scan", "analytics_identity_scan"):
        return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event == "attachment_pii_scan":
        base["category"] = "SUPPORT_ATTACHMENT"
        return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event == "message_read":
        return [Observation(present=True, exposed=direct, linkable=True, **base)]
    elif event in ("analytics_profile_read", "analytics_profile_read_completed"):
        n = _int(f.get("direct_identifiers"))
        exposed = direct or bool(n)
        linkable = exposed or bool(norm_key(f.get("customer_reference")))
        return [Observation(present=True, exposed=exposed, linkable=linkable, **base)]
    elif event in ("support_ticket_read_completed",):
        return [Observation(present=True, exposed=direct, linkable=True, **base)]
    elif event in ("audit_record_read_completed",):
        if rows == 0:
            return [Observation(present=False, **base)]
        return [Observation(present=True, **base)]
    elif event in ("connector_heartbeat", "connector_config_loaded", "connector_config_read_completed"):
        return [Observation(present=True, active=_truthy(f.get("enabled")), **base)]
    elif event == "restore_candidate_evaluated":
        eligible = _truthy(f.get("eligible"))
        blocked = _truthy(f.get("deletion_block"))
        active = bool(eligible) and not bool(blocked)
        return [Observation(present=True, active=active, **base)]
    elif event == "restore_authorization_completed":
        return [Observation(present=True, active=_truthy(f.get("decision")), **base)]
    elif event == "restore_policy_read_completed":
        active = _truthy(f.get("restore_allowed"))
        if _truthy(f.get("archive_present")) is False:
            active = False
        return [Observation(present=True, active=active, **base)]
    elif event in ("export_download_check_completed", "export_metadata_read_completed"):
        avail = _truthy(f.get("available"))
        return [Observation(present=bool(avail), exposed=bool(avail), **base)]
    elif event in ("contact_lookup_completed", "contact_query_completed"):
        base["category"] = "SECONDARY_IDENTIFIER"
        if rows == 0:
            return [Observation(present=False, **base)]
        return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event == "deletion_marker_check":
        if _truthy(f.get("marker_found")) is False:
            base["category"] = "SECONDARY_IDENTIFIER"
            return [Observation(present=True, exposed=True, linkable=True, **base)]
    elif event == "record_lookup":
        obs = status_observation(
            system=f.get("system"), resource_id=rid, record_type=f.get("record_type"),
            result=f.get("result"), subject=f.get("subject_reference"),
            evidence_id=evidence_id, available_at=available_at, observed_at=ts,
            origin="log:record_lookup")
        return [obs] if obs else []
    return []


def extract_log(path: Path, evidence_id: str, available_at: datetime) -> List[Observation]:
    parsed = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        p = parse_log_line(line)
        if p:
            parsed.append(p)
    # identifier keys shared through a trace id (lookup started -> completed)
    trace_keys: Dict[str, set] = {}
    for ts, f in parsed:
        tid = f.get("trace_id")
        if not tid:
            continue
        ks = trace_keys.setdefault(tid, set())
        for fld in LOOKUP_FIELDS:
            k = norm_key(f.get(fld))
            if k:
                ks.add(k)
    out: List[Observation] = []
    for ts, f in parsed:
        keys = trace_keys.get(f.get("trace_id") or "", set())
        # a trace id shared by unrelated lines (collector ids) never carries lookup keys
        if f.get("event") == "contact_query_completed" and f.get("lookup_key"):
            keys = keys | {norm_key(f.get("lookup_key"))}
        out.extend(_log_event_obs(ts, f, keys, evidence_id, available_at))
    return out


def extract_text_record(path: Path, evidence_id: str, available_at: datetime) -> List[Observation]:
    out: List[Observation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = HANDOVER_RE.match(line.strip())
        if not m:
            continue
        ts, system, rid, rtype, result, subject = m.groups()
        subj = None if subject.lower().startswith("no direct") else subject
        obs = status_observation(
            system=system, resource_id=rid, record_type=rtype, result=result, subject=subj,
            evidence_id=evidence_id, available_at=available_at,
            observed_at=_ts(ts) or available_at, origin="text:handover")
        if obs:
            out.append(obs)
    return out


# ---------------------------------------------------------------------------
# PDF / image extractions (multimodal cache)
# ---------------------------------------------------------------------------
def extract_media(evidence_id: str, available_at: datetime) -> List[Observation]:
    cache = load_media_cache()
    entry = cache.get(evidence_id)
    if not entry:
        return []
    out: List[Observation] = []
    for item in entry.get("observations", []):
        rid = item["resource_id"]
        keys = {norm_key(k) for k in item.get("identifiers", [])} - {None}
        out.append(Observation(
            evidence_id=evidence_id,
            available_at=available_at,
            observed_at=_ts(item.get("observed_at")) or available_at,
            system_id=item.get("system_id") or canonical_system(rid, None),
            resource_id=rid,
            category=item.get("category") or resource_info(rid)[1],
            present=item.get("present"),
            exposed=item.get("exposed"),
            linkable=item.get("linkable"),
            active=item.get("active"),
            keys=frozenset(keys),
            origin="media",
        ))
    return out


def load_media_cache() -> Dict[str, Any]:
    from .media_extractions import MEDIA_EXTRACTIONS
    return MEDIA_EXTRACTIONS


# ---------------------------------------------------------------------------
# system_activity.csv
# ---------------------------------------------------------------------------
REPOPULATED_RE = re.compile(r"repopulated downstream resource (\S+?)\.?$")


def extract_activity(rows: Iterable[Dict[str, str]]) -> List[Observation]:
    """Only observational activity rows become state evidence.

    Workflow results (DELETE_RECORD SUCCESS, "Policy action completed" ...) are
    claims and are *not* turned into state.  Checks and repopulation events
    describe what a system actually did, so they are kept.
    """
    out: List[Observation] = []
    for row in rows:
        et = _ts(row.get("event_time"))
        if et is None:
            continue
        aid = row["activity_id"]
        etype = row.get("event_type", "")
        rid = row.get("resource_id", "")
        details = row.get("details", "") or ""
        base = dict(evidence_id=aid, available_at=et, observed_at=et, origin=f"activity:{etype}")
        if etype == "CHECK_DATA_FLOW" and "remains enabled" in details:
            out.append(Observation(system_id=canonical_system(rid, row.get("target_system")),
                                   resource_id=rid, category="DATA_FLOW", present=True,
                                   active=True, **base))
        elif etype == "CHECK_RESTORE_ACCESS" and "can still be restored" in details:
            out.append(Observation(system_id=canonical_system(rid, row.get("target_system")),
                                   resource_id=rid, category="BACKUP_ARCHIVE", present=True,
                                   active=True, **base))
        elif etype in ("SYNC_RECORD", "RESTORE_BACKUP") and "repopulated downstream resource" in details:
            m = REPOPULATED_RE.search(details)
            category = "DATA_FLOW" if etype == "SYNC_RECORD" else "BACKUP_ARCHIVE"
            target = m.group(1) if m else None
            out.append(Observation(system_id=canonical_system(rid, row.get("source_system")),
                                   resource_id=rid, category=category, present=True,
                                   active=True, refs=frozenset({target} if target else ()), **base))
            if target:
                # the recreated copy exists again, and the process that recreated
                # it belongs to the same subject
                out.append(Observation(system_id=canonical_system(target, row.get("target_system")),
                                       resource_id=target, category=resource_info(target)[1],
                                       present=True, exposed=True, linkable=True,
                                       refs=frozenset({rid}), **base))
    return out


# ---------------------------------------------------------------------------
# Catalog links (data_catalog LINK_RESOURCE_IDENTITY rows)
# ---------------------------------------------------------------------------
LINK_RE = re.compile(r"(?:linked|confirmed) (\S+) \(([^)]+)\) (?:to|belongs only to) (\S+) and (user_\d+)")


@dataclass
class CatalogLink:
    activity_id: str
    at: datetime
    system_id: str
    resource_id: str
    alias: str
    keys: frozenset


def extract_catalog_links(rows: Iterable[Dict[str, str]]) -> List[CatalogLink]:
    out = []
    for row in rows:
        if row.get("event_type") != "LINK_RESOURCE_IDENTITY":
            continue
        m = LINK_RE.search(row.get("details", ""))
        if not m:
            continue
        rid, alias, email, user = m.groups()
        out.append(CatalogLink(
            activity_id=row["activity_id"], at=_ts(row["event_time"]),
            system_id=row.get("target_system") or canonical_system(rid, None),
            resource_id=rid, alias=alias,
            keys=frozenset(k for k in (norm_key(email), norm_key(user)) if k)))
    return out


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def all_observations() -> Tuple[Observation, ...]:
    manifest = read_csv(DATASET / "evidence_files.csv")
    out: List[Observation] = []
    for m in manifest:
        path = DATASET / m["file_path"]
        eid = m["file_id"]
        avail = parse_timestamp(m["captured_at"])
        ext = path.suffix.lower()
        if ext == ".sql":
            out.extend(extract_sql(path, eid, avail))
        elif ext == ".json":
            out.extend(extract_json(path, eid, avail))
        elif ext == ".log":
            out.extend(extract_log(path, eid, avail))
        elif ext == ".txt":
            out.extend(extract_text_record(path, eid, avail))
        elif ext in (".pdf", ".png", ".jpg", ".jpeg"):
            out.extend(extract_media(eid, avail))
    out.extend(extract_activity(read_csv(DATASET / "system_activity.csv")))
    return tuple(out)


@lru_cache(maxsize=1)
def catalog_links() -> Tuple[CatalogLink, ...]:
    return tuple(extract_catalog_links(read_csv(DATASET / "system_activity.csv")))
