from __future__ import annotations

import asyncio
import subprocess
import threading
from types import SimpleNamespace

import pytest

import agents.agent as agent


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_login_claude_returns_when_already_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent,
        "_run_claude_cli",
        lambda *args, **kwargs: _completed(0, stdout='{"loggedIn": true}'),
    )

    agent.login_claude()


def test_login_claude_triggers_login_flow_on_nonzero_exit_with_valid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real `claude auth status --json` exits non-zero when the user is
    # not logged in, while still printing valid JSON with `loggedIn: false`
    # — this must trigger the login flow, not be treated as a failed check.
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(args)
        if args[:2] == ("auth", "status"):
            return _completed(
                1, stdout='{"loggedIn": false, "authMethod": "none"}'
            )
        if args[:2] == ("auth", "login"):
            return _completed(0)
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(agent, "_run_claude_cli", fake_run)

    agent.login_claude()

    assert ("auth", "status", "--json") in calls
    assert ("auth", "login", "--claudeai") in calls


def test_login_claude_raises_when_status_output_is_not_parseable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agent,
        "_run_claude_cli",
        lambda *args, **kwargs: _completed(1, stderr="unexpected crash"),
    )

    with pytest.raises(RuntimeError, match="Could not verify Claude login status"):
        agent.login_claude()


def test_login_claude_raises_when_login_flow_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
        if args[:2] == ("auth", "status"):
            return _completed(1, stdout='{"loggedIn": false}')
        if args[:2] == ("auth", "login"):
            return _completed(1)
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(agent, "_run_claude_cli", fake_run)

    with pytest.raises(RuntimeError, match="Login to the Anthropic account failed"):
        agent.login_claude()


def test_claude_thread_close_stops_the_loop_even_if_disconnect_raises() -> None:
    """Regression test: `close()` used to call `self._client.disconnect()`
    before stopping the background event-loop thread, with no try/finally
    around it — if `disconnect()` raised, the loop was never stopped and
    the thread never joined, leaking both for the rest of the process.
    This matters because a brand-new `Agent` (and therefore a brand-new
    `ClaudeThread`) is constructed and closed for every single reviewer/
    programmer call (Tr5-base decision 9), so a disconnect failure on any
    one of those calls would otherwise leak a thread every time.

    Constructs a `ClaudeThread` without running `__init__` (which needs a
    real login and a real `ClaudeSDKClient`) and wires up only what
    `close()` actually touches: a real background event-loop thread (so
    the assertion that it actually stops is meaningful, not mocked away)
    and a fake client whose `disconnect()` raises.
    """
    thread = object.__new__(agent.ClaudeThread)
    thread._closed = False
    thread._lock = threading.Lock()

    loop = asyncio.new_event_loop()
    loop_ready = threading.Event()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(loop_ready.set)
        loop.run_forever()

    loop_thread = threading.Thread(target=_run_loop, daemon=True)
    loop_thread.start()
    loop_ready.wait()
    thread._loop = loop
    thread._loop_thread = loop_thread

    class _FailingClient:
        async def disconnect(self) -> None:
            raise RuntimeError("boom")

    thread._client = _FailingClient()

    with pytest.raises(RuntimeError, match="boom"):
        thread.close()

    loop_thread.join(timeout=2)
    assert not loop_thread.is_alive()
    assert thread._closed is True


def test_summarize_tool_use_includes_the_files_path() -> None:
    block = agent.ToolUseBlock(id="1", name="Read", input={"file_path": "agents/pipeline.py"})
    assert agent._summarize_tool_use(block) == "Read: agents/pipeline.py"


def test_summarize_tool_use_includes_the_bash_command() -> None:
    block = agent.ToolUseBlock(id="1", name="Bash", input={"command": "pytest -q"})
    assert agent._summarize_tool_use(block) == "Bash: pytest -q"


def test_summarize_tool_use_falls_back_to_just_the_tool_name() -> None:
    block = agent.ToolUseBlock(id="1", name="SomeFutureTool", input={"unexpected_key": "x"})
    assert agent._summarize_tool_use(block) == "SomeFutureTool"


def test_claude_thread_ask_logs_tool_use_blocks(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: `_ask_async` used to only ever collect `TextBlock`
    content, silently discarding every `ToolUseBlock` the SDK streamed —
    the one signal that could show what a multi-minute call was actually
    doing while it was still in flight. Bypasses `__init__` (needs a real
    login and a real `ClaudeSDKClient`); only `_ask_async`'s own fields
    (`_client`, `cwd`, `agent_label`) are exercised.
    """
    (tmp_path / "agents" / "reviewer").mkdir(parents=True)
    thread = object.__new__(agent.ClaudeThread)
    thread.cwd = tmp_path
    thread.agent_label = "reviewer"

    message = agent.AssistantMessage(
        content=[
            agent.ToolUseBlock(id="1", name="Read", input={"file_path": "agents/pipeline.py"}),
            agent.TextBlock(text="Looks good."),
        ],
        model="test-model",
    )

    class _FakeClient:
        async def query(self, text: str) -> None:
            return None

        async def receive_response(self):
            yield message

    thread._client = _FakeClient()

    result = asyncio.run(thread._ask_async("review this"))

    assert result == "Looks good."
    out = capsys.readouterr().out
    assert "[reviewer] Read: agents/pipeline.py" in out
    log_path = tmp_path / "agents" / "reviewer" / "runtime" / "session.log"
    assert "Read: agents/pipeline.py" in log_path.read_text(encoding="utf-8")


def test_log_codex_event_ignores_non_item_methods(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    event = SimpleNamespace(method="turn/completed", payload=SimpleNamespace())
    agent._log_codex_event(tmp_path, "programmer", event)
    assert capsys.readouterr().out == ""


def test_log_codex_event_summarizes_a_command_execution(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    item = SimpleNamespace(type="commandExecution", command="pytest -q")
    event = SimpleNamespace(
        method="item/started", payload=SimpleNamespace(item=SimpleNamespace(root=item))
    )
    agent._log_codex_event(tmp_path, "programmer", event)
    assert "commandExecution started: pytest -q" in capsys.readouterr().out


def test_log_codex_event_summarizes_a_file_change(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    item = SimpleNamespace(
        type="fileChange",
        changes=[SimpleNamespace(path="agents/pipeline.py"), SimpleNamespace(path="README.md")],
    )
    event = SimpleNamespace(
        method="item/completed", payload=SimpleNamespace(item=SimpleNamespace(root=item))
    )
    agent._log_codex_event(tmp_path, "programmer", event)
    out = capsys.readouterr().out
    assert "fileChange done: agents/pipeline.py, README.md" in out


def test_log_codex_event_truncates_a_long_agent_message(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    item = SimpleNamespace(type="agentMessage", text="x" * 200)
    event = SimpleNamespace(
        method="item/started", payload=SimpleNamespace(item=SimpleNamespace(root=item))
    )
    agent._log_codex_event(tmp_path, "programmer", event)
    out = capsys.readouterr().out
    assert ("x" * 80) in out
    assert ("x" * 81) not in out


def test_log_codex_event_handles_a_missing_item_without_crashing(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    event = SimpleNamespace(method="item/started", payload=SimpleNamespace(item=None))
    agent._log_codex_event(tmp_path, "programmer", event)
    assert capsys.readouterr().out == ""


def test_codex_run_with_progress_falls_back_to_run_when_collector_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(agent, "_codex_collect_turn_result", None)

    class _FakeThread:
        def run(self, text: str) -> str:
            return f"plain result for {text!r}"

    result = agent._codex_run_with_progress(
        _FakeThread(), "do the thing", project_root=tmp_path, agent_label="programmer"
    )
    assert result == "plain result for 'do the thing'"


def test_codex_run_with_progress_logs_each_streamed_item(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: `CodexThread.ask()` used to call the SDK's blocking
    `Thread.run()` directly, which internally streams and then discards
    every intermediate item event before returning — total silence for the
    whole duration of a programmer/reviewer call. This asserts the events
    a real `TurnHandle.stream()` would yield are observed (logged) on their
    way through, not only the final collected result."""
    events = [
        SimpleNamespace(
            method="item/started",
            payload=SimpleNamespace(
                item=SimpleNamespace(root=SimpleNamespace(type="commandExecution", command="ls"))
            ),
        ),
        SimpleNamespace(method="turn/completed", payload=SimpleNamespace()),
    ]

    closed = []

    class _FakeStream:
        def __iter__(self):
            return iter(events)

        def close(self) -> None:
            closed.append(True)

    class _FakeTurnHandle:
        id = "turn-1"

        def stream(self) -> "_FakeStream":
            return _FakeStream()

    class _FakeThread:
        def turn(self, text: str) -> _FakeTurnHandle:
            return _FakeTurnHandle()

    consumed = []

    def _fake_collect(stream, *, turn_id: str) -> str:
        consumed.extend(stream)
        assert turn_id == "turn-1"
        return "the final result"

    monkeypatch.setattr(agent, "_codex_collect_turn_result", _fake_collect)

    result = agent._codex_run_with_progress(
        _FakeThread(), "implement it", project_root=tmp_path, agent_label="programmer"
    )

    assert result == "the final result"
    assert len(consumed) == 2
    assert closed == [True]
    assert "commandExecution started: ls" in capsys.readouterr().out
