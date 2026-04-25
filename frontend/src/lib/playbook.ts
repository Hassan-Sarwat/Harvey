// Tooltip definitions for rule citations returned by the AI.
export const RULE_LIBRARY: Record<string, { title: string; body: string; source: "Playbook" | "Statute" }> = {
  "P-01": { source: "Playbook", title: "Four-Eyes Principle", body: "Dual signatures mandatory for any DPA above €500,000 contract value." },
  "P-02": { source: "Playbook", title: "Board Approval Threshold", body: "Contracts above €5,000,000 annual value require Board of Management approval." },
  "P-03": { source: "Playbook", title: "Liability Cap", body: "Processor liability cap must not be lower than 100% of annual contract value." },
  "P-04": { source: "Playbook", title: "Sub-Processor Consent", body: "Prior written consent and 30-day objection period required for new sub-processors." },
  "P-05": { source: "Playbook", title: "Audit Rights", body: "BMW must retain on-site audit rights with maximum 30 days notice." },
  "P-06": { source: "Playbook", title: "Data Location", body: "Personal data must remain in EU/EEA unless adequacy decision or BMW-approved SCCs apply." },
  "P-07": { source: "Playbook", title: "Retention", body: "Data must be returned or deleted within 30 days of contract termination." },
  "P-08": { source: "Playbook", title: "Insurance", body: "Processor must maintain cyber liability insurance ≥ €10M." },
  "L-01": { source: "Statute", title: "Art. 28(3) GDPR", body: "DPA must specify subject-matter, duration, nature/purpose, type of personal data and obligations." },
  "L-02": { source: "Statute", title: "Art. 33 GDPR", body: "Breach notification without undue delay — interpreted as 24h max for BMW Group." },
  "L-03": { source: "Statute", title: "Art. 32 GDPR", body: "Technical and organisational measures must be specified — encryption, access controls, testing." },
  "L-04": { source: "Statute", title: "Art. 28(2) GDPR", body: "No sub-processor without prior written authorisation of the controller." },
  "L-05": { source: "Statute", title: "Art. 44–49 GDPR", body: "International transfers require appropriate safeguards (SCCs, adequacy, BCRs)." },
  "L-06": { source: "Statute", title: "§ 26 BDSG", body: "Special rules for employee data processing under German federal law." },
  "L-07": { source: "Statute", title: "Art. 82 GDPR", body: "Joint and several liability for damages — limiting clauses are void." },
};

export function lookupRule(reference: string) {
  const match = reference.match(/(P-\d{2}|L-\d{2})/);
  if (!match) return null;
  return { id: match[1], ...RULE_LIBRARY[match[1]] };
}