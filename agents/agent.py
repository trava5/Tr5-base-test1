from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypeAlias

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolUseBlock,
)
from dotenv import load_dotenv
from openai_codex import ApprovalMode, Codex, Sandbox

from .progress import log_event

# `openai_codex.Thread.run()` is a single blocking call that internally
# streams per-item events (which tool/command is running, which file is
# being edited) and only returns once the whole turn is done — throwing
# every intermediate event away. `_collect_turn_result` is the private
# helper that call ultimately delegates to; importing it directly lets
# `_codex_run_with_progress` (below) observe the same event stream live
# (via `TurnHandle.stream()`) while still handing off the actual
# result-extraction logic (final response, failure handling) to the SDK's
# own exact implementation, rather than reimplementing it independently
# and risking a subtly different answer. Imported defensively: if a future
# `openai_codex` release restructures this private module, Codex calls
# fall back to the plain blocking `thread.run(text)` (see
# `_codex_run_with_progress`) — no live per-item detail, but still
# correct, exactly today's behavior.
try:
    from openai_codex._run import _collect_turn_result as _codex_collect_turn_result
except ImportError:  # pragma: no cover - exercised only by a real SDK restructure
    _codex_collect_turn_result = None


# This module lives at <project_root>/agents/agent.py, so the project root
# is one level up from this file — not this file's own directory (see
# ADR-021).
WORKSPACE = Path(__file__).parent.parent.resolve()

PROVIDERS = ("codex", "claude")
CODEX_REASONING = ("low", "medium", "high")
CLAUDE_REASONING = ("low", "medium", "high")
ALL_REASONING = tuple(dict.fromkeys((*CODEX_REASONING, *CLAUDE_REASONING)))
PERMISSION_PROFILES = ("review", "edit", "full")
Provider = Literal["codex", "claude"]
Reasoning: TypeAlias = Literal["low", "medium", "high"]
PermissionProfile: TypeAlias = Literal["review", "edit", "full"]

PERMISSION_REVIEW: PermissionProfile = "review"
PERMISSION_EDIT: PermissionProfile = "edit"
PERMISSION_FULL: PermissionProfile = "full"

CLAUDE_REVIEW_TOOLS = ("Read", "Grep", "Glob")
CLAUDE_EDIT_TOOLS = (*CLAUDE_REVIEW_TOOLS, "Edit", "Write")
CLAUDE_FULL_TOOLS = (*CLAUDE_EDIT_TOOLS, "Bash")


def _env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Missing value {key} in .env.")
    return value.strip()


@dataclass(frozen=True)
class AgentConfig:
    """Configuration loaded from .env. Importing the module alone does not load .env."""

    PROVIDER_CODEX: str
    PROVIDER_CLAUDE: str
    MODEL_CODEX_LOW: str
    MODEL_CODEX_MID: str
    MODEL_CODEX_HIGH: str
    MODEL_CLAUDE_LOW: str
    MODEL_CLAUDE_MID: str
    MODEL_CLAUDE_HIGH: str
    REASONING_LOW: str
    REASONING_MID: str
    REASONING_HIGH: str

    @classmethod
    def load(cls, env_path: Path = WORKSPACE / ".env") -> "AgentConfig":
        load_dotenv(env_path)
        config = cls(
            PROVIDER_CODEX=_env("PROVIDER_CODEX"),
            PROVIDER_CLAUDE=_env("PROVIDER_CLAUDE"),
            MODEL_CODEX_LOW=_env("MODEL_CODEX_LOW"),
            MODEL_CODEX_MID=_env("MODEL_CODEX_MID"),
            MODEL_CODEX_HIGH=_env("MODEL_CODEX_HIGH"),
            MODEL_CLAUDE_LOW=_env("MODEL_CLAUDE_LOW"),
            MODEL_CLAUDE_MID=_env("MODEL_CLAUDE_MID"),
            MODEL_CLAUDE_HIGH=_env("MODEL_CLAUDE_HIGH"),
            REASONING_LOW=_env("REASONING_LOW"),
            REASONING_MID=_env("REASONING_MID"),
            REASONING_HIGH=_env("REASONING_HIGH"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        _validate_provider(self.PROVIDER_CODEX)
        _validate_provider(self.PROVIDER_CLAUDE)
        for reasoning in (self.REASONING_LOW, self.REASONING_MID, self.REASONING_HIGH):
            _validate_reasoning(reasoning)

    def models_for(self, provider: Provider) -> tuple[str, ...]:
        if provider == "codex":
            return (self.MODEL_CODEX_LOW, self.MODEL_CODEX_MID, self.MODEL_CODEX_HIGH)
        return (self.MODEL_CLAUDE_LOW, self.MODEL_CLAUDE_MID, self.MODEL_CLAUDE_HIGH)


CLAUDE_BIN = (
    Path(claude_agent_sdk.__file__).parent
    / "_bundled"
    / ("claude.exe" if platform.system() == "Windows" else "claude")
)


class AgentThread(Protocol):
    """Shared synchronous interface for a long-lived conversational thread."""

    name: str
    model: str
    reasoning: Reasoning
    permission_profile: PermissionProfile

    def ask(self, text: str) -> str: ...

    def close(self) -> None: ...


def _validate_provider(provider: str) -> Provider:
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}")
    return provider  # type: ignore[return-value]


def _validate_reasoning(reasoning: str) -> Reasoning:
    if reasoning not in ALL_REASONING:
        raise ValueError(f"Unknown reasoning level: {reasoning!r}")
    return reasoning  # type: ignore[return-value]


def _validate_reasoning_for_provider(provider: Provider, reasoning: Reasoning) -> None:
    allowed = CODEX_REASONING if provider == "codex" else CLAUDE_REASONING
    if reasoning not in allowed:
        values = ", ".join(allowed)
        raise ValueError(
            f"Reasoning {reasoning!r} is not supported for {provider}. "
            f"Allowed values: {values}."
        )


def _validate_permission_profile(permission_profile: str) -> PermissionProfile:
    if permission_profile not in PERMISSION_PROFILES:
        values = ", ".join(PERMISSION_PROFILES)
        raise ValueError(
            f"Unknown permission profile: {permission_profile!r}. "
            f"Allowed values: {values}."
        )
    return permission_profile  # type: ignore[return-value]


def _codex_permissions(permission_profile: PermissionProfile) -> tuple[ApprovalMode, Sandbox]:
    if permission_profile == "review":
        return ApprovalMode.deny_all, Sandbox.read_only
    if permission_profile == "edit":
        return ApprovalMode.deny_all, Sandbox.workspace_write
    return ApprovalMode.deny_all, Sandbox.full_access


def _claude_permissions(permission_profile: PermissionProfile) -> tuple[list[str], list[str], str]:
    if permission_profile == "review":
        tools = CLAUDE_REVIEW_TOOLS
    elif permission_profile == "edit":
        tools = CLAUDE_EDIT_TOOLS
    else:
        tools = CLAUDE_FULL_TOOLS
    return list(tools), list(tools), "dontAsk"


def _validate_model(model: str | None) -> str:
    if model:
        return model.strip()
    raise RuntimeError("No model specified. Use one of the MODEL_* values from .env.")


def _validate_model_for_provider(provider: Provider, model: str, config: AgentConfig) -> None:
    allowed = tuple(dict.fromkeys(config.models_for(provider)))
    if model not in allowed:
        values = ", ".join(allowed)
        raise ValueError(
            f"Model {model!r} is not supported for {provider}. "
            f"Allowed values from .env: {values}."
        )


def login(codex: Codex) -> None:
    account = codex.account(refresh_token=True)
    if account.account is not None or not account.requires_openai_auth:
        return

    login_flow = codex.login_chatgpt()
    print("Open this address in your browser:")
    print(login_flow.auth_url)
    result = login_flow.wait()
    if not result.success:
        raise RuntimeError(
            f"Login via ChatGPT failed: {result.error or 'unknown error'}."
        )

    account = codex.account(refresh_token=True)
    if account.account is None:
        raise RuntimeError("Login completed, but no active account is available yet.")
    print("Login succeeded.")


def _run_claude_cli(*args: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [str(CLAUDE_BIN), *args],
            capture_output=capture_output,
            text=capture_output,
            check=False,
        )
    except OSError as error:
        raise RuntimeError(
            f"Failed to launch the bundled `claude` CLI at path {CLAUDE_BIN}: {error}"
        ) from error


def login_claude() -> None:
    status = _run_claude_cli("auth", "status", "--json", capture_output=True)
    # The `claude` CLI exits non-zero for "not logged in" (it still prints
    # valid JSON, e.g. {"loggedIn": false, ...}), not only for a genuine
    # failure to run the check. So the exit code alone cannot distinguish
    # "not logged in" from "could not check" — only a body that parses as
    # the expected JSON with a `loggedIn` field is a reliable signal either
    # way; anything else (empty output, garbage, a crash) is a real failure.
    info = None
    if status.stdout:
        try:
            parsed = json.loads(status.stdout)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict) and "loggedIn" in parsed:
            info = parsed

    if info is not None and info.get("loggedIn"):
        return
    if info is None:
        detail = (status.stderr or status.stdout or "").strip()
        if detail:
            raise RuntimeError(f"Could not verify Claude login status: {detail}")
        raise RuntimeError("Could not verify Claude login status.")

    print("Open your browser and sign in to your Anthropic account...")
    result = _run_claude_cli("auth", "login", "--claudeai")
    if result.returncode != 0:
        raise RuntimeError("Login to the Anthropic account failed.")
    print("Login succeeded.")


def initialize_login(provider: Provider | None = None) -> None:
    if provider is not None:
        provider = _validate_provider(provider)
    if provider is None or provider == "codex":
        codex = Codex()
        try:
            login(codex)
        finally:
            codex.close()
    if provider is None or provider == "claude":
        login_claude()


def _log_codex_event(project_root: Path, agent_label: str, event: object) -> None:
    """Logs one live-streamed Codex turn event via `progress.log_event`,
    if it is an item start/completion carrying anything worth showing.

    Deliberately duck-typed (`getattr` throughout, never an `isinstance`
    against a specific generated schema class) so a future `openai_codex`
    release adding/renaming item fields degrades to a plainer log line
    instead of raising — this function is display-only and must never be
    able to break the actual agent call it is reporting on.
    """
    method = getattr(event, "method", "")
    if method not in ("item/started", "item/completed"):
        return
    payload = getattr(event, "payload", None)
    item = getattr(payload, "item", None)
    if item is None:
        return
    item = getattr(item, "root", item)
    kind = getattr(item, "type", None) or type(item).__name__

    detail = None
    if kind == "commandExecution":
        detail = getattr(item, "command", None)
    elif kind == "fileChange":
        changes = getattr(item, "changes", None) or []
        paths = [path for path in (getattr(change, "path", None) for change in changes) if path]
        detail = ", ".join(paths) if paths else None
    elif kind == "agentMessage":
        text = getattr(item, "text", None) or ""
        detail = text[:80] + ("…" if len(text) > 80 else "")

    verb = "started" if method == "item/started" else "done"
    message = f"{kind} {verb}"
    if detail:
        message += f": {detail}"
    log_event(project_root, agent_label, message)


def _codex_run_with_progress(thread, text: str, *, project_root: Path, agent_label: str):
    """Runs one Codex turn like `Thread.run()`, but also logs each item as
    it streams in (see `_log_codex_event`) instead of only returning the
    final collected result once the whole turn is already done — the gap
    this module (`agents/progress.py`) exists to close. Falls back to the
    plain blocking `thread.run(text)` when `_codex_collect_turn_result`
    could not be imported (see the module-level `try`/`except` above) —
    same result, no live detail.
    """
    if _codex_collect_turn_result is None:
        return thread.run(text)

    turn = thread.turn(text)
    stream = turn.stream()

    def _tee():
        for event in stream:
            _log_codex_event(project_root, agent_label, event)
            yield event

    try:
        return _codex_collect_turn_result(_tee(), turn_id=turn.id)
    finally:
        stream.close()


class CodexThread:
    name = "Codex"

    def __init__(
        self,
        model: str,
        reasoning: Reasoning,
        permission_profile: PermissionProfile,
        approval_mode: ApprovalMode,
        sandbox: Sandbox,
        instructions: str | None = None,
        cwd: Path | str = WORKSPACE,
        agent_label: str = "Codex",
    ) -> None:
        self.model = model
        self.reasoning = reasoning
        self.permission_profile = permission_profile
        self.cwd = Path(cwd).resolve()
        self.agent_label = agent_label
        self._lock = threading.Lock()
        self._closed = False
        self._codex = Codex()
        try:
            login(self._codex)
            kwargs = {
                "approval_mode": approval_mode,
                "cwd": str(self.cwd),
                "model": model,
                "config": {"model_reasoning_effort": reasoning},
                "sandbox": sandbox,
            }
            if instructions:
                kwargs["developer_instructions"] = instructions
            self._thread = self._codex.thread_start(**kwargs)
        except Exception:
            self._codex.close()
            raise

        print("\nNew Codex thread created:")
        print(f"  Thread ID:   {self._thread.id}")
        print(f"  Model:       {model}")
        print(f"  Reasoning:   {reasoning}")
        print(f"  Permissions: {permission_profile}")
        print(f"  Sandbox:     {sandbox.value}")
        print(f"  Project:     {self.cwd}\n")

    def ask(self, text: str) -> str:
        if self._closed:
            raise RuntimeError("Codex thread is closed.")
        with self._lock:
            result = _codex_run_with_progress(
                self._thread, text, project_root=self.cwd, agent_label=self.agent_label
            )
        return result.final_response or ""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._codex.close()

    def __enter__(self) -> "CodexThread":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def _summarize_tool_use(block: ToolUseBlock) -> str:
    """Short, human-readable label for one `ToolUseBlock` — the tool name
    plus its main argument, when one of the common ones is present
    (`file_path`/`path` for Read/Edit/Write, `pattern` for Grep/Glob,
    `command` for Bash — covers every tool `CLAUDE_FULL_TOOLS` grants).
    Falls back to just the tool name for anything else, rather than
    guessing at an unfamiliar input shape."""
    input_data = block.input or {}
    for key in ("file_path", "path", "pattern", "command"):
        value = input_data.get(key)
        if value:
            return f"{block.name}: {value}"
    return block.name


class ClaudeThread:
    name = "Claude"

    def __init__(
        self,
        model: str,
        permission_profile: PermissionProfile,
        tools: list[str],
        allowed_tools: list[str],
        reasoning: Reasoning = "medium",
        permission_mode: str = "dontAsk",
        instructions: str | None = None,
        cwd: Path | str = WORKSPACE,
        agent_label: str = "Claude",
    ) -> None:
        self.model = model
        self.reasoning = reasoning
        self.permission_profile = permission_profile
        self.cwd = Path(cwd).resolve()
        self.agent_label = agent_label
        self._lock = threading.Lock()
        self._closed = False
        login_claude()

        self._loop = asyncio.new_event_loop()
        loop_ready = threading.Event()

        def _run_loop() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.call_soon(loop_ready.set)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, daemon=True)
        self._loop_thread.start()
        loop_ready.wait()

        options_kwargs = {
            "cwd": str(self.cwd),
            "model": model,
            "effort": reasoning,
            "tools": tools,
            "allowed_tools": allowed_tools,
            "permission_mode": permission_mode,
        }
        if instructions:
            options_kwargs["system_prompt"] = instructions
        options = ClaudeAgentOptions(**options_kwargs)
        self._client = ClaudeSDKClient(options)
        try:
            self._run(self._client.connect())
        except Exception:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=2)
            raise

        print("\nNew Claude thread created:")
        print(f"  Model:       {model}")
        print(f"  Effort:      {reasoning}")
        print(f"  Permissions: {permission_profile}")
        print(f"  Tools:       {', '.join(tools)}")
        print(f"  Project:     {self.cwd}\n")

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def ask(self, text: str) -> str:
        if self._closed:
            raise RuntimeError("Claude thread is closed.")
        with self._lock:
            return self._run(self._ask_async(text))

    async def _ask_async(self, text: str) -> str:
        await self._client.query(text)
        parts: list[str] = []
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        # Live visibility into what the call is doing right
                        # now (`Read agents/pipeline.py`, `Grep ...`, ...) —
                        # the SDK already streams this per message; it was
                        # previously discarded here, leaving total console
                        # silence for the whole duration of a call. See
                        # `agents/progress.py`.
                        log_event(self.cwd, self.agent_label, _summarize_tool_use(block))
        return "\n".join(parts)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._run(self._client.disconnect())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop_thread.join(timeout=2)

    def __enter__(self) -> "ClaudeThread":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def create_thread(
    provider: str,
    model: str,
    reasoning: str,
    permission_profile: str,
    *,
    config: AgentConfig | None = None,
    instructions: str | None = None,
    cwd: Path | str | None = None,
    agent_label: str | None = None,
) -> CodexThread | ClaudeThread:
    """Creates a generic long-lived thread.

    ``instructions`` is an optional, ready-made instructions text. The
    function does not care where it comes from; profile logic is handled by
    the higher-level ``create_agent``.

    ``cwd`` sets the provider's working directory. If omitted, the original
    behavior is kept and ``WORKSPACE`` is used.

    ``agent_label`` tags progress log lines (see `agents/progress.py`) and
    the log file they are persisted to
    (``agents/<agent_label>/runtime/session.log``); omitted, it falls back
    to the generic provider name (``"Codex"``/``"Claude"``) — a direct
    `create_thread()` caller with no role still gets progress visibility on
    the console, just not a per-role log file. `create_agent()`
    (`agents/agent_profile.py`) passes the actual role name
    (`architect`/`reviewer`/`programmer`).
    """
    if config is None:
        config = AgentConfig.load()

    working_directory = Path(cwd).resolve() if cwd is not None else WORKSPACE

    provider = _validate_provider(provider)
    model = _validate_model(model)
    reasoning = _validate_reasoning(reasoning)
    permission_profile = _validate_permission_profile(permission_profile)
    _validate_reasoning_for_provider(provider, reasoning)
    _validate_model_for_provider(provider, model, config)

    if provider == "codex":
        approval_mode, sandbox = _codex_permissions(permission_profile)
        return CodexThread(
            model,
            reasoning=reasoning,
            permission_profile=permission_profile,
            approval_mode=approval_mode,
            sandbox=sandbox,
            instructions=instructions,
            cwd=working_directory,
            agent_label=agent_label or "Codex",
        )

    tools, allowed_tools, permission_mode = _claude_permissions(permission_profile)
    return ClaudeThread(
        model,
        permission_profile=permission_profile,
        tools=tools,
        allowed_tools=allowed_tools,
        reasoning=reasoning,
        permission_mode=permission_mode,
        instructions=instructions,
        cwd=working_directory,
        agent_label=agent_label or "Claude",
    )


def main() -> None:
    AgentConfig.load()
    initialize_login()
    print("Login is ready. Create threads from code via create_thread().")


if __name__ == "__main__":
    main()
