# ORCHESTRATION.md: Ghost Data Still Exists (simple, step-by-step)

This guide is written for an agent that works best with small, clear steps.
Follow it in order. Do not skip steps. Do not do two steps at once.

---

## PART A. READ THIS FIRST

### A1. The goal in one sentence
For each of the 518 requests in `dataset/deletion_requests.csv`, decide if the person's data is really deleted, and write one row to the root `output.csv`.

### A2. Output format
Header: `case_id,deletion_status,steps_json`
- `deletion_status` is one of `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`
- `steps_json` is a JSON list. For `NOT_APPLICABLE` it is `[]`.
- Exactly 518 rows, sorted by `case_id`.

### A3. Ten golden rules
1. **One step at a time.** Finish a step, check it, write progress, then move on.
2. **Look before you code.** Print real data from every file before writing code that uses it.
3. **Never guess a column name.** Print the header first and copy it exactly.
4. **No hardcoding.** Never type a real case_id, email, user_id, resource_id, evidence_id or system name into code because you saw it in a sample. Names must come from the data.
5. **Python standard library only** (`csv json sqlite3 re pathlib datetime hashlib`). Ask the human before adding any package.
6. **Code writes the answer.** An LLM must never write `steps_json`. Code does.
7. **Claims are not proof.** `reported_status` and "success" in logs are claims. Proof is a record that exists or does not exist in the evidence at `audit_at`.
8. **Ignore anything after `audit_at`.** Among events before it, the latest one wins.
9. **Check the score after every change.** Run the evaluation script. If the score gets worse, undo the change.
10. **Write progress to `PROGRESS.md`** after every step (template in Part G). If you lose context, read `PROGRESS.md` and this file, then continue.

### A4. The four modes and when to use them
| Mode | Use it to | Never |
| --- | --- | --- |
| **Plan** | choose the next step, update `PROGRESS.md` | edit code |
| **Code** | do exactly one step from Part C | change more than that step needs |
| **Debug** | find why a case is wrong (Part E) | rewrite big parts of the code |
| **Ask** | answer "what does this file/rule say?" by reading files | edit anything, or guess |

Loop: **Plan picks a step → Code does it → run checks → pass? Plan picks next. Fail? Debug, then Code fixes.**
When any mode is unsure about the data or the rules, switch to **Ask** and read the file.

### A5. Every turn ends with this block
```
## HANDOFF
mode: <Plan|Code|Debug|Ask>
step: <step id, e.g. C3>
status: <done|blocked>
changed_files: [..]
check_result: <score numbers or "n/a">
next: <mode> -> <step id>
```
Also append the turn to `log.txt` as `AGENTS.md` says.

---

## PART B. HOW TO READ EACH INPUT FILE

Do this section before writing any real code. Start with B0. Save what you learn to `docs/DATA_NOTES.md`.
For every file: print the header, print 5 rows, count rows, then write 3 to 5 plain sentences in `DATA_NOTES.md`.

Use this helper for every CSV (save as `code/tools/peek.py`):
```python
import csv, sys
path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
print("columns:", list(rows[0].keys()) if rows else "EMPTY")
print("row count:", len(rows))
for r in rows[:5]:
    print(r)
```
Run: `python3 code/tools/peek.py dataset/<file>.csv`

### B0. Look at the existing starter code (do this before anything else)
The repo already has a `code/` folder. Inside it there is an `evaluation/` folder, and inside that there is a `main.py`.
Do these in order:
1. Run `ls -R code` and write the tree into `docs/DATA_NOTES.md`.
2. Open `code/evaluation/main.py` and read all of it. Write 3 sentences: what it does, what it reads, what it prints or writes.
3. Check whether `code/main.py` also exists. The solution entry must be `python3 code/main.py` (writes root `output.csv`). If it does not exist, create it in step C10.
4. Do not delete or rewrite existing starter files. Extend them. If a file is an empty placeholder, you may replace it.
5. `code/evaluation/main.py` is the evaluation entry. Everything this guide calls "the evaluation script" is that file.
6. Reports go in `code/evaluation/`: `evaluation_report.md` and `usage_report.md`.

### B1. `deletion_rules.csv` (READ THIS FIRST, it is the rulebook)
Look for: the column that names a data category, the column that says what treatment is required (delete / redact / anonymize / retain or similar), any column about which identifiers may stay, any column about system or retention.
Write in `DATA_NOTES.md`: a table `category -> required treatment -> identifiers allowed to remain`.
Check: list every distinct treatment value and every distinct category. Print them with `sorted(set(...))`.

### B2. `deletion_requests.csv`
Columns (from the contract): `case_id,email,requested_at,reported_status,reported_at,audit_at,request_text`.
Look for: how `request_text` is phrased. Print 30 different `request_text` values and sort them mentally into: clear delete request, question, access/export request, "do not delete", unclear.
Check: are timestamps all one format? Is `email` always lowercase? Do any emails look like old addresses?

### B3. `sample_deletion_requests.csv` and `sample_output.csv`
These are your only answer key (32 cases). Study them closely:
1. Count statuses: how many `COMPLETE`, `INCOMPLETE`, `NOT_APPLICABLE`.
2. Pick 1 case of each status. For each, print its `steps_json` pretty-printed.
3. For every step ask: *Which input row or file made this step?* Write the answer in `DATA_NOTES.md`.
4. Note exactly: which operations appear, in what order, what `evidence_id` looks like (empty or filled) in each phase, how `system_id` and `resource_id` look.
Never copy sample values into code. Use them only to learn the pattern.

### B4. `user_identities.csv`
Look for: user id column, email, phone, email hash, name, status (active/deleted), time columns.
Check: can one user have several rows? Can two users share an email?

### B5. `user_audit_log.csv`
Look for: user id, what field changed, old value, new value, when, an `audit_id`.
Check: does an email change here create an old email that no longer appears in `user_identities.csv`? That old email must still be searched.

### B6. `system_activity.csv`
Look for: `activity_id`, time, system, resource, operation (delete, sync, export, backup, restore, index...), result/status, user id or identifier.
Print the distinct operation values and the distinct system values.
Check: find a sample case where a delete is followed later by a sync or restore. That is the "ghost" pattern.

### B7. `evidence_files.csv`
Look for: `file_id`, file path, file type, system, a time or description.
Count files per type (pdf, image, log, json, sql, txt).
Check that every listed path really exists under `dataset/evidence/`.

### B8. Evidence files, one type at a time
Open at least 2 files of each type and write what you see.

| Type | How to inspect | What to extract |
| --- | --- | --- |
| `.sql` | read as text; then load into SQLite and run `.tables` style queries via `sqlite_master` | for each table: columns and any row mentioning the user's identifiers. A file may hold several databases (primary, regional replicas, reporting, failover). Find how they are separated (comments, `ATTACH`, separate schemas) and treat each as its own copy |
| `.log` / `.txt` | print first 30 lines, then grep for an email | lines that contain the user's identifiers, with their timestamp |
| `.json` | `json.load`, print keys and one item | any field holding an identifier; the record id |
| `.pdf` | try text extraction | identifiers shown in the text |
| image | look at it | identifiers written in the image; if text reading is impossible, mark as `UNREADABLE` and ask the human |

SQL loading helper idea (adjust after you see the files):
```python
import sqlite3
con = sqlite3.connect(":memory:")
con.executescript(open(path, encoding="utf-8").read())
tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
```
If `executescript` fails, read the error, look at the line it complains about, and handle that case. Do not delete the file.

### B9. Exit check for Part B
`DATA_NOTES.md` must contain: the rules table, the list of operations seen in the samples, how each evidence type is read, and a list of open questions. If an open question blocks you, use **Ask** mode or ask the human.

---

## PART C. BUILD STEPS (do in this order)

Create the folders first:
```
code/main.py
code/audit/{loader,identity,intent,evidence,state,policy,planner,ordering,validate,llm}.py
code/evaluation/{main.py,custom_cases/}   <- main.py ALREADY EXISTS (starter), extend it
code/tools/peek.py
code/README.md   (short: how to run)
```

### C1. Loader (`loader.py`)
Do: functions that read each CSV into a list of dicts and parse timestamps into timezone-aware `datetime`.
Done when: a test script loads all CSVs and prints the row counts you recorded in Part B.

### C2. Validator (`validate.py`)
Do: a function `validate_output(path)` that checks all of:
- header is exactly `case_id,deletion_status,steps_json`
- 518 rows, sorted by `case_id`, one row per request
- status is one of the three allowed values
- `steps_json` is valid JSON list; `[]` for `NOT_APPLICABLE`
- `step_no` starts at 1 and increases by 1
- each step has the 7 keys: `step_no, phase, system_id, resource_id, operation, state, evidence_id`
- phase order is FINDING, then REMEDIATION, then VERIFICATION
- the (phase, operation, state) triple is in the allowed table below
Done when: it passes on a hand-made good file and fails on a hand-made bad file.

Allowed triples:
```
FINDING      REPORT_REMAINING_RECORD  PRESENT
FINDING      REPORT_EXPOSED_PII       PRESENT
FINDING      REPORT_ACTIVE_DATA_FLOW  ACTIVE
FINDING      REPORT_RESTORE_RISK      ACTIVE
REMEDIATION  DISABLE_DATA_FLOW        DISABLED
REMEDIATION  BLOCK_RESTORE            BLOCKED
REMEDIATION  DELETE_RECORD            ABSENT
REMEDIATION  REDACT_RECORD            REDACTED
REMEDIATION  ANONYMIZE_RECORD         ANONYMIZED
VERIFICATION VERIFY_RECORD_ABSENT     ABSENT
VERIFICATION VERIFY_RECORD_PRESENT    PRESENT
VERIFICATION VERIFY_RECORD_REDACTED   REDACTED
VERIFICATION VERIFY_RECORD_ANONYMIZED ANONYMIZED
VERIFICATION VERIFY_DATA_FLOW_DISABLED DISABLED
VERIFICATION VERIFY_RESTORE_BLOCKED   BLOCKED
```
Operation order inside each phase is the order listed above (top to bottom within that phase).

### C3. Evaluation script (`code/evaluation/main.py`, already exists)
First read the existing file fully (see B0). Extend it; do not delete what is there unless it is clearly an empty placeholder. If it is a placeholder, replace it.
Do: run the pipeline on `sample_deletion_requests.csv`, compare to `sample_output.csv`, print:
1. status accuracy (correct / total)
2. step-level accuracy: a predicted step is correct if all 7 fields match an expected step in the same case
3. per-field accuracy for `phase, system_id, resource_id, operation, state, evidence_id`
4. exact-sequence accuracy: the whole ordered list equals expected
5. for each wrong case: missing steps, extra steps, order problems
Done when: it runs even if your pipeline outputs nothing yet (score will be 0).

### C4. Identity resolution (`identity.py`)
Algorithm (write it exactly like this, in plain code):
```
1. user = find in user_identities by request email (compare lowercase, stripped).
2. if not found: search user_audit_log for the email as an old/new value; take that user_id.
3. collect identifiers for that user_id:
     - every email, phone, email_hash, name in user_identities
     - every old and new value for those fields in user_audit_log for that user_id
4. return: user_id, set of identifiers, each with its type and the time range it was valid.
5. SAFETY: if an old email is now used by a DIFFERENT user_id, do not add that other user's data.
```
Done when: for each sample case, printing the identifier set shows every email/phone/hash you expect, and none from other users.

### C5. Intent (`intent.py`)
Algorithm:
```
1. Lowercase request_text.
2. If it clearly asks to delete/erase/remove the account or data -> deletion_requested = True
3. If it is a question, an access/export/download request, a complaint without a delete ask,
   or says not to delete -> deletion_requested = False
4. Anything else -> unclear
```
Use your sample table from B3 to tune the word lists. Use the LLM only for "unclear", and only to return `{"deletion_requested": true/false}`. If no LLM is configured, default unclear to the answer that best matches the samples and note it in `PROGRESS.md`.
Done when: `NOT_APPLICABLE` vs not-NOT_APPLICABLE is correct on all 32 samples.

### C6. Evidence to facts (`evidence.py`)
Make every finding into one simple record:
```
Fact(system_id, resource_id, category, kind, state, identifiers_exposed, evidence_id, observed_at)
kind is one of: RECORD, FLOW, RESTORE_PATH
```
Build one extractor per source, one at a time, testing each on the samples before the next:
1. SQL snapshots (search every table and every text column for each identifier; one set of facts per database copy)
2. `system_activity.csv` (flows, syncs, exports, backups, restores, indexing)
3. JSON and log files
4. PDF and images (last; use the human or an LLM only if text cannot be read; cache the result in a file)
How to get `resource_id` and `system_id`: copy them from the data (table name + primary key, file id, activity resource). Look at the sample outputs to see which naming they use.
Done when: for each sample case the extractor finds the records the expected findings talk about.

### C7. State at `audit_at` (`state.py`)
Algorithm for each resource:
```
1. take all events and snapshots for it
2. throw away anything with time > audit_at
3. sort by time; the latest decides the state
4. a later restore/sync that recreates the record means PRESENT again
5. a log saying "deleted" does NOT prove absence; a snapshot without the record or an
   absence confirmed by the latest evidence does
```
Done when: states match the expected findings on the samples.

### C8. Policy (`policy.py`)
Algorithm for each fact:
```
treatment = look up fact.category in deletion_rules
if treatment is delete:    record must be ABSENT
if treatment is redact:    record may exist, but only allowed identifiers may remain
if treatment is anonymize: record may exist, but must not link to the user
if treatment is retain:    record must still exist (never delete it)
tombstone (account record kept): user_id may stay; name, email, phone, email hash must go
active data flow that can copy/recreate data: must be disabled
backup/restore path that can bring data back: must be blocked
```
A fact is a problem when reality does not match the required result. Mark its problem type:
- should be gone but is present -> remaining record
- allowed to stay but still holds forbidden identifiers -> exposed PII
- flow still active -> active data flow
- restore path still works -> restore risk
Done when: policy decisions match the samples with no hardcoded names.

### C9. Planner and ordering (`planner.py`, `ordering.py`)
Algorithm:
```
if deletion not requested: status = NOT_APPLICABLE, steps = []
else collect problems from C8
  if no problems:  status = COMPLETE
       steps = only VERIFICATION steps proving current state (include VERIFY_RECORD_PRESENT for retained records),
               each with a real evidence_id (file_id, activity_id or audit_id)
  if problems:     status = INCOMPLETE
       FINDING steps (real evidence_id) for every problem
       REMEDIATION steps for every problem (evidence_id = "")
       VERIFICATION steps for every fixed thing (evidence_id = "")
```
Mapping from problem to steps:
```
remaining record  -> REPORT_REMAINING_RECORD -> DELETE_RECORD     -> VERIFY_RECORD_ABSENT
exposed PII       -> REPORT_EXPOSED_PII      -> REDACT_RECORD or ANONYMIZE_RECORD (as policy says)
                                              -> VERIFY_RECORD_REDACTED or VERIFY_RECORD_ANONYMIZED
active flow       -> REPORT_ACTIVE_DATA_FLOW -> DISABLE_DATA_FLOW -> VERIFY_DATA_FLOW_DISABLED
restore risk      -> REPORT_RESTORE_RISK     -> BLOCK_RESTORE     -> VERIFY_RESTORE_BLOCKED
retained record   -> VERIFY_RECORD_PRESENT (to prove it was kept)
```
Ordering function (`ordering.py`), write it once and test it alone:
```
sort key = (phase_rank, operation_rank, system_id, resource_id)
phase_rank:      FINDING=0, REMEDIATION=1, VERIFICATION=2
operation_rank:  position of the operation in the table in C2 (top to bottom)
then number the steps 1,2,3,...
```
Check against the samples whether `system_id`/`resource_id` ascending is plain string order. If the samples show a different order, follow the samples.
Done when: sequence accuracy on the samples is high. Then move on to Part D.

### C10. `main.py`
Do: read `dataset/deletion_requests.csv`, run the pipeline for each case, sort by `case_id`, write root `output.csv`, then call `validate_output`.
Done when: `python3 code/main.py` produces a file that passes validation.

---

## PART D. IMPROVE THE SCORE

Repeat this loop until the sample score stops improving:
1. Run `python3 code/evaluation/main.py`.
2. Pick the **single worst failure type** (use the order in Part E).
3. Use **Debug** mode to find the cause for 1 or 2 cases of that type.
4. Use **Code** mode to make the smallest fix.
5. Re-run the evaluation. Better and nothing else worse? Keep it. Otherwise undo.
6. Add one row to the failures table (Part H).

Then check generalization:
- Hide half of the samples while tuning; test on the other half.
- Run on all 518 requests and read 15 random outputs by hand. Look for empty steps on `INCOMPLETE`, steps on `NOT_APPLICABLE`, repeated identical rows, and anything that looks copied from a sample.

---

## PART E. DEBUG CHECKLIST (follow in this order)

For a wrong case, find the **first** stage where your output differs from the expected one:
1. **Status wrong?** Check intent (C5), then identity (C4), then whether a fact was missed (C6).
2. **Missing findings?** The extractor missed a system or an identifier. Print the identifier set and which databases/files were searched.
3. **Extra findings?** A false match. Check: a retained record treated as deletable, another user's data pulled in by a reused email, an event after `audit_at` counted.
4. **Right steps, wrong order?** Check `ordering.py` only.
5. **Wrong evidence_id?** Findings and `COMPLETE` verifications need a real id of the evidence that proves the fact; remediation and future verification use `""`.
6. **Wrong operation?** Check the policy lookup and the mapping in C9.

Always print these four things for the failing case before changing code: identifier set, facts found, state at `audit_at`, policy decision.

---

## PART F. LLM AND OTHER OPTIONAL TOOLS

Use an LLM only for: unclear `request_text`, and PDFs or images that cannot be read as text.
Rules:
- Output must be strict JSON, checked by code. If it is invalid, fall back to the default and log it.
- Temperature 0. Cache every answer in a file keyed by a hash of the input, so reruns cost nothing.
- Log each call: model, provider, input tokens, output tokens. Write the log to a file during the final run. `usage_report.md` is built from this file.
- If no LLM is used in the final run, `usage_report.md` must still exist and state zero calls and zero cost.
Never put API keys in code, prompts, README or `log.txt`. Read them from environment variables.

---

## PART G. PROGRESS FILE (`PROGRESS.md`, keep it updated)

```
# PROGRESS
## Done steps
- B1 rules read  (notes in docs/DATA_NOTES.md)
...
## Current step
C5 intent
## Latest sample score
status: x/32  steps: y%  sequence: z%
## Known problems
- ...
## Open questions for the human
- ...
```

---

## PART H. REPORTS AND PACKAGING (do last)

1. `code/evaluation/evaluation_report.md` must include:
   - sample metrics: status, step-level, field-level, sequence
   - at least 3 custom test cases you made, with input, expected output, actual result. Ideas: an email changed twice with data under the oldest email; a request that is only a question (expect `NOT_APPLICABLE`, `[]`); a delete followed by a sync that recreated the record; a tombstone that still has an email hash (expect redact, not delete); a replica that still holds the user while the primary is clean; an old email reused by a different user
   - a failures table: `# | pattern | symptom | root cause | fix | score before -> after`
   - honest limitations
2. `code/evaluation/usage_report.md` (from the final full run only): providers, model names, number of calls, input and output tokens, total and average per request, estimated cost total and per request, per-model and overall totals.
3. `code/README.md`: how to run (`python3 code/main.py`), what each file does, dependencies (ideally none), where the LLM is used.
4. Package:
```
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/venv/*" "*/node_modules/*" "*/.git/*" "*/.DS_Store"
```
5. Final checks: `output.csv` has 518 sorted rows and passes `validate.py`; `code.zip` has no dataset, caches, or nested archives; no secrets anywhere; `log.txt` is complete.

---

## PART I. WHEN YOU ARE STUCK

- Unknown column or file format: print it, do not guess.
- Two rules seem to conflict: `deletion_rules.csv` and the samples win. Write the conflict in `PROGRESS.md` under open questions.
- A sample answer cannot be explained: write the case id and what is unclear in `PROGRESS.md`, skip it, continue, and come back later.
- More than 3 failed attempts on the same problem: stop, switch to **Ask** mode or tell the human exactly what you tried and what you saw.
- Never fix a score by typing a sample's answer into code.