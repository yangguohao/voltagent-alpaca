# VoltAgent workspace

代码已按职责拆分为四个目录：

- [`alpaca_infra/`](alpaca_infra/)：共享的 Alpaca 客户端、行情、期权、订单和持仓基础设施。
- [`tradier_infra/`](tradier_infra/)：可选的 Tradier 实时正股与期权行情基础设施；交易仍由 Alpaca 执行。
- [`ai_agent/`](ai_agent/)：AI Agent 波动率交易系统，包括 LLM、信号、风险控制与调度。
- [`soxl_strategy/`](soxl_strategy/)：依据 `soxl.md` 实现的 SOXL 趋势过滤与 Covered Call 方案。

四个目录都是独立的 Python 包；两个交易应用共同依赖 `alpaca_infra`。AI Agent 仅在
`SOXL_STRATEGY_ENABLED=true` 时调用 SOXL 模块。

安装与运行说明见 [`ai_agent/README.md`](ai_agent/README.md)，SOXL 规则说明见
[`soxl_strategy/README.md`](soxl_strategy/README.md)。
