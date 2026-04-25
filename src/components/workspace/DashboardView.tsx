import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2, ShieldAlert, XCircle, TrendingUp, AlertTriangle, FileText, Gauge, BarChart3,
} from "lucide-react";
import { useAuditStore } from "@/lib/auditStore";
import { lookupRule, RULE_LIBRARY } from "@/lib/playbook";

export const DashboardView = () => {
  const audits = useAuditStore((s) => s.audits);

  const stats = useMemo(() => {
    const total = audits.length;
    const approved = audits.filter((a) => a.result.status === "Approved").length;
    const escalated = audits.filter((a) => a.result.status === "Escalated").length;
    const rejected = audits.filter((a) => a.result.status === "Rejected").length;
    const pctApproved = total ? Math.round((approved / total) * 100) : 0;
    const pctEscalated = total ? Math.round(((escalated + rejected) / total) * 100) : 0;

    // Aggregate violation reasons by rule reference
    const reasonCounts = new Map<string, number>();
    const ruleCounts = new Map<string, number>();
    let totalViolations = 0;
    for (const a of audits) {
      for (const v of a.result.violations) {
        totalViolations++;
        const ruleId = v.reference.match(/(P-\d{2}|L-\d{2})/)?.[1];
        if (ruleId) ruleCounts.set(ruleId, (ruleCounts.get(ruleId) ?? 0) + 1);
        const key = ruleId ? `${ruleId}` : v.reference;
        reasonCounts.set(key, (reasonCounts.get(key) ?? 0) + 1);
      }
    }

    const topReasons = [...reasonCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([ref, count]) => ({ ref, count, rule: lookupRule(ref) }));

    const topPlaybookBreaches = [...ruleCounts.entries()]
      .filter(([id]) => id.startsWith("P-"))
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([id, count]) => ({ id, count, rule: RULE_LIBRARY[id] }));

    return { total, approved, escalated, rejected, pctApproved, pctEscalated, totalViolations, topReasons, topPlaybookBreaches };
  }, [audits]);

  if (stats.total === 0) {
    return (
      <div className="h-full grid place-items-center px-6">
        <div className="text-center max-w-md">
          <div className="h-16 w-16 mx-auto rounded-2xl bg-primary/10 border border-primary/20 grid place-items-center mb-5">
            <BarChart3 className="h-7 w-7 text-primary" />
          </div>
          <h2 className="text-2xl font-bold mb-2">No data yet</h2>
          <p className="text-muted-foreground">
            Run a few audits in <strong>Review Contract</strong> and the dashboard will populate with KPIs, escalation reasons and the most-exceeded playbook defaults.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-y-auto h-full">
      <div className="max-w-6xl mx-auto px-8 py-8">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <div className="text-[10px] uppercase tracking-[0.2em] text-primary font-semibold mb-1">Insights</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-1">Audit Dashboard</h1>
          <p className="text-muted-foreground mb-8">
            Across <strong className="text-foreground">{stats.total}</strong> contract{stats.total === 1 ? "" : "s"} reviewed.
          </p>

          {/* KPI tiles */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <KpiCard
              icon={CheckCircle2}
              color="success"
              label="Auto-approved by AI"
              value={stats.approved}
              footer={`${stats.pctApproved}% of reviews`}
            />
            <KpiCard
              icon={ShieldAlert}
              color="warning"
              label="Escalated for review"
              value={stats.escalated + stats.rejected}
              footer={`${stats.pctEscalated}% require human counsel`}
            />
            <KpiCard
              icon={XCircle}
              color="destructive"
              label="Rejected outright"
              value={stats.rejected}
              footer={`Hard statutory failures`}
            />
            <KpiCard
              icon={TrendingUp}
              color="primary"
              label="Total findings"
              value={stats.totalViolations}
              footer={`Avg ${stats.total ? (stats.totalViolations / stats.total).toFixed(1) : "0"} per contract`}
            />
          </div>

          {/* Two-column insights */}
          <div className="grid lg:grid-cols-2 gap-6">
            {/* Reasons for escalation */}
            <Section title="Reasons behind escalations" subtitle="Most-cited rules across all audits" icon={AlertTriangle}>
              {stats.topReasons.length === 0 ? (
                <Empty>No violations yet — congratulations.</Empty>
              ) : (
                <div className="space-y-3">
                  {stats.topReasons.map((r) => {
                    const max = stats.topReasons[0].count;
                    const pct = (r.count / max) * 100;
                    const isLaw = r.ref.startsWith("L-");
                    return (
                      <div key={r.ref}>
                        <div className="flex items-center justify-between mb-1.5">
                          <div className="flex items-center gap-2">
                            <span
                              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border"
                              style={{
                                color: isLaw ? "hsl(var(--severity-high))" : "hsl(var(--primary))",
                                borderColor: isLaw ? "hsl(var(--severity-high) / 0.4)" : "hsl(var(--primary) / 0.4)",
                                background: isLaw ? "hsl(var(--severity-high) / 0.08)" : "hsl(var(--primary) / 0.08)",
                              }}
                            >
                              {r.ref}
                            </span>
                            <span className="text-sm text-foreground truncate">{r.rule?.title ?? "Unknown rule"}</span>
                          </div>
                          <span className="text-xs font-mono text-muted-foreground">{r.count}×</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted/40 overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${pct}%` }}
                            transition={{ duration: 0.8, ease: "easeOut" }}
                            className="h-full rounded-full"
                            style={{ background: isLaw ? "hsl(var(--severity-high))" : "hsl(var(--primary))" }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Section>

            {/* Default values exceeded */}
            <Section title="Default values most exceeded" subtitle="Playbook defaults that vendors push back on" icon={Gauge}>
              {stats.topPlaybookBreaches.length === 0 ? (
                <Empty>No playbook defaults breached yet.</Empty>
              ) : (
                <div className="space-y-3">
                  {stats.topPlaybookBreaches.map((p) => (
                    <div key={p.id} className="rounded-xl border border-border/60 bg-card/40 p-4">
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center gap-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-primary/10 text-primary border border-primary/30">
                            {p.id}
                          </span>
                          <span className="text-sm font-semibold">{p.rule?.title}</span>
                        </div>
                        <span className="text-xs font-mono text-muted-foreground">
                          breached <strong className="text-foreground">{p.count}×</strong>
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground leading-relaxed">{p.rule?.body}</p>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          {/* Recent activity */}
          <Section title="Recent audits" subtitle="Last contracts processed" icon={FileText} className="mt-6">
            <div className="rounded-xl border border-border/60 bg-card/40 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/30 text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                  <tr>
                    <th className="text-left px-4 py-2 font-semibold">Contract</th>
                    <th className="text-left px-4 py-2 font-semibold">Status</th>
                    <th className="text-right px-4 py-2 font-semibold">Findings</th>
                    <th className="text-right px-4 py-2 font-semibold">Value</th>
                    <th className="text-right px-4 py-2 font-semibold">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40">
                  {audits.slice(0, 8).map((a) => (
                    <tr key={a.id}>
                      <td className="px-4 py-3 font-medium truncate max-w-[200px]">{a.fileName}</td>
                      <td className="px-4 py-3">
                        <StatusChip status={a.result.status} />
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">{a.result.violations.length}</td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {a.result.contract_value_eur ? `€${a.result.contract_value_eur.toLocaleString()}` : "—"}
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-muted-foreground">
                        {new Date(a.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
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
    className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card relative overflow-hidden"
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
    <div className="rounded-2xl border border-border/60 gradient-card p-5 shadow-card">{children}</div>
  </div>
);

const Empty = ({ children }: { children: React.ReactNode }) => (
  <div className="text-sm text-muted-foreground py-6 text-center">{children}</div>
);

const StatusChip = ({ status }: { status: "Approved" | "Escalated" | "Rejected" }) => {
  const map = {
    Approved: "success",
    Escalated: "warning",
    Rejected: "destructive",
  } as const;
  const c = map[status];
  return (
    <span
      className="inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
      style={{ background: `hsl(var(--${c}) / 0.15)`, color: `hsl(var(--${c}))` }}
    >
      {status}
    </span>
  );
};