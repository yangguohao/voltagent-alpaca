#!/usr/bin/env python3
"""Minimal Groq hello-world request using the official SDK."""

import os
from pathlib import Path

from groq import APIStatusError, Groq


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
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("Missing GROQ_API_KEY; add it to tmp/.env")

    try:
        result = Groq(api_key=api_key).chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": "Reply with exactly: Hello, world!"}],
            max_tokens=20,
            temperature=0,
        )
    except APIStatusError as exc:
        raise SystemExit(f"Groq request failed ({exc.status_code}): {exc.message}") from exc

    content = result.choices[0].message.content
    if not content:
        raise SystemExit("Groq returned no message content")
    print(content)


if __name__ == "__main__":
    main()
