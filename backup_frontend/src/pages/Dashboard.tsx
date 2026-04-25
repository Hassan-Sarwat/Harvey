import { useEffect, useState } from "react";
import { getDashboardMetrics } from "../api/client";

export function Dashboard() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getDashboardMetrics().then(setMetrics).catch(() => setMetrics({ error: "Could not load metrics" }));
  }, []);

  return (
    <section>
      <h1>AI Performance Dashboard</h1>
      <pre>{JSON.stringify(metrics, null, 2)}</pre>
    </section>
  );
}
