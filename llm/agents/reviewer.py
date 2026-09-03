"""Trade review agent with model cascade and rule-based fallback."""

from pydantic import BaseModel, Field

from config.settings import Settings
from llm.groq_client import GroqClient
from llm.router import LLMTask, ModelRouter
from observability.logger import get_logger

logger = get_logger("reviewer")


class TradeReview(BaseModel):
    approve: bool = True
    reason: str = Field(default="", max_length=120)
    adjustments: str = Field(default="", max_length=120)
    source: str = Field(default="llm", max_length=32)


SYSTEM_PROMPT = (
    'Reply with a json object exactly like: {"approve":true,"reason":"ok","adjustments":""}. '
    "Set approve to false only for obvious risk issues."
)


class ReviewerAgent:
    def __init__(self, groq: GroqClient, router: ModelRouter, settings: Settings) -> None:
        self.groq = groq
        self.router = router
        self.settings = settings

    def _compact_payload(self, trade_summary: dict, risk_context: dict) -> str:
        payload = {
            "s": trade_summary.get("strategy"),
            "sym": trade_summary.get("symbol"),
            "legs": trade_summary.get("legs"),
            "dte": trade_summary.get("dte"),
            "iv": trade_summary.get("iv_rank"),
            "eq": round(float(risk_context.get("equity", 0)), 0),
            "pos": risk_context.get("positions"),
        }
        return str(payload)

    async def review(self, trade_summary: dict, risk_context: dict) -> TradeReview:
        task = LLMTask.TRADE_REVIEW
        primary = self.router.resolve(task)
        fallback = self.settings.groq_model_fast
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._compact_payload(trade_summary, risk_context)},
        ]

        try:
            result = await self.groq.complete(
                primary,
                messages,
                TradeReview,
                task="trade_review",
                max_tokens=self.router.max_tokens(task),
                fallback_model=fallback,
                max_retries=2,
            )
            result.source = f"llm:{primary.split('/')[-1]}"
            return result
        except Exception as exc:
            logger.error("Trade review LLM failed: %s", exc)
            if self.settings.llm_review_fallback_approve:
                return TradeReview(
                    approve=True,
                    reason="risk_gates_passed",
                    adjustments="",
                    source="fallback:auto_approve",
                )
            return TradeReview(
                approve=False,
                reason="llm_unavailable",
                adjustments="",
                source="fallback:reject",
            )
