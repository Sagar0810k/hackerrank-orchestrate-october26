# DATA NOTES — Ghost Data Still Exists

## Source: Part B (file inspection)

### deletion_rules.csv
Columns: rule_id, data_category, condition, required_action (15 rules)

Table: category -> required treatment -> notes on identifiers allowed to remain

| data_category | required_action | condition |
|---|---|---|
| USER_PROFILE | DELETE | Always |
| SECONDARY_IDENTIFIER | DELETE | Always |
| SEARCH_INDEX_ENTRY | DELETE | Always |
| CACHE_ENTRY | DELETE | Always |
| SUPPORT_MESSAGE | REDACT | Conversation contains shared customer, agent, or order context that must be retained |
| SUPPORT_ATTACHMENT | DELETE | Attachment belongs only to the deletion subject |
| ANALYTICS_PROFILE | ANONYMIZE | Record is still attributable to a user |
| PRODUCT_TELEMETRY | ANONYMIZE | Record is still attributable to a user |
| USER_EXPORT | DELETE | Always |
| MARKETING_PROFILE | DELETE | Always |
| EMAIL_DELIVERY_LOG | REDACT | Log contains a user email address |
| SECURITY_AUDIT_LOG | RETAIN | Record is within the supplied retention period |
| LEGAL_HOLD_RECORD | RETAIN | A supplied legal hold is active |
| BACKUP_ARCHIVE | RETAIN | Restore access can be blocked |
| ACCOUNT_TOMBSTONE | REDACT | Account is deleted and only a stable internal user_id is needed to preserve references to retained records |

Distinct treatments: ANONYMIZE, DELETE, REDACT, RETAIN
Distinct categories: 15 (listed above)

Tombstone rule (rule_15): ACCOUNT_TOMBSTONE -> REDACT. Keep stable user_id; remove name, email, phone, email hash and other direct identifiers.

### deletion_requests.csv
Columns: case_id, email, requested_at, reported_status, reported_at, audit_at, request_text (518 rows)
Timestamps are ISO-8601 UTC with Z. Emails appear lowercase. request_text varies (English, Spanish, French samples seen). reported_status in {COMPLETE, PARTIALLY_COMPLETE, NOT_STARTED}.

### sample_deletion_requests.csv / sample_output.csv
Same request columns (32 rows). sample_output columns: case_id, deletion_status, steps_json.
Sample statuses observed: COMPLETE, INCOMPLETE.
Sample steps_json key order (example): step_no, phase, system_id, resource_id, operation, state, evidence_id.
evidence_id is a real file_id/activity_id/audit_id for FINDING and COMPLETE-verification steps; "" for REMEDIATION and future VERIFICATION steps.

### user_identities.csv
Columns: user_id, name, email, phone, email_hash, updated_at (850 rows)
One row per user_id in current snapshot. email may be current or historical for matching.

### user_audit_log.csv
Columns: audit_id, user_id, event_time, field_name, old_value, new_value (306 rows)
Records historical field changes. An email change creates an old email that may no longer be in user_identities.csv — that old email must still be searched.

### system_activity.csv
Columns: activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details (4011 rows)
event_types: ANONYMIZE_RECORD, BLOCK_RESTORE, CHECK_DATA_FLOW, CHECK_RESTORE_ACCESS, CLASSIFY_REQUEST, CREATE_EXPORT, DELETE_RECORD, DISABLE_DATA_FLOW, INDEX_RECORD, LINK_RESOURCE_IDENTITY, REDACT_RECORD, REFRESH_CACHE, RESTORE_BACKUP, RETAIN_RECORD, SEND_EMAIL, SYNC_RECORD, UPDATE_RECORD
source_systems: account_service, backup_service, data_catalog, deletion_worker, export_service, integration_service, notification_service, privacy_intake, profile_service, security_service, support_platform
target_systems: account_failover_replica, account_replication_cluster, account_service, analytics_platform, archive_service, backup_service, cache_service, email_delivery_service, export_service, identity_service, integration_service, legal_service, marketing_platform, object_storage, object_store, privacy_case_management, search_service, security_service, support_platform
reported_results: FAILED, PARTIAL, SUCCESS (claims only — not proof)

### evidence_files.csv
Columns: file_id, file_path, origin, captured_at (94 rows)
Paths verified to exist under dataset/evidence/. Subfolders: databases, documents, images, logs, records.
Types: .sql (many DB snapshots: primary, read replica, regional replica, reporting replica, failover replica, inventory), .pdf (documents), .png (images), .log/.txt (logs), .json (records).

### How each evidence type is read (Part B8)
- .sql: read as text, load into in-memory SQLite via executescript, list tables via sqlite_master, search every table/text column for user identifiers. Each DB copy (primary/replica/reporting/failover/inventory) treated as its own copy with its own capture time.
- .log/.txt: print first 30 lines, grep for identifiers; extract lines containing identifiers with timestamps.
- .json: json.load, print keys and one item, extract fields holding identifiers and record ids.
- .pdf: text extraction; extract identifiers shown in text.
- images: visual inspection; if text cannot be read, mark UNREADABLE and escalate.

## Open questions
- How is data_category assigned to a fact extracted from arbitrary evidence (table name / file origin hints)? Needs mapping logic from system_id/table name to category.
- How to determine "still attributable to a user" for ANALYTICS_PROFILE/PRODUCT_TELEMETRY (ANONYMIZE condition)?
- How to determine "within retention period" for SECURITY_AUDIT_LOG and "legal hold active" for LEGAL_HOLD_RECORD without organizer truth?
- Image text extraction requires an LLM or human; caching strategy needed.
- Confirm system_id/resource_id naming convention used in sample steps matches table-name + primary-key pattern.

## Done steps (Part B)
- B0 starter code read (code/main.py and code/evaluation/main.py are empty placeholders; output.csv is blank header template)
- B1 deletion_rules.csv read (15 rules, table above)
- B2 deletion_requests.csv peeked (518 rows, columns confirmed)
- B3 sample files peeked (32 cases)
- B4 user_identities.csv peeked (850 rows)
- B5 user_audit_log.csv peeked (306 rows)
- B6 system_activity.csv peeked (4011 rows, distinct event types/systems captured)
- B7 evidence_files.csv peeked (94 files, all paths exist)
- B8 evidence types catalogued
