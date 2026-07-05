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


def check_provider(verify: bool = False) -> dict:
    provider = os.getenv("EMBEDDING_PROVIDER", "mock").strip().lower()
    model = os.getenv("EMBEDDING_MODEL", "").strip()
    api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
    dim_str = os.getenv("EMBEDDING_DIMENSION", "").strip()

    dimension = 1536
    if dim_str:
        try:
            dimension = int(dim_str)
        except ValueError:
            pass

    print("Embedding Provider Check")
    print("=" * 40)
    print(f"  EMBEDDING_PROVIDER:  {provider}")
    if model:
        print(f"  EMBEDDING_MODEL:     {model}")
    else:
        print(f"  EMBEDDING_MODEL:     (default: mock-deterministic)")
    print(f"  EMBEDDING_DIMENSION: {dimension}")
    print(f"  API key:             {'present' if api_key else 'missing'}  (value NOT shown)")
    if base_url:
        # Show only the hostname, not the full URL
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            print(f"  EMBEDDING_BASE_URL:  {parsed.scheme}://{parsed.hostname} (host only, path hidden)")
        except Exception:
            print(f"  EMBEDDING_BASE_URL:  (set, hostname hidden)")
    print()

    if provider == "mock":
        print("mock_ready: true")
        print("provider_ready: true  (mock — deterministic, keyword-aware, no external API)")
        print()
        print("NOTE: mock embedding captures lexical overlap only.")
        print("Real semantic retrieval (synonyms, paraphrases) requires a real provider.")
        print("Set EMBEDDING_PROVIDER=openai and EMBEDDING_API_KEY=<key> for real embeddings.")
        if verify:
            from app.embedding import get_embedding_provider
            ep = get_embedding_provider()
            vec = ep.embed("test embedding readiness check")
            print()
            print(f"test_embed: ok  dim={len(vec)}  first_5={[round(v, 6) for v in vec[:5]]}")
        return {"mock_ready": True, "provider_ready": True, "provider": "mock"}

    if provider in ("openai", "openai_compatible"):
        if not api_key:
            print("mock_ready: true")
            print("provider_ready: false  (API key missing)")
            print()
            print("Set EMBEDDING_API_KEY or OPENAI_API_KEY to enable real embeddings.")
            print("Key is NEVER printed in logs or output.")
            return {"mock_ready": True, "provider_ready": False,
                    "reason": "api_key_missing", "provider": provider}

        print(f"API key: present (NOT shown)")
        print()

        if verify:
            try:
                from app.embedding import get_embedding_provider
                ep = get_embedding_provider(provider=provider, model=model or None,
                                            api_key=api_key, dimension=dimension)
                vec = ep.embed("test embedding readiness check")
                print(f"test_embed: ok")
                print(f"  dimension:  {len(vec)}")
                print(f"  first_5:    {[round(v, 6) for v in vec[:5]]}")
                print(f"  model:      {ep.model_name}")
                print()
                print("provider_ready: true")
                return {"mock_ready": True, "provider_ready": True,
                        "provider": provider, "dimension": len(vec)}
            except Exception as exc:
                msg = str(exc)[:300]
                # Scrub any potential key leak
                if api_key and api_key in msg:
                    msg = msg.replace(api_key, "[REDACTED]")
                print(f"test_embed: FAILED")
                print(f"  error: {msg}")
                print()
                print("provider_ready: false")
                print()
                print("Check EMBEDDING_API_KEY and network connectivity.")
                return {"mock_ready": True, "provider_ready": False,
                        "reason": "embed_failed", "error": msg, "provider": provider}

        print("provider_ready: unknown  (use --verify to test a real embed call)")
        return {"mock_ready": True, "provider_ready": "unknown",
                "provider": provider}

    print(f"Unknown provider: '{provider}'")
    print("mock_ready: true  (fallback)")
    return {"mock_ready": True, "provider_ready": False,
            "reason": f"unknown_provider:{provider}"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check embedding provider readiness."
    )
    parser.add_argument("--verify", action="store_true",
                        help="Perform a test embed call to verify the provider")
    args = parser.parse_args()
    result = check_provider(verify=args.verify)
    sys.exit(0 if result.get("provider_ready") in (True, "unknown") else 1)


if __name__ == "__main__":
    main()
