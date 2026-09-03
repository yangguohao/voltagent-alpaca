"""Market regime detection agent."""

from pydantic import BaseModel, Field

from llm.groq_client import GroqClient
from llm.router import LLMTask, ModelRouter


class RegimeResult(BaseModel):
    regime: str = Field(description="low_vol, high_vol, trending, or choppy")
    confidence: float = Field(ge=0, le=1)
    notes: str = ""


SYSTEM_PROMPT = """You are a volatility regime analyst.
Reply with json only: {"regime": "low_vol|high_vol|trending|choppy", "confidence": 0.0-1.0, "notes": "..."}"""


class RegimeAgent:
    def __init__(self, groq: GroqClient, router: ModelRouter) -> None:
        self.groq = groq
        self.router = router

    async def analyze(self, summary: dict) -> RegimeResult:
        model = self.router.resolve(LLMTask.REGIME_DETECTION)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": str(summary)},
        ]
        return await self.groq.complete(
            model, messages, RegimeResult,
            task="regime_detection",
            max_tokens=self.router.max_tokens(LLMTask.REGIME_DETECTION),
        )
