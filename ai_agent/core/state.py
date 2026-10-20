"""SQLite-backed agent state persistence."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_order_id TEXT,
                    symbol TEXT,
                    strategy TEXT,
                    status TEXT,
                    payload TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS signal_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    signal_type TEXT,
                    strength REAL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    response TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def set(self, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), now),
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return json.loads(row["value"])

    def log_trade(self, client_order_id: str, symbol: str, strategy: str, status: str, payload: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trade_log (client_order_id, symbol, strategy, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (client_order_id, symbol, strategy, status, json.dumps(payload), now),
            )

    def log_signal(self, symbol: str, signal_type: str, strength: float, metadata: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO signal_log (symbol, signal_type, strength, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                (symbol, signal_type, strength, json.dumps(metadata), now),
            )

    def log_llm(self, task: str, model: str, input_tokens: int, output_tokens: int, response: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO llm_log (task, model, input_tokens, output_tokens, response, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (task, model, input_tokens, output_tokens, response, now),
            )
