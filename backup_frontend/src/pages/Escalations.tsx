import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  EscalationDetail,
  EscalationListItem,
  Severity,
  Suggestion,
  TriggerAnnotation,
  askEscalationQuestion,
  getEscalation,
  listEscalations
} from "../api/client";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

type TextSegment = {
  text: string;
  annotation?: TriggerAnnotation;
};

export function Escalations() {
  const [items, setItems] = useState<EscalationListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    listEscalations()
      .then((payload) => {
        if (!active) {
          return;
        }
        setItems(payload.items);
        setSelectedId((current) => current ?? payload.items[0]?.id ?? null);
        setError(null);
      })
      .catch(() => {
        if (active) {
          setError("Could not load escalations.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }

    let active = true;
    setDetailLoading(true);
    setChatMessages([]);
    getEscalation(selectedId)
      .then((payload) => {
        if (active) {
          setDetail(payload);
          setError(null);
        }
      })
      .catch(() => {
        if (active) {
          setError("Could not load escalation detail.");
        }
      })
      .finally(() => {
        if (active) {
          setDetailLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [selectedId]);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = chatQuestion.trim();
    if (!detail || !question || chatLoading) {
      return;
    }

    setChatQuestion("");
    setChatLoading(true);
    setChatMessages((messages) => [...messages, { role: "user", text: question }]);
    try {
      const response = await askEscalationQuestion(detail.id, question);
      setChatMessages((messages) => [...messages, { role: "assistant", text: response.answer }]);
    } catch {
      setChatMessages((messages) => [
        ...messages,
        { role: "assistant", text: "Could not answer from the escalation context." }
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <section className="escalations-page">
      <div className="page-heading">
        <div>
          <h1>Escalation Investigation</h1>
        </div>
        <span className="queue-count">{items.length} records</span>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <div className="empty-state">Loading escalations...</div>}
      {!loading && items.length === 0 && <div className="empty-state">No escalations have been created yet.</div>}

      {!loading && items.length > 0 && (
        <div className="escalation-workspace">
          <EscalationQueue items={items} selectedId={selectedId} onSelect={setSelectedId} />

          <main className="escalation-detail">
            {detailLoading && <div className="empty-state">Loading selected escalation...</div>}
            {!detailLoading && detail && (
              <>
                <DetailHeader detail={detail} />
                <HighlightedContract detail={detail} />
                <AgentTriggers detail={detail} />
              </>
            )}
          </main>

          <aside className="legal-context-panel">
            {detail ? (
              <>
                <SuggestionPanel suggestions={uniqueSuggestions(detail)} legalFixes={detail.fix_suggestions} />
                <ChatPanel
                  messages={chatMessages}
                  question={chatQuestion}
                  loading={chatLoading}
                  onQuestionChange={setChatQuestion}
                  onSubmit={submitQuestion}
                />
              </>
            ) : (
              <div className="empty-state">Select an escalation.</div>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}

function EscalationQueue({
  items,
  selectedId,
  onSelect
}: {
  items: EscalationListItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="escalation-queue" aria-label="Escalation queue">
      {items.map((item) => (
        <button
          key={item.id}
          className={`queue-item ${selectedId === item.id ? "selected" : ""}`}
          onClick={() => onSelect(item.id)}
        >
          <span className={`status-pill status-${item.status}`}>{item.status.replace("_", " ")}</span>
          <strong>{item.reason}</strong>
          <span>{item.contract_id}</span>
          <span>{item.source_agents.map(formatAgentName).join(", ")}</span>
        </button>
      ))}
    </aside>
  );
}

function DetailHeader({ detail }: { detail: EscalationDetail }) {
  const highestSeverity = getHighestSeverity(detail.trigger_annotations);

  return (
    <header className="detail-header">
      <div>
        <span className={`severity-pill severity-${highestSeverity}`}>{highestSeverity}</span>
        <h2>{detail.reason}</h2>
        <p>
          {detail.contract_id}
          {detail.version_number ? `, version ${detail.version_number}` : ""} · {formatDate(detail.created_at)}
        </p>
      </div>
      <div className="detail-meta">
        <span>{detail.status.replace("_", " ")}</span>
        <span>{detail.source_finding_ids.length} trigger ids</span>
      </div>
    </header>
  );
}

function HighlightedContract({ detail }: { detail: EscalationDetail }) {
  const segments = useMemo(
    () => buildTextSegments(detail.contract_text, detail.trigger_annotations),
    [detail.contract_text, detail.trigger_annotations]
  );
  const unplacedTriggers = detail.trigger_annotations.filter(
    (annotation) => typeof annotation.start !== "number" || typeof annotation.end !== "number"
  );

  return (
    <section className="contract-panel" aria-label="Highlighted contract">
      <div className="panel-heading">
        <h3>Contract</h3>
        <SeverityLegend />
      </div>
      {detail.contract_text ? (
        <div className="contract-text">
          {segments.map((segment, index) =>
            segment.annotation ? (
              <mark
                key={`${segment.annotation.id}-${index}`}
                className={`contract-highlight highlight-${displaySeverity(segment.annotation.severity)}`}
                title={`${segment.annotation.title ?? "Trigger"} · ${segment.annotation.severity}`}
              >
                {segment.text}
              </mark>
            ) : (
              <span key={`text-${index}`}>{segment.text}</span>
            )
          )}
        </div>
      ) : (
        <div className="empty-state">Contract text was not stored for this escalation.</div>
      )}

      {unplacedTriggers.length > 0 && (
        <div className="unplaced-triggers">
          {unplacedTriggers.map((trigger) => (
            <span key={trigger.id} className={`severity-chip severity-${displaySeverity(trigger.severity)}`}>
              {trigger.title}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function AgentTriggers({ detail }: { detail: EscalationDetail }) {
  const groups = detail.trigger_annotations.reduce<Record<string, TriggerAnnotation[]>>((accumulator, annotation) => {
    accumulator[annotation.agent_name] = [...(accumulator[annotation.agent_name] ?? []), annotation];
    return accumulator;
  }, {});

  return (
    <section className="agent-trigger-panel" aria-label="Agent trigger output">
      <div className="panel-heading">
        <h3>Agent Findings</h3>
        <span>{detail.trigger_annotations.length} highlighted findings</span>
      </div>
      {Object.entries(groups).map(([agentName, annotations]) => (
        <div className="agent-section" key={agentName}>
          <div className="agent-section-heading">
            <strong>{formatAgentName(agentName)}</strong>
            <span>{annotations.length} triggers</span>
          </div>
          {annotations.map((annotation) => (
            <article className="finding-card" key={annotation.id}>
              <div className="finding-title-row">
                <span className={`severity-pill severity-${displaySeverity(annotation.severity)}`}>
                  {annotation.severity}
                </span>
                <h4>{annotation.title}</h4>
              </div>
              <p>{annotation.description}</p>
              {annotation.text && <blockquote>{annotation.text}</blockquote>}
              {annotation.ruling && (
                <div className="ruling-box">
                  <strong>{annotation.ruling.citation}</strong>
                  <span>{annotation.ruling.source}</span>
                  <p>{annotation.ruling.quote}</p>
                </div>
              )}
              {annotation.suggestions.length > 0 && (
                <div className="finding-suggestions">
                  {annotation.suggestions.map((suggestion) => (
                    <p key={`${annotation.id}-${suggestion.proposed_text}`}>
                      <strong>Suggestion:</strong> {suggestion.proposed_text}
                    </p>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      ))}
    </section>
  );
}

function SuggestionPanel({ suggestions, legalFixes }: { suggestions: Suggestion[]; legalFixes: string[] }) {
  return (
    <section className="side-panel-section" aria-label="AI suggestions">
      <h3>AI Suggestions</h3>
      {suggestions.length === 0 && legalFixes.length === 0 && <p>No suggestions recorded.</p>}
      {suggestions.map((suggestion) => (
        <article className="suggestion-item" key={`${suggestion.finding_id}-${suggestion.proposed_text}`}>
          <strong>{suggestion.finding_id}</strong>
          <p>{suggestion.proposed_text}</p>
          <span>{suggestion.rationale}</span>
        </article>
      ))}
      {legalFixes.map((fix) => (
        <article className="suggestion-item legal-fix" key={fix}>
          <strong>Legal fix</strong>
          <p>{fix}</p>
        </article>
      ))}
    </section>
  );
}

function ChatPanel({
  messages,
  question,
  loading,
  onQuestionChange,
  onSubmit
}: {
  messages: ChatMessage[];
  question: string;
  loading: boolean;
  onQuestionChange: (question: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="side-panel-section chat-section" aria-label="Escalation chat">
      <h3>Context Chat</h3>
      <div className="chat-messages">
        {messages.length === 0 && <p className="chat-empty">No messages yet.</p>}
        {messages.map((message, index) => (
          <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
            {message.text}
          </div>
        ))}
        {loading && <div className="chat-message assistant">Checking escalation context...</div>}
      </div>
      <form className="chat-form" onSubmit={onSubmit}>
        <textarea
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="Ask about this escalation"
          rows={3}
        />
        <button className="primary" type="submit" disabled={loading || !question.trim()}>
          Ask
        </button>
      </form>
    </section>
  );
}

function SeverityLegend() {
  return (
    <div className="severity-legend" aria-label="Highlight severity legend">
      <span className="legend-item low">Low</span>
      <span className="legend-item medium">Medium</span>
      <span className="legend-item high">High</span>
    </div>
  );
}

function buildTextSegments(contractText: string, annotations: TriggerAnnotation[]): TextSegment[] {
  const ranges = annotations
    .filter((annotation) => typeof annotation.start === "number" && typeof annotation.end === "number")
    .map((annotation) => ({
      annotation,
      start: Math.max(0, annotation.start ?? 0),
      end: Math.min(contractText.length, annotation.end ?? 0)
    }))
    .filter((range) => range.end > range.start)
    .sort((left, right) => left.start - right.start || severityWeight(right.annotation.severity) - severityWeight(left.annotation.severity));

  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const range of ranges) {
    if (range.end <= cursor) {
      continue;
    }
    if (range.start > cursor) {
      segments.push({ text: contractText.slice(cursor, range.start) });
    }
    const start = Math.max(range.start, cursor);
    segments.push({
      text: contractText.slice(start, range.end),
      annotation: range.annotation
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
    ...detail.trigger_annotations.flatMap((annotation) => annotation.suggestions)
  ];
  const seen = new Set<string>();
  return suggestions.filter((suggestion) => {
    const key = `${suggestion.finding_id}:${suggestion.proposed_text}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function getHighestSeverity(annotations: TriggerAnnotation[]): Severity {
  return annotations.reduce<Severity>(
    (highest, annotation) =>
      severityWeight(annotation.severity) > severityWeight(highest) ? annotation.severity : highest,
    "info"
  );
}

function displaySeverity(severity: Severity): Severity {
  return severity === "blocker" ? "high" : severity;
}

function severityWeight(severity: Severity): number {
  const weights: Record<Severity, number> = {
    info: 0,
    low: 1,
    medium: 2,
    high: 3,
    blocker: 4
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
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}
