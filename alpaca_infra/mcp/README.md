# Alpaca MCP Server (Development & Demo)

Runtime uses `alpaca-py` SDK. Configure MCP for Cursor/Claude development.

## Cursor MCP Config

```json
{
  "mcpServers": {
    "alpaca": {
      "command": "uvx",
      "args": ["alpaca-mcp-server"],
      "env": {
        "ALPACA_API_KEY": "your_key",
        "ALPACA_SECRET_KEY": "your_secret",
        "ALPACA_PAPER_TRADE": "true",
        "ALPACA_TOOLSETS": "account,trading,options-data,stock-data"
      }
    }
  }
}
```
