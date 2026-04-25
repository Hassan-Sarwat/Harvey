import type { AppConfig, DashboardMetrics, RunResult } from "./types";

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
  question: string;
  context: string;
  sources: string[];
  agents: string[];
  files: File[];
  demoMode?: boolean;
}): Promise<RunResult> {
  const form = new FormData();
  form.append("question", payload.question);
  form.append("context", payload.context);
  form.append("selected_sources", JSON.stringify(payload.sources));
  form.append("selected_agents", JSON.stringify(payload.agents));
  form.append("demo_mode", payload.demoMode ? "true" : "false");
  payload.files.forEach((file) => form.append("files", file));

  const response = await fetch("/api/analyze", {
    method: "POST",
    body: form
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Analysis failed");
  }
  return response.json();
}
