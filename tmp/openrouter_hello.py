#!/usr/bin/env python3
"""Minimal OpenRouter hello-world request using only the standard library."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_URL = "https://openrouter.ai/api/v1/chat/completions"


def load_local_env() -> None:
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key and not key.startswith("#"):
            os.environ.setdefault(key, value.split(" #", 1)[0].strip().strip("'\""))


def main() -> None:
    load_local_env()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENROUTER_API_KEY; add it to tmp/.env")

    payload = json.dumps({
        # "model": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        # "model": "openrouter/deepseek-r1:free",
        "model": "minimax/minimax-m3.1-flash:free",
        "messages": [{"role": "user", "content": "Reply with exactly: Hello, world!"}],
        "max_tokens": 100,
        "reasoning": {"enabled": True},
    }).encode()
    request = Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "VoltAgent OpenRouter Hello World",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise SystemExit(f"OpenRouter request failed ({exc.code}): {exc.read().decode()}") from exc

    content = result["choices"][0]["message"].get("content")
    if not content:
        raise SystemExit("OpenRouter returned no message content")
    print(content)


if __name__ == "__main__":
    main()
