"""Shared fixtures for vault tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def vault_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal vault skeleton in tmp_path and point VAULT_PATH at it.

    Creates:
        tmp_path/
            AGENTS.md
            log.md
            raw/
            wiki/
    """
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / "log.md").write_text("# Log\n", encoding="utf-8")

    # Clear any pre-existing vault env vars, then set ours.
    monkeypatch.delenv("LLM_WIKI_PATH", raising=False)
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    return tmp_path
