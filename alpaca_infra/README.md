# Alpaca infrastructure

Reusable broker infrastructure shared by `ai_agent` and `soxl_strategy`:

- `clients.py` — trading, stock-data, and option-data SDK clients.
- `market_data.py` — daily bars and latest stock prices.
- `options_chain.py` / `option_quotes.py` — option contracts, snapshots, Greeks, and quotes.
- `occ.py` — OCC option-symbol parsing.
- `metrics.py` — account and exposure snapshots.
- `models.py` — broker-facing trade candidate and leg models.
- `execution/` — option pricing, order construction/submission, and position grouping.
- `mcp/` — Alpaca MCP development notes.

The package has no dependency on `ai_agent` or `soxl_strategy`; callers provide compatible
settings and trade-log objects through structural interfaces.
