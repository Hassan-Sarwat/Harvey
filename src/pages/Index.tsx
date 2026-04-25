import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowRight, ShieldCheck, Scale, FileSearch, Sparkles, Lock, Gauge } from "lucide-react";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: ShieldCheck,
    title: "Internal Playbook",
    desc: "Four-Eyes Principle, €5M Board threshold, sub-processor consent and audit-rights checks.",
  },
  {
    icon: Scale,
    title: "GDPR + BDSG",
    desc: "Art. 28, 32, 33 GDPR and German BDSG enforced with statutory citations.",
  },
  {
    icon: FileSearch,
    title: "Redline Suggestions",
    desc: "Concrete replacement clauses, severity-graded and ready to paste into the contract.",
  },
  {
    icon: Lock,
    title: "Escalation Routing",
    desc: "Auto-flags Board of Management approval for any contract above €5,000,000.",
  },
];

const stats = [
  { value: "15+", label: "Rules enforced" },
  { value: "<8s", label: "Avg. audit time" },
  { value: "100%", label: "Citations grounded" },
];

const Index = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="border-b border-border/60 backdrop-blur-md sticky top-0 z-40 bg-background/70">
        <nav className="container mx-auto flex items-center justify-between py-4">
          <Link to="/" className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg gradient-primary grid place-items-center shadow-glow">
              <Scale className="h-4 w-4 text-primary-foreground" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">BMW Group</div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Legal AI Auditor</div>
            </div>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
            <a href="#features" className="hover:text-foreground transition-colors">Capabilities</a>
            <a href="#how" className="hover:text-foreground transition-colors">How it works</a>
            <a href="#stack" className="hover:text-foreground transition-colors">Knowledge base</a>
          </div>
          <Link to="/review">
            <Button size="sm" className="gradient-primary border-0 text-primary-foreground hover:opacity-90">
              Open Auditor
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 gradient-hero" aria-hidden />
        <div className="absolute inset-0 grid-bg opacity-[0.25]" aria-hidden />
        <div className="container mx-auto relative py-24 md:py-32">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1] }}
            className="max-w-3xl"
          >
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-border/80 bg-card/60 backdrop-blur text-xs font-medium text-muted-foreground mb-6">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              Powered by Lovable AI · Gemini 2.5 Pro
            </div>
            <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.05] mb-6">
              Audit any DPA in <span className="text-gradient">seconds</span>, not weeks.
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mb-10">
              The BMW Group's internal counsel for Data Processing Agreements. Cross-checks every clause
              against the corporate playbook and German GDPR law, then drafts the redlines for you.
            </p>
            <div className="flex flex-wrap gap-3">
              <Link to="/review">
                <Button size="lg" className="gradient-primary border-0 text-primary-foreground shadow-elegant hover:opacity-90 h-12 px-6">
                  Audit a contract
                  <Sparkles className="h-4 w-4 ml-2" />
                </Button>
              </Link>
              <a href="#features">
                <Button size="lg" variant="outline" className="h-12 px-6 border-border/80">
                  See capabilities
                </Button>
              </a>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-6 mt-16 max-w-xl">
              {stats.map((s) => (
                <div key={s.label}>
                  <div className="text-3xl md:text-4xl font-bold text-gradient">{s.value}</div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground mt-1">{s.label}</div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="container mx-auto py-24">
        <div className="max-w-2xl mb-14">
          <div className="text-xs uppercase tracking-[0.25em] text-primary font-semibold mb-3">Capabilities</div>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight">Two knowledge bases. One verdict.</h2>
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className="group relative rounded-2xl border border-border/60 gradient-card p-8 shadow-card hover:border-primary/40 transition-colors"
            >
              <div className="h-12 w-12 rounded-xl bg-primary/10 border border-primary/20 grid place-items-center mb-5 group-hover:shadow-glow transition-shadow">
                <f.icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">{f.title}</h3>
              <p className="text-muted-foreground">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="container mx-auto py-24 border-t border-border/60">
        <div className="grid lg:grid-cols-2 gap-16 items-start">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-primary font-semibold mb-3">Workflow</div>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-6">From upload to redline in three steps.</h2>
            <p className="text-muted-foreground text-lg">
              The Auditor parses the contract, evaluates every clause against the BMW Playbook and GDPR,
              and returns a structured verdict with severity, citations and ready-to-paste redlines.
            </p>
          </div>
          <div className="space-y-3">
            {[
              { n: "01", t: "Upload contract", d: "Paste contract text or upload the DPA and any schedules." },
              { n: "02", t: "AI cross-checks", d: "Every clause evaluated against 15+ corporate and statutory rules." },
              { n: "03", t: "Receive verdict", d: "Status, escalation, severity-graded violations, citations and redlines." },
            ].map((s) => (
              <div key={s.n} className="flex gap-5 p-5 rounded-xl border border-border/60 gradient-card">
                <div className="font-mono text-sm text-primary font-semibold pt-0.5">{s.n}</div>
                <div>
                  <div className="font-semibold mb-1">{s.t}</div>
                  <div className="text-sm text-muted-foreground">{s.d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto py-24">
        <div className="relative overflow-hidden rounded-3xl border border-primary/30 p-12 md:p-16 text-center gradient-card">
          <div className="absolute inset-0 gradient-hero opacity-60" aria-hidden />
          <div className="relative">
            <Gauge className="h-10 w-10 text-primary mx-auto mb-6" />
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">
              Ready to audit your first DPA?
            </h2>
            <p className="text-muted-foreground text-lg mb-8 max-w-xl mx-auto">
              Try it now with a sample contract — no setup required.
            </p>
            <Link to="/review">
              <Button size="lg" className="gradient-primary border-0 text-primary-foreground shadow-elegant h-12 px-8">
                Launch Auditor
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <footer id="stack" className="border-t border-border/60 py-10">
        <div className="container mx-auto flex flex-wrap justify-between items-center gap-4 text-xs text-muted-foreground">
          <div>BMW Group · Legal AI Auditor · Internal Prototype</div>
          <div className="font-mono">v0.1.0 · Hackathon Build</div>
        </div>
      </footer>
    </div>
  );
};

export default Index;
