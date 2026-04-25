import { useState } from "react";
import { reviewContract } from "../api/client";

const sampleText =
  "Supplier accepts unlimited liability. The supplier processes personal data for BMW but no effective date is listed.";

export function Review() {
  const [contractText, setContractText] = useState(sampleText);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runReview() {
    setError(null);
    try {
      setResult(await reviewContract(contractText, "data_protection"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  return (
    <section>
      <h1>Contract Review</h1>
      <textarea value={contractText} onChange={(event) => setContractText(event.target.value)} />
      <button className="primary" onClick={runReview}>Run AI Review</button>
      {error && <p className="error">{error}</p>}
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </section>
  );
}
