"""
Wave-based dispatch engine for multi-agent team coordination.

Executes tasks in dependency order — each wave runs in parallel,
and the next wave starts only when all prerequisites complete.
"""

import json
import logging
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger("hermes_squad.dispatch")


class WaveDispatcher:
    """
    Orchestrates task execution across multiple waves based on dependencies.

    Usage:
        dispatcher = WaveDispatcher(tasks, team_id, workspace="/path/to/project")
        results = dispatcher.run(parent_agent)
    """

    def __init__(
        self,
        tasks: list[dict],
        team_id: str,
        workspace: Optional[str] = None,
    ):
        self.tasks = tasks
        self.team_id = team_id
        self.workspace = workspace
        self._wave_counter = 0

    # ── public API ──────────────────────────────────────────────────────

    def run(self, parent_agent=None) -> dict:
        """
        Execute all tasks in dependency order.

        Args:
            parent_agent: Hermes AIAgent instance with delegate_task().
                          Pass None for stub/testing mode.

        Returns:
            {
                "waves": [
                    {"wave": 1, "tasks": [...], "results": [...]},
                    {"wave": 2, "tasks": [...], "results": [...]},
                ],
                "total_waves": N,
                "all_completed": true
            }
        """
        from hermes_squad.task_service import get_task_service

        task_service = get_task_service()

        # 1. Create Task entries in DB
        task_map = self._create_task_entries(task_service)

        # 2. Execute waves
        waves = []
        remaining = set(task_map.keys())

        while remaining:
            wave = self._next_wave(remaining, task_service)
            if not wave:
                stuck = [
                    task_service.get(tid) for tid in remaining
                ]
                stuck_info = [
                    {
                        "id": t["id"][:8],
                        "subject": t["subject"],
                        "blocked_by": t.get("blocked_by", []),
                    }
                    for t in stuck
                    if t
                ]
                return {
                    "error": "Deadlock detected",
                    "stuck_tasks": stuck_info,
                    "waves": waves,
                }

            # Execute wave
            wave_results = self._execute_wave(wave, task_service, parent_agent)
            waves.append(wave_results)

            # Mark tasks based on their result status and unblock dependents
            result_map = {}
            for r in wave_results.get("results", []):
                result_map[r.get("task_id")] = r.get("status", "completed")

            for task in wave:
                short_id = task["id"][:8]
                status = result_map.get(short_id, "completed")
                task_service.update(task["id"], status=status)
                if status == "completed":
                    task_service.check_unblocks(task["id"])
                remaining.discard(task["id"])

        return {
            "waves": waves,
            "total_waves": len(waves),
            "all_completed": True,
        }

    # ── internal ────────────────────────────────────────────────────────

    def _create_task_entries(self, task_service) -> dict:
        """Create TeamTask entries in the DB. Returns {task_id: task_dict}."""
        task_map = {}

        for i, task in enumerate(self.tasks):
            task_id = task.get("id") or f"task-{i}-{uuid.uuid4().hex[:6]}"
            depends_on = task.get("depends_on", [])

            created = task_service.create(
                team_id=self.team_id,
                subject=task.get("goal", f"Task {i}")[:200],
                description=task.get("context"),
                owner=task_id,  # task owns itself initially
                depends_on=depends_on,
            )
            task_map[created["id"]] = {**task, "id": created["id"]}

        return task_map

    def _next_wave(
        self, remaining: set, task_service
    ) -> list[dict]:
        """Find tasks whose dependencies are all satisfied."""
        wave = []
        for task_id in remaining:
            task = task_service.get(task_id)
            if not task:
                continue

            blocked_by = task.get("blocked_by", [])
            # A task is ready if all its blockers are completed (not in remaining)
            ready = all(b not in remaining for b in blocked_by)

            if ready:
                task_service.update(task_id, status="in_progress")
                wave.append(task)

        return wave

    def _execute_wave(
        self, wave: list[dict], task_service, parent_agent
    ) -> dict:
        """
        Execute a wave of tasks in parallel via Hermes's delegate_task.
        Falls back to context-only stub mode when parent_agent is unavailable
        (e.g. running standalone or in tests).
        """
        self._wave_counter += 1
        wave_num = self._wave_counter
        results = []
        live_mode = parent_agent is not None and hasattr(parent_agent, "delegate_task")

        if live_mode:
            results = self._execute_wave_live(wave, wave_num, parent_agent)
        else:
            results = self._execute_wave_stub(wave, wave_num)

        return {
            "wave": wave_num,
            "task_count": len(wave),
            "tasks": [t["id"][:8] for t in wave],
            "results": results,
        }

    def _execute_wave_live(
        self, wave: list[dict], wave_num: int, parent_agent
    ) -> list[dict]:
        """Spawn subagents via Hermes delegate_task."""
        delegate_tasks = []
        for task in wave:
            context = self._build_subagent_context(task)
            delegate_tasks.append({
                "goal": task.get("goal", task.get("subject", f"Complete task {task['id'][:8]}")),
                "context": context,
                "toolsets": ["terminal", "file", "web"],
            })

        try:
            delegate_results = parent_agent.delegate_task(
                tasks=delegate_tasks,
            )
        except Exception as e:
            logger.error("Wave %d delegate_task failed: %s", wave_num, e)
            delegate_results = [{"error": str(e), "task_id": t["id"][:8]} for t in wave]

        results = []
        for task, result in zip(wave, delegate_results):
            is_error = isinstance(result, dict) and "error" in result
            results.append({
                "task_id": task["id"][:8],
                "subject": task["subject"],
                "result": result if isinstance(result, dict) else {"summary": str(result)},
                "status": "failed" if is_error else "completed",
            })

        return results

    def _execute_wave_stub(
        self, wave: list[dict], wave_num: int
    ) -> list[dict]:
        """Return structured context for testing/standalone mode."""
        logger.info("Wave %d: no parent_agent — stub mode (context only)", wave_num)
        results = []
        for task in wave:
            context = self._build_subagent_context(task)
            results.append({
                "task_id": task["id"][:8],
                "subject": task["subject"],
                "context": context,
                "workspace": self.workspace,
                "team_id": self.team_id,
                "toolset": [
                    "team_send", "team_inbox", "team_task_create",
                    "team_task_update", "team_task_list",
                ],
                "note": "stub mode — parent_agent not available",
            })

        return results

    def _build_subagent_context(self, task: dict) -> str:
        """Build the context string injected into subagent prompts."""
        context = task.get("context", task.get("description", ""))

        team_context = f"""
---
You are part of a multi-agent team working together on a shared goal.

Team ID: {self.team_id}
Shared workspace: {self.workspace or 'current working directory'}
Your task ID: {task.get('id', 'unknown')[:8]}

Team coordination tools available to you:
• team_task_update(task_id, status) — Mark your work as in_progress or completed
• team_send(to, content) — Send results or questions to the team leader
• team_inbox() — Check for messages from teammates
• team_task_list() — See all team tasks and their status

When you complete your work:
1. Call team_task_update to mark your task "completed"
2. Call team_send(to="leader", content="your results summary") to report

Your specific task:
{task.get('goal', task.get('subject', ''))}
"""
        return context + team_context


# ── Convenience function ───────────────────────────────────────────────────


def dispatch_team(
    tasks: list[dict],
    team_id: Optional[str] = None,
    workspace: Optional[str] = None,
    parent_agent=None,
) -> dict:
    """
    Convenience function: create a team, dispatch tasks in waves.

    Args:
        tasks: List of {goal, context, depends_on[], ...}
        team_id: Auto-generated if not provided
        workspace: Shared working directory path
        parent_agent: Hermes AIAgent instance (for subagent spawning)

    Returns:
        Dispatch result dict from WaveDispatcher.run()
    """
    if team_id is None:
        team_id = f"team-{uuid.uuid4().hex[:12]}"

    dispatcher = WaveDispatcher(tasks, team_id, workspace)
    return dispatcher.run(parent_agent)
