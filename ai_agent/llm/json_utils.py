"""Robust JSON extraction from LLM responses."""

import json
import re
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                cleaned = part
                break

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"No JSON object found in response: {text[:200]!r}")


def parse_model_response(content: str, schema: Type[T]) -> T:
    data = extract_json_object(content)
    return schema.model_validate(data)
