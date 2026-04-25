import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { WorkspaceSidebar, type WorkspaceView } from "@/components/workspace/Sidebar";
import { ReviewView } from "@/components/workspace/ReviewView";
import { QAView } from "@/components/workspace/QAView";
import { EscalationsView } from "@/components/workspace/EscalationsView";
import { DashboardView } from "@/components/workspace/DashboardView";

const titles: Record<WorkspaceView, { title: string; sub: string }> = {
  review: { title: "Review Contract", sub: "Upload or paste a contract for backend playbook review" },
  qa: { title: "Legal Q&A", sub: "Ask about GDPR, BDSG, legal evidence, or BMW playbook" },
  escalations: { title: "Escalations", sub: "Pending legal tickets with contract highlights, AI flags, and decisions" },
  dashboard: { title: "Dashboard", sub: "Backend metrics across reviews and legal outcomes" },
};

const Index = () => {
  const [view, setView] = useState<WorkspaceView>("review");
  const meta = titles[view];

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      <WorkspaceSidebar active={view} onChange={setView} />

      <div className="flex-1 flex flex-col min-w-0 h-screen">
        {/* Top bar */}
        <header className="border-b border-border/60 bg-background/70 backdrop-blur-md px-8 py-4 flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{meta.title}</h1>
            <p className="text-xs text-muted-foreground">{meta.sub}</p>
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-mono">
            BMW Group · Internal
          </div>
        </header>

        {/* View */}
        <main className="flex-1 min-h-0 overflow-hidden">
          <AnimatePresence mode="wait">
            <motion.div
              key={view}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
              className="h-full"
            >
              {view === "review" && <ReviewView />}
              {view === "qa" && <QAView />}
              {view === "escalations" && <EscalationsView />}
              {view === "dashboard" && <DashboardView />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
};

export default Index;
