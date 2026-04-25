type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

export type Severity = "info" | "low" | "medium" | "high" | "blocker";

export type ContractIdentity = {
  contractType?: string;
  vendor: string;
  effectiveDate: string;
  playbookId?: string;
};

export type RulingReference = {
  source?: string;
  citation?: string;
  quote?: string;
  url?: string;
};

export type Suggestion = {
  finding_id: string;
  proposed_text: string;
  rationale: string;
};

export type ReviewFinding = {
  id: string;
  title: string;
  description: string;
  severity: Severity;
  clause_reference?: string | null;
  trigger?: {
    text: string;
    start?: number | null;
    end?: number | null;
  } | null;
  ruling?: RulingReference | null;
  evidence?: RulingReference[];
  requires_escalation: boolean;
};

export type ReviewResponse = {
  contract_id?: string;
  version_id?: string;
  version_number?: number;
  is_new_contract?: boolean;
  agent_name: string;
  summary: string;
  findings: ReviewFinding[];
  suggestions: Suggestion[];
  confidence: number;
  requires_escalation: boolean;
  metadata: Record<string, unknown>;
};

export type ReviewViolation = {
  severity: "High" | "Medium";
  clause: string;
  issue: string;
  reference: string;
  source?: string;
  suggestion: string;
  rationale?: string;
};

export type ReviewAuditResult = {
  contract_summary: string;
  status: "Approved" | "Escalated" | "NeedsRevision";
  escalation_required: boolean;
  escalation_created: boolean;
  can_escalate: boolean;
  violations: ReviewViolation[];
  confidence: number;
  contract_id?: string;
  version_number?: number;
  escalation_id?: string;
  business_status?: string;
  recognized_contract_type?: string;
};

export type LegalQAResponse = {
  summary: string;
  recommendation: string;
  company_basis: RulingReference[];
  legal_basis: RulingReference[];
  escalate: boolean;
};

export type TriggerAnnotation = {
  id: string;
  agent_name: string;
  finding_id: string;
  title?: string;
  description?: string;
  severity: Severity;
  requires_escalation: boolean;
  start?: number | null;
  end?: number | null;
  text?: string | null;
  ruling?: RulingReference | null;
  suggestions: Suggestion[];
};

export type AgentOutput = {
  agent_name: string;
  summary: string;
  findings: ReviewFinding[];
  suggestions: Suggestion[];
  confidence: number;
  requires_escalation: boolean;
  metadata: Record<string, unknown>;
};

export type EscalationStatus = "pending_legal" | "accepted" | "denied";

export type EscalationListItem = {
  id: string;
  ticket_id: string;
  contract_id: string;
  version_id?: string | null;
  version_number?: number | null;
  status: EscalationStatus;
  reason: string;
  highest_severity: Severity;
  source_agents: string[];
  source_finding_ids: string[];
  ai_suggestions: Suggestion[];
  legal_decision?: string | null;
  legal_notes?: string | null;
  fix_suggestions: string[];
  decided_by?: string | null;
  created_at: string;
  updated_at: string;
  decided_at?: string | null;
  next_owner?: string | null;
  timeline: Array<{ event: string; at: string | null }>;
};

export type EscalationDetail = EscalationListItem & {
  review_result: ReviewResponse;
  contract_text: string;
  trigger_annotations: TriggerAnnotation[];
  agent_outputs: AgentOutput[];
};

export type EscalationChatResponse = {
  escalation_id: string;
  question: string;
  answer: string;
  cited_context: Array<Record<string, unknown>>;
};

export type DashboardMetrics = {
  ai_approved?: number;
  escalated?: number;
  average_contract_value_vs_default?: Array<Record<string, unknown>>;
  frequent_playbook_deviations?: string[];
  escalation_metrics?: {
    total_escalations: number;
    pending_escalations: number;
    accepted_escalations: number;
    denied_escalations: number;
    false_escalations: number;
    positive_escalations: number;
    top_false_escalation_agent: Record<string, unknown> | null;
    top_positive_escalation_agent: Record<string, unknown> | null;
    per_agent: Array<Record<string, unknown>>;
  };
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers: isFormData ? undefined : { "Content-Type": "application/json" },
    body: isFormData ? options.body : options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(readErrorMessage(response.status, detail));
  }

  return response.json() as Promise<T>;
}

export function reviewContractText(contractText: string, identity: ContractIdentity) {
  const body: Record<string, unknown> = {
    contract_text: contractText,
    vendor: identity.vendor,
    effective_date: identity.effectiveDate,
  };
  if (identity.contractType?.trim()) {
    body.contract_type = identity.contractType.trim();
  }

  return request<ReviewResponse>("/contracts/review", {
    method: "POST",
    body,
  });
}

export function reviewContractFile(file: File, identity: ContractIdentity) {
  const body = new FormData();
  body.append("file", file);
  body.append("vendor", identity.vendor);
  body.append("effective_date", identity.effectiveDate);
  if (identity.contractType?.trim()) {
    body.append("contract_type", identity.contractType.trim());
  }
  if (identity.playbookId) {
    body.append("playbook_id", identity.playbookId);
  }

  return request<ReviewResponse>("/contracts/review/upload", {
    method: "POST",
    body,
  });
}

export function escalateContractVersion(
  contractId: string,
  versionNumber: number,
  payload: { reason?: string; requested_by?: string } = {},
) {
  return request<EscalationDetail>(`/contracts/${contractId}/versions/${versionNumber}/escalate`, {
    method: "POST",
    body: payload,
  });
}

export function askLegalQuestion(question: string, useCase = "contract_review", contractType = "data_protection") {
  return request<LegalQAResponse>("/legal-qa", {
    method: "POST",
    body: { question, use_case: useCase, contract_type: contractType },
  });
}

export function listEscalations(status?: EscalationStatus) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<{ items: EscalationListItem[] }>(`/escalations${query}`);
}

export function getEscalation(escalationId: string) {
  return request<EscalationDetail>(`/escalations/${escalationId}`);
}

export function askEscalationQuestion(escalationId: string, question: string) {
  return request<EscalationChatResponse>(`/escalations/${escalationId}/chat`, {
    method: "POST",
    body: { question },
  });
}

export function decideEscalation(
  escalationId: string,
  payload: {
    decision: "accepted" | "denied";
    notes?: string;
    fix_suggestions?: string[];
    decided_by?: string;
  },
) {
  return request<EscalationDetail>(`/escalations/${escalationId}/decision`, {
    method: "POST",
    body: payload,
  });
}

export function getDashboardMetrics() {
  return request<DashboardMetrics>("/dashboard/metrics");
}

export function toAuditResult(review: ReviewResponse): ReviewAuditResult {
  const suggestionsByFinding = new Map(review.suggestions.map((suggestion) => [suggestion.finding_id, suggestion]));
  const highestSeverity = review.findings.reduce((highest, finding) => Math.max(highest, severityWeight(finding.severity)), 0);
  const escalationId = typeof review.metadata?.escalation_id === "string" ? review.metadata.escalation_id : undefined;
  const businessStatus = metadataString(review.metadata, "business_status");
  const recognizedContractType = metadataString(review.metadata, "recognized_contract_type");
  const escalationCreated = Boolean(escalationId);
  const canEscalate = review.requires_escalation && Boolean(review.contract_id && review.version_number) && !escalationCreated;
  const violations = review.findings.map((finding) => {
    const suggestion = suggestionsByFinding.get(finding.id);
    return {
      severity: severityWeight(finding.severity) >= severityWeight("high") ? "High" : "Medium",
      clause: finding.trigger?.text || finding.clause_reference || "No exact clause text was recorded.",
      issue: `${finding.title}\n\n${finding.description}`,
      reference: finding.ruling?.citation || finding.id,
      source: finding.ruling?.source,
      suggestion: suggestion?.proposed_text || "Route this issue to the responsible legal reviewer before approval.",
      rationale: suggestion?.rationale,
    } satisfies ReviewViolation;
  });

  return {
    contract_summary: [
      review.summary,
      recognizedContractType ? `Recognized type: ${formatContractType(recognizedContractType)}.` : "",
      review.contract_id ? `Contract ${review.contract_id}` : "",
    ].filter(Boolean).join(" "),
    status: escalationCreated ? "Escalated" : review.findings.length || highestSeverity >= severityWeight("high") ? "NeedsRevision" : "Approved",
    escalation_required: review.requires_escalation,
    escalation_created: escalationCreated,
    can_escalate: canEscalate,
    violations,
    confidence: review.confidence,
    contract_id: review.contract_id,
    version_number: review.version_number,
    escalation_id: escalationId,
    business_status: businessStatus,
    recognized_contract_type: recognizedContractType,
  };
}

export function formatLegalAnswer(response: LegalQAResponse) {
  const lines = [
    `### Summary\n${response.summary}`,
    `### Recommendation\n${response.recommendation}`,
  ];

  if (response.company_basis.length) {
    lines.push(`### BMW Basis\n${formatBasis(response.company_basis)}`);
  }
  if (response.legal_basis.length) {
    lines.push(`### Legal Evidence\n${formatBasis(response.legal_basis)}`);
  }
  if (response.escalate) {
    lines.push("### Escalation\nThis question should be escalated to legal counsel before the business team proceeds.");
  }

  return lines.join("\n\n");
}

function formatBasis(items: RulingReference[]) {
  return items
    .map((item) => {
      const heading = [item.source, item.citation].filter(Boolean).join(" - ");
      const quote = item.quote ? `\n> ${item.quote}` : "";
      return `- **${heading || "Evidence"}**${quote}`;
    })
    .join("\n");
}

function severityWeight(severity: Severity) {
  const weights: Record<Severity, number> = {
    info: 0,
    low: 1,
    medium: 2,
    high: 3,
    blocker: 4,
  };
  return weights[severity];
}

function metadataString(metadata: Record<string, unknown>, key: string) {
  const value = metadata[key];
  return typeof value === "string" ? value : undefined;
}

function formatContractType(contractType: string) {
  return contractType.replace(/_/g, " ");
}

function readErrorMessage(status: number, body: string) {
  if (!body) {
    return `Request failed with status ${status}`;
  }

  try {
    const parsed = JSON.parse(body);
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (Array.isArray(parsed.detail)) {
      return parsed.detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ");
    }
  } catch {
    return `Request failed with status ${status}`;
  }

  return `Request failed with status ${status}`;
}
