"""
Team coordination tools for Hermes Agent.

Five tools that subagents and parent agents use to coordinate work:
- team_send: Send message to teammate's mailbox
- team_inbox: Read unread messages
- team_task_create: Create task on shared board
- team_task_update: Update task status
- team_task_list: List all team tasks
"""

import json
import logging

logger = logging.getLogger("hermes_squad.tools")

# ── Schemas ────────────────────────────────────────────────────────────────

TEAM_SEND_SCHEMA = {
    "name": "team_send",
    "description": (
        "Send a message to another team member's mailbox. The message persists "
        "until the recipient reads it. Use this to report results, share findings, "
        "ask for help, or coordinate next steps.\n\n"
        "Use '*' as the recipient to broadcast to all team members."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": (
                    "Recipient agent ID or name. Use '*' to broadcast to all "
                    "team members."
                ),
            },
            "subject": {
                "type": "string",
                "description": "Short subject line summarizing the message.",
            },
            "content": {
                "type": "string",
                "description": (
                    "The message body. Include all relevant details the recipient "
                    "needs — results, findings, questions, or next steps."
                ),
            },
            "team_id": {
                "type": "string",
                "description": "Team session ID (provided in your team context).",
            },
        },
        "required": ["to", "content", "team_id"],
    },
}

TEAM_INBOX_SCHEMA = {
    "name": "team_inbox",
    "description": (
        "Read your unread team messages. Messages are marked as read after "
        "retrieval and won't appear again. Use this to check for new assignments, "
        "results from teammates, or coordination requests.\n\n"
        "Set history=true to see all messages including previously read ones."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "team_id": {
                "type": "string",
                "description": "Team session ID (provided in your team context).",
            },
            "history": {
                "type": "boolean",
                "description": (
                    "If true, return all messages (not just unread). Default: false."
                ),
            },
        },
        "required": ["team_id"],
    },
}

TEAM_TASK_CREATE_SCHEMA = {
    "name": "team_task_create",
    "description": (
        "Create a new task on the team's shared task board. Tasks are visible "
        "to all team members and help coordinate work.\n\n"
        "Best practices:\n"
        "- Create tasks before assigning work\n"
        "- Set the owner to the teammate who should work on it\n"
        "- Use depends_on to express dependencies between tasks\n"
        "- Break large tasks into smaller, actionable items"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "team_id": {
                "type": "string",
                "description": "Team session ID.",
            },
            "subject": {
                "type": "string",
                "description": "Short task title — what needs to be done.",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of the task.",
            },
            "owner": {
                "type": "string",
                "description": "Teammate name/ID to assign this task to.",
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Task IDs that must complete before this task can start."
                ),
            },
        },
        "required": ["team_id", "subject"],
    },
}

TEAM_TASK_UPDATE_SCHEMA = {
    "name": "team_task_update",
    "description": (
        "Update the status or assignment of an existing task. "
        "Use this to mark work as in_progress, completed, or failed.\n\n"
        "Task IDs can be shortened to the first 8 characters."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Task ID (first 8 chars are enough).",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "failed"],
                "description": "New task status.",
            },
            "owner": {
                "type": "string",
                "description": "Reassign to a different teammate.",
            },
        },
        "required": ["task_id", "status"],
    },
}

TEAM_TASK_LIST_SCHEMA = {
    "name": "team_task_list",
    "description": (
        "List all tasks on the team's shared task board. Shows task ID, subject, "
        "status, and owner for each task. Use this to check what work is pending, "
        "in progress, or completed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "team_id": {
                "type": "string",
                "description": "Team session ID.",
            },
            "owner": {
                "type": "string",
                "description": "Filter to tasks assigned to a specific teammate.",
            },
        },
        "required": ["team_id"],
    },
}

# ── Handlers ───────────────────────────────────────────────────────────────


def handle_team_send(args, **kwargs):
    """Send a message to one or all teammates."""
    from hermes_squad.mailbox import get_mailbox
    from hermes_squad.task_service import get_task_service

    mailbox = get_mailbox()
    task_service = get_task_service()

    team_id = args["team_id"]
    to = args["to"]
    content = args["content"]
    subject = args.get("subject")
    from_agent = kwargs.get("task_id", "orchestrator")

    if to == "*":
        recipients = task_service.get_team_members(team_id)
        if not recipients:
            return json.dumps(
                {"error": "No team members found to broadcast to."}
            )
    else:
        recipients = [to]

    sent = []
    for recipient in recipients:
        mailbox.write(
            team_id=team_id,
            to_agent_id=recipient,
            from_agent_id=from_agent,
            content=content,
            subject=subject,
        )
        sent.append(recipient)

    logger.info(
        "team_send: %s → %s (%d recipients)", from_agent, to, len(sent)
    )
    return json.dumps({"sent": len(sent), "recipients": sent})


def handle_team_inbox(args, **kwargs):
    """Read unread (or all) messages for the calling agent."""
    from hermes_squad.mailbox import get_mailbox

    mailbox = get_mailbox()
    team_id = args["team_id"]
    agent_id = kwargs.get("task_id", "orchestrator")

    if args.get("history"):
        messages = mailbox.read_all(team_id, agent_id)
    else:
        messages = mailbox.read_unread(team_id, agent_id)

    if not messages:
        return json.dumps({"messages": [], "count": 0, "note": "No messages."})

    # Include full content so the agent can act on it
    return json.dumps({"messages": messages, "count": len(messages)})


def handle_team_task_create(args, **kwargs):
    """Create a new task on the shared board."""
    from hermes_squad.task_service import get_task_service

    task_service = get_task_service()

    task = task_service.create(
        team_id=args["team_id"],
        subject=args["subject"],
        description=args.get("description"),
        owner=args.get("owner"),
        depends_on=args.get("depends_on"),
    )

    short_id = task["id"][:8]
    return json.dumps(
        {
            "task_id": task["id"],
            "short_id": short_id,
            "subject": task["subject"],
            "status": task["status"],
            "owner": task.get("owner"),
            "depends_on": task["blocked_by"],
            "message": f"Task created: [{short_id}] \"{task['subject']}\"",
        }
    )


def handle_team_task_update(args, **kwargs):
    """Update task status or owner."""
    from hermes_squad.task_service import get_task_service

    task_service = get_task_service()
    task_id = args["task_id"]
    status = args.get("status")
    owner = args.get("owner")

    try:
        task = task_service.update(task_id, status=status, owner=owner)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    short_id = task["id"][:8]

    # If marking completed, auto-unblock dependents
    unblocked = []
    if status == "completed":
        unblocked = task_service.check_unblocks(task["id"])

    result = {
        "task_id": task["id"],
        "short_id": short_id,
        "status": task["status"],
        "owner": task.get("owner"),
    }

    if unblocked:
        result["unblocked"] = [
            {"id": t["id"][:8], "subject": t["subject"]} for t in unblocked
        ]
        result["message"] = (
            f"Task [{short_id}] marked {status}. "
            f"{len(unblocked)} dependent task(s) unblocked."
        )
    else:
        result["message"] = f"Task [{short_id}] updated: {status}."

    return json.dumps(result)


def handle_team_task_list(args, **kwargs):
    """List all tasks for a team."""
    from hermes_squad.task_service import get_task_service

    task_service = get_task_service()
    team_id = args["team_id"]
    owner = args.get("owner")

    if owner:
        tasks = task_service.get_by_owner(team_id, owner)
    else:
        tasks = task_service.list_all(team_id)

    if not tasks:
        return json.dumps({"tasks": [], "count": 0, "note": "No tasks yet."})

    summary = []
    for t in tasks:
        summary.append(
            {
                "short_id": t["id"][:8],
                "subject": t["subject"],
                "status": t["status"],
                "owner": t.get("owner", "unassigned"),
                "depends_on": [d[:8] for d in t.get("blocked_by", [])],
                "blocks": [b[:8] for b in t.get("blocks", [])],
            }
        )

    return json.dumps({"tasks": summary, "count": len(summary)})


# ── Tool registry map ──────────────────────────────────────────────────────

TOOLS = {
    "team_send": (TEAM_SEND_SCHEMA, handle_team_send),
    "team_inbox": (TEAM_INBOX_SCHEMA, handle_team_inbox),
    "team_task_create": (TEAM_TASK_CREATE_SCHEMA, handle_team_task_create),
    "team_task_update": (TEAM_TASK_UPDATE_SCHEMA, handle_team_task_update),
    "team_task_list": (TEAM_TASK_LIST_SCHEMA, handle_team_task_list),
}
