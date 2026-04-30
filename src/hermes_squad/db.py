"""
SQLite database for Hermes Squad plugin.

Creates and manages the team database at ~/.hermes/plugins/hermes-squad/team.db.
Lazy-initialized — tables are created on first access.
"""

import sqlite3
import threading
from pathlib import Path

import logging

logger = logging.getLogger("hermes_squad.db")

# Singleton
_db: sqlite3.Connection | None = None
_lock = threading.Lock()
_db_path: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_mailbox (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    to_agent_id TEXT NOT NULL,
    from_agent_id TEXT NOT NULL,
    subject TEXT,
    content TEXT NOT NULL,
    files TEXT,
    read INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS team_tasks (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending',
    owner TEXT,
    blocked_by TEXT DEFAULT '[]',
    blocks TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mailbox_unread
    ON team_mailbox(team_id, to_agent_id, read);

CREATE INDEX IF NOT EXISTS idx_mailbox_team
    ON team_mailbox(team_id, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_team
    ON team_tasks(team_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_owner
    ON team_tasks(team_id, owner);
"""


def _resolve_db_path() -> Path:
    """Determine the DB path from Hermes home or fall back to default."""
    hermes_home = Path.home() / ".hermes"
    plugin_dir = hermes_home / "plugins" / "hermes-squad"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return plugin_dir / "team.db"


def get_db() -> sqlite3.Connection:
    """Get the team database connection. Creates tables on first call."""
    global _db, _db_path

    if _db is not None:
        return _db

    with _lock:
        if _db is not None:
            return _db

        _db_path = _resolve_db_path()
        _db = sqlite3.connect(str(_db_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA foreign_keys=ON")
        _db.executescript(SCHEMA)
        _db.commit()
        logger.info("hermes-squad DB initialized at %s", _db_path)

    return _db


def get_db_path() -> Path:
    """Return the database file path (lazy-initializes DB)."""
    get_db()
    return _db_path  # type: ignore[return-value]


def close_db():
    """Close the database connection (for testing/cleanup)."""
    global _db
    if _db is not None:
        _db.close()
        _db = None
