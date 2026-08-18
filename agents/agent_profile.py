from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .agent import (
    PERMISSION_PROFILES,
    AgentConfig,
    AgentThread,
    PermissionProfile,
    Provider,
    Reasoning,
    WORKSPACE,
    create_thread,
)


ProfileLevel = Literal["low", "mid", "high"]


@dataclass(frozen=True)
class AgentProfileConfig:
    name: str
    display_name: str
    provider: Provider
    model_profile: ProfileLevel
    reasoning_profile: ProfileLevel
    permission_profile: PermissionProfile
    persistent_thread: bool = False
    load_private_memory: bool = True
    load_working_state: bool = True
    load_shared_memory: bool = True
    load_principles: bool = True


class AgentProfile:
    """Loads a versioned profile for a single agent from ``agents/<name>/``."""

    def __init__(self, project_root: Path, agent_name: str) -> None:
        self.project_root = project_root.resolve()
        self.agent_name = self._validate_agent_name(agent_name)
        self.directory = self.project_root / "agents" / self.agent_name
        self.config_file = self.directory / "config.json"
        self.role_file = self.directory / "ROLE.md"
        self.memory_file = self.directory / "MEMORY.md"
        self.working_state_file = self.directory / "WORKING_STATE.md"
        self.commands_file = self.directory / "COMMANDS.md"
        self.commands_directory = self.directory / "commands"
        self.runtime_directory = self.directory / "runtime"
        self.thread_file = self.runtime_directory / "thread.json"
        self.principles_file = self.project_root / "PRINCIPLES.md"
        self.config = self._load_config()

    @staticmethod
    def _validate_agent_name(agent_name: str) -> str:
        normalized = agent_name.strip()
        if not normalized or not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
            raise ValueError(
                "Agent name may only contain letters, digits, '_' and '-'."
            )
        return normalized

    def _load_config(self) -> AgentProfileConfig:
        data = json.loads(self._read_required(self.config_file))
        required = {
            "name",
            "provider",
            "model_profile",
            "reasoning_profile",
            "permission_profile",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValueError(
                f"{self.config_file} is missing fields: {', '.join(missing)}"
            )
        if data["name"] != self.agent_name:
            raise ValueError(
                f"The name in config.json ({data['name']!r}) does not match "
                f"the agent's directory ({self.agent_name!r})."
            )

        provider = data["provider"]
        if provider not in ("codex", "claude"):
            raise ValueError(f"Unknown profile provider: {provider!r}")


        permission_profile = data["permission_profile"]
        if permission_profile not in PERMISSION_PROFILES:
            allowed = ", ".join(PERMISSION_PROFILES)
            raise ValueError(
                f"Invalid permission_profile: {permission_profile!r}. "
                f"Allowed values: {allowed}."
            )

        model_profile = self._validate_level(data["model_profile"], "model_profile")
        reasoning_profile = self._validate_level(
            data["reasoning_profile"], "reasoning_profile"
        )

        return AgentProfileConfig(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            provider=provider,
            model_profile=model_profile,
            reasoning_profile=reasoning_profile,
            permission_profile=permission_profile,  # type: ignore[arg-type]
            persistent_thread=bool(data.get("persistent_thread", False)),
            load_private_memory=bool(data.get("load_private_memory", True)),
            load_working_state=bool(data.get("load_working_state", True)),
            load_shared_memory=bool(data.get("load_shared_memory", True)),
            load_principles=bool(data.get("load_principles", True)),
        )

    @staticmethod
    def _validate_level(value: str, field_name: str) -> ProfileLevel:
        if value not in ("low", "mid", "high"):
            raise ValueError(
                f"Invalid value for {field_name}: {value!r}. "
                "Allowed values: low, mid, high."
            )
        return value  # type: ignore[return-value]

    @staticmethod
    def _read_required(path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Required file does not exist: {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"File is empty: {path}")
        return content

    @staticmethod
    def _read_optional(path: Path) -> str:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def load_role(self) -> str:
        return self._read_required(self.role_file)

    def load_principles(self) -> str:
        return self._read_optional(self.principles_file)

    def load_private_memory(self) -> str:
        return self._read_optional(self.memory_file)

    def load_working_state(self) -> str:
        return self._read_optional(self.working_state_file)

    def load_command(self, command_name: str, **variables: str) -> str:
        command_name = self._validate_agent_name(command_name)
        path = self.commands_directory / f"{command_name}.md"
        template = self._read_required(path)

        for key, value in variables.items():
            template = template.replace("{{" + key.upper() + "}}", value)

        unresolved = sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", template)))
        if unresolved:
            raise ValueError(
                f"Command {command_name!r} is missing values: {', '.join(unresolved)}"
            )
        return template


class Agent:
    """Higher-level agent object: profile + underlying conversational thread."""

    def __init__(self, profile: AgentProfile, thread: AgentThread) -> None:
        self.profile = profile
        self.thread = thread

    @property
    def name(self) -> str:
        return self.profile.config.name

    @property
    def display_name(self) -> str:
        return self.profile.config.display_name

    @property
    def provider(self) -> Provider:
        return self.profile.config.provider

    @property
    def model(self) -> str:
        return self.thread.model

    @property
    def reasoning(self) -> Reasoning:
        return self.thread.reasoning

    @property
    def permission_profile(self) -> str:
        return self.thread.permission_profile

    def ask(self, text: str) -> str:
        return self.thread.ask(text)

    def run_command(self, command_name: str, **variables: str) -> str:
        prompt = self.profile.load_command(command_name, **variables)
        return self.thread.ask(prompt)

    def close(self) -> None:
        self.thread.close()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def _resolve_provider(profile_provider: Provider, config: AgentConfig) -> Provider:
    configured = {
        "codex": config.PROVIDER_CODEX,
        "claude": config.PROVIDER_CLAUDE,
    }[profile_provider]
    if configured != profile_provider:
        raise ValueError(
            f"Profile provider {profile_provider!r} does not match the "
            f"value in .env ({configured!r})."
        )
    return profile_provider


def _select_model(config: AgentConfig, provider: Provider, level: ProfileLevel) -> str:
    if provider == "codex":
        mapping = {
            "low": config.MODEL_CODEX_LOW,
            "mid": config.MODEL_CODEX_MID,
            "high": config.MODEL_CODEX_HIGH,
        }
    else:
        mapping = {
            "low": config.MODEL_CLAUDE_LOW,
            "mid": config.MODEL_CLAUDE_MID,
            "high": config.MODEL_CLAUDE_HIGH,
        }
    return mapping[level]


def _select_reasoning(config: AgentConfig, level: ProfileLevel) -> str:
    return {
        "low": config.REASONING_LOW,
        "mid": config.REASONING_MID,
        "high": config.REASONING_HIGH,
    }[level]


def build_agent_instructions(profile: AgentProfile) -> str:
    parts = [profile.load_role()]

    if profile.config.load_principles:
        principles = profile.load_principles()
        if principles:
            parts.append(
                "# Principles\n\n"
                "Binding operating principles for this project (constitutional "
                "layer, takes precedence over habit or convenience, but not "
                "over an explicit contract requirement or an explicit "
                "instruction from the owner):\n\n"
                f"<principles>\n{principles}\n</principles>"
            )

    if profile.config.load_private_memory:
        memory = profile.load_private_memory()
        if memory:
            parts.append(
                "# Private long-term memory\n\n"
                "Memory is supporting context; current code and approved "
                "project decisions take precedence.\n\n"
                f"<private_memory>\n{memory}\n</private_memory>"
            )

    if profile.config.load_working_state:
        state = profile.load_working_state()
        if state:
            parts.append(
                "# Current working state\n\n"
                f"<working_state>\n{state}\n</working_state>"
            )

    if profile.config.load_shared_memory:
        parts.append(
            "# Shared project memory\n\n"
            "Before a significant task, read the relevant files in the "
            "`memory/` directory as needed, especially `PROJECT_STATE.md`, "
            "`DECISIONS.md`, and `OPEN_TASKS.md`. Current source code takes "
            "precedence over old memory."
        )

    parts.append(
        "# Technical profile\n\n"
        f"- Agent: `{profile.config.name}`\n"
        f"- Provider: `{profile.config.provider}`\n"
        f"- Permissions: `{profile.config.permission_profile}`\n"
        f"- Project root: `{profile.project_root}`\n\n"
        "You may read across the whole project. Do not limit your reading to "
        "your own subfolder under `agents/`. Writing is scoped: once "
        "`project/` holds real code, implement contract work there by "
        "default. Touching the framework layer (`agents/*.py`, "
        "`chat_architect.py`) or a governance `.md` file (`AGENTS.md`, "
        "`PRINCIPLES.md`, `ROLE.md`, `COMMANDS.md`) is in scope only when "
        "the contract explicitly calls for it. A technical sandbox "
        "restriction always takes precedence over a text instruction."
    )
    return "\n\n".join(parts)


def create_agent(
    agent_name: str,
    *,
    config: AgentConfig | None = None,
    project_root: Path = WORKSPACE,
) -> Agent:
    """Loads ``agents/<name>/`` and creates a configured agent."""
    if config is None:
        config = AgentConfig.load(project_root / ".env")

    profile = AgentProfile(project_root=project_root, agent_name=agent_name)
    provider = _resolve_provider(profile.config.provider, config)
    model = _select_model(config, provider, profile.config.model_profile)
    reasoning = _select_reasoning(config, profile.config.reasoning_profile)
    instructions = build_agent_instructions(profile)

    thread = create_thread(
        provider=provider,
        model=model,
        reasoning=reasoning,
        permission_profile=profile.config.permission_profile,
        config=config,
        instructions=instructions,
        cwd=profile.project_root,
        agent_label=profile.config.name,
    )
    return Agent(profile=profile, thread=thread)
