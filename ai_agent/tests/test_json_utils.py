"""Tests for LLM JSON parsing."""

import pytest

from ai_agent.llm.json_utils import extract_json_object, parse_model_response
from ai_agent.llm.agents.reviewer import TradeReview


def test_extract_plain_json():
    data = extract_json_object('{"approve": true, "reason": "ok"}')
    assert data["approve"] is True


def test_extract_fenced_json():
    text = '```json\n{"approve": false, "reason": "high risk"}\n```'
    data = extract_json_object(text)
    assert data["approve"] is False


def test_parse_trade_review():
    review = parse_model_response('{"approve": true, "reason": "ok", "adjustments": ""}', TradeReview)
    assert review.approve is True


def test_extract_invalid_raises():
    with pytest.raises(ValueError):
        extract_json_object("not json at all")
