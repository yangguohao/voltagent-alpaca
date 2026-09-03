# VoltAgent — Autonomous Volatility Options Agent

**Alpaca AI Trading Agents Hackathon**  
Track: Options / Volatility  
Runtime: `alpaca-py` SDK paper trading (Options Level 3)  
AI: Groq `qwen/qwen3.8-27b` + `openai/gpt-oss-120b`  
Schedule: America/New_York market-hours daemon

---

## One-line pitch

A governed options agent that **detects volatility regimes, selects defined-risk multi-leg trades, and executes them on Alpaca** — with **hard risk gates the LLM cannot override**.

## Problem

Retail and small-desk traders can now place options electronically, but most “AI trading bots” either:

1. Let the model invent contracts and size (unsafe), or
2. Are indicator scripts with a chatbot bolted on (not autonomous).

Volatility is the more natural options problem: implied vs realized vol, defined risk, and a clear reason to use multi-leg structures. The missing piece is an agent that **runs unattended during U.S. market hours**, **logs why it traded or refused**, and **exits on adaptive P&L / DTE rules**.

## Solution

VoltAgent is a **rule-first, LLM-advisory** paper-trading agent:

```
signals (IV rank / HV-IV)
        ↓
regime LLM (gpt-oss-120b)  →  hard regime gate
        ↓
strategy candidates (straddle / strangle / iron condor)
        ↓
selector LLM (qwen3.8-27b)  →  rule fallback if hold / JSON fail
        ↓
hard risk gates  (LLM cannot skip)
        ↓
sizer + MLeg limit order on Alpaca
        ↓
exit cycle: adaptive TP / SL + DTE force-close
```

The LLM may **choose among pre-built candidates or hold**. It cannot invent strikes, change quantities, or bypass risk.

---

## 1. AI Logic

Three Groq agents, routed by task. Local Python owns signals, candidate construction, sizing, and execution.

| Agent | Model | Job | Constraint |
|-------|--------|-----|------------|
| **Regime** | `openai/gpt-oss-120b` | Classify `low_vol` / `high_vol` / `trending` / `choppy` from equity, P&L, watchlist | JSON only; confidence < 0.5 disables the regime gate |
| **Selector** | `qwen/qwen3.8-27b` | Pick `straddle` / `strangle` / `iron_condor` / `hold` from **approved names only** | If `hold` and fallback is on, rules pick (low IV → straddle; high IV → iron condor) |
| **Reviewer** | `openai/gpt-oss-120b` | Approve or reject one candidate | Compact payload; fallback approve only after risk gates already passed |

**What the model never sees:** raw option chains as a free-form “write me a trade.” Legs are built in `strategies/` from ATM / OTM selection (`TARGET_DTE` 14–35). The selector only receives **strategy names** plus signal metadata (symbol, IV rank, strength).

**Why AI is required:** regime language (choppy vs trending) is poorly captured by a single IV-rank cutoff; the reviewer is a second pass on “does this still make sense given portfolio state.” Both are **advisory**. Deterministic code remains the authority.

Decision logs use stable prefixes for judging / audit:

- `[AI:regime]` — regime + confidence + notes  
- `[AI:selector]` — strategy + rationale  
- `[AI:reviewer]` — approve / reject  
- `[DECISION]` — skip vs submit  
- `[EXIT]` — hold vs close reason  

---

## 2. Risk Gates

Implemented in `risk/gates.py`, `risk/regime_gate.py`, `risk/sizer.py`, `execution/exit_manager.py`. **No LLM path can skip these checks.**

### Entry (hard rejects)

| Gate | Default | Effect |
|------|---------|--------|
| Daily loss | `MAX_DAILY_LOSS=0.03` | Stop **new** entries if equity is down ≥ 3% vs prior close |
| Max underlyings | `MAX_POSITIONS=5` | Count unique underlyings, not option legs |
| Duplicate symbol | open position **or** working order | Skip SPY/QQQ/… already in the book |
| Open interest | `MIN_OPEN_INTEREST=100` | Illiquid contracts rejected |
| Bid–ask | `MAX_BID_ASK_SPREAD_PCT=0.10` | Wide markets rejected |
| DTE | `MIN_DTE=7` | No new trades inside 7 DTE |

### Regime gate

| Regime | Allowed signals | Allowed strategies |
|--------|-----------------|-------------------|
| `low_vol` | `low_iv` | straddle, long strangle |
| `high_vol` | `high_iv` | iron condor, short strangle |
| `trending` | `low_iv` | straddle / long strangle (no short premium) |
| `choppy` | `high_iv` | iron condor / short strangle |

### Sizing

Qty = `floor(equity × MAX_RISK_PER_TRADE / estimated_max_loss_per_contract)`, capped by `MAX_CONTRACTS_PER_TRADE`.

- Debit (straddle / long strangle): max loss ≈ premium paid × 100  
- Credit (iron condor / short strangle): max loss ≈ (wing width − credit) × 100  

### Exit (adaptive)

Checked **before** new entries on every intraday cycle.

Thresholds interpolate with remaining DTE (`EXIT_FORCE_DTE=7` → `EXIT_DTE_SCALE_MAX=35`):

| DTE | Take profit | Stop loss |
|-----|-------------|-----------|
| 7 | +15% | −20% |
| ~23 (current book) | ~+29% | ~−31% |
| 35 | +40% | −40% |

**Force close:** any grouped structure with min DTE ≤ 7 is closed regardless of P&L.  
Closes are reverse MLeg orders (`sell_to_close` / `buy_to_close`).

---

## 3. Alpaca Infrastructure

**Runtime (this repo):** `alpaca-py` Trading + Market Data + Options Data clients (`data/alpaca_client.py`). Paper mode is locked via `ALPACA_PAPER=true`.

**Development / demo:** Alpaca MCP Server config in `mcp/README.md` (account, trading, options-data, stock-data) so Cursor/Claude can inspect the same paper account without putting MCP on the hot path.

| Piece | Implementation |
|-------|----------------|
| Equity quotes | IEX feed (free-tier compatible) |
| Option chain | Server-side DTE filter + pagination |
| Quotes for pricing | Indicative option NBBO; natural debit/credit + slippage |
| Orders | Multi-leg (`OrderClass.MLEG`) **limit** by default (`LIMIT_SLIPPAGE_PCT=0.05`); market fallback if quotes missing |
| State | SQLite `data/agent_state.db` — regime, trades, signals, LLM traces, last metrics |
| Clock | `America/New_York` — **not** the operator’s local TZ |

**Daemon** (`--mode daemon --live`):

| ET time | Action |
|---------|--------|
| 09:25 | Premarket regime |
| 09:25–15:30 | Intraday: **exit cycle first**, then scan watchlist every 30 min |
| 15:50 | Postmarket metrics snapshot |
| After 15:50 / weekends | Sleep until next weekday 09:25 ET |

Entry points:

```bash
PYTHONPATH=. python scripts/run_agent.py --mode health
PYTHONPATH=. python scripts/run_agent.py --mode once --phase intraday          # dry-run
PYTHONPATH=. python scripts/run_agent.py --mode once --phase exit --live
./scripts/start_agent.sh                                                       # daemon --live
PYTHONPATH=. python scripts/check_orders.py
```

Watchlist default: `SPY,QQQ,AAPL,MSFT,NVDA`.

---

## 4. Options Strategy

All strategies are **volatility structures**, not directional stock picks. Contracts are selected in `strategies/selection.py` (ATM / ±OTM, liquid expirations 14–35 DTE).

| Strategy | When | Structure | Risk |
|----------|------|-----------|------|
| **Long straddle** | Low IV rank (≤ 0.35), `low_iv` signal | Buy ATM put + ATM call | Debit = max loss |
| **Long / short strangle** | Low IV buy / high IV sell | ±7% OTM put + call | Long: debit; short: wing-defined |
| **Iron condor** | High IV, range-bound | Short ±5% OTM, long wings | Credit; max loss = width − credit |

**Hackathon live book (example, 2026-09-02):** the agent opened **Sep 25 ATM straddles** on SPY, QQQ, and MSFT after a `low_vol` regime and `low_iv` signals. Duplicate-symbol guard now skips those names on later cycles so the book is not scaled blindly.

---

## 5. P&L Tracking

- Live: Alpaca account equity, cash, buying power, daily P&L (`observability/metrics.py`)  
- Positions grouped by **underlying** (OCC root), not raw leg count  
- Postmarket writes `last_metrics` to SQLite  
- CLI: `scripts/check_orders.py` (account, legs, orders, local trade log, regime)  
- Decision audit: `logs/agent.log` + `llm_log` / `trade_log` tables  

**Paper snapshot after 2026-09-02 session (postmarket):**

| Metric | Value |
|--------|--------|
| Starting equity | $100,000 |
| Ending equity | **$99,112.46** |
| Session P&L | **−$887.54 (−0.89%)** |
| Open underlyings | SPY, QQQ, MSFT (10 option legs) |
| Strategy | Long straddles, ~23 DTE |

That P&L is **consistent with the thesis**: long volatility in a quiet, low-IV tape pays theta. The agent did **not** stop out (−31% band not hit). Exits remain armed for the rest of the event.

We report this honestly: a 1–2 day paper window is not a Sharpe study. Judges should score **governed autonomy + defined-risk options + inspectable logs**, not a lottery ticket on one session.

---

## Architecture (repo)

```
config/            settings, model routing
core/              TradingAgent, NY-session daemon, SQLite state
data/              Alpaca clients, bars, chains, OCC parse, quotes
signals/           IV-rank / HV proxy
strategies/        iron_condor, straddle, strangle + selection
risk/              gates, regime gate, sizer, adaptive exits
llm/               Groq client, JSON repair, regime / selector / reviewer
execution/         MLeg builder, limit pricer, exit manager
observability/     logs, metrics
scripts/           run_agent, check_orders, start_agent.sh
mcp/               Alpaca MCP notes for development
```

---

## Target user & why this is a product

**User:** a technically literate options trader who wants unattended **vol** exposure with a written kill-switch, not a black-box LLM that writes tickets.

**Why now:** Alpaca paper + options Level 3 + cheap Groq inference makes a full loop (research → order → exit) runnable on a laptop.

**Sketch of a post-hackathon product:** hosted paper daemon, then live with the same gates; optional MCP so the trader’s assistant can **read** positions but still cannot bypass `RiskGate`.

---

## Limitations (known)

- IV is proxied from realized vol when chain IV is thin; not a full IV-surface model  
- No holiday calendar beyond weekday skip  
- Streamlit dashboard is a stub; judging path today is CLI + logs  
- Groq JSON failures exist; we retry, then fall back to **rules after gates**, never to unconstrained LLM orders  

---

## lablab.ai portal copy (paste-ready)

**Title:** VoltAgent: Governed Volatility Options Agent on Alpaca  

**Short description (≤255 chars):**  
Autonomous paper-trading agent for U.S. options volatility. Groq LLMs advise regime and strategy; Python risk gates, sizing, MLeg limits, and adaptive exits execute on Alpaca. The model cannot invent contracts.

**Tags (suggested):** Alpaca, Options, Trading Agents, Groq, Python, Risk Management  

**Long description** — use sections 1–5 above (well over 100 words).
