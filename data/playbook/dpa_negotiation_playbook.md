# DPA Negotiation Playbook

**Standard · Fall-back · Red line**

A short reference for negotiating Data Processing Agreements under GDPR Article 28. For each clause, the playbook sets out three positions: the preferred outcome (**Standard**), the negotiated compromise that remains within tolerance (**Fall-back**), and the position that triggers escalation or walk-away (**Red line**). The tiers reflect common controller-side market practice; vendor-side playbooks would mirror them in reverse.

---

## 1. Breach notification timeline

- **Standard** — Notification within 48 hours of discovery, including nature of incident, categories of data affected, and remediation steps under way.
- **Fall-back** — 72 hours after confirmation of an incident — still GDPR-compliant given the controller's own 72-hour reporting duty under Article 33.
- **Red line** — 30-day or "commercially reasonable" notification windows that put the controller in regulatory non-compliance from the outset.

## 2. Sub-processor governance

- **Standard** — Prior written notification of each new sub-processor with a 30-day objection window on reasonable grounds.
- **Fall-back** — General authorisation against a publicly maintained list, with advance notice and a right of termination without penalty where objections cannot be resolved.
- **Red line** — Blanket authorisation allowing the processor to appoint sub-processors unilaterally, with no notice or objection mechanism.

## 3. Audit and inspection rights

- **Standard** — Right to conduct or commission an independent assessment with reasonable notice, particularly for critical vendors.
- **Fall-back** — Annual SOC 2 Type II report, plus one audit per year on 30 days' notice within a defined scope, preserving an unrestricted right of audit where mandated by a supervisory authority.
- **Red line** — Self-certification only, with no documentary evidence and no carve-out for regulator-mandated audits.

## 4. Data deletion and return at termination

- **Standard** — Certified deletion within 30 days, with written confirmation, expressly covering backups, disaster-recovery copies, and sub-processor-held data.
- **Fall-back** — 30-day export window in standard formats, followed by secure deletion of all copies including backups within a further 60 days.
- **Red line** — Deletion limited to the primary production environment; no certification; indefinite retention for the processor's own purposes (e.g. model training, product analytics).

## 5. Liability for security incidents

- **Standard** — Uncapped liability for breaches of confidentiality, data protection obligations, and regulatory fines attributable to the processor.
- **Fall-back** — Separate "super-cap" for data-protection-related claims, set at a multiple (e.g. 2x–3x) of the general liability cap in the master agreement.
- **Red line** — Data protection liability subsumed within an ordinary 12-month-fee cap, or regulatory fines excluded from the scope of recoverable damages.

## 6. International transfers and data residency

- **Standard** — Explicit enumeration of processing locations and the legal basis for each transfer (SCCs, adequacy decisions, or BCRs), with a documented Transfer Impact Assessment.
- **Fall-back** — Transfers permitted to a defined set of regions (typically EEA plus adequacy countries), with SCCs governing any further transfers.
- **Red line** — General right for the processor to process data in any jurisdiction without specified safeguards or notice.

## 7. Encryption and technical safeguards

- **Standard** — AES-256 (or equivalent) at rest, TLS 1.2 or higher in transit, and controls aligned with SOC 2, ISO 27001, or the NIST Cybersecurity Framework.
- **Fall-back** — Equivalent industry-standard encryption supported by documented technical and organisational measures.
- **Red line** — Vague "commercially reasonable security measures" with no specified standards, certifications, or evidentiary basis.

---

**Sources:** Cyberbase, *What Is Redlining a Contract? The CISO's Complete Guide* (cyberbase.ai); Secure Privacy, *SaaS DPA Guide* (secureprivacy.ai); Venable LLP, *Smoothing Privacy Contracting* (venable.com); Scott & Scott LLP, *Negotiating a Data Processing Agreement Under GDPR*.

> Tier positions reflect common market practice; clause language should be reviewed by qualified counsel before use.
