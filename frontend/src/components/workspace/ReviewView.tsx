import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload, Sparkles, Loader2, FileText, Send, Paperclip, CheckCircle2, ShieldAlert, XCircle,
  AlertTriangle, FileWarning,
} from "lucide-react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import {
  type ContractIdentity,
  type ReviewAuditResult,
  type ReviewResponse,
  type ReviewViolation,
  reviewContractFile,
  reviewContractText,
  toAuditResult,
} from "@/api/client";
import { SAMPLE_CONTRACT } from "@/lib/sampleContract";
import { lookupRule } from "@/lib/playbook";
import { cn } from "@/lib/utils";

type ChatMsg =
  | { role: "user"; kind: "upload"; fileName: string; preview: string }
  | { role: "user"; kind: "text"; content: string }
  | { role: "assistant"; kind: "thinking" }
  | { role: "assistant"; kind: "audit"; result: ReviewAuditResult };

const DEFAULT_IDENTITY: ContractIdentity = {
  contractType: "data_protection",
  vendor: "GlobalCloud Services Ltd.",
  effectiveStartDate: "2026-01-01",
  effectiveEndDate: "2026-12-31",
};

export const ReviewView = () => {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [identity, setIdentity] = useState<ContractIdentity>(DEFAULT_IDENTITY);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (loading) return;
    if (file.size > 10_000_000) {
      toast.error("File too large (max 10 MB).");
      return;
    }

    const reviewIdentity = buildIdentity(identity, file.name);
    if (!reviewIdentity) return;

    const preview = await previewFile(file);
    setMessages((m) => [
      ...m,
      { role: "user", kind: "upload", fileName: file.name, preview },
    ]);
    void runReview(() => reviewContractFile(file, reviewIdentity));
  };

  const loadSample = () => {
    if (loading) return;
    const sampleIdentity = { ...identity, vendor: identity.vendor.trim() || DEFAULT_IDENTITY.vendor };
    setIdentity(sampleIdentity);
    setMessages((m) => [
      ...m,
      { role: "user", kind: "upload", fileName: "sample-dpa.txt", preview: SAMPLE_CONTRACT.slice(0, 240) },
    ]);
    void runReview(() => reviewContractText(SAMPLE_CONTRACT, sampleIdentity));
  };

  const sendText = () => {
    if (!input.trim() || loading) return;
    if (input.trim().length < 50) {
      toast.error("Paste full contract text (min 50 chars) or upload a file.");
      return;
    }

    const reviewIdentity = buildIdentity(identity, "pasted-contract.txt");
    if (!reviewIdentity) return;

    const text = input.trim();
    setMessages((m) => [...m, { role: "user", kind: "text", content: text.slice(0, 600) + (text.length > 600 ? "..." : "") }]);
    setInput("");
    void runReview(() => reviewContractText(text, reviewIdentity));
  };

  const runReview = async (action: () => Promise<ReviewResponse>) => {
    setLoading(true);
    setMessages((m) => [...m, { role: "assistant", kind: "thinking" }]);
    try {
      const review = await action();
      const result = toAuditResult(review);
      setMessages((m) => [
        ...m.filter((x) => !(x.role === "assistant" && x.kind === "thinking")),
        { role: "assistant", kind: "audit", result },
      ]);
      toast.success(result.escalation_required ? "Review complete and escalated" : "Review complete");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Review failed";
      setMessages((m) => m.filter((x) => !(x.role === "assistant" && x.kind === "thinking")));
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const empty = messages.length === 0;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 py-8">
            {empty ? (
              <Welcome onSample={loadSample} onUpload={() => fileRef.current?.click()} />
            ) : (
              <div className="space-y-6">
                <AnimatePresence initial={false}>
                  {messages.map((m, i) => (
                    <MessageBubble key={i} m={m} />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>

        <div className="border-t border-border/60 bg-background/80 backdrop-blur">
          <div className="max-w-3xl mx-auto px-6 py-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
              <IdentityField label="Vendor">
                <input
                  value={identity.vendor}
                  onChange={(event) => setIdentity((current) => ({ ...current, vendor: event.target.value }))}
                  className="w-full min-w-0 bg-card/60 border border-border/70 rounded-md px-3 py-2 text-xs focus:outline-none focus:border-primary/60"
                />
              </IdentityField>
              <IdentityField label="Contract Type">
                <select
                  value={identity.contractType}
                  onChange={(event) => setIdentity((current) => ({ ...current, contractType: event.target.value }))}
                  className="w-full min-w-0 bg-card/60 border border-border/70 rounded-md px-3 py-2 text-xs focus:outline-none focus:border-primary/60"
                >
                  <option value="data_protection">Data protection</option>
                  <option value="litigation">Litigation</option>
                  <option value="general">General</option>
                </select>
              </IdentityField>
              <IdentityField label="Start Date">
                <input
                  type="date"
                  value={identity.effectiveStartDate}
                  onChange={(event) => setIdentity((current) => ({ ...current, effectiveStartDate: event.target.value }))}
                  className="w-full min-w-0 bg-card/60 border border-border/70 rounded-md px-3 py-2 text-xs focus:outline-none focus:border-primary/60"
                />
              </IdentityField>
              <IdentityField label="End Date">
                <input
                  type="date"
                  value={identity.effectiveEndDate}
                  onChange={(event) => setIdentity((current) => ({ ...current, effectiveEndDate: event.target.value }))}
                  className="w-full min-w-0 bg-card/60 border border-border/70 rounded-md px-3 py-2 text-xs focus:outline-none focus:border-primary/60"
                />
              </IdentityField>
            </div>

            <div className="rounded-2xl border border-border/80 bg-card/60 shadow-card focus-within:border-primary/60 transition-colors">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendText();
                  }
                }}
                placeholder="Paste contract text, or upload a DPA to review..."
                className="w-full bg-transparent resize-none px-5 py-4 text-sm placeholder:text-muted-foreground focus:outline-none min-h-[60px] max-h-[200px]"
                rows={2}
              />
              <div className="flex items-center justify-between px-3 pb-3">
                <div className="flex items-center gap-1">
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".txt,.md,.doc,.docx,.pdf,.xls,.xlsx,.csv,.json"
                    className="hidden"
                    onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => fileRef.current?.click()}
                    disabled={loading}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Paperclip className="h-4 w-4 mr-1.5" />
                    Upload
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={loadSample} disabled={loading} className="text-muted-foreground hover:text-foreground">
                    <Sparkles className="h-4 w-4 mr-1.5" />
                    Sample
                  </Button>
                </div>
                <Button
                  type="button"
                  size="sm"
                  onClick={sendText}
                  disabled={loading || !input.trim()}
                  className="gradient-primary border-0 text-primary-foreground"
                >
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            <div className="text-[10px] text-muted-foreground text-center mt-2 font-mono">
              BMW playbook checks + German legal evidence. Legal counsel owns final approval.
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
};

const IdentityField = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="block min-w-0">
    <span className="block text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-semibold mb-1">
      {label}
    </span>
    {children}
  </label>
);

const Welcome = ({ onSample, onUpload }: { onSample: () => void; onUpload: () => void }) => (
  <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center pt-12">
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border/80 bg-card/60 text-xs text-muted-foreground mb-6">
      <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
      BMW playbook + German legal evidence
    </div>
    <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">
      Review a contract in <span className="text-gradient">seconds</span>
    </h1>
    <p className="text-muted-foreground max-w-xl mx-auto mb-10">
      Drop a Data Processing Agreement and Harvey will check the draft against BMW mock rules and legal evidence,
      then create an escalation when legal judgment is required.
    </p>
    <div className="grid sm:grid-cols-2 gap-3 max-w-xl mx-auto">
      <button
        onClick={onUpload}
        className="group rounded-2xl border border-border/60 gradient-card p-5 text-left hover:border-primary/60 transition-colors"
      >
        <Upload className="h-5 w-5 text-primary mb-2" />
        <div className="font-semibold mb-1">Upload contract</div>
        <div className="text-xs text-muted-foreground">PDF, Word, Excel, text, Markdown, CSV, or JSON.</div>
      </button>
      <button
        onClick={onSample}
        className="group rounded-2xl border border-border/60 gradient-card p-5 text-left hover:border-primary/60 transition-colors"
      >
        <Sparkles className="h-5 w-5 text-primary mb-2" />
        <div className="font-semibold mb-1">Try a sample</div>
        <div className="text-xs text-muted-foreground">DPA with playbook and legal review triggers.</div>
      </button>
    </div>
  </motion.div>
);

const MessageBubble = ({ m }: { m: ChatMsg }) => {
  if (m.role === "user" && m.kind === "upload") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm border border-primary/30 bg-primary/10 p-3 px-4">
          <div className="flex items-center gap-2 text-xs font-medium text-primary mb-1.5">
            <FileText className="h-3.5 w-3.5" />
            {m.fileName}
          </div>
          <div className="text-xs text-muted-foreground font-mono line-clamp-3 whitespace-pre-wrap">
            {m.preview}
          </div>
        </div>
      </motion.div>
    );
  }
  if (m.role === "user" && m.kind === "text") {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary text-primary-foreground p-3 px-4 text-sm whitespace-pre-wrap">
          {m.content}
        </div>
      </motion.div>
    );
  }
  if (m.role === "assistant" && m.kind === "thinking") {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-3 text-muted-foreground">
        <div className="h-8 w-8 rounded-lg gradient-primary grid place-items-center shrink-0">
          <Loader2 className="h-4 w-4 animate-spin text-primary-foreground" />
        </div>
        <div className="text-sm">Checking the draft against the playbook and legal evidence...</div>
      </motion.div>
    );
  }
  return <AuditMessage result={(m as Extract<ChatMsg, { kind: "audit" }>).result} />;
};

const AuditMessage = ({ result }: { result: ReviewAuditResult }) => {
  const map = {
    Approved: { icon: CheckCircle2, color: "success", label: "Approved" },
    Escalated: { icon: ShieldAlert, color: "warning", label: "Escalated" },
    Rejected: { icon: XCircle, color: "destructive", label: "Needs revision" },
  } as const;
  const v = map[result.status];
  const Icon = v.icon;
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
      <div className="h-8 w-8 rounded-lg gradient-primary grid place-items-center shrink-0 mt-1">
        <Sparkles className="h-4 w-4 text-primary-foreground" />
      </div>
      <div className="flex-1 space-y-4 min-w-0">
        <div className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card">
          <div className="flex items-center gap-3 flex-wrap">
            <div
              className="h-10 w-10 rounded-lg grid place-items-center"
              style={{ background: `hsl(var(--${v.color}) / 0.12)`, border: `1px solid hsl(var(--${v.color}) / 0.4)` }}
            >
              <Icon className="h-5 w-5" style={{ color: `hsl(var(--${v.color}))` }} />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Verdict</div>
              <div className="text-xl font-bold" style={{ color: `hsl(var(--${v.color}))` }}>{v.label}</div>
            </div>
            <div className="ml-auto flex gap-3 text-xs text-muted-foreground flex-wrap justify-end">
              <span><strong className="text-severity-high">{result.violations.filter((finding) => finding.severity === "High").length}</strong> High</span>
              <span><strong className="text-severity-medium">{result.violations.filter((finding) => finding.severity === "Medium").length}</strong> Medium</span>
              <span><strong className="text-foreground font-mono">{Math.round(result.confidence * 100)}%</strong> confidence</span>
            </div>
          </div>
          <p className="text-sm text-foreground mt-3 leading-relaxed">{result.contract_summary}</p>
          {(result.contract_id || result.version_number) && (
            <div className="text-[10px] text-muted-foreground mt-3 font-mono">
              {result.contract_id}
              {result.version_number ? ` / v${result.version_number}` : ""}
            </div>
          )}
        </div>

        {result.escalation_required && (
          <div
            className="rounded-2xl border-2 p-4 flex items-start gap-3"
            style={{
              borderColor: "hsl(var(--warning) / 0.5)",
              background: "linear-gradient(135deg, hsl(var(--warning) / 0.08), hsl(var(--warning) / 0.02))",
            }}
          >
            <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" style={{ color: "hsl(var(--warning))" }} />
            <div>
              <div className="font-bold text-sm" style={{ color: "hsl(var(--warning))" }}>
                Requires legal counsel review
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {result.escalation_id ? `Escalation ${result.escalation_id} was created in the legal queue.` : "Open the escalation queue for legal context."}
              </div>
            </div>
          </div>
        )}

        {result.violations.length > 0 ? (
          <div className="space-y-3">
            {result.violations.map((violation, i) => (
              <ViolationCard key={`${violation.reference}-${i}`} v={violation} index={i + 1} />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-success/30 p-6 text-center" style={{ background: "hsl(var(--success) / 0.05)" }}>
            <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-success" />
            <div className="font-semibold">No material findings detected</div>
          </div>
        )}
      </div>
    </motion.div>
  );
};

const ViolationCard = ({ v, index }: { v: ReviewViolation; index: number }) => {
  const sev = v.severity === "High" ? "high" : "medium";
  const rule = lookupRule(v.reference);
  return (
    <div className={cn("rounded-2xl border border-border/60 gradient-card overflow-hidden shadow-card")}>
      <div className="p-4 border-b border-border/60">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <span className="text-[10px] font-mono text-muted-foreground">#{String(index).padStart(2, "0")}</span>
          <span
            className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
            style={{ background: `hsl(var(--severity-${sev}) / 0.15)`, color: `hsl(var(--severity-${sev}))` }}
          >
            {v.severity}
          </span>
          {rule ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border border-border bg-background/40 hover:border-primary/60 transition-colors flex items-center gap-1">
                  <FileWarning className="h-3 w-3" />
                  {rule.id}
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <div className="text-[10px] uppercase tracking-wider opacity-70 mb-1">{rule.source} - {rule.id}</div>
                <div className="font-semibold mb-1">{rule.title}</div>
                <div className="text-xs opacity-90">{rule.body}</div>
              </TooltipContent>
            </Tooltip>
          ) : (
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border border-border bg-background/40">
              {v.reference}
            </span>
          )}
          {v.source && <span className="text-[10px] text-muted-foreground truncate max-w-[220px]">{v.source}</span>}
        </div>
        <div className="prose prose-sm prose-invert max-w-none text-sm text-foreground">
          <ReactMarkdown>{v.issue}</ReactMarkdown>
        </div>
      </div>
      <div className="p-3 bg-background/40">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-2 px-1">
          Original - Suggested fix
        </div>
        <div className="rounded-lg overflow-hidden border border-border/60 text-xs">
          <ReactDiffViewer
            oldValue={v.clause}
            newValue={v.suggestion}
            splitView={false}
            compareMethod={DiffMethod.WORDS}
            hideLineNumbers
            useDarkTheme
            styles={{
              variables: {
                dark: {
                  diffViewerBackground: "hsl(220 30% 9%)",
                  diffViewerColor: "hsl(210 40% 90%)",
                  addedBackground: "hsl(152 60% 25% / 0.35)",
                  addedColor: "hsl(152 80% 80%)",
                  removedBackground: "hsl(0 75% 35% / 0.3)",
                  removedColor: "hsl(0 80% 85%)",
                  wordAddedBackground: "hsl(152 70% 40% / 0.5)",
                  wordRemovedBackground: "hsl(0 75% 50% / 0.45)",
                  gutterBackground: "transparent",
                  gutterBackgroundDark: "transparent",
                  emptyLineBackground: "transparent",
                },
              },
              contentText: { fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", lineHeight: "1.6" },
            }}
          />
        </div>
        {v.rationale && <p className="text-xs text-muted-foreground mt-2 px-1">{v.rationale}</p>}
      </div>
    </div>
  );
};

function buildIdentity(identity: ContractIdentity, fileName: string): ContractIdentity | null {
  const candidate = {
    ...identity,
    vendor: identity.vendor.trim() || inferVendor(fileName),
    contractType: identity.contractType.trim() || "data_protection",
  };

  if (!candidate.vendor || !candidate.effectiveStartDate || !candidate.effectiveEndDate) {
    toast.error("Vendor, start date, and end date are required.");
    return null;
  }
  if (candidate.effectiveEndDate < candidate.effectiveStartDate) {
    toast.error("End date must be on or after start date.");
    return null;
  }

  return candidate;
}

function inferVendor(fileName: string) {
  const baseName = fileName.replace(/\.[^/.]+$/, "").replace(/[-_]+/g, " ").trim();
  return baseName || DEFAULT_IDENTITY.vendor;
}

async function previewFile(file: File) {
  if (/\.(txt|md|csv|json)$/i.test(file.name)) {
    try {
      const text = await file.text();
      return text.slice(0, 240) + (text.length > 240 ? "..." : "");
    } catch {
      return `${formatBytes(file.size)} uploaded for backend extraction.`;
    }
  }

  return `${formatBytes(file.size)} uploaded for backend extraction.`;
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
