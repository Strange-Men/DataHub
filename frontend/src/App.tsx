import { FormEvent, useEffect, useState } from "react";

type ImportResult = {
  batch_id: string;
  source_name: string;
  message_count: number;
  conversation_count: number;
  created_at: string;
  status: "raw_imported";
};

type CleaningJob = {
  job_id: string;
  source_batch_id: string;
  sanitized_batch_id: string;
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  status: "completed";
  created_at: string;
  completed_at: string;
};

type SanitizedMessage = {
  conversation_id: string;
  message_id: string;
  source_message_id: string;
  role: "customer" | "agent" | "system";
  content: string;
  pii_detected: boolean;
  pii_types: string[];
  cleaning_notes: string[];
};

type SanitizedBatch = {
  batch_id: string;
  source_batch_id: string;
  status: "sanitized";
  raw_message_count: number;
  sanitized_message_count: number;
  dropped_message_count: number;
  pii_detected_count: number;
  created_at: string;
  messages: SanitizedMessage[];
};

type ExtractionJob = {
  job_id: string;
  source_batch_id: string;
  candidate_count: number;
  status: "completed";
  extraction_method: "rule_based_mock";
  created_at: string;
  completed_at: string;
};

type KnowledgeCandidate = {
  candidate_id: string;
  source_batch_id: string;
  source_conversation_id: string;
  source_message_ids: string[];
  knowledge_type:
    | "faq"
    | "standard_answer"
    | "business_rule"
    | "human_handoff_rule"
    | "forbidden_answer_rule";
  question: string;
  answer: string;
  intent:
    | "shipping"
    | "refund"
    | "order_status"
    | "product_info"
    | "handoff"
    | "prohibited_answer"
    | "general";
  tags: string[];
  risk_level: "low" | "medium" | "high";
  review_status: "pending_review";
  quality_score: number;
  extraction_method: "rule_based_mock";
  created_at: string;
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
        },
        {
          "message_id": "msg_003",
          "role": "customer",
          "content": "Please contact me at alex.customer@example.test or +1 202 555 0175. My order number is ORDER-AX91-4455.",
          "timestamp": "2026-07-03T10:02:00"
        },
        {
          "message_id": "msg_004",
          "role": "agent",
          "content": "We can help. The tracking number TRK-9988776655 shows dispatch is pending.",
          "timestamp": "2026-07-03T10:03:00"
        }
      ]
    },
    {
      "conversation_id": "conv_002",
      "messages": [
        {
          "message_id": "msg_005",
          "role": "customer",
          "content": "Ship it to 123 Example Street, Testville.",
          "timestamp": "2026-07-03T11:10:00"
        },
        {
          "message_id": "msg_006",
          "role": "agent",
          "content": " ",
          "timestamp": "2026-07-03T11:11:00"
        }
      ]
    }
  ]
}`);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingSources, setIsLoadingSources] = useState(false);
  const [runningBatchId, setRunningBatchId] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [sources, setSources] = useState<ImportResult[]>([]);
  const [cleaningResult, setCleaningResult] = useState<CleaningJob | null>(null);
  const [sanitizedBatch, setSanitizedBatch] = useState<SanitizedBatch | null>(null);
  const [sanitizedBatches, setSanitizedBatches] = useState<SanitizedBatch[]>([]);
  const [runningExtractionBatchId, setRunningExtractionBatchId] = useState<string | null>(null);
  const [extractionResult, setExtractionResult] = useState<ExtractionJob | null>(null);
  const [candidates, setCandidates] = useState<KnowledgeCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadSources();
  }, []);

  async function loadSources() {
    setIsLoadingSources(true);
    try {
      const response = await fetch("/api/sources");
      const body = await response.json();
      if (response.ok && body.success) {
        const sourceList = body.data.sources;
        setSources(sourceList);
        await loadSanitizedBatchList(sourceList);
      }
    } catch {
      setError("Could not load raw batch list. Confirm the backend is running.");
    } finally {
      setIsLoadingSources(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);
    setCleaningResult(null);
    setSanitizedBatch(null);
    setExtractionResult(null);
    setCandidates([]);
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
        setError("Import failed. Confirm the JSON follows the sample format.");
        return;
      }
      setResult(body.data);
      await loadSources();
    } catch {
      setError("Import request failed. Confirm the FastAPI backend is running.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function runCleaning(batchId: string) {
    setError(null);
    setCleaningResult(null);
    setSanitizedBatch(null);
    setRunningBatchId(batchId);
    try {
      const response = await fetch(`/api/cleaning/run/${batchId}`, {
        method: "POST"
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Cleaning failed. Confirm the raw batch still exists.");
        return;
      }
      setCleaningResult(body.data);
      await loadSanitized(batchId);
      await loadSources();
    } catch {
      setError("Cleaning request failed. Confirm the FastAPI backend is running.");
    } finally {
      setRunningBatchId(null);
    }
  }

  async function loadSanitized(batchId: string, options?: { silent?: boolean }) {
    if (!options?.silent) {
      setError(null);
    }
    try {
      const response = await fetch(`/api/sanitized/${batchId}`);
      const body = await response.json();
      if (!response.ok || !body.success) {
        if (!options?.silent) {
          setError("No sanitized batch found for this raw batch yet.");
        }
        return null;
      }
      setSanitizedBatch(body.data);
      return body.data as SanitizedBatch;
    } catch {
      if (!options?.silent) {
        setError("Could not load sanitized batch.");
      }
      return null;
    }
  }

  async function loadSanitizedBatchList(sourceList: ImportResult[]) {
    const loaded = await Promise.all(
      sourceList.map((source) => loadSanitized(source.batch_id, { silent: true }))
    );
    setSanitizedBatches(
      loaded.filter((batch): batch is SanitizedBatch => batch !== null)
    );
  }

  async function runExtraction(batchId: string) {
    setError(null);
    setExtractionResult(null);
    setCandidates([]);
    setRunningExtractionBatchId(batchId);
    try {
      const response = await fetch(`/api/extraction/run/${batchId}`, {
        method: "POST"
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Extraction failed. Confirm the sanitized batch exists.");
        return;
      }
      setExtractionResult(body.data);
      await loadCandidates();
    } catch {
      setError("Extraction request failed. Confirm the FastAPI backend is running.");
    } finally {
      setRunningExtractionBatchId(null);
    }
  }

  async function loadCandidates() {
    setError(null);
    try {
      const response = await fetch("/api/knowledge/candidates");
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Could not load knowledge candidates.");
        return;
      }
      setCandidates(body.data.candidates);
    } catch {
      setError("Could not load knowledge candidates.");
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <p className="eyebrow">DataHub</p>
        <h1>Knowledge candidates</h1>
        <p className="summary">
          M4 extracts pending-review knowledge candidates from sanitized
          customer service chat batches. These candidates are not approved and
          cannot enter RAG.
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

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">Raw batches</p>
              <h2>Run cleaning</h2>
            </div>
            <button type="button" className="secondary" onClick={loadSources}>
              {isLoadingSources ? "Loading..." : "Refresh"}
            </button>
          </div>

          {sources.length === 0 ? (
            <p className="empty-state">No raw batches imported yet.</p>
          ) : (
            <div className="batch-list">
              {sources.map((source) => (
                <article className="batch-row" key={source.batch_id}>
                  <div>
                    <strong>{source.source_name}</strong>
                    <span>{source.batch_id}</span>
                    <span>
                      {source.message_count} messages across{" "}
                      {source.conversation_count} conversations
                    </span>
                  </div>
                  <div className="row-actions">
                    <button
                      type="button"
                      onClick={() => runCleaning(source.batch_id)}
                      disabled={runningBatchId === source.batch_id}
                    >
                      {runningBatchId === source.batch_id
                        ? "Cleaning..."
                        : "Run cleaning"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void loadSanitized(source.batch_id)}
                    >
                      View sanitized
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        {cleaningResult ? (
          <div className="result-panel" aria-live="polite">
            <h2>Cleaning complete</h2>
            <dl>
              <div>
                <dt>job_id</dt>
                <dd>{cleaningResult.job_id}</dd>
              </div>
              <div>
                <dt>raw_message_count</dt>
                <dd>{cleaningResult.raw_message_count}</dd>
              </div>
              <div>
                <dt>sanitized_message_count</dt>
                <dd>{cleaningResult.sanitized_message_count}</dd>
              </div>
              <div>
                <dt>dropped_message_count</dt>
                <dd>{cleaningResult.dropped_message_count}</dd>
              </div>
              <div>
                <dt>pii_detected_count</dt>
                <dd>{cleaningResult.pii_detected_count}</dd>
              </div>
              <div>
                <dt>status</dt>
                <dd>{cleaningResult.status}</dd>
              </div>
            </dl>
          </div>
        ) : null}

        {sanitizedBatch ? (
          <section className="panel">
            <p className="eyebrow compact">Sanitized batch</p>
            <h2>{sanitizedBatch.batch_id}</h2>
            <p className="summary compact-summary">
              {sanitizedBatch.sanitized_message_count} sanitized messages,{" "}
              {sanitizedBatch.dropped_message_count} dropped,{" "}
              {sanitizedBatch.pii_detected_count} with PII masked.
            </p>
            <div className="message-list">
              {sanitizedBatch.messages.map((message) => (
                <article
                  className="sanitized-message"
                  key={`${message.conversation_id}-${message.message_id}`}
                >
                  <div className="message-meta">
                    <span>{message.role}</span>
                    <span>{message.conversation_id}</span>
                    <span>{message.message_id}</span>
                  </div>
                  <p>{message.content}</p>
                  <div className="pill-row">
                    {message.pii_detected ? (
                      message.pii_types.map((type) => (
                        <span className="pill" key={type}>
                          {type}
                        </span>
                      ))
                    ) : (
                      <span className="pill muted">no pii</span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">Sanitized batches</p>
              <h2>Run extraction</h2>
            </div>
            <button type="button" className="secondary" onClick={loadSources}>
              Refresh
            </button>
          </div>

          {sanitizedBatches.length === 0 ? (
            <p className="empty-state">
              No sanitized batches found. Import raw JSON and run cleaning first.
            </p>
          ) : (
            <div className="batch-list">
              {sanitizedBatches.map((batch) => (
                <article className="batch-row" key={batch.batch_id}>
                  <div>
                    <strong>{batch.batch_id}</strong>
                    <span>{batch.status}</span>
                    <span>
                      {batch.sanitized_message_count} sanitized messages,{" "}
                      {batch.pii_detected_count} with PII masked
                    </span>
                  </div>
                  <div className="row-actions">
                    <button
                      type="button"
                      onClick={() => runExtraction(batch.batch_id)}
                      disabled={runningExtractionBatchId === batch.batch_id}
                    >
                      {runningExtractionBatchId === batch.batch_id
                        ? "Extracting..."
                        : "Run extraction"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        {extractionResult ? (
          <div className="result-panel" aria-live="polite">
            <h2>Extraction complete</h2>
            <dl>
              <div>
                <dt>job_id</dt>
                <dd>{extractionResult.job_id}</dd>
              </div>
              <div>
                <dt>source_batch_id</dt>
                <dd>{extractionResult.source_batch_id}</dd>
              </div>
              <div>
                <dt>candidate_count</dt>
                <dd>{extractionResult.candidate_count}</dd>
              </div>
              <div>
                <dt>status</dt>
                <dd>{extractionResult.status}</dd>
              </div>
              <div>
                <dt>method</dt>
                <dd>{extractionResult.extraction_method}</dd>
              </div>
            </dl>
          </div>
        ) : null}

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">Knowledge candidates</p>
              <h2>Pending review only</h2>
            </div>
            <button type="button" className="secondary" onClick={loadCandidates}>
              Refresh
            </button>
          </div>
          <p className="warning-note">
            Candidates are not approved knowledge and cannot enter RAG.
          </p>
          {candidates.length === 0 ? (
            <p className="empty-state">No knowledge candidates extracted yet.</p>
          ) : (
            <div className="message-list">
              {candidates.map((candidate) => (
                <article className="candidate-card" key={candidate.candidate_id}>
                  <div className="message-meta">
                    <span>{candidate.review_status}</span>
                    <span>{candidate.knowledge_type}</span>
                    <span>{candidate.intent}</span>
                    <span>quality {candidate.quality_score}</span>
                  </div>
                  <h3>{candidate.question}</h3>
                  <p>{candidate.answer}</p>
                  <div className="pill-row">
                    {candidate.tags.map((tag) => (
                      <span className="pill" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

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
            <strong>M4 knowledge candidates</strong>
          </div>
        </div>
      </section>
    </main>
  );
}
