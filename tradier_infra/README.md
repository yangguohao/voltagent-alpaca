# Tradier infrastructure

Live Tradier market-data adapter used alongside Alpaca order execution.

- `client.py` — authenticated production REST client.
- `options_chain.py` — expiration discovery plus live option quotes, open interest,
  IV, and Greeks in the shape expected by the existing strategies.
- `option_quotes.py` — latest NBBO used to price Alpaca limit orders.

Set `OPTION_DATA_PROVIDER=tradier` and `TRADIER_API_KEY` in the root `.env`.
Only the production endpoint is used: Tradier Sandbox market data is delayed by
15 minutes. The token is never logged.
