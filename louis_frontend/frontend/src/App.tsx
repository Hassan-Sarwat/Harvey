import {
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Database,
  ExternalLink,
  FileSearch,
  FileText,
  FolderOpen,
  Gauge,
  Gavel,
  LayoutDashboard,
  Loader2,
  Menu,
  MessageSquareText,
  Play,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Users
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { analyzeMatter, getConfig, getDashboard, runDemo } from "./api";
import type { AgentStep, AppConfig, ConfigItem, DashboardMetrics, Finding, RunResult } from "./types";

const emptyConfig: AppConfig = {
  app_name: "BMW Legal Agent Platform",
  workflow_name: "Contract Intake Copilot",
  demo_question: "Can I proceed with this IT vendor DPA, or do I need to escalate it to Legal?",
  demo_context: "",
  sources: [],
  agents: [],
  default_sources: [],
  default_agents: []
};

const optimisticSteps: AgentStep[] = [
  {
    id: "intake",
    label: "Intake classification",
    agent: "Legal Intake Manager",
    status: "running",
    summary: "Classifying the request and selecting specialist checks.",
    detail: "The manager keeps ownership of the final answer.",
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString()
  },
  {
    id: "parsing",
    label: "File parsing",
    agent: "Document Extraction Tool",
    status: "queued",
    summary: "Extracting contract, DPA, annex, email, and spreadsheet text.",
    detail: "Supports PDF, DOCX, XLSX, PPTX, TXT, CSV, EML, and ZIP bundles.",
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString()
  },
  {
    id: "completeness",
    label: "Completeness check",
    agent: "Completeness Agent",
    status: "queued",
    summary: "Looking for missing TOMs, annexes, SCCs, side letters, and amendments.",
    detail: "",
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString()
  },
  {
    id: "playbook",
    label: "DPA playbook review",
    agent: "DPA Playbook Agent",
    status: "queued",
    summary: "Comparing clauses against BMW-style green/yellow/red positions.",
    detail: "",
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString()
  },
  {
    id: "judge",
    label: "Escalation judgment",
    agent: "Escalation Judge Agent",
    status: "queued",
    summary: "Deciding whether Legal should be involved before signature.",
    detail: "",
    started_at: new Date().toISOString(),
    completed_at: new Date().toISOString()
  }
];

const mockMatterSummary = {
  agreement_type: "IT vendor SaaS agreement / DPA",
  counterparty: "Nimbus Analytics Ltd.",
  governing_law: "EU GDPR / German data protection",
  contract_value: "Estimated €45,000 pilot",
  personal_data: true,
  uploaded_documents: 4,
  missing_documents: ["Annex 2 - TOMs", "Subprocessor list", "SCCs"]
};

const mockFindings: Finding[] = [
  {
    id: "MOCK-COMPLETE-001",
    title: "DPA package likely incomplete",
    category: "Completeness",
    severity: "High",
    band: "redline",
    description: "The intake context suggests employee usage data, so the bundle should include a DPA, TOMs, subprocessors, and transfer safeguards.",
    recommendation: "Request the full DPA package before Legal review.",
    evidence: [],
    confidence: 0.76
  },
  {
    id: "MOCK-DPA-001",
    title: "Personal data processing likely triggers Privacy review",
    category: "Data protection",
    severity: "Medium",
    band: "fallback",
    description: "Employee usage data and support tickets usually include personal data and may require BMW Privacy/Legal review.",
    recommendation: "Run the DPA Playbook Agent and Otto Schmidt research before approval.",
    evidence: [],
    confidence: 0.72
  },
  {
    id: "MOCK-DOA-001",
    title: "Vendor paper should be routed through Purchasing",
    category: "Delegation of authority",
    severity: "Medium",
    band: "fallback",
    description: "The vendor appears to have sent its own paper, which is usually not a standard self-approval path.",
    recommendation: "Assign a Purchasing owner and keep Legal escalation available.",
    evidence: [],
    confidence: 0.7
  }
];

const mockLegalSources = [
  {
    title: "GDPR Art. 28 - processor agreement",
    source: "Otto Schmidt / Legal Data Hub target",
    excerpt: "Processor arrangements should set out processing subject matter, duration, categories of data, data subjects, and processor obligations.",
    url: "https://gdpr.eu/article-28-processor/",
    confidence: 0.7
  },
  {
    title: "GDPR Art. 32 - security of processing",
    source: "Otto Schmidt / Legal Data Hub target",
    excerpt: "Security measures should be appropriate to the risk and are commonly documented in TOMs or an equivalent security annex.",
    url: "https://gdpr.eu/article-32-security-of-processing/",
    confidence: 0.68
  },
  {
    title: "International transfer safeguards",
    source: "Otto Schmidt / Legal Data Hub target",
    excerpt: "Third-country transfers may require SCCs, adequacy analysis, and additional safeguards depending on the destination and processing setup.",
    url: "https://commission.europa.eu/law/law-topic/data-protection/international-dimension-data-protection/standard-contractual-clauses-scc_en",
    confidence: 0.66
  }
];

function applyAutoRoutingFallback(result: RunResult, wasAutoMode: boolean): RunResult {
  if (!wasAutoMode || result.agent_routing_mode) return result;
  const routedAgents = result.routed_agents?.length ? result.routed_agents : result.selected_agents;
  return {
    ...result,
    agent_routing_mode: "auto",
    routed_agents: routedAgents,
    routing_summary: "Auto Mode routed this run from the submitted matter."
  };
}

function App() {
  const [config, setConfig] = useState<AppConfig>(emptyConfig);
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null);
  const [activeView, setActiveView] = useState<"intake" | "dashboard" | "playbook">("intake");
  const [question, setQuestion] = useState(emptyConfig.demo_question);
  const [context, setContext] = useState("");
  const [sources, setSources] = useState<string[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then((loaded) => {
        setConfig(loaded);
        setQuestion(loaded.demo_question);
        setContext(loaded.demo_context);
        setSources(loaded.default_sources);
        setAgents([]);
      })
      .catch((err) => setError(err.message));
    getDashboard().then(setDashboard).catch(() => undefined);
  }, []);

  const steps = isRunning ? optimisticSteps : result?.agent_steps ?? [];
  const selectedSourceItems = useMemo(() => config.sources.filter((item) => sources.includes(item.id)), [config.sources, sources]);
  const selectedAgentItems = useMemo(() => config.agents.filter((item) => agents.includes(item.id)), [config.agents, agents]);
  const agentLabelsById = useMemo(() => Object.fromEntries(config.agents.map((item) => [item.id, item.label])), [config.agents]);
  const routedAgentItems = useMemo(
    () => config.agents.filter((item) => (result?.routed_agents ?? []).includes(item.id)),
    [config.agents, result?.routed_agents]
  );

  async function handleAnalyze(demoMode = false) {
    setIsRunning(true);
    setError(null);
    try {
      const wasAutoMode = !demoMode && agents.length === 0;
      const next = demoMode
        ? await runDemo()
        : await analyzeMatter({ question, context, sources, agents, files, demoMode: false });
      setResult(applyAutoRoutingFallback(next, wasAutoMode));
      setActiveView("intake");
      getDashboard().then(setDashboard).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setIsRunning(false);
    }
  }

  function toggle(list: string[], value: string, setter: (next: string[]) => void) {
    setter(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  return (
    <div className="app-shell">
      <Sidebar activeView={activeView} onChange={setActiveView} />
      <main className="main">
        <Topbar />
        {activeView === "dashboard" ? (
          <DashboardView dashboard={dashboard} />
        ) : activeView === "playbook" ? (
          <PlaybookView />
        ) : (
          <IntakeView
            config={config}
            question={question}
            context={context}
            sources={sources}
            agents={agents}
            selectedSourceItems={selectedSourceItems}
            selectedAgentItems={selectedAgentItems}
            routedAgentItems={routedAgentItems}
            agentLabelsById={agentLabelsById}
            files={files}
            result={result}
            steps={steps}
            isRunning={isRunning}
            error={error}
            setQuestion={setQuestion}
            setContext={setContext}
            setFiles={setFiles}
            toggleSource={(id) => toggle(sources, id, setSources)}
            toggleAgent={(id) => toggle(agents, id, setAgents)}
            selectAutoAgents={() => setAgents([])}
            onAnalyze={() => handleAnalyze(false)}
            onDemo={() => handleAnalyze(true)}
          />
        )}
      </main>
    </div>
  );
}

function Sidebar({ activeView, onChange }: { activeView: string; onChange: (view: "intake" | "dashboard" | "playbook") => void }) {
  const nav = [
    { id: "intake", label: "Ask & Intake", icon: MessageSquareText },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "playbook", label: "Playbooks", icon: BookOpen }
  ] as const;
  const muted = [
    { label: "Escalations", icon: AlertTriangle, badge: "3" },
    { label: "Legal Research", icon: Search },
    { label: "Matter Archive", icon: Database }
  ];
  const admin = [
    { label: "Settings", icon: Settings }
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">B</div>
        <div>
          <strong>BMW LEGAL</strong>
          <span>Agent Platform</span>
        </div>
      </div>
      <nav className="nav">
        <span className="nav-section">Primary</span>
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.id} className={activeView === item.id ? "nav-item active" : "nav-item"} onClick={() => onChange(item.id)}>
              <Icon size={19} />
              <span>{item.label}</span>
            </button>
          );
        })}
        <div className="nav-divider" />
        <span className="nav-section">Workspace</span>
        {muted.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.label} className="nav-item muted">
              <Icon size={19} />
              <span>{item.label}</span>
              {item.badge ? <b>{item.badge}</b> : null}
            </button>
          );
        })}
        <div className="nav-divider" />
        <span className="nav-section">Admin</span>
        {admin.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.label} className="nav-item muted">
              <Icon size={19} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <ShieldCheck size={18} />
        <div>
          <strong>Governance mode</strong>
          <span>Traceable agent runs</span>
          <a>View audit log <ChevronRight size={14} /></a>
        </div>
      </div>
    </aside>
  );
}

function Topbar() {
  return (
    <header className="topbar">
      <button className="icon-button" aria-label="Open menu">
        <Menu size={24} />
      </button>
      <div className="searchbox">
        <Search size={18} />
        <span>Search matters, clauses, playbooks, legal sources...</span>
        <kbd>⌘K</kbd>
      </div>
      <div className="topbar-actions">
        <span className="status-pill secure"><ShieldCheck size={16} />Demo-safe cache enabled</span>
        <button className="icon-button" aria-label="Notifications">
          <Bell size={20} />
        </button>
        <div className="avatar">PS</div>
        <ChevronDown size={18} />
      </div>
    </header>
  );
}

function IntakeView(props: {
  config: AppConfig;
  question: string;
  context: string;
  sources: string[];
  agents: string[];
  selectedSourceItems: ConfigItem[];
  selectedAgentItems: ConfigItem[];
  routedAgentItems: ConfigItem[];
  agentLabelsById: Record<string, string>;
  files: File[];
  result: RunResult | null;
  steps: AgentStep[];
  isRunning: boolean;
  error: string | null;
  setQuestion: (value: string) => void;
  setContext: (value: string) => void;
  setFiles: (files: File[]) => void;
  toggleSource: (id: string) => void;
  toggleAgent: (id: string) => void;
  selectAutoAgents: () => void;
  onAnalyze: () => void;
  onDemo: () => void;
}) {
  return (
    <div className="workspace">
      <section className="center-pane">
        <div className="page-title">
          <div>
            <p className="eyebrow">Contract Intake Copilot</p>
            <h1>Ask a legal routing question and let the right agents take it.</h1>
          </div>
          <button className="secondary-button" onClick={props.onDemo} disabled={props.isRunning}>
            <Play size={17} />
            Run demo matter
          </button>
        </div>

        <div className="question-card">
          <label>Question</label>
          <div className="field-shell">
            <textarea value={props.question} onChange={(event) => props.setQuestion(event.target.value)} rows={3} maxLength={500} />
            <span>{props.question.length}/500</span>
          </div>
          <label>Business context</label>
          <div className="field-shell">
            <textarea value={props.context} onChange={(event) => props.setContext(event.target.value)} rows={4} maxLength={1000} />
            <span>{props.context.length}/1000</span>
          </div>
          <div className="selector-grid">
            <Selector title="Sources" icon={<Database size={18} />} items={props.config.sources} selected={props.sources} onToggle={props.toggleSource} />
            <AgentSelector
              items={props.config.agents}
              selected={props.agents}
              routedItems={props.routedAgentItems}
              routingMode={props.result?.agent_routing_mode}
              onToggle={props.toggleAgent}
              onAutoSelect={props.selectAutoAgents}
            />
          </div>
          <UploadBox files={props.files} setFiles={props.setFiles} />
          <div className="action-row">
            <div className="mini-stack">
              <span><FileText size={17} />{props.selectedSourceItems.length} source groups</span>
              <span><Users size={17} />{props.agents.length ? `${props.selectedAgentItems.length} agents selected` : "Auto routing"}</span>
            </div>
            <button className="primary-button" onClick={props.onAnalyze} disabled={props.isRunning}>
              {props.isRunning ? <Loader2 className="spin" size={18} /> : <FileSearch size={18} />}
              Run legal intake
            </button>
          </div>
          {props.error ? <div className="error-box">{props.error}</div> : null}
        </div>

        <AgentTimeline steps={props.steps} isRunning={props.isRunning} />
        {props.result ? <ResultPanel result={props.result} agentLabelsById={props.agentLabelsById} /> : <EmptyState />}
      </section>

      <aside className="right-pane">
        <MatterPanel result={props.result} />
        <FlagsPanel findings={props.result?.findings ?? mockFindings} isMock={!props.result} />
        <SourcesPanel result={props.result} />
      </aside>
    </div>
  );
}

function Selector({ title, icon, items, selected, onToggle }: { title: string; icon: ReactNode; items: ConfigItem[]; selected: string[]; onToggle: (id: string) => void }) {
  return (
    <div className="selector">
      <div className="selector-title">
        {icon}
        <span>{title}</span>
      </div>
      <div className="chips">
        {items.map((item) => (
          <button key={item.id} className={selected.includes(item.id) ? "chip selected" : "chip"} onClick={() => onToggle(item.id)} title={item.description}>
            {item.label}
            {selected.includes(item.id) ? <CheckCircle2 size={13} /> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function AgentSelector({
  items,
  selected,
  routedItems,
  routingMode,
  onToggle,
  onAutoSelect
}: {
  items: ConfigItem[];
  selected: string[];
  routedItems: ConfigItem[];
  routingMode?: "auto" | "manual";
  onToggle: (id: string) => void;
  onAutoSelect: () => void;
}) {
  const autoMode = selected.length === 0;
  return (
    <div className="selector agent-selector">
      <div className="selector-title">
        <BrainCircuit size={18} />
        <span>Agents</span>
      </div>
      <button className={autoMode ? "auto-route-card selected" : "auto-route-card"} onClick={onAutoSelect} title="Auto Mode">
        <span>
          <Sparkles size={17} />
          Auto Mode
        </span>
        <small>Smart legal routing</small>
        {autoMode ? <CheckCircle2 size={16} /> : null}
      </button>
      {routingMode === "auto" && routedItems.length ? (
        <div className="route-result">
          <span>Selected by Auto</span>
          <strong>{routedItems.map((item) => item.label).join(", ")}</strong>
        </div>
      ) : null}
      <div className="chips">
        {items.map((item) => (
          <button key={item.id} className={selected.includes(item.id) ? "chip selected" : "chip"} onClick={() => onToggle(item.id)} title={item.description}>
            {item.label}
            {selected.includes(item.id) ? <CheckCircle2 size={13} /> : null}
          </button>
        ))}
      </div>
    </div>
  );
}

function UploadBox({ files, setFiles }: { files: File[]; setFiles: (files: File[]) => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const addFiles = (incoming: File[]) => {
    const merged = [...files];
    const seen = new Set(merged.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
    incoming.forEach((file) => {
      const key = `${file.name}-${file.size}-${file.lastModified}`;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(file);
      }
    });
    setFiles(merged);
  };

  return (
    <div
      className={isDragging ? "upload-box dragging" : "upload-box"}
      onDragEnter={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "copy";
        setIsDragging(true);
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDragging(false);
        addFiles(Array.from(event.dataTransfer.files ?? []));
      }}
    >
      <UploadCloud size={24} />
      <div>
        <strong>{isDragging ? "Drop files to attach them" : "Upload contract bundle"}</strong>
        <span>Drag files here or browse: PDF, DOCX, XLSX, PPTX, TXT, CSV, EML, ZIP</span>
      </div>
      <label className="file-button">
        <FolderOpen size={17} />
        Browse files
        <input
          type="file"
          multiple
          onChange={(event) => addFiles(Array.from(event.target.files ?? []))}
          accept=".pdf,.docx,.xlsx,.pptx,.txt,.csv,.eml,.zip,.md"
        />
      </label>
      {files.length ? (
        <div className="file-list">
          {files.map((file) => (
            <span key={`${file.name}-${file.size}`}>
              <FileText size={14} />
              {file.name}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AgentTimeline({ steps, isRunning }: { steps: AgentStep[]; isRunning: boolean }) {
  if (!steps.length) return null;
  return (
    <section className="timeline-card">
      <div className="section-head">
        <div>
          <p className="eyebrow">Agent orchestration</p>
          <h2>Visible workflow</h2>
        </div>
        {isRunning ? <span className="status-pill blue">Running</span> : <span className="status-pill">Trace saved</span>}
      </div>
      <div className="timeline">
        {steps.map((step, index) => (
          <div key={step.id} className="timeline-step">
            <div className={step.status === "running" ? "step-dot running" : "step-dot"}>
              {step.status === "running" ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
            </div>
            <div>
              <span className="step-index">{String(index + 1).padStart(2, "0")} / {step.agent}</span>
              <strong>{step.label}</strong>
              <p>{step.summary}</p>
              {step.detail ? <small>{step.detail}</small> : null}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultPanel({ result, agentLabelsById }: { result: RunResult; agentLabelsById: Record<string, string> }) {
  const routingMode = result.agent_routing_mode ?? "manual";
  const routedLabels = (result.routed_agents ?? []).map((agentId) => agentLabelsById[agentId] ?? agentId);
  return (
    <section className="result-card">
      <div className="section-head">
        <div>
          <p className="eyebrow">Recommendation</p>
          <h2>{result.escalation_state}</h2>
        </div>
        <div className="result-badges">
          <span className={routingMode === "auto" ? "status-pill blue" : "status-pill"}>
            <Sparkles size={14} />
            {routingMode === "auto" ? "Auto-routed" : "Manual route"}
          </span>
          <Confidence value={result.confidence} />
        </div>
      </div>
      {routedLabels.length ? (
        <div className="routing-banner">
          <BrainCircuit size={18} />
          <div>
            <span>{routingMode === "auto" ? "Auto selected" : "Selected agents"}</span>
            <strong>{routedLabels.join(", ")}</strong>
          </div>
        </div>
      ) : null}
      <p className="answer">{result.plain_answer}</p>
      <div className="answer-grid">
        <div>
          <h3>Why it matters</h3>
          <p>{result.legal_answer}</p>
        </div>
        <div>
          <h3>Next action</h3>
          <p>{result.next_action}</p>
        </div>
      </div>
      <div className="suggested-language">
        <div className="suggestion-title">
          <ClipboardCheck size={18} />
          <span>Suggested fallback language</span>
        </div>
        <pre>{result.suggested_language}</pre>
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <section className="empty-state">
      <Sparkles size={27} />
      <div>
        <strong>Best-guess intake preview</strong>
        <p>Likely route: DPA/privacy review recommended before approval. Run the agents to replace these assumptions with a traceable decision.</p>
      </div>
    </section>
  );
}

function MatterPanel({ result }: { result: RunResult | null }) {
  const summary = result?.matter_summary ?? mockMatterSummary;
  return (
    <section className="side-card">
      <div className="section-head compact">
        <h2>Matter summary</h2>
        <span className="linkish">Edit</span>
      </div>
      <div className="summary-grid">
        <SummaryItem icon={<FileText size={18} />} label="Agreement" value={summary.agreement_type} />
        <SummaryItem icon={<Users size={18} />} label="Counterparty" value={summary.counterparty} />
        <SummaryItem icon={<Gavel size={18} />} label="Law focus" value={summary.governing_law} />
        <SummaryItem icon={<Gauge size={18} />} label="Value" value={summary.contract_value} />
      </div>
      <div className="summary-footer">
        <span>{summary.uploaded_documents} document(s) expected</span>
        <span>{summary.personal_data ? "Personal data likely" : "Personal data not confirmed"}</span>
      </div>
    </section>
  );
}

function SummaryItem({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="summary-item">
      {icon}
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function FlagsPanel({ findings, isMock = false }: { findings: Finding[]; isMock?: boolean }) {
  const grouped = useMemo(() => {
    const groups: Record<string, Finding[]> = {};
    findings.forEach((finding) => {
      groups[finding.category] = groups[finding.category] || [];
      groups[finding.category].push(finding);
    });
    return Object.entries(groups);
  }, [findings]);

  return (
    <section className="side-card">
      <div className="section-head compact">
        <h2>Review flags</h2>
        <span className="counter">{findings.length} {isMock ? "likely" : ""} issues</span>
      </div>
      <div className="flag-list">
        {grouped.length ? (
          grouped.map(([category, items]) => (
            <div className="flag-group" key={category}>
              <div className="flag-group-title">
                <AlertTriangle size={17} />
                <strong>{category}</strong>
                <span>{items.length}</span>
              </div>
              {items.map((finding) => (
                <div className="flag-item" key={finding.id}>
                  <div>
                    <strong>{finding.title}</strong>
                    <p>{finding.description}</p>
                  </div>
                  <Band band={finding.band} severity={finding.severity} />
                </div>
              ))}
            </div>
          ))
        ) : (
          <div className="quiet-box">No findings yet.</div>
        )}
      </div>
    </section>
  );
}

function SourcesPanel({ result }: { result: RunResult | null }) {
  const sources = result?.legal_sources ?? mockLegalSources;
  return (
    <section className="side-card">
      <div className="section-head compact">
        <h2>Legal sources</h2>
      </div>
      <div className="source-list">
        {sources.slice(0, 3).map((source) => (
          <a href={source.url || "#"} target="_blank" rel="noreferrer" className="source-item" key={source.title}>
            <BookOpen size={16} />
            <div>
              <strong>{source.title}</strong>
              <p>{source.excerpt}</p>
              <span>{source.source}</span>
            </div>
          </a>
        ))}
        {!result ? <div className="quiet-box source-empty"><p>These are best-guess source targets. The Otto Schmidt agent will replace them with run-specific citations.</p><a>Go to Legal Data Hub <ExternalLink size={14} /></a></div> : null}
      </div>
    </section>
  );
}

function DashboardView({ dashboard }: { dashboard: DashboardMetrics | null }) {
  return (
    <div className="dashboard-view">
      <div className="page-title">
        <div>
          <p className="eyebrow">Performance dashboard</p>
          <h1>AI intake performance and playbook drift.</h1>
        </div>
      </div>
      <div className="metric-grid">
        <Metric icon={<BarChart3 />} label="Total matters" value={dashboard?.total_runs ?? 0} />
        <Metric icon={<CheckCircle2 />} label="No escalation" value={dashboard?.auto_cleared ?? 0} />
        <Metric icon={<AlertTriangle />} label="Legal recommended" value={dashboard?.legal_recommended ?? 0} />
        <Metric icon={<Gavel />} label="Legal required" value={dashboard?.legal_required ?? 0} />
      </div>
      <div className="dashboard-grid">
        <section className="timeline-card">
          <div className="section-head">
            <h2>Playbook positions</h2>
          </div>
          <div className="bars">
            {(dashboard?.playbook_deviations ?? []).map((item) => (
              <div className="bar-row" key={item.label}>
                <span>{item.label}</span>
                <div className="bar-track">
                  <div className={`bar-fill ${item.color}`} style={{ width: `${Math.min(100, item.value * 18 + 8)}%` }} />
                </div>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="timeline-card">
          <div className="section-head">
            <h2>Top escalation triggers</h2>
            <span className="status-pill">{dashboard?.missing_docs_rate ?? 0}% missing-doc rate</span>
          </div>
          <div className="trigger-list">
            {(dashboard?.top_triggers ?? []).map((item) => (
              <div key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
            {!dashboard?.top_triggers.length ? <div className="quiet-box">Run an intake to populate metrics.</div> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <section className="metric-card">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function PlaybookView() {
  const rows = [
    ["DPA required", "Signed DPA before processing", "DPA requested before go-live", "Processing without DPA"],
    ["Breach notice", "24 hours", "Without undue delay, max 48 hours", "72 hours or no clear deadline"],
    ["Subprocessors", "Prior written approval", "Notice plus objection right", "No notice or unrestricted changes"],
    ["Transfers", "EEA or SCCs plus TIA", "Safeguards under review", "Unrestricted global transfers"],
    ["TOMs", "TOMs attached", "Security whitepaper for intake", "No security annex"]
  ];
  return (
    <div className="playbook-view">
      <div className="page-title">
        <div>
          <p className="eyebrow">BMW-style mock playbook</p>
          <h1>Clear positions for what to accept, where to bend, and where to stop.</h1>
        </div>
      </div>
      <section className="timeline-card">
        <div className="playbook-legend">
          <span><i className="legend-dot green" /> Standard position</span>
          <span><i className="legend-dot yellow" /> Fallback</span>
          <span><i className="legend-dot red" /> Red line</span>
        </div>
        <div className="playbook-table">
          {rows.map((row) => (
            <div className="playbook-row" key={row[0]}>
              <strong>{row[0]}</strong>
              <span>{row[1]}</span>
              <span>{row[2]}</span>
              <span>{row[3]}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Confidence({ value }: { value: number }) {
  return <span className="confidence">{Math.round(value * 100)}% confidence</span>;
}

function Band({ band, severity }: { band: Finding["band"]; severity: Finding["severity"] }) {
  return <span className={`band ${band}`}>{band === "redline" ? "Red line" : band === "fallback" ? "Fallback" : "Standard"} / {severity}</span>;
}

export default App;
