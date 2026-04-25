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

export type TextSegment = {
  text: string;
  start: number;
  end: number;
  annotation?: TriggerAnnotation;
  showMarker?: boolean;
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
    const payload = await listEscalations("pending_legal");
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
          <h2 className="text-2xl font-bold mb-2">No pending tickets</h2>
          <p className="text-muted-foreground">
            No contracts are currently waiting for legal. Pending ticketed escalations will appear here with context and highlights.
          </p>
          {error && <p className="text-sm text-destructive mt-4">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[320px_minmax(0,1fr)_380px] h-full overflow-hidden">
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
      <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">Pending Tickets</div>
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
            <SeverityPill severity={item.highest_severity} />
            {item.next_owner && (
              <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground">
                {item.next_owner}
              </span>
            )}
          </div>
          <div className="text-base font-semibold mb-1">{item.ticket_id}</div>
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
  const highestSeverity = detail.highest_severity ?? getHighestSeverity(detail.trigger_annotations);

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-1">
              Legal Ticket
            </div>
            <h1 className="text-2xl font-bold flex items-start gap-2">
              <Scale className="h-5 w-5 text-primary mt-1 shrink-0" />
              {detail.ticket_id}
            </h1>
            <div className="text-sm text-muted-foreground mt-1">
              {detail.reason}
            </div>
            <div className="text-xs text-muted-foreground mt-1 font-mono">
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
      </motion.div>
    </div>
  );
};

const HighlightedContract = ({ detail }: { detail: EscalationDetail }) => {
  const segments = useMemo(
    () => buildTextSegments(detail.contract_text, detail.trigger_annotations),
    [detail.contract_text, detail.trigger_annotations],
  );
  const annotationMarkers = useMemo(() => buildAnnotationMarkerMap(detail.trigger_annotations), [detail.trigger_annotations]);

  return (
    <section className="rounded-lg border border-border/60 bg-card/40 shadow-card overflow-hidden">
      <div className="px-5 py-3 border-b border-border/60 flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
            Contract Viewer
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">Extracted text preview with AI flags overlaid.</div>
        </div>
        <SeverityLegend />
      </div>
      {detail.contract_text ? (
        <div className="bg-slate-300/10 px-4 py-5 sm:px-6 max-h-[calc(100vh-190px)] overflow-y-auto">
          <article className="mx-auto min-h-[760px] max-w-[820px] border border-slate-300 bg-slate-50 px-8 py-9 text-slate-950 shadow-2xl sm:px-12">
            <div className="mb-6 flex items-center justify-between border-b border-slate-300 pb-3 text-[10px] uppercase tracking-[0.18em] text-slate-500">
              <span>{detail.ticket_id}</span>
              <span>{detail.version_number ? `Version ${detail.version_number}` : "Unversioned"}</span>
            </div>
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 text-slate-950">
              {segments.map((segment, index) =>
                segment.annotation ? (
                  <HighlightedSpan
                    key={`${segment.annotation.id}-${segment.start}-${index}`}
                    annotation={segment.annotation}
                    marker={annotationMarkers.get(segment.annotation.id)}
                    showMarker={segment.showMarker}
                    text={segment.text}
                  />
                ) : (
                  <span key={`text-${segment.start}-${index}`}>{segment.text}</span>
                ),
              )}
            </pre>
          </article>
        </div>
      ) : (
        <div className="p-6 text-sm text-muted-foreground">Contract text was not stored for this escalation.</div>
      )}
    </section>
  );
};

const HighlightedSpan = ({
  annotation,
  marker,
  showMarker,
  text,
}: {
  annotation: TriggerAnnotation;
  marker?: number;
  showMarker?: boolean;
  text: string;
}) => {
  const sev = displaySeverity(annotation.severity);
  const style = documentHighlightStyle(sev);
  return (
    <span
      className="relative rounded px-1 py-0.5 cursor-help"
      style={style}
      title={`${annotation.title ?? "Trigger"} - ${annotation.severity}`}
    >
      {text}
      {showMarker && marker && (
        <sup className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded bg-slate-950 px-1 text-[10px] font-bold leading-none text-white">
          {marker}
        </sup>
      )}
    </span>
  );
};

const AnnotationPanel = ({ detail }: { detail: EscalationDetail }) => {
  const annotations = orderAnnotations(detail.trigger_annotations);
  const markers = buildAnnotationMarkerMap(detail.trigger_annotations);

  return (
    <section className="rounded-lg border border-border/60 gradient-card p-5 shadow-card">
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">AI flags</h2>
      </div>
      {annotations.length === 0 ? (
        <p className="text-sm text-muted-foreground">No trigger annotations were stored for this ticket.</p>
      ) : (
        <div className="space-y-3">
          {annotations.map((annotation) => {
            const marker = markers.get(annotation.id);
            const suggestions = annotation.suggestions ?? [];
            return (
              <article key={annotation.id} className="rounded-lg border border-border/60 bg-background/30 p-4">
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  {marker && (
                    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-primary px-1.5 text-[10px] font-bold text-primary-foreground">
                      {marker}
                    </span>
                  )}
                  <SeverityPill severity={annotation.severity} />
                  <span className="text-[10px] font-mono text-muted-foreground">{formatAgentName(annotation.agent_name)}</span>
                </div>
                <h3 className="text-sm font-semibold mb-1">{annotation.title}</h3>
                <p className="text-xs text-muted-foreground">{annotation.description}</p>
                {annotation.text && (
                  <blockquote className="mt-3 border-l-2 border-primary/60 pl-3 text-xs text-foreground/80">
                    {annotation.text}
                  </blockquote>
                )}
                {suggestions[0] && (
                  <div className="mt-3 rounded-lg border border-success/30 bg-success/5 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-success font-semibold mb-1">AI fix</div>
                    <p className="text-xs text-foreground/90">{suggestions[0].proposed_text}</p>
                  </div>
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
            );
          })}
        </div>
      )}
    </section>
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
        <div className="rounded-lg border border-border/60 gradient-card p-5 text-sm text-muted-foreground">
          Select a pending ticket.
        </div>
      ) : (
        <>
          <AnnotationPanel detail={detail} />

          <section className="rounded-lg border border-border/60 gradient-card p-5 shadow-card">
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

          <section className="rounded-lg border border-border/60 gradient-card p-5 shadow-card">
            <div className="flex items-center gap-2 mb-4">
              <MessageSquare className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">Ask about this contract</h2>
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
                placeholder="Ask about this contract..."
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

          <section className="rounded-lg border border-border/60 gradient-card p-5 shadow-card">
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
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-low) / 0.55)" }} />
      Ambiguous
    </span>
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-medium) / 0.55)" }} />
      Medium
    </span>
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-high) / 0.55)" }} />
      Illegal / high
    </span>
  </div>
);

type AnnotationRange = {
  annotation: TriggerAnnotation;
  start: number;
  end: number;
};

export function buildTextSegments(contractText: string, annotations: TriggerAnnotation[]): TextSegment[] {
  const ranges = buildAnnotationRanges(contractText, annotations);
  if (ranges.length === 0) {
    return [{ text: contractText, start: 0, end: contractText.length }];
  }

  const boundaries = [...new Set([0, contractText.length, ...ranges.flatMap((range) => [range.start, range.end])])]
    .filter((boundary) => boundary >= 0 && boundary <= contractText.length)
    .sort((left, right) => left - right);

  const segments: TextSegment[] = [];
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    if (end <= start) continue;

    const coveringRanges = ranges.filter((range) => range.start < end && range.end > start);
    const primaryRange = coveringRanges.sort(compareRangePriority)[0];
    segments.push({
      text: contractText.slice(start, end),
      start,
      end,
      annotation: primaryRange?.annotation,
      showMarker: primaryRange ? start === primaryRange.start : false,
    });
  }

  return segments.length ? segments : [{ text: contractText, start: 0, end: contractText.length }];
}

export function orderAnnotations(annotations: TriggerAnnotation[]): TriggerAnnotation[] {
  return [...annotations].sort((left, right) => {
    const leftStart = typeof left.start === "number" ? left.start : Number.MAX_SAFE_INTEGER;
    const rightStart = typeof right.start === "number" ? right.start : Number.MAX_SAFE_INTEGER;
    return (
      leftStart - rightStart ||
      severityWeight(right.severity) - severityWeight(left.severity) ||
      left.id.localeCompare(right.id)
    );
  });
}

export function buildAnnotationMarkerMap(annotations: TriggerAnnotation[]): Map<string, number> {
  return new Map(orderAnnotations(annotations).map((annotation, index) => [annotation.id, index + 1]));
}

function buildAnnotationRanges(contractText: string, annotations: TriggerAnnotation[]): AnnotationRange[] {
  return annotations
    .filter((annotation) => typeof annotation.start === "number" && typeof annotation.end === "number")
    .map((annotation) => ({
      annotation,
      start: Math.max(0, annotation.start ?? 0),
      end: Math.min(contractText.length, annotation.end ?? 0),
    }))
    .filter((range) => range.end > range.start)
    .sort((left, right) => left.start - right.start || compareRangePriority(left, right));
}

function compareRangePriority(left: AnnotationRange, right: AnnotationRange): number {
  return (
    severityWeight(right.annotation.severity) - severityWeight(left.annotation.severity) ||
    left.start - right.start ||
    right.end - left.end ||
    left.annotation.id.localeCompare(right.annotation.id)
  );
}

function documentHighlightStyle(severity: ReturnType<typeof displaySeverity>) {
  const styles = {
    low: {
      backgroundColor: "rgba(250, 204, 21, 0.42)",
      boxShadow: "inset 0 -2px 0 rgba(202, 138, 4, 0.85)",
    },
    medium: {
      backgroundColor: "rgba(251, 146, 60, 0.42)",
      boxShadow: "inset 0 -2px 0 rgba(234, 88, 12, 0.9)",
    },
    high: {
      backgroundColor: "rgba(248, 113, 113, 0.48)",
      boxShadow: "inset 0 -2px 0 rgba(220, 38, 38, 0.95)",
    },
  } as const;
  return styles[severity];
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
