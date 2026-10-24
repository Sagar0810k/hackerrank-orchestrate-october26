"""Unit tests for the pure building blocks (no dataset access needed).

Run from the repository root:  python -m unittest discover -s code/tests -v
"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit.intent import detect_intent  # noqa: E402
from audit.linker import event_phase, phase_distance  # noqa: E402
from audit.normalize import collect_keys, has_direct_identifier, norm_key  # noqa: E402
from audit.ordering import order_steps  # noqa: E402
from audit.planner import decide  # noqa: E402
from audit.state import ResourceState  # noqa: E402
from audit.validate import validate_output  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_email_is_lowercased_and_trimmed(self):
        self.assertEqual(norm_key("  Jane.Doe@Mail.COM "), "jane.doe@mail.com")

    def test_lookalike_email_is_a_different_key(self):
        self.assertNotEqual(norm_key("g.silva76@gmail.com"), norm_key("g.silva76.jr@gmail.com"))

    def test_phone_reduced_to_digits(self):
        self.assertEqual(norm_key("+44 7700 900-123", "phone"), "tel:447700900123")

    def test_stable_reference_and_hash(self):
        self.assertEqual(norm_key("USER_42"), "user_42")
        h = "A" * 64
        self.assertEqual(norm_key(h), h.lower())

    def test_resource_ids_are_not_identifiers(self):
        self.assertIsNone(norm_key("analytics_257"))

    def test_keys_found_inside_free_text(self):
        keys = collect_keys({"message_text": "Please send the update to a.b@c.com, ref user_7."})
        self.assertEqual(keys, {"a.b@c.com", "user_7"})

    def test_integrity_seal_is_not_an_email_hash(self):
        self.assertEqual(collect_keys({"integrity_seal": "sha256:" + "0" * 64}), set())

    def test_direct_identifier_rules(self):
        self.assertFalse(has_direct_identifier({"subject_reference": "user_9", "message_text": "[REDACTED]"}))
        self.assertTrue(has_direct_identifier({"requester_email": "x@y.com"}))
        self.assertTrue(has_direct_identifier({"subject_selector": "x@y.com"}))
        self.assertFalse(has_direct_identifier({"email": None, "phone": "null", "full_name": None}))


class IntentTests(unittest.TestCase):
    def assertIntent(self, text, expected):
        self.assertEqual(detect_intent(text)["deletion_requested"], expected, text)

    def test_deletion_requests(self):
        self.assertIntent("Please erase the account linked to this email address.", True)
        self.assertIntent("Solicito la eliminación permanente de la cuenta.", True)
        self.assertIntent("Je demande la suppression définitive du compte.", True)
        self.assertIntent("이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다.", True)
        self.assertIntent("このメールアドレスに関連するアカウントの完全な削除を依頼します。", True)
        self.assertIntent("Please confirm that the profile is gone and that records cannot identify me.", True)

    def test_non_deletion_requests_with_deletion_words(self):
        self.assertIntent("Please remove me from marketing lists only.", False)
        self.assertIntent("This is an information request, not a request to erase it.", False)
        self.assertIntent("Could you send me a copy? I still use it, so please don't delete anything.", False)
        self.assertIntent("Can you correct it without removing any of my records?", False)

    def test_empty_text(self):
        self.assertIntent("", False)


class OrderingTests(unittest.TestCase):
    def step(self, phase, op, system, rid, state="ABSENT"):
        return {"phase": phase, "operation": op, "system_id": system, "resource_id": rid,
                "state": state, "evidence_id": ""}

    def test_phase_then_operation_then_system_then_resource(self):
        steps = [
            self.step("VERIFICATION", "VERIFY_RECORD_PRESENT", "security_service", "audit_record_1", "PRESENT"),
            self.step("VERIFICATION", "VERIFY_RECORD_ABSENT", "search_service", "search_2"),
            self.step("REMEDIATION", "DELETE_RECORD", "search_service", "search_2"),
            self.step("REMEDIATION", "DISABLE_DATA_FLOW", "integration_service", "data_flow_1", "DISABLED"),
            self.step("FINDING", "REPORT_ACTIVE_DATA_FLOW", "integration_service", "data_flow_1", "ACTIVE"),
            self.step("FINDING", "REPORT_REMAINING_RECORD", "search_service", "search_2", "PRESENT"),
            self.step("VERIFICATION", "VERIFY_RECORD_ABSENT", "account_service", "account_1"),
        ]
        out = order_steps(steps)
        self.assertEqual([s["step_no"] for s in out], list(range(1, 8)))
        self.assertEqual([s["operation"] for s in out], [
            "REPORT_REMAINING_RECORD", "REPORT_ACTIVE_DATA_FLOW", "DISABLE_DATA_FLOW", "DELETE_RECORD",
            "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT"])
        self.assertEqual(out[4]["system_id"], "account_service")
        self.assertEqual(list(out[0].keys()),
                         ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"])

    def test_duplicates_removed(self):
        s = self.step("REMEDIATION", "DELETE_RECORD", "search_service", "search_2")
        self.assertEqual(len(order_steps([s, dict(s)])), 1)


class PolicyDecisionTests(unittest.TestCase):
    def rs(self, rid, category, **kw):
        base = dict(system_id="x", resource_id=rid, category=category, present=None, exposed=None,
                    linkable=None, active=None, evidence_id="evidence_1")
        base.update(kw)
        return ResourceState(**base)

    def test_deleted_category_still_present_is_remaining(self):
        d = decide(self.rs("search_1", "SEARCH_INDEX_ENTRY", present=True, exposed=True))
        self.assertEqual((d.problem, d.target), ("REMAINING", "ABSENT"))

    def test_absent_profile_is_proven_compliant(self):
        d = decide(self.rs("account_1", "USER_PROFILE", present=False))
        self.assertIsNone(d.problem)
        self.assertTrue(d.proven)

    def test_tombstone_with_identifiers_needs_redaction_not_deletion(self):
        d = decide(self.rs("tombstone_1", "ACCOUNT_TOMBSTONE", present=True, exposed=True))
        self.assertEqual(d.problem, "EXPOSED_REDACT")

    def test_tombstone_with_only_user_reference_is_compliant(self):
        d = decide(self.rs("tombstone_1", "ACCOUNT_TOMBSTONE", present=True, exposed=False, linkable=True))
        self.assertIsNone(d.problem)
        self.assertEqual(d.verify_state, "REDACTED")

    def test_analytics_still_linkable_needs_anonymization(self):
        d = decide(self.rs("analytics_1", "ANALYTICS_PROFILE", present=True, exposed=False, linkable=True))
        self.assertEqual(d.problem, "EXPOSED_ANONYMIZE")

    def test_retained_audit_record_is_verified_present(self):
        d = decide(self.rs("audit_record_1", "SECURITY_AUDIT_LOG", present=True))
        self.assertEqual((d.problem, d.verify_state, d.proven), (None, "PRESENT", True))

    def test_flows_and_restores(self):
        self.assertEqual(decide(self.rs("data_flow_1", "DATA_FLOW", present=True, active=True)).problem,
                         "ACTIVE_FLOW")
        self.assertEqual(decide(self.rs("backup_1", "BACKUP_ARCHIVE", present=True, active=True)).problem,
                         "RESTORE_RISK")
        self.assertIsNone(decide(self.rs("backup_1", "BACKUP_ARCHIVE", present=True, active=False)).problem)


class RunPhaseTests(unittest.TestCase):
    def test_phase_shifts_match_run_structure(self):
        rep = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
        account = rep - timedelta(minutes=51, seconds=17)          # profile delete
        before = account + timedelta(minutes=22, seconds=41)       # treatment before the report
        after = account + timedelta(hours=1, minutes=50, seconds=52)  # action after the report
        p0 = event_phase(account, "account_1", rep)
        self.assertLessEqual(phase_distance(p0, event_phase(before, "analytics_1", rep)), 1)
        self.assertLessEqual(phase_distance(p0, event_phase(after, "search_1", rep)), 1)

    def test_phase_distance_is_circular(self):
        self.assertEqual(phase_distance(29.0, 1.0), 2.0)


class ValidatorTests(unittest.TestCase):
    def write(self, rows):
        f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        w = csv.writer(f)
        w.writerow(["case_id", "deletion_status", "steps_json"])
        w.writerows(rows)
        f.close()
        return Path(f.name)

    def test_good_file_passes(self):
        step = {"step_no": 1, "phase": "VERIFICATION", "system_id": "account_service",
                "resource_id": "account_1", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT",
                "evidence_id": "evidence_1"}
        path = self.write([["case_2", "COMPLETE", json.dumps([step])], ["case_10", "NOT_APPLICABLE", "[]"]])
        ok, msgs = validate_output(path, ["case_10", "case_2"])
        self.assertTrue(ok, msgs)

    def test_bad_triple_and_steps_on_not_applicable_fail(self):
        step = {"step_no": 1, "phase": "FINDING", "system_id": "a", "resource_id": "b",
                "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""}
        path = self.write([["case_1", "INCOMPLETE", json.dumps([step])],
                           ["case_2", "NOT_APPLICABLE", json.dumps([step])]])
        ok, msgs = validate_output(path, ["case_1", "case_2"])
        self.assertFalse(ok)
        self.assertTrue(any("not allowed" in m for m in msgs))
        self.assertTrue(any("NOT_APPLICABLE" in m for m in msgs))


if __name__ == "__main__":
    unittest.main()
