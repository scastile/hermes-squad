"""Tests for TeamMailbox."""

import pytest

from hermes_squad.mailbox import TeamMailbox, get_mailbox


class TestTeamMailbox:
    def test_write_and_read_unread(self):
        mailbox = TeamMailbox()
        team_id = "team-1"

        # Write 3 messages to agent-a
        mailbox.write(team_id, "agent-a", "agent-b", "Hello 1")
        mailbox.write(team_id, "agent-a", "agent-b", "Hello 2")
        mailbox.write(team_id, "agent-a", "agent-c", "Hello 3")

        # Read unread — should get all 3
        messages = mailbox.read_unread(team_id, "agent-a")
        assert len(messages) == 3
        assert messages[0]["content"] == "Hello 1"
        assert messages[0]["from_agent_id"] == "agent-b"

        # Read again — should be empty (atomically marked read)
        messages = mailbox.read_unread(team_id, "agent-a")
        assert len(messages) == 0

    def test_read_all_includes_read(self):
        mailbox = TeamMailbox()
        team_id = "team-2"

        mailbox.write(team_id, "agent-a", "agent-b", "Message 1")
        mailbox.read_unread(team_id, "agent-a")  # marks as read

        # read_all should still return it
        all_msgs = mailbox.read_all(team_id, "agent-a")
        assert len(all_msgs) == 1

    def test_unread_count(self):
        mailbox = TeamMailbox()
        team_id = "team-3"

        assert mailbox.unread_count(team_id, "agent-x") == 0

        mailbox.write(team_id, "agent-x", "agent-y", "Hello")
        assert mailbox.unread_count(team_id, "agent-x") == 1

        mailbox.read_unread(team_id, "agent-x")
        assert mailbox.unread_count(team_id, "agent-x") == 0

    def test_different_agents_isolated(self):
        mailbox = TeamMailbox()
        team_id = "team-4"

        mailbox.write(team_id, "agent-a", "system", "For A")
        mailbox.write(team_id, "agent-b", "system", "For B")

        a_msgs = mailbox.read_unread(team_id, "agent-a")
        b_msgs = mailbox.read_unread(team_id, "agent-b")

        assert len(a_msgs) == 1
        assert a_msgs[0]["content"] == "For A"
        assert len(b_msgs) == 1
        assert b_msgs[0]["content"] == "For B"

    def test_delete_team(self):
        mailbox = TeamMailbox()
        team_id = "team-5"

        mailbox.write(team_id, "agent-a", "system", "Hello")
        mailbox.delete_team(team_id)

        assert mailbox.unread_count(team_id, "agent-a") == 0
        assert len(mailbox.read_all(team_id, "agent-a")) == 0

    def test_subject_and_files(self):
        mailbox = TeamMailbox()
        team_id = "team-6"

        msg = mailbox.write(
            team_id,
            "agent-a",
            "agent-b",
            "Check this out",
            subject="Results",
            files=["/tmp/file1.png", "/tmp/file2.txt"],
        )

        assert msg["subject"] == "Results"
        assert msg["files"] == ["/tmp/file1.png", "/tmp/file2.txt"]

        messages = mailbox.read_unread(team_id, "agent-a")
        assert len(messages) == 1
        assert messages[0]["subject"] == "Results"
        assert messages[0]["files"] == ["/tmp/file1.png", "/tmp/file2.txt"]
