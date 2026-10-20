"""Route LLM tasks to the appropriate Groq model."""

from enum import Enum

from ai_agent.config.settings import Settings


class LLMTask(str, Enum):
    REGIME_DETECTION = "regime_detection"
    STRATEGY_SELECTION = "strategy_selection"
    INTRADAY_REVIEW = "intraday_review"
    TRADE_REVIEW = "trade_review"


class ModelRouter:
    SMART_TASKS = {LLMTask.REGIME_DETECTION, LLMTask.TRADE_REVIEW}
    MAX_TOKENS = {
        LLMTask.REGIME_DETECTION: 256,
        LLMTask.STRATEGY_SELECTION: 256,
        LLMTask.INTRADAY_REVIEW: 256,
        LLMTask.TRADE_REVIEW: 1024,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve(self, task: LLMTask) -> str:
        if task in self.SMART_TASKS:
            return self.settings.groq_model_smart
        return self.settings.groq_model_fast

    def max_tokens(self, task: LLMTask) -> int:
        return self.MAX_TOKENS.get(task, self.settings.gpt_oss_max_tokens)
