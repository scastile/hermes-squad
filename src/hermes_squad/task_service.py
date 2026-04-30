"""
Shared task board with bidirectional dependency tracking.

Tasks support: pending → in_progress → completed (or failed).
Dependencies are tracked via blocked_by/blocks arrays.
When a task completes, dependent tasks are auto-unblocked.
"""

import json
import time
import uuid
from typing import Optional

import logging

from hermes_squad.db import get_db

logger = logging.getLogger("hermes_squad.task_service")

VALID_STATUSES = {"pending", "in_progress", "completed", "failed"}


class TeamTaskService:
    """CRUD service for team tasks with dependency graph resolution."""

    # ── create ─────────────────────────────────────────────────────────

    def create(
        self,
        team_id: str,
        subject: str,
        *,
        description: Optional[str] = None,
        owner: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
    ) -> dict:
        """
        Create a new task. When depends_on is provided, also updates
        the `blocks` array of each prerequisite task for bidirectional tracking.
        """
        db = get_db()
        task_id = uuid.uuid4().hex
        now = int(time.time() * 1000)
        blocked_by = depends_on or []

        db.execute(
            """INSERT INTO team_tasks (id, team_id, subject, description,
               status, owner, blocked_by, blocks, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, '[]', '{}', ?, ?)""",
            (
                task_id,
                team_id,
                subject,
                description,
                owner,
                json.dumps(blocked_by),
                now,
                now,
            ),
        )

        # Bidirectional link: add this task to each prerequisite's `blocks` array
        if blocked_by:
            for upstream_id in blocked_by:
                self._append_to_blocks(upstream_id, task_id)

        db.commit()

        return {
            "id": task_id,
            "team_id": team_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "owner": owner,
            "blocked_by": blocked_by,
            "blocks": [],
            "metadata": {},
            "created_at": now,
            "updated_at": now,
        }

    # ── update ─────────────────────────────────────────────────────────

    def update(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> dict:
        """Update task status and/or owner. Validates status values."""
        db = get_db()

        if status is not None and status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )

        now = int(time.time() * 1000)
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if owner is not None:
            updates.append("owner = ?")
            params.append(owner)

        if not updates:
            # Nothing to update
            row = db.execute(
                "SELECT * FROM team_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Task '{task_id}' not found")
            return dict(row)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(task_id)

        db.execute(
            f"UPDATE team_tasks SET {', '.join(updates)} WHERE id = ?", params
        )
        db.commit()

        row = db.execute(
            "SELECT * FROM team_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Task '{task_id}' not found")

        return dict(row)

    # ── query ──────────────────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[dict]:
        """Get a single task by ID (supports prefix matching for short IDs)."""
        db = get_db()

        row = db.execute(
            "SELECT * FROM team_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row and len(task_id) < 32:
            row = db.execute(
                "SELECT * FROM team_tasks WHERE id LIKE ? LIMIT 1",
                (f"{task_id}%",),
            ).fetchone()

        return dict(row) if row else None

    def list_all(self, team_id: str) -> list[dict]:
        """List all tasks for a team, ordered by creation time."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM team_tasks WHERE team_id = ? ORDER BY created_at ASC",
            (team_id,),
        ).fetchall()
        return [_deserialize_task(r) for r in rows]

    def get_by_owner(self, team_id: str, owner: str) -> list[dict]:
        """Get tasks assigned to a specific agent."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM team_tasks WHERE team_id = ? AND owner = ? ORDER BY created_at ASC",
            (team_id, owner),
        ).fetchall()
        return [_deserialize_task(r) for r in rows]

    def get_team_members(self, team_id: str) -> list[str]:
        """Get unique agent IDs that own tasks in this team."""
        db = get_db()
        rows = db.execute(
            "SELECT DISTINCT owner FROM team_tasks WHERE team_id = ? AND owner IS NOT NULL",
            (team_id,),
        ).fetchall()
        return [r["owner"] for r in rows]

    # ── dependencies ───────────────────────────────────────────────────

    def check_unblocks(self, task_id: str) -> list[dict]:
        """
        When a task completes, remove it from all dependents' blocked_by arrays.
        Returns the subset of dependent tasks that are now fully unblocked
        (blocked_by became empty).
        """
        db = get_db()

        # Find the completed task
        completed = db.execute(
            "SELECT * FROM team_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not completed:
            return []

        team_id = completed["team_id"]
        completed_dict = dict(completed)

        # Find all tasks in the same team that block on this task
        all_tasks = db.execute(
            "SELECT * FROM team_tasks WHERE team_id = ?", (team_id,)
        ).fetchall()

        dependents = []
        for row in all_tasks:
            blocked_by = json.loads(row["blocked_by"] or "[]")
            if task_id in blocked_by:
                dependents.append(row)

        if not dependents:
            # Clean up the completed task's stale blocks pointer
            db.execute(
                "UPDATE team_tasks SET blocks = '[]', updated_at = ? WHERE id = ?",
                (int(time.time() * 1000), task_id),
            )
            db.commit()
            return []

        unblocked = []
        for dep in dependents:
            blocked_by = json.loads(dep["blocked_by"] or "[]")
            blocked_by = [b for b in blocked_by if b != task_id]
            db.execute(
                "UPDATE team_tasks SET blocked_by = ?, updated_at = ? WHERE id = ?",
                (json.dumps(blocked_by), int(time.time() * 1000), dep["id"]),
            )
            if not blocked_by:
                unblocked.append(_deserialize_task(dep))

        # Clean up the completed task's stale blocks pointer
        db.execute(
            "UPDATE team_tasks SET blocks = '[]', updated_at = ? WHERE id = ?",
            (int(time.time() * 1000), task_id),
        )
        db.commit()

        return unblocked

    # ── helpers ────────────────────────────────────────────────────────

    def _append_to_blocks(self, task_id: str, block_id: str):
        """Add block_id to the task's blocks array (bidirectional link)."""
        db = get_db()
        row = db.execute(
            "SELECT blocks FROM team_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return
        blocks = json.loads(row["blocks"] or "[]")
        if block_id not in blocks:
            blocks.append(block_id)
            db.execute(
                "UPDATE team_tasks SET blocks = ?, updated_at = ? WHERE id = ?",
                (json.dumps(blocks), int(time.time() * 1000), task_id),
            )

    # ── cleanup ────────────────────────────────────────────────────────

    def delete_team(self, team_id: str):
        """Delete all tasks for a team."""
        db = get_db()
        db.execute("DELETE FROM team_tasks WHERE team_id = ?", (team_id,))
        db.commit()


def _deserialize_task(row) -> dict:
    """Convert a DB row to a dict with deserialized JSON fields."""
    d = dict(row)
    for field in ("blocked_by", "blocks"):
        try:
            d[field] = json.loads(d.get(field, "[]") or "[]")
        except (json.JSONDecodeError, TypeError):
            d[field] = []
    try:
        d["metadata"] = json.loads(d.get("metadata", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["metadata"] = {}
    return d


# Module-level singleton
_task_service: Optional[TeamTaskService] = None


def get_task_service() -> TeamTaskService:
    global _task_service
    if _task_service is None:
        _task_service = TeamTaskService()
    return _task_service
