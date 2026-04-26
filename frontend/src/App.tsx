import {
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
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
  Paperclip,
  Send,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  Users
} from "lucide-react";
import React, { useEffect, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { analyzeMatter, askEscalationQuestion, decideEscalation, dropHistoryItem, getDashboard, getEscalation, getHistory, getHistoryItem, listEscalations } from "./api";
import donnaLogo from "./assets/donna-logo.png";
import type { AgentMetric, AskMode, BusinessInputItem, ConfigItem, DashboardMetrics, EscalationDetail, EscalationListItem, EscalationStatus, Finding, HistoryDetail, HistorySummary, RunResult, Severity, Suggestion, TriggerAnnotation } from "./types";

type ModelMode = "quality" | "fast";
type AskAttachment = { name: string; size: number };
type AskChatMessage = { role: "user" | "assistant"; content: string; result?: RunResult; attachments?: AskAttachment[] };

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
  const [dashboard, setDashboard] = useState<DashboardMetrics | null>(null);
  const [activeView, setActiveView] = useState<"ask" | "history" | "dashboard" | "escalations">("ask");
  const [escalationCount, setEscalationCount] = useState(0);
  const [askMode, setAskMode] = useState<AskMode>("general_question");
  const [modelMode, setModelMode] = useState<ModelMode>("quality");
  const [message, setMessage] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isFinalVersion, setIsFinalVersion] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [chatMessages, setChatMessages] = useState<AskChatMessage[]>([]);
  const [historyItems, setHistoryItems] = useState<HistorySummary[]>([]);
  const [selectedHistory, setSelectedHistory] = useState<HistoryDetail | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard().then(setDashboard).catch(() => undefined);
    loadHistory().catch(() => undefined);
    listEscalations("pending_legal").then((data) => setEscalationCount(data.items.length)).catch(() => undefined);
  }, []);

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

  function reopenHistoryInChat(detail: HistoryDetail) {
    setThreadId(detail.id);
    setAskMode(detail.mode);
    setChatMessages(historyDetailToChatMessages(detail));
    setMessage("");
    setFiles([]);
    setIsFinalVersion(false);
    setSelectedHistory(detail);
    setActiveView("ask");
  }

  async function handleAnalyze() {
    const submitted = message.trim();
    if (!submitted && !files.length) {
      setError("Ask Donna needs a question, contract text, or uploaded file.");
      return;
    }
    const displayedMessage =
      submitted || (askMode === "general_question" ? "Summarize uploaded document(s)." : "Review uploaded contract bundle.");
    const submittedAttachments = files.map((file) => ({ name: file.name, size: file.size }));
    setIsRunning(true);
    setError(null);
    setChatMessages((items) => [...items, { role: "user", content: displayedMessage, attachments: submittedAttachments }]);
    setMessage("");
    try {
      const next = await analyzeMatter({ message: submitted, mode: askMode, threadId, isFinalVersion, files, demoMode: false, modelMode });
      const normalized = applyAutoRoutingFallback(next, true);
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
      <Sidebar activeView={activeView} onChange={setActiveView} escalationCount={escalationCount} />
      <main className="main">
        <Topbar />
        {activeView === "dashboard" ? (
          <DashboardView dashboard={dashboard} />
        ) : activeView === "escalations" ? (
          <EscalationsView />
        ) : activeView === "history" ? (
          <HistoryView
            items={historyItems}
            selected={selectedHistory}
            isLoading={isHistoryLoading}
            error={error}
            onRefresh={loadHistory}
            onSelect={selectHistoryItem}
            onDrop={handleDropHistory}
            onOpenInChat={reopenHistoryInChat}
          />
        ) : (
          <AskDonnaView
            mode={askMode}
            message={message}
            threadId={threadId}
            isFinalVersion={isFinalVersion}
            chatMessages={chatMessages}
            files={files}
            isRunning={isRunning}
            error={error}
            modelMode={modelMode}
            setMode={setAskMode}
            setModelMode={setModelMode}
            setMessage={setMessage}
            setIsFinalVersion={setIsFinalVersion}
            setFiles={setFiles}
            onAnalyze={handleAnalyze}
          />
        )}
      </main>
    </div>
  );
}

function Sidebar({ activeView, onChange, escalationCount }: { activeView: string; onChange: (view: "ask" | "history" | "dashboard" | "escalations") => void; escalationCount: number }) {
  const general = [
    { id: "ask", label: "Ask Donna", icon: MessageSquareText },
    { id: "history", label: "History", icon: HistoryIcon }
  ] as const;
  const legal = [
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "escalations", label: "Escalations", icon: AlertTriangle },
  ] as const;
  const admin = [
    { label: "Settings", icon: Settings }
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-mark" src={donnaLogo} alt="Donna" />
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
          return (
            <button
              key={item.label}
              className={activeView === item.id ? "nav-item active" : "nav-item"}
              onClick={() => onChange(item.id)}
            >
              <Icon size={19} />
              <span>{item.label}</span>
              {item.id === "escalations" && escalationCount > 0 ? <b>{escalationCount}</b> : null}
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
        <button className="icon-button" aria-label="Notifications">
          <Bell size={20} />
        </button>
        <div className="avatar">PS</div>
        <ChevronDown size={18} />
      </div>
    </header>
  );
}

function historyDetailToChatMessages(detail: HistoryDetail): AskChatMessage[] {
  const runsById = new Map(detail.runs.map((run) => [run.id, run]));
  return detail.messages.map((message) => {
    if (message.role === "assistant") {
      const runId = typeof message.metadata?.run_id === "string" ? message.metadata.run_id : "";
      const run = runsById.get(runId);
      return {
        role: "assistant",
        content: message.content,
        result: run?.result,
      };
    }
    const uploaded = Array.isArray(message.metadata?.uploaded_filenames) ? message.metadata.uploaded_filenames : [];
    return {
      role: "user",
      content: message.content,
      attachments: uploaded.map((name) => ({ name: String(name), size: 0 })),
    };
  });
}

function AskDonnaView(props: {
  mode: AskMode;
  message: string;
  threadId: string | null;
  isFinalVersion: boolean;
  chatMessages: AskChatMessage[];
  files: File[];
  isRunning: boolean;
  error: string | null;
  modelMode: ModelMode;
  setMode: (value: AskMode) => void;
  setModelMode: (value: ModelMode) => void;
  setMessage: (value: string) => void;
  setIsFinalVersion: (value: boolean) => void;
  setFiles: (files: File[]) => void;
  onAnalyze: () => void;
}) {
  const placeholder =
    props.mode === "contract_review"
      ? "Paste the contract text, describe the business context, or upload a file. Ask Donna will identify the contract type and route the right checks."
      : "Ask about law, BMW playbook positions, or an uploaded document. For example: summarize this PDF or explain GDPR Art. 28.";
  const addFilesToComposer = (incoming: File[]) => props.setFiles(mergeUniqueFiles(props.files, incoming));

  return (
    <div className="workspace ask-workspace">
      <section className="center-pane">
        <div className="page-title">
          <div>
            <p className="eyebrow">Ask Donna</p>
            <h1>Ask questions, review contracts, and keep the full decision trail.</h1>
          </div>
        </div>

        <div className="chat-card">
          {props.isRunning ? <RunningAgentRail mode={props.mode} /> : null}
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
                <MessageAvatar role={item.role} />
                <div className="message-bubble">
                  {item.role === "assistant" && item.result ? <ChatResultSummary result={item.result} /> : null}
                  {item.role === "assistant" ? <FootnotedAnswer content={item.content} result={item.result} onAddFiles={addFilesToComposer} /> : <p>{item.content}</p>}
                  {item.role === "user" && item.attachments?.length ? <MessageAttachments attachments={item.attachments} /> : null}
                </div>
              </div>
            ))}
            {props.isRunning ? (
              <div className="chat-message assistant">
                <MessageAvatar role="assistant" />
                <div className="message-bubble typing">
                  <Loader2 className="spin" size={18} />
                  Donna is checking sources and routing agents.
                </div>
              </div>
            ) : null}
          </div>

          <div className="composer">
            <div className="composer-toolbar">
              <div className="mode-switch" role="group" aria-label="Ask Donna mode">
                <span>Mode</span>
                <div className="mode-switch-track">
                  <button
                    type="button"
                    className={props.mode === "general_question" ? "mode-switch-option active" : "mode-switch-option"}
                    onClick={() => props.setMode("general_question")}
                    aria-pressed={props.mode === "general_question"}
                  >
                    <MessageSquareText size={16} />
                    General
                  </button>
                  <button
                    type="button"
                    className={props.mode === "contract_review" ? "mode-switch-option active" : "mode-switch-option"}
                    onClick={() => props.setMode("contract_review")}
                    aria-pressed={props.mode === "contract_review"}
                  >
                    <FileSearch size={16} />
                    Contract
                  </button>
                </div>
              </div>
              <button
                className={props.modelMode === "fast" ? "fast-mode-toggle active" : "fast-mode-toggle"}
                type="button"
                onClick={() => props.setModelMode(props.modelMode === "fast" ? "quality" : "fast")}
                aria-pressed={props.modelMode === "fast"}
                title={props.modelMode === "fast" ? "Using gpt-5.4-mini" : "Using gpt-5.5"}
              >
                <span className="fast-switch" />
                <span>
                  {props.modelMode === "fast" ? "Fast mode" : "Quality mode"}
                  <small>{props.modelMode === "fast" ? "5.4 mini" : "5.5"}</small>
                </span>
              </button>
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
              rows={3}
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
      </section>
    </div>
  );
}

function RunningAgentRail({ mode }: { mode: AskMode }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const steps =
    mode === "contract_review"
      ? [
          "Contract classification",
          "DPA playbook judge",
          "German / EU legal check",
          "Risk aggregation",
          "Completeness gate",
          "Escalation decision"
        ]
      : [
          "Question routing",
          "BMW playbook context",
          "German / EU legal evidence",
          "Answer drafting",
          "History update"
        ];

  useEffect(() => {
    setActiveIndex(0);
    const interval = window.setInterval(() => {
      setActiveIndex((current) => Math.min(current + 1, steps.length - 1));
    }, mode === "contract_review" ? 2600 : 1900);
    return () => window.clearInterval(interval);
  }, [mode, steps.length]);

  return (
    <div className="agent-run-rail" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }} aria-label="Running agent workflow">
      {steps.map((step, index) => {
        const state = index < activeIndex ? "completed" : index === activeIndex ? "active" : "pending";
        const status = state === "completed" ? "Completed" : state === "active" ? "In progress" : "Pending";
        return (
          <div className={`agent-run-step ${state}`} key={step}>
            <div className={`agent-run-index ${state}`}>
              {state === "completed" ? <CheckCircle2 size={16} /> : index + 1}
            </div>
            <div className="agent-run-copy">
              <strong>{step}</strong>
              <span>{status}</span>
            </div>
            {index < steps.length - 1 ? <div className="agent-run-line" /> : null}
          </div>
        );
      })}
    </div>
  );
}

function MessageAvatar({ role }: { role: "user" | "assistant" }) {
  if (role === "user") {
    return <div className="message-avatar">You</div>;
  }

  return (
    <div className="message-avatar donna-avatar" aria-label="Donna">
      <img src={donnaLogo} alt="" />
    </div>
  );
}

function MessageAttachments({ attachments }: { attachments: AskAttachment[] }) {
  return (
    <div className="message-attachments" aria-label="Attached files">
      {attachments.map((file, index) => (
        <span className="message-attachment-chip" key={`${file.name}-${file.size}-${index}`} title={file.name}>
          <Paperclip size={14} />
          <span>{file.name}</span>
        </span>
      ))}
    </div>
  );
}

function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="message-markdown">
      <ReactMarkdown skipHtml>{content}</ReactMarkdown>
    </div>
  );
}

function ChatResultSummary({ result }: { result: RunResult }) {
  const sources = result.source_usage ?? [];
  return (
    <div className="chat-result-summary">
      <div className="chat-result-meta">
        <span className={statusPillClass(result.contract_status)}>
          {result.contract_status ? result.contract_status.replace("_", " ") : result.escalation_state}
        </span>
        <span className="status-pill source-count">
          <Database size={15} />
          {sources.length ? `${sources.length} source group${sources.length === 1 ? "" : "s"}` : "No sources recorded"}
        </span>
        {result.metrics?.openai_model ? <span className="status-pill model-pill">{String(result.metrics.openai_model)}</span> : null}
      </div>
    </div>
  );
}

function statusPillClass(status?: RunResult["contract_status"]) {
  if (status === "approved") return "status-pill approved";
  if (status === "pending_legal") return "status-pill warning";
  if (status === "needs_business_input") return "status-pill needs-input";
  return "status-pill";
}

function FootnotedAnswer({
  content,
  result,
  onAddFiles
}: {
  content: string;
  result?: RunResult;
  onAddFiles?: (files: File[]) => void;
}) {
  const footnotes = result ? buildCitationFootnotes(content, result) : [];
  const linkedContent = result ? linkCitationNumbers(content, result.id, new Set(footnotes.map((footnote) => footnote.number))) : content;
  return (
    <>
      <MarkdownMessage content={linkedContent} />
      {result?.business_input?.status === "needs_business_input" ? <LegalReviewGatePanel result={result} onAddFiles={onAddFiles} /> : null}
      {result ? <CitationFootnotes resultId={result.id} footnotes={footnotes} sourceGroups={result.source_usage ?? []} /> : null}
    </>
  );
}

function LegalReviewGatePanel({ result, onAddFiles }: { result: RunResult; onAddFiles?: (files: File[]) => void }) {
  const [step, setStep] = useState<"review" | "missing" | "ticket">("review");
  const [isOpen, setIsOpen] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [addedFiles, setAddedFiles] = useState<string[]>([]);
  const [ticketQuestion, setTicketQuestion] = useState("Please review the flagged playbook deviations and approve the proposed escalation path.");
  const [ticketOwner, setTicketOwner] = useState("John Doe");
  const [ticketUrgency, setTicketUrgency] = useState("normal");
  const [ticketNotes, setTicketNotes] = useState("");
  const [ticketSent, setTicketSent] = useState(false);
  const check = result.business_input;
  const addMissingFiles = (incoming: File[]) => {
    if (!incoming.length) return;
    onAddFiles?.(incoming);
    setAddedFiles((current) => [...current, ...incoming.map((file) => file.name)]);
  };

  const closeWorkflow = () => {
    setIsOpen(false);
    setIsDragging(false);
  };

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeWorkflow();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen]);

  if (!check || check.status !== "needs_business_input") return null;

  const missing = check.missing_items ?? [];
  const escalationFindings = (result.findings ?? []).filter(isLegalEscalationFinding).slice(0, 3);
  const sourceLabel = check.source === "openai" ? "LLM file check" : "File reference parser";

  const uploadArea = (title: string, description: string, visibleCount: number) => (
    <>
      <label
        className={isDragging ? "legal-flow-upload dragging" : "legal-flow-upload"}
        onDragEnter={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
          setIsDragging(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setIsDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setIsDragging(false);
          addMissingFiles(Array.from(event.dataTransfer.files ?? []));
        }}
      >
        <UploadCloud size={18} />
        <span>
          <strong>{title}</strong>
          <small>{description}</small>
        </span>
        <input
          type="file"
          multiple
          onChange={(event) => {
            addMissingFiles(Array.from(event.target.files ?? []));
            event.currentTarget.value = "";
          }}
        />
      </label>

      {addedFiles.length ? (
        <div className="legal-flow-added">
          {addedFiles.slice(-visibleCount).map((filename, index) => (
            <span key={`${filename}-${index}`}>
              <Paperclip size={13} />
              {filename}
            </span>
          ))}
        </div>
      ) : null}
    </>
  );

  const stepContent =
    step === "review" ? (
      <div className="legal-flow-pane">
        <div className="legal-flow-head">
          <Gavel size={18} />
          <div>
            <strong>Recommended for Legal review</strong>
            <span>Donna checked the contract against the BMW playbook first. The package is not ready to send yet because referenced files are missing.</span>
          </div>
        </div>

        <div className="legal-flow-list">
          {escalationFindings.length ? (
            escalationFindings.map((finding) => (
              <article className="legal-flow-item" key={finding.id}>
                <div>
                  <strong>{finding.title}</strong>
                  <span className={finding.severity === "High" ? "severity-high" : ""}>{finding.category} · {finding.severity}</span>
                </div>
                <p>{finding.description}</p>
                {finding.evidence?.[0]?.quote ? <blockquote>{finding.evidence[0].quote}</blockquote> : null}
              </article>
            ))
          ) : (
            <article className="legal-flow-item">
              <div>
                <strong>Playbook deviation detected</strong>
                <span>Legal review recommended</span>
              </div>
              <p>{result.plain_answer}</p>
            </article>
          )}
        </div>

        <button className="legal-flow-next" type="button" onClick={() => setStep("missing")}>
          Next: add missing {missing.length === 1 ? "file" : "files"}
          <ChevronRight size={16} />
        </button>
      </div>
    ) : step === "missing" ? (
      <div className="legal-flow-pane">
        <div className="legal-flow-head">
          <Paperclip size={18} />
          <div>
            <strong>Add missing referenced {missing.length === 1 ? "file" : "files"}</strong>
            <span>{sourceLabel} only checked explicit references in the uploaded file against the current attachments.</span>
          </div>
        </div>

        <div className="legal-flow-list">
          {missing.map((item, index) => (
            <article className="legal-flow-item missing" key={`${item.label}-${index}`}>
              <div>
                <strong>{item.label}</strong>
                <span>{item.source_file || "ticket intake"}</span>
              </div>
              <p>{item.reason}</p>
              {item.source_quote ? (
                <blockquote>
                  <span>Why Donna expects it</span>
                  {item.source_quote}
                </blockquote>
              ) : null}
            </article>
          ))}
        </div>

        <div className="legal-flow-actions">
          <button className="legal-flow-back" type="button" onClick={() => setStep("review")}>
            Back
          </button>
          <button className="legal-flow-next" type="button" onClick={() => setStep("ticket")}>
            Next: ticket details
            <ChevronRight size={16} />
          </button>
          <span>Upload the missing file{missing.length === 1 ? "" : "s"} and rerun before sending to Legal.</span>
        </div>

        {uploadArea("Add missing files", "Drop here or browse. Files are attached to the composer for the rerun.", 4)}
      </div>
    ) : (
      <div className="legal-flow-pane">
        <div className="legal-flow-head">
          <Send size={18} />
          <div>
            <strong>Submit Legal ticket</strong>
            <span>Add the missing files and business context, then send the prepared package to Legal.</span>
          </div>
        </div>

        {uploadArea("Attach missing files", "Drop files here or browse. They will be included in the Legal package draft.", 6)}

        <div className="ticket-form-grid">
          <label className="ticket-field wide">
            <span>Question for Legal</span>
            <textarea value={ticketQuestion} onChange={(event) => setTicketQuestion(event.target.value)} rows={3} />
          </label>
          <label className="ticket-field">
            <span>Business owner</span>
            <input value={ticketOwner} onChange={(event) => setTicketOwner(event.target.value)} placeholder="Name or team" />
          </label>
          <label className="ticket-field">
            <span>Urgency</span>
            <select value={ticketUrgency} onChange={(event) => setTicketUrgency(event.target.value)}>
              <option value="normal">Normal</option>
              <option value="urgent">Urgent</option>
              <option value="signing_blocker">Signing blocker</option>
            </select>
          </label>
          <label className="ticket-field wide">
            <span>Relevant business context</span>
            <textarea value={ticketNotes} onChange={(event) => setTicketNotes(event.target.value)} rows={4} placeholder="Commercial pressure, signing deadline, negotiation history, vendor position, or why a referenced file is unavailable." />
          </label>
        </div>

        <div className="ticket-review-box">
          <strong>Ticket package status</strong>
          <span>{missing.length} referenced file{missing.length === 1 ? "" : "s"} still flagged by Donna.</span>
          {addedFiles.length ? <span>{addedFiles.length} new file{addedFiles.length === 1 ? "" : "s"} added to the composer for rerun.</span> : null}
          <small>After adding files, rerun Donna so the completeness gate can verify the package before the ticket is sent.</small>
        </div>

        <div className="legal-flow-actions">
          <button className="legal-flow-back" type="button" onClick={() => setStep("missing")}>
            Back
          </button>
          <button
            className="legal-flow-next"
            type="button"
            onClick={() => {
              setIsOpen(false);
              setTicketSent(true);
            }}
          >
            Send ticket to Legal
            <CheckCircle2 size={16} />
          </button>
        </div>
      </div>
    );

  return (
    <>
      <section className="legal-flow-card legal-flow-launcher" aria-label="Legal review and missing files">
        <div className="legal-flow-head">
          <Gavel size={18} />
          <div>
            <strong>Recommended for Legal review</strong>
            <span>{missing.length} referenced file{missing.length === 1 ? "" : "s"} must be added or explained before Legal gets the ticket.</span>
          </div>
        </div>
        <button className="legal-flow-next" type="button" onClick={() => setIsOpen(true)}>
          Open escalation workflow
          <ChevronRight size={16} />
        </button>
      </section>

      {isOpen ? (
        <div className="ticket-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeWorkflow();
        }}>
          <section className="ticket-modal legal-flow-modal" role="dialog" aria-modal="true" aria-label="Legal escalation workflow">
            <div className="ticket-modal-head">
              <div>
                <span>Escalation workflow</span>
                <strong>Prepare Legal review package</strong>
              </div>
              <button className="icon-button modal-close-button" type="button" onClick={closeWorkflow} aria-label="Close escalation workflow">
                ×
              </button>
            </div>

            <div className="legal-flow-steps">
              <button className={step === "review" ? "active" : ""} type="button" onClick={() => setStep("review")}>
                <span>1</span>
                Legal review
              </button>
              <button className={step === "missing" ? "active" : ""} type="button" onClick={() => setStep("missing")}>
                <span>2</span>
                Missing files
              </button>
              <button className={step === "ticket" ? "active" : ""} type="button" onClick={() => setStep("ticket")}>
                <span>3</span>
                Ticket details
              </button>
            </div>

            {stepContent}
          </section>
        </div>
      ) : null}

      {ticketSent ? (
        <LegalTicketModal
          result={result}
          missing={missing}
          escalationFindings={escalationFindings}
          addedFiles={addedFiles}
          ticketQuestion={ticketQuestion}
          ticketOwner={ticketOwner}
          ticketUrgency={ticketUrgency}
          ticketNotes={ticketNotes}
          onClose={() => setTicketSent(false)}
        />
      ) : null}
    </>
  );
}

function LegalTicketModal({
  result,
  missing,
  escalationFindings,
  addedFiles,
  ticketQuestion,
  ticketOwner,
  ticketUrgency,
  ticketNotes,
  onClose
}: {
  result: RunResult;
  missing: BusinessInputItem[];
  escalationFindings: Finding[];
  addedFiles: string[];
  ticketQuestion: string;
  ticketOwner: string;
  ticketUrgency: string;
  ticketNotes: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  return (
    <div className="ticket-modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="ticket-modal" role="dialog" aria-modal="true" aria-label="Legal ticket package">
        <div className="ticket-modal-head">
          <div>
            <span>Legal ticket</span>
            <strong>Package sent to Legal</strong>
          </div>
          <button className="icon-button modal-close-button" type="button" onClick={onClose} aria-label="Close Legal ticket popup">
            ×
          </button>
        </div>

        <div className="ticket-state-grid">
          <div>
            <span>Status</span>
            <strong>Pending Legal review</strong>
          </div>
          <div>
            <span>Urgency</span>
            <strong>{ticketUrgency.replace(/_/g, " ")}</strong>
          </div>
          <div>
            <span>Owner</span>
            <strong>{ticketOwner || "Not provided"}</strong>
          </div>
          <div>
            <span>Tracking</span>
            <strong>{result.id}</strong>
          </div>
        </div>

        <div className="ticket-modal-section">
          <h3>Question for Legal</h3>
          <p>{ticketQuestion || "Not provided"}</p>
        </div>

        <div className="ticket-modal-section">
          <h3>Escalation basis</h3>
          {escalationFindings.map((finding) => (
            <div className="ticket-modal-item" key={finding.id}>
              <strong>{finding.title}</strong>
              <span className={finding.severity === "High" ? "severity-high" : ""}>{finding.category} · {finding.severity}</span>
              <p>{finding.description}</p>
            </div>
          ))}
        </div>

        <div className="ticket-modal-section">
          <h3>Missing-file state</h3>
          <p>{missing.length} referenced file{missing.length === 1 ? "" : "s"} flagged by Donna. {addedFiles.length} file{addedFiles.length === 1 ? "" : "s"} added in this submission screen.</p>
          <div className="ticket-modal-chips">
            {missing.map((item) => <span key={item.label}>{item.label}</span>)}
          </div>
        </div>

        <div className="ticket-modal-section">
          <h3>Added attachments</h3>
          <div className="ticket-modal-chips">
            {addedFiles.length ? addedFiles.map((file, index) => <span key={`${file}-${index}`}>{file}</span>) : <span>No new files attached here</span>}
          </div>
        </div>

        <div className="ticket-modal-section">
          <h3>Business context</h3>
          <p>{ticketNotes || "No additional business context provided."}</p>
        </div>

        <div className="ticket-state-grid compact">
          <div>
            <span>Model</span>
            <strong>{String(result.metrics?.openai_model || "Not recorded")}</strong>
          </div>
          <div>
            <span>Sources</span>
            <strong>{(result.source_usage ?? []).length} group(s)</strong>
          </div>
          <div>
            <span>Findings</span>
            <strong>{result.findings.length}</strong>
          </div>
          <div>
            <span>Created</span>
            <strong>{new Date(result.created_at).toLocaleString()}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}

function EscalationReasonPanel({ result }: { result: RunResult }) {
  const escalationFindings = (result.findings ?? []).filter(isLegalEscalationFinding).slice(0, 3);
  if (!escalationFindings.length) return null;

  return (
    <section className="escalation-reason-panel" aria-label="Legal escalation reason">
      <div className="escalation-reason-head">
        <Gavel size={18} />
        <div>
          <strong>Step 1 · Playbook review recommends Legal escalation</strong>
          <span>Donna first checked the contract clauses against the active BMW playbook and German/EU legal review path.</span>
        </div>
      </div>
      <div className="escalation-reason-list">
        {escalationFindings.map((finding) => (
          <article className="escalation-reason-card" key={finding.id}>
            <div>
              <strong>{finding.title}</strong>
                    <span className={finding.severity === "High" ? "severity-high" : ""}>{finding.category} · {finding.severity}</span>
            </div>
            <p>{finding.description}</p>
            {finding.evidence?.[0]?.quote ? <blockquote>{finding.evidence[0].quote}</blockquote> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function BusinessInputPanel({ result }: { result: RunResult }) {
  const check = result.business_input;
  if (!check || check.status !== "needs_business_input") return null;
  const missing = check.missing_items ?? [];
  const sourceLabel = check.source === "openai" ? "LLM completeness judge" : "Completeness fallback parser";

  return (
    <section className="business-input-panel" aria-label="Missing business input">
      <div className="business-input-head">
        <AlertTriangle size={18} />
        <div>
          <strong>Step 2 · Add {missing.length === 1 ? "the missing file" : `${missing.length} missing files`} before Legal receives this ticket</strong>
          <span>{sourceLabel} looked only for documents explicitly referenced in the uploaded file and compared them against the current attachments.</span>
        </div>
      </div>

      <div className="missing-file-list">
        {missing.map((item, index) => (
          <article className="missing-file-card" key={`${item.label}-${index}`}>
            <div className="missing-file-top">
              <span className="missing-file-index">{index + 1}</span>
              <div>
                <strong>{item.label}</strong>
                <small>{item.severity === "blocking" ? "Blocking Legal submission" : item.severity}</small>
              </div>
            </div>
            <p>{item.reason}</p>
            {item.source_quote ? (
              <blockquote>
                <span>Why Donna expects it</span>
                {item.source_quote}
              </blockquote>
            ) : null}
            <div className="missing-file-meta">
              <span><FileText size={14} />Referenced in: {item.source_file || "ticket intake"}</span>
              {typeof item.confidence === "number" ? <span>{Math.round(item.confidence * 100)}% confidence</span> : null}
            </div>
            <div className="missing-file-action">
              <strong>Next step</strong>
              <span>{businessActionLabel(item.user_action)}</span>
            </div>
          </article>
        ))}
      </div>

      <details className="completeness-audit">
        <summary>Show what Donna checked</summary>
        <div className="completeness-audit-grid">
          <div>
            <strong>Uploaded files</strong>
            {check.uploaded_files.length ? (
              check.uploaded_files.map((file, index) => (
                <span key={`${file.filename}-${index}`}>
                  {file.filename || "Unnamed file"}
                  {file.character_count ? ` · ${file.character_count.toLocaleString()} chars` : ""}
                  {file.extraction_method ? ` · ${file.extraction_method.replace(/_/g, " ")}` : ""}
                </span>
              ))
            ) : (
              <span>No uploaded files were attached.</span>
            )}
          </div>
          <div>
            <strong>Expected package</strong>
            {check.expected_documents.length ? (
              check.expected_documents.map((item, index) => <span key={index}>{documentLabel(item)}</span>)
            ) : (
              <span>No expected documents were returned.</span>
            )}
          </div>
          <div>
            <strong>Matched files</strong>
            {check.found_documents.length ? (
              check.found_documents.map((item, index) => <span key={index}>{documentMatchLabel(item)}</span>)
            ) : (
              <span>No referenced files were matched.</span>
            )}
          </div>
        </div>
      </details>
    </section>
  );
}

function isCompletenessFinding(finding: Finding) {
  const id = finding.id.toLowerCase();
  return (
    id.startsWith("missing-required-document") ||
    id.startsWith("missing-business-input") ||
    finding.category.toLowerCase() === "completeness"
  );
}

function isLegalEscalationFinding(finding: Finding) {
  return !isCompletenessFinding(finding) && finding.severity === "High";
}

function businessActionLabel(action?: string) {
  if (action === "add_specific_business_question") return "Add the requested file or remove the unavailable reference before rerunning the review.";
  return "Upload this file to the document bundle, or record why it is unavailable before escalation.";
}

function documentLabel(item: Record<string, unknown>) {
  const label = String(item.label || item.normalized_label || "Expected document");
  const basis = item.basis ? ` (${String(item.basis).replace(/_/g, " ")})` : "";
  return `${label}${basis}`;
}

function documentMatchLabel(item: Record<string, unknown>) {
  const label = String(item.expected_label || "Expected document");
  const status = String(item.status || "checked").replace(/_/g, " ");
  const matched = item.matched_filename ? `: ${String(item.matched_filename)}` : "";
  return `${label} - ${status}${matched}`;
}

type CitationFootnote = {
  number: string;
  title: string;
  source?: string;
  excerpt?: string;
  url?: string;
  fallback?: boolean;
  fallback_reason?: string;
  groupLabel?: string;
};

function CitationFootnotes({
  resultId,
  footnotes,
  sourceGroups
}: {
  resultId: string;
  footnotes: CitationFootnote[];
  sourceGroups: NonNullable<RunResult["source_usage"]>;
}) {
  if (!footnotes.length && !sourceGroups.length) return null;
  return (
    <aside className="citation-footnotes" aria-label="Quellen und Fußnoten">
      <div className="citation-footnotes-head">
        <strong>Quellen / Fußnoten</strong>
        {sourceGroups.length ? <span>{sourceGroups.map((source) => source.label).join(", ")}</span> : null}
      </div>
      {footnotes.length ? (
        <ol>
          {footnotes.map((footnote) => (
            <li id={sourceAnchorId(resultId, footnote.number)} key={footnote.number}>
              <span className="footnote-number">{footnote.number}</span>
              <div>
                <strong>{footnote.title}</strong>
                {footnote.source ? <small>{footnote.source}{footnote.groupLabel ? ` · ${footnote.groupLabel}` : ""}</small> : null}
                {footnote.excerpt ? <p>{footnote.excerpt}</p> : null}
                {footnote.fallback ? <span className="source-warning">Fallback evidence</span> : null}
                {footnote.url ? (
                  <a href={footnote.url} target="_blank" rel="noreferrer">
                    Open source <ExternalLink size={13} />
                  </a>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p>Donna used {sourceGroups.length} source group{sourceGroups.length === 1 ? "" : "s"}, but the answer does not contain numbered footnote markers.</p>
      )}
    </aside>
  );
}

function buildCitationFootnotes(content: string, result: RunResult): CitationFootnote[] {
  const citedNumbers = extractCitationNumbers(content);
  if (!citedNumbers.length) return [];

  const byNumber = new Map<string, CitationFootnote>();
  for (const group of result.source_usage ?? []) {
    for (const item of group.items) {
      const number = citationNumberFromTitle(item.title);
      if (!number || byNumber.has(number)) continue;
      byNumber.set(number, {
        number,
        title: item.title?.replace(/^\[\d+\]\s*/, "") || item.source || `Source ${number}`,
        source: item.source,
        excerpt: item.excerpt,
        url: item.url,
        fallback: item.fallback,
        fallback_reason: item.fallback_reason,
        groupLabel: group.label
      });
    }
  }

  for (const item of result.legal_sources ?? []) {
    const number = citationNumberFromTitle(item.title);
    if (!number || byNumber.has(number)) continue;
    byNumber.set(number, {
      number,
      title: item.title.replace(/^\[\d+\]\s*/, ""),
      source: item.source,
      excerpt: item.excerpt,
      url: item.url,
      fallback: item.retrieval_mode === "fallback",
      fallback_reason: item.fallback_reason,
      groupLabel: "Otto Schmidt"
    });
  }

  return citedNumbers.map((number) => byNumber.get(number) ?? {
    number,
    title: `Source ${number}`,
    source: "Referenced in Donna's answer, but no matching source record was returned.",
  });
}

function extractCitationNumbers(content: string) {
  const seen = new Set<string>();
  const numbers: string[] = [];
  for (const match of content.matchAll(/\[(\d+)\]/g)) {
    const number = match[1];
    if (seen.has(number)) continue;
    seen.add(number);
    numbers.push(number);
  }
  return numbers;
}

function linkCitationNumbers(content: string, resultId: string, availableNumbers: Set<string>) {
  return content.replace(/\[(\d+)\]/g, (match, number: string) => {
    if (!availableNumbers.has(number)) return match;
    return `[${toSuperscript(number)}](#${sourceAnchorId(resultId, number)})`;
  });
}

function citationNumberFromTitle(title?: string) {
  return title?.match(/^\[(\d+)\]/)?.[1];
}

function sourceAnchorId(resultId: string, number: string) {
  return `donna-footnote-${resultId.replace(/[^a-zA-Z0-9_-]/g, "-")}-${number}`;
}

function toSuperscript(value: string) {
  const digits: Record<string, string> = {
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
  };
  return value.split("").map((char) => digits[char] ?? char).join("");
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

function mergeUniqueFiles(files: File[], incoming: File[]) {
    const merged = [...files];
    const seen = new Set(merged.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
    incoming.forEach((file) => {
      const key = `${file.name}-${file.size}-${file.lastModified}`;
      if (!seen.has(key)) {
        seen.add(key);
        merged.push(file);
      }
    });
    return merged;
}

function UploadBox({ files, setFiles }: { files: File[]; setFiles: (files: File[]) => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const addFiles = (incoming: File[]) => {
    setFiles(mergeUniqueFiles(files, incoming));
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
        <strong>{isDragging ? "Drop files to attach them" : "Upload document bundle"}</strong>
        <span>Drag files here or browse: contracts, annexes, emails, spreadsheets, PDFs, ZIPs</span>
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
  onDrop,
  onOpenInChat
}: {
  items: HistorySummary[];
  selected: HistoryDetail | null;
  isLoading: boolean;
  error: string | null;
  onRefresh: () => Promise<HistorySummary[]>;
  onSelect: (id: string) => void;
  onDrop: (id: string) => void;
  onOpenInChat: (detail: HistoryDetail) => void;
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
                <div className="history-detail-actions">
                  <HistoryStatus item={selected} />
                  <button className="secondary-button" type="button" onClick={() => onOpenInChat(selected)}>
                    <MessageSquareText size={17} />
                    Reopen in chat
                  </button>
                </div>
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
                      {latestRun.result.agent_steps?.length ? (
                        <div className="history-trace">
                          <h3>Agent trace</h3>
                          <div className="trace-list">
                            {latestRun.result.agent_steps.map((step) => (
                              <div className="trace-item" key={step.id}>
                                <BrainCircuit size={16} />
                                <div>
                                  <strong>{step.label}</strong>
                                  <p>{step.summary}</p>
                                  {step.detail ? <span>{step.detail}</span> : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
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
  const agentMetrics = dashboard?.per_agent_metrics ?? [];
  const topFalse = dashboard?.top_false_escalation_agent;
  const topPositive = dashboard?.top_positive_escalation_agent;

  return (
    <div className="dashboard-view">
      <div className="page-title">
        <div>
          <p className="eyebrow">Performance dashboard</p>
          <h1>AI intake performance and agent analytics.</h1>
        </div>
      </div>

      {/* Summary metrics */}
      <div className="metric-grid">
        <Metric icon={<BarChart3 />} label="Total escalations" value={dashboard?.total_runs ?? 0} />
        <Metric icon={<CheckCircle2 />} label="AI approved" value={dashboard?.auto_cleared ?? 0} />
        <Metric icon={<AlertTriangle />} label="Pending legal" value={dashboard?.legal_recommended ?? 0} />
        <Metric icon={<Gavel />} label="Denied by legal" value={dashboard?.legal_required ?? 0} />
      </div>

      {/* Callout cards for top agents */}
      {(topFalse || topPositive) ? (
        <div className="dashboard-grid">
          {topFalse ? (
            <section className="timeline-card">
              <div className="section-head">
                <div>
                  <p className="eyebrow">Most false escalations</p>
                  <h2>{topFalse.label ?? topFalse.agent_name.replace(/_/g, " ")}</h2>
                </div>
                <span className="status-pill warning">{topFalse.false_escalations} accepted</span>
              </div>
              <p className="dash-callout-desc">This agent raised the most escalations that legal accepted (AI was overly cautious).</p>
            </section>
          ) : null}
          {topPositive ? (
            <section className="timeline-card">
              <div className="section-head">
                <div>
                  <p className="eyebrow">Most valid escalations</p>
                  <h2>{topPositive.label ?? topPositive.agent_name.replace(/_/g, " ")}</h2>
                </div>
                <span className="status-pill">{topPositive.positive_escalations} denied</span>
              </div>
              <p className="dash-callout-desc">This agent raised the most escalations that legal denied (contract had real issues).</p>
            </section>
          ) : null}
        </div>
      ) : null}

      {/* Per-agent analytics table */}
      {agentMetrics.length > 0 ? (
        <section className="timeline-card">
          <div className="section-head">
            <h2>Per-agent performance</h2>
            <span className="status-pill">False escalation = legal accepted (AI was wrong)</span>
          </div>
          <p className="dash-callout-desc">
            Only agents that can independently trigger Legal escalation are shown here. Assistance and aggregation steps stay in the contract trace.
          </p>
          <div className="agent-table">
            <div className="agent-table-head">
              <span>Agent</span>
              <span>Total</span>
              <span>Pending</span>
              <span>Accepted (false)</span>
              <span>Denied (valid)</span>
              <span>False rate</span>
            </div>
            {agentMetrics.map((agent) => (
              <div className="agent-table-row" key={agent.agent_name}>
                <span className="agent-table-name">
                  <strong>{agent.label ?? agent.agent_name.replace(/_/g, " ")}</strong>
                  {agent.description ? <small>{agent.description}</small> : null}
                </span>
                <span>{agent.total}</span>
                <span>{agent.pending}</span>
                <span>{agent.accepted}</span>
                <span>{agent.denied}</span>
                <span className={agent.false_escalation_rate > 0.5 ? "agent-rate high" : agent.false_escalation_rate > 0.25 ? "agent-rate medium" : "agent-rate"}>
                  {Math.round(agent.false_escalation_rate * 100)}%
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

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
            <span className="status-pill">{dashboard?.missing_docs_rate ?? 0}% denial rate</span>
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

// ─────────────────────────────────────────────
// Escalations page
// ─────────────────────────────────────────────

type ChatMessage = { role: "user" | "assistant"; text: string };

type TextSegment = {
  text: string;
  start: number;
  end: number;
  annotation?: TriggerAnnotation;
  showMarker?: boolean;
};

type AnnotationRange = { annotation: TriggerAnnotation; start: number; end: number };

function severityWeight(severity: Severity): number {
  return ({ info: 0, low: 1, medium: 2, high: 3, blocker: 4 } as Record<Severity, number>)[severity] ?? 0;
}

function displaySeverity(severity: Severity): "low" | "medium" | "high" {
  if (severity === "blocker" || severity === "high") return "high";
  if (severity === "medium") return "medium";
  return "low";
}

function documentHighlightStyle(sev: "low" | "medium" | "high"): React.CSSProperties {
  const styles = {
    low: { backgroundColor: "rgba(250,204,21,0.42)", boxShadow: "inset 0 -2px 0 rgba(202,138,4,0.85)" },
    medium: { backgroundColor: "rgba(251,146,60,0.42)", boxShadow: "inset 0 -2px 0 rgba(234,88,12,0.9)" },
    high: { backgroundColor: "rgba(248,113,113,0.48)", boxShadow: "inset 0 -2px 0 rgba(220,38,38,0.95)" },
  } as const;
  return styles[sev];
}

function buildAnnotationRanges(contractText: string, annotations: TriggerAnnotation[]): AnnotationRange[] {
  return annotations
    .filter((a) => typeof a.start === "number" && typeof a.end === "number")
    .map((a) => ({ annotation: a, start: Math.max(0, a.start ?? 0), end: Math.min(contractText.length, a.end ?? 0) }))
    .filter((r) => r.end > r.start);
}

function compareRangePriority(left: AnnotationRange, right: AnnotationRange): number {
  return (
    severityWeight(right.annotation.severity) - severityWeight(left.annotation.severity) ||
    left.start - right.start ||
    right.end - left.end
  );
}

function buildTextSegments(contractText: string, annotations: TriggerAnnotation[]): TextSegment[] {
  const ranges = buildAnnotationRanges(contractText, annotations);
  if (!ranges.length) return [{ text: contractText, start: 0, end: contractText.length }];

  const boundaries = [...new Set([0, contractText.length, ...ranges.flatMap((r) => [r.start, r.end])])]
    .filter((b) => b >= 0 && b <= contractText.length)
    .sort((a, b) => a - b);

  const segments: TextSegment[] = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    const start = boundaries[i];
    const end = boundaries[i + 1];
    if (end <= start) continue;
    const covering = ranges.filter((r) => r.start < end && r.end > start).sort(compareRangePriority);
    const primary = covering[0];
    segments.push({ text: contractText.slice(start, end), start, end, annotation: primary?.annotation, showMarker: primary ? start === primary.start : false });
  }
  return segments.length ? segments : [{ text: contractText, start: 0, end: contractText.length }];
}

function buildAnnotationMarkerMap(annotations: TriggerAnnotation[]): Map<string, number> {
  const sorted = [...annotations].sort((a, b) => {
    const as = typeof a.start === "number" ? a.start : Number.MAX_SAFE_INTEGER;
    const bs = typeof b.start === "number" ? b.start : Number.MAX_SAFE_INTEGER;
    return as - bs || severityWeight(b.severity) - severityWeight(a.severity);
  });
  return new Map(sorted.map((a, i) => [a.id, i + 1]));
}

function uniqueSuggestions(detail: EscalationDetail): Suggestion[] {
  const seen = new Set<string>();
  return [...detail.ai_suggestions, ...detail.trigger_annotations.flatMap((a) => a.suggestions)].filter((s) => {
    const key = `${s.finding_id}:${s.proposed_text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function formatEscDate(value: string): string {
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

function EscSeverityPill({ severity }: { severity: Severity }) {
  const sev = displaySeverity(severity);
  const colours = { low: "#ca8a04", medium: "#ea580c", high: "#dc2626" };
  return (
    <span className="esc-severity-pill" style={{ color: colours[sev], background: colours[sev] + "22" }}>
      {severity}
    </span>
  );
}

function EscStatusPill({ status }: { status: EscalationStatus }) {
  const map: Record<EscalationStatus, { label: string; color: string }> = {
    pending_legal: { label: "Pending legal", color: "#b45309" },
    accepted: { label: "Accepted", color: "#16a34a" },
    denied: { label: "Denied", color: "#dc2626" },
  };
  const m = map[status];
  return (
    <span className="esc-status-pill" style={{ color: m.color, background: m.color + "22" }}>
      {m.label}
    </span>
  );
}

function HighlightedSpan({ annotation, marker, showMarker, text }: { annotation: TriggerAnnotation; marker?: number; showMarker?: boolean; text: string }) {
  const style = documentHighlightStyle(displaySeverity(annotation.severity));
  return (
    <span className="esc-highlight-span" style={style} title={`${annotation.title ?? "Trigger"} — ${annotation.severity}`}>
      {text}
      {showMarker && marker ? (
        <sup className="esc-marker">{marker}</sup>
      ) : null}
    </span>
  );
}

function HighlightedContract({ detail }: { detail: EscalationDetail }) {
  const segments = useMemo(() => buildTextSegments(detail.contract_text, detail.trigger_annotations), [detail.contract_text, detail.trigger_annotations]);
  const markerMap = useMemo(() => buildAnnotationMarkerMap(detail.trigger_annotations), [detail.trigger_annotations]);

  return (
    <div className="esc-contract-card">
      <div className="esc-contract-header">
        <div>
          <p className="eyebrow">Contract Viewer</p>
          <span className="esc-hint">Extracted text with AI flags overlaid</span>
        </div>
        <div className="esc-legend">
          <span><span className="esc-legend-dot" style={{ background: "rgba(250,204,21,0.7)" }} />Low</span>
          <span><span className="esc-legend-dot" style={{ background: "rgba(251,146,60,0.7)" }} />Medium</span>
          <span><span className="esc-legend-dot" style={{ background: "rgba(248,113,113,0.7)" }} />High</span>
        </div>
      </div>
      {detail.contract_text ? (
        <div className="esc-contract-scroll">
          <article className="esc-paper">
            <div className="esc-paper-header">
              <span>{detail.ticket_id}</span>
              <span>{detail.version_number ? `Version ${detail.version_number}` : "Unversioned"}</span>
            </div>
            <pre className="esc-contract-pre">
              {segments.map((seg, i) =>
                seg.annotation ? (
                  <HighlightedSpan
                    key={`${seg.annotation.id}-${seg.start}-${i}`}
                    annotation={seg.annotation}
                    marker={markerMap.get(seg.annotation.id)}
                    showMarker={seg.showMarker}
                    text={seg.text}
                  />
                ) : (
                  <span key={`t-${seg.start}-${i}`}>{seg.text}</span>
                )
              )}
            </pre>
          </article>
        </div>
      ) : (
        <div className="quiet-box">Contract text was not stored for this escalation.</div>
      )}
    </div>
  );
}

function AnnotationList({ detail }: { detail: EscalationDetail }) {
  const markers = useMemo(() => buildAnnotationMarkerMap(detail.trigger_annotations), [detail.trigger_annotations]);
  const sorted = useMemo(() =>
    [...detail.trigger_annotations].sort((a, b) => {
      const as = typeof a.start === "number" ? a.start : Number.MAX_SAFE_INTEGER;
      const bs = typeof b.start === "number" ? b.start : Number.MAX_SAFE_INTEGER;
      return as - bs;
    }),
    [detail.trigger_annotations]
  );

  if (!sorted.length) return <div className="quiet-box">No trigger annotations stored.</div>;
  return (
    <div className="esc-annotation-list">
      {sorted.map((ann) => {
        const marker = markers.get(ann.id);
        return (
          <div className="esc-annotation-card" key={ann.id}>
            <div className="esc-annotation-meta">
              {marker ? <span className="esc-marker-badge">{marker}</span> : null}
              <EscSeverityPill severity={ann.severity} />
              <span className="esc-agent-label">{ann.agent_name.replace(/_/g, " ")}</span>
            </div>
            <strong className="esc-annotation-title">{ann.title}</strong>
            <p className="esc-annotation-desc">{ann.description}</p>
            {ann.text ? <blockquote className="esc-annotation-quote">{ann.text}</blockquote> : null}
            {ann.suggestions[0] ? (
              <div className="esc-fix-box">
                <span className="esc-fix-label">AI fix</span>
                <p>{ann.suggestions[0].proposed_text}</p>
              </div>
            ) : null}
            {ann.ruling ? (
              <div className="esc-ruling-box">
                <span className="esc-ruling-citation">{ann.ruling.citation}</span>
                <span className="esc-ruling-source">{ann.ruling.source}</span>
                <p>{ann.ruling.quote}</p>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function EscalationContextPanel({
  detail,
  chatMessages,
  chatQuestion,
  chatLoading,
  decisionNotes,
  fixSuggestions,
  decisionLoading,
  onQuestionChange,
  onSubmitQuestion,
  onNotesChange,
  onFixSuggestionsChange,
  onDecision,
}: {
  detail: EscalationDetail | null;
  chatMessages: ChatMessage[];
  chatQuestion: string;
  chatLoading: boolean;
  decisionNotes: string;
  fixSuggestions: string;
  decisionLoading: boolean;
  onQuestionChange: (v: string) => void;
  onSubmitQuestion: (e: React.FormEvent) => void;
  onNotesChange: (v: string) => void;
  onFixSuggestionsChange: (v: string) => void;
  onDecision: (d: "accepted" | "denied") => void;
}) {
  if (!detail) return <div className="esc-context-panel"><div className="quiet-box">Select a pending ticket.</div></div>;
  const canDecide = detail.status === "pending_legal";
  const suggestions = uniqueSuggestions(detail);

  return (
    <aside className="esc-context-panel">
      {/* AI flags */}
      <div className="esc-section">
        <div className="section-head compact">
          <h2>AI flags</h2>
          <span className="counter">{detail.trigger_annotations.length}</span>
        </div>
        <AnnotationList detail={detail} />
      </div>

      {/* Suggested fixes */}
      {(suggestions.length > 0 || detail.fix_suggestions.length > 0) ? (
        <div className="esc-section">
          <div className="section-head compact"><h2>Suggested fixes</h2></div>
          <div className="esc-annotation-list">
            {suggestions.map((s) => (
              <div className="esc-annotation-card" key={`${s.finding_id}-${s.proposed_text}`}>
                <span className="esc-agent-label">{s.finding_id}</span>
                <p className="esc-annotation-desc">{s.proposed_text}</p>
                <p className="esc-annotation-desc" style={{ opacity: 0.7 }}>{s.rationale}</p>
              </div>
            ))}
            {detail.fix_suggestions.map((fix) => (
              <div className="esc-fix-box" key={fix}>
                <span className="esc-fix-label">Legal fix</span>
                <p>{fix}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Chat */}
      <div className="esc-section">
        <div className="section-head compact"><h2>Ask about this contract</h2></div>
        <div className="esc-chat">
          {chatMessages.length === 0 ? <p className="esc-chat-empty">No messages yet.</p> : null}
          {chatMessages.map((msg, i) => (
            <div key={`${msg.role}-${i}`} className={`esc-chat-msg ${msg.role}`}>{msg.text}</div>
          ))}
          {chatLoading ? <div className="esc-chat-msg assistant"><Loader2 className="spin" size={14} /> Checking context…</div> : null}
        </div>
        <form onSubmit={onSubmitQuestion} className="esc-chat-form">
          <textarea
            value={chatQuestion}
            onChange={(e) => onQuestionChange(e.target.value)}
            placeholder="Ask about this contract…"
            rows={3}
          />
          <button type="submit" className="primary-button" disabled={chatLoading || !chatQuestion.trim()}>
            <Send size={15} /> Ask
          </button>
        </form>
      </div>

      {/* Legal decision */}
      <div className="esc-section">
        <div className="section-head compact"><h2>Legal decision</h2></div>
        {!canDecide ? (
          <div className="quiet-box">
            Decision recorded as <strong>{detail.status.replace("_", " ")}</strong>
            {detail.legal_notes ? `: ${detail.legal_notes}` : "."}
          </div>
        ) : null}
        <textarea
          value={decisionNotes}
          onChange={(e) => onNotesChange(e.target.value)}
          placeholder="Legal notes…"
          rows={3}
          disabled={!canDecide || decisionLoading}
          className="esc-notes-input"
        />
        <textarea
          value={fixSuggestions}
          onChange={(e) => onFixSuggestionsChange(e.target.value)}
          placeholder="Fix suggestions for denied escalations, one per line…"
          rows={4}
          disabled={!canDecide || decisionLoading}
          className="esc-notes-input"
        />
        <div className="esc-decision-row">
          <button
            className="secondary-button esc-accept-btn"
            disabled={!canDecide || decisionLoading}
            onClick={() => onDecision("accepted")}
          >
            <CheckCircle2 size={15} /> Accept
          </button>
          <button
            className="secondary-button esc-deny-btn"
            disabled={!canDecide || decisionLoading}
            onClick={() => onDecision("denied")}
          >
            <AlertTriangle size={15} /> Deny
          </button>
        </div>
      </div>
    </aside>
  );
}

function EscalationsView() {
  const [items, setItems] = useState<EscalationListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [fixSuggestions, setFixSuggestions] = useState("");
  const [decisionLoading, setDecisionLoading] = useState(false);

  const refreshItems = async () => {
    const data = await listEscalations();
    setItems(data.items);
    setSelectedId((cur) => (cur && data.items.some((i) => i.id === cur) ? cur : data.items[0]?.id ?? null));
  };

  useEffect(() => {
    setLoading(true);
    refreshItems().then(() => setError(null)).catch(() => setError("Could not load escalations.")).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    setDetailLoading(true);
    setChatMessages([]);
    setDecisionNotes("");
    setFixSuggestions("");
    getEscalation(selectedId)
      .then((d) => { setDetail(d); setError(null); })
      .catch(() => setError("Could not load escalation detail."))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const submitQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = chatQuestion.trim();
    if (!detail || !q || chatLoading) return;
    setChatQuestion("");
    setChatLoading(true);
    setChatMessages((msgs) => [...msgs, { role: "user", text: q }]);
    try {
      const resp = await askEscalationQuestion(detail.id, q);
      setChatMessages((msgs) => [...msgs, { role: "assistant", text: resp.answer }]);
    } catch {
      setChatMessages((msgs) => [...msgs, { role: "assistant", text: "Could not answer from the escalation context." }]);
    } finally {
      setChatLoading(false);
    }
  };

  const submitDecision = async (decision: "accepted" | "denied") => {
    if (!detail || decisionLoading) return;
    const fixes = fixSuggestions.split("\n").map((s) => s.trim()).filter(Boolean);
    if (decision === "denied" && !fixes.length) {
      setError("Denied escalations require at least one legal fix suggestion.");
      return;
    }
    setDecisionLoading(true);
    setError(null);
    try {
      const updated = await decideEscalation(detail.id, { decision, notes: decisionNotes.trim() || undefined, fix_suggestions: fixes, decided_by: "legal-team" });
      setDetail(updated);
      await refreshItems();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save legal decision.");
    } finally {
      setDecisionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="workspace">
        <div className="empty-state">
          <Loader2 className="spin" size={24} />
          <div><strong>Loading escalations…</strong></div>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace esc-workspace">
      <div className="page-title">
        <div>
          <p className="eyebrow">Legal Escalations</p>
          <h1>Review flagged contracts, inspect highlights, and record legal decisions.</h1>
        </div>
      </div>
      {error ? <div className="error-box">{error}</div> : null}
      {items.length === 0 ? (
        <div className="empty-state">
          <AlertTriangle size={27} />
          <div>
            <strong>No pending escalations</strong>
            <p>Run a final-version contract review to generate escalation tickets.</p>
          </div>
        </div>
      ) : (
        <div className="esc-shell">
          {/* Left: queue */}
          <div className="esc-queue">
            <div className="esc-queue-header">
              <span className="eyebrow">Pending tickets</span>
              <strong className="esc-queue-count">{items.length}</strong>
            </div>
            {items.map((item) => (
              <button
                key={item.id}
                className={selectedId === item.id ? "esc-queue-item active" : "esc-queue-item"}
                onClick={() => setSelectedId(item.id)}
              >
                <div className="esc-queue-item-pills">
                  <EscStatusPill status={item.status} />
                  <EscSeverityPill severity={item.highest_severity} />
                </div>
                <strong className="esc-queue-ticket">{item.ticket_id}</strong>
                <p className="esc-queue-reason">{item.reason}</p>
                <span className="esc-queue-meta">{formatEscDate(item.created_at)}</span>
              </button>
            ))}
          </div>

          {/* Centre: contract viewer */}
          <div className="esc-center">
            {detailLoading ? (
              <div className="empty-state"><Loader2 className="spin" size={24} /></div>
            ) : detail ? (
              <>
                <div className="esc-detail-head">
                  <div>
                    <p className="eyebrow">Legal Ticket</p>
                    <h2 className="esc-ticket-id">{detail.ticket_id}</h2>
                    <p className="esc-ticket-reason">{detail.reason}</p>
                  </div>
                  <EscStatusPill status={detail.status} />
                </div>
                <HighlightedContract detail={detail} />
              </>
            ) : (
              <div className="empty-state"><HistoryIcon size={24} /><div><strong>Select a ticket</strong></div></div>
            )}
          </div>

          {/* Right: context panel */}
          <EscalationContextPanel
            detail={detail}
            chatMessages={chatMessages}
            chatQuestion={chatQuestion}
            chatLoading={chatLoading}
            decisionNotes={decisionNotes}
            fixSuggestions={fixSuggestions}
            decisionLoading={decisionLoading}
            onQuestionChange={setChatQuestion}
            onSubmitQuestion={submitQuestion}
            onNotesChange={setDecisionNotes}
            onFixSuggestionsChange={setFixSuggestions}
            onDecision={submitDecision}
          />
        </div>
      )}
    </div>
  );
}

function Band({ band, severity }: { band: Finding["band"]; severity: Finding["severity"] }) {
  return <span className={`band ${band}`}>{band === "redline" ? "Red line" : band === "fallback" ? "Fallback" : "Standard"} / {severity}</span>;
}

export default App;
