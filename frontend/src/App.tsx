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
  History as HistoryIcon,
  LayoutDashboard,
  Loader2,
  Menu,
  MessageSquareText,
  Play,
  Send,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Users
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { analyzeMatter, dropHistoryItem, getConfig, getDashboard, getHistory, getHistoryItem, runDemo } from "./api";
import type { AgentStep, AppConfig, AskMode, ConfigItem, DashboardMetrics, Finding, HistoryDetail, HistorySummary, RunResult } from "./types";

const emptyConfig: AppConfig = {
  app_name: "BMW Legal Agent Platform",
  workflow_name: "Ask Donna",
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
    source: "Otto Schmidt / Legal Data Hub",
    excerpt: "Processor arrangements should set out processing subject matter, duration, categories of data, data subjects, and processor obligations.",
    url: "https://gdpr.eu/article-28-processor/",
    confidence: 0.7
  },
  {
    title: "GDPR Art. 32 - security of processing",
    source: "Otto Schmidt / Legal Data Hub",
    excerpt: "Security measures should be appropriate to the risk and are commonly documented in TOMs or an equivalent security annex.",
    url: "https://gdpr.eu/article-32-security-of-processing/",
    confidence: 0.68
  },
  {
    title: "International transfer safeguards",
    source: "Otto Schmidt / Legal Data Hub",
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
  const [activeView, setActiveView] = useState<"ask" | "history" | "dashboard" | "playbook">("ask");
  const [askMode, setAskMode] = useState<AskMode>("general_question");
  const [message, setMessage] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isFinalVersion, setIsFinalVersion] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; content: string; result?: RunResult }>>([]);
  const [historyItems, setHistoryItems] = useState<HistorySummary[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<HistoryDetail | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then((loaded) => {
        setConfig(loaded);
      })
      .catch((err) => setError(err.message));
    getDashboard().then(setDashboard).catch(() => undefined);
    loadHistory().catch(() => undefined);
  }, []);

  const steps = isRunning ? optimisticSteps : result?.agent_steps ?? [];
  const agentLabelsById = useMemo(() => Object.fromEntries(config.agents.map((item) => [item.id, item.label])), [config.agents]);
  async function loadHistory() {
    const next = await getHistory();
    setHistoryItems(next.items);
    return next.items;
  }

  async function selectHistoryItem(id: string) {
    setIsHistoryLoading(true);
    setError(null);
    try {
      const detail = await getHistoryItem(id);
      setSelectedHistory(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load history");
    } finally {
      setIsHistoryLoading(false);
    }
  }

  async function handleDropHistory(id: string) {
    setIsHistoryLoading(true);
    setError(null);
    try {
      const detail = await dropHistoryItem(id, "Business marked this contract as dropped from History.");
      setSelectedHistory(detail);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not drop history item");
    } finally {
      setIsHistoryLoading(false);
    }
  }

  async function handleAnalyze(demoMode = false) {
    const submitted = demoMode ? config.demo_question : message.trim();
    if (!submitted && !files.length) {
      setError("Ask Donna needs a question, contract text, or uploaded file.");
      return;
    }
    setIsRunning(true);
    setError(null);
    if (!demoMode) {
      setChatMessages((items) => [...items, { role: "user", content: submitted }]);
      setMessage("");
    }
    try {
      const next = demoMode
        ? await runDemo()
        : await analyzeMatter({ message: submitted, mode: askMode, threadId, isFinalVersion, files, demoMode: false });
      const normalized = applyAutoRoutingFallback(next, true);
      setResult(normalized);
      setThreadId(normalized.history_thread_id ?? threadId);
      setChatMessages((items) => [...items, { role: "assistant", content: normalized.plain_answer, result: normalized }]);
      setFiles([]);
      setIsFinalVersion(false);
      setActiveView("ask");
      getDashboard().then(setDashboard).catch(() => undefined);
      loadHistory().catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setIsRunning(false);
    }
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
        ) : activeView === "history" ? (
          <HistoryView
            items={historyItems}
            selected={selectedHistory}
            isLoading={isHistoryLoading}
            error={error}
            onRefresh={loadHistory}
            onSelect={selectHistoryItem}
            onDrop={handleDropHistory}
          />
        ) : (
          <AskDonnaView
            config={config}
            mode={askMode}
            message={message}
            threadId={threadId}
            isFinalVersion={isFinalVersion}
            chatMessages={chatMessages}
            agentLabelsById={agentLabelsById}
            files={files}
            result={result}
            steps={steps}
            isRunning={isRunning}
            error={error}
            setMode={setAskMode}
            setMessage={setMessage}
            setIsFinalVersion={setIsFinalVersion}
            setFiles={setFiles}
            onAnalyze={() => handleAnalyze(false)}
            onDemo={() => handleAnalyze(true)}
          />
        )}
      </main>
    </div>
  );
}

function Sidebar({ activeView, onChange }: { activeView: string; onChange: (view: "ask" | "history" | "dashboard" | "playbook") => void }) {
  const general = [
    { id: "ask", label: "Ask Donna", icon: MessageSquareText },
    { id: "history", label: "History", icon: HistoryIcon }
  ] as const;
  const legal = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "playbook", label: "Playbook", icon: BookOpen },
    { label: "Escalations", icon: AlertTriangle, badge: "3" },
  ] as const;
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
        <span className="nav-section">General</span>
        {general.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.id} className={activeView === item.id ? "nav-item active" : "nav-item"} onClick={() => onChange(item.id)}>
              <Icon size={19} />
              <span>{item.label}</span>
            </button>
          );
        })}
        <div className="nav-divider" />
        <span className="nav-section">Legal</span>
        {legal.map((item) => {
          const Icon = item.icon;
          const id = "id" in item ? item.id : null;
          return (
            <button
              key={item.label}
              className={id && activeView === id ? "nav-item active" : "nav-item muted"}
              onClick={id ? () => onChange(id) : undefined}
            >
              <Icon size={19} />
              <span>{item.label}</span>
              {"badge" in item && item.badge ? <b>{item.badge}</b> : null}
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
        <span>Search history, clauses, playbooks, legal sources...</span>
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

function AskDonnaView(props: {
  config: AppConfig;
  mode: AskMode;
  message: string;
  threadId: string | null;
  isFinalVersion: boolean;
  chatMessages: Array<{ role: "user" | "assistant"; content: string; result?: RunResult }>;
  agentLabelsById: Record<string, string>;
  files: File[];
  result: RunResult | null;
  steps: AgentStep[];
  isRunning: boolean;
  error: string | null;
  setMode: (value: AskMode) => void;
  setMessage: (value: string) => void;
  setIsFinalVersion: (value: boolean) => void;
  setFiles: (files: File[]) => void;
  onAnalyze: () => void;
  onDemo: () => void;
}) {
  const placeholder =
    props.mode === "contract_review"
      ? "Paste the contract text, describe the business context, or upload a file. Ask Donna will identify the contract type and route the right checks."
      : "Ask a legal or playbook question. Add any business context in the same message.";

  return (
    <div className="workspace ask-workspace">
      <section className="center-pane">
        <div className="page-title">
          <div>
            <p className="eyebrow">Ask Donna</p>
            <h1>Ask questions, review contracts, and keep the full decision trail.</h1>
          </div>
          <button className="secondary-button" onClick={props.onDemo} disabled={props.isRunning}>
            <Play size={17} />
            Run demo matter
          </button>
        </div>

        <div className="chat-card">
          <div className="chat-transcript">
            {!props.chatMessages.length ? (
              <div className="welcome-message">
                <Sparkles size={24} />
                <div>
                  <strong>Start a conversation with Donna</strong>
                  <p>Donna will select sources and agents automatically, then store the reply, source usage, and visible reasoning in History.</p>
                </div>
              </div>
            ) : null}
            {props.chatMessages.map((item, index) => (
              <div className={`chat-message ${item.role}`} key={`${item.role}-${index}`}>
                <div className="message-avatar">{item.role === "user" ? "You" : "D"}</div>
                <div className="message-bubble">
                  <p>{item.content}</p>
                  {item.result ? <ChatResultSummary result={item.result} agentLabelsById={props.agentLabelsById} /> : null}
                </div>
              </div>
            ))}
            {props.isRunning ? (
              <div className="chat-message assistant">
                <div className="message-avatar">D</div>
                <div className="message-bubble typing">
                  <Loader2 className="spin" size={18} />
                  Donna is checking sources and routing agents.
                </div>
              </div>
            ) : null}
          </div>

          <div className="composer">
            <div className="composer-toolbar">
              <label className="mode-select">
                <span>Mode</span>
                <select value={props.mode} onChange={(event) => props.setMode(event.target.value as AskMode)}>
                  <option value="general_question">General question</option>
                  <option value="contract_review">Contract review</option>
                </select>
              </label>
              {props.mode === "contract_review" ? (
                <button
                  className={props.isFinalVersion ? "final-toggle selected" : "final-toggle"}
                  onClick={() => props.setIsFinalVersion(!props.isFinalVersion)}
                  type="button"
                >
                  <CheckCircle2 size={17} />
                  Final version
                </button>
              ) : null}
              {props.threadId ? <span className="status-pill">Thread saved</span> : <span className="status-pill blue">New chat</span>}
            </div>
            <textarea
              value={props.message}
              onChange={(event) => props.setMessage(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") props.onAnalyze();
              }}
              rows={6}
              placeholder={placeholder}
            />
            <UploadBox files={props.files} setFiles={props.setFiles} />
            <div className="action-row">
              <div className="mini-stack">
                <span><Database size={17} />Sources selected automatically</span>
                <span><Users size={17} />Agents routed automatically</span>
              </div>
              <button className="primary-button" onClick={props.onAnalyze} disabled={props.isRunning}>
                {props.isRunning ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
                Send to Donna
              </button>
            </div>
            {props.isFinalVersion && props.mode === "contract_review" ? (
              <div className="final-banner">
                <ShieldCheck size={18} />
                Donna will store this contract in History as approved only if all checks pass. Unresolved findings will be marked pending Legal.
              </div>
            ) : null}
            {props.error ? <div className="error-box">{props.error}</div> : null}
          </div>
        </div>

        <AgentTimeline steps={props.steps} isRunning={props.isRunning} />
        {props.result ? <ResultPanel result={props.result} agentLabelsById={props.agentLabelsById} /> : <EmptyState />}
      </section>
    </div>
  );
}

function ChatResultSummary({ result, agentLabelsById }: { result: RunResult; agentLabelsById: Record<string, string> }) {
  const routed = (result.routed_agents ?? []).map((agentId) => agentLabelsById[agentId] ?? agentId.replace("_", " "));
  return (
    <div className="chat-result-summary">
      <span className={result.contract_status === "approved" ? "status-pill approved" : result.contract_status === "pending_legal" ? "status-pill warning" : "status-pill"}>
        {result.contract_status ? result.contract_status.replace("_", " ") : result.escalation_state}
      </span>
      {routed.length ? <small>Routed to {routed.join(", ")}</small> : null}
      {result.source_usage?.length ? <small>{result.source_usage.length} source group(s) recorded</small> : null}
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
  return (
    <div className="upload-box">
      <UploadCloud size={24} />
      <div>
        <strong>Upload contract bundle</strong>
        <span>PDF, DOCX, XLSX, PPTX, TXT, CSV, EML, or ZIP</span>
      </div>
      <label className="file-button">
        <FolderOpen size={17} />
        Browse files
        <input
          type="file"
          multiple
          onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
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
  const usage = result?.source_usage ?? [];
  const sources = result?.legal_sources ?? mockLegalSources;
  return (
    <section className="side-card">
      <div className="section-head compact">
        <h2>Sources used</h2>
      </div>
      <div className="source-list">
        {usage.length ? (
          usage.map((group) => (
            <div className="source-item" key={group.id}>
              <BookOpen size={16} />
              <div>
                <strong>{group.label}</strong>
                <p>{group.description}</p>
                <span>{group.item_count} item(s) recorded</span>
              </div>
            </div>
          ))
        ) : sources.slice(0, 3).map((source) => (
          <a href={source.url || "#"} target="_blank" rel="noreferrer" className="source-item" key={source.title}>
            <BookOpen size={16} />
            <div>
              <strong>{source.title}</strong>
              <p>{source.excerpt}</p>
              <span>{source.source}</span>
            </div>
          </a>
        ))}
        {!result ? <div className="quiet-box source-empty"><p>Donna will replace this preview with run-specific Otto Schmidt and playbook citations.</p><a>Go to Legal Data Hub <ExternalLink size={14} /></a></div> : null}
      </div>
    </section>
  );
}

function HistoryView({
  items,
  selected,
  isLoading,
  error,
  onRefresh,
  onSelect,
  onDrop
}: {
  items: HistorySummary[];
  selected: HistoryDetail | null;
  isLoading: boolean;
  error: string | null;
  onRefresh: () => Promise<HistorySummary[]>;
  onSelect: (id: string) => void;
  onDrop: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) =>
      [item.title, item.contract_status, item.contract_type, item.counterparty]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalized))
    );
  }, [items, query]);
  const latestRun = selected?.runs[selected.runs.length - 1];

  return (
    <div className="history-view">
      <div className="page-title">
        <div>
          <p className="eyebrow">General History</p>
          <h1>Previous chats, finalized contracts, and approval reasoning.</h1>
        </div>
        <button className="secondary-button" onClick={() => onRefresh()} disabled={isLoading}>
          {isLoading ? <Loader2 className="spin" size={17} /> : <HistoryIcon size={17} />}
          Refresh history
        </button>
      </div>
      {error ? <div className="error-box history-error">{error}</div> : null}
      <div className="history-grid">
        <section className="history-list-panel">
          <div className="history-search">
            <Search size={17} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search chats or contracts" />
          </div>
          <div className="history-list">
            {filtered.map((item) => (
              <button key={item.id} className={selected?.id === item.id ? "history-row active" : "history-row"} onClick={() => onSelect(item.id)}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.mode === "contract_review" ? "Contract review" : "General question"}</span>
                </div>
                <HistoryStatus item={item} />
              </button>
            ))}
            {!filtered.length ? <div className="quiet-box">No history records found.</div> : null}
          </div>
        </section>

        <section className="history-detail-panel">
          {!selected ? (
            <div className="empty-state history-empty">
              <HistoryIcon size={27} />
              <div>
                <strong>Select a history item</strong>
                <p>Open a prior chat to review Donna's reply, visible reasoning, sources, status, and modification timeline.</p>
              </div>
            </div>
          ) : (
            <>
              <div className="history-detail-head">
                <div>
                  <p className="eyebrow">{selected.mode === "contract_review" ? "Contract History" : "Chat History"}</p>
                  <h2>{selected.title}</h2>
                </div>
                <HistoryStatus item={selected} />
              </div>

              <div className="history-columns">
                <div className="history-chat">
                  <h3>Transcript</h3>
                  {selected.messages.map((message) => (
                    <div className={`history-message ${message.role}`} key={message.id}>
                      <strong>{message.role === "assistant" ? "Donna" : "Business"}</strong>
                      <p>{message.content}</p>
                    </div>
                  ))}
                </div>
                <div className="history-reasoning">
                  <h3>Reasoning and sources</h3>
                  {latestRun ? (
                    <>
                      <div className="quiet-box">
                        <strong>{latestRun.result.escalation_state}</strong>
                        <p>{latestRun.result.next_action}</p>
                      </div>
                      <div className="source-list history-sources">
                        {latestRun.sources_used.map((source) => (
                          <div className="source-item" key={source.id}>
                            <BookOpen size={16} />
                            <div>
                              <strong>{source.label}</strong>
                              <p>{source.description}</p>
                              <span>{source.item_count} item(s)</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="quiet-box">No run trace is stored for this item.</div>
                  )}
                </div>
              </div>

              <div className="history-events">
                <div className="section-head compact">
                  <h2>Modification timeline</h2>
                  {selected.contract_status !== "dropped" ? (
                    <button className="text-button" onClick={() => onDrop(selected.id)}>
                      Mark dropped
                    </button>
                  ) : null}
                </div>
                {selected.events.map((event) => (
                  <div className="event-row" key={event.id}>
                    <span>{event.actor}</span>
                    <strong>{event.summary}</strong>
                    <small>{new Date(event.created_at).toLocaleString()}</small>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function HistoryStatus({ item }: { item: HistorySummary | HistoryDetail }) {
  if (!item.contract_status) return <span className="status-pill">chat</span>;
  return <span className={`status-pill history-status ${item.contract_status}`}>{item.contract_status.replace("_", " ")}</span>;
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
          <p className="eyebrow">BMW playbook</p>
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
