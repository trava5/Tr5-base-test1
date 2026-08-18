from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .agent_profile import Agent
from .contract_workflow import (
    Contract,
    ContractStore,
    MemoryUpdate,
    parse_json_response,
    render_contract_summary,
)
from .git_ops import commit_and_push
from tools.discovery_engine.generate_current_state import render_diff_markdown, run_discovery_scan

# Tr5-base decision 9: the reviewer and the programmer get a brand-new
# thread for every single call — no carryover between contracts, and none
# between a contract's own Architecture Review and its later Implementation
# Review either. A live `Agent` cannot provide that on its own (asking it
# twice just continues the same underlying conversation) — so every
# function below that actually needs to talk to the reviewer or the
# programmer takes a zero-argument factory instead of a constructed
# `Agent`, and constructs (then closes) a fresh one for that one call. Only
# the architect is a long-lived `Agent`, passed in directly — decision 9
# explicitly allows it to stay naturally continuous within one
# `chat_architect.py` session.
AgentFactory = Callable[[], Agent]


def create_contract(
    architect: Agent,
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
    task: str,
) -> None:
    """Runs a discovery scan before the architect drafts anything (Tr5-base
    decision 3's "structural trigger") — memory/CURRENT_STATE.md is freshly
    regenerated, so `create_contract.md`'s instruction to read it before
    filling in "current_state" reads current data, not something stale."""
    run_discovery_scan(store.project_root)
    response = architect.run_command("create_contract", task=task)
    data = parse_json_response(response, required_keys=("title", "points"))
    contract = store.create_contract(
        title=str(data["title"]),
        points=list(data["points"]),
        purpose=str(data.get("purpose", "")),
        intent=str(data.get("intent", "")),
        current_state=str(data.get("current_state", "")),
        inputs=str(data.get("inputs", "")),
        outputs=str(data.get("outputs", "")),
        out_of_scope=str(data.get("out_of_scope", "")),
        future_evolution=str(data.get("future_evolution", "")),
        risk_level=str(data.get("risk_level", "standard")),
    )
    print(f"Created {store.path_for(contract.number).name} (DRAFT, risk: {contract.risk_level})")
    reviewed = run_architecture_review(reviewer_factory, store, contract.number)
    continue_pipeline(reviewer_factory, programmer_factory, store, reviewed)


def revise_contract(
    architect: Agent,
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
    number: int,
    task: str,
) -> None:
    run_discovery_scan(store.project_root)
    response = architect.run_command("create_contract", task=task)
    data = parse_json_response(response, required_keys=("title", "points"))
    store.revise_contract(
        number,
        title=str(data["title"]),
        points=list(data["points"]),
        purpose=str(data.get("purpose", "")),
        intent=str(data.get("intent", "")),
        current_state=str(data.get("current_state", "")),
        inputs=str(data.get("inputs", "")),
        outputs=str(data.get("outputs", "")),
        out_of_scope=str(data.get("out_of_scope", "")),
        future_evolution=str(data.get("future_evolution", "")),
        risk_level=data.get("risk_level"),
    )
    print(f"IMPLEMENTATION_CONTRACT_{number:04d} rewritten (DRAFT).")
    reviewed = run_architecture_review(reviewer_factory, store, number)
    continue_pipeline(reviewer_factory, programmer_factory, store, reviewed)


def continue_pipeline(
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
    contract: Contract,
) -> None:
    """Chains the automatic part of the pipeline after architecture review.

    Only proceeds if the contract passed architecture review
    (READY_FOR_PROGRAMMER). CHANGES_REQUESTED and REJECTED already stop at
    the architect/owner — nothing to chain. Commits checkpoint 1 (see
    ADR-019/ADR-030), then either continues straight through the programmer
    and the reviewer's implementation review (`risk_level == "standard"`),
    or pauses here and waits for an explicit `/proceed <n>` from the owner
    (`risk_level == "high"`, Tr5-base decision 7) — the same pause happens
    again after the programmer finishes, before the reviewer's
    implementation review runs. Every return to the architect/owner is a
    checkpoint, not a place to keep looping automatically (see ADR-018).
    """
    if contract.status != "READY_FOR_PROGRAMMER":
        return

    committed = commit_and_push(
        store.project_root, f"CONTRACT_{contract.number:04d}"
    )
    print(
        f"Committed and pushed: CONTRACT_{contract.number:04d}"
        if committed
        else "Nothing to commit before implementation."
    )

    if contract.risk_level == "high":
        print(
            f"IMPLEMENTATION_CONTRACT_{contract.number:04d} is high-risk; "
            f"pausing before implementation (Tr5-base decision 7). "
            f"Run /proceed {contract.number} when ready."
        )
        return

    _implement_and_review(reviewer_factory, programmer_factory, store, contract.number)


def proceed(
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
    number: int,
) -> None:
    """Resumes a high-risk contract paused by `continue_pipeline` (Tr5-base
    decision 7). Standard-risk contracts never pause, so this only does
    something meaningful for `risk_level == "high"`, at one of its two
    pause points: `READY_FOR_PROGRAMMER` (resumes implementation, then
    pauses again before review) or `READY_FOR_REVIEWER` (resumes review).
    Prints a message and does nothing if the contract is not at either
    point."""
    contract = store.load(number)
    if contract.status == "READY_FOR_PROGRAMMER":
        _implement_and_review(reviewer_factory, programmer_factory, store, number)
        return
    if contract.status == "READY_FOR_REVIEWER":
        _review_and_commit(reviewer_factory, store, number)
        return
    print(
        f"IMPLEMENTATION_CONTRACT_{number:04d} is not at a pause point "
        f"(status: {contract.status})."
    )


def _implement_and_review(
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
    number: int,
) -> None:
    implemented = implement_next(programmer_factory, store, number=number)
    if implemented is None:
        return

    committed = commit_and_push(
        store.project_root, f"CONTRACT_{implemented.number:04d} - IMPLEMENTED"
    )
    print(
        f"Committed and pushed: CONTRACT_{implemented.number:04d} - IMPLEMENTED"
        if committed
        else "Nothing to commit after implementation."
    )

    if implemented.risk_level == "high":
        print(
            f"IMPLEMENTATION_CONTRACT_{implemented.number:04d} is high-risk; "
            f"pausing before implementation review (Tr5-base decision 7). "
            f"Run /proceed {implemented.number} when ready."
        )
        return

    _review_and_commit(reviewer_factory, store, implemented.number)


def _review_and_commit(
    reviewer_factory: AgentFactory, store: ContractStore, number: int
) -> None:
    reviewed = run_implementation_review(reviewer_factory, store, number=number)
    if reviewed is None or reviewed.status != "APPROVED":
        return

    if reviewed.risk_level == "high":
        print(
            f"IMPLEMENTATION_CONTRACT_{number:04d} is APPROVED (high-risk) — "
            f"the REVIEWED commit is not pushed automatically (Tr5-base "
            f"decision 7). Run yourself, or use /commit {number}:\n"
            f"  git add -A && git commit -m \"CONTRACT_{number:04d} - REVIEWED\" "
            f"&& git push"
        )
        return

    committed = commit_and_push(
        store.project_root, f"CONTRACT_{number:04d} - REVIEWED"
    )
    print(
        f"Committed and pushed: CONTRACT_{number:04d} - REVIEWED"
        if committed
        else "Nothing to commit after review."
    )
    print(render_contract_summary(reviewed))


def commit_approved_contract(store: ContractStore, number: int) -> None:
    """Manual override for the third checkpoint (`- REVIEWED`, see
    ADR-030). For `standard`-risk contracts this is already auto-committed
    by `continue_pipeline`/`proceed` and normally finds nothing to commit;
    for `high`-risk contracts (Tr5-base decision 7) this is how the owner
    actually pushes it."""
    contract = store.load(number)
    if contract.status != "APPROVED":
        print(
            f"IMPLEMENTATION_CONTRACT_{number:04d} is not APPROVED "
            f"(status: {contract.status}); not committing."
        )
        return
    committed = commit_and_push(
        store.project_root, f"CONTRACT_{number:04d} - REVIEWED"
    )
    print(
        f"Committed and pushed: CONTRACT_{number:04d} - REVIEWED"
        if committed
        else "Nothing to commit."
    )
    print(render_contract_summary(contract))


def run_architecture_review(
    reviewer_factory: AgentFactory, store: ContractStore, number: int
) -> Contract:
    """Constructs a brand-new reviewer thread for this one call and closes
    it afterward (Tr5-base decision 9) — never a thread reused from a prior
    contract's review, and never the same thread this same contract's own
    later Implementation Review will use."""
    path = store.path_for(number)
    with reviewer_factory() as reviewer:
        response = reviewer.run_command(
            "architecture_review",
            contract_path=path.relative_to(store.project_root).as_posix(),
            contract_content=path.read_text(encoding="utf-8"),
        )
    data = parse_json_response(response, required_keys=("verdict", "findings"))
    updates = [
        MemoryUpdate(path=str(item["path"]), text=str(item["text"]))
        for item in data.get("memory_updates", [])
    ]
    contract = store.record_architecture_review(
        number,
        verdict=str(data["verdict"]),
        findings=str(data["findings"]),
        risk_level=data.get("risk_level"),
        memory_updates=updates,
    )
    print(
        f"Architecture review: {contract.status} (risk: {contract.risk_level}); "
        f"handed off to {contract.handoff_to}."
    )
    return contract


def implement_next(
    programmer_factory: AgentFactory, store: ContractStore, *, number: int | None = None
) -> Contract | None:
    """Constructs a brand-new programmer thread for this one call and
    closes it afterward (Tr5-base decision 9) — never a thread reused
    across contracts."""
    if number is None:
        queued = store.next_for_programmer()
        if queued is None:
            print("Programmer has no contract ready.")
            return None
        number = queued.number

    contract = store.claim(number)
    path = store.path_for(contract.number)
    with programmer_factory() as programmer:
        response = programmer.run_command(
            "implement_contract",
            contract_path=path.relative_to(store.project_root).as_posix(),
            contract_content=path.read_text(encoding="utf-8"),
        )
    data = parse_json_response(response, required_keys=("summary", "notes"))
    contract = store.record_programmer_result(
        contract.number,
        summary=str(data["summary"]),
        notes=list(data["notes"]),
        tests=list(data.get("tests", [])),
    )
    print(f"IMPLEMENTATION_CONTRACT_{contract.number:04d} handed off to the reviewer for implementation review.")
    return contract


def run_implementation_review(
    reviewer_factory: AgentFactory, store: ContractStore, *, number: int | None = None
) -> Contract | None:
    """Runs implementation review via a brand-new reviewer thread (Tr5-base
    decision 1 — the reviewer holds both review gates, not the architect;
    decision 9 — this thread has no memory of this same contract's own
    earlier Architecture Review, or of any other contract). Feeds it the
    discovery-engine diff between the pre-implementation and
    post-implementation snapshots (Tr5-base decision 3), so the Out of
    Scope check is grounded in a mechanical added/removed/changed list
    instead of the reviewer eyeballing `git diff` itself."""
    if number is None:
        queued = store.next_for_implementation_review()
        if queued is None:
            print("Reviewer has no contract ready for implementation review.")
            return None
        number = queued.number

    diff = store.out_of_scope_diff(number)
    diff_text = (
        render_diff_markdown(diff)
        if diff is not None
        else "No discovery snapshot available for this contract — check the "
        "actual diff yourself (e.g. `git diff`)."
    )

    path = store.path_for(number)
    with reviewer_factory() as reviewer:
        response = reviewer.run_command(
            "review_contract",
            contract_path=path.relative_to(store.project_root).as_posix(),
            contract_content=path.read_text(encoding="utf-8"),
            out_of_scope_diff=diff_text,
        )
    data = parse_json_response(
        response,
        required_keys=(
            "approved",
            "summary",
            "reviews",
            "out_of_scope_ok",
            "out_of_scope_findings",
        ),
    )
    updates = [
        MemoryUpdate(path=str(item["path"]), text=str(item["text"]))
        for item in data.get("memory_updates", [])
    ]
    updated = store.record_implementation_review(
        number,
        approved=bool(data["approved"]),
        summary=str(data["summary"]),
        reviews=list(data["reviews"]),
        out_of_scope_ok=bool(data["out_of_scope_ok"]),
        out_of_scope_findings=str(data["out_of_scope_findings"]),
        memory_updates=updates,
    )
    print(
        f"IMPLEMENTATION_CONTRACT_{number:04d}: {updated.status}; "
        f"handed off to {updated.handoff_to}."
    )
    return updated


def print_status(store: ContractStore) -> None:
    contracts = store.list_contracts()
    if not contracts:
        print("No contracts yet.")
        return
    for contract in contracts:
        print(
            f"IMPLEMENTATION_CONTRACT_{contract.number:04d} | {contract.status:<28} | "
            f"risk: {contract.risk_level:<8} | handoff: {contract.handoff_to:<10} | "
            f"{contract.title}"
        )


def show_inbox(project_root: Path, agent: str) -> None:
    path = project_root / "agents" / agent / "INBOX.md"
    if agent == "owner":
        path = project_root / "contracts" / "OWNER_INBOX.md"
    if not path.is_file():
        print(f"Inbox {agent!r} is empty.")
        return
    print(path.read_text(encoding="utf-8"))


def status_text(store: ContractStore) -> str:
    """Plain-text contract queue, for grounding the architect's opening
    greeting in real data instead of a guess (see ADR-021). Delegates to
    `ContractStore.render_queue_summary()`, the same rendering the
    generated `WORKING_STATE.md` uses (Tr5-base decision 10) — one place
    computes this."""
    return store.render_queue_summary()


def opening_briefing(store: ContractStore, project_root: Path) -> str:
    """Builds the first message sent to the architect when a session starts.

    Grounds the greeting in the actual contract queue and the architect's
    own inbox, rather than letting the model guess what might be pending
    (see PRINCIPLES.md P4/P6 and ADR-021).
    """
    inbox_path = project_root / "agents" / "architect" / "INBOX.md"
    inbox_text = (
        inbox_path.read_text(encoding="utf-8").strip()
        if inbox_path.is_file()
        else ""
    )
    return (
        "The owner just started a new session with you. Greet them, briefly "
        "mention anything in the contract queue or your inbox that needs "
        "attention, and ask what is on the agenda today.\n\n"
        f"Current contract queue:\n{status_text(store)}\n\n"
        f"Your inbox:\n{inbox_text or '(empty)'}"
    )


# --- Conversational actions (ADR-040) ---------------------------------
#
# Before this, the only way to actually move the pipeline forward was
# typing the exact slash command (`/new`, `/revise <n> <topic>`, ...) —
# plain conversation (`architect.ask(...)`) never had any side effect on
# the contract store, no matter how clearly the owner's message expressed
# intent to proceed. `agents/architect/ROLE.md` now instructs the
# architect to signal a confirmed, unambiguous intent by appending a
# fenced ```action block to an otherwise plain-text reply; the three
# functions below are what `chat_architect.py` uses to detect that block,
# describe it back to the owner in the same vocabulary as the slash
# commands, and — only after the owner explicitly confirms a second time
# — dispatch to the *exact same* pipeline function the matching slash
# command already calls. No pipeline behavior is duplicated here, only a
# second path to trigger it; the actual mutation is still gated behind an
# explicit, code-enforced confirmation, not merely the model's own
# judgment that it was already agreed (per PRINCIPLES.md P4 — a text
# instruction alone is not a structural safeguard).

_ACTION_BLOCK_RE = re.compile(r"```action\s*(\{.*?\})\s*```", re.DOTALL)

_ACTION_DESCRIPTIONS: dict[str, Callable[[dict[str, Any]], str]] = {
    "new_contract": lambda a: f"/new {a['topic']}",
    "revise_contract": lambda a: f"/revise {a['number']} {a['topic']}",
    "work": lambda a: f"/work {a['number']}" if a.get("number") is not None else "/work",
    "review": lambda a: f"/review {a['number']}" if a.get("number") is not None else "/review",
    "proceed": lambda a: f"/proceed {a['number']}",
    "commit": lambda a: f"/commit {a['number']}",
}


def parse_conversational_action(response: str) -> tuple[str, dict[str, Any] | None]:
    """Extracts an optional trailing ```action fenced JSON block from a
    plain conversational architect reply (see `agents/architect/ROLE.md`'s
    "Conversational actions").

    Returns `(display_text, action)`: `display_text` has the block
    removed — it is never shown raw to the owner — and `action` is the
    parsed dict, or `None` if no block is present. A block that is
    present but not valid JSON (or not a JSON object with a `"type"`
    field) is treated the same as "no action": the original response is
    returned unmodified, block and all, rather than silently discarding
    text or raising over a malformed one-off response.
    """
    match = _ACTION_BLOCK_RE.search(response)
    if not match:
        return response, None
    try:
        action = json.loads(match.group(1))
    except json.JSONDecodeError:
        return response, None
    if not isinstance(action, dict) or "type" not in action:
        return response, None
    display_text = (response[: match.start()] + response[match.end() :]).strip()
    return display_text, action


def describe_conversational_action(action: dict[str, Any]) -> str:
    """Human-readable, slash-command-equivalent description of a detected
    conversational action, shown in the confirmation prompt
    `chat_architect.py` prints before calling
    `dispatch_conversational_action` — ties the new conversational path
    back to the exact vocabulary `README.md`/`/help` already document,
    instead of describing what is about to run in novel wording.

    Raises `ValueError` for an unknown `"type"` or a missing required
    field — `chat_architect.py` treats that as "cannot act on this,"
    the same as if no action had been detected at all.
    """
    action_type = action.get("type")
    builder = _ACTION_DESCRIPTIONS.get(action_type)
    if builder is None:
        raise ValueError(f"Unknown conversational action type: {action_type!r}")
    try:
        return builder(action)
    except KeyError as error:
        raise ValueError(
            f"Conversational action {action_type!r} is missing required field: {error}"
        ) from error


def dispatch_conversational_action(
    action: dict[str, Any],
    *,
    architect: Agent,
    reviewer_factory: AgentFactory,
    programmer_factory: AgentFactory,
    store: ContractStore,
) -> None:
    """Runs the pipeline function a confirmed conversational action maps
    to — the exact same functions `chat_architect.py`'s `/new`, `/revise`,
    `/work`, `/review`, `/proceed`, and `/commit` handlers already call,
    so a conversationally-triggered action and its slash-command
    equivalent are, from this point on, indistinguishable: no pipeline
    logic is duplicated here, only routed.

    Only ever called after the owner has explicitly confirmed (see
    `chat_architect.py`) — this function performs no confirmation of its
    own and assumes the caller already got one.
    """
    action_type = action.get("type")
    if action_type == "new_contract":
        create_contract(
            architect, reviewer_factory, programmer_factory, store, str(action["topic"])
        )
    elif action_type == "revise_contract":
        revise_contract(
            architect,
            reviewer_factory,
            programmer_factory,
            store,
            int(action["number"]),
            str(action["topic"]),
        )
    elif action_type == "work":
        number = action.get("number")
        implement_next(programmer_factory, store, number=int(number) if number is not None else None)
    elif action_type == "review":
        number = action.get("number")
        run_implementation_review(
            reviewer_factory, store, number=int(number) if number is not None else None
        )
    elif action_type == "proceed":
        proceed(reviewer_factory, programmer_factory, store, int(action["number"]))
    elif action_type == "commit":
        commit_approved_contract(store, int(action["number"]))
    else:
        raise ValueError(f"Unknown conversational action type: {action_type!r}")
