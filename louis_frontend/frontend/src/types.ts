export type EscalationState =
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
};

export type RunResult = {
  id: string;
  created_at: string;
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
  suggested_language: string;
  metrics: Record<string, number | string | boolean>;
};

export type DashboardMetrics = {
  total_runs: number;
  auto_cleared: number;
  legal_recommended: number;
  legal_required: number;
  missing_docs_rate: number;
  top_triggers: Array<{ label: string; value: number }>;
  playbook_deviations: Array<{ label: string; value: number; color: string }>;
  recent_runs: Array<{
    id: string;
    question: string;
    created_at: string;
    state: EscalationState;
    confidence: number;
    findings: number;
  }>;
};
