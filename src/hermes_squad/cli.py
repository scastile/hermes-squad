"""
CLI commands for hermes-squad plugin.

Exposes: hermes team setup | status | web | cleanup
"""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger("hermes_squad.cli")


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse tree for 'hermes team' subcommands."""
    parser = argparse.ArgumentParser(
        prog="hermes team",
        description="Hermes Squad — multi-agent coordination plugin",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # ── setup ──────────────────────────────────────────────────────────
    setup_parser = sub.add_parser("setup", help="Initialize team database")
    setup_parser.set_defaults(handler=cmd_setup)

    # ── status ─────────────────────────────────────────────────────────
    status_parser = sub.add_parser("status", help="Show team status")
    status_parser.add_argument(
        "--team-id", help="Filter to specific team"
    )
    status_parser.set_defaults(handler=cmd_status)

    # ── web ────────────────────────────────────────────────────────────
    web_parser = sub.add_parser("web", help="Start team dashboard web UI")
    web_parser.add_argument(
        "--port", type=int, default=8093, help="Port (default: 8093)"
    )
    web_parser.add_argument(
        "--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)"
    )
    web_parser.add_argument(
        "--no-open", action="store_true", help="Don't open browser"
    )
    web_parser.set_defaults(handler=cmd_web)

    # ── cleanup ────────────────────────────────────────────────────────
    cleanup_parser = sub.add_parser("cleanup", help="Remove old data")
    cleanup_parser.add_argument(
        "--older-than",
        type=int,
        default=7,
        help="Remove data older than N days (default: 7)",
    )
    cleanup_parser.add_argument(
        "--team-id", help="Delete a specific team entirely"
    )
    cleanup_parser.set_defaults(handler=cmd_cleanup)

    return parser


# ── command handlers ───────────────────────────────────────────────────────


def cmd_setup(args):
    """Initialize the team database and verify installation."""
    from hermes_squad.db import get_db, get_db_path

    db = get_db()
    db_path = get_db_path()

    # Ensure uploads directory
    uploads_dir = db_path.parent / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    print("✓ Database initialized at", db_path)
    print("✓ 5 team tools registered (team_send, team_inbox, team_task_*)")
    print("✓ Upload directory:", uploads_dir)
    print()
    print("Ready! Use team tools in any Hermes session.")
    print("Start dashboard: hermes team web")


def cmd_status(args):
    """Show team status: tasks and mailbox stats."""
    from hermes_squad.task_service import get_task_service
    from hermes_squad.mailbox import get_mailbox

    task_service = get_task_service()
    mailbox = get_mailbox()

    team_id = args.team_id

    if team_id:
        _show_team_status(team_id, task_service, mailbox)
    else:
        # Show summary of all teams
        db = __import__("hermes_squad.db", fromlist=["get_db"]).get_db()
        teams = db.execute(
            "SELECT DISTINCT team_id FROM team_tasks UNION SELECT DISTINCT team_id FROM team_mailbox"
        ).fetchall()

        if not teams:
            print("No teams found. Create one by dispatching tasks with team coordination.")
            return

        for row in teams:
            tid = row[0]
            _show_team_status(tid, task_service, mailbox)
            print()


def _show_team_status(team_id, task_service, mailbox):
    """Print status for a single team."""
    tasks = task_service.list_all(team_id)
    members = task_service.get_team_members(team_id)

    statuses = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
    for t in tasks:
        s = t.get("status", "pending")
        statuses[s] = statuses.get(s, 0) + 1

    print(f"Team: {team_id}")
    print(
        f"  Tasks: {statuses['pending']} pending, "
        f"{statuses['in_progress']} in progress, "
        f"{statuses['completed']} completed, "
        f"{statuses['failed']} failed"
    )
    print(f"  Members: {len(members)} ({', '.join(members) if members else 'none'})")

    for member in members:
        unread = mailbox.unread_count(team_id, member)
        if unread:
            print(f"  📬 {member}: {unread} unread")


def cmd_web(args):
    """Start the web dashboard."""
    import webbrowser

    from hermes_squad.web.server import start as start_web

    url = f"http://{args.host}:{args.port}"
    if args.host == "0.0.0.0":
        url = f"http://localhost:{args.port}"

    print(f"✓ Team dashboard: {url}")
    print(f"✓ Image uploads: ~/.hermes/plugins/hermes-squad/uploads/")
    print()

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    start_web(port=args.port, host=args.host)


def cmd_cleanup(args):
    """Clean up old data or delete a specific team."""
    from hermes_squad.mailbox import get_mailbox
    from hermes_squad.task_service import get_task_service

    mailbox = get_mailbox()
    task_service = get_task_service()

    if args.team_id:
        mailbox.delete_team(args.team_id)
        task_service.delete_team(args.team_id)
        print(f"✓ Team '{args.team_id}' deleted.")
    else:
        deleted = mailbox.delete_old(older_than_days=args.older_than)
        print(f"✓ Deleted {deleted} messages older than {args.older_than} days.")
        print("  (Tasks are preserved — use --team-id to delete a full team.)")
