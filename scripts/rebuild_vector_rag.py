#!/usr/bin/env python3
"""Rebuild vector RAG embeddings from approved knowledge candidates.

Usage:
  python scripts/rebuild_vector_rag.py
  python scripts/rebuild_vector_rag.py --base-url https://datahub-jr8x.onrender.com --verbose
  python scripts/rebuild_vector_rag.py --base-url http://127.0.0.1:8000 --verbose

This script:
1. Checks embedding provider readiness (via local check or API health).
2. Verifies dimension compatibility with pgvector table.
3. Triggers RAG build via POST /api/rag/build to sync approved candidates → rag_embeddings.
4. Validates the rebuild result.

If the embedding provider is not ready or dimension mismatch, rebuild is BLOCKED.

Never prints API keys or connection strings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


PGVECTOR_TABLE_DIMENSION = 1536


def _safe_url_display(url: str) -> str:
    """Show only scheme + hostname, never full path."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}"
        return "(hidden)"
    except Exception:
        return "(hidden)"


def _api_get(base_url: str, path: str, verbose: bool = False) -> dict[str, Any] | None:
    """GET request with error handling."""
    url = f"{base_url.rstrip('/')}{path}"
    if verbose:
        print(f"  GET {_safe_url_display(url)}{path}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"  HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  Request failed: {str(e)[:200]!r}")
        return None


def _api_post(base_url: str, path: str, body: dict | None = None,
              verbose: bool = False) -> dict[str, Any] | None:
    """POST request with error handling."""
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body or {}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if verbose:
        print(f"  POST {_safe_url_display(url)}{path}")
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"  HTTP {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  Request failed: {str(e)[:200]!r}")
        return None


def check_provider_locally(verbose: bool = False) -> dict[str, Any]:
    """Run local embedding provider check (no --base-url)."""
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    dim_str = os.getenv("EMBEDDING_DIMENSION", "").strip()

    expected_dim = PGVECTOR_TABLE_DIMENSION
    if dim_str:
        try:
            expected_dim = int(dim_str)
        except ValueError:
            pass

    print(f"Local Embedding Provider Check")
    print(f"  provider:  {provider}")
    print(f"  api_key:   {'present' if api_key else 'missing'}")
    print(f"  dimension: {expected_dim}")
    print()

    if provider == "mock":
        print("mock_ready: true")
        print("provider_ready: true (mock only)")
        print("real_embedding_provider: false")
        print()
        return {"mock_ready": True, "provider_ready": True,
                "real_embedding_provider": False, "provider": "mock"}

    if provider in ("openai", "openai_compatible", "siliconflow", "jina"):
        if not api_key:
            print("BLOCKED: missing_api_key")
            print("Set EMBEDDING_API_KEY to enable real embeddings.")
            return {"mock_ready": True, "provider_ready": False,
                    "real_embedding_provider": False,
                    "reason": "missing_api_key", "provider": provider}

        # Try a test embed to verify
        try:
            from app.embedding import get_embedding_provider
            ep = get_embedding_provider(provider=provider, api_key=api_key)
            vec = ep.embed("test embedding readiness check")
            actual_dim = len(vec)

            if actual_dim != PGVECTOR_TABLE_DIMENSION:
                print("=" * 40)
                print("BLOCKED_DIMENSION_MISMATCH")
                print("=" * 40)
                print(f"  real_dim:  {actual_dim}")
                print(f"  expected:  {PGVECTOR_TABLE_DIMENSION}")
                print()
                print("Solutions:")
                print(f"  A. Switch to a {PGVECTOR_TABLE_DIMENSION}-dim model")
                print(f"  B. ALTER TABLE rag_embeddings for vector({actual_dim})")
                print(f"  C. Create separate table rag_embeddings_{actual_dim}dim")
                print()
                return {"mock_ready": True, "provider_ready": False,
                        "real_embedding_provider": False,
                        "reason": "dimension_mismatch",
                        "blocked": "BLOCKED_DIMENSION_MISMATCH",
                        "actual_dimension": actual_dim,
                        "expected_dimension": PGVECTOR_TABLE_DIMENSION,
                        "provider": provider}

            print(f"real_embedding_provider: true")
            print(f"dimension: {actual_dim} (matches table)")
            print(f"provider_ready: true")
            print()
            return {"mock_ready": True, "provider_ready": True,
                    "real_embedding_provider": True,
                    "dimension": actual_dim, "dimension_match": True,
                    "provider": provider}

        except Exception as exc:
            msg = str(exc)[:300]
            if api_key and api_key in msg:
                msg = msg.replace(api_key, "[REDACTED]")
            print(f"BLOCKED: embed_failed — {msg}")
            return {"mock_ready": True, "provider_ready": False,
                    "real_embedding_provider": False,
                    "reason": "embed_failed", "error": msg,
                    "provider": provider}

    print(f"Unknown provider: {provider}")
    return {"mock_ready": True, "provider_ready": False,
            "reason": f"unknown_provider:{provider}"}


def check_provider_via_api(base_url: str, verbose: bool = False) -> dict[str, Any]:
    """Check embedding provider readiness via remote API health."""
    health = _api_get(base_url, "/api/health", verbose=verbose)
    if not health:
        print("Failed to reach /api/health")
        return {"provider_ready": False, "reason": "api_unreachable"}

    # Also try check_embedding endpoint if available, or infer from health
    print(f"Health check: status={health.get('status')}, phase={health.get('phase')}")
    pgv = health.get("pgvector_status", {})
    print(f"pgvector: available={pgv.get('pgvector_available')}, backend={pgv.get('backend')}")

    # We need to trigger rebuild via POST /api/rag/build
    # But first, let's check the current state by listing candidates
    return {"provider_ready": "unknown", "note": "check via API rebuild result"}


def trigger_rag_rebuild(base_url: str, verbose: bool = False) -> dict[str, Any] | None:
    """Trigger RAG build via POST /api/rag/build and parse the result."""
    print()
    print("Triggering RAG rebuild via POST /api/rag/build ...")
    result = _api_post(base_url, "/api/rag/build", verbose=verbose)
    return result


def run_rebuild(base_url: str | None = None, verbose: bool = False,
                force: bool = False) -> dict[str, Any]:
    """Main rebuild logic."""
    print("=" * 60)
    print("DataHub Vector RAG Rebuild")
    print("=" * 60)
    print()

    # Step 1: Check embedding provider readiness
    print("--- Step 1: Embedding Provider Check ---")
    if base_url:
        # Remote mode: check via API
        _ = check_provider_via_api(base_url, verbose=verbose)
        # For remote mode, we rely on the API server's own embedding config
        print("(Remote mode — API server uses its own embedding configuration)")
        provider_result = {"provider_ready": True, "remote": True}
    else:
        # Local mode: check directly
        provider_result = check_provider_locally(verbose=verbose)

    if not provider_result.get("provider_ready"):
        blocked_reason = provider_result.get("reason", "unknown")
        print()
        print("=" * 40)
        print("REBUILD BLOCKED")
        print("=" * 40)
        print(f"  reason: {blocked_reason}")
        if provider_result.get("blocked"):
            print(f"  status: {provider_result['blocked']}")
        print()
        print("Vector rebuild cannot proceed. Resolve the issue above and retry.")
        if not force:
            return {"rebuild_status": "BLOCKED",
                    "blocked_reason": blocked_reason,
                    **provider_result}
        print("--force specified, proceeding anyway...")

    # Step 2: Trigger RAG rebuild
    print()
    print("--- Step 2: RAG Rebuild ---")

    if base_url:
        result = trigger_rag_rebuild(base_url, verbose=verbose)
        if not result:
            print("ERROR: RAG rebuild API call failed.")
            return {"rebuild_status": "FAILED", "error": "api_call_failed"}

        # Parse the API response
        data = result.get("data", result)
        embedding_count = data.get("embedding_count", 0)
        failed_embedding_count = data.get("failed_embedding_count", 0)
        vector_sync_enabled = data.get("vector_sync_enabled", False)
        embedding_provider = data.get("embedding_provider", "unknown")
        embedding_model = data.get("embedding_model", "unknown")
        embedding_dimension = data.get("embedding_dimension", 0)
        approved_candidate_count = data.get("approved_candidate_count", 0)
        vector_sync_error = data.get("vector_sync_error")
        chunk_count = data.get("chunk_count", 0)

        print()
        print("--- Rebuild Result ---")
        print(f"  approved_candidate_count: {approved_candidate_count}")
        print(f"  chunk_count:              {chunk_count}")
        print(f"  embedding_count:          {embedding_count}")
        print(f"  failed_embedding_count:   {failed_embedding_count}")
        print(f"  vector_sync_enabled:      {vector_sync_enabled}")
        print(f"  embedding_provider:       {embedding_provider}")
        print(f"  embedding_model:          {embedding_model}")
        print(f"  embedding_dimension:      {embedding_dimension}")
        if vector_sync_error:
            print(f"  vector_sync_error:        {vector_sync_error}")

        return {
            "rebuild_status": "SUCCESS" if embedding_count > 0 else "FAILED",
            "approved_candidate_count": approved_candidate_count,
            "embedding_count": embedding_count,
            "failed_embedding_count": failed_embedding_count,
            "provider": embedding_provider,
            "model": embedding_model,
            "dimension": embedding_dimension,
            "vector_sync_enabled": vector_sync_enabled,
            "vector_sync_error": vector_sync_error,
        }
    else:
        # Local mode: import and call directly
        print("Local rebuild mode — using storage.build_rag_chunks() directly.")
        try:
            # Add backend to path
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
            from app.storage import build_rag_chunks

            result = build_rag_chunks()
            print()
            print("--- Rebuild Result ---")
            print(f"  approved_candidate_count: {result.approved_candidate_count}")
            print(f"  chunk_count:              {result.chunk_count}")
            print(f"  embedding_count:          {result.embedding_count}")
            print(f"  failed_embedding_count:   {result.failed_embedding_count}")
            print(f"  vector_sync_enabled:      {result.vector_sync_enabled}")
            print(f"  embedding_provider:       {result.embedding_provider}")
            print(f"  embedding_model:          {result.embedding_model}")
            print(f"  embedding_dimension:      {result.embedding_dimension}")
            if result.vector_sync_error:
                print(f"  vector_sync_error:        {result.vector_sync_error}")

            return {
                "rebuild_status": "SUCCESS" if result.embedding_count > 0 else "FAILED",
                "approved_candidate_count": result.approved_candidate_count,
                "embedding_count": result.embedding_count,
                "failed_embedding_count": result.failed_embedding_count,
                "provider": result.embedding_provider,
                "model": result.embedding_model,
                "dimension": result.embedding_dimension,
                "vector_sync_enabled": result.vector_sync_enabled,
                "vector_sync_error": result.vector_sync_error,
            }
        except Exception as exc:
            print(f"Local rebuild failed: {exc}")
            return {"rebuild_status": "FAILED", "error": str(exc)[:300]}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild vector RAG embeddings from approved knowledge candidates."
    )
    parser.add_argument("--base-url", type=str, default=None,
                        help="Base URL of the DataHub API (e.g. https://datahub-jr8x.onrender.com)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed request/response info")
    parser.add_argument("--force", action="store_true",
                        help="Proceed with rebuild even if provider check is not ready")
    args = parser.parse_args()

    result = run_rebuild(base_url=args.base_url, verbose=args.verbose, force=args.force)

    print()
    print("=" * 40)
    print(f"Rebuild status: {result.get('rebuild_status', 'UNKNOWN')}")
    if result.get("rebuild_status") == "BLOCKED":
        print(f"Blocked reason: {result.get('blocked_reason', 'see above')}")
    print("=" * 40)

    if result.get("rebuild_status") == "SUCCESS":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
