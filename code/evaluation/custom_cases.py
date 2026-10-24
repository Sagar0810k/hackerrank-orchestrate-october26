"""Participant-made evaluation cases (beyond the 32 public samples).

Each case is a new request row run against the real participant dataset.
Expected answers are either inherited from a public sample whose answer is
known (when the variation must not change the answer) or derived by hand
from the evidence files (reasoning written next to each case).

Run:  python code/evaluation/main.py --custom
"""
from __future__ import annotations

CUSTOM_CASES = [
    {
        "case_id": "custom_01",
        "purpose": "Historical identity: request sent from the subject's *old* email address.",
        "request": {
            "email": "minjun.kim90@gmail.com",  # user_12 before audit_282 changed it
            "requested_at": "2026-08-24T12:00:00Z", "reported_status": "COMPLETE",
            "reported_at": "2026-08-25T12:00:00Z", "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "I changed the email on this account before deleting it. Please check "
                            "that nothing tied to the old address was left behind.",
        },
        # Same person and window as sample case_12, so the answer must be identical.
        "expected_from_sample": "case_12",
    },
    {
        "case_id": "custom_02",
        "purpose": "Identifier normalisation: mixed case and surrounding spaces in the request email.",
        "request": {
            "email": "  Leila.Haddad@Yahoo.COM ",
            "requested_at": "2026-08-27T14:17:00Z", "reported_status": "COMPLETE",
            "reported_at": "2026-08-28T09:03:00Z", "audit_at": "2026-09-08T13:40:00Z",
            "request_text": "Please delete my account; the same email is still recognized.",
        },
        "expected_from_sample": "case_05",
    },
    {
        "case_id": "custom_03",
        "purpose": "State at audit_at: same subject as sample case_27 (COMPLETE at 2026-09-15) but "
                   "audited after evidence_02 (captured 2026-09-17), whose account snapshot shows "
                   "account_3866 ACTIVE again with the subject's email.",
        "request": {
            "email": "ananya-nair@gmail.com",
            "requested_at": "2026-08-29T12:00:00Z", "reported_status": "COMPLETE",
            "reported_at": "2026-08-30T12:00:00Z", "audit_at": "2026-09-18T12:00:00Z",
            "request_text": "Please audit the deletion of my account as it stands today.",
        },
        # Hand-derived: latest in-window observation of account_3866 is evidence_02's
        # 2026-09-17 snapshot (present, email exposed) -> remaining record.  Every other
        # record of user_27 keeps its compliant state from the 2026-09-15 evidence and is
        # listed as a post-remediation check (empty evidence_id because the case is INCOMPLETE).
        "expected": {
            "deletion_status": "INCOMPLETE",
            "steps": [
                ("FINDING", "account_service", "account_3866", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_02"),
                ("REMEDIATION", "account_service", "account_3866", "DELETE_RECORD", "ABSENT", ""),
                ("VERIFICATION", "account_service", "account_3866", "VERIFY_RECORD_ABSENT", "ABSENT", ""),
                ("VERIFICATION", "security_service", "audit_record_3830", "VERIFY_RECORD_PRESENT", "PRESENT", ""),
                ("VERIFICATION", "support_platform", "support_4707", "VERIFY_RECORD_REDACTED", "REDACTED", ""),
                ("VERIFICATION", "analytics_platform", "analytics_4574", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED", ""),
                ("VERIFICATION", "integration_service", "data_flow_2295", "VERIFY_DATA_FLOW_DISABLED", "DISABLED", ""),
                ("VERIFICATION", "backup_service", "backup_5970", "VERIFY_RESTORE_BLOCKED", "BLOCKED", ""),
            ],
        },
    },
    {
        "case_id": "custom_04",
        "purpose": "Intent: a marketing opt-out that uses the word 'remove' must not authorize deletion.",
        "request": {
            "email": "e.varga90@yahoo.com",
            "requested_at": "2026-08-17T12:00:00Z", "reported_status": "PARTIALLY_COMPLETE",
            "reported_at": "2026-08-19T12:00:00Z", "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "Please remove me from the marketing newsletter only. I want to keep my "
                            "account open.",
        },
        "expected": {"deletion_status": "NOT_APPLICABLE", "steps": []},
    },
    {
        "case_id": "custom_05",
        "purpose": "Multilingual intent: a German deletion request for the subject of sample case_13.",
        "request": {
            "email": "noor-khalil@proton.me",
            "requested_at": "2026-09-08T12:00:00Z", "reported_status": "NOT_STARTED",
            "reported_at": "2026-09-09T12:00:00Z", "audit_at": "2026-10-01T12:00:00Z",
            "request_text": "Bitte löschen Sie mein Konto und alle damit verbundenen "
                            "personenbezogenen Daten.",
        },
        "expected_from_sample": "case_13",
    },
]
