import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileSearch, MessagesSquare, AlertTriangle, LayoutDashboard, Scale } from "lucide-react";
import { getDashboardMetrics, listEscalations } from "@/api/client";
import { cn } from "@/lib/utils";

export type WorkspaceView = "review" | "qa" | "escalations" | "dashboard";

const items: { id: WorkspaceView; label: string; icon: typeof FileSearch; desc: string }[] = [
  { id: "review", label: "Review Contract", icon: FileSearch, desc: "Audit a DPA" },
  { id: "qa", label: "Legal Q&A", icon: MessagesSquare, desc: "Ask the AI counsel" },
  { id: "escalations", label: "Escalations", icon: AlertTriangle, desc: "Flagged contracts" },
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, desc: "KPIs & insights" },
];

export const WorkspaceSidebar = ({
  active,
  onChange,
}: {
  active: WorkspaceView;
  onChange: (v: WorkspaceView) => void;
}) => {
  const [counts, setCounts] = useState<Partial<Record<WorkspaceView, number>>>({});

  useEffect(() => {
    let active = true;
    Promise.all([listEscalations("pending_legal"), getDashboardMetrics()])
      .then(([escalations, metrics]) => {
        if (!active) return;
        setCounts({
          escalations: escalations.items.length,
          dashboard: metrics.escalation_metrics?.total_escalations ?? escalations.items.length,
        });
      })
      .catch(() => {
        if (active) setCounts({});
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <aside className="w-[260px] shrink-0 border-r border-border/60 bg-card/40 backdrop-blur-xl flex flex-col h-screen sticky top-0">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-border/60 flex items-center gap-3">
        <div className="h-10 w-10 rounded-lg gradient-primary grid place-items-center shadow-glow">
          <Scale className="h-5 w-5 text-primary-foreground" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">BMW Group</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Legal AI Auditor</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="px-3 mb-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
          Workspace
        </div>
        {items.map((it) => {
          const isActive = active === it.id;
          const Icon = it.icon;
          const count = counts[it.id];
          return (
            <button
              key={it.id}
              onClick={() => onChange(it.id)}
              className={cn(
                "w-full group relative text-left px-3 py-2.5 rounded-lg flex items-center gap-3 transition-colors",
                isActive
                  ? "bg-primary/15 text-foreground"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-active"
                  className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-primary"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <Icon className={cn("h-4 w-4 shrink-0", isActive && "text-primary")} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{it.label}</div>
                <div className="text-[10px] text-muted-foreground/70 truncate">{it.desc}</div>
              </div>
              {count !== undefined && count > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-muted/60 text-muted-foreground">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border/60 text-[10px] text-muted-foreground font-mono flex items-center justify-between">
        <span>v0.2.0</span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          Live
        </span>
      </div>
    </aside>
  );
};
