"""Test fixtures for hermes-squad."""
import tempfile
from pathlib import Path

import pytest

from hermes_squad import db as db_module


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Use a temporary database for each test."""
    db_path = tmp_path / "team.db"
    monkeypatch.setattr(db_module, "_resolve_db_path", lambda: db_path)
    monkeypatch.setattr(db_module, "_db", None)
    yield db_path
    db_module.close_db()
