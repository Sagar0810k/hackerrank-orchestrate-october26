"""Intent detection (Part C5): does ``request_text`` authorize deletion?

Rule-based and multilingual.  Order matters:

1. explicit *non-deletion* signals win (negated deletion, "marketing lists
   only", access/export/correction requests) -- these texts often contain
   words such as "remove" or "erase" in a negative sense;
2. otherwise a deletion verb/noun in any supported language authorizes
   deletion (this includes follow-ups such as "verify that my account was
   deleted", which ask the audit to confirm a deletion);
3. otherwise the text is not a deletion request.

All 518 evaluation texts and 32 samples are decided by rules 1-2, so the
submitted run makes no model call.  ``detect_intent`` accepts an optional
``llm`` callable (text -> bool | None) as a fallback for texts that match
neither list; it must return strict booleans and is not wired in by default.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

# --- 1. non-deletion signals (checked first) --------------------------------
NON_DELETION_PATTERNS = [
    # negated deletion / explicit refusal
    r"\bnot (?:asking|requesting|looking) (?:for|to) (?:a |an |the )?(?:deletion|delete|erasure|erase|removal|remove)",
    r"\bnot a (?:deletion|erasure) request\b",
    r"\bnot a request to (?:erase|delete|remove|close)",
    r"\b(?:do not|don't|dont|never|please don't|please do not) (?:delete|erase|remove|close|deactivate)",
    r"\bwithout (?:removing|deleting|erasing|closing)\b",
    r"\b(?:keep|leave) (?:the|my|this) (?:account|profile)\b",
    r"\bleave (?:the|my) (?:account|profile)[\w ,]* (?:active|in place|as it is)",
    r"\bcontinue using\b",
    r"\bstill (?:want|need) (?:the|my|this) account\b",
    # marketing opt-out only
    r"\bmarketing (?:lists?|emails?|messages?)? ?only\b",
    r"\bstop (?:the |all )?(?:promotional|marketing|newsletter) (?:e-?mails?|messages?)",
    r"\bunsubscribe\b", r"\bopt(?:-| )?out of (?:marketing|promotional|newsletters?)",
    # access / portability requests
    r"\bdownload my (?:account |personal )?(?:information|data)\b",
    r"\bportable format\b",
    r"\b(?:send|give|provide) me a copy\b",
    r"\bcopy of (?:the |my |last year's )?(?:information|data|invoices|records)\b",
    r"\bwhat personal (?:information|data) (?:you|do you) hold\b",
    r"\binformation request\b",
    # rectification / account support
    r"\b(?:change|update|correct|replace) (?:the |my )?(?:email|e-mail|address|phone|mobile|number|surname|name)\b",
    r"\b(?:is|are) (?:out of date|misspelled|incorrect|wrong)\b",
    r"\breset(?:ting)? (?:the |my )?(?:login|password)\b",
    # other languages
    r"\bno (?:borren|eliminen|quiero eliminar)\b", r"\bnão (?:excluam|apaguem|quero excluir)\b",
    r"\bne (?:supprimez|pas supprimer)\b",
]

# --- 2. deletion signals ------------------------------------------------------
DELETION_PATTERNS = [
    r"\bdelet(?:e|ed|es|ing|ion)\b", r"\berase[ds]?\b", r"\berasure\b", r"\berasing\b",
    r"\bremov(?:e|ed|al|ing)\b", r"\bpurge\b", r"\bwipe\b",
    r"\bclos(?:e|ed|ing) (?:my|this|the) account\b", r"\baccount[- ]deletion\b",
    r"\bclose (?:it|the account) (?:completely|permanently)\b",
    # follow-ups asking the audit to confirm the data is gone
    r"\b(?:profile|account|data|records?) (?:is|are|was|were|has been|have been) gone\b",
    r"\b(?:can ?not|can't|no longer) (?:identify|be linked to) me\b",
    # es / pt / fr / de / it / nl
    r"\belimina(?:r|ción|cion)\b", r"\bborra(?:r|do)\b", r"\bsuprim",
    r"\bexclus[ãa]o\b", r"\bexclu(?:ir|am)\b", r"\bapagar\b",
    r"\bsuppression\b", r"\bsupprim(?:er|ez)\b", r"\beffacer\b",
    r"\bl[öo]sch(?:en|ung)\b", r"\bcancellazione\b", r"\bverwijder",
    # ko / ja / zh
    "삭제", "탈퇴", "削除", "消去", "退会", "删除", "注销",
]

_NON = [re.compile(p, re.IGNORECASE) for p in NON_DELETION_PATTERNS]
_DEL = [re.compile(p, re.IGNORECASE) for p in DELETION_PATTERNS]


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def detect_intent(request_text: str, llm=None) -> Dict[str, object]:
    text = _clean(request_text)
    if not text:
        return {"deletion_requested": False, "method": "empty", "matched": None}
    for rx in _NON:
        m = rx.search(text)
        if m:
            return {"deletion_requested": False, "method": "non_deletion_rule", "matched": m.group(0)}
    for rx in _DEL:
        m = rx.search(text)
        if m:
            return {"deletion_requested": True, "method": "deletion_rule", "matched": m.group(0)}
    if llm is not None:
        verdict: Optional[bool] = llm(text)
        if verdict is not None:
            return {"deletion_requested": verdict, "method": "llm", "matched": None}
    return {"deletion_requested": False, "method": "no_deletion_signal", "matched": None}
