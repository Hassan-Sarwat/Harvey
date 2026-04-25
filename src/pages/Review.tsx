import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Upload, FileText, Sparkles, AlertTriangle, CheckCircle2, XCircle,
  ShieldAlert, Scale, Loader2, FileWarning, Info,
} from "lucide-react";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { SAMPLE_CONTRACT } from "@/lib/sampleContract";
import { lookupRule } from "@/lib/playbook";

type Violation = {
  severity: "High" | "Medium";
  clause: string;
  issue: string;
  reference: string;
  suggestion: string;
};

type AuditResult = {
  contract_summary: string;
  contract_value_eur?: number;
  status: "Approved" | "Escalated" | "Rejected";
  escalation_required: boolean;
  violations: Violation[];
};

const Review = () => {
  const [contractText, setContractText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AuditResult | null>(null);

  const handleFile = useCallback(async (file: File) => {
    if (!file) return;
    if (file.size > 2_000_000) {
      toast.error("File too large (max 2 MB).");
      return;
    }
    const text = await file.text();
    setContractText(text);
    setFileName(file.name);
    toast.success(`Loaded ${file.name}`);
  }, []);

  const runAudit = async () => {
    if (contractText.trim().length < 50) {
      toast.error("Please paste or upload a contract first.");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data, error } = await supabase.functions.invoke("audit-dpa", {
        body: { contractText },
      });
      if (error) {
        const msg = (error as { message?: string }).message || "Audit failed";
        if (msg.includes("429")) toast.error("Rate limit reached. Please retry shortly.");
        else if (msg.includes("402")) toast.error("AI credits exhausted. Add funds in workspace settings.");
        else toast.error(msg);
        return;
      }
      if (data?.error) {
        toast.error(data.error);
        return;
      }
      setResult(data as AuditResult);
      toast.success("Audit complete");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Audit failed");
    } finally {
      setLoading(false);
    }
  };

  const loadSample = () => {
    setContractText(SAMPLE_CONTRACT);
    setFileName("sample-dpa.txt");
    toast.info("Sample contract loaded");
  };

  return (
    <TooltipProvider delayDuration={150}>
      <div className="min-h-screen bg-background text-foreground">
        {/* Header */}
        <header className="border-b border-border/60 backdrop-blur-md sticky top-0 z-40 bg-background/70">
          <div className="container mx-auto flex items-center justify-between py-4">
            <Link to="/" className="flex items-center gap-3 group">
              <ArrowLeft className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
              <div className="h-9 w-9 rounded-lg gradient-primary grid place-items-center shadow-glow">
                <Scale className="h-4 w-4 text-primary-foreground" />
              </div>
              <div className="leading-tight">
                <div className="text-sm font-semibold tracking-tight">DPA Auditor</div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Review Workspace</div>
              </div>
            </Link>
            <div className="text-xs text-muted-foreground font-mono">
              {result ? `${result.violations.length} findings` : "Awaiting input"}
            </div>
          </div>
        </header>

        <main className="container mx-auto py-10 grid lg:grid-cols-[420px_1fr] gap-8">
          {/* LEFT — Input */}
          <aside className="space-y-4">
            <div className="rounded-2xl border border-border/60 gradient-card p-6 shadow-card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Contract input</h2>
                <button
                  onClick={loadSample}
                  className="text-xs text-primary hover:text-primary-glow transition-colors font-medium"
                >
                  Load sample
                </button>
              </div>

              <label className="block">
                <input
                  type="file"
                  accept=".txt,.md,.docx,.pdf"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
                <div className="border border-dashed border-border rounded-xl px-4 py-6 text-center cursor-pointer hover:border-primary/60 hover:bg-primary/5 transition-colors">
                  <Upload className="h-5 w-5 mx-auto mb-2 text-muted-foreground" />
                  <div className="text-sm font-medium">
                    {fileName ?? "Upload contract or schedules"}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">.txt, .md (best results)</div>
                </div>
              </label>

              <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground uppercase tracking-wider">
                <div className="h-px flex-1 bg-border" /> or paste <div className="h-px flex-1 bg-border" />
              </div>

              <Textarea
                value={contractText}
                onChange={(e) => setContractText(e.target.value)}
                placeholder="Paste the DPA text here..."
                className="min-h-[280px] font-mono text-xs bg-background/60 border-border/60 resize-none"
              />

              <Button
                onClick={runAudit}
                disabled={loading}
                size="lg"
                className="w-full mt-4 gradient-primary border-0 text-primary-foreground shadow-elegant hover:opacity-90 disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Auditing contract…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Run Audit
                  </>
                )}
              </Button>

              <div className="mt-4 flex items-start gap-2 text-xs text-muted-foreground">
                <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                <span>Audits run against the BMW Internal Playbook (P-##) and GDPR / BDSG (L-##).</span>
              </div>
            </div>
          </aside>

          {/* RIGHT — Results */}
          <section>
            <AnimatePresence mode="wait">
              {!result && !loading && <EmptyState key="empty" />}
              {loading && <LoadingState key="loading" />}
              {result && !loading && (
                <motion.div
                  key="result"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4 }}
                  className="space-y-6"
                >
                  <Verdict result={result} />
                  {result.escalation_required && <EscalationBanner />}
                  <Summary result={result} />
                  <Violations violations={result.violations} />
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        </main>
      </div>
    </TooltipProvider>
  );
};

/* -------------------- sub-components -------------------- */

const EmptyState = () => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="rounded-2xl border border-border/60 gradient-card p-16 text-center shadow-card"
  >
    <div className="h-16 w-16 mx-auto rounded-2xl bg-primary/10 border border-primary/20 grid place-items-center mb-6">
      <FileText className="h-7 w-7 text-primary" />
    </div>
    <h3 className="text-2xl font-semibold mb-2">Ready when you are</h3>
    <p className="text-muted-foreground max-w-md mx-auto">
      Upload a Data Processing Agreement or paste the text on the left, then run the audit
      to see severity-graded violations, citations and redline suggestions.
    </p>
  </motion.div>
);

const LoadingState = () => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="rounded-2xl border border-border/60 gradient-card p-16 text-center shadow-card relative overflow-hidden"
  >
    <div className="absolute inset-x-0 top-0 h-1 shimmer" />
    <div className="h-16 w-16 mx-auto rounded-2xl bg-primary/10 border border-primary/20 grid place-items-center mb-6">
      <Loader2 className="h-7 w-7 text-primary animate-spin" />
    </div>
    <h3 className="text-2xl font-semibold mb-2">Cross-checking 15+ rules…</h3>
    <p className="text-muted-foreground max-w-md mx-auto">
      Evaluating every clause against the BMW Internal Playbook and German GDPR/BDSG.
    </p>
  </motion.div>
);

const Verdict = ({ result }: { result: AuditResult }) => {
  const map = {
    Approved: { icon: CheckCircle2, color: "success", label: "Approved" },
    Escalated: { icon: ShieldAlert, color: "warning", label: "Escalated" },
    Rejected: { icon: XCircle, color: "destructive", label: "Rejected" },
  } as const;
  const v = map[result.status];
  const Icon = v.icon;
  return (
    <div className="rounded-2xl border border-border/60 gradient-card p-6 shadow-card">
      <div className="flex items-start gap-5">
        <div
          className="h-14 w-14 rounded-xl grid place-items-center shrink-0"
          style={{ background: `hsl(var(--${v.color}) / 0.12)`, border: `1px solid hsl(var(--${v.color}) / 0.4)` }}
        >
          <Icon className="h-7 w-7" style={{ color: `hsl(var(--${v.color}))` }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Verdict</span>
            <span
              className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider"
              style={{ background: `hsl(var(--${v.color}) / 0.15)`, color: `hsl(var(--${v.color}))` }}
            >
              {v.label}
            </span>
          </div>
          <h2 className="text-3xl font-bold mt-2">
            {result.violations.length === 0
              ? "No violations detected"
              : `${result.violations.length} violation${result.violations.length === 1 ? "" : "s"} found`}
          </h2>
          <div className="flex flex-wrap gap-4 mt-3 text-sm text-muted-foreground">
            <span>
              <strong className="text-severity-high">{result.violations.filter((v) => v.severity === "High").length}</strong> High
            </span>
            <span>
              <strong className="text-severity-medium">{result.violations.filter((v) => v.severity === "Medium").length}</strong> Medium
            </span>
            {typeof result.contract_value_eur === "number" && result.contract_value_eur > 0 && (
              <span>
                Value: <strong className="text-foreground font-mono">€{result.contract_value_eur.toLocaleString()}</strong>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const EscalationBanner = () => (
  <motion.div
    initial={{ opacity: 0, scale: 0.98 }}
    animate={{ opacity: 1, scale: 1 }}
    className="rounded-2xl border-2 p-5 flex items-start gap-4 relative overflow-hidden"
    style={{
      borderColor: "hsl(var(--warning) / 0.5)",
      background: "linear-gradient(135deg, hsl(var(--warning) / 0.08), hsl(var(--warning) / 0.02))",
    }}
  >
    <div className="h-10 w-10 rounded-xl grid place-items-center shrink-0" style={{ background: "hsl(var(--warning) / 0.15)" }}>
      <AlertTriangle className="h-5 w-5" style={{ color: "hsl(var(--warning))" }} />
    </div>
    <div>
      <div className="font-bold text-lg" style={{ color: "hsl(var(--warning))" }}>
        🚨 Requires Board of Management Approval (&gt; €5M)
      </div>
      <div className="text-sm text-muted-foreground mt-1">
        This contract exceeds the €5,000,000 threshold defined in BMW Playbook P-02. Route to the Board of Management before signature.
      </div>
    </div>
  </motion.div>
);

const Summary = ({ result }: { result: AuditResult }) => (
  <div className="rounded-2xl border border-border/60 gradient-card p-6 shadow-card">
    <div className="text-xs uppercase tracking-[0.2em] text-primary font-semibold mb-2">Contract summary</div>
    <p className="text-foreground leading-relaxed">{result.contract_summary}</p>
  </div>
);

const Violations = ({ violations }: { violations: Violation[] }) => {
  if (violations.length === 0) {
    return (
      <div className="rounded-2xl border border-success/30 p-8 text-center" style={{ background: "hsl(var(--success) / 0.05)" }}>
        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-success" />
        <h3 className="text-xl font-semibold">All clear</h3>
        <p className="text-muted-foreground mt-1">No issues against the playbook or statutory rules.</p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-semibold">Findings &amp; redlines</h3>
        <div className="text-xs text-muted-foreground font-mono">{violations.length} total</div>
      </div>
      {violations.map((v, i) => (
        <ViolationCard key={i} v={v} index={i + 1} />
      ))}
    </div>
  );
};

const ViolationCard = ({ v, index }: { v: Violation; index: number }) => {
  const sev = v.severity === "High" ? "high" : "medium";
  const rule = lookupRule(v.reference);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-2xl border border-border/60 gradient-card overflow-hidden shadow-card"
    >
      <div className="p-5 border-b border-border/60">
        <div className="flex items-start justify-between gap-4 mb-3 flex-wrap">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs font-mono text-muted-foreground">#{String(index).padStart(2, "0")}</span>
            <span
              className="px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider"
              style={{ background: `hsl(var(--severity-${sev}) / 0.15)`, color: `hsl(var(--severity-${sev}))` }}
            >
              {v.severity} severity
            </span>
            {rule ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button className="px-2.5 py-1 rounded-md text-[10px] font-mono uppercase tracking-wider border border-border bg-background/40 hover:border-primary/60 transition-colors flex items-center gap-1.5">
                    <FileWarning className="h-3 w-3" />
                    {v.reference}
                  </button>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <div className="text-xs uppercase tracking-wider opacity-70 mb-1">{rule.source} · {rule.id}</div>
                  <div className="font-semibold mb-1">{rule.title}</div>
                  <div className="text-xs opacity-90">{rule.body}</div>
                </TooltipContent>
              </Tooltip>
            ) : (
              <span className="px-2.5 py-1 rounded-md text-[10px] font-mono uppercase tracking-wider border border-border bg-background/40">
                {v.reference}
              </span>
            )}
          </div>
        </div>
        <p className="text-foreground leading-relaxed">{v.issue}</p>
      </div>

      <div className="p-5 bg-background/40">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-2">
          Original → Suggested redline
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
              contentText: { fontFamily: "'JetBrains Mono', monospace", fontSize: "12px", lineHeight: "1.6" },
            }}
          />
        </div>
      </div>
    </motion.div>
  );
};

export default Review;