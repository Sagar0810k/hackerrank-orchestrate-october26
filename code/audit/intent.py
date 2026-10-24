"""Intent detection (Part C5).

Decides whether request_text authorizes deletion of the account/personal data.
Returns {"deletion_requested": bool}.
"""
from __future__ import annotations

import os
import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

# Words that clearly ask to delete / erase / remove the account or data.
DELETE_WORDS = [
    "delete", "deletion", "delete my", "erase", "erase my", "remove my",
    "remove the account", "close my account", "close the account",
    "supprimer", "eliminar", "borrar", "cutto", "kaatso", "ausradieren", "löschen",
    "permanently delete", "permanent deletion", "remove all my data",
    "wipe", "wipe my", "purge", "purge my",
]

# Non-deletion intents that should NOT trigger deletion.
NON_DELETE_WORDS = [
    "access my", "export my", "download my", "copy of my data", "portability",
    "rectify", "correct my", "update my", "change my email", "change my address",
    "marketing opt", "opt out", "unsubscribe", "stop emailing", "do not call",
    "complaint", "dispute", "question", "inquiry", "inquire",
    "do not delete", "please do not delete", "not delete", "never delete",
    "keep my", "retain my", "restore my account", "reactivate",
]

# Phrases that explicitly refuse/withdraw deletion.
REFUSE_DELETE = [
    "do not delete", "please do not delete", "do not delete my",
    "not delete", "never delete", "do not erase", "do not remove",
    "i do not want", "i do not want my data deleted",
]

CACHE_DIR = Path("code/audit/_llm_cache")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _cache_path(text: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{key}.json"


def _llm_decide(text: str) -> Optional[bool]:
    """Ask an LLM (if configured) for a strict JSON bool. Returns None if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        import urllib.request  # stdlib only
        prompt = (
            'Return ONLY strict JSON {"deletion_requested": true/false}. '
            "Does this request authorize deleting the user's account/personal data? "
            "Access, export, correction, marketing opt-out, complaint, or 'do not delete' = false.\n"
            f'REQUEST: {text}'
        )
        data = json.dumps({
            "model": "claude-3-haiku-20240307",
            "max_tokens": 50,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body.get("content", [{}])[0].get("text", "")
        m = re.search(r"\{[\s\S]*?\}", content)
        if m:
            obj = json.loads(m.group(0))
            return bool(obj.get("deletion_requested", False))
    except Exception:
        return None
    return None


def detect_intent(request_text: str) -> Dict[str, Any]:
    """Detect deletion intent.

    Priority:
      1. explicit refuse -> False
      2. delete keywords -> True
      3. non-delete keywords -> False
      4. LLM (if configured & cached) -> bool
      5. default: True (treat as deletion unless clearly otherwise)
    """
    result: Dict[str, Any] = {"deletion_requested": True, "method": "default", "text": request_text}
    text = _norm(request_text)

    if not text:
        result["deletion_requested"] = False
        result["method"] = "empty"
        return result

    # 1. explicit refuse / withdraw
    if any(w in text for w in REFUSE_DELETE):
        result["deletion_requested"] = False
        result["method"] = "refuse"
        return result

    # 2. clear delete request
    if any(w in text for w in DELETE_WORDS):
        result["deletion_requested"] = True
        result["method"] = "keywords"
        return result

    # 3. clearly non-delete
    if any(w in text for w in NON_DELETE_WORDS):
        result["deletion_requested"] = False
        result["method"] = "non_delete_keywords"
        return result

    # 4. unclear -> LLM if available
    llm = _llm_decide(request_text)
    if llm is not None:
        result["deletion_requested"] = llm
        result["method"] = "llm"
        return result

    # 5. default: when unsure, treat as a deletion request (safer for audit)
    result["method"] = "default_delete"
    return result
