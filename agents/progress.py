"""Best-effort, timestamped progress visibility for long-running agent calls.

Both provider SDKs (`claude_agent_sdk`, `openai_codex`) stream fine-grained
events while a call is in progress — which tool is being used, which
command is running, which file is being edited — but `agents/agent.py`
previously discarded all of that and returned only the final text once the
whole call was done. For a multi-minute reviewer/programmer call this meant
total console silence until the call either finished or hung, with nothing
left afterward to tell the difference or to see which step it was on. This
module is what `agents/agent.py` calls to surface those events instead:
printed live with a timestamp and the agent's role name, and appended to
that role's own log file (`agents/<name>/runtime/session.log` — already
gitignored, see `.gitignore`'s `agents/*/runtime/*`) so the record survives
a closed terminal.

Best-effort by design: a failure to log a progress line (a disk write
error, a permissions issue) must never break the underlying agent call it
is reporting on, so `log_event` swallows its own I/O failures rather than
raising them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def log_event(project_root: Path, agent_label: str, message: str) -> None:
    """Prints one timestamped progress line, and appends the same line to
    `agents/<agent_label>/runtime/session.log` if `agents/<agent_label>/`
    exists. `agent_label` is expected to be a real per-role directory name
    (`architect`/`reviewer`/`programmer`) when created via
    `agents.agent_profile.create_agent()`; a caller using the lower-level
    `create_thread()` directly without a role (no matching
    `agents/<agent_label>/` directory) still gets the console line, just
    no persisted file — this function never creates a new top-level agent
    directory on its own.
    """
    line = f"[{datetime.now().strftime('%H:%M:%S')}] [{agent_label}] {message}"
    print(line)
    try:
        agent_dir = Path(project_root) / "agents" / agent_label
        if not agent_dir.is_dir():
            return
        runtime_dir = agent_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with open(runtime_dir / "session.log", "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
