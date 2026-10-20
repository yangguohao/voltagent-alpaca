# SOXL strategy

本目录只包含 SOXL 趋势过滤与 Covered Call 交易方法：

- [`soxl.md`](soxl.md)：原始交易规则。
- [`strategy.py`](strategy.py)：V27.0 四季状态机（QQQ MA252、SOXX 252 日回撤、
  MA20/60 日成交量）、30 日熔断、SOXX 五日涨幅和合约筛选。
- [`manager.py`](manager.py)：持仓覆盖检查、开仓、T-1 与趋势转坏平仓。
- [`tests/`](tests/)：SOXL 专项测试。

该方案复用 `alpaca_infra` 的 Alpaca 行情、订单类型和执行器，但不参与 AI/LLM 的策略选择。
启用及运行：

```bash
cp ai_agent/.env.example .env
# 在 .env 中设置 SOXL_STRATEGY_ENABLED=true
PYTHONPATH=. python ai_agent/scripts/run_agent.py --mode once --phase soxl
```
