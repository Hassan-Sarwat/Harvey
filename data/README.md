# Mock Data Catalog

This folder contains synthetic raw demo data for Harvey. The files are designed to feel like working legal and procurement material, but they are not real BMW contracts, not Legal Data Hub exports, and not legal advice.

## Playbooks

- `playbook/dpa_negotiation_playbook.md`: active backend-readable DPA negotiation playbook. The backend parses this Markdown into structured rule rows and also sends the full Markdown into the clause judge context.
- `playbook/bmw_litigation.csv`: backend-readable structured German litigation playbook.
- `playbook/BMW_German_Litigation_Playbook_2026.xlsx`: spreadsheet version for demos and uploads.
- `playbook/BMW_German_Litigation_Playbook_2026.docx`: narrative playbook in the Siemens sample style.
- `playbook/archive/`: older DPA CSV/PDF/DOCX/XLSX playbook variants retained for reference, not active backend routing.

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
