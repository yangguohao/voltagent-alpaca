"""Strategy selection agent."""

from pydantic import BaseModel, Field

from ai_agent.llm.groq_client import GroqClient
from ai_agent.llm.router import LLMTask, ModelRouter


class StrategySelection(BaseModel):
    strategy: str = Field(description="iron_condor, straddle, strangle, or hold")
    rationale: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)


SYSTEM_PROMPT = """You are an options strategy selector for volatility trades.
If the symbol is already in held_symbols, reply with strategy "hold".
Reply with json only: {"strategy": "iron_condor|straddle|strangle|hold", "rationale": "...", "confidence": 0.0-1.0}"""


class SelectorAgent:
    def __init__(self, groq: GroqClient, router: ModelRouter) -> None:
        self.groq = groq
        self.router = router

    async def select(
        self,
        signal_summary: dict,
        candidates: list[str],
        held_symbols: list[str] | None = None,
    ) -> StrategySelection:
        model = self.router.resolve(LLMTask.STRATEGY_SELECTION)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Signal: {signal_summary}\n"
                    f"Candidates: {candidates}\n"
                    f"Held symbols: {held_symbols or []}"
                ),
            },
        ]
        return await self.groq.complete(
            model, messages, StrategySelection,
            task="strategy_selection",
            max_tokens=self.router.max_tokens(LLMTask.STRATEGY_SELECTION),
            fallback_model=None,
            max_retries=2,
        )
