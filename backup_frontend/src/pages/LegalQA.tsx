import { useState } from "react";
import { askLegalQuestion } from "../api/client";

export function LegalQA() {
  const [question, setQuestion] = useState("Can a supplier waive GDPR data subject rights?");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  async function submit() {
    setResult(await askLegalQuestion(question, "BMW data processing agreement", "data_protection"));
  }

  return (
    <section>
      <h1>Legal Q&A</h1>
      <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
      <button className="primary" onClick={submit}>Ask</button>
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </section>
  );
}
