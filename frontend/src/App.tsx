import { FormEvent, useState } from "react";

type ImportResult = {
  batch_id: string;
  source_name: string;
  message_count: number;
  conversation_count: number;
  created_at: string;
  status: "raw_imported";
};

export function App() {
  const [sourceName, setSourceName] = useState("sample_customer_chat");
  const [jsonText, setJsonText] = useState(`{
  "source_name": "sample_customer_chat",
  "conversations": [
    {
      "conversation_id": "conv_001",
      "messages": [
        {
          "message_id": "msg_001",
          "role": "customer",
          "content": "How long does shipping take to Germany?",
          "timestamp": "2026-07-03T10:00:00"
        },
        {
          "message_id": "msg_002",
          "role": "agent",
          "content": "Shipping to Germany usually takes 7-12 business days after dispatch.",
          "timestamp": "2026-07-03T10:01:00"
        }
      ]
    }
  ]
}`);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setError(null);

    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      setError("JSON is not valid. Please check the pasted content.");
      return;
    }

    if (!sourceName.trim()) {
      setError("Source name is required.");
      return;
    }

    const payload =
      parsed && typeof parsed === "object"
        ? { ...parsed, source_name: sourceName.trim() }
        : parsed;

    setIsSubmitting(true);
    try {
      const response = await fetch("/api/sources/import-json", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Import failed. Confirm the JSON follows the M2 sample format.");
        return;
      }
      setResult(body.data);
    } catch {
      setError("Import request failed. Confirm the FastAPI backend is running.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <p className="eyebrow">DataHub</p>
        <h1>JSON chat import</h1>
        <p className="summary">
          M2 only imports JSON customer service chat records and stores them as
          raw batches. Cleaning, desensitization, extraction, and RAG are not
          part of this milestone.
        </p>

        <form className="import-form" onSubmit={handleSubmit}>
          <label>
            <span>Source name</span>
            <input
              value={sourceName}
              onChange={(event) => setSourceName(event.target.value)}
              placeholder="sample_customer_chat"
            />
          </label>

          <label>
            <span>Customer chat JSON</span>
            <textarea
              value={jsonText}
              onChange={(event) => setJsonText(event.target.value)}
              spellCheck={false}
            />
          </label>

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Importing..." : "Import raw JSON"}
          </button>
        </form>

        {error ? <p className="message error">{error}</p> : null}

        {result ? (
          <div className="result-panel" aria-live="polite">
            <h2>Import complete</h2>
            <dl>
              <div>
                <dt>batch_id</dt>
                <dd>{result.batch_id}</dd>
              </div>
              <div>
                <dt>message_count</dt>
                <dd>{result.message_count}</dd>
              </div>
              <div>
                <dt>conversation_count</dt>
                <dd>{result.conversation_count}</dd>
              </div>
              <div>
                <dt>status</dt>
                <dd>{result.status}</dd>
              </div>
            </dl>
          </div>
        ) : null}

        <div className="status-grid" aria-label="Project status">
          <div>
            <span className="label">Frontend</span>
            <strong>React + TypeScript</strong>
          </div>
          <div>
            <span className="label">Backend</span>
            <strong>FastAPI + Python</strong>
          </div>
          <div>
            <span className="label">Current milestone</span>
            <strong>M2 raw JSON import</strong>
          </div>
        </div>
      </section>
    </main>
  );
}
