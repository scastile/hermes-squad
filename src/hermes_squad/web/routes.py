"""
REST API routes for Hermes Squad dashboard.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

router = APIRouter(prefix="/api")


# ── helpers ────────────────────────────────────────────────────────────────


def _get_upload_dir() -> Path:
    from hermes_squad.db import get_db_path

    d = get_db_path().parent / "uploads"
    d.mkdir(exist_ok=True)
    return d


# ── status ─────────────────────────────────────────────────────────────────


@router.get("/status")
def team_status(team_id: str = Query(None)):
    """Overview: active tasks, messages waiting, agent statuses."""
    from hermes_squad.task_service import get_task_service
    from hermes_squad.mailbox import get_mailbox

    task_service = get_task_service()
    mailbox = get_mailbox()

    if team_id:
        tasks = task_service.list_all(team_id)
        members = task_service.get_team_members(team_id)
        unread = {
            m: mailbox.unread_count(team_id, m) for m in members
        }
        return {
            "team_id": team_id,
            "members": members,
            "unread_counts": unread,
            "tasks": _task_summary(tasks),
        }

    # All teams summary
    from hermes_squad.db import get_db

    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT team_id FROM team_tasks UNION SELECT DISTINCT team_id FROM team_mailbox"
    ).fetchall()

    teams = []
    for row in rows:
        tid = row[0]
        tasks = task_service.list_all(tid)
        teams.append(
            {
                "team_id": tid,
                "task_count": len(tasks),
                "tasks": _task_summary(tasks),
            }
        )

    return {"teams": teams}


def _task_summary(tasks: list) -> dict:
    statuses = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
    for t in tasks:
        s = t.get("status", "pending")
        statuses[s] = statuses.get(s, 0) + 1
    return statuses


# ── tasks ──────────────────────────────────────────────────────────────────


@router.get("/tasks")
def list_tasks(team_id: str = Query(...)):
    """Full task board with dependencies."""
    from hermes_squad.task_service import get_task_service

    task_service = get_task_service()
    tasks = task_service.list_all(team_id)

    return {
        "team_id": team_id,
        "tasks": [
            {
                "id": t["id"],
                "short_id": t["id"][:8],
                "subject": t["subject"],
                "description": t.get("description"),
                "status": t["status"],
                "owner": t.get("owner"),
                "blocked_by": t.get("blocked_by", []),
                "blocks": t.get("blocks", []),
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
            }
            for t in tasks
        ],
    }


# ── mailbox ────────────────────────────────────────────────────────────────


@router.get("/mailbox/{agent_id}")
def agent_mailbox(
    agent_id: str,
    team_id: str = Query(...),
    history: bool = Query(False),
):
    """Read messages for an agent. Consumes unread messages (marks them read)
    so they don't appear as unread on subsequent fetches."""
    from hermes_squad.mailbox import get_mailbox

    mailbox = get_mailbox()

    if history:
        # Consume any unread messages first, then return full history.
        # This ensures messages are only "unread" once — the first time
        # they appear in a poll cycle.
        mailbox.read_unread(team_id, agent_id)
        messages = mailbox.read_all(team_id, agent_id)
    else:
        # Non-destructive peek — doesn't consume, for the status endpoint.
        messages = mailbox.peek_unread(team_id, agent_id)

    return {
        "agent_id": agent_id,
        "team_id": team_id,
        "messages": messages,
        "count": len(messages),
    }


@router.post("/mailbox/{agent_id}")
def write_to_agent(
    agent_id: str,
    team_id: str = Query(...),
    from_agent_id: str = Query(...),
    subject: str = Query(default=""),
    content: str = Query(...),
):
    """Write a message to an agent's mailbox. Enables agent-to-agent comms."""
    from hermes_squad.mailbox import get_mailbox

    mailbox = get_mailbox()
    msg = mailbox.write(
        team_id=team_id,
        to_agent_id=agent_id,
        from_agent_id=from_agent_id,
        subject=subject or None,
        content=content,
    )
    return {"status": "sent", "message": msg}


# ── upload ─────────────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """
    Accept image uploads (drag-and-drop or paste).
    Returns path for referencing in Hermes chat via MEDIA: prefix.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are allowed")

    # Generate unique filename
    ext = "png"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
            ext = "png"

    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = _get_upload_dir()
    filepath = upload_dir / filename

    content = await file.read()
    filepath.write_bytes(content)

    return {
        "filename": filename,
        "path": str(filepath),
        "url": f"/uploads/{filename}",
        "hermes_ref": f"MEDIA:{filepath}",
        "size": len(content),
        "content_type": file.content_type,
    }
