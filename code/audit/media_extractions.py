"""Facts extracted from PDF and screenshot evidence (multimodal step).

Structured facts extracted from PDF and PNG evidence. PDFs were read with pdftotext; screenshots were transcribed with a vision-capable LLM (Claude, via Claude Code) during development and cached here so runs are deterministic and cost nothing. Only facts visible in each artifact are recorded: the focal resource, its state, and the identifiers shown with it. Each file id is the participant-visible file_id from dataset/evidence_files.csv. Cases are never named here; linking to a case happens in code through the identifiers.

How the cache was produced (development time, not at run time):
* PDFs (evidence/documents/*.pdf): text extracted with ``pdftotext -layout``.
* Screenshots (evidence/images/*.png): read by a vision-capable LLM (Claude,
  inside Claude Code) and transcribed into the structure below.

Schema per file id: ``file`` (path under dataset/), ``summary`` (what the
artifact shows), optional ``aliases`` (business reference -> resource id, as
catalogued by the data catalog), and ``observations``: the focal resource(s)
with ``present``/``exposed``/``linkable``/``active`` flags and the identifiers
visible next to them.  Linking these facts to requests happens in code.
"""

MEDIA_EXTRACTIONS = {'evidence_04': {'file': 'evidence/images/account_admin_console_20260926.png',
                 'summary': 'Customer Operations console: live customer page for Haruka Sato '
                            '(user_11, account_5762), email haruka.s1838@zoho.com, phone +81 90 '
                            '7610 2507, orders and support history CS-8538 / support_9538.',
                 'observations': [{'resource_id': 'account_5762',
                                   'system_id': 'account_service',
                                   'category': 'USER_PROFILE',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['user_11',
                                                   'haruka.s1838@zoho.com',
                                                   '+81 90 7610 2507']}]},
 'evidence_09': {'file': 'evidence/images/search_index_inspector_20260901.png',
                 'summary': 'Search Console query email:g.silva76@gmail.com on '
                            'customer_directory_v3: 2 hits. search_428 (Gabriel Silva, '
                            'g.silva76@gmail.com, user_13, indexed 2026-09-01T05:58:21Z) and '
                            'search_1874 (g.silva76.jr@gmail.com, no name/reference).',
                 'observations': [{'resource_id': 'search_428',
                                   'system_id': 'search_service',
                                   'category': 'SEARCH_INDEX_ENTRY',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'observed_at': '2026-09-01T06:00:14Z',
                                   'identifiers': ['user_13', 'g.silva76@gmail.com']},
                                  {'resource_id': 'search_1874',
                                   'system_id': 'search_service',
                                   'category': 'SEARCH_INDEX_ENTRY',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'observed_at': '2026-09-01T06:00:14Z',
                                   'identifiers': ['g.silva76.jr@gmail.com']}]},
 'evidence_14': {'file': 'evidence/images/connector_management_console_20260807.png',
                 'summary': 'BridgeOps connections at 2026-08-07 08:00 UTC: data_flow_1121 -> '
                            'customer_analytics_warehouse, selector jain.aditi@gmail.com, '
                            'continuous, healthy, delivering events; data_flow_9846 -> '
                            'customer_analytics_warehouse, selector lucia-torres@gmail.com, '
                            'continuous.',
                 'observations': [{'resource_id': 'data_flow_1121',
                                   'system_id': 'integration_service',
                                   'category': 'DATA_FLOW',
                                   'present': True,
                                   'active': True,
                                   'identifiers': ['jain.aditi@gmail.com']},
                                  {'resource_id': 'data_flow_9846',
                                   'system_id': 'integration_service',
                                   'category': 'DATA_FLOW',
                                   'present': True,
                                   'active': True,
                                   'identifiers': ['lucia-torres@gmail.com']}]},
 'evidence_18': {'file': 'evidence/documents/account_history_report_20260718.pdf',
                 'summary': 'Customer statement NST-2026-0718-1842 for Ingrid Dahl, user_18, '
                            'ingrid.dahl@outlook.com, order ORD-20261260, delivery address in '
                            'Trondheim. The statement number is the export alias catalogued for '
                            'export_1842.',
                 'aliases': {'NST-2026-0718-1842': 'export_1842'},
                 'observations': [{'resource_id': 'export_1842',
                                   'system_id': 'export_service',
                                   'category': 'USER_EXPORT',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['user_18', 'ingrid.dahl@outlook.com']}]},
 'evidence_19': {'file': 'evidence/images/analytics_profile_view_20260713.png',
                 'summary': 'Pulse Analytics user page: Omar Darwish, user_20, analytics_7438, '
                            'darwish.omar@icloud.com, 90-day metrics and event timeline (last '
                            'activity 13 Jul 2026).',
                 'observations': [{'resource_id': 'analytics_7438',
                                   'system_id': 'analytics_platform',
                                   'category': 'ANALYTICS_PROFILE',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['user_20', 'darwish.omar@icloud.com']}]},
 'evidence_23': {'file': 'evidence/images/customer_export_console_20260618.png',
                 'summary': 'Customer Download Center: export_1260 (customer_export_1260.zip) '
                            'owner ingrid.dahl@outlook.com, status Ready, created 18 Jun 06:42 '
                            'UTC, expires 25 Jun; other rows belong to staff accounts.',
                 'observations': [{'resource_id': 'export_1260',
                                   'system_id': 'export_service',
                                   'category': 'USER_EXPORT',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['ingrid.dahl@outlook.com']}]},
 'evidence_27': {'file': 'evidence/documents/legal_retention_register_20260529.pdf',
                 'summary': 'Disputed orders and tax records register (May 2026): retained order '
                            'rows for user_08, user_12, user_17, user_21, user_24, user_29, each '
                            'retained until 2033. No system resource ids are shown.',
                 'observations': []},
 'evidence_28': {'file': 'evidence/images/support_ticket_console_20260524.png',
                 'summary': "Helpline Console ticket CS-5034 (support_1034) 'Where is my "
                            "delivery?': customer Kofi Agyeman, kagyeman8947@fastmail.com, "
                            'conversation with agent Maya Chen about order ORD-20265034.',
                 'observations': [{'resource_id': 'support_1034',
                                   'system_id': 'support_platform',
                                   'category': 'SUPPORT_MESSAGE',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['kagyeman8947@fastmail.com']}]},
 'evidence_32': {'file': 'evidence/images/backup_restore_console_20260429.png',
                 'summary': 'Vault Recovery Manager archives: backup_9287 for account '
                            'areed1433@gmail.com, weekly snapshot 26 Apr 2026, checksum verified, '
                            'restorable (no restore block shown), retention end 26 Jul 2026.',
                 'observations': [{'resource_id': 'backup_9287',
                                   'system_id': 'backup_service',
                                   'category': 'BACKUP_ARCHIVE',
                                   'present': True,
                                   'active': True,
                                   'identifiers': ['areed1433@gmail.com']}]},
 'evidence_37': {'file': 'evidence/images/security_audit_explorer_20260905.png',
                 'summary': 'Sentinel account events for subject user_03 (18-26 Aug 2026): six '
                            "signed events, selected audit_record_003 'Account closure recorded', "
                            'integrity valid.',
                 'observations': [{'resource_id': 'audit_record_003',
                                   'system_id': 'security_service',
                                   'category': 'SECURITY_AUDIT_LOG',
                                   'present': True,
                                   'identifiers': ['user_03']}]},
 'evidence_42': {'file': 'evidence/images/deleted_account_reference_20260310.png',
                 'summary': 'Customer Reference Registry: retained customer key user_17 with '
                            'linked orders/support/finance records; no name, email, phone or hash '
                            'displayed.',
                 'observations': [{'resource_id': 'tombstone_17',
                                   'system_id': 'identity_service',
                                   'category': 'ACCOUNT_TOMBSTONE',
                                   'present': True,
                                   'exposed': False,
                                   'linkable': True,
                                   'identifiers': ['user_17']}]},
 'evidence_46': {'file': 'evidence/images/object_storage_browser_20260213.png',
                 'summary': 'Nimbus Object Storage bucket '
                            'northstar-customer-data/support-attachments/2026/02: '
                            'delivery_confirmation_19.pdf (684 KB, v3, uploader support-service, '
                            'modified 12 Feb 2026 18:42 UTC) is stored. The catalogue alias '
                            'delivery_confirmation_19.pdf maps to object_19.',
                 'aliases': {'delivery_confirmation_19.pdf': 'object_19'},
                 'observations': [{'resource_id': 'object_19',
                                   'system_id': 'object_storage',
                                   'category': 'SUPPORT_ATTACHMENT',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': []}]},
 'evidence_55': {'file': 'evidence/documents/security_retention_extract.pdf',
                 'summary': 'Compliance journal extract CJX-20260905-0630: event audit_record_003, '
                            'subject user_03, account closure recorded 25 Aug 2026, retain until '
                            '25 Aug 2027, integrity seal valid.',
                 'observations': [{'resource_id': 'audit_record_003',
                                   'system_id': 'security_service',
                                   'category': 'SECURITY_AUDIT_LOG',
                                   'present': True,
                                   'identifiers': ['user_03']}]},
 'evidence_58': {'file': 'evidence/documents/delivery_correction_attachment.pdf',
                 'summary': 'Delivery address correction request uploaded by the customer: support '
                            'reference CS-4827 / support_001, Priya Raman, priya.raman@gmail.com, '
                            '+91 98765 73142, order ORD-20264827.',
                 'observations': [{'resource_id': 'support_001',
                                   'system_id': 'support_platform',
                                   'category': 'SUPPORT_ATTACHMENT',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['priya.raman@gmail.com', '+91 98765 73142']}]},
 'evidence_60': {'file': 'evidence/images/marketing_profile_console.png',
                 'summary': 'Audience Operations profile: Soo-jin Park, marketing_001, '
                            'sj.park@naver.com, +82 10-5837-9451, live, last refreshed 15 Sep 2026 '
                            '23:40 UTC.',
                 'observations': [{'resource_id': 'marketing_001',
                                   'system_id': 'marketing_platform',
                                   'category': 'MARKETING_PROFILE',
                                   'present': True,
                                   'exposed': True,
                                   'linkable': True,
                                   'identifiers': ['sj.park@naver.com', '+82 10-5837-9451']}]}}
