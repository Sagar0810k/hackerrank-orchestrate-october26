"""Identifier normalisation shared by identity resolution and evidence parsing.

Every identifier is reduced to one canonical string ("key") so that evidence
and identities can be compared with exact set membership:

    email       -> lower-cased address            e.g. "jane.doe@mail.com"
    user ref    -> lower-cased stable reference   e.g. "user_42"
    email hash  -> lower-case 64-hex string
    phone       -> "tel:" + digits                e.g. "tel:447700900123"
    person name -> "name:" + lower-cased words    e.g. "name:jane doe"

Exact matching (never substring matching) is deliberate: the dataset contains
decoys such as ``jane.doe.jr@mail.com`` next to ``jane.doe@mail.com``.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Set

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
USER_RE = re.compile(r"\buser_\d+\b", re.IGNORECASE)
HASH_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
PHONE_RE = re.compile(r"\+\d[\d\s\-().]{6,}\d")
RESOURCE_LIKE_RE = re.compile(r"^[a-z]+(?:_[a-z]+)*_\d+$")

NULL_STRINGS = {"", "null", "none", "nil", "-", "—", "n/a"}
REDACTED_MARKERS = ("[redacted]", "redacted", "***")

NAME_FIELDS = {"full_name", "name", "display_name", "requester_name", "customer_name"}
PHONE_FIELDS = {"phone", "requester_phone", "owner_phone", "customer_phone"}
HASH_FIELDS = {"email_hash"}
# fields whose value is a stable internal reference, not a direct identifier
REFERENCE_FIELDS = {"user_id", "customer_reference", "subject_reference", "subject_selector",
                    "subject_ref", "correlation_key", "lookup_value"}


def is_null(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in NULL_STRINGS:
        return True
    return False


def phone_key(value: str) -> Optional[str]:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 7:
        return None
    return "tel:" + digits


def name_key(value: str) -> Optional[str]:
    words = re.sub(r"\s+", " ", (value or "").strip().lower())
    if len(words.split(" ")) < 2 or any(ch.isdigit() for ch in words):
        return None
    return "name:" + words


def norm_key(value: Any, field: str = "") -> Optional[str]:
    """Normalise one identifier value.  Returns None for non-identifiers."""
    if is_null(value) or isinstance(value, (bool, int, float)):
        return None
    s = str(value).strip().strip('"')
    low = s.lower()
    if field in PHONE_FIELDS:
        return phone_key(s)
    if field in NAME_FIELDS:
        return name_key(s)
    if EMAIL_RE.fullmatch(s):
        return low
    if USER_RE.fullmatch(s):
        return low
    if HASH_RE.fullmatch(s):
        return low
    if PHONE_RE.fullmatch(s):
        return phone_key(s)
    if RESOURCE_LIKE_RE.match(low):
        return None
    return None


def keys_in_text(text: str) -> Set[str]:
    out: Set[str] = set()
    if not text:
        return out
    for m in EMAIL_RE.findall(text):
        out.add(m.lower())
    for m in USER_RE.findall(text):
        out.add(m.lower())
    for m in HASH_RE.findall(text):
        out.add(m.lower())
    for m in PHONE_RE.findall(text):
        k = phone_key(m)
        if k:
            out.add(k)
    return out


# technical fields whose values can look like identifiers (sha256 seals, object keys)
NON_IDENTIFIER_FIELDS = {"integrity_seal", "checksum", "archive_key", "archive_path", "object_key",
                         "file_name", "file", "index_name", "index"}


def collect_keys(obj: Any, field: str = "") -> Set[str]:
    """All identifier keys found anywhere inside a (nested) record."""
    out: Set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in NON_IDENTIFIER_FIELDS:
                continue
            out |= collect_keys(v, str(k))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= collect_keys(v, field)
    elif isinstance(obj, str) and not is_null(obj):
        k = norm_key(obj, field)
        if k:
            out.add(k)
        else:
            out |= keys_in_text(obj)
    return out


def has_direct_identifier(obj: Any, field: str = "") -> bool:
    """True if a record still shows a name, email, phone or email hash.

    Stable internal references (user_42) are *not* direct identifiers: an
    account tombstone or a redacted support message may keep them.
    """
    if isinstance(obj, dict):
        return any(has_direct_identifier(v, str(k)) for k, v in obj.items()
                   if str(k) not in NON_IDENTIFIER_FIELDS)
    if isinstance(obj, (list, tuple)):
        return any(has_direct_identifier(v, field) for v in obj)
    if not isinstance(obj, str) or is_null(obj):
        return False
    s = obj.strip()
    if s.lower() in REDACTED_MARKERS or s.lower().startswith("[redacted"):
        return False
    if field in REFERENCE_FIELDS:
        # a reference field may still carry a raw email (e.g. subject_selector=email)
        return bool(EMAIL_RE.search(s))
    if field in NAME_FIELDS:
        return name_key(s) is not None
    if field in PHONE_FIELDS:
        return phone_key(s) is not None
    if field in HASH_FIELDS:
        return bool(HASH_RE.fullmatch(s))
    if field in ("email", "requester_email", "owner_email", "customer_email", "matched_value"):
        return True
    return bool(EMAIL_RE.search(s) or PHONE_RE.search(s))


