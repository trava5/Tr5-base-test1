from __future__ import annotations

from pathlib import Path

import pytest

from agents.progress import log_event


def test_log_event_prints_a_timestamped_line(capsys: pytest.CaptureFixture[str]) -> None:
    log_event(Path("/does/not/matter"), "reviewer", "running architecture_review...")

    out = capsys.readouterr().out
    assert "[reviewer] running architecture_review..." in out
    # HH:MM:SS timestamp prefix, e.g. "[14:03:07]".
    assert out.startswith("[") and out[3] == ":" and out[6] == ":"


def test_log_event_persists_to_the_agents_own_runtime_log(tmp_path: Path) -> None:
    (tmp_path / "agents" / "reviewer").mkdir(parents=True)

    log_event(tmp_path, "reviewer", "commandExecution started: pytest -q")

    log_path = tmp_path / "agents" / "reviewer" / "runtime" / "session.log"
    assert log_path.is_file()
    assert "commandExecution started: pytest -q" in log_path.read_text(encoding="utf-8")


def test_log_event_appends_across_multiple_calls(tmp_path: Path) -> None:
    (tmp_path / "agents" / "programmer").mkdir(parents=True)

    log_event(tmp_path, "programmer", "first")
    log_event(tmp_path, "programmer", "second")

    content = (tmp_path / "agents" / "programmer" / "runtime" / "session.log").read_text(
        encoding="utf-8"
    )
    assert "first" in content
    assert "second" in content
    assert content.index("first") < content.index("second")


def test_log_event_skips_the_file_when_the_agent_directory_does_not_exist(
    tmp_path: Path,
) -> None:
    """`agent_label` values that are not a real per-role directory (e.g. the
    generic provider-name fallback `"Claude"`/`"Codex"` used when
    `create_thread()` is called directly, with no role) must not create a
    stray `agents/<label>/` directory just to hold a log file."""
    log_event(tmp_path, "Claude", "some progress line")

    assert not (tmp_path / "agents" / "Claude").exists()


def test_log_event_swallows_file_write_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failure to persist the log line (disk full, permissions, ...) must
    never raise — logging is best-effort support for the actual agent call,
    not something that call's own success should depend on."""
    (tmp_path / "agents" / "architect").mkdir(parents=True)

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk is on fire")

    monkeypatch.setattr("builtins.open", _boom)

    log_event(tmp_path, "architect", "should still print")

    assert "should still print" in capsys.readouterr().out
