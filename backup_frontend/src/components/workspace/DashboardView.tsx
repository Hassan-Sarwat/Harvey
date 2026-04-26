import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2, ShieldAlert, XCircle, TrendingUp, AlertTriangle, FileText, Gauge, BarChart3,
  Loader2,
} from "lucide-react";
import {
  type DashboardMetrics,
  type EscalationListItem,
  getDashboardMetrics,
  listEscalations,
} from "@/api/client";

export const DashboardView = () => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [escalations, setEscalations] = useState<EscalationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([getDashboardMetrics(), listEscalations()])
      .then(([dashboardMetrics, escalationPayload]) => {
        if (!active) return;
        setMetrics(dashboardMetrics);
        setEscalations(escalationPayload.items);
        setError(null);
      })
      .catch(() => {
        if (active) setError("Could not load dashboard metrics.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const stats = useMemo(() => {
    const escalationMetrics = metrics?.escalation_metrics;
    const aiApproved = metrics?.ai_approved ?? 0;
    const aiEscalated = escalationMetrics?.total_escalations ?? metrics?.escalated ?? 0;
    const pending = escalationMetrics?.pending_escalations ?? escalations.filter((item) => item.status === "pending_legal").length;
    const accepted = escalationMetrics?.accepted_escalations ?? escalations.filter((item) => item.status === "accepted").length;
    const denied = escalationMetrics?.denied_escalations ?? escalations.filter((item) => item.status === "denied").length;
    const totalDecisions = accepted + denied;
    const falseRate = totalDecisions ? Math.round((accepted / totalDecisions) * 100) : 0;
    const positiveRate = totalDecisions ? Math.round((denied / totalDecisions) * 100) : 0;

    return {
      aiApproved,
      aiEscalated,
      pending,
      accepted,
      denied,
      falseRate,
      positiveRate,
      perAgent: escalationMetrics?.per_agent ?? [],
      deviations: metrics?.frequent_playbook_deviations ?? [],
      defaults: metrics?.average_contract_value_vs_default ?? [],
    };
  }, [metrics, escalations]);

  if (loading) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading dashboard...
        </div>
      </div>
    );
  }

  if (error || !metrics) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="text-center max-w-md">
          <div className="h-16 w-16 mx-auto rounded-2xl bg-destructive/10 border border-destructive/30 grid place-items-center mb-5">
            <AlertTriangle className="h-7 w-7 text-destructive" />
          </div>
          <h2 className="text-2xl font-bold mb-2">Dashboard unavailable</h2>
          <p className="text-muted-foreground">{error ?? "The backend did not return metrics."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full">
      <div className="max-w-6xl mx-auto px-8 py-8">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-semibold mb-1">Insights</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-1">AI Performance Dashboard</h1>
          <p className="text-muted-foreground mb-8">
            Backend metrics across AI reviews, legal escalations, and legal decision outcomes.
          </p>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <KpiCard
              icon={CheckCircle2}
              color="success"
              label="AI approved"
              value={stats.aiApproved}
              footer="Demo auto-approval count"
            />
            <KpiCard
              icon={ShieldAlert}
              color="warning"
              label="Escalated"
              value={stats.aiEscalated}
              footer={`${stats.pending} pending legal`}
            />
            <KpiCard
              icon={XCircle}
              color="destructive"
              label="Denied by legal"
              value={stats.denied}
              footer={`${stats.positiveRate}% positive escalation rate`}
            />
            <KpiCard
              icon={TrendingUp}
              color="primary"
              label="Accepted by legal"
              value={stats.accepted}
              footer={`${stats.falseRate}% false escalation rate`}
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            <Section title="Frequent deviations" subtitle="Most common playbook issues" icon={AlertTriangle}>
              {stats.deviations.length === 0 ? (
                <Empty>No deviations reported by the backend.</Empty>
              ) : (
                <div className="space-y-3">
                  {stats.deviations.map((deviation, index) => (
                    <div key={deviation} className="rounded-xl border border-border/60 bg-card/40 p-4 flex gap-3">
                      <span className="h-6 w-6 rounded grid place-items-center text-[10px] font-bold shrink-0 mt-0.5 bg-warning/15 text-warning">
                        {index + 1}
                      </span>
                      <div className="text-sm text-foreground">{deviation}</div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            <Section title="Defaults exceeded" subtitle="Observed values against playbook defaults" icon={Gauge}>
              {stats.defaults.length === 0 ? (
                <Empty>No default comparison metrics reported.</Empty>
              ) : (
                <div className="space-y-3">
                  {stats.defaults.map((item, index) => (
                    <div key={`${String(item.metric)}-${index}`} className="rounded-xl border border-border/60 bg-card/40 p-4">
                      <div className="flex items-center justify-between mb-1 gap-3">
                        <span className="text-sm font-semibold">{formatMetricName(String(item.metric ?? "Metric"))}</span>
                        <span className="text-xs font-mono text-muted-foreground">
                          {String(item.average_observed ?? "n/a")} vs {String(item.playbook_default ?? "n/a")}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted/40 overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${comparisonWidth(item)}%` }}
                          transition={{ duration: 0.8, ease: "easeOut" }}
                          className="h-full rounded-full bg-primary"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          <div className="grid lg:grid-cols-2 gap-6 mt-6">
            <Section title="Per-agent outcomes" subtitle="Escalation quality by source agent" icon={BarChart3}>
              {stats.perAgent.length === 0 ? (
                <Empty>No per-agent escalation outcomes yet.</Empty>
              ) : (
                <div className="space-y-3">
                  {stats.perAgent.map((agent) => (
                    <div key={String(agent.agent_name)} className="rounded-xl border border-border/60 bg-card/40 p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-semibold">{formatAgentName(String(agent.agent_name))}</span>
                        <span className="text-xs font-mono text-muted-foreground">{String(agent.total ?? 0)} total</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
                        <span>Pending <strong className="text-foreground">{String(agent.pending ?? 0)}</strong></span>
                        <span>Accepted <strong className="text-success">{String(agent.accepted ?? 0)}</strong></span>
                        <span>Denied <strong className="text-destructive">{String(agent.denied ?? 0)}</strong></span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            <Section title="Recent escalations" subtitle="Latest contracts routed to legal" icon={FileText}>
              {escalations.length === 0 ? (
                <Empty>No legal escalations have been created yet.</Empty>
              ) : (
                <div className="rounded-xl border border-border/60 bg-card/40 overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/30 text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                      <tr>
                        <th className="text-left px-4 py-2 font-semibold">Reason</th>
                        <th className="text-left px-4 py-2 font-semibold">Status</th>
                        <th className="text-right px-4 py-2 font-semibold">When</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40">
                      {escalations.slice(0, 8).map((item) => (
                        <tr key={item.id}>
                          <td className="px-4 py-3 font-medium max-w-[260px]">
                            <div className="line-clamp-2">{item.reason}</div>
                            <div className="text-[10px] text-muted-foreground font-mono mt-1">
                              {item.ticket_id} · {item.contract_id}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <StatusChip status={item.status} />
                          </td>
                          <td className="px-4 py-3 text-right text-xs text-muted-foreground">
                            {formatDate(item.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          </div>
        </motion.div>
      </div>
    </div>
  );
};

const KpiCard = ({
  icon: Icon, color, label, value, footer,
}: { icon: typeof CheckCircle2; color: string; label: string; value: number; footer: string }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    className="rounded-2xl border border-border/60 surface-card p-5 shadow-card relative overflow-hidden"
  >
    <div
      className="absolute -top-12 -right-12 h-32 w-32 rounded-full blur-3xl opacity-30"
      style={{ background: `hsl(var(--${color}))` }}
    />
    <div className="flex items-center justify-between mb-3 relative">
      <div
        className="h-9 w-9 rounded-lg grid place-items-center"
        style={{ background: `hsl(var(--${color}) / 0.12)`, border: `1px solid hsl(var(--${color}) / 0.4)` }}
      >
        <Icon className="h-4 w-4" style={{ color: `hsl(var(--${color}))` }} />
      </div>
    </div>
    <div className="text-3xl font-bold tracking-tight relative">{value}</div>
    <div className="text-xs text-muted-foreground mt-0.5 relative">{label}</div>
    <div className="text-[10px] text-muted-foreground/70 mt-2 font-mono relative">{footer}</div>
  </motion.div>
);

const Section = ({
  title, subtitle, icon: Icon, children, className,
}: { title: string; subtitle: string; icon: typeof CheckCircle2; children: React.ReactNode; className?: string }) => (
  <div className={className}>
    <div className="flex items-center gap-3 mb-4">
      <div className="h-8 w-8 rounded-lg bg-primary/10 border border-primary/20 grid place-items-center">
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
    </div>
    <div className="rounded-2xl border border-border/60 surface-card p-5 shadow-card">{children}</div>
  </div>
);

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="text-sm text-muted-foreground py-6 text-center">{children}</div>
);

const StatusChip = ({ status }: { status: EscalationListItem["status"] }) => {
  const map = {
    pending_legal: "warning",
    accepted: "success",
    denied: "destructive",
  } as const;
  const c = map[status];
  return (
    <span
      className="inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `hsl(var(--${c}) / 0.15)`, color: `hsl(var(--${c}))` }}
    >
      {status.replace("_", " ")}
    </span>
  );
};

function comparisonWidth(item: Record<string, unknown>) {
  const observed = Number(item.average_observed);
  const playbook = Number(item.playbook_default);
  if (!Number.isFinite(observed) || !Number.isFinite(playbook) || playbook <= 0) return 35;
  return Math.max(8, Math.min(100, (observed / playbook) * 60));
}

function formatMetricName(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatAgentName(value: string) {
  return formatMetricName(value);
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
