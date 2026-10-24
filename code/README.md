# Ghost Data Still Exists — deletion-audit agent

Deterministic evidence-reconstruction pipeline that decides, for every request in
`dataset/deletion_requests.csv`, whether a deletion is `COMPLETE`, `INCOMPLETE` or
`NOT_APPLICABLE`, and emits the ordered FINDING → REMEDIATION → VERIFICATION steps.

## Setup and run

Requirements: Python 3.10+ (tested with 3.12). **Standard library only**, no `pip install`.
No API keys or network access are needed.

```bash
# from the repository root
python code/main.py                     # writes ./output.csv (518 rows) and validates it
python code/evaluation/main.py          # scores the pipeline on the 32 public samples
python code/evaluation/main.py --show-diff   # ... with per-case missing/extra steps
python code/evaluation/main.py --custom      # runs the 5 participant-made evaluation cases
python code/main.py --input dataset/sample_deletion_requests.csv --output sample_pred.csv
python code/audit/validate.py output.csv     # contract checks only
python -m unittest discover -s code/tests    # 29 unit + regression tests
```

(`python3` on macOS/Linux.) A full run takes about one second.

Current results: samples status 32/32, step precision 100 %, recall 95.85 %, F1 97.88 %,
exact sequence 24/32; custom cases 5/5. Details: `evaluation/evaluation_report.md`.

## Architecture

```
request ─► intent.py ─► identity.py ─► linker.py ─► state.py ─► policy.py ─► planner.py ─► ordering.py ─► output.csv
             │              │             ▲             ▲
             │              │             └── evidence.py (all evidence → Observation records)
             │              │                     └── media_extractions.py (PDF / screenshot facts)
             └ NOT_APPLICABLE short-circuit
```

| File | Role |
| --- | --- |
| `main.py` | Entry point: runs every request, writes `output.csv`, validates it |
| `audit/loader.py` | CSV reading, ISO timestamps → UTC `datetime`, repo-relative paths |
| `audit/intent.py` | Multilingual rule-based classifier: explicit non-deletion patterns first (opt-out, export, correction, "do not delete"), then deletion verbs in EN/ES/PT/FR/DE/KO/JA/ZH |
| `audit/normalize.py` | Canonical identifier keys (email, `user_N`, email hash, `tel:` digits); exact matching only |
| `audit/identity.py` | Request email (current *or* historical) → `user_id` + every identifier from `user_identities.csv` and `user_audit_log.csv`; identifiers shared by two people are dropped |
| `audit/evidence.py` | One parser per evidence format (SQL snapshots incl. primary/replica tables, snapshot bundles, read-back exports, status lists, 8 log dialects joined by trace id, hand-over text, activity checks/repopulations, data-catalog links) → `Observation(system, resource, category, present/exposed/linkable/active, identifier keys, evidence_id, times)` |
| `audit/media_extractions.py` | Cached facts from the 4 PDFs and 11 screenshots (pdftotext + vision transcription made once during development) |
| `audit/linker.py` | Which resources belong to the request (see below) |
| `audit/state.py` | Latest in-window observation wins; copies seen at the same instant merge to the worst state; absence can be proven by a covering snapshot that omits the record |
| `audit/policy.py` | Target state per category, read from `deletion_rules.csv` (DELETE→ABSENT, REDACT→REDACTED, ANONYMIZE→ANONYMIZED, RETAIN→PRESENT, flows→DISABLED, backups→BLOCKED) |
| `audit/planner.py` | Violations → findings + remediation + post-checks (INCOMPLETE); otherwise evidence-backed checks only (COMPLETE) |
| `audit/ordering.py` | Phase → contract operation order → `system_id` → `resource_id`; consecutive `step_no` |
| `audit/validate.py` | Output contract validator |
| `evaluation/main.py` | Sample + custom evaluation (status, step P/R/F1, field and sequence accuracy) |
| `evaluation/custom_cases.py` | 5 participant-made cases with expected answers |
| `tests/` | `unittest` suite: normalisation, intent, ordering, policy decisions, run phase, validator, sample/custom regression, determinism |
| `tools/` | Small inspection helpers used while exploring the data |

### Key decisions

* **Claims are not proof.** Workflow results (`DELETE_RECORD SUCCESS`, "Policy action completed")
  never set a state. Only observations (snapshots, read-backs, lookups, scans, connector/restore
  checks, repopulation events) do.
* **Evidence window = `[requested_at, audit_at]`, by the manifest capture time.** Several log
  archives contain lines timestamped before `audit_at` but were exported after it; they are
  excluded, as the contract requires. Pre-request evidence describes the state before the deletion
  ran and produced only false links on the samples.
* **Identifier links first.** A resource belongs to the subject when an in-window observation
  carries one of the subject's identifiers, a data-catalog row links it, or a linked record points
  at it (`source_resource_id`, repopulation events).
* **Workflow-timing links second.** Profiles that now return 404 and records that were already
  anonymized/redacted carry no identifier. The deletion worker processes a request in a fixed
  slot (profile delete 0.7–1.3 h before `reported_at`; compliant-record treatments 0.05–0.55 h
  before it). Candidates are filtered by owner (evidence tying them to another person), by the
  worker's profile result matching the request's `reported_status` (SUCCESS/PARTIAL/FAILED ↔
  COMPLETE/PARTIALLY_COMPLETE/NOT_STARTED, true for 175 of 176 identifier-linked profiles), by
  the **run clock phase**, and by evidence fit. They are then assigned with forced choices first
  and a deterministic matching for real ties.
* **Run clock phase.** Each worker run has its own sub-30-second phase. Relative to the run's
  profile delete, its other actions land 9–11 s (before `reported_at`) or 20–22 s (after it) past
  a 30 s boundary. In all 307 requests with two or more identifier-linked worker actions, every
  action is within 2 s of one phase. A candidate from a run with a different phase is rejected,
  which cut tie-broken requests from 111 to 46.
* **No hard-coded answers.** No case id, email, resource id or evidence id from the samples
  appears in the pipeline; every rule is derived from the data or the contract.

## LLM usage

The submitted run makes **zero** model calls (see `evaluation/usage_report.md`). An LLM was used
only during development, to transcribe the 11 screenshots, and its output is cached in
`audit/media_extractions.py`.
