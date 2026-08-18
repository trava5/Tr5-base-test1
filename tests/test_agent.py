from __future__ import annotations

import asyncio
import subprocess
import threading

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
