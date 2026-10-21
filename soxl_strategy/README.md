# SOXL strategy

本目录只包含 SOXL 趋势过滤与 Covered Call 交易方法：

- [`soxl.md`](soxl.md)：原始交易规则。
- [`strategy.py`](strategy.py)：V27.0 四季状态机（QQQ MA252、SOXX 252 日回撤、
  MA20/60 日成交量）、30 日熔断、SOXX 五日涨幅和合约筛选。
- [`manager.py`](manager.py)：持仓覆盖检查、开仓、T-1 与趋势转坏平仓。
- [`backtest.py`](backtest.py)：使用公开历史日线回测 V27 正股配置，并与 SOXL/SOXX
  买入持有比较；不包含 Covered Call。
- [`covered_call_backtest.py`](covered_call_backtest.py)：使用 Alpaca 2024-02 之后的
  历史期权成交 Bar 回测 Covered Call；需要 Alpaca 凭据。
- [`tests/`](tests/)：SOXL 专项测试。

该方案复用 `alpaca_infra` 的 Alpaca 行情、订单类型和执行器，但不参与 AI/LLM 的策略选择。
启用及运行：

```bash
cp ai_agent/.env.example .env
# 在 .env 中设置 SOXL_STRATEGY_ENABLED=true
SOXL_UNDERLYING_REBALANCE_ENABLED=true  # 仅 Paper：自动执行 V27 正股调仓
PYTHONPATH=. python ai_agent/scripts/run_agent.py --mode once --phase soxl
```

正股历史回测不需要 Alpaca 凭据：

```bash
PYTHONPATH=. python -m soxl_strategy.backtest
```

回测信号在收盘后生成、从下一交易日开始生效，默认按每单位换手收取 5 bps 成本。
Covered Call 的可靠回测仍需历史期权链、Delta 与 Bid/Ask 数据。

Covered Call 成交价近似回测：

```bash
PYTHONPATH=. python -m soxl_strategy.covered_call_backtest
```

Alpaca 没有历史期权 Bid/Ask 端点，因此该工具在信号日收盘确认后使用下一交易日
期权开盘成交价、退出日收盘成交价并反推 Delta，默认在两侧各施加 5% 期权价格
滑点。它不等同于 OPRA 报价级回测。

只运行 SOXL Paper 策略守护进程（不会运行 AI Agent 的其他策略）：

```bash
PYTHONPATH=. python ai_agent/scripts/run_agent.py --mode daemon --phase soxl --live
```
