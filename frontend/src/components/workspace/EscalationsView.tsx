import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle, FileText, ShieldAlert, XCircle, Clock, Loader2, MessageSquare,
  CheckCircle2, Send, Scale,
} from "lucide-react";
import {
  type EscalationDetail,
  type EscalationListItem,
  type EscalationStatus,
  type Severity,
  type Suggestion,
  type TriggerAnnotation,
  askEscalationQuestion,
  decideEscalation,
  getEscalation,
  listEscalations,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

type TextSegment = {
  text: string;
  annotation?: TriggerAnnotation;
};

export const EscalationsView = () => {
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

  const refreshItems = useCallback(async () => {
    const payload = await listEscalations();
    setItems(payload.items);
    setSelectedId((current) => {
      if (current && payload.items.some((item) => item.id === current)) {
        return current;
      }
      return payload.items[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    refreshItems()
      .then(() => {
        if (active) setError(null);
      })
      .catch(() => {
        if (active) setError("Could not load escalations.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshItems]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    let active = true;
    setDetailLoading(true);
    setChatMessages([]);
    setDecisionNotes("");
    setFixSuggestions("");
    getEscalation(selectedId)
      .then((payload) => {
        if (active) {
          setDetail(payload);
          setError(null);
        }
      })
      .catch(() => {
        if (active) setError("Could not load escalation detail.");
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedId]);

  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = chatQuestion.trim();
    if (!detail || !question || chatLoading) return;

    setChatQuestion("");
    setChatLoading(true);
    setChatMessages((messages) => [...messages, { role: "user", text: question }]);
    try {
      const response = await askEscalationQuestion(detail.id, question);
      setChatMessages((messages) => [...messages, { role: "assistant", text: response.answer }]);
    } catch {
      setChatMessages((messages) => [
        ...messages,
        { role: "assistant", text: "Could not answer from the escalation context." },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const submitDecision = async (decision: "accepted" | "denied") => {
    if (!detail || decisionLoading) return;
    const fixes = fixSuggestions
      .split("\n")
      .map((fix) => fix.trim())
      .filter(Boolean);

    if (decision === "denied" && fixes.length === 0) {
      toast.error("Denied escalations require at least one legal fix suggestion.");
      return;
    }

    setDecisionLoading(true);
    try {
      const updated = await decideEscalation(detail.id, {
        decision,
        notes: decisionNotes.trim() || undefined,
        fix_suggestions: fixes,
        decided_by: "legal-team",
      });
      setDetail(updated);
      await refreshItems();
      toast.success(decision === "accepted" ? "Escalation accepted" : "Escalation denied with fixes");
    } catch (event) {
      toast.error(event instanceof Error ? event.message : "Could not save legal decision.");
    } finally {
      setDecisionLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading escalations...
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="text-center max-w-md">
          <div className="h-16 w-16 mx-auto rounded-2xl bg-warning/10 border border-warning/30 grid place-items-center mb-5">
            <AlertTriangle className="h-7 w-7 text-warning" />
          </div>
          <h2 className="text-2xl font-bold mb-2">No escalations yet</h2>
          <p className="text-muted-foreground">
            Run a contract review. High-risk contracts that require legal judgment will appear here with context and highlights.
          </p>
          {error && <p className="text-sm text-destructive mt-4">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[300px_minmax(0,1fr)_340px] h-full overflow-hidden">
      <EscalationQueue items={items} selectedId={selectedId} onSelect={setSelectedId} />

      <div className="overflow-y-auto border-r border-border/60">
        {error && <div className="m-4 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
        {detailLoading && (
          <div className="h-full grid place-items-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        )}
        {!detailLoading && detail && <EscalationDetailView detail={detail} />}
      </div>

      <ContextPanel
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
  );
};

const EscalationQueue = ({
  items,
  selectedId,
  onSelect,
}: {
  items: EscalationListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) => (
  <div className="border-r border-border/60 overflow-y-auto bg-card/30">
    <div className="px-5 py-4 border-b border-border/60">
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">Legal Queue</div>
      <div className="text-2xl font-bold mt-0.5">{items.length}</div>
    </div>
    <div className="divide-y divide-border/40">
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect(item.id)}
          className={cn(
            "w-full text-left px-5 py-4 hover:bg-muted/30 transition-colors",
            selectedId === item.id && "bg-primary/10 border-l-2 border-primary",
          )}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <StatusPill status={item.status} />
            {item.next_owner && (
              <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground">
                {item.next_owner}
              </span>
            )}
          </div>
          <div className="text-sm font-medium line-clamp-2 flex items-start gap-1.5">
            <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
            {item.reason}
          </div>
          <div className="text-[10px] text-muted-foreground mt-2 flex items-center gap-1.5 font-mono">
            <Clock className="h-3 w-3" />
            {formatDate(item.created_at)}
          </div>
          <div className="text-[10px] text-muted-foreground mt-1 truncate">
            {item.contract_id}
            {item.version_number ? ` / v${item.version_number}` : ""}
          </div>
        </button>
      ))}
    </div>
  </div>
);

const EscalationDetailView = ({ detail }: { detail: EscalationDetail }) => {
  const highestSeverity = getHighestSeverity(detail.trigger_annotations);

  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-1">
              Escalation
            </div>
            <h1 className="text-2xl font-bold flex items-start gap-2">
              <Scale className="h-5 w-5 text-primary mt-1 shrink-0" />
              {detail.reason}
            </h1>
            <div className="text-sm text-muted-foreground mt-1">
              {detail.contract_id}
              {detail.version_number ? ` / version ${detail.version_number}` : ""} - {formatDate(detail.created_at)}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusPill status={detail.status} />
            <SeverityPill severity={highestSeverity} />
          </div>
        </div>

        <HighlightedContract detail={detail} />
        <AgentFindings detail={detail} />
      </motion.div>
    </div>
  );
};

const HighlightedContract = ({ detail }: { detail: EscalationDetail }) => {
  const segments = useMemo(
    () => buildTextSegments(detail.contract_text, detail.trigger_annotations),
    [detail.contract_text, detail.trigger_annotations],
  );

  return (
    <section className="rounded-2xl border border-border/60 bg-card/40 shadow-card overflow-hidden mb-6">
      <div className="px-5 py-3 border-b border-border/60 flex items-center justify-between gap-3 flex-wrap">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
          Source document with highlights
        </div>
        <SeverityLegend />
      </div>
      {detail.contract_text ? (
        <pre className="px-6 py-6 text-xs leading-relaxed font-mono whitespace-pre-wrap break-words text-foreground/90 max-h-[560px] overflow-y-auto">
          {segments.map((segment, index) =>
            segment.annotation ? (
              <HighlightedSpan key={`${segment.annotation.id}-${index}`} annotation={segment.annotation} text={segment.text} />
            ) : (
              <span key={`text-${index}`}>{segment.text}</span>
            ),
          )}
        </pre>
      ) : (
        <div className="p-6 text-sm text-muted-foreground">Contract text was not stored for this escalation.</div>
      )}
    </section>
  );
};

const HighlightedSpan = ({ annotation, text }: { annotation: TriggerAnnotation; text: string }) => {
  const sev = displaySeverity(annotation.severity);
  return (
    <span
      className="relative px-1 py-0.5 rounded cursor-help"
      style={{
        background: `hsl(var(--severity-${sev}) / 0.18)`,
        boxShadow: `inset 0 -2px 0 hsl(var(--severity-${sev}) / 0.7)`,
      }}
      title={`${annotation.title ?? "Trigger"} - ${annotation.severity}`}
    >
      {text}
    </span>
  );
};

const AgentFindings = ({ detail }: { detail: EscalationDetail }) => {
  const groups = detail.trigger_annotations.reduce<Record<string, TriggerAnnotation[]>>((accumulator, annotation) => {
    accumulator[annotation.agent_name] = [...(accumulator[annotation.agent_name] ?? []), annotation];
    return accumulator;
  }, {});

  return (
    <div className="space-y-4">
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
        Agent findings
      </div>
      {detail.trigger_annotations.length === 0 && (
        <div className="rounded-2xl border border-border/60 gradient-card p-5 text-sm text-muted-foreground">
          No trigger annotations were stored for this escalation.
        </div>
      )}
      {Object.entries(groups).map(([agentName, annotations]) => (
        <section className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card" key={agentName}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{formatAgentName(agentName)}</h2>
            <span className="text-xs text-muted-foreground">{annotations.length} trigger{annotations.length === 1 ? "" : "s"}</span>
          </div>
          <div className="space-y-3">
            {annotations.map((annotation) => (
              <article key={annotation.id} className="rounded-xl border border-border/60 bg-background/30 p-4">
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  <SeverityPill severity={annotation.severity} />
                  <span className="text-[10px] font-mono text-muted-foreground">{annotation.finding_id}</span>
                </div>
                <h3 className="text-sm font-semibold mb-1">{annotation.title}</h3>
                <p className="text-sm text-muted-foreground">{annotation.description}</p>
                {annotation.text && (
                  <blockquote className="mt-3 border-l-2 border-primary/60 pl-3 text-xs text-foreground/80">
                    {annotation.text}
                  </blockquote>
                )}
                {annotation.ruling && (
                  <div className="mt-3 rounded-lg border border-border/60 bg-card/40 p-3">
                    <div className="text-[10px] font-mono uppercase tracking-wider text-primary mb-1">
                      {annotation.ruling.citation}
                    </div>
                    <div className="text-xs text-muted-foreground mb-1">{annotation.ruling.source}</div>
                    <p className="text-xs text-foreground/85">{annotation.ruling.quote}</p>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
};

const ContextPanel = ({
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
  onQuestionChange: (value: string) => void;
  onSubmitQuestion: (event: FormEvent<HTMLFormElement>) => void;
  onNotesChange: (value: string) => void;
  onFixSuggestionsChange: (value: string) => void;
  onDecision: (decision: "accepted" | "denied") => void;
}) => {
  const suggestions = detail ? uniqueSuggestions(detail) : [];
  const canDecide = detail?.status === "pending_legal";

  return (
    <aside className="overflow-y-auto bg-card/20 p-5 space-y-4">
      {!detail ? (
        <div className="rounded-2xl border border-border/60 gradient-card p-5 text-sm text-muted-foreground">
          Select an escalation.
        </div>
      ) : (
        <>
          <section className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">Suggested fixes</h2>
            </div>
            {suggestions.length === 0 && detail.fix_suggestions.length === 0 && (
              <p className="text-sm text-muted-foreground">No suggestions recorded.</p>
            )}
            <div className="space-y-3">
              {suggestions.map((suggestion) => (
                <SuggestionCard key={`${suggestion.finding_id}-${suggestion.proposed_text}`} suggestion={suggestion} />
              ))}
              {detail.fix_suggestions.map((fix) => (
                <div key={fix} className="rounded-xl border border-success/30 bg-success/5 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-success font-semibold mb-1">Legal fix</div>
                  <p className="text-xs text-foreground/90">{fix}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card">
            <div className="flex items-center gap-2 mb-4">
              <MessageSquare className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">Context chat</h2>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto mb-3">
              {chatMessages.length === 0 && <p className="text-sm text-muted-foreground">No messages yet.</p>}
              {chatMessages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={cn(
                    "rounded-xl px-3 py-2 text-xs whitespace-pre-wrap",
                    message.role === "user" ? "bg-primary text-primary-foreground ml-6" : "bg-background/50 border border-border/60 mr-6",
                  )}
                >
                  {message.text}
                </div>
              ))}
              {chatLoading && (
                <div className="rounded-xl px-3 py-2 text-xs bg-background/50 border border-border/60 mr-6 flex items-center gap-2">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Checking context...
                </div>
              )}
            </div>
            <form onSubmit={onSubmitQuestion} className="space-y-2">
              <textarea
                value={chatQuestion}
                onChange={(event) => onQuestionChange(event.target.value)}
                placeholder="Ask about this escalation..."
                rows={3}
                className="w-full resize-none rounded-xl border border-border/70 bg-background/40 px-3 py-2 text-xs focus:outline-none focus:border-primary/60"
              />
              <Button
                type="submit"
                size="sm"
                disabled={chatLoading || !chatQuestion.trim()}
                className="w-full gradient-primary border-0 text-primary-foreground"
              >
                {chatLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 mr-1.5" />}
                Ask
              </Button>
            </form>
          </section>

          <section className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card">
            <div className="flex items-center gap-2 mb-4">
              <ShieldAlert className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">Legal decision</h2>
            </div>
            {!canDecide && (
              <div className="rounded-xl border border-border/60 bg-background/40 p-3 text-xs text-muted-foreground mb-3">
                Decision recorded as <strong className="text-foreground">{detail.status.replace("_", " ")}</strong>
                {detail.legal_notes ? `: ${detail.legal_notes}` : "."}
              </div>
            )}
            <textarea
              value={decisionNotes}
              onChange={(event) => onNotesChange(event.target.value)}
              placeholder="Legal notes..."
              rows={3}
              disabled={!canDecide || decisionLoading}
              className="w-full resize-none rounded-xl border border-border/70 bg-background/40 px-3 py-2 text-xs focus:outline-none focus:border-primary/60 disabled:opacity-60"
            />
            <textarea
              value={fixSuggestions}
              onChange={(event) => onFixSuggestionsChange(event.target.value)}
              placeholder="Fix suggestions for denied escalations, one per line..."
              rows={4}
              disabled={!canDecide || decisionLoading}
              className="w-full resize-none rounded-xl border border-border/70 bg-background/40 px-3 py-2 text-xs mt-2 focus:outline-none focus:border-primary/60 disabled:opacity-60"
            />
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canDecide || decisionLoading}
                onClick={() => onDecision("accepted")}
                className="border-success/40 text-success hover:bg-success/10"
              >
                <CheckCircle2 className="h-4 w-4 mr-1.5" />
                Accept
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!canDecide || decisionLoading}
                onClick={() => onDecision("denied")}
                className="border-destructive/40 text-destructive hover:bg-destructive/10"
              >
                <XCircle className="h-4 w-4 mr-1.5" />
                Deny
              </Button>
            </div>
          </section>
        </>
      )}
    </aside>
  );
};

const SuggestionCard = ({ suggestion }: { suggestion: Suggestion }) => (
  <div className="rounded-xl border border-border/60 bg-background/30 p-3">
    <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono mb-1">
      {suggestion.finding_id}
    </div>
    <p className="text-xs text-foreground/90 mb-1">{suggestion.proposed_text}</p>
    <p className="text-[11px] text-muted-foreground">{suggestion.rationale}</p>
  </div>
);

const StatusPill = ({ status }: { status: EscalationStatus }) => {
  const map = {
    pending_legal: { color: "warning", icon: ShieldAlert, label: "Pending legal" },
    accepted: { color: "success", icon: CheckCircle2, label: "Accepted" },
    denied: { color: "destructive", icon: XCircle, label: "Denied" },
  } as const;
  const m = map[status];
  const Icon = m.icon;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `hsl(var(--${m.color}) / 0.15)`, color: `hsl(var(--${m.color}))` }}
    >
      <Icon className="h-3 w-3" />
      {m.label}
    </span>
  );
};

const SeverityPill = ({ severity }: { severity: Severity }) => {
  const sev = displaySeverity(severity);
  return (
    <span
      className="inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `hsl(var(--severity-${sev}) / 0.15)`, color: `hsl(var(--severity-${sev}))` }}
    >
      {severity}
    </span>
  );
};

const SeverityLegend = () => (
  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-high) / 0.4)" }} />
      High
    </span>
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-medium) / 0.4)" }} />
      Medium
    </span>
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-low) / 0.4)" }} />
      Low
    </span>
  </div>
);

function buildTextSegments(contractText: string, annotations: TriggerAnnotation[]): TextSegment[] {
  const ranges = annotations
    .filter((annotation) => typeof annotation.start === "number" && typeof annotation.end === "number")
    .map((annotation) => ({
      annotation,
      start: Math.max(0, annotation.start ?? 0),
      end: Math.min(contractText.length, annotation.end ?? 0),
    }))
    .filter((range) => range.end > range.start)
    .sort((left, right) => left.start - right.start || severityWeight(right.annotation.severity) - severityWeight(left.annotation.severity));

  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const range of ranges) {
    if (range.end <= cursor) continue;
    if (range.start > cursor) {
      segments.push({ text: contractText.slice(cursor, range.start) });
    }
    const start = Math.max(range.start, cursor);
    segments.push({
      text: contractText.slice(start, range.end),
      annotation: range.annotation,
    });
    cursor = range.end;
  }

  if (cursor < contractText.length) {
    segments.push({ text: contractText.slice(cursor) });
  }

  return segments.length ? segments : [{ text: contractText }];
}

function uniqueSuggestions(detail: EscalationDetail): Suggestion[] {
  const suggestions = [
    ...detail.ai_suggestions,
    ...detail.trigger_annotations.flatMap((annotation) => annotation.suggestions),
  ];
  const seen = new Set<string>();
  return suggestions.filter((suggestion) => {
    const key = `${suggestion.finding_id}:${suggestion.proposed_text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function getHighestSeverity(annotations: TriggerAnnotation[]): Severity {
  return annotations.reduce<Severity>(
    (highest, annotation) =>
      severityWeight(annotation.severity) > severityWeight(highest) ? annotation.severity : highest,
    "info",
  );
}

function displaySeverity(severity: Severity) {
  if (severity === "blocker" || severity === "high") return "high";
  if (severity === "medium") return "medium";
  return "low";
}

function severityWeight(severity: Severity): number {
  const weights: Record<Severity, number> = {
    info: 0,
    low: 1,
    medium: 2,
    high: 3,
    blocker: 4,
  };
  return weights[severity];
}

function formatAgentName(agentName: string) {
  return agentName
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
