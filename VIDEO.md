# Demo video outline (not a lablab required field)

lablab judges score a **≤5 minute MP4** (plus PDF slides). They do **not** ask for a video outline inside `SUBMISSION.md`. Use this file only as a shot list.

Target length: **4:00–4:30**. Record in English. 16:9. Show real paper account / logs — no mock P&L.

Suggested on-screen title: **VoltAgent — Alpaca paper, options, Groq advisory, hard gates**

---

## 0:00–0:25 — Problem

- Most “AI traders” either invent tickets or never place them.
- We built an agent that **places multi-leg options on Alpaca paper** and **refuses** when risk says no.

**On screen:** one sentence + architecture one-liner  
`signals → LLM advise → risk gates → MLeg → adaptive exit`

---

## 0:25–1:10 — How AI is used (and limited)

Talk over a 4-box diagram:

1. **Regime** (`gpt-oss-120b`) — `low_vol` / `high_vol` / …
2. **Selector** (`qwen3.8-27b`) — pick from **named** strategies only
3. **Reviewer** — approve / reject
4. **Python** — chain, strikes, size, orders

**Line to say:** “The LLM never chooses a strike. If JSON fails, rules fire **after** gates, not instead of them.”

---

## 1:10–2:40 — Live demo (this is the scoring core)

Do in this order. Keep terminal font large.

1. **Health**  
   `PYTHONPATH=. python scripts/run_agent.py --mode health`  
   Show `ACTIVE`, paper, equity.

2. **Positions / P&L**  
   `PYTHONPATH=. python scripts/check_orders.py`  
   Point at SPY/QQQ/MSFT straddles, 3 underlyings vs 10 legs, daily P&L.  
   Say: “Long vol in a quiet tape — small red is expected, not hidden.”

3. **Decision log**  
   `grep -E '\[DECISION\]|\[AI:|\[EXIT\]' logs/agent.log | tail -30`  
   Highlight:
   - skip already-held names
   - NVDA blocked by `low_vol` vs `high_iv`
   - `[EXIT] hold … tp29%/sl-31%`

4. **Daemon**  
   Show last log line: sleeping until **next 09:25 America/New_York**.  
   One sentence: “It does not poll 24/7. It wakes for the U.S. session.”

Optional if time: `--mode once --phase exit` dry-run (no `--live`) so they see hold, not a surprise close.

---

## 2:40–3:25 — Risk + exits

Table on a slide (or `.env.example` on screen):

- 2% risk / trade, 3% daily stop on **new** risk  
- No duplicate underlying  
- DTE-scaled TP/SL, force close at 7 DTE  
- MCP is for **dev inspection**; the live loop is `alpaca-py`

---

## 3:25–3:55 — Who it’s for + roadmap

- User: options trader who wants unattended vol, with a kill-switch  
- Next: holiday calendar, real IV surface, public Streamlit, same gates on live  

---

## 3:55–4:15 — Close

- Repo + paper account + logs are the demo  
- Tagline: **Advise with models. Authorize with code. Execute on Alpaca.**

Do **not** promise a winning P&L. Promise an inspectable agent.

---

## Recording checklist

- [ ] Paper account, no real-money keys on screen (blur `.env`)
- [ ] Video ≥ 3 min (lablab “limited” band is &lt; 3 min)
- [ ] Demo of **working** CLI, not slides-only
- [ ] Mention options + Alpaca + autonomous schedule
- [ ] Honest P&L (~−0.9% as of 2026-09-02 postmarket)

## Suggested PDF slide titles (upload separately)

1. Title / one-liner  
2. Problem  
3. Pipeline diagram  
4. AI vs gates  
5. Strategies (straddle / strangle / iron condor)  
6. Live book screenshot  
7. Adaptive exits  
8. Roadmap
