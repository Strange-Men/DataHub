"""Secret-safe Bearer header helpers shared by local acceptance clients."""

from __future__ import annotations

import os
import re


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")


def load_bearer_token(env_name: str | None) -> str | None:
    if env_name is None:
        return None
    normalized = env_name.strip()
    if not _ENV_NAME.fullmatch(normalized):
        raise ValueError("auth token environment variable name is invalid")
    token = os.getenv(normalized, "").strip()
    if not token:
        raise ValueError(f"auth token environment variable {normalized} is empty")
    return token


def bearer_headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}
