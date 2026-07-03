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
  review_status: "pending_review" | "needs_revision" | "approved" | "rejected";
  quality_score: number;
  extraction_method: "rule_based_mock";
  created_at: string;
  reviewer?: string | null;
  review_note?: string | null;
  reviewed_at?: string | null;
  updated_at?: string | null;
};

type CandidateEditState = {
  question: string;
  answer: string;
  intent: KnowledgeCandidate["intent"];
  tags: string;
  risk_level: KnowledgeCandidate["risk_level"];
  quality_score: string;
};

type RagChunk = {
  chunk_id: string;
  candidate_id: string;
  source_batch_id: string;
  source_conversation_id: string;
  source_message_ids: string[];
  knowledge_type: KnowledgeCandidate["knowledge_type"];
  intent: KnowledgeCandidate["intent"];
  tags: string[];
  risk_level: KnowledgeCandidate["risk_level"];
  quality_score: number;
  review_status: "approved";
  chunk_text: string;
  created_at: string;
  build_method: "local_json_mock_retrieval";
};

type RagBuildResult = {
  built_count: number;
  skipped_count: number;
  skipped_reasons: Record<string, number>;
  chunk_count: number;
  status: "completed";
  build_method: "local_json_mock_retrieval";
  created_at: string;
};

type RagSearchResult = RagChunk & {
  score: number;
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
  const [reviewQueue, setReviewQueue] = useState<KnowledgeCandidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<KnowledgeCandidate | null>(null);
  const [candidateEdit, setCandidateEdit] = useState<CandidateEditState | null>(null);
  const [reviewer, setReviewer] = useState("local_reviewer");
  const [reviewNote, setReviewNote] = useState("");
  const [ragBuildResult, setRagBuildResult] = useState<RagBuildResult | null>(null);
  const [ragChunks, setRagChunks] = useState<RagChunk[]>([]);
  const [ragQuery, setRagQuery] = useState("shipping Germany");
  const [ragTopK, setRagTopK] = useState("5");
  const [ragSearchResults, setRagSearchResults] = useState<RagSearchResult[]>([]);
  const [isBuildingRag, setIsBuildingRag] = useState(false);
  const [isSearchingRag, setIsSearchingRag] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadSources();
    void loadReviewQueue();
    void loadCandidates();
    void loadRagChunks();
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
      await loadReviewQueue();
    } catch {
      setError("Could not load knowledge candidates.");
    }
  }

  async function loadReviewQueue() {
    setError(null);
    try {
      const response = await fetch("/api/review/pending");
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Could not load review queue.");
        return;
      }
      setReviewQueue(body.data.candidates);
    } catch {
      setError("Could not load review queue.");
    }
  }

  function selectCandidate(candidate: KnowledgeCandidate) {
    setSelectedCandidate(candidate);
    setCandidateEdit({
      question: candidate.question,
      answer: candidate.answer,
      intent: candidate.intent,
      tags: candidate.tags.join(", "),
      risk_level: candidate.risk_level,
      quality_score: String(candidate.quality_score)
    });
    setReviewNote(candidate.review_note || "");
  }

  async function saveCandidateEdits() {
    if (!selectedCandidate || !candidateEdit) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(
        `/api/knowledge/candidates/${selectedCandidate.candidate_id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            question: candidateEdit.question,
            answer: candidateEdit.answer,
            intent: candidateEdit.intent,
            tags: candidateEdit.tags
              .split(",")
              .map((tag) => tag.trim())
              .filter(Boolean),
            risk_level: candidateEdit.risk_level,
            quality_score: Number(candidateEdit.quality_score)
          })
        }
      );
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Could not save candidate edits.");
        return;
      }
      setSelectedCandidate(body.data);
      selectCandidate(body.data);
      await loadCandidates();
    } catch {
      setError("Could not save candidate edits.");
    }
  }

  async function reviewCandidate(action: "approve" | "reject" | "needs-revision") {
    if (!selectedCandidate) {
      return;
    }
    if (!reviewer.trim()) {
      setError("Reviewer is required.");
      return;
    }
    setError(null);
    try {
      const response = await fetch(
        `/api/review/${selectedCandidate.candidate_id}/${action}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            reviewer: reviewer.trim(),
            review_note: reviewNote
          })
        }
      );
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Review action failed.");
        return;
      }
      setSelectedCandidate(body.data);
      selectCandidate(body.data);
      await loadCandidates();
      await loadReviewQueue();
      await loadRagChunks();
    } catch {
      setError("Review action failed.");
    }
  }

  async function loadRagChunks() {
    setError(null);
    try {
      const response = await fetch("/api/rag/chunks");
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("Could not load RAG chunks.");
        return;
      }
      setRagChunks(body.data.chunks);
    } catch {
      setError("Could not load RAG chunks.");
    }
  }

  async function buildRagChunks() {
    setError(null);
    setIsBuildingRag(true);
    setRagBuildResult(null);
    setRagSearchResults([]);
    try {
      const response = await fetch("/api/rag/build", {
        method: "POST"
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("RAG build failed.");
        return;
      }
      setRagBuildResult(body.data);
      await loadRagChunks();
    } catch {
      setError("RAG build request failed.");
    } finally {
      setIsBuildingRag(false);
    }
  }

  async function searchRag() {
    if (!ragQuery.trim()) {
      setError("RAG search query is required.");
      return;
    }
    setError(null);
    setIsSearchingRag(true);
    setRagSearchResults([]);
    try {
      const response = await fetch("/api/rag/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          query: ragQuery.trim(),
          top_k: Number(ragTopK)
        })
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        setError("RAG search failed.");
        return;
      }
      setRagSearchResults(body.data.results);
    } catch {
      setError("RAG search request failed.");
    } finally {
      setIsSearchingRag(false);
    }
  }

  const approvedCandidateCount = candidates.filter(
    (candidate) => candidate.review_status === "approved"
  ).length;

  return (
    <main className="app-shell">
      <section className="workspace">
        <p className="eyebrow">DataHub</p>
        <h1>Local RAG builder</h1>
        <p className="summary">
          M6 builds local JSON RAG chunks from approved knowledge candidates
          only. This is an internal retrieval test, not a CustomerOpsAgent
          integration and not a real vector database.
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

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">Human review</p>
              <h2>Review candidates</h2>
            </div>
            <button type="button" className="secondary" onClick={loadReviewQueue}>
              Refresh queue
            </button>
          </div>
          <p className="warning-note">
            Approved here means human-reviewed only. It is not indexed, embedded,
            or available to CustomerOpsAgent.
          </p>

          {reviewQueue.length === 0 ? (
            <p className="empty-state">No pending or needs-revision candidates.</p>
          ) : (
            <div className="batch-list">
              {reviewQueue.map((candidate) => (
                <article className="batch-row" key={candidate.candidate_id}>
                  <div>
                    <strong>{candidate.question}</strong>
                    <span>{candidate.candidate_id}</span>
                    <span>
                      {candidate.review_status} - {candidate.intent} - quality{" "}
                      {candidate.quality_score}
                    </span>
                  </div>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => selectCandidate(candidate)}
                    >
                      Review
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        {selectedCandidate && candidateEdit ? (
          <section className="panel">
            <p className="eyebrow compact">Candidate detail</p>
            <h2>{selectedCandidate.candidate_id}</h2>
            <div className="review-grid">
              <label>
                <span>Question</span>
                <textarea
                  className="compact-textarea"
                  value={candidateEdit.question}
                  onChange={(event) =>
                    setCandidateEdit({ ...candidateEdit, question: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Answer</span>
                <textarea
                  className="compact-textarea"
                  value={candidateEdit.answer}
                  onChange={(event) =>
                    setCandidateEdit({ ...candidateEdit, answer: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Intent</span>
                <select
                  value={candidateEdit.intent}
                  onChange={(event) =>
                    setCandidateEdit({
                      ...candidateEdit,
                      intent: event.target.value as KnowledgeCandidate["intent"]
                    })
                  }
                >
                  <option value="shipping">shipping</option>
                  <option value="refund">refund</option>
                  <option value="order_status">order_status</option>
                  <option value="product_info">product_info</option>
                  <option value="handoff">handoff</option>
                  <option value="prohibited_answer">prohibited_answer</option>
                  <option value="general">general</option>
                </select>
              </label>
              <label>
                <span>Tags</span>
                <input
                  value={candidateEdit.tags}
                  onChange={(event) =>
                    setCandidateEdit({ ...candidateEdit, tags: event.target.value })
                  }
                />
              </label>
              <label>
                <span>Risk level</span>
                <select
                  value={candidateEdit.risk_level}
                  onChange={(event) =>
                    setCandidateEdit({
                      ...candidateEdit,
                      risk_level: event.target.value as KnowledgeCandidate["risk_level"]
                    })
                  }
                >
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
              <label>
                <span>Quality score</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={candidateEdit.quality_score}
                  onChange={(event) =>
                    setCandidateEdit({
                      ...candidateEdit,
                      quality_score: event.target.value
                    })
                  }
                />
              </label>
              <label>
                <span>Reviewer</span>
                <input
                  value={reviewer}
                  onChange={(event) => setReviewer(event.target.value)}
                />
              </label>
              <label>
                <span>Review note</span>
                <textarea
                  className="compact-textarea"
                  value={reviewNote}
                  onChange={(event) => setReviewNote(event.target.value)}
                />
              </label>
            </div>
            <div className="review-actions">
              <button type="button" className="secondary" onClick={saveCandidateEdits}>
                Save edits
              </button>
              <button type="button" onClick={() => reviewCandidate("approve")}>
                Approve
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => reviewCandidate("needs-revision")}
              >
                Needs revision
              </button>
              <button
                type="button"
                className="danger"
                onClick={() => reviewCandidate("reject")}
              >
                Reject
              </button>
            </div>
            <dl className="review-meta">
              <div>
                <dt>review_status</dt>
                <dd>{selectedCandidate.review_status}</dd>
              </div>
              <div>
                <dt>source_batch_id</dt>
                <dd>{selectedCandidate.source_batch_id}</dd>
              </div>
              <div>
                <dt>source_conversation_id</dt>
                <dd>{selectedCandidate.source_conversation_id}</dd>
              </div>
              <div>
                <dt>source_message_ids</dt>
                <dd>{selectedCandidate.source_message_ids.join(", ")}</dd>
              </div>
            </dl>
          </section>
        ) : null}

        <section className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow compact">Local RAG test</p>
              <h2>Build chunks from approved candidates</h2>
            </div>
            <button type="button" className="secondary" onClick={loadRagChunks}>
              Refresh chunks
            </button>
          </div>
          <p className="warning-note">
            Only approved candidates can enter this local RAG test. It is not
            connected to CustomerOpsAgent, embeddings, or a real vector store.
          </p>
          <div className="rag-toolbar">
            <div>
              <span className="label">Approved candidates</span>
              <strong>{approvedCandidateCount}</strong>
            </div>
            <div>
              <span className="label">RAG chunks</span>
              <strong>{ragChunks.length}</strong>
            </div>
            <button type="button" onClick={buildRagChunks} disabled={isBuildingRag}>
              {isBuildingRag ? "Building..." : "Build RAG chunks"}
            </button>
          </div>

          {ragBuildResult ? (
            <div className="result-panel compact-panel" aria-live="polite">
              <h2>RAG build complete</h2>
              <dl>
                <div>
                  <dt>built_count</dt>
                  <dd>{ragBuildResult.built_count}</dd>
                </div>
                <div>
                  <dt>skipped_count</dt>
                  <dd>{ragBuildResult.skipped_count}</dd>
                </div>
                <div>
                  <dt>chunk_count</dt>
                  <dd>{ragBuildResult.chunk_count}</dd>
                </div>
                <div>
                  <dt>status</dt>
                  <dd>{ragBuildResult.status}</dd>
                </div>
                <div>
                  <dt>skipped_reasons</dt>
                  <dd>{JSON.stringify(ragBuildResult.skipped_reasons)}</dd>
                </div>
              </dl>
            </div>
          ) : null}

          {ragChunks.length === 0 ? (
            <p className="empty-state">
              No RAG chunks built yet. Approve at least one candidate first.
            </p>
          ) : (
            <div className="message-list">
              {ragChunks.map((chunk) => (
                <article className="candidate-card" key={chunk.chunk_id}>
                  <div className="message-meta">
                    <span>{chunk.review_status}</span>
                    <span>{chunk.intent}</span>
                    <span>quality {chunk.quality_score}</span>
                  </div>
                  <h3>{chunk.chunk_id}</h3>
                  <p>{chunk.chunk_text}</p>
                  <dl className="review-meta">
                    <div>
                      <dt>candidate_id</dt>
                      <dd>{chunk.candidate_id}</dd>
                    </div>
                    <div>
                      <dt>source_conversation_id</dt>
                      <dd>{chunk.source_conversation_id}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <p className="eyebrow compact">RAG search</p>
          <h2>Internal retrieval test</h2>
          <div className="search-row">
            <label>
              <span>Query</span>
              <input
                value={ragQuery}
                onChange={(event) => setRagQuery(event.target.value)}
              />
            </label>
            <label>
              <span>Top K</span>
              <input
                type="number"
                min="1"
                max="20"
                value={ragTopK}
                onChange={(event) => setRagTopK(event.target.value)}
              />
            </label>
            <button type="button" onClick={searchRag} disabled={isSearchingRag}>
              {isSearchingRag ? "Searching..." : "Search RAG"}
            </button>
          </div>

          {ragSearchResults.length === 0 ? (
            <p className="empty-state">No search results shown yet.</p>
          ) : (
            <div className="message-list">
              {ragSearchResults.map((result) => (
                <article className="candidate-card" key={result.chunk_id}>
                  <div className="message-meta">
                    <span>score {result.score}</span>
                    <span>{result.chunk_id}</span>
                    <span>{result.candidate_id}</span>
                    <span>{result.source_conversation_id}</span>
                  </div>
                  <p>{result.chunk_text}</p>
                  <div className="pill-row">
                    {result.tags.map((tag) => (
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
            <strong>M6 local RAG builder</strong>
          </div>
        </div>
      </section>
    </main>
  );
}
