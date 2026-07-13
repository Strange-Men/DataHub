#!/usr/bin/env python3
"""Check embedding provider readiness.

Usage:
  python scripts/check_embedding_provider.py
  python scripts/check_embedding_provider.py --verify

Reports:
  - provider name, model name, dimension
  - mock_ready: true/false
  - API key status (present/missing, never prints the key)
  - provider_ready: true/false
  - If real provider: actual embedding dimension vs expected table dimension
  - BLOCKED_DIMENSION_MISMATCH if dimensions don't match

With --verify:
  - Performs a test embed of a short text
  - Reports embedding dimension, first 5 values
  - Reports success/failure with safe error messages

Never prints API keys, DATABASE_URL, or full embedding vectors.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _load_local_env_if_unconfigured() -> None:
    """Load the project .env only when no embedding config is already set.

    Render and explicit shell environment variables always win because
    load_dotenv is called with override=False. The file contents are never
    printed.
    """
    if os.getenv("EMBEDDING_PROVIDER") or os.getenv("EMBEDDING_API_KEY"):
        return
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=env_path, override=False)


_load_local_env_if_unconfigured()

# Current pgvector table constraint on Render PostgreSQL
PGVECTOR_TABLE_DIMENSION = 1536


def _safe_url_display(base_url: str) -> str:
    """Show only scheme + hostname, never the full path or query string."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.hostname:
            return f"{parsed.scheme}://{parsed.hostname}"
        return "(set, host hidden)"
    except Exception:
        return "(set, host hidden)"


def _scrub_key(msg: str, api_key: str) -> str:
    """Remove API key from an error message if present."""
    if api_key and api_key in msg:
        return msg.replace(api_key, "[REDACTED]")
    return msg


def check_provider(verify: bool = False) -> dict:
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    model = os.getenv("EMBEDDING_MODEL", "").strip()
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    dim_str = os.getenv("EMBEDDING_DIMENSION", "").strip()
    timeout_str = os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30").strip()
    max_retries_str = os.getenv("EMBEDDING_MAX_RETRIES", "3").strip()

    expected_dimension = PGVECTOR_TABLE_DIMENSION
    if dim_str:
        try:
            expected_dimension = int(dim_str)
        except ValueError:
            pass

    print("Embedding Provider Check")
    print("=" * 40)
    print(f"  EMBEDDING_PROVIDER:       {provider}")
    if model:
        print(f"  EMBEDDING_MODEL:          {model}")
    else:
        print(f"  EMBEDDING_MODEL:          (default)")
    print(f"  EMBEDDING_DIMENSION:      {expected_dimension}")
    print(f"  API key:                  {'present' if api_key else 'missing'}  (value NOT shown)")
    if base_url:
        print(f"  EMBEDDING_BASE_URL:       {_safe_url_display(base_url)} (host only)")
    print(f"  EMBEDDING_TIMEOUT_SECONDS:{timeout_str}")
    print(f"  EMBEDDING_MAX_RETRIES:    {max_retries_str}")
    print(f"  pgvector table dimension: {PGVECTOR_TABLE_DIMENSION}")
    print()

    # --- mock provider ---
    if provider == "mock":
        print("mock_ready:              true")
        print("provider_ready:          true  (mock — deterministic, keyword-aware)")
        print("real_embedding_provider: false")
        print()
        print("NOTE: mock embedding captures lexical overlap only.")
        print("Real semantic retrieval (synonyms, paraphrases) requires a real provider.")
        print("Set EMBEDDING_PROVIDER=openai|siliconflow|jina and EMBEDDING_API_KEY=<key>.")
        if verify:
            from app.embedding import get_embedding_provider
            ep = get_embedding_provider()
            vec = ep.embed("test embedding readiness check")
            print()
            print(f"test_embed: ok  dim={len(vec)}  first_5={[round(v, 6) for v in vec[:5]]}")
        return {"mock_ready": True, "provider_ready": True, "real_embedding_provider": False,
                "provider": "mock", "dimension": expected_dimension}

    # --- real providers (openai, openai_compatible, siliconflow, jina) ---
    if provider in ("openai", "openai_compatible", "siliconflow", "jina"):
        if not api_key:
            print("mock_ready:              true")
            print("provider_ready:          false")
            print("reason:                  missing_api_key")
            print("real_embedding_provider: false")
            print()
            print("Set EMBEDDING_API_KEY to enable real embeddings.")
            print("Key is NEVER printed in logs or output.")
            return {"mock_ready": True, "provider_ready": False,
                    "real_embedding_provider": False,
                    "reason": "missing_api_key", "provider": provider}

        print(f"API key: present (NOT shown)")
        print()

        if verify:
            try:
                from app.embedding import get_embedding_provider
                ep = get_embedding_provider(provider=provider, model=model or None,
                                            api_key=api_key, dimension=expected_dimension)
                vec = ep.embed("test embedding readiness check")
                actual_dim = len(vec)
                print(f"test_embed: ok")
                print(f"  actual_dimension:  {actual_dim}")
                print(f"  expected_dimension: {expected_dimension}")
                print(f"  first_5:           {[round(v, 6) for v in vec[:5]]}")
                print(f"  model:             {ep.model_name}")
                print()

                # Dimension mismatch check
                if actual_dim != PGVECTOR_TABLE_DIMENSION:
                    print("=" * 40)
                    print("BLOCKED_DIMENSION_MISMATCH")
                    print("=" * 40)
                    print(f"  Real embedding dimension: {actual_dim}")
                    print(f"  pgvector table expects:   {PGVECTOR_TABLE_DIMENSION}")
                    print()
                    print("The real embedding provider returns {}-dim vectors, but the".format(actual_dim))
                    print("rag_embeddings table uses pgvector Vector({}).".format(PGVECTOR_TABLE_DIMENSION))
                    print()
                    print("Solutions:")
                    print("  A. Switch to a {}-dim embedding model.".format(PGVECTOR_TABLE_DIMENSION))
                    print("     e.g. EMBEDDING_MODEL=text-embedding-3-small (OpenAI, 1536 dim)")
                    print("  B. ALTER TABLE rag_embeddings to use vector({})".format(actual_dim))
                    print("     ALTER TABLE rag_embeddings ALTER COLUMN embedding TYPE vector({});".format(actual_dim))
                    print("  C. Create a separate table for this provider dimension.")
                    print("     e.g. rag_embeddings_{}dim".format(actual_dim))
                    print()
                    print("Vector rebuild is BLOCKED until this is resolved.")
                    return {"mock_ready": True, "provider_ready": False,
                            "real_embedding_provider": False,
                            "reason": "dimension_mismatch",
                            "blocked": "BLOCKED_DIMENSION_MISMATCH",
                            "actual_dimension": actual_dim,
                            "expected_dimension": PGVECTOR_TABLE_DIMENSION,
                            "provider": provider}

                # Dimension matches
                print(f"dimension_match: true  ({actual_dim} == {PGVECTOR_TABLE_DIMENSION})")
                print("Vector rebuild is ALLOWED.")
                print()
                print("provider_ready:          true")
                print("real_embedding_provider: true")
                return {"mock_ready": True, "provider_ready": True,
                        "real_embedding_provider": True,
                        "provider": provider, "model": model or ep.model_name,
                        "dimension": actual_dim, "dimension_match": True}

            except Exception as exc:
                msg = _scrub_key(str(exc)[:300], api_key)
                # Also scrub DATABASE_URL if present
                db_url = os.getenv("DATABASE_URL", "")
                if db_url and db_url in msg:
                    msg = msg.replace(db_url, "[REDACTED]")
                print(f"test_embed: FAILED")
                print(f"  error: {msg}")
                print()
                print("provider_ready:          false")
                print("real_embedding_provider: false")
                print()
                print("Check EMBEDDING_API_KEY and network connectivity.")
                return {"mock_ready": True, "provider_ready": False,
                        "real_embedding_provider": False,
                        "reason": "embed_failed", "error": msg, "provider": provider}

        # No --verify: provider_ready = unknown without actual test
        print("provider_ready:          unknown  (use --verify to test a real embed call)")
        print("real_embedding_provider: unknown")
        return {"mock_ready": True, "provider_ready": "unknown",
                "real_embedding_provider": "unknown",
                "provider": provider}

    # --- unknown provider ---
    print(f"Unknown provider: '{provider}'")
    print("mock_ready:              true  (fallback)")
    print("provider_ready:          false")
    print("real_embedding_provider: false")
    return {"mock_ready": True, "provider_ready": False,
            "real_embedding_provider": False,
            "reason": f"unknown_provider:{provider}"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check embedding provider readiness."
    )
    parser.add_argument("--verify", action="store_true",
                        help="Perform a test embed call to verify the provider")
    args = parser.parse_args()
    result = check_provider(verify=args.verify)

    exit_code = 0
    if result.get("provider_ready") is False:
        exit_code = 1
    elif result.get("provider_ready") == "unknown":
        exit_code = 0  # Not a failure, just unverified
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
