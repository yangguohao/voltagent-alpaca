"""LLM response cache."""

import hashlib
import json
import time
from typing import Any


class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def _key(self, model: str, messages: list[dict], schema_name: str) -> str:
        payload = json.dumps({"model": model, "messages": messages, "schema": schema_name}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, model: str, messages: list[dict], schema_name: str) -> Any | None:
        key = self._key(model, messages, schema_name)
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, model: str, messages: list[dict], schema_name: str, value: Any) -> None:
        key = self._key(model, messages, schema_name)
        self._store[key] = (time.time(), value)
