import { useEffect, useState } from "react";
import { listEscalations } from "../api/client";

export function Escalations() {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    listEscalations().then(setResult).catch(() => setResult({ error: "Could not load escalations" }));
  }, []);

  return (
    <section>
      <h1>Escalation Investigation</h1>
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </section>
  );
}
