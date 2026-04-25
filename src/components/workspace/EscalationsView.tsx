import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, FileText, ShieldAlert, XCircle, Clock } from "lucide-react";
import { useAuditStore, type AuditRecord } from "@/lib/auditStore";
import { lookupRule } from "@/lib/playbook";
import { cn } from "@/lib/utils";

export const EscalationsView = () => {
  const audits = useAuditStore((s) => s.audits);
  const escalations = useMemo(
    () => audits.filter((a) => a.result.escalation_required || a.result.status !== "Approved"),
    [audits],
  );
  const [selectedId, setSelectedId] = useState<string | null>(escalations[0]?.id ?? null);
  const selected = escalations.find((e) => e.id === selectedId) ?? escalations[0] ?? null;

  if (escalations.length === 0) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="text-center max-w-md">
          <div className="h-16 w-16 mx-auto rounded-2xl bg-warning/10 border border-warning/30 grid place-items-center mb-5">
            <AlertTriangle className="h-7 w-7 text-warning" />
          </div>
          <h2 className="text-2xl font-bold mb-2">No escalations yet</h2>
          <p className="text-muted-foreground">
            Run an audit in <strong>Review Contract</strong>. Any contract that fails the playbook or exceeds €5M will appear here with the offending clauses highlighted.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[300px_1fr] h-full overflow-hidden">
      {/* List */}
      <div className="border-r border-border/60 overflow-y-auto bg-card/30">
        <div className="px-5 py-4 border-b border-border/60">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">Flagged</div>
          <div className="text-2xl font-bold mt-0.5">{escalations.length}</div>
        </div>
        <div className="divide-y divide-border/40">
          {escalations.map((e) => (
            <button
              key={e.id}
              onClick={() => setSelectedId(e.id)}
              className={cn(
                "w-full text-left px-5 py-4 hover:bg-muted/30 transition-colors",
                selected?.id === e.id && "bg-primary/10 border-l-2 border-primary",
              )}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <StatusPill status={e.result.status} />
                {e.result.escalation_required && (
                  <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-warning/15 text-warning">
                    Board
                  </span>
                )}
              </div>
              <div className="text-sm font-medium truncate flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                {e.fileName}
              </div>
              <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1.5 font-mono">
                <Clock className="h-3 w-3" />
                {new Date(e.createdAt).toLocaleString()}
                <span>·</span>
                <span>{e.result.violations.length} findings</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail with highlighted contract */}
      <div className="overflow-y-auto">
        {selected && <HighlightedContract record={selected} />}
      </div>
    </div>
  );
};

const StatusPill = ({ status }: { status: AuditRecord["result"]["status"] }) => {
  const map = {
    Approved: { color: "success", icon: ShieldAlert },
    Escalated: { color: "warning", icon: AlertTriangle },
    Rejected: { color: "destructive", icon: XCircle },
  } as const;
  const m = map[status];
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `hsl(var(--${m.color}) / 0.15)`, color: `hsl(var(--${m.color}))` }}
    >
      <m.icon className="h-3 w-3" />
      {status}
    </span>
  );
};

/** Render the contract text with violation clauses highlighted in place. */
const HighlightedContract = ({ record }: { record: AuditRecord }) => {
  const segments = useMemo(() => buildSegments(record.contractText, record.result.violations), [record]);

  return (
    <div className="max-w-4xl mx-auto px-8 py-8">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-1">Contract</div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              {record.fileName}
            </h1>
            <div className="text-sm text-muted-foreground mt-1">{record.result.contract_summary}</div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <StatusPill status={record.result.status} />
            <div className="flex gap-3 text-xs text-muted-foreground">
              <span><strong className="text-severity-high">{record.result.violations.filter((v) => v.severity === "High").length}</strong> High</span>
              <span><strong className="text-severity-medium">{record.result.violations.filter((v) => v.severity === "Medium").length}</strong> Medium</span>
            </div>
          </div>
        </div>

        {record.result.escalation_required && (
          <div
            className="rounded-xl border-2 p-4 mb-6 flex items-start gap-3"
            style={{
              borderColor: "hsl(var(--warning) / 0.5)",
              background: "linear-gradient(135deg, hsl(var(--warning) / 0.08), hsl(var(--warning) / 0.02))",
            }}
          >
            <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" style={{ color: "hsl(var(--warning))" }} />
            <div>
              <div className="font-bold text-sm" style={{ color: "hsl(var(--warning))" }}>
                🚨 Requires Board of Management Approval (&gt; €5M) · BMW Playbook P-02
              </div>
              {!!record.result.contract_value_eur && (
                <div className="text-xs text-muted-foreground mt-0.5">
                  Contract value: €{record.result.contract_value_eur.toLocaleString()}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Document with highlights */}
        <div className="rounded-2xl border border-border/60 bg-card/40 shadow-card overflow-hidden">
          <div className="px-5 py-3 border-b border-border/60 flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
              Source document with highlights
            </div>
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-high) / 0.4)" }} /> High</span>
              <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: "hsl(var(--severity-medium) / 0.4)" }} /> Medium</span>
            </div>
          </div>
          <pre className="px-6 py-6 text-xs leading-relaxed font-mono whitespace-pre-wrap break-words text-foreground/90 max-h-[560px] overflow-y-auto">
            {segments.map((seg, i) =>
              seg.violation ? (
                <HighlightedSpan key={i} text={seg.text} index={seg.index!} severity={seg.violation.severity} reference={seg.violation.reference} issue={seg.violation.issue} />
              ) : (
                <span key={i}>{seg.text}</span>
              ),
            )}
          </pre>
        </div>

        {/* Legend of findings */}
        <div className="mt-6 space-y-2">
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-2">All findings</div>
          {record.result.violations.map((v, i) => {
            const sev = v.severity === "High" ? "high" : "medium";
            const rule = lookupRule(v.reference);
            return (
              <div key={i} className="rounded-xl border border-border/60 bg-card/30 p-4 flex gap-3">
                <span
                  className="h-6 w-6 rounded grid place-items-center text-[10px] font-bold shrink-0 mt-0.5"
                  style={{ background: `hsl(var(--severity-${sev}) / 0.2)`, color: `hsl(var(--severity-${sev}))` }}
                >
                  {i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded border border-border bg-background/60">
                      {v.reference}
                    </span>
                    {rule && <span className="text-[10px] text-muted-foreground">{rule.title}</span>}
                  </div>
                  <div className="text-sm text-foreground">{v.issue}</div>
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>
    </div>
  );
};

const HighlightedSpan = ({
  text, index, severity, reference, issue,
}: { text: string; index: number; severity: "High" | "Medium"; reference: string; issue: string }) => {
  const sev = severity === "High" ? "high" : "medium";
  return (
    <span
      className="relative px-1 py-0.5 rounded cursor-help group"
      style={{
        background: `hsl(var(--severity-${sev}) / 0.18)`,
        boxShadow: `inset 0 -2px 0 hsl(var(--severity-${sev}) / 0.7)`,
      }}
      title={`[${reference}] ${issue}`}
    >
      <sup
        className="text-[9px] font-bold mr-0.5 px-1 rounded"
        style={{ background: `hsl(var(--severity-${sev}))`, color: "hsl(var(--background))" }}
      >
        {index}
      </sup>
      {text}
    </span>
  );
};

/** Locate violation clauses inside the contract text and split into segments. */
function buildSegments(text: string, violations: AuditRecord["result"]["violations"]) {
  type Seg = { text: string; violation?: AuditRecord["result"]["violations"][number]; index?: number };
  const matches: { start: number; end: number; v: AuditRecord["result"]["violations"][number]; index: number }[] = [];

  violations.forEach((v, i) => {
    if (!v.clause) return;
    const needle = v.clause.trim();
    if (!needle) return;

    // Try exact match first, then a fuzzy first-50-chars match
    let idx = text.indexOf(needle);
    if (idx === -1) {
      const probe = needle.slice(0, Math.min(60, needle.length));
      idx = text.indexOf(probe);
      if (idx !== -1) {
        matches.push({ start: idx, end: idx + probe.length, v, index: i + 1 });
        return;
      }
    } else {
      matches.push({ start: idx, end: idx + needle.length, v, index: i + 1 });
    }
  });

  // Sort + remove overlaps (keep earliest)
  matches.sort((a, b) => a.start - b.start);
  const cleaned: typeof matches = [];
  for (const m of matches) {
    if (cleaned.length === 0 || m.start >= cleaned[cleaned.length - 1].end) cleaned.push(m);
  }

  const segs: Seg[] = [];
  let cursor = 0;
  for (const m of cleaned) {
    if (m.start > cursor) segs.push({ text: text.slice(cursor, m.start) });
    segs.push({ text: text.slice(m.start, m.end), violation: m.v, index: m.index });
    cursor = m.end;
  }
  if (cursor < text.length) segs.push({ text: text.slice(cursor) });
  return segs;
}