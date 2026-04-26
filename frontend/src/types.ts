export type EscalationState =
  | "Needs business input"
  | "No legal escalation recommended"
  | "Legal review recommended"
  | "Legal review required before signature";

export type ConfigItem = {
  id: string;
  label: string;
  description: string;
};

export type AppConfig = {
  app_name: string;
  workflow_name: string;
  demo_question: string;
  demo_context: string;
  sources: ConfigItem[];
  agents: ConfigItem[];
  default_sources: string[];
  default_agents: string[];
};

export type Evidence = {
  source_type: string;
  title: string;
  quote: string;
  locator?: string;
  url?: string;
};

export type Finding = {
  id: string;
  title: string;
  category: string;
  severity: "Low" | "Medium" | "High";
  band: "standard" | "fallback" | "redline";
  description: string;
  recommendation: string;
  evidence: Evidence[];
  confidence: number;
};

export type AgentStep = {
  id: string;
  label: string;
  agent: string;
  status: string;
  summary: string;
  detail: string;
  started_at: string;
  completed_at: string;
};

export type MatterSummary = {
  agreement_type: string;
  counterparty: string;
  governing_law: string;
  contract_value: string;
  personal_data: boolean;
  uploaded_documents: number;
  missing_documents: string[];
};

export type LegalSource = {
  title: string;
  source: string;
  excerpt: string;
  url?: string;
  confidence: number;
  retrieval_mode?: "live" | "fallback" | string;
  fallback_reason?: string;
};

export type AskMode = "general_question" | "contract_review";

export type SourceUsage = {
  id: string;
  label: string;
  description: string;
  item_count: number;
  items: Array<{
    title?: string;
    source?: string;
    excerpt?: string;
    url?: string;
    fallback?: boolean;
    fallback_reason?: string;
  }>;
};

export type RunResult = {
  id: string;
  created_at: string;
  mode?: AskMode;
  question: string;
  context: string;
  selected_sources: string[];
  selected_agents: string[];
  agent_routing_mode: "auto" | "manual";
  routed_agents: string[];
  routing_summary: string;
  escalation_state: EscalationState;
  confidence: number;
  plain_answer: string;
  legal_answer: string;
  next_action: string;
  matter_summary: MatterSummary;
  agent_steps: AgentStep[];
  findings: Finding[];
  legal_sources: LegalSource[];
  source_usage?: SourceUsage[];
  suggested_language: string;
  history_thread_id?: string;
  contract_id?: string | null;
  contract_status?: "approved" | "pending_legal" | "needs_business_input" | "dropped" | null;
  is_final_version?: boolean;
  escalation_id?: string | null;
  metrics: Record<string, number | string | boolean>;
};

export type HistorySummary = {
  id: string;
  title: string;
  mode: AskMode;
  item_type: "chat" | "contract";
  contract_status?: "approved" | "pending_legal" | "needs_business_input" | "dropped" | null;
  contract_id?: string | null;
  version_id?: string | null;
  version_number?: number | null;
  escalation_id?: string | null;
  contract_type?: string | null;
  counterparty?: string | null;
  created_at: string;
  updated_at: string;
};

export type HistoryMessage = {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type HistoryRun = {
  id: string;
  mode: AskMode;
  reply: string;
  reasoning: Record<string, unknown>;
  sources_used: SourceUsage[];
  routed_agents: string[];
  findings: Finding[];
  result: RunResult;
  created_at: string;
};

export type HistoryEvent = {
  id: string;
  actor: string;
  event_type: string;
  summary: string;
  status?: "approved" | "pending_legal" | "needs_business_input" | "dropped" | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type HistoryDetail = HistorySummary & {
  messages: HistoryMessage[];
  runs: HistoryRun[];
  events: HistoryEvent[];
};

// ---- Escalations ----

export type EscalationStatus = "pending_legal" | "accepted" | "denied";

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
  fix_suggestions: string[];
  created_at: string;
  updated_at: string;
  decided_at?: string | null;
  next_owner?: string | null;
  legal_notes?: string | null;
  timeline: Array<{ event: string; at: string | null }>;
};

export type EscalationDetail = EscalationListItem & {
  review_result: RunResult;
  contract_text: string;
  trigger_annotations: TriggerAnnotation[];
  agent_outputs: unknown[];
};

export type AgentMetric = {
  agent_name: string;
  total: number;
  pending: number;
  accepted: number;
  denied: number;
  false_escalation_rate: number;
};

export type DashboardMetrics = {
  total_runs: number;
  auto_cleared: number;
  legal_recommended: number;
  legal_required: number;
  missing_docs_rate: number;
  top_triggers: Array<{ label: string; value: number }>;
  playbook_deviations: Array<{ label: string; value: number; color: string }>;
  per_agent_metrics?: AgentMetric[];
  top_false_escalation_agent?: { agent_name: string; false_escalations: number } | null;
  top_positive_escalation_agent?: { agent_name: string; positive_escalations: number } | null;
  recent_runs: Array<{
    id: string;
    question: string;
    created_at: string;
    state: EscalationState;
    confidence: number;
    findings: number;
  }>;
};
