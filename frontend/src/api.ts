import type { AppConfig, AskMode, DashboardMetrics, EscalationDetail, EscalationListItem, EscalationStatus, HistoryDetail, HistorySummary, RunResult } from "./types";

export async function getConfig(): Promise<AppConfig> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error("Could not load app config");
  return response.json();
}

export async function getDashboard(): Promise<DashboardMetrics> {
  const response = await fetch("/api/dashboard");
  if (!response.ok) throw new Error("Could not load dashboard metrics");
  return response.json();
}

export async function runDemo(): Promise<RunResult> {
  const response = await fetch("/api/demo", { method: "POST" });
  if (!response.ok) throw new Error("Demo run failed");
  return response.json();
}

export async function analyzeMatter(payload: {
  message: string;
  mode: AskMode;
  threadId?: string | null;
  isFinalVersion?: boolean;
  files: File[];
  demoMode?: boolean;
  modelMode?: "quality" | "fast";
}): Promise<RunResult> {
  const form = new FormData();
  form.append("message", payload.message);
  form.append("mode", payload.mode);
  if (payload.threadId) form.append("thread_id", payload.threadId);
  form.append("is_final_version", payload.isFinalVersion ? "true" : "false");
  form.append("selected_sources", JSON.stringify([]));
  form.append("selected_agents", JSON.stringify([]));
  form.append("demo_mode", payload.demoMode ? "true" : "false");
  form.append("model_mode", payload.modelMode ?? "quality");
  payload.files.forEach((file) => form.append("files", file));

  let response: Response;
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      body: form
    });
  } catch (err) {
    const detail = err instanceof Error && err.message ? ` (${err.message})` : "";
    throw new Error(
      `Upload failed before Donna reached the backend${detail}. Make sure the backend is running at http://127.0.0.1:8000 and try the drop again.`
    );
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new Error(detail || "Analysis failed");
  }
  return response.json();
}

async function readErrorDetail(response: Response): Promise<string> {
  const raw = await response.text();
  if (!raw) return "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg?: unknown }).msg ?? item);
          }
          return String(item);
        })
        .join("; ");
    }
  } catch {
    // Keep the server text if it was not JSON.
  }
  return raw;
}

export async function getHistory(): Promise<{ items: HistorySummary[] }> {
  const response = await fetch("/api/history");
  if (!response.ok) throw new Error("Could not load history");
  return response.json();
}

export async function getHistoryItem(id: string): Promise<HistoryDetail> {
  const response = await fetch(`/api/history/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error("Could not load history item");
  return response.json();
}

export async function dropHistoryItem(id: string, reason?: string): Promise<HistoryDetail> {
  const response = await fetch(`/api/history/${encodeURIComponent(id)}/drop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason })
  });
  if (!response.ok) throw new Error("Could not drop history item");
  return response.json();
}

export async function listEscalations(status?: EscalationStatus): Promise<{ items: EscalationListItem[] }> {
  const url = status ? `/escalations?status=${encodeURIComponent(status)}` : "/escalations";
  const response = await fetch(url);
  if (!response.ok) throw new Error("Could not load escalations");
  return response.json();
}

export async function getEscalation(id: string): Promise<EscalationDetail> {
  const response = await fetch(`/escalations/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error("Could not load escalation detail");
  return response.json();
}

export async function askEscalationQuestion(id: string, question: string): Promise<{ answer: string; cited_context: unknown[] }> {
  const response = await fetch(`/escalations/${encodeURIComponent(id)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) throw new Error("Could not get answer from escalation context");
  return response.json();
}

export async function decideEscalation(
  id: string,
  payload: { decision: "accepted" | "denied"; notes?: string; fix_suggestions: string[]; decided_by?: string }
): Promise<EscalationDetail> {
  const response = await fetch(`/escalations/${encodeURIComponent(id)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Could not save escalation decision");
  }
  return response.json();
}
