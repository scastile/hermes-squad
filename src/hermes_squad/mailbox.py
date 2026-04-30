"""
Async inter-agent mailbox backed by SQLite.

Every team session gets its own mailbox namespace (keyed by team_id).
Agents write messages to each other and read their unread queue atomically.
"""

import json
import time
import uuid
from typing import Optional

import logging

from hermes_squad.db import get_db

logger = logging.getLogger("hermes_squad.mailbox")


class TeamMailbox:
    """Persistent async mailbox for team agent communication."""

    # ── write ──────────────────────────────────────────────────────────

    def write(
        self,
        team_id: str,
        to_agent_id: str,
        from_agent_id: str,
        content: str,
        *,
        subject: Optional[str] = None,
        files: Optional[list[str]] = None,
    ) -> dict:
        """Write a message to an agent's mailbox. Returns the persisted message."""
        db = get_db()
        msg_id = uuid.uuid4().hex
        now = int(time.time() * 1000)

        db.execute(
            """INSERT INTO team_mailbox (id, team_id, to_agent_id, from_agent_id,
               subject, content, files, read, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                msg_id,
                team_id,
                to_agent_id,
                from_agent_id,
                subject,
                content,
                json.dumps(files) if files else None,
                now,
            ),
        )
        db.commit()

        return {
            "id": msg_id,
            "team_id": team_id,
            "to_agent_id": to_agent_id,
            "from_agent_id": from_agent_id,
            "subject": subject,
            "content": content,
            "files": files,
            "read": False,
            "created_at": now,
        }

    # ── read ───────────────────────────────────────────────────────────

    def read_unread(self, team_id: str, agent_id: str) -> list[dict]:
        """
        Atomically read all unread messages for an agent and mark them read.
        Uses a single transaction to prevent double-delivery.
        """
        db = get_db()
        messages = []

        with db:  # transaction
            rows = db.execute(
                """SELECT * FROM team_mailbox
                   WHERE team_id = ? AND to_agent_id = ? AND read = 0
                   ORDER BY created_at ASC""",
                (team_id, agent_id),
            ).fetchall()

            if rows:
                ids = [r["id"] for r in rows]
                placeholders = ",".join("?" for _ in ids)
                db.execute(
                    f"UPDATE team_mailbox SET read = 1 WHERE id IN ({placeholders})",
                    ids,
                )
            messages = [dict(r) for r in rows]

        # Deserialize files from JSON string
        for msg in messages:
            if msg.get("files"):
                try:
                    msg["files"] = json.loads(msg["files"])
                except (json.JSONDecodeError, TypeError):
                    msg["files"] = None

        return messages

    def peek_unread(self, team_id: str, agent_id: str) -> list[dict]:
        """Read unread messages without marking them as read (read-only query)."""
        db = get_db()
        rows = db.execute(
            """SELECT * FROM team_mailbox
               WHERE team_id = ? AND to_agent_id = ? AND read = 0
               ORDER BY created_at ASC""",
            (team_id, agent_id),
        ).fetchall()

        messages = [dict(r) for r in rows]
        for msg in messages:
            if msg.get("files"):
                try:
                    msg["files"] = json.loads(msg["files"])
                except (json.JSONDecodeError, TypeError):
                    msg["files"] = None

        return messages

    def read_all(
        self, team_id: str, agent_id: str, limit: int = 50
    ) -> list[dict]:
        """Read all messages for an agent (newest first), including read ones."""
        db = get_db()
        rows = db.execute(
            """SELECT * FROM team_mailbox
               WHERE team_id = ? AND to_agent_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (team_id, agent_id, limit),
        ).fetchall()

        messages = [dict(r) for r in rows]
        for msg in messages:
            if msg.get("files"):
                try:
                    msg["files"] = json.loads(msg["files"])
                except (json.JSONDecodeError, TypeError):
                    msg["files"] = None

        return messages

    # ── stats ──────────────────────────────────────────────────────────

    def unread_count(self, team_id: str, agent_id: str) -> int:
        """Count unread messages for an agent."""
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM team_mailbox WHERE team_id = ? AND to_agent_id = ? AND read = 0",
            (team_id, agent_id),
        ).fetchone()
        return row["cnt"] if row else 0

    # ── cleanup ────────────────────────────────────────────────────────

    def delete_team(self, team_id: str):
        """Delete all mailbox messages for a team."""
        db = get_db()
        db.execute("DELETE FROM team_mailbox WHERE team_id = ?", (team_id,))
        db.commit()

    def delete_old(self, older_than_days: int = 7) -> int:
        """Delete messages older than N days. Returns count deleted."""
        db = get_db()
        cutoff = int((time.time() - older_than_days * 86400) * 1000)
        cursor = db.execute(
            "DELETE FROM team_mailbox WHERE created_at < ?", (cutoff,)
        )
        db.commit()
        return cursor.rowcount


# Module-level singleton
_mailbox: Optional[TeamMailbox] = None


def get_mailbox() -> TeamMailbox:
    global _mailbox
    if _mailbox is None:
        _mailbox = TeamMailbox()
    return _mailbox
