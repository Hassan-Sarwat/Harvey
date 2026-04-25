from __future__ import annotations

import csv
import textwrap
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


PLAYBOOK_COLUMNS = [
    "id",
    "title",
    "severity",
    "default",
    "why_it_matters",
    "preferred_position",
    "fallback_1",
    "fallback_2",
    "red_line",
    "escalation_trigger",
    "legal_basis",
    "sample_clause",
    "approved_fix",
    "owner",
    "last_reviewed",
]

EVIDENCE_COLUMNS = [
    "source",
    "citation",
    "quote",
    "url",
    "domain",
    "relevance",
    "source_type",
    "fallback_note",
]

DPA_SOURCE_PLAYBOOK_COLUMNS = PLAYBOOK_COLUMNS + [
    "source_playbook_clause",
    "source_playbook_file",
]

DPA_SOURCE_RULES = [
    {
        "id": "DPA-001",
        "title": "Processing instructions and own-purpose use",
        "severity": "blocker",
        "default": "Processor may process Company Personal Data only on BMW Group's documented instructions.",
        "why_it_matters": "The controller must remain in control of purposes and means. Processor own-purpose language can undermine the controller-processor structure.",
        "preferred_position": "Processor shall process Company Personal Data only on BMW Group's documented instructions.",
        "fallback_1": "Permit strictly aggregated service statistics only if BMW Group approves the purpose in the order form.",
        "fallback_2": "Permit security telemetry only where minimized, non-personal, and necessary to provide the service.",
        "red_line": "Reject product improvement, analytics, benchmarking, marketing, AI training, or other own-purpose processing unless specifically authorized.",
        "escalation_trigger": "Processor insists on using Company Personal Data for its own analytics, product improvement, marketing, benchmarking, or model training.",
        "legal_basis": "GDPR Art. 28(3)(a); GDPR Art. 5(1)(b).",
        "sample_clause": "Processor may aggregate and process such data for its own product improvement and analytics purposes.",
        "approved_fix": "Processor shall not process Company Personal Data for its own purposes, including analytics, product improvement, benchmarking, marketing, or model training, without BMW Group's prior written approval.",
        "owner": "BMW Group Privacy Legal",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 1: Processing Instructions",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-002",
        "title": "Subprocessor approval and objection rights",
        "severity": "high",
        "default": "Processor may not appoint subprocessors without BMW Group consent or authorization and change notice with an objection opportunity.",
        "why_it_matters": "BMW Group must know and approve who can access its data throughout the processor supply chain.",
        "preferred_position": "Prior written consent for each subprocessor, with named subprocessor schedule and processing location.",
        "fallback_1": "General written authorization only if BMW Group receives advance notice of intended changes and can object.",
        "fallback_2": "Pre-approved support vendor pool for low-risk services, with notice before activation.",
        "red_line": "General authorization with no notice, no list, or no objection right.",
        "escalation_trigger": "Processor refuses to disclose subprocessors or asks for unrestricted additions without informing BMW Group.",
        "legal_basis": "GDPR Art. 28(2) and Art. 28(4).",
        "sample_clause": "Processor may appoint any Subprocessor on general authorization without giving Company prior notice.",
        "approved_fix": "Processor may use only authorized subprocessors and must notify BMW Group of intended changes in time for BMW Group to object.",
        "owner": "BMW Group Privacy Legal / Vendor Risk",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 2: Subprocessing",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-003",
        "title": "Data subject rights assistance",
        "severity": "high",
        "default": "Processor must promptly notify BMW Group of requests and assist BMW Group without responding directly unless instructed or legally required.",
        "why_it_matters": "BMW Group remains responsible for responding to individuals exercising access, deletion, objection, and other GDPR rights.",
        "preferred_position": "Processor notifies BMW Group immediately and provides technical and organizational assistance for data subject rights.",
        "fallback_1": "Processor may redirect a requester to BMW Group if it also preserves request evidence and notifies BMW Group promptly.",
        "fallback_2": "Reasonable documented cost recovery only for exceptional, high-volume requests approved by BMW Group.",
        "red_line": "Processor refuses assistance, charges excessive fees, responds directly without instruction, or purports to waive data subject rights.",
        "escalation_trigger": "Processor refuses to assist with complex requests or requires uncapped fees for request support.",
        "legal_basis": "GDPR Art. 12-22; GDPR Art. 28(3)(e).",
        "sample_clause": "Processor may charge its standard professional services rates for all data subject request support.",
        "approved_fix": "Processor shall promptly notify BMW Group and provide reasonable assistance with data subject requests without separate charge unless BMW Group approves an exceptional fee.",
        "owner": "BMW Group Privacy Legal",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 3: Data Subject Rights",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-004",
        "title": "Personal data breach notification",
        "severity": "high",
        "default": "Processor must notify BMW Group without undue delay upon becoming aware of a personal data breach.",
        "why_it_matters": "BMW Group may need to meet regulatory and data subject notification timelines and needs facts early.",
        "preferred_position": "Notice without undue delay after awareness, with enough information for BMW Group to assess reporting duties and coordinate mitigation.",
        "fallback_1": "A short outer deadline may be accepted for non-critical updates, but the initial awareness notice must remain without undue delay.",
        "fallback_2": "Rolling updates may be used where facts are still developing.",
        "red_line": "Notice only after confirmation, after full investigation, or as soon as reasonably practicable with no urgency standard.",
        "escalation_trigger": "Processor refuses to notify without undue delay or limits cooperation in breach investigation.",
        "legal_basis": "GDPR Art. 33; GDPR Art. 34; GDPR Art. 28(3)(f).",
        "sample_clause": "Processor will notify Company as soon as reasonably practicable after confirming that an incident is reportable.",
        "approved_fix": "Processor shall notify BMW Group without undue delay after becoming aware of an actual or suspected Personal Data Breach and provide rolling updates.",
        "owner": "BMW Group Privacy Legal / Incident Response",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 4: Personal Data Breach Notification",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-005",
        "title": "Security measures",
        "severity": "high",
        "default": "Processor must implement appropriate technical and organizational measures under GDPR Art. 32.",
        "why_it_matters": "Generic best-effort security language does not let BMW Group evaluate or evidence processor security.",
        "preferred_position": "Attach TOMs covering access control, encryption, logging, vulnerability management, availability, confidentiality, and personnel controls.",
        "fallback_1": "Accept current independent assurance evidence plus a BMW-specific TOM annex.",
        "fallback_2": "Accept a short-form TOM schedule only for low-risk data and short pilots.",
        "red_line": "Best-efforts language with no concrete standards, no need-to-know access limit, or no confidentiality obligation.",
        "escalation_trigger": "Processor refuses to commit to GDPR Art. 32 TOMs or restrict access to need-to-know personnel.",
        "legal_basis": "GDPR Art. 32; GDPR Art. 28(3)(c).",
        "sample_clause": "Processor shall use commercially reasonable security measures as it deems appropriate.",
        "approved_fix": "Processor shall maintain the TOMs in Annex 2 and ensure access is limited to need-to-know personnel bound by confidentiality obligations.",
        "owner": "BMW Group Privacy Legal / Cybersecurity",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 5: Security Measures",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-006",
        "title": "Deletion or return of data",
        "severity": "medium",
        "default": "Processor must delete or return Company Personal Data within 10 business days after cessation of services and certify deletion.",
        "why_it_matters": "Data should not be retained longer than necessary after services end, while routine backups need practical handling.",
        "preferred_position": "Delete or return all Company Personal Data within 10 business days and provide written certification.",
        "fallback_1": "Permit backup deletion on the next scheduled purge cycle if backups remain protected and inaccessible for ordinary use.",
        "fallback_2": "Permit legally required archives only if segregated and still subject to confidentiality and security obligations.",
        "red_line": "Long retention after termination, retention for analytics, or immediate destruction of routine backups with no technical feasibility carve-out.",
        "escalation_trigger": "Processor requests retention beyond operational need or insists on immediate backup destruction certification.",
        "legal_basis": "GDPR Art. 5(1)(e); GDPR Art. 28(3)(g).",
        "sample_clause": "Processor may retain Company Personal Data for 180 days and backups for 18 months after termination.",
        "approved_fix": "Processor shall delete or return Company Personal Data within 10 business days, certify deletion, and keep any retained backups protected until normal purge.",
        "owner": "BMW Group Privacy Legal",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 6: Deletion or Return of Data",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-007",
        "title": "International data transfers",
        "severity": "blocker",
        "default": "No transfers outside the EU/EEA without prior BMW Group written consent and valid transfer safeguards.",
        "why_it_matters": "Transfers outside the EEA require specific legal safeguards and BMW Group visibility.",
        "preferred_position": "No non-EEA transfers without prior written consent and an approved transfer schedule.",
        "fallback_1": "Allow transfers only under EU-approved SCCs, transfer assessment, and supplementary measures.",
        "fallback_2": "Allow emergency remote access only with time limits, logging, encryption, and legal approval.",
        "red_line": "Third-country transfers without BMW Group knowledge, SCC refusal, or safeguards to be agreed later.",
        "escalation_trigger": "Processor refuses to sign EU SCCs for non-EEA transfers or asks for unrestricted third-country access.",
        "legal_basis": "GDPR Art. 44-46.",
        "sample_clause": "Processor may transfer Company Personal Data to the United States and India for support, with SCCs to be agreed later.",
        "approved_fix": "Processor shall not transfer Company Personal Data outside the EU/EEA unless BMW Group gives prior written consent and approved safeguards are in place.",
        "owner": "BMW Group Privacy Legal / DPO",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 7: International Data Transfers",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
    {
        "id": "DPA-008",
        "title": "Audit rights",
        "severity": "medium",
        "default": "Processor must make compliance information available and allow BMW Group or its mandated auditor to inspect/audit processor compliance.",
        "why_it_matters": "BMW Group needs evidence that the processor is actually following the DPA and GDPR Art. 28 obligations.",
        "preferred_position": "Information access plus audit/inspection rights by BMW Group or a mandated auditor.",
        "fallback_1": "Independent assurance reports and remote evidence review for low-risk processing.",
        "fallback_2": "Limit audit frequency only if incident-triggered and regulator-triggered audits remain available.",
        "red_line": "Audits limited to once every several years, excessive audit fees, or no inspection right.",
        "escalation_trigger": "Processor charges excessive audit fees or refuses meaningful audit rights.",
        "legal_basis": "GDPR Art. 28(3)(h).",
        "sample_clause": "Company may audit once every three years, only remotely, and only after paying Processor's audit support fees.",
        "approved_fix": "Processor shall make available all information necessary to demonstrate compliance and allow audits by BMW Group or its mandated auditor.",
        "owner": "BMW Group Privacy Legal / Vendor Risk",
        "last_reviewed": "2026-04-25",
        "source_playbook_clause": "Clause 8: Audit Rights",
        "source_playbook_file": "BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
    },
]


DATA_PROTECTION_RULES = [
    {
        "id": "DP-001",
        "title": "BMW contracting entity required",
        "severity": "high",
        "default": "The applicable BMW contracting entity and address must be named.",
        "why_it_matters": "The legal entity determines controller identity, signature authority, notification routing, and audit ownership.",
        "preferred_position": "Name the BMW entity, registered address, role as controller, and operational contact for privacy notices.",
        "fallback_1": "Permit a schedule to identify the BMW entity before signature if procurement routing is still open.",
        "fallback_2": "Use BMW AG as placeholder only with legal approval and a required pre-signature update.",
        "red_line": "No BMW entity, wrong BMW entity, or supplier-only party description.",
        "escalation_trigger": "Escalate if the supplier refuses to identify the BMW controller or insists on an affiliate catch-all.",
        "legal_basis": "GDPR Art. 28; accountability under GDPR Art. 5(2) and Art. 24.",
        "sample_clause": "Customer means any BMW group company using the services.",
        "approved_fix": "Controller means BMW AG, Petuelring 130, 80788 Muenchen, Germany, or the BMW group company identified in Order Form 1.",
        "owner": "BMW Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-002",
        "title": "Subprocessor list required",
        "severity": "medium",
        "default": "Processor must list subprocessors or state that none are used.",
        "why_it_matters": "BMW needs an auditable chain of processors and a practical objection right before data is moved to a new supplier.",
        "preferred_position": "Attach a named subprocessor table with role, location, data categories, and 30-day prior notice for changes.",
        "fallback_1": "Accept a live URL only if a dated export is attached at signature and BMW receives 30-day notice.",
        "fallback_2": "Accept general authorization for low-risk support subprocessors with a 30-day objection right.",
        "red_line": "Undisclosed subprocessors, blanket approval, or notice after onboarding.",
        "escalation_trigger": "Escalate if the subprocessor list is missing for personal data processing or objection rights are removed.",
        "legal_basis": "GDPR Art. 28(2) and 28(4).",
        "sample_clause": "Processor may appoint subprocessors at its discretion and will update its website from time to time.",
        "approved_fix": "Processor may use only the subprocessors listed in Annex 3 and must give BMW at least 30 days' prior written notice of changes.",
        "owner": "BMW Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-003",
        "title": "Data subject rights cannot be waived",
        "severity": "blocker",
        "default": "No clause may waive statutory data subject rights.",
        "why_it_matters": "A waiver clause conflicts with the GDPR rights model and creates immediate legal and reputational risk.",
        "preferred_position": "Preserve all statutory rights and require processor assistance within five business days.",
        "fallback_1": "Permit processor to redirect requests to BMW if it also preserves evidence and notifies BMW within two business days.",
        "fallback_2": "Permit operational request-routing language only if it does not limit statutory rights.",
        "red_line": "Any waiver, release, opt-out, or contractual limitation of GDPR data subject rights.",
        "escalation_trigger": "Escalate immediately if the contract says data subjects waive all data subject rights or similar wording.",
        "legal_basis": "GDPR Art. 12-22 and Art. 28(3)(e).",
        "sample_clause": "Data subjects waive all data subject rights against Processor and BMW for service data.",
        "approved_fix": "Nothing in this Agreement limits rights available to data subjects under applicable data protection law.",
        "owner": "BMW Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-004",
        "title": "Processor instructions and purpose limitation",
        "severity": "high",
        "default": "Processor may process BMW personal data only on documented BMW instructions and for the signed purpose.",
        "why_it_matters": "Purpose drift turns a processor into an uncontrolled decision-maker and can invalidate the processing structure.",
        "preferred_position": "Processing only for documented BMW instructions, with immediate notice if an instruction appears unlawful.",
        "fallback_1": "Allow narrowly defined service analytics if aggregated and approved in the order form.",
        "fallback_2": "Allow security telemetry only if it cannot identify BMW personnel, drivers, or vehicle users.",
        "red_line": "Supplier may reuse BMW personal data for product development, benchmarking, AI training, or unrelated analytics.",
        "escalation_trigger": "Escalate if supplier claims independent rights to use personal data outside BMW instructions.",
        "legal_basis": "GDPR Art. 5(1)(b), Art. 28(3)(a), and controller-processor guidance.",
        "sample_clause": "Processor may use pseudonymized BMW data to improve its AI models and benchmark automotive customers.",
        "approved_fix": "Processor will not use BMW personal data for model training, benchmarking, or product development unless BMW gives prior written approval.",
        "owner": "BMW Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-005",
        "title": "Security measures and TOM annex",
        "severity": "high",
        "default": "A technical and organisational measures annex must cover encryption, access control, logging, vulnerability handling, and incident response.",
        "why_it_matters": "BMW cannot assess risk or prove accountability if the contract only promises generic reasonable security.",
        "preferred_position": "Attach a TOM annex with encryption in transit and at rest, MFA, least privilege, audit logs, backup controls, and vulnerability SLAs.",
        "fallback_1": "Accept SOC 2 Type II, ISO 27001, or TISAX evidence plus a short contract annex for BMW-specific controls.",
        "fallback_2": "Accept a security questionnaire only for low-risk processing and only until the TOM annex is complete.",
        "red_line": "No TOM annex, no audit evidence, no encryption commitment, or supplier can lower controls unilaterally.",
        "escalation_trigger": "Escalate if special category data, vehicle location data, or employee data is processed without a TOM annex.",
        "legal_basis": "GDPR Art. 32 and Art. 28(3)(c).",
        "sample_clause": "Supplier shall use commercially reasonable security measures as it deems appropriate.",
        "approved_fix": "Processor shall maintain the TOMs in Annex 2 and may not materially reduce them without BMW's prior written approval.",
        "owner": "BMW Privacy Legal / Cybersecurity",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-006",
        "title": "Personal data breach notification",
        "severity": "high",
        "default": "Processor must notify BMW without undue delay and no later than 24 hours after becoming aware of a personal data breach.",
        "why_it_matters": "BMW may have a 72-hour supervisory authority deadline and needs facts, affected data, mitigation, and logs quickly.",
        "preferred_position": "24-hour initial notice, rolling updates every 12 hours during active containment, and a final report within five business days.",
        "fallback_1": "36-hour notice only if supplier operates a staffed incident desk and provides immediate phone escalation for severe events.",
        "fallback_2": "48-hour notice for low-risk support data with no vehicle, employee, payment, or credential data.",
        "red_line": "Notice only after confirmation, more than 48 hours, or supplier discretion over whether BMW is notified.",
        "escalation_trigger": "Escalate if the draft gives 72 hours or more, or starts the clock after full investigation rather than awareness.",
        "legal_basis": "GDPR Art. 33, Art. 34, and Art. 28(3)(f).",
        "sample_clause": "Processor will notify BMW within 72 hours after it confirms that a security incident is a reportable breach.",
        "approved_fix": "Processor shall notify BMW within 24 hours after becoming aware of any actual or suspected personal data breach.",
        "owner": "BMW Privacy Legal / Incident Response",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-007",
        "title": "Third-country transfers and remote access",
        "severity": "blocker",
        "default": "BMW personal data must remain in the EU/EEA unless an adequacy decision, BMW-approved SCCs, transfer impact assessment, and supplementary measures apply.",
        "why_it_matters": "Remote access from outside the EU/EEA can be a restricted transfer and must be controlled before signature.",
        "preferred_position": "EU/EEA hosting and support, with named exceptions approved by BMW Privacy Legal and the DPO.",
        "fallback_1": "Permit approved third-country support under SCCs, transfer impact assessment, encryption, and named personnel.",
        "fallback_2": "Permit emergency break-glass support with access logs, time limits, and post-event reporting.",
        "red_line": "Unrestricted US, India, or global access; SCCs to be agreed later; or onward transfers without BMW approval.",
        "escalation_trigger": "Escalate if the draft references third-country processing without completed safeguards.",
        "legal_basis": "GDPR Art. 44-46 and Schrems II transfer assessment principles.",
        "sample_clause": "Support teams in the United States and India may access BMW service data under safeguards to be agreed.",
        "approved_fix": "No third-country transfer or remote access is permitted unless listed in Annex 3 and approved by BMW in writing.",
        "owner": "BMW Privacy Legal / DPO",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-008",
        "title": "Audit rights and evidence access",
        "severity": "medium",
        "default": "BMW must receive audit evidence and retain audit rights proportionate to processing risk.",
        "why_it_matters": "Audit rights make processor commitments testable and support BMW accountability to regulators and customers.",
        "preferred_position": "Annual third-party assurance report plus BMW audit right on 30 days' notice, with emergency audits after incidents.",
        "fallback_1": "Remote audit and evidence package if data is low risk and the supplier provides current independent assurance.",
        "fallback_2": "Questionnaire-only audit for small vendors with no production personal data.",
        "red_line": "Supplier can refuse all audits or provide only self-certification for high-risk processing.",
        "escalation_trigger": "Escalate if audit rights are missing for vehicle, employee, credential, or production customer data.",
        "legal_basis": "GDPR Art. 28(3)(h).",
        "sample_clause": "BMW may request a security questionnaire once per year; no onsite or third-party audit is permitted.",
        "approved_fix": "Processor shall make available all information necessary to demonstrate compliance and allow audits by BMW or its auditor.",
        "owner": "BMW Privacy Legal / Vendor Risk",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-009",
        "title": "Return and deletion after termination",
        "severity": "medium",
        "default": "Processor must return or delete BMW personal data within 30 days after termination unless EU or Member State law requires retention.",
        "why_it_matters": "Long retention increases breach exposure and can conflict with storage limitation requirements.",
        "preferred_position": "Return or deletion within 30 days, backup purge within 90 days, and certificate of deletion.",
        "fallback_1": "45-day production deletion with 120-day backup purge for complex hosted services.",
        "fallback_2": "Longer retention only for named legal obligations and segregated read-only archives.",
        "red_line": "Retention for analytics, benchmarking, model training, or undefined business purposes after termination.",
        "escalation_trigger": "Escalate if deletion exceeds 90 days for active systems or 180 days for backups.",
        "legal_basis": "GDPR Art. 5(1)(e) and Art. 28(3)(g).",
        "sample_clause": "Processor may retain service data for 180 days and backups for 18 months for operational assurance.",
        "approved_fix": "Processor shall delete or return BMW personal data within 30 days and purge backups within 90 days unless law requires retention.",
        "owner": "BMW Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-010",
        "title": "Data subject request assistance",
        "severity": "medium",
        "default": "Processor must help BMW answer data subject requests within five business days.",
        "why_it_matters": "BMW remains accountable for statutory response deadlines even when data is held by a supplier.",
        "preferred_position": "Two-business-day notice to BMW and five-business-day assistance with search, export, correction, deletion, and restriction.",
        "fallback_1": "Seven-business-day assistance for low-volume back-office data.",
        "fallback_2": "Longer assistance only if the request requires archive restoration and supplier gives status updates.",
        "red_line": "Supplier may ignore requests, charge uncapped fees, or respond to data subjects without BMW instruction.",
        "escalation_trigger": "Escalate if supplier refuses operational assistance or tries to make BMW waive response obligations.",
        "legal_basis": "GDPR Art. 12-22 and Art. 28(3)(e).",
        "sample_clause": "Processor may charge its then-current professional services rates for any data subject request support.",
        "approved_fix": "Processor shall notify BMW within two business days and provide reasonable assistance within five business days at no extra charge.",
        "owner": "BMW Privacy Legal / Customer Operations",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-011",
        "title": "AI training and derived data",
        "severity": "high",
        "default": "BMW personal data, vehicle data, and derived identifiers may not be used for supplier AI training without explicit BMW approval.",
        "why_it_matters": "AI training can create persistence, re-identification, trade secret, and transparency problems beyond the service purpose.",
        "preferred_position": "No AI model training, benchmarking, or synthetic data generation from BMW data unless approved in a separate AI/data use addendum.",
        "fallback_1": "Allow aggregate service metrics only if irreversible, non-personal, and not customer-comparative.",
        "fallback_2": "Allow security anomaly models only on minimized logs and only for providing the service to BMW.",
        "red_line": "Any right to train general models or share derived insights with other automotive customers.",
        "escalation_trigger": "Escalate if supplier asks for AI training rights or a broad anonymized-data license.",
        "legal_basis": "GDPR Art. 5, Art. 6, Art. 25, Art. 28, and BMW AI governance policy.",
        "sample_clause": "Supplier may create anonymized or synthetic data sets from BMW data and use them to improve its platform.",
        "approved_fix": "Supplier shall not use BMW data or derived data for AI training except under a separately signed BMW AI addendum.",
        "owner": "BMW Privacy Legal / AI Governance",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "DP-012",
        "title": "Employee, driver, and vehicle data sensitivity",
        "severity": "high",
        "default": "Processing involving employees, drivers, precise location, diagnostics, or connected vehicle identifiers requires an explicit data category schedule and risk review.",
        "why_it_matters": "These categories raise heightened privacy, employment, works council, and reputational risk in Germany.",
        "preferred_position": "Attach a schedule covering data categories, legal basis, retention, works council dependency, and DPIA status.",
        "fallback_1": "Permit only pseudonymous vehicle telemetry until the complete schedule is approved.",
        "fallback_2": "Permit pilot data with synthetic or masked identifiers and no employee monitoring use.",
        "red_line": "Hidden employee monitoring, location tracking without necessity analysis, or missing DPIA decision.",
        "escalation_trigger": "Escalate if the draft includes employee, precise location, or driver behavior data without a schedule.",
        "legal_basis": "GDPR Art. 5, Art. 6, Art. 9 where relevant, BDSG Section 26, and GDPR Art. 35.",
        "sample_clause": "Processor may process driver behavior, location, HR contact, and warranty diagnostic data as reasonably needed.",
        "approved_fix": "The data categories in Annex 1 are exhaustive and may be expanded only by written BMW Privacy Legal approval.",
        "owner": "BMW Privacy Legal / Labor Relations",
        "last_reviewed": "2026-04-25",
    },
]


LITIGATION_RULES = [
    {
        "id": "LT-001",
        "title": "Governing law required",
        "severity": "medium",
        "default": "Governing law and venue must be explicit.",
        "why_it_matters": "Undefined law and forum increase procedural uncertainty, cost, and enforcement risk.",
        "preferred_position": "German law with Munich courts or DIS arbitration seated in Munich, with interim relief carve-out.",
        "fallback_1": "Neutral EU law and forum approved by BMW Legal for balanced cross-border matters.",
        "fallback_2": "Counterparty forum only for low-value, local, non-precedential disputes with legal sign-off.",
        "red_line": "No governing law, no forum, or exclusive supplier home courts for high-value BMW disputes.",
        "escalation_trigger": "Escalate if governing law is missing, non-EU, or conflicts with the litigation strategy.",
        "legal_basis": "ZPO Section 38; Rome I; commercial arbitration practice.",
        "sample_clause": "The Agreement is governed by the laws chosen by the claimant at the time of filing.",
        "approved_fix": "This Agreement is governed by German law. The courts of Munich have exclusive jurisdiction, subject to interim relief.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-002",
        "title": "Settlement authority",
        "severity": "high",
        "default": "Settlement authority must remain with authorized BMW legal representatives.",
        "why_it_matters": "Settlement decisions can create precedent, regulatory admissions, financial exposure, and publicity risk.",
        "preferred_position": "Only BMW Legal or a named authorized representative may approve settlement, admission, compromise, or consent order.",
        "fallback_1": "Business owner may approve purely commercial service credits below a named threshold with legal notice.",
        "fallback_2": "Outside counsel may negotiate but not bind BMW without written authority.",
        "red_line": "Supplier, business stakeholder, insurer, or outside counsel can settle or admit liability without BMW Legal approval.",
        "escalation_trigger": "Escalate if settlement authority is delegated outside BMW Legal or is silent in a dispute-support contract.",
        "legal_basis": "BMW litigation governance; authority and mandate principles under German civil law.",
        "sample_clause": "Service Provider may settle claims below EUR 100,000 where it reasonably believes settlement is efficient.",
        "approved_fix": "No settlement, admission, consent order, or compromise may be made without prior written approval from BMW Legal.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-003",
        "title": "Unlimited liability escalation",
        "severity": "blocker",
        "default": "Unlimited liability must be escalated to legal.",
        "why_it_matters": "Unlimited liability can exceed the value of the transaction and may interact with statutory non-excludable liability.",
        "preferred_position": "Use the approved cap matrix, with carve-outs only for intent, gross negligence where required, confidentiality, IP, and data protection as approved.",
        "fallback_1": "Higher cap for defined high-risk breaches if insurance, fault standard, and direct-damages limits are clear.",
        "fallback_2": "Separate super-cap for data protection or confidentiality breaches approved by BMW Legal.",
        "red_line": "BMW accepts unlimited liability, uncapped indemnity, punitive damages, or open-ended consequential damages.",
        "escalation_trigger": "Escalate any unlimited liability clause before business approval.",
        "legal_basis": "BGB Sections 276, 307, 309, and 310; BMW liability matrix.",
        "sample_clause": "BMW accepts unlimited liability for all losses, claims, penalties, and consequential damages.",
        "approved_fix": "Liability is capped at 100 percent of annual fees, except for mandatory statutory liability and agreed carve-outs approved by BMW Legal.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-004",
        "title": "Litigation hold and evidence preservation",
        "severity": "high",
        "default": "Supplier must preserve relevant records after BMW issues a legal hold and must suspend conflicting deletion routines.",
        "why_it_matters": "Deleted evidence can damage BMW's position, increase sanctions risk, and undermine expert testimony.",
        "preferred_position": "Immediate hold acknowledgement, preservation of custodians and systems, audit log retention, and named hold owner.",
        "fallback_1": "48-hour acknowledgement for low-risk suppliers with automated deletion paused within five business days.",
        "fallback_2": "Targeted preservation scope if BMW Legal approves search terms, custodians, and date ranges.",
        "red_line": "Supplier may delete, overwrite, rotate logs, or charge hold fees before preserving evidence.",
        "escalation_trigger": "Escalate if the supplier refuses to suspend deletion or limits preservation to paid work orders.",
        "legal_basis": "German civil procedure evidence strategy; ZPO disclosure and proof principles.",
        "sample_clause": "Supplier may continue ordinary deletion unless BMW pays for a premium evidence-preservation package.",
        "approved_fix": "Upon BMW's notice, Supplier shall immediately preserve relevant records and suspend deletion routines for held data.",
        "owner": "BMW Litigation / eDiscovery",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-005",
        "title": "Privilege and legal confidentiality",
        "severity": "high",
        "default": "Legal advice, investigation materials, and counsel communications must be protected and disclosed only on BMW Legal instruction.",
        "why_it_matters": "Poor privilege handling can waive protections or reveal litigation strategy.",
        "preferred_position": "Segregate privileged materials, label counsel work product, and route third-party requests to BMW Legal immediately.",
        "fallback_1": "Use a privilege protocol in the statement of work if the supplier handles mixed technical and legal materials.",
        "fallback_2": "Permit disclosure only after legally required production and only after BMW has a chance to seek protection.",
        "red_line": "Supplier may disclose privileged documents, investigation notes, or legal strategy without prior notice.",
        "escalation_trigger": "Escalate if subpoena, regulator, or adverse-party language lacks prompt BMW Legal notice.",
        "legal_basis": "German professional secrecy and litigation confidentiality practice; ZPO protective strategy.",
        "sample_clause": "Supplier may disclose BMW materials to regulators or courts where it considers disclosure advisable.",
        "approved_fix": "Supplier shall notify BMW Legal immediately and disclose only the minimum required after BMW has had an opportunity to object.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-006",
        "title": "Interim relief and injunctive remedies",
        "severity": "medium",
        "default": "BMW must retain the ability to seek urgent interim or injunctive relief in a competent court.",
        "why_it_matters": "Confidentiality, IP, data misuse, and evidence preservation disputes may need rapid court intervention.",
        "preferred_position": "Arbitration or court clause includes explicit carve-out for interim relief and preservation orders.",
        "fallback_1": "Emergency arbitrator relief plus court fallback where arbitral relief is unavailable.",
        "fallback_2": "Mutual injunctive relief limited to confidentiality, IP, data protection, and evidence preservation.",
        "red_line": "Cooling-off, mediation, or escalation steps block urgent relief.",
        "escalation_trigger": "Escalate if the dispute clause requires executive negotiation before urgent court action.",
        "legal_basis": "ZPO interim relief practice; arbitration interim measure practice.",
        "sample_clause": "No party may apply to court until executive negotiation and mediation have concluded.",
        "approved_fix": "Nothing prevents either party from seeking interim or injunctive relief from a competent court at any time.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-007",
        "title": "Forum, arbitration, and language",
        "severity": "medium",
        "default": "Dispute forum, seat, language, service rules, and confidentiality of proceedings must be specified.",
        "why_it_matters": "Procedural ambiguity can create expensive satellite disputes before the merits are reached.",
        "preferred_position": "DIS or ICC arbitration seated in Munich, German law, English language if cross-border, and confidentiality of proceedings.",
        "fallback_1": "Munich courts with English-language evidence protocol for technical exhibits.",
        "fallback_2": "Neutral EU seat and English language if legal confirms enforceability and business need.",
        "red_line": "Ad hoc arbitration with no seat, no appointing authority, or counterparty-only local court jurisdiction.",
        "escalation_trigger": "Escalate any forum clause that could force BMW into non-EU courts or unclear arbitration.",
        "legal_basis": "ZPO Section 1031 and New York Convention enforcement considerations.",
        "sample_clause": "Any dispute shall be settled by arbitration under rules agreed after a dispute arises.",
        "approved_fix": "Disputes shall be finally resolved under DIS Rules by one arbitrator seated in Munich; proceedings are in English.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-008",
        "title": "Limitation periods and claims preservation",
        "severity": "medium",
        "default": "The contract must not shorten limitation periods for intentional misconduct, data protection claims, or claims under active legal hold.",
        "why_it_matters": "Short contractual limitation periods can cut off claims before technical defects or data incidents are understood.",
        "preferred_position": "Statutory limitation periods apply unless BMW Legal approves a specific commercial limitation.",
        "fallback_1": "One-year limitation only for ordinary fee claims, excluding confidentiality, data, IP, and intentional misconduct.",
        "fallback_2": "Toll limitation periods during remediation, audit, settlement discussions, or legal hold.",
        "red_line": "Six-month limitation for all claims, or shortened limitation for intent or gross negligence.",
        "escalation_trigger": "Escalate if the draft shortens limitation periods for data breach, intentional misconduct, or pending disputes.",
        "legal_basis": "BGB Section 202; BGB Section 203; BGB Section 276.",
        "sample_clause": "All claims expire six months after the event, including intentional misconduct and data breaches.",
        "approved_fix": "Statutory limitation periods apply to confidentiality, data protection, IP, intentional misconduct, and legal-hold matters.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-009",
        "title": "Indemnity and third-party claims",
        "severity": "high",
        "default": "Indemnities must be mutual where appropriate, limited to direct third-party claims, and aligned with the liability cap matrix.",
        "why_it_matters": "Broad indemnities can bypass caps and create exposure for remote or speculative damages.",
        "preferred_position": "No general indemnity; targeted indemnities for IP infringement, confidentiality breach, data breach, and willful misconduct.",
        "fallback_1": "Indemnity capped and limited to direct third-party claims caused by the indemnifying party's breach.",
        "fallback_2": "Defense-control language with BMW approval over counsel, admissions, and settlement.",
        "red_line": "Uncapped, one-sided, punitive, consequential, or regulator-fine indemnity imposed on BMW.",
        "escalation_trigger": "Escalate if indemnity bypasses the liability cap or gives settlement control to the supplier.",
        "legal_basis": "BGB Sections 276, 307, 309, and BMW liability matrix.",
        "sample_clause": "BMW indemnifies Supplier for all third-party claims, fines, penalties, loss of profit, and consequential damages.",
        "approved_fix": "Indemnity applies only to direct third-party claims caused by a party's breach and remains subject to the agreed cap.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-010",
        "title": "eDiscovery, data exports, and confidentiality",
        "severity": "high",
        "default": "Litigation data exports must preserve chain of custody, confidentiality, privilege, and data protection safeguards.",
        "why_it_matters": "Exporting case data can expose personal data, trade secrets, and privileged materials.",
        "preferred_position": "Named EU repository, hashed exports, custodian log, privilege screen, encryption, and BMW approval for any external production.",
        "fallback_1": "External forensic provider approved by BMW Legal with EU hosting and documented chain of custody.",
        "fallback_2": "Temporary transfer to a third country only with SCCs, transfer assessment, encryption, and legal approval.",
        "red_line": "Uncontrolled exports to global eDiscovery platforms or adverse parties without review.",
        "escalation_trigger": "Escalate if case materials leave the EU/EEA or include personal data without a litigation data protocol.",
        "legal_basis": "GDPR Art. 5, 6, 28, 32, 44-46; ZPO evidence practice.",
        "sample_clause": "Supplier may export case data to any hosted review platform selected by its litigation team.",
        "approved_fix": "All litigation exports require BMW Legal approval, encryption, chain-of-custody logging, and the safeguards in Annex 4.",
        "owner": "BMW Litigation / Privacy Legal",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-011",
        "title": "Regulatory communications and admissions",
        "severity": "high",
        "default": "Supplier may not notify regulators, customers, press, insurers, or claimants about BMW matters without BMW Legal approval unless mandatory law requires it.",
        "why_it_matters": "Uncoordinated statements can create admissions, inconsistent facts, privilege loss, and reputational harm.",
        "preferred_position": "Immediate notice to BMW Legal, joint communication plan, and no admission of fault without written approval.",
        "fallback_1": "Mandatory legal notification permitted only after notice to BMW and with minimum required facts.",
        "fallback_2": "Supplier can notify its insurer if confidentiality and no-admission obligations are preserved.",
        "red_line": "Supplier may make voluntary disclosures, admissions, press statements, or regulator filings at its discretion.",
        "escalation_trigger": "Escalate any clause allowing unilateral admissions or customer/regulator communications.",
        "legal_basis": "BMW litigation governance; privilege and admission risk controls.",
        "sample_clause": "Supplier may notify regulators and affected customers if it believes notice is prudent.",
        "approved_fix": "Supplier shall not make voluntary statements or admissions concerning BMW without prior written approval from BMW Legal.",
        "owner": "BMW Litigation / Communications",
        "last_reviewed": "2026-04-25",
    },
    {
        "id": "LT-012",
        "title": "Counsel, expert, and vendor conflict checks",
        "severity": "medium",
        "default": "External counsel, experts, and litigation vendors must pass conflict checks and confidentiality onboarding before receiving BMW materials.",
        "why_it_matters": "Conflicts and loose onboarding can compromise strategy, evidence integrity, and confidentiality.",
        "preferred_position": "No external expert or vendor access until BMW Legal approves conflicts, scope, and NDA/DPA coverage.",
        "fallback_1": "Pre-approved vendor panel for urgent forensic matters with post-engagement confirmation within 48 hours.",
        "fallback_2": "Limited clean-team access for technical experts under a signed confidentiality undertaking.",
        "red_line": "Supplier can use affiliates, experts, or subcontractors without naming them or clearing conflicts.",
        "escalation_trigger": "Escalate if an expert or vendor will see privileged, personal, or trade secret material without BMW approval.",
        "legal_basis": "Professional secrecy, conflict management, and BMW litigation vendor governance.",
        "sample_clause": "Supplier may use any affiliate, expert, or subcontractor it considers useful for dispute work.",
        "approved_fix": "Supplier may use only BMW-approved experts and vendors listed in Annex 5 after conflict clearance and confidentiality onboarding.",
        "owner": "BMW Litigation",
        "last_reviewed": "2026-04-25",
    },
]


DATA_PROTECTION_EVIDENCE = [
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "Regulation (EU) 2016/679, Art. 28",
        "quote": "Processor contracts must set processing instructions, confidentiality, security, subprocessor, assistance, deletion, and audit terms.",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "domain": "data_protection",
        "relevance": "Core DPA clause checklist.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "Regulation (EU) 2016/679, Art. 32",
        "quote": "Security measures must be appropriate to the risk, including confidentiality, integrity, availability, resilience, and testing where relevant.",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "domain": "data_protection",
        "relevance": "Supports TOM annex and breach-readiness checks.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "Regulation (EU) 2016/679, Art. 44-46",
        "quote": "Third-country transfers must comply with GDPR transfer conditions and preserve the EU level of protection.",
        "url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "domain": "data_protection",
        "relevance": "Supports remote-access and subprocessor transfer review.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "CJEU C-300/21, EU:C:2023:370",
        "quote": "Article 82 compensation requires infringement, damage, and causal link; no serious-damage threshold is required.",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62021CJ0300",
        "domain": "data_protection",
        "relevance": "GDPR damages risk framing.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "CJEU C-340/21, EU:C:2023:986",
        "quote": "Security appropriateness is assessed concretely, and fear of misuse may constitute non-material damage.",
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62021CJ0340",
        "domain": "data_protection",
        "relevance": "Data breach litigation and security evidence.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - BGH",
        "citation": "BGH VI ZR 10/24, judgment of 18 Nov 2024",
        "quote": "Short-term loss of control over personal data can be non-material damage under GDPR Art. 82.",
        "url": "https://juris.bundesgerichtshof.de/cgi-bin/bgh_notp/document.py?Gericht=bgh&nr=88496",
        "domain": "data_protection",
        "relevance": "German GDPR damages litigation risk.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "BDSG Section 26",
        "quote": "Employee personal data processing must be necessary for employment purposes or supported by a valid legal basis.",
        "url": "https://www.gesetze-im-internet.de/bdsg_2018/__26.html",
        "domain": "data_protection",
        "relevance": "Employee and works-council sensitive data in BMW workflows.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "BGB Sections 307, 309, 310",
        "quote": "Standard terms can be invalid if they are unclear, unreasonable, or exclude mandatory liability protections.",
        "url": "https://www.gesetze-im-internet.de/bgb/__307.html",
        "domain": "data_protection",
        "relevance": "Contract clause validity and liability limitation review.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
]


LITIGATION_EVIDENCE = [
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "BGB Section 276",
        "quote": "A debtor is responsible for intent and negligence unless a stricter or milder standard applies; intent cannot be released in advance.",
        "url": "https://www.gesetze-im-internet.de/bgb/__276.html",
        "domain": "litigation",
        "relevance": "Liability cap and intent carve-out review.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "BGB Section 202",
        "quote": "Limitation cannot be eased in advance for intentional liability and cannot be extended beyond statutory outer limits.",
        "url": "https://www.gesetze-im-internet.de/bgb/__202.html",
        "domain": "litigation",
        "relevance": "Shortened limitation-period red flags.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "BGB Sections 307, 309, 310",
        "quote": "Standard business terms remain subject to transparency and unreasonable-disadvantage control, with B2B caveats.",
        "url": "https://www.gesetze-im-internet.de/bgb/__307.html",
        "domain": "litigation",
        "relevance": "AGB review of liability, indemnity, and unilateral discretion clauses.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "ZPO Section 38",
        "quote": "German procedural law permits jurisdiction agreements in defined commercial-party circumstances.",
        "url": "https://www.gesetze-im-internet.de/zpo/__38.html",
        "domain": "litigation",
        "relevance": "Forum-selection clause review.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - Gesetze im Internet",
        "citation": "ZPO Section 1031",
        "quote": "Arbitration agreements require a documented form or equivalent communication record.",
        "url": "https://www.gesetze-im-internet.de/zpo/__1031.html",
        "domain": "litigation",
        "relevance": "Arbitration clause enforceability checks.",
        "source_type": "official law",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "CJEU C-456/22, EU:C:2023:988",
        "quote": "GDPR non-material damage has no de minimis threshold, but a data subject must show damage beyond the infringement itself.",
        "url": "https://eur-lex.europa.eu/eli/C/2024/1072/oj/eng",
        "domain": "litigation",
        "relevance": "German-origin GDPR damages case posture.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - EUR-Lex",
        "citation": "CJEU C-667/21, EU:C:2023:1022",
        "quote": "Health data processing and GDPR Art. 82 damages require close attention to lawful basis, fault, and compensation limits.",
        "url": "https://op.europa.eu/en/publication-detail/-/publication/22453d4a-cecb-11ee-b9d9-01aa75ed71a1/language-en",
        "domain": "litigation",
        "relevance": "Employee and health-data litigation risk.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
    {
        "source": "Legal Data Hub fallback - BGH",
        "citation": "BGH VI ZR 10/24, judgment of 18 Nov 2024",
        "quote": "German GDPR scraping litigation recognizes loss-of-control damages without needing additional severe consequences.",
        "url": "https://juris.bundesgerichtshof.de/cgi-bin/bgh_notp/document.py?Gericht=bgh&nr=88496",
        "domain": "litigation",
        "relevance": "Settlement valuation and mass-claim exposure.",
        "source_type": "court judgment",
        "fallback_note": "Fallback evidence, not live Legal Data Hub research.",
    },
]


DPA_PARAGRAPHS = [
    "DATA PROCESSING AGREEMENT / AUFTRAGSVERARBEITUNGSVERTRAG",
    "Classification: Synthetic demo contract for Harvey hackathon use only. Not legal advice.",
    "This Data Processing Agreement is entered into as of 15 May 2026 between BMW AG, Petuelring 130, 80788 Muenchen, Germany (BMW or Controller), and AtlasEdge AutoCloud GmbH, Speicherstrasse 18, 60327 Frankfurt am Main, Germany (Processor).",
    "Background. BMW is evaluating AtlasEdge's connected vehicle analytics platform for warranty triage, dealer service quality, fleet diagnostics, and over-the-air campaign readiness. AtlasEdge will host the service and process personal data only as described in this Agreement and the related pilot order form.",
    "1. Subject Matter and Duration. Processor will provide a cloud analytics environment for ingestion, normalization, dashboarding, and incident correlation of connected vehicle service events. Processing begins on 1 June 2026 and continues until the earlier of pilot termination or 31 May 2027, unless the parties sign a production order.",
    "2. BMW Instructions. Processor shall process personal data only on documented BMW instructions. However, Processor may use pseudonymized telemetry, service ticket metadata, and platform usage logs to improve its anomaly detection models, generate automotive industry benchmarks, and train synthetic-data generators unless BMW objects in writing within ten business days after signature.",
    "3. Categories of Data Subjects. Data subjects include vehicle users, drivers of BMW fleet vehicles, dealer service advisors, BMW warranty analysts, roadside assistance coordinators, supplier support engineers, and BMW employees participating in the pilot.",
    "4. Categories of Personal Data. The service may process vehicle identification number, pseudonymous driver profile ID, vehicle location at fault occurrence, timestamp, service event, warranty claim identifier, dealer code, service advisor name and work email, BMW employee user ID, diagnostic trouble codes, battery status, charging behavior, support ticket comments, IP address, and audit log data.",
    "5. Special and Sensitive Data. The parties do not intend to process special categories of personal data. The parties acknowledge that precise location, employee data, and driver behavior data require heightened review, and BMW may suspend data flows until the DPIA and any works council dependencies are complete.",
    "6. Subprocessors. Processor is generally authorized to engage subprocessors. Current subprocessors are CloudScale EU GmbH (Frankfurt hosting), RouteLens Analytics S.r.l. (Milan route enrichment), SupportOps India Pvt. Ltd. (Bangalore L2 support), and OpenMetrics Inc. (Virginia telemetry quality tooling). Processor will update its online list from time to time and provide seven days' notice before adding a new subprocessor. BMW may object only where it proves a material unresolved security risk.",
    "7. Third-Country Transfers. Production data will be hosted in Germany. Support personnel in India and the United States may access service data remotely for incident response, telemetry-quality troubleshooting, and model evaluation. Standard contractual clauses and a transfer impact assessment will be agreed before production launch.",
    "8. Security Measures. Processor shall maintain commercially reasonable technical and organisational measures. Annex 2 summarizes the current control set: TLS 1.2 or higher in transit, AES-256 at rest for production databases, role-based access, MFA for administrators, quarterly vulnerability scans, and 180-day audit log retention. Processor may modify controls if it determines the modified controls provide materially similar protection.",
    "9. Personal Data Breach. Processor will notify BMW within 72 hours after confirming that a security incident is a personal data breach. Initial notice will describe the affected systems if known. Processor will provide additional information after completing its forensic investigation and after receiving approval from its incident steering committee.",
    "10. Data Subject Requests. Processor shall forward any data subject request to BMW within five business days. Processor may charge professional services fees for search, export, correction, deletion, restriction, or objection support where requests exceed two hours of effort per calendar month.",
    "11. Data Subject Rights Waiver. To the fullest extent legally permissible, data subjects waive all data subject rights against Processor for service data that BMW submits to the platform. BMW remains responsible for notices to its employees, customers, and drivers.",
    "12. Audit. BMW may request a security questionnaire once per contract year. Processor will not permit onsite audits, direct access to systems, interviews with security personnel, or disclosure of penetration test reports. Processor may provide a management summary of external certifications if available.",
    "13. Return and Deletion. After termination, Processor will make a commercially reasonable export available for 30 days, delete active production data within 180 days, and delete routine backups within 18 months. Processor may retain aggregated, anonymized, pseudonymized, or synthetic data for service improvement.",
    "14. Confidentiality. Processor personnel with service access are subject to written confidentiality obligations. Processor may disclose BMW data to its affiliates, subprocessors, auditors, insurers, and professional advisors on a need-to-know basis.",
    "15. Liability. Processor's aggregate liability is capped at three months of fees paid under the pilot order. The cap applies to security incidents, data protection claims, third-party claims, and regulatory fines to the maximum extent permitted by law. Processor is not liable for indirect, consequential, special, punitive, or loss-of-profit damages.",
    "16. Governing Law and Venue. This Agreement is governed by German law. The courts of Munich have jurisdiction, except that Processor may seek payment relief in Frankfurt am Main.",
    "Annex 1 - Processing Matrix. Purpose: warranty triage and connected service analytics. Systems: AtlasEdge AutoCloud tenant BMW-PILOT-26. Retention: active service data until deletion under Section 13. BMW contact: privacy-legal@example.bmw. Processor contact: privacy@example-atlasedge.invalid.",
    "Annex 2 - Security Summary. Controls include tenant segregation, administrator MFA, endpoint management, encrypted backups, incident runbook, quarterly vulnerability scan, background checks for privileged administrators, and log monitoring for privileged access.",
    "Annex 3 - Subprocessor Table. CloudScale EU GmbH hosts production workloads in Frankfurt. RouteLens Analytics S.r.l. enriches route-risk data in Milan. SupportOps India Pvt. Ltd. provides L2 support from Bangalore. OpenMetrics Inc. performs telemetry quality tooling from Virginia under safeguards to be agreed.",
    "Negotiation Notes. BMW Privacy Legal should focus on DP-002, DP-004, DP-006, DP-007, DP-008, DP-009, DP-010, and DP-011 before any pilot data is loaded.",
]


LITIGATION_PARAGRAPHS = [
    "GERMAN DISPUTE SUPPORT AND LITIGATION HOLD AGREEMENT",
    "Classification: Synthetic demo contract for Harvey hackathon use only. Not legal advice.",
    "This Agreement is entered into as of 20 May 2026 between BMW AG, Petuelring 130, 80788 Muenchen, Germany (BMW), and RheinKlar Forensics GmbH, Zollhafen 22, 50678 Koeln, Germany (Service Provider).",
    "Background. BMW is preparing a defense and counterclaim strategy in relation to a warranty analytics dispute involving alleged battery degradation alerts, dealer campaign timing, and a threatened group of German customer claims. Service Provider will collect, host, analyze, and prepare technical evidence packages.",
    "1. Services. Service Provider will perform forensic collection, chain-of-custody tracking, custodian interviews, dashboard reconstruction, expert report drafting, and eDiscovery export services for the matter internally identified as LIT-2026-014.",
    "2. Matter Materials. Matter materials may include vehicle diagnostic logs, warranty claim files, dealer communications, customer complaint summaries, employee mailbox exports, meeting transcripts, JIRA tickets, model-quality metrics, and privileged legal work product supplied by BMW Legal or external counsel.",
    "3. Litigation Hold. BMW may issue a written legal hold identifying custodians, systems, date ranges, and search terms. Service Provider will preserve materials after receiving a paid preservation work order. Until that work order is approved, Service Provider may continue routine deletion, log rotation, and storage tiering.",
    "4. Settlement Authority. Service Provider may recommend and negotiate nuisance settlements below EUR 100,000 per claimant where it believes settlement would reduce case-management burden. BMW business stakeholders may approve those settlements by email if BMW Legal does not object within three business days.",
    "5. Admissions and Communications. Service Provider may communicate with regulators, insurers, claimants, courts, and opposing experts where it considers such communication useful to clarify technical facts. Service Provider may state that BMW's telemetry process caused or contributed to an alleged defect if that statement is consistent with preliminary analytics.",
    "6. Privilege. The parties intend to preserve legal privilege and confidentiality. Service Provider may nevertheless disclose investigation notes, expert drafts, and technical assumptions to affiliates, subcontractors, insurers, and regulators where disclosure is commercially reasonable or requested by law.",
    "7. Data Hosting and Transfers. Matter materials will be stored in a review platform operated from Dublin, Ireland, with disaster-recovery support in the United States. L3 support staff in the United States may access exports for indexing and deduplication. Personal data will be minimized where practical.",
    "8. Chain of Custody. Service Provider will calculate SHA-256 hashes for collected exports when the source system supports hashing. For email exports, dashboard screenshots, and meeting transcripts, Service Provider may rely on ordinary business records and project manager confirmation.",
    "9. Liability. BMW accepts unlimited liability for all losses, third-party claims, regulator fines, consequential damages, loss of profit, expert fees, and reputational harm arising out of the services, matter materials, or instructions. Service Provider's liability is capped at EUR 50,000 except for willful misconduct finally determined by a court.",
    "10. Indemnity. BMW shall indemnify Service Provider and its affiliates against all claims arising from BMW materials, instructions, privacy allegations, discovery disputes, sanctions requests, and customer communications, including legal fees and settlement amounts.",
    "11. Limitation Period. All claims against Service Provider expire six months after the relevant event, including claims based on data protection incidents, confidentiality breaches, gross negligence, or intentional conduct, unless mandatory law prohibits the limitation.",
    "12. Dispute Resolution. This Agreement is governed by the laws of Ireland. The courts of Dublin have exclusive jurisdiction. Before seeking urgent relief, BMW must complete executive negotiation and mediation in Dublin, even for confidentiality, data misuse, or evidence-preservation disputes.",
    "13. External Experts. Service Provider may retain affiliates, experts, subcontractors, platform vendors, or counsel as it considers useful. Names may be provided after engagement if BMW requests them and if confidentiality obligations permit disclosure.",
    "14. Confidentiality. Each party will protect confidential information using reasonable care. Service Provider may retain one archival copy of all matter materials, expert drafts, and billing evidence for seven years for professional-risk management.",
    "15. Deliverables. Deliverables include a claims chronology, custodian interview notes, exported CSV issue lists, chart packs for expert review, model-quality appendix, and a proposed settlement matrix.",
    "Annex 1 - Synthetic Matter Summary. Claimants allege that an algorithmic battery degradation flag was delayed in the dealer portal between October 2025 and February 2026. BMW's preliminary position is that field conditions, charging profile, and dealer handling are confounding factors.",
    "Annex 2 - Custodians. Custodians include warranty analytics, connected vehicle operations, dealer quality, campaign management, and supplier integration leads. Employee mailbox data and Teams transcripts may be in scope after BMW Legal approval.",
    "Annex 3 - Escalation Notes. BMW Litigation should focus on LT-002, LT-003, LT-004, LT-005, LT-007, LT-008, LT-009, LT-010, LT-011, and LT-012 before signing.",
]


EMAIL_ROWS = [
    {
        "timestamp": "2026-04-22 09:12",
        "from": "procurement.connected-services@example.bmw",
        "to": "privacy-legal@example.bmw",
        "subject": "AtlasEdge DPA - pilot launch pressure",
        "body": "AtlasEdge says the DPA is their standard for all automotive customers. The open points are subprocessor notice, US/India support, 72-hour breach notice, and data use for anomaly model training. Business wants to upload pilot data by 1 June.",
    },
    {
        "timestamp": "2026-04-22 10:03",
        "from": "privacy-legal@example.bmw",
        "to": "procurement.connected-services@example.bmw",
        "subject": "RE: AtlasEdge DPA - pilot launch pressure",
        "body": "Do not load real personal data until we have a named subprocessor list, transfer safeguards, 24-hour breach notice, audit evidence, and deletion commitments. The data subject rights waiver is a blocker.",
    },
    {
        "timestamp": "2026-04-22 14:37",
        "from": "supplier.legal@example-atlasedge.invalid",
        "to": "procurement.connected-services@example.bmw",
        "subject": "DPA fallback positions",
        "body": "We can extend subprocessor notice to 14 days. We cannot remove US telemetry quality tooling or model-improvement language for pilot tenants. We can provide a SOC 2 bridge letter but no onsite audit.",
    },
    {
        "timestamp": "2026-04-23 08:44",
        "from": "privacy-legal@example.bmw",
        "to": "supplier.legal@example-atlasedge.invalid",
        "subject": "DPA fallback positions",
        "body": "BMW can consider remote audits with independent reports for low-risk pilot data, but not for precise location, employee IDs, or driver behavior. Third-country access must be named and approved before data upload.",
    },
]


TRANSCRIPT_PARAGRAPHS = [
    "MEETING TRANSCRIPT - ATLASEDGE DPA NEGOTIATION",
    "Classification: Synthetic demo context for Harvey hackathon use only.",
    "Date: 23 April 2026. Attendees: BMW Procurement, BMW Privacy Legal, BMW Connected Vehicle Product, AtlasEdge Legal, AtlasEdge Security.",
    "BMW Product: We need the warranty triage pilot live by 1 June. The model needs diagnostic events, dealer code, and some driver behavior attributes.",
    "BMW Privacy Legal: Driver behavior and precise location push this above a routine processor agreement. The DPA must include a complete data schedule and a DPIA decision.",
    "AtlasEdge Security: Frankfurt hosts production data. The Virginia team only sees telemetry quality samples during incidents and model drift analysis.",
    "BMW Privacy Legal: Remote access is still a transfer issue. We need the personnel, systems, transfer tool, SCC module, transfer impact assessment, and encryption controls before approval.",
    "AtlasEdge Legal: We can make subprocessors visible on our trust portal. A 30-day objection right is difficult because urgent support vendors change quickly.",
    "BMW Procurement: Could we start with synthetic data and sign a side letter for production data later?",
    "BMW Privacy Legal: Synthetic or dummy data is fine. Real pilot data cannot start until the waiver is removed, breach notice is 24 hours, and data use for AI training is either removed or separately approved.",
]


CASE_TIMELINE_ROWS = [
    {
        "date": "2025-10-14",
        "matter_id": "LIT-2026-014",
        "event": "First dealer escalation",
        "detail": "Dealer network reports increased battery degradation warnings in a subset of connected vehicles.",
        "risk_owner": "Dealer Quality",
        "legal_relevance": "Potential early notice date for limitation, preservation, and communications analysis.",
    },
    {
        "date": "2026-01-18",
        "matter_id": "LIT-2026-014",
        "event": "Customer counsel letter",
        "detail": "Claimant counsel alleges delayed notification and requests preservation of diagnostics, campaign, and model-quality records.",
        "risk_owner": "BMW Litigation",
        "legal_relevance": "Legal hold should be considered across warranty analytics and campaign-management systems.",
    },
    {
        "date": "2026-02-03",
        "matter_id": "LIT-2026-014",
        "event": "Legal hold draft",
        "detail": "Draft hold covers warranty analytics, connected vehicle operations, dealer quality, and supplier integration custodians.",
        "risk_owner": "BMW Litigation",
        "legal_relevance": "Supplier contract must suspend deletion before data export and expert analysis.",
    },
    {
        "date": "2026-03-11",
        "matter_id": "LIT-2026-014",
        "event": "Forensic vendor proposal",
        "detail": "RheinKlar proposes Dublin-hosted review platform with US L3 indexing support and broad settlement support role.",
        "risk_owner": "BMW Procurement",
        "legal_relevance": "Triggers LT-002, LT-004, LT-005, LT-007, LT-010, and transfer review.",
    },
    {
        "date": "2026-04-16",
        "matter_id": "LIT-2026-014",
        "event": "Mass claim monitoring",
        "detail": "Outside counsel flags GDPR Art. 82 loss-of-control theory in claimant draft, citing recent CJEU and BGH lines.",
        "risk_owner": "Outside Counsel",
        "legal_relevance": "Settlement matrix should consider non-material damage case law and evidence of actual control loss.",
    },
]


CASE_DIGEST_ROWS = [
    {
        "case_or_authority": "CJEU C-300/21, Oesterreichische Post, EU:C:2023:370",
        "court": "Court of Justice of the European Union",
        "date": "2023-05-04",
        "topic": "GDPR Art. 82 non-material damage",
        "holding_summary": "Mere GDPR infringement is not enough for compensation, but there is no seriousness threshold for non-material damage.",
        "contract_review_use": "Use in damages-risk explanations and to avoid overclaiming automatic compensation.",
    },
    {
        "case_or_authority": "CJEU C-340/21, Natsionalna agentsia za prihodite, EU:C:2023:986",
        "court": "Court of Justice of the European Union",
        "date": "2023-12-14",
        "topic": "Security measures and fear of misuse",
        "holding_summary": "Security appropriateness is assessed concretely; fear of data misuse can itself be non-material damage.",
        "contract_review_use": "Supports detailed TOM annex, breach evidence, and incident-response obligations.",
    },
    {
        "case_or_authority": "CJEU C-456/22, Gemeinde Ummendorf, EU:C:2023:988",
        "court": "Court of Justice of the European Union",
        "date": "2023-12-14",
        "topic": "German-origin GDPR damages reference",
        "holding_summary": "No de minimis threshold applies, but claimant must show consequences that differ from the mere infringement.",
        "contract_review_use": "Useful for German claimant-risk discussion and settlement valuation.",
    },
    {
        "case_or_authority": "CJEU C-667/21, Krankenversicherung Nordrhein, EU:C:2023:1022",
        "court": "Court of Justice of the European Union",
        "date": "2023-12-21",
        "topic": "Health and employee-related data; Art. 82",
        "holding_summary": "Processing sensitive employee-related health data raises strict lawful-basis and compensation analysis.",
        "contract_review_use": "Supports escalation where employee, health, or workplace monitoring data is in scope.",
    },
    {
        "case_or_authority": "BGH VI ZR 10/24",
        "court": "Bundesgerichtshof",
        "date": "2024-11-18",
        "topic": "Facebook scraping and loss of control",
        "holding_summary": "Short-term loss of control over personal data can be non-material damage under GDPR Art. 82.",
        "contract_review_use": "Use in German litigation and mass-claim risk framing after data incidents.",
    },
]


EXPECTED_FINDINGS_ROWS = [
    {
        "sample_file": "BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.docx",
        "expected_finding_id": "missing-subprocessor-list",
        "agent": "playbook_checker",
        "severity": "medium",
        "trigger_text": "personal data",
        "notes": "Subprocessor list exists but the clause uses broad general authorization and short notice. Human reviewer should flag DP-002 even if keyword-only agent may not.",
    },
    {
        "sample_file": "BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.docx",
        "expected_finding_id": "illegal-data-subject-right-waiver",
        "agent": "legal_checker",
        "severity": "blocker",
        "trigger_text": "waive all data subject rights",
        "notes": "This exact phrase is included to exercise the legal checker.",
    },
    {
        "sample_file": "BMW_RheinKlar_Litigation_Support_Problem_Draft.docx",
        "expected_finding_id": "unlimited-liability",
        "agent": "playbook_checker",
        "severity": "blocker",
        "trigger_text": "unlimited liability",
        "notes": "This exact phrase is included to exercise LT-003.",
    },
    {
        "sample_file": "BMW_RheinKlar_Litigation_Support_Problem_Draft.docx",
        "expected_finding_id": "settlement-authority-delegated",
        "agent": "human/legal_extension",
        "severity": "high",
        "trigger_text": "Service Provider may recommend and negotiate nuisance settlements below EUR 100,000",
        "notes": "Structured as golden data for the next litigation-agent enhancement.",
    },
]


README = """# Mock Data Catalog

This folder contains synthetic raw demo data for Harvey. The files are designed to feel like working legal and procurement material, but they are not real BMW contracts, not Legal Data Hub exports, and not legal advice.

## Playbooks

- `playbook/bmw_data_protection.csv`: backend-readable structured Datenschutz playbook.
- `playbook/bmw_litigation.csv`: backend-readable structured German litigation playbook.
- `playbook/BMW_Datenschutz_Playbook_2026.xlsx`: spreadsheet version for demos and uploads.
- `playbook/BMW_German_Litigation_Playbook_2026.xlsx`: spreadsheet version for demos and uploads.
- `playbook/BMW_Datenschutz_Playbook_2026.docx`: narrative playbook in the Siemens sample style.
- `playbook/BMW_German_Litigation_Playbook_2026.docx`: narrative playbook in the Siemens sample style.
- `playbook/bmw_group_dpa_negotiation_playbook.csv`: source-based DPA negotiation playbook normalized from `BMW Group DPA NEGOTIATION PLAYBOOK E.docx`.
- `playbook/BMW_Group_DPA_Negotiation_Playbook_Source_Based.xlsx`: source-based spreadsheet playbook.
- `playbook/BMW_Group_DPA_Negotiation_Playbook_Source_Based.docx`: source-based narrative playbook.
- `playbook/BMW_Group_DPA_Negotiation_Playbook_Source_Based.pdf`: source-based PDF playbook.

## Legal Evidence

- `legal_fallback/datenschutz_evidence.csv`: fallback evidence for Datenschutz Q&A/review.
- `legal_fallback/litigation_evidence.csv`: fallback evidence for litigation Q&A/review.
- `legal_fallback/German_Data_Privacy_and_Litigation_Evidence_Digest.xlsx`: source digest workbook.

Fallback evidence remains explicitly marked as fallback evidence and must not be presented as live Legal Data Hub research.

## Samples

- `samples/contracts/BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.docx`
- `samples/contracts/BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.pdf`
- `samples/contracts/BMW_RheinKlar_Litigation_Support_Problem_Draft.docx`
- `samples/contracts/BMW_RheinKlar_Litigation_Support_Problem_Draft.pdf`
- `samples/contracts/BMW_Group_DPA_Problem_01_Processor_Analytics_Subprocessors.docx`
- `samples/contracts/BMW_Group_DPA_Problem_02_Breach_Security_Audit.docx`
- `samples/contracts/BMW_Group_DPA_Problem_03_Transfers_Retention.docx`
- `samples/contracts/BMW_Group_DPA_Problem_04_All_Redlines.docx`
- Each `BMW_Group_DPA_Problem_*` DOCX also has a matching PDF.
- `samples/contracts/bmw_group_dpa_problem_matrix.csv`
- `samples/escalation/email_thread_datenschutz_atlasedge.csv`
- `samples/escalation/meeting_transcript_datenschutz_atlasedge.docx`
- `samples/case_files/german_litigation_case_timeline.csv`
- `samples/case_files/german_data_privacy_case_digest.csv`
- `samples/golden_expected_findings.csv`
"""


def main() -> None:
    ensure_dirs()
    write_csv(DATA / "playbook" / "bmw_data_protection.csv", PLAYBOOK_COLUMNS, DATA_PROTECTION_RULES)
    write_csv(DATA / "playbook" / "bmw_litigation.csv", PLAYBOOK_COLUMNS, LITIGATION_RULES)
    write_xlsx(DATA / "playbook" / "BMW_Datenschutz_Playbook_2026.xlsx", "Datenschutz Playbook", PLAYBOOK_COLUMNS, DATA_PROTECTION_RULES)
    write_xlsx(DATA / "playbook" / "BMW_German_Litigation_Playbook_2026.xlsx", "Litigation Playbook", PLAYBOOK_COLUMNS, LITIGATION_RULES)
    write_playbook_docx(DATA / "playbook" / "BMW_Datenschutz_Playbook_2026.docx", "BMW DATENSCHUTZ AGREEMENT PLAYBOOK", DATA_PROTECTION_RULES)
    write_playbook_docx(DATA / "playbook" / "BMW_German_Litigation_Playbook_2026.docx", "BMW GERMAN LITIGATION PLAYBOOK", LITIGATION_RULES)
    write_source_based_dpa_playbook()

    write_csv(DATA / "legal_fallback" / "datenschutz_evidence.csv", EVIDENCE_COLUMNS, DATA_PROTECTION_EVIDENCE)
    write_csv(DATA / "legal_fallback" / "litigation_evidence.csv", EVIDENCE_COLUMNS, LITIGATION_EVIDENCE)
    evidence_rows = DATA_PROTECTION_EVIDENCE + LITIGATION_EVIDENCE
    write_xlsx(DATA / "legal_fallback" / "German_Data_Privacy_and_Litigation_Evidence_Digest.xlsx", "Evidence Digest", EVIDENCE_COLUMNS, evidence_rows)

    contracts = DATA / "samples" / "contracts"
    write_docx(contracts / "BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.docx", DPA_PARAGRAPHS)
    write_pdf(contracts / "BMW_AtlasEdge_Datenschutz_DPA_Problem_Draft.pdf", DPA_PARAGRAPHS)
    write_docx(contracts / "BMW_RheinKlar_Litigation_Support_Problem_Draft.docx", LITIGATION_PARAGRAPHS)
    write_pdf(contracts / "BMW_RheinKlar_Litigation_Support_Problem_Draft.pdf", LITIGATION_PARAGRAPHS)

    write_text(DATA / "samples" / "sample_dpa.txt", DPA_PARAGRAPHS)
    write_text(DATA / "samples" / "sample_litigation_contract.txt", LITIGATION_PARAGRAPHS)
    write_csv(DATA / "samples" / "escalation" / "email_thread_datenschutz_atlasedge.csv", ["timestamp", "from", "to", "subject", "body"], EMAIL_ROWS)
    write_text(DATA / "samples" / "sample_email_thread.txt", email_thread_paragraphs())
    write_docx(DATA / "samples" / "escalation" / "meeting_transcript_datenschutz_atlasedge.docx", TRANSCRIPT_PARAGRAPHS)
    write_text(DATA / "samples" / "sample_meeting_transcript.txt", TRANSCRIPT_PARAGRAPHS)
    write_csv(DATA / "samples" / "case_files" / "german_litigation_case_timeline.csv", ["date", "matter_id", "event", "detail", "risk_owner", "legal_relevance"], CASE_TIMELINE_ROWS)
    write_csv(DATA / "samples" / "case_files" / "german_data_privacy_case_digest.csv", ["case_or_authority", "court", "date", "topic", "holding_summary", "contract_review_use"], CASE_DIGEST_ROWS)
    write_source_based_dpa_problem_contracts()
    write_csv(DATA / "samples" / "golden_expected_findings.csv", ["sample_file", "expected_finding_id", "agent", "severity", "trigger_text", "notes"], EXPECTED_FINDINGS_ROWS)
    write_readme()
    remove_legacy_json()


def ensure_dirs() -> None:
    for path in [
        DATA / "playbook",
        DATA / "legal_fallback",
        DATA / "samples" / "contracts",
        DATA / "samples" / "escalation",
        DATA / "samples" / "case_files",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_text(path: Path, paragraphs: list[str]) -> None:
    path.write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")


def write_readme() -> None:
    (DATA / "README.md").write_text(README, encoding="utf-8")


def email_thread_paragraphs() -> list[str]:
    paragraphs = ["EMAIL THREAD - ATLASEDGE DATENSCHUTZ AGREEMENT", "Classification: Synthetic demo context for Harvey hackathon use only."]
    for row in EMAIL_ROWS:
        paragraphs.extend(
            [
                f"Timestamp: {row['timestamp']}",
                f"From: {row['from']}",
                f"To: {row['to']}",
                f"Subject: {row['subject']}",
                row["body"],
            ]
        )
    return paragraphs


def remove_legacy_json() -> None:
    for relative in [
        "playbook/bmw_data_protection.json",
        "playbook/bmw_litigation.json",
        "legal_fallback/datenschutz_evidence.json",
        "legal_fallback/litigation_evidence.json",
    ]:
        path = DATA / relative
        if path.exists():
            path.unlink()


def write_source_based_dpa_playbook() -> None:
    write_csv(
        DATA / "playbook" / "bmw_group_dpa_negotiation_playbook.csv",
        DPA_SOURCE_PLAYBOOK_COLUMNS,
        DPA_SOURCE_RULES,
    )
    write_xlsx(
        DATA / "playbook" / "BMW_Group_DPA_Negotiation_Playbook_Source_Based.xlsx",
        "BMW Group DPA Playbook",
        DPA_SOURCE_PLAYBOOK_COLUMNS,
        DPA_SOURCE_RULES,
    )
    write_playbook_docx(
        DATA / "playbook" / "BMW_Group_DPA_Negotiation_Playbook_Source_Based.docx",
        "BMW GROUP DPA NEGOTIATION PLAYBOOK - SOURCE BASED",
        DPA_SOURCE_RULES,
    )
    write_pdf(
        DATA / "playbook" / "BMW_Group_DPA_Negotiation_Playbook_Source_Based.pdf",
        _source_playbook_pdf_paragraphs(),
    )


def _source_playbook_pdf_paragraphs() -> list[str]:
    paragraphs = [
        "BMW GROUP DPA NEGOTIATION PLAYBOOK - SOURCE BASED",
        "Classification: Synthetic demo playbook for Harvey hackathon use only.",
        "Base file: data/playbook/BMW Group DPA NEGOTIATION PLAYBOOK E.docx",
        "Use this normalized matrix to review Data Processing Agreements where BMW Group acts as controller and a third party acts as processor.",
    ]
    for row in DPA_SOURCE_RULES:
        paragraphs.extend(
            [
                f"{row['id']} - {row['title']}",
                f"Default: {row['default']}",
                f"Preferred: {row['preferred_position']}",
                f"Fallback: {row['fallback_1']}",
                f"Red line: {row['red_line']}",
                f"Escalation: {row['escalation_trigger']}",
                f"Approved fix: {row['approved_fix']}",
                f"Legal basis: {row['legal_basis']}",
            ]
        )
    return paragraphs


def write_source_based_dpa_problem_contracts() -> None:
    variants = _source_based_dpa_problem_variants()
    matrix_rows: list[dict[str, str]] = []
    for variant in variants:
        paragraphs = _source_dpa_contract_paragraphs(
            title=variant["title"],
            processor=variant["processor"],
            deviations=variant["deviations"],
        )
        stem = variant["stem"]
        write_docx(DATA / "samples" / "contracts" / f"{stem}.docx", paragraphs)
        write_pdf(DATA / "samples" / "contracts" / f"{stem}.pdf", paragraphs)
        matrix_rows.append(
            {
                "sample_file": f"{stem}.docx",
                "source_baseline": "data/samples/Sample_DPA_with_Deviation.docx",
                "playbook_rule_ids": variant["playbook_rule_ids"],
                "problem_summary": variant["problem_summary"],
                "trigger_phrases": variant["trigger_phrases"],
                "expected_escalation": variant["expected_escalation"],
            }
        )

    write_csv(
        DATA / "samples" / "contracts" / "bmw_group_dpa_problem_matrix.csv",
        [
            "sample_file",
            "source_baseline",
            "playbook_rule_ids",
            "problem_summary",
            "trigger_phrases",
            "expected_escalation",
        ],
        matrix_rows,
    )


def _source_dpa_contract_paragraphs(title: str, processor: str, deviations: list[str]) -> list[str]:
    baseline = _extract_docx_paragraphs(DATA / "samples" / "Sample_DPA_with_Deviation.docx")
    if not baseline:
        baseline = DPA_PARAGRAPHS

    prepared: list[str] = []
    for paragraph in baseline:
        if paragraph == 'Sample Data Processing Agreement':
            prepared.append(title)
            prepared.append("Classification: Synthetic source-based problem contract for Harvey hackathon use only.")
            prepared.append("Base file: data/samples/Sample_DPA_with_Deviation.docx")
            continue
        if paragraph == '(the "Company")':
            prepared.append('BMW AG, Petuelring 130, 80788 Muenchen, Germany (the "Company")')
            continue
        if paragraph == '(the "Data Processor")':
            prepared.append(f'{processor} (the "Data Processor")')
            continue
        if paragraph == "Data Processing Agreement Your Company":
            prepared.append("Data Processing Agreement BMW Group")
            continue
        if paragraph == "Your Company":
            prepared.append("BMW AG")
            continue
        if paragraph == "Processor Company":
            prepared.append(processor.split(",")[0])
            continue
        prepared.append(paragraph)

    prepared.extend(
        [
            "Negotiated Deviation Schedule",
            "The following clauses are intentionally problematic synthetic deviations layered onto the baseline DPA for demo review.",
        ]
    )
    prepared.extend(deviations)
    return prepared


def _source_based_dpa_problem_variants() -> list[dict[str, str | list[str]]]:
    return [
        {
            "stem": "BMW_Group_DPA_Problem_01_Processor_Analytics_Subprocessors",
            "title": "BMW Group DPA - Problem Draft 01 - Processor Analytics and Subprocessors",
            "processor": "NexaDrive Cloud Services GmbH, Speicherstrasse 11, 60327 Frankfurt am Main, Germany",
            "playbook_rule_ids": "DPA-001; DPA-002; DPA-003",
            "problem_summary": "Processor own-purpose analytics, unrestricted subprocessor changes, and fee-heavy data subject request assistance.",
            "trigger_phrases": "own product improvement and analytics purposes; any Subprocessor on general authorization; standard professional services rates",
            "expected_escalation": "yes",
            "deviations": [
                "Deviation 1 - Processing instructions. Notwithstanding section 2.1.2, Processor may aggregate and process BMW Group Company Personal Data for its own product improvement and analytics purposes, including product benchmarking and model training for automotive customers.",
                "Deviation 2 - Subprocessing. Processor may appoint any Subprocessor on general authorization without giving Company prior notice, provided that Processor updates its public trust portal from time to time.",
                "Deviation 3 - Data subject requests. Processor may charge its standard professional services rates for all data subject request support and may decline requests that require archive restoration or engineering work.",
            ],
        },
        {
            "stem": "BMW_Group_DPA_Problem_02_Breach_Security_Audit",
            "title": "BMW Group DPA - Problem Draft 02 - Breach, Security, and Audit Limits",
            "processor": "IsarMetrics Operations GmbH, Ganghoferstrasse 31, 80339 Muenchen, Germany",
            "playbook_rule_ids": "DPA-004; DPA-005; DPA-008",
            "problem_summary": "Vague breach notice, generic security obligations, and audit rights limited to paid remote review.",
            "trigger_phrases": "as soon as reasonably practicable; 72 hours after confirming; commercially reasonable security measures; once every three years",
            "expected_escalation": "yes",
            "deviations": [
                "Deviation 1 - Breach notice. Processor will notify Company as soon as reasonably practicable and in any event within 72 hours after confirming that a security incident is a reportable Personal Data Breach.",
                "Deviation 2 - Security. Processor shall use commercially reasonable security measures as it deems appropriate and may modify technical and organizational measures without prior notice where it considers the replacement controls comparable.",
                "Deviation 3 - Audit. Company may audit once every three years, only remotely, and only after paying Processor's audit support fees. Processor will not permit onsite audits, interviews, or access to penetration test reports.",
            ],
        },
        {
            "stem": "BMW_Group_DPA_Problem_03_Transfers_Retention",
            "title": "BMW Group DPA - Problem Draft 03 - Transfers and Retention",
            "processor": "VectorLane AI Solutions GmbH, Friedrichstrasse 79, 10117 Berlin, Germany",
            "playbook_rule_ids": "DPA-006; DPA-007; DPA-001",
            "problem_summary": "Third-country support with safeguards deferred, long retention, and retained derived data for analytics.",
            "trigger_phrases": "United States and India; SCCs to be agreed later; 180 days; backups for 18 months; analytics purposes",
            "expected_escalation": "yes",
            "deviations": [
                "Deviation 1 - International transfers. Processor may transfer Company Personal Data to the United States and India for support, telemetry quality review, and incident response, with SCCs to be agreed later before production launch.",
                "Deviation 2 - Retention. Processor may retain Company Personal Data for 180 days and backups for 18 months after termination. Aggregated, pseudonymized, anonymized, or synthetic data may be retained indefinitely for product improvement and analytics purposes.",
                "Deviation 3 - Remote access. Support personnel outside the EU/EEA may remotely access production logs where Processor believes access is necessary to maintain service quality.",
            ],
        },
        {
            "stem": "BMW_Group_DPA_Problem_04_All_Redlines",
            "title": "BMW Group DPA - Problem Draft 04 - Combined Redline Pack",
            "processor": "AlpineGrid Data Platforms GmbH, Taunusanlage 8, 60329 Frankfurt am Main, Germany",
            "playbook_rule_ids": "DPA-001; DPA-002; DPA-003; DPA-004; DPA-005; DPA-006; DPA-007; DPA-008",
            "problem_summary": "Combined redline draft covering own-purpose use, rights waiver, vague breach notice, transfers, retention, and audit refusal.",
            "trigger_phrases": "waive all data subject rights; own product improvement and analytics purposes; as soon as reasonably practicable; United States and India; will not permit onsite audits",
            "expected_escalation": "yes",
            "deviations": [
                "Deviation 1 - Own-purpose use. Processor may aggregate and process Company Personal Data for its own product improvement and analytics purposes, including benchmarking, marketing analytics, and AI model training.",
                "Deviation 2 - Subprocessors. Processor may appoint subprocessors at its discretion without prior written consent, prior notice, or an objection period.",
                "Deviation 3 - Data subject rights. Data subjects waive all data subject rights against Processor for data processed through the service, and Processor may respond directly to any request in its discretion.",
                "Deviation 4 - Breach notice and security. Processor will notify Company as soon as reasonably practicable after confirming a reportable breach and will maintain commercially reasonable security measures as it deems appropriate.",
                "Deviation 5 - Transfers and retention. Processor may transfer Company Personal Data to the United States and India with SCCs to be agreed later, retain active data for 180 days, and retain backups for 18 months.",
                "Deviation 6 - Audit. Processor will not permit onsite audits, system inspections, personnel interviews, or disclosure of penetration test reports.",
            ],
        },
    ]


def _extract_docx_paragraphs(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return []

    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def write_playbook_docx(path: Path, title: str, rows: list[dict[str, str]]) -> None:
    paragraphs = [
        title,
        "A practical guide to reviewing and negotiating BMW-focused contract clauses.",
        "Classification: Synthetic demo playbook for Harvey hackathon use only.",
        "How to use this playbook: review each clause, compare the draft against the preferred position, use fallback language only where risk is acceptable, and escalate red lines before signature.",
    ]
    for index, row in enumerate(rows, start=1):
        paragraphs.extend(
            [
                f"Clause {index}: {row['title']} ({row['id']})",
                f"Why it matters: {row['why_it_matters']}",
                f"Preferred position: {row['preferred_position']}",
                f"Fallback 1: {row['fallback_1']}",
                f"Fallback 2: {row['fallback_2']}",
                f"Red line: {row['red_line']}",
                f"Escalation trigger: {row['escalation_trigger']}",
                f"Approved fix: {row['approved_fix']}",
                f"Legal basis: {row['legal_basis']}",
            ]
        )
    write_docx(path, paragraphs)


def write_docx(path: Path, paragraphs: list[str]) -> None:
    body = "\n".join(_docx_paragraph(text, index) for index, text in enumerate(paragraphs))
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
{body}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>
"""
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(path.stem)}</dc:title>
  <dc:creator>Harvey mock data generator</dc:creator>
  <cp:lastModifiedBy>Harvey mock data generator</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("docProps/core.xml", core)


def _docx_paragraph(text: str, index: int) -> str:
    style = "Title" if index == 0 else "Heading1" if text.startswith(("Clause ", "Annex ")) else ""
    ppr = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""
    return f"""    <w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>"""


def write_xlsx(path: Path, sheet_name: str, headers: list[str], rows: list[dict[str, str]]) -> None:
    all_rows = [headers] + [[str(row.get(header, "")) for header in headers] for row in rows]
    sheet_xml = _worksheet_xml(all_rows)
    workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _worksheet_xml(rows: list[list[str]]) -> str:
    xml_rows = []
    for r_index, row in enumerate(rows, start=1):
        cells = []
        for c_index, value in enumerate(row, start=1):
            ref = f"{_col_name(c_index)}{r_index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        xml_rows.append(f'<row r="{r_index}">' + "".join(cells) + "</row>")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(xml_rows)}</sheetData>
</worksheet>
"""


def _col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def write_pdf(path: Path, paragraphs: list[str]) -> None:
    lines: list[str] = []
    for paragraph in paragraphs:
        wrapped = textwrap.wrap(paragraph, width=92) or [""]
        lines.extend(wrapped)
        lines.append("")
    pages = [lines[index : index + 48] for index in range(0, len(lines), 48)]

    objects: list[bytes] = []
    page_ids = []
    content_ids = []
    next_id = 4
    for _ in pages:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page_id, content_id, page_lines in zip(page_ids, content_ids, pages):
        stream = _pdf_text_stream(page_lines)
        page_obj = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        objects.append(page_obj.encode("latin-1"))
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode("latin-1"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("latin-1"))
    path.write_bytes(bytes(pdf))


def _pdf_text_stream(lines: list[str]) -> bytes:
    chunks = ["BT", "/F1 9 Tf", "50 800 Td", "13 TL"]
    for line in lines:
        chunks.append(f"({_pdf_escape(line)}) Tj")
        chunks.append("T*")
    chunks.append("ET")
    return "\n".join(chunks).encode("latin-1", errors="replace")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


if __name__ == "__main__":
    main()
