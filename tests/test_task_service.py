"""Tests for TeamTaskService."""

import pytest

from hermes_squad.task_service import TeamTaskService, get_task_service


class TestTeamTaskService:
    def test_create_task(self):
        svc = TeamTaskService()
        task = svc.create("team-1", "Build login page")

        assert task["subject"] == "Build login page"
        assert task["status"] == "pending"
        assert task["blocked_by"] == []
        assert task["blocks"] == []

    def test_create_with_dependencies(self):
        svc = TeamTaskService()

        # Create task A
        task_a = svc.create("team-1", "Research API")
        # Create task B that depends on A
        task_b = svc.create(
            "team-1", "Implement API", depends_on=[task_a["id"]]
        )
        # Create task C that depends on both A and B
        task_c = svc.create(
            "team-1", "Test API", depends_on=[task_a["id"], task_b["id"]]
        )

        assert task_b["blocked_by"] == [task_a["id"]]
        assert task_c["blocked_by"] == [task_a["id"], task_b["id"]]

        # Check bidirectional links
        a_updated = svc.get(task_a["id"])
        assert task_b["id"] in a_updated["blocks"]
        assert task_c["id"] in a_updated["blocks"]

    def test_update_status(self):
        svc = TeamTaskService()
        task = svc.create("team-1", "Test task")

        updated = svc.update(task["id"], status="in_progress")
        assert updated["status"] == "in_progress"

        updated = svc.update(task["id"], status="completed")
        assert updated["status"] == "completed"

    def test_update_invalid_status(self):
        svc = TeamTaskService()
        task = svc.create("team-1", "Test task")

        with pytest.raises(ValueError, match="Invalid status"):
            svc.update(task["id"], status="bogus")

    def test_list_all(self):
        svc = TeamTaskService()
        svc.create("team-1", "Task 1")
        svc.create("team-1", "Task 2")
        svc.create("team-2", "Other team task")

        team1_tasks = svc.list_all("team-1")
        assert len(team1_tasks) == 2

        team2_tasks = svc.list_all("team-2")
        assert len(team2_tasks) == 1

    def test_get_by_owner(self):
        svc = TeamTaskService()
        svc.create("team-1", "Alice task", owner="alice")
        svc.create("team-1", "Bob task", owner="bob")
        svc.create("team-1", "Alice task 2", owner="alice")

        alice_tasks = svc.get_by_owner("team-1", "alice")
        assert len(alice_tasks) == 2

    def test_check_unblocks(self):
        svc = TeamTaskService()

        # Chain: A → B → C
        task_a = svc.create("team-1", "A")
        task_b = svc.create("team-1", "B", depends_on=[task_a["id"]])
        task_c = svc.create("team-1", "C", depends_on=[task_b["id"]])

        # Complete A — B should become unblocked
        svc.update(task_a["id"], status="completed")
        unblocked = svc.check_unblocks(task_a["id"])

        assert len(unblocked) == 1
        assert unblocked[0]["id"] == task_b["id"]

        # C should still be blocked (B isn't done yet)
        c = svc.get(task_c["id"])
        assert task_b["id"] in c["blocked_by"]

        # Complete B — C should become unblocked
        svc.update(task_b["id"], status="completed")
        unblocked = svc.check_unblocks(task_b["id"])

        assert len(unblocked) == 1
        assert unblocked[0]["id"] == task_c["id"]

    def test_short_id_lookup(self):
        svc = TeamTaskService()
        task = svc.create("team-1", "Test")
        short = task["id"][:8]

        found = svc.get(short)
        assert found is not None
        assert found["id"] == task["id"]

    def test_get_team_members(self):
        svc = TeamTaskService()
        svc.create("team-1", "Task 1", owner="alice")
        svc.create("team-1", "Task 2", owner="bob")
        svc.create("team-1", "Task 3", owner="alice")

        members = svc.get_team_members("team-1")
        assert set(members) == {"alice", "bob"}
