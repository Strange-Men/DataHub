"""Shared, backward-compatible run-scope helpers for maintenance Eval runners.

Run scope is an evaluation concern. It never changes production ranking and it
never authorizes broad database deletion. A runtime manifest is trusted for
cleanup only when it explicitly identifies itself as a DataHub test corpus.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


RUN_SCOPE_VERSION = "p1-p2-m9.1-run-scope-v1"
RUN_NAMESPACE_PREFIX = "datahub-eval:"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,95}$")


def normalize_run_id(value: object) -> str:
    run_id = str(value or "").strip()
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id must contain 6-96 letters, digits, dots, underscores or hyphens"
        )
    return run_id


def make_run_scope(run_id: str, *, trace_id: str, creator: str) -> dict[str, object]:
    normalized = normalize_run_id(run_id)
    return {
        "version": RUN_SCOPE_VERSION,
        "run_id": normalized,
        "namespace": f"{RUN_NAMESPACE_PREFIX}{normalized}",
        "trace_id": str(trace_id),
        "creator": str(creator),
        "test_corpus": True,
    }


def load_run_scope(payload: object) -> dict[str, object] | None:
    """Return a validated scope or None for a legacy manifest."""
    if not isinstance(payload, dict) or "run_scope" not in payload:
        return None
    raw = payload.get("run_scope")
    if not isinstance(raw, dict):
        raise ValueError("run_scope must be an object")
    run_id = normalize_run_id(raw.get("run_id"))
    namespace = str(raw.get("namespace", "")).strip()
    if namespace != f"{RUN_NAMESPACE_PREFIX}{run_id}":
        raise ValueError("run_scope namespace does not match run_id")
    if raw.get("test_corpus") is not True:
        raise ValueError("run_scope must explicitly mark test_corpus=true")
    if str(raw.get("version", "")) != RUN_SCOPE_VERSION:
        raise ValueError("unsupported run_scope version")
    creator = str(raw.get("creator", "")).strip()
    trace_id = str(raw.get("trace_id", "")).strip()
    if not creator or not trace_id:
        raise ValueError("run_scope requires creator and trace_id")
    return {
        "version": RUN_SCOPE_VERSION,
        "run_id": run_id,
        "namespace": namespace,
        "trace_id": trace_id,
        "creator": creator,
        "test_corpus": True,
    }


def collect_p2_scope_ids(entries: Iterable[object]) -> set[str]:
    fields = (
        "expected_knowledge_asset_ids",
        "expected_asset_ids",
        "expected_chunk_ids",
        "forbidden_knowledge_asset_ids",
        "forbidden_asset_ids",
        "forbidden_chunk_ids",
        "expected_p2_knowledge_asset_ids",
        "expected_p2_asset_ids",
        "expected_p2_chunk_ids",
        "forbidden_p2_knowledge_asset_ids",
        "forbidden_p2_asset_ids",
        "forbidden_p2_chunk_ids",
    )
    identifiers: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for field in fields:
            values = entry.get(field, [])
            if isinstance(values, list):
                identifiers.update(
                    str(value).strip() for value in values if str(value).strip()
                )
    return identifiers


def result_is_p2(result: dict[str, Any]) -> bool:
    source = str(result.get("source_index") or result.get("source_type") or "").lower()
    return "p2" in source or bool(result.get("knowledge_asset_id"))


def result_in_p2_scope(result: dict[str, Any], scope_ids: set[str]) -> bool:
    if not scope_ids:
        return True
    return any(
        str(result.get(field, "")).strip() in scope_ids
        for field in ("knowledge_asset_id", "asset_id", "chunk_id")
    )


def filter_p2_results(
    results: Iterable[dict[str, Any]],
    scope_ids: set[str],
    *,
    keep_non_p2: bool,
) -> list[dict[str, Any]]:
    """Preserve result order while excluding P2 rows from older Eval runs."""
    filtered: list[dict[str, Any]] = []
    for result in results:
        if result_is_p2(result):
            if result_in_p2_scope(result, scope_ids):
                filtered.append(result)
        elif keep_non_p2:
            filtered.append(result)
    return filtered
