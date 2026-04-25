type RequestOptions = {
  method?: "GET" | "POST";
  body?: unknown;
};

export type Severity = "info" | "low" | "medium" | "high" | "blocker";

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
  findings: Array<Record<string, unknown>>;
  suggestions: Suggestion[];
  confidence: number;
  requires_escalation: boolean;
  metadata: Record<string, unknown>;
};

export type EscalationListItem = {
  id: string;
  contract_id: string;
  version_id?: string | null;
  version_number?: number | null;
  status: "pending_legal" | "accepted" | "denied";
  reason: string;
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
  review_result: Record<string, unknown>;
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

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? "GET",
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function reviewContract(contractText: string, contractType: string) {
  return request<Record<string, unknown>>("/contracts/demo-contract-1/review", {
    method: "POST",
    body: { contract_text: contractText, contract_type: contractType }
  });
}

export function askLegalQuestion(question: string, useCase: string, contractType: string) {
  return request<Record<string, unknown>>("/legal-qa", {
    method: "POST",
    body: { question, use_case: useCase, contract_type: contractType }
  });
}

export function listEscalations() {
  return request<{ items: EscalationListItem[] }>("/escalations");
}

export function getEscalation(escalationId: string) {
  return request<EscalationDetail>(`/escalations/${escalationId}`);
}

export function askEscalationQuestion(escalationId: string, question: string) {
  return request<EscalationChatResponse>(`/escalations/${escalationId}/chat`, {
    method: "POST",
    body: { question }
  });
}

export function getDashboardMetrics() {
  return request<Record<string, unknown>>("/dashboard/metrics");
}
