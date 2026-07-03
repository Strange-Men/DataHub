# DataHub Tech Stack Candidates

This document records current technical direction and candidates. It does not finalize every infrastructure choice.

## 1. Confirmed Stack

### 1.1 Frontend

Confirmed:

- React
- TypeScript

Reason:

- DataHub phase one needs a focused single-page management backend.
- SSR is not required.
- Next.js App Router is not needed.
- React + TypeScript is sufficient for import, review, queue, and management workflows.

### 1.2 Backend

Confirmed:

- FastAPI
- Python

Reason:

- FastAPI is suitable for typed API development.
- Python is convenient for text processing, LLM integration, RAG experiments, and data processing scripts.
- It keeps the backend close to the AI and data processing ecosystem.

## 2. Frontend Build Candidate

### 2.1 Vite

Pros:

- Lightweight setup for React + TypeScript.
- Fast local development.
- Suitable for SPA management systems.
- Avoids unnecessary full-stack framework complexity.

Cons:

- Does not provide SSR or server-side routing.
- Requires separate backend deployment.

Phase-one recommendation:

- Recommended.

Why:

- DataHub does not need SSR.
- A Vite SPA plus FastAPI backend matches the current scope.

## 3. Database Candidates

### 3.1 SQLite

Pros:

- Very simple local setup.
- Good for early prototype and documentation-driven validation.
- No separate database service required.
- Easy to reset during development.

Cons:

- Not ideal for concurrent multi-user workflows.
- Not ideal for production-like deployments.
- Vector support and operational tooling are limited compared with PostgreSQL.

Phase-one recommendation:

- Recommended only for the earliest local prototype if speed matters.

Why:

- It can reduce setup cost during M1 or very early M2.
- It should not be treated as the likely long-term storage choice.

### 3.2 PostgreSQL

Pros:

- Strong relational data model.
- Good for traceability, review records, versions, and workflow states.
- Better production path than SQLite.
- Can work with pgvector if that candidate is chosen later.

Cons:

- Requires a database service.
- Slightly more setup complexity than SQLite.

Phase-one recommendation:

- Recommended as the stronger default candidate for MVP if setup time is acceptable.

Why:

- DataHub needs traceability, review history, state transitions, and future growth.
- PostgreSQL gives a cleaner path from MVP to real use.

## 4. Vector Store Candidates

### 4.1 pgvector

Pros:

- Keeps relational data and vector search close in PostgreSQL.
- Reduces the number of services.
- Good enough for early RAG validation and smaller knowledge bases.
- Simplifies deployment if PostgreSQL is already selected.

Cons:

- Less specialized than a dedicated vector database.
- Advanced vector operations and scaling may be more limited than Qdrant.

Phase-one recommendation:

- Recommended candidate if PostgreSQL is selected.

Why:

- Phase one needs a controlled retrieval loop, not a high-scale vector platform.
- Simpler infrastructure is preferable.

### 4.2 Qdrant

Pros:

- Dedicated vector database.
- Strong vector search features.
- Better fit if retrieval scale or filtering complexity grows.

Cons:

- Adds another service.
- Adds operational complexity.
- Premature if phase-one data volume is small.

Phase-one recommendation:

- Keep as a later candidate.

Why:

- Qdrant may be useful after the retrieval workload grows.
- It should not be introduced before the basic text loop is validated unless pgvector proves insufficient.

## 5. ORM Candidates

### 5.1 SQLAlchemy

Pros:

- Mature Python ORM.
- Flexible and widely used.
- Strong ecosystem and migration tooling compatibility.

Cons:

- Can be verbose.
- Requires discipline around schema and model organization.

Phase-one recommendation:

- Recommended candidate.

Why:

- It is reliable for a workflow-heavy backend with traceability and versioning.

### 5.2 SQLModel

Pros:

- Built on SQLAlchemy and Pydantic.
- Concise for FastAPI projects.
- Good developer ergonomics for simple models.

Cons:

- Less mature than plain SQLAlchemy for complex cases.
- May become limiting if the schema grows complex.

Phase-one recommendation:

- Reasonable candidate for a small MVP.

Why:

- It can speed up early development, but the team should reassess before adding complex workflows.

## 6. RAG Orchestration Candidates

### 6.1 Lightweight Handwritten Service

Pros:

- Minimal dependency surface.
- Easier to understand and test.
- Keeps business rules explicit.
- Avoids premature framework coupling.

Cons:

- Requires implementing retrieval flow, prompt boundaries, and result formatting manually.
- May need refactoring if workflows become more complex.

Phase-one recommendation:

- Recommended starting point.

Why:

- DataHub phase one needs strict governance more than complex agent orchestration.
- A simple service can enforce "approved only" retrieval clearly.

### 6.2 LangChain

Pros:

- Broad ecosystem for LLM and RAG workflows.
- Useful abstractions for retrievers, chains, and integrations.

Cons:

- Adds framework complexity.
- Can hide important control flow if used too early.

Phase-one recommendation:

- Candidate, not default.

Why:

- Consider only when handwritten service becomes repetitive or integration needs justify it.

### 6.3 LlamaIndex

Pros:

- Strong focus on data indexing and retrieval.
- Useful for document ingestion and retrieval abstractions.

Cons:

- Adds framework dependency and learning cost.
- May be unnecessary for a narrow first-phase text loop.

Phase-one recommendation:

- Candidate, not default.

Why:

- Useful later if indexing workflows become more complex.

## 7. Background Task Candidates

### 7.1 FastAPI BackgroundTasks

Pros:

- Simple.
- No separate worker service.
- Good for early local jobs.

Cons:

- Not ideal for long-running or reliable production jobs.
- Limited retry and monitoring behavior.

Phase-one recommendation:

- Recommended for very early MVP tasks.

Why:

- Cleaning and extraction can start simple while job volume is low.

### 7.2 Celery

Pros:

- Mature distributed task queue.
- Supports retries, scheduling, and worker scaling.

Cons:

- Requires broker setup.
- Adds infrastructure complexity.

Phase-one recommendation:

- Keep as later candidate.

Why:

- Introduce only when job reliability, retries, or workload size require it.

### 7.3 RQ

Pros:

- Simpler than Celery.
- Works well with Redis.
- Good for straightforward background jobs.

Cons:

- Still requires Redis.
- Less feature-rich than Celery.

Phase-one recommendation:

- Candidate if BackgroundTasks becomes insufficient but Celery feels too heavy.

Why:

- It can be a middle path for queue-based processing.

## 8. Deployment Candidates

### 8.1 Local Docker Compose

Pros:

- Good for reproducible local development.
- Can run frontend, backend, database, and vector store candidates together.
- Useful before cloud deployment.

Cons:

- Requires Docker.
- Adds config files and service orchestration.

Phase-one recommendation:

- Recommended after basic project initialization.

Why:

- It keeps local environments consistent without choosing a cloud platform too early.

### 8.2 Later Cloud Deployment

Pros:

- Required for team usage or real integrations.
- Can support stable CustomerOpsAgent access.

Cons:

- Premature before the MVP loop works.
- Requires decisions about hosting, secrets, database, storage, and network boundaries.

Phase-one recommendation:

- Not recommended before MVP validation.

Why:

- First prove the local CustomerOpsAgent loop.

## 9. Current Recommendation Summary

Confirmed:

- Frontend: React + TypeScript.
- Backend: FastAPI + Python.

Strong phase-one candidates:

- Frontend build: Vite.
- Database: PostgreSQL, with SQLite allowed for earliest prototype speed.
- Vector store: pgvector if PostgreSQL is selected.
- ORM: SQLAlchemy or SQLModel after schema complexity is clearer.
- RAG orchestration: lightweight handwritten service first.
- Background tasks: FastAPI BackgroundTasks first.
- Deployment: local Docker Compose after initialization.

Do not finalize all choices until M1 project initialization planning.
