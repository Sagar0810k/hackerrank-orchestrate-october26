# Evaluation report — Ghost Data Still Exists

All numbers below come from `python code/evaluation/main.py` (public samples) and
`python code/evaluation/main.py --custom` (participant-made cases) on the final code.
The pipeline is deterministic: repeated runs produce a byte-identical `output.csv`.

## 1. Metrics on the 32 public samples

| Metric | Result |
| --- | --- |
| Case-level `deletion_status` accuracy | **32 / 32 = 100.00 %** (COMPLETE 10/10, INCOMPLETE 22/22) |
| Step precision (exact match of phase, system_id, resource_id, operation, state, evidence_id) | **185 / 185 = 100.00 %** |
| Step recall | **185 / 193 = 95.85 %** |
| Step F1 | **97.88 %** |
| Sequence accuracy (whole ordered `steps_json` identical) | **24 / 32 = 75.00 %** |

Field-level accuracy (position-aligned: step *i* of the prediction vs step *i* of the answer,
over all 193 expected steps; a single missing step shifts every later position, so these are
stricter than the step-level numbers):

| phase | system_id | resource_id | operation | state | evidence_id |
| --- | --- | --- | --- | --- | --- |
| 95.85 % | 89.64 % | 89.64 % | 89.64 % | 89.64 % | 95.34 % |

Generalization checks (no rule was fitted to individual sample answers; the timing windows, the
status↔worker-result mapping and the run phase were measured on identifier-linked records of all
550 requests):

| Subset | Status | Step P | Step R | Step F1 | Sequence |
| --- | --- | --- | --- | --- | --- |
| odd-numbered samples (16) | 16/16 | 100 % | 96.8 % | 98.4 % | 13/16 |
| even-numbered samples (16) | 16/16 | 100 % | 95.0 % | 97.4 % | 11/16 |
| hand-written samples 01–10 | 10/10 | 100 % | 93.5 % | 96.7 % | 8/10 |
| generated samples 11–32 | 22/22 | 100 % | 96.3 % | 98.1 % | 16/22 |

Unit and regression tests: `python -m unittest discover -s code/tests` (29 tests, all pass). They
cover normalisation, intent, ordering, policy decisions, run-phase maths, the validator, the sample
and custom quality floors, and determinism of the full run.

### Remaining sample errors (8 cases, 8 missing steps, 0 extra)

| Case | Missing | Root cause | Fixable? |
| --- | --- | --- | --- |
| 18, 20, 23, 24, 29, 30, 09 | one `VERIFY_RECORD_PRESENT` on a security audit record each | The record id appears only in evidence captured **after** `audit_at` (evidence_02, evidence_06) or in no participant file at all (audit_record_6645, audit_record_5569). Using it would break the time cut-off rule. | No, by design |
| 04 | `account_004` | The hand-written case has no worker activity and no evidence row for this account. | No |

## 2. Participant-made evaluation cases

Defined in `code/evaluation/custom_cases.py` and run against the real dataset. Expected answers
are either inherited from a public sample whose answer is known (the variation must not change
it) or derived by hand from the evidence.

| Case | Purpose | Input (changed fields) | Expected | Actual |
| --- | --- | --- | --- | --- |
| custom_01 | Historical identity | `email = minjun.kim90@gmail.com` (old address of user_12, see audit_282); timestamps and text of sample case_12 | Same as sample case_12: INCOMPLETE, REMAINING `analytics_platform/analytics_9914` (evidence_01) → DELETE → verify account_9797 ABSENT, analytics_9914 ABSENT, audit_record_2945 PRESENT | PASS, 5/5 steps, exact sequence |
| custom_02 | Identifier normalisation | `email = "  Leila.Haddad@Yahoo.COM "`; timestamps of sample case_05 | Same as sample case_05: INCOMPLETE, REMAINING `account_005` (failover replica, evidence_54) → DELETE → VERIFY ABSENT | PASS, 3/3 |
| custom_03 | State at `audit_at` | Subject of sample case_27 (COMPLETE at 2026-09-15) but `audit_at = 2026-09-18T12:00Z`, after evidence_02 (captured 2026-09-17) whose account snapshot shows `account_3866` ACTIVE with the subject's email | INCOMPLETE: REMAINING account_3866 (evidence_02) → DELETE; post-checks with empty evidence: account_3866 ABSENT, audit_record_3830 PRESENT, support_4707 REDACTED, analytics_4574 ANONYMIZED, data_flow_2295 DISABLED, backup_5970 BLOCKED | PASS, 8/8 (failed before fix #9 below) |
| custom_04 | Intent with misleading verb | Sample case_19 subject, text "Please remove me from the marketing newsletter only. I want to keep my account open." | NOT_APPLICABLE, `[]` | PASS |
| custom_05 | Multilingual intent | Sample case_13 subject and timestamps, German text "Bitte löschen Sie mein Konto und alle damit verbundenen personenbezogenen Daten." | Same as sample case_13 (8 steps) | PASS, 8/8 |

Custom suite totals: status 5/5, step P/R/F1 100 % / 100 % / 100 %, sequence 5/5.

## 3. Full evaluation run (518 requests)

* Output: 518 rows, contract validator passes (`validate: validation passed`).
* Status mix: INCOMPLETE 355, COMPLETE 153, NOT_APPLICABLE 10.
* 3,131 steps (6.16 per deletion request); findings: 368 remaining records, 214 exposed-PII
  records, 113 active data flows, 26 restore risks. All 1,244 cited evidence ids are participant
  `file_id`s captured inside the request window.
* Manual review: every evidence batch (≈10 requests per generated evidence file) was printed and
  read (status-list files, diagnostic logs, regional/reporting/failover replicas, read-back
  exports, bundles, multimodal cases). The 10 non-deletion requests are exactly the ones whose
  accounts appear in `CLASSIFY_REQUEST … as non-deletion` activity rows. Three log archives
  (evidence_11, 21, 44) are never cited because they were exported after their requests'
  `audit_at`.
* Uncertainty: 370 requests use at least one workflow-timing link; 46 contain a link chosen by
  the tie-break (42 profiles, 4 anonymized analytics profiles). These are concurrent runs whose
  clock phases collide, so expect some wrong resource ids there.

## 4. Failures found and improvements made

Scores are on the 32 samples unless noted.

| # | Pattern | Symptom | Root cause | Fix | Before → after |
| --- | --- | --- | --- | --- | --- |
| 1 | Broken starter code | `evidence.py` raised `IndentationError`; validator had a duplicated tail; evaluation printed field accuracy 2.78 % | Earlier draft pasted code twice; field denominators accumulated per field and per step | Rewrote `evidence.py`, cleaned the validator, rewrote `evaluation/main.py` (multiset step matching, aligned fields) | pipeline could not run → runs |
| 2 | Decoy look-alike emails | `smartinez6461.jr@…`, `g.silva76.jr@…` | Substring matching | Exact canonical keys only (`normalize.py`) | 0 decoy links |
| 3 | Pre-request evidence | 3 false resource links on samples (e.g. a tombstone screenshot from March for a September request) | Window had no lower bound | Evidence window `[requested_at, audit_at]` by manifest capture time | 3 false links → 0, recall unchanged (76/111 resources) |
| 4 | Follow-up phrasing | Sample case_26 ("confirm that the profile is gone…") classified non-deletion | No deletion verb | Added follow-up patterns ("is gone", "cannot identify me") | status 31/32 → 32/32 |
| 5 | Identifier-less records | Absent accounts (404) and anonymized analytics never linked | No identifier left on the record | Workflow-timing links around `reported_at` | resources 76/111 → 93/111; step F1 92.11 % (first end-to-end run) |
| 6 | Concurrent requests | Wrong account given to COMPLETE requests | Several requests share `reported_at` | Evidence-fit tiers: COMPLETE-looking requests prefer evidenced candidates, INCOMPLETE-looking ones unevidenced | P 93.58 → 95.11 %, F1 92.11 → 92.84 % |
| 7 | Concurrent requests | Remaining account swaps | Ties | Worker profile result must match `reported_status` (175/176) | P 95.11 → 99.46 %, R 90.67 → 94.82 %, F1 → 97.08 %, sequence 17 → 22 |
| 8 | Batch slots | 6 evaluation COMPLETE requests without an account check | ±2 h windows let the next hour's batch win | Per-type core slots measured from data (profiles −1.3…−0.7 h; treatments −0.55…0 h) with a ±0.2 h fallback | evaluation: 6 → 1 request missing the account (samples unchanged) |
| 9 | Non-deletion requests | A NOT_APPLICABLE request took a deletion-worker account from case_547 | Timing links considered every request | Exclude non-deletion requests from timing links | evaluation: case_547 gained its account |
| 10 | Same person, two requests | custom_03 lost `analytics_4574` to sample case_27 | Timing links were exclusive per request | Share a timing-linked record with every request of the same subject whose window holds the same worker action | custom 4/5 → 5/5, samples unchanged |
| 11 | Replica copies | Primary and replica rows at the same instant can disagree | `max()` picked one copy | Merge same-instant copies to the worst state (any copy present/exposed/active) | defensive, no score change |
| 12 | Technical hashes | `integrity_seal` sha256 values parsed as email hashes | Generic 64-hex detection | Skip technical fields (`integrity_seal`, `archive_key`, …) | defensive, no score change |
| 13 | Concurrent runs | 111 evaluation requests still decided by tie-break; sample case_03 wrong | Timing and status alone cannot separate runs reporting at the same minute | **Run clock phase**: actions of one worker run share a sub-30 s phase (307/307 requests within 2 s). Candidates from a run with another phase are rejected, and a profile assigned to a request fixes its phase for the next record type. Re-checked that INCOMPLETE requests must still not take already-treated records: in the samples, phase matches there belong to other runs | P 99.46 → 100 %, R 94.82 → 95.34 %, F1 → 97.61 %, sequence 22 → 23; eval tie-broken requests 111 → 46 |
| 14 | Rule exception | Sample case_08 lost its only profile candidate | Strict status↔result filter (wrong for 1/176) | Mismatched result is the lowest tier, used only when nothing else fits (applies to case_08 only) | R 95.34 → 95.85 %, F1 → 97.88 %, sequence 23 → 24 |

## 5. Limitations and honest caveats

* **Ties are guessed.** When concurrent requests share the same reported status *and* the same
  run clock phase, and each needs an identifier-less record, no participant evidence tells them
  apart. The pipeline assigns them deterministically (earliest worker action ↔ earliest request)
  and records a note. This affects 46 of 518 evaluation requests.
* **The run-phase signal is statistical.** It holds for every identifier-linked request (307/307
  within 2 s), but two concurrent runs collide in phase about a quarter of the time. It narrows
  candidates and never overrides identifier evidence.
* **Missing retained records.** INCOMPLETE answers in the key list retained audit records that
  are invisible before `audit_at`; we do not reproduce them.
* **Multimodal cache.** Screenshot facts were transcribed once with a vision model and stored in
  `audit/media_extractions.py`. New images need that step to be re-run; the cache records what each
  artifact shows, not which request it belongs to.
* **One screenshot contradicts its catalog link.** `marketing_001` is catalogued to user_09, but
  the screenshot shows a different name and email. The pipeline follows the catalog link for
  ownership and the screenshot for state (record present), so evaluation case_63 is reported
  INCOMPLETE. This is a judgement call.
* **Legal-hold register PDF** lists user references without resource ids, so it cannot produce
  steps.
* Rule-based intent covers the languages present in the data (EN, ES, PT, FR, KO, JA plus DE/IT/NL/ZH
  keywords); unseen phrasings without a deletion verb default to NOT_APPLICABLE.
