# Hermes Squad

Team coordination plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — async mailbox, shared task board, wave-based subagent dispatch, and a web dashboard with image upload.

Built as a native Hermes plugin.

## Install

```bash
pip install hermes-squad
hermes team setup
```

Or from source:

```bash
git clone https://github.com/scastile/hermes-squad
cd hermes-squad
pip install -e .
hermes team setup
```

## What You Get

### 5 Team Coordination Tools

Subagents and parent agents use these to coordinate:

| Tool | What it does |
|------|-------------|
| `team_send` | Send messages to teammates' mailboxes (or broadcast to all) |
| `team_inbox` | Read unread messages (atomically marked read) |
| `team_task_create` | Create tasks on the shared board with dependency tracking |
| `team_task_update` | Update task status (pending → in_progress → completed → failed) |
| `team_task_list` | View all team tasks with statuses |

### Web Dashboard

```bash
hermes team web
# → http://localhost:8093
```

- **Task Board** — 4-column kanban (Pending / In Progress / Completed / Failed)
- **Mailbox Inspector** — per-agent message view with unread counts
- **Image Upload** — drag-and-drop, returns `MEDIA:` ref for Hermes chat

### Wave Dispatch

Tasks with dependencies execute in order — wave 1 runs in parallel, wave 2 starts only when all prerequisites complete.

```
Wave 1: [researcher, coder]         ← run together
Wave 2: [reviewer]                  ← waits for coder
Wave 3: [tester]                    ← waits for reviewer + researcher
```

## Usage

### In Hermes Chat

Just tell Hermes what you need — the team coordinator skill handles the rest:

```
"Use the team coordinator to build a FastAPI auth endpoint.
I need a researcher to find best practices, a coder to implement,
and a reviewer to check the code. The reviewer depends on the coder."
```

### Via Python API

```python
from hermes_squad.dispatch import dispatch_team

result = dispatch_team(
    tasks=[
        {"goal": "Research FastAPI auth patterns", "id": "research"},
        {"goal": "Implement auth endpoint", "id": "code"},
        {"goal": "Review implementation", "id": "review", "depends_on": ["code"]},
    ],
    workspace="/path/to/project",
)
```

### CLI

```bash
hermes team setup        # Initialize database
hermes team status       # Show teams and task counts
hermes team web          # Start dashboard (port 8093)
hermes team cleanup      # Remove old messages
```

## Architecture

```
hermes-squad/
├── db.py              # SQLite (team_mailbox + team_tasks tables)
├── mailbox.py         # Async message passing (write, read_unread, read_all)
├── task_service.py    # Task CRUD + bidirectional dependency graph
├── tools.py           # 5 tool schemas + handlers
├── dispatch.py        # Wave-based dispatch engine
├── plugin.py          # Hermes plugin lifecycle (register(ctx))
├── cli.py             # hermes team setup|status|web|cleanup
└── web/               # FastAPI server + dashboard SPA
    ├── server.py      # Uvicorn/FastAPI app
    ├── routes.py      # REST API + image upload endpoint
    └── static/        # Apple-inspired dark dashboard
        ├── index.html
        ├── style.css
        └── app.js
```

## Design

- **No TCP/MCP bridge** — Subagents share Hermes's tool registry. No network hops.
- **Atomic mailbox** — `read_unread` uses a SQLite transaction to prevent double-delivery.
- **Bidirectional dependencies** — `blocked_by` + `blocks` arrays kept in sync automatically.
- **Plugin-native** — Uses `ctx.register_tool()` and `ctx.register_cli_command()`. Zero core changes to Hermes.

## Testing

```bash
PYTHONPATH=src python -m pytest tests/ -v
```

## License

Apache 2.0 — same as AionUi, same as Hermes.
