from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from tools.discovery_engine.generate_current_state import (
    diff_scans,
    load_snapshot,
    save_snapshot,
    scan_repository,
)


ContractStatus = Literal[
    "DRAFT",
    "ARCHITECTURE_CHANGES_REQUESTED",
    "REJECTED",
    "READY_FOR_PROGRAMMER",
    "IN_PROGRESS",
    # Renamed from READY_FOR_ARCHITECT_REVIEW (Tr5-base decision 1): the
    # reviewer now holds Implementation Review, never the architect.
    "READY_FOR_REVIEWER",
    "CHANGES_REQUESTED",
    "APPROVED",
]

PointStatus = Literal["PENDING", "IMPLEMENTED", "APPROVED", "CHANGES_REQUESTED"]

ArchitectureVerdict = Literal["ACCEPTED", "REJECTED", "CHANGES_REQUESTED"]

# Per-contract risk flag (Tr5-base decision 7): "standard" auto-chains the
# pipeline through both review gates with no pause; "high" (real
# credentials/external systems/native-hardware libraries) pauses for the
# owner at each checkpoint instead. Set by the architect at creation, may
# be escalated (never downgraded) by the reviewer during architecture
# review.
RiskLevel = Literal["standard", "high"]

CONTRACT_FILE_RE = re.compile(r"^IMPLEMENTATION_CONTRACT_(\d{4})\.md$")
META_RE = re.compile(
    r"<!-- CONTRACT-META\s*(\{.*?\})\s*CONTRACT-META -->",
    re.DOTALL,
)

ALLOWED_MEMORY_TARGETS = (
    re.compile(r"^memory/[A-Za-z0-9_.-]+\.md$"),
    re.compile(r"^agents/[A-Za-z0-9_-]+/MEMORY\.md$"),
    re.compile(r"^PRINCIPLES\.md$"),
)
# `agents/<agent>/WORKING_STATE.md` is deliberately NOT an allowed
# memory_updates target (Tr5-base decision 10): it is a generated
# artifact (see ContractStore.refresh_working_state()), regenerated on
# every save() from the live contract queue — a manual write here would
# just be overwritten on the next state change.


@dataclass
class ContractPoint:
    number: int
    assignment: str
    acceptance_criteria: list[str] = field(default_factory=list)
    programmer_note: str = ""
    programmer_note_author: str = ""
    programmer_note_at: str = ""
    programmer_files: list[str] = field(default_factory=list)
    programmer_tests: list[str] = field(default_factory=list)
    # Implementation Review finding for this point. Renamed from
    # `architect_review` (Tr5-base decision 1): the reviewer holds both
    # review gates now, the architect no longer reviews its own contract's
    # implementation.
    reviewer_note: str = ""
    reviewer_note_author: str = ""
    reviewer_note_at: str = ""
    status: PointStatus = "PENDING"


@dataclass
class Contract:
    number: int
    title: str
    status: ContractStatus
    created_by: str
    assigned_to: str
    handoff_to: str
    created_at: str
    updated_at: str
    points: list[ContractPoint]
    implementer: str = "programmer"
    reviewer: str = "reviewer"
    # Tr5-base decision 7: gates full auto-chaining ("standard") vs.
    # step-by-step owner pacing ("high") in the pipeline layer.
    risk_level: RiskLevel = "standard"
    # Why (human-readable architectural intent) — separate from the What (points).
    purpose: str = ""
    intent: str = ""
    current_state: str = ""
    inputs: str = ""
    outputs: str = ""
    out_of_scope: str = ""
    future_evolution: str = ""
    lessons_learned: str = ""
    # Append-only round history for both review gates. Never overwritten,
    # only appended to — a round represents one verdict at one point in time.
    architecture_review_rounds: list[dict[str, Any]] = field(default_factory=list)
    completion_notes: str = ""
    implementation_review_rounds: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryUpdate:
    path: str
    text: str


class ContractStore:
    """File-backed contract queue and handoff between agents.

    Pipeline (two review gates, three roles; Tr5-base decision 1 changes
    who holds the second gate relative to bod_zero's original design —
    the reviewer now holds both, never the architect):

        create_contract (architect+owner) -> DRAFT            (-> reviewer)
        record_architecture_review (reviewer, may escalate risk_level):
            ACCEPTED             -> READY_FOR_PROGRAMMER      (-> implementer)
            CHANGES_REQUESTED    -> ARCHITECTURE_CHANGES_REQUESTED (-> architect)
            REJECTED             -> REJECTED                  (-> architect)
        revise_contract (architect, only from ARCHITECTURE_CHANGES_REQUESTED)
            -> DRAFT                                          (-> reviewer)
        claim (programmer)          -> IN_PROGRESS
        record_programmer_result    -> READY_FOR_REVIEWER (-> reviewer)
        record_implementation_review (reviewer; out_of_scope_ok/
        out_of_scope_findings are required, not optional):
            APPROVED (all points, out_of_scope_ok) -> APPROVED (-> owner)
            otherwise                                -> CHANGES_REQUESTED (-> implementer)

    Once both gates return a verdict, architect+owner do one final,
    non-gating pass for strategic fit — not tracked as contract state,
    since nothing about the contract itself changes as a result of it.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.contracts_dir = self.project_root / "contracts"
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    def create_contract(
        self,
        title: str,
        points: list[dict[str, Any]],
        *,
        purpose: str = "",
        intent: str = "",
        current_state: str = "",
        inputs: str = "",
        outputs: str = "",
        out_of_scope: str = "",
        future_evolution: str = "",
        created_by: str = "architect",
        implementer: str = "programmer",
        reviewer: str = "reviewer",
        risk_level: RiskLevel | str = "standard",
    ) -> Contract:
        if not title.strip():
            raise ValueError("A contract must have a title.")
        risk_level_upper = str(risk_level).lower()
        if risk_level_upper not in {"standard", "high"}:
            raise ValueError(f"Invalid risk_level: {risk_level!r}. Must be 'standard' or 'high'.")

        number = self.next_number()
        now = _timestamp()
        contract_points = _build_points(points)

        contract = Contract(
            number=number,
            title=title.strip(),
            status="DRAFT",
            created_by=created_by,
            assigned_to=reviewer,
            handoff_to=reviewer,
            created_at=now,
            updated_at=now,
            points=contract_points,
            implementer=implementer,
            reviewer=reviewer,
            risk_level=risk_level_upper,  # type: ignore[arg-type]
            purpose=purpose.strip(),
            intent=intent.strip(),
            current_state=current_state.strip(),
            inputs=inputs.strip(),
            outputs=outputs.strip(),
            out_of_scope=out_of_scope.strip(),
            future_evolution=future_evolution.strip(),
        )
        self.save(contract)
        return contract

    def revise_contract(
        self,
        number: int,
        title: str,
        points: list[dict[str, Any]],
        *,
        purpose: str = "",
        intent: str = "",
        current_state: str = "",
        inputs: str = "",
        outputs: str = "",
        out_of_scope: str = "",
        future_evolution: str = "",
        risk_level: RiskLevel | str | None = None,
    ) -> Contract:
        """Rewrite the requirements of a contract returned by the reviewer.

        Only allowed in ARCHITECTURE_CHANGES_REQUESTED — before a contract is
        accepted, no permanent history exists yet (no implementation, no
        inserted annotations), so rewriting the requirements does not violate
        the append-only rule. The history of past architecture review rounds
        (`architecture_review_rounds`) is never cleared. After revision the
        contract returns to DRAFT and is handed back to the reviewer.

        `risk_level` follows the same escalation-only rule as
        `record_architecture_review` (Tr5-base decision 7 — "never
        downgraded back to standard by anyone"): omitting it leaves the
        current value unchanged (a prior escalation to "high" is not
        silently lost on revision), and passing `"standard"` explicitly
        on a contract already `"high"` is a no-op, not a downgrade — there
        is no code path, silent or explicit, that lowers risk_level.
        """
        contract = self.load(number)
        if contract.status != "ARCHITECTURE_CHANGES_REQUESTED":
            raise ValueError(
                f"Contract {number:04d} cannot be edited in status {contract.status}."
            )
        if not title.strip():
            raise ValueError("A contract must have a title.")

        contract.title = title.strip()
        contract.points = _build_points(points)
        contract.purpose = purpose.strip()
        contract.intent = intent.strip()
        contract.current_state = current_state.strip()
        contract.inputs = inputs.strip()
        contract.outputs = outputs.strip()
        contract.out_of_scope = out_of_scope.strip()
        contract.future_evolution = future_evolution.strip()
        if risk_level is not None:
            risk_level_upper = str(risk_level).lower()
            if risk_level_upper not in {"standard", "high"}:
                raise ValueError(
                    f"Invalid risk_level: {risk_level!r}. Must be 'standard' or 'high'."
                )
            if risk_level_upper == "high":
                contract.risk_level = "high"
        contract.status = "DRAFT"
        contract.assigned_to = contract.reviewer
        contract.handoff_to = contract.reviewer
        self.save(contract)
        return contract

    def next_number(self) -> int:
        numbers = []
        for path in self.contracts_dir.glob("IMPLEMENTATION_CONTRACT_*.md"):
            match = CONTRACT_FILE_RE.match(path.name)
            if match:
                numbers.append(int(match.group(1)))
        return max(numbers, default=0) + 1

    def path_for(self, number: int) -> Path:
        return self.contracts_dir / f"IMPLEMENTATION_CONTRACT_{number:04d}.md"

    def save(self, contract: Contract) -> Path:
        contract.updated_at = _timestamp()
        path = self.path_for(contract.number)
        path.write_text(render_contract(contract), encoding="utf-8")
        self.refresh_working_state()
        return path

    def render_queue_summary(self) -> str:
        """Plain-text contract queue: status, risk, handoff, title for
        every contract. Single source of truth for both the architect's
        opening briefing (`pipeline.status_text()`) and the generated
        `WORKING_STATE.md` (`refresh_working_state()`, Tr5-base
        decision 10) — one place computes this, nothing else duplicates
        it."""
        contracts = self.list_contracts()
        if not contracts:
            return "No contracts yet."
        return "\n".join(
            f"IMPLEMENTATION_CONTRACT_{c.number:04d}: {c.status} (risk: {c.risk_level}) "
            f"(handed off to {c.handoff_to}) — {c.title}"
            for c in contracts
        )

    def refresh_working_state(self) -> Path:
        """Regenerates `agents/architect/WORKING_STATE.md` from the live
        contract queue (Tr5-base decision 10) — a generated artifact,
        never agent-authored. Called automatically by `save()`, so it can
        never drift the way an agent-proposed `memory_update` to this path
        could (that path is disallowed now — see `ALLOWED_MEMORY_TARGETS`).
        Only the architect has this file loaded (`load_working_state:
        true`); the reviewer and programmer don't (Tr5-base decision 9 —
        they carry no standing state between fresh-thread calls, so a
        working-state view would have nothing to serve)."""
        path = self.project_root / "agents" / "architect" / "WORKING_STATE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Current Working State\n\n"
            "Generated automatically from the live contract queue on every "
            "state change (Tr5-base decision 10) — do not edit by hand, "
            "edits are overwritten on the next transition.\n\n"
            f"{self.render_queue_summary()}\n",
            encoding="utf-8",
        )
        return path

    def load(self, number: int) -> Contract:
        path = self.path_for(number)
        if not path.is_file():
            raise FileNotFoundError(f"Contract does not exist: {path}")
        return parse_contract(path.read_text(encoding="utf-8"))

    def list_contracts(
        self,
        *,
        assigned_to: str | None = None,
        statuses: set[str] | None = None,
    ) -> list[Contract]:
        contracts: list[Contract] = []
        for path in sorted(self.contracts_dir.glob("IMPLEMENTATION_CONTRACT_*.md")):
            match = CONTRACT_FILE_RE.match(path.name)
            if not match:
                continue
            contract = self.load(int(match.group(1)))
            if assigned_to and contract.handoff_to != assigned_to:
                continue
            if statuses and contract.status not in statuses:
                continue
            contracts.append(contract)
        return contracts

    def next_for_architecture_review(self) -> Contract | None:
        contracts = self.list_contracts(
            assigned_to="reviewer",
            statuses={"DRAFT"},
        )
        return contracts[0] if contracts else None

    def next_for_revision(self) -> Contract | None:
        contracts = self.list_contracts(
            assigned_to="architect",
            statuses={"ARCHITECTURE_CHANGES_REQUESTED"},
        )
        return contracts[0] if contracts else None

    def next_for_programmer(self) -> Contract | None:
        contracts = self.list_contracts(
            assigned_to="programmer",
            statuses={"READY_FOR_PROGRAMMER", "CHANGES_REQUESTED"},
        )
        return contracts[0] if contracts else None

    def next_for_implementation_review(self) -> Contract | None:
        contracts = self.list_contracts(
            assigned_to="reviewer",
            statuses={"READY_FOR_REVIEWER"},
        )
        return contracts[0] if contracts else None

    def record_architecture_review(
        self,
        number: int,
        *,
        verdict: ArchitectureVerdict | str,
        findings: str,
        memory_updates: list[MemoryUpdate] | None = None,
        from_agent: str = "reviewer",
        risk_level: RiskLevel | str | None = None,
    ) -> Contract:
        """`risk_level` lets the reviewer escalate a contract to "high" here
        if it spots real-system/credential/hardware exposure the architect
        did not flag at creation (Tr5-base decision 7) — a genuine use of
        the reviewer's independence, not a rubber stamp on the architect's
        own risk call. Only escalation is supported here: passing
        "standard" on a contract already flagged "high" is a no-op, not a
        downgrade — lowering risk back down is not this call's job.
        """
        contract = self.load(number)
        if contract.status != "DRAFT":
            raise ValueError(
                f"Architecture review can only be recorded in status DRAFT, "
                f"currently {contract.status}."
            )
        verdict_upper = str(verdict).upper()
        if verdict_upper not in {"ACCEPTED", "REJECTED", "CHANGES_REQUESTED"}:
            raise ValueError(f"Invalid architecture review verdict: {verdict!r}.")
        findings_text = findings.strip()
        if not findings_text:
            raise ValueError("Architecture review must include findings.")
        if risk_level is not None:
            risk_level_upper = str(risk_level).lower()
            if risk_level_upper not in {"standard", "high"}:
                raise ValueError(
                    f"Invalid risk_level: {risk_level!r}. Must be 'standard' or 'high'."
                )
            if risk_level_upper == "high":
                contract.risk_level = "high"

        round_number = len(contract.architecture_review_rounds) + 1
        contract.architecture_review_rounds.append(
            {
                "round": round_number,
                "date": _timestamp(),
                "verdict": verdict_upper,
                "reviewer": from_agent,
                "findings": findings_text,
            }
        )

        if verdict_upper == "ACCEPTED":
            contract.status = "READY_FOR_PROGRAMMER"
            contract.assigned_to = contract.implementer
            contract.handoff_to = contract.implementer
            event = "Contract passed architecture review and is ready for implementation."
        elif verdict_upper == "CHANGES_REQUESTED":
            contract.status = "ARCHITECTURE_CHANGES_REQUESTED"
            contract.assigned_to = contract.created_by
            contract.handoff_to = contract.created_by
            event = "Architecture review requires the contract to be revised (see revise_contract)."
        else:
            contract.status = "REJECTED"
            contract.assigned_to = contract.created_by
            contract.handoff_to = contract.created_by
            event = "Contract was rejected in architecture review."

        self.save(contract)

        for update in memory_updates or []:
            self.append_memory(update, source=f"IMPLEMENTATION_CONTRACT_{number:04d}")

        self.notify(
            to_agent=contract.handoff_to,
            from_agent=from_agent,
            contract=contract,
            event=event,
        )
        return contract

    def claim(self, number: int, *, agent: str = "programmer") -> Contract:
        """Claims a contract for `agent`, transitioning it to `IN_PROGRESS`.

        Re-claiming a contract already `IN_PROGRESS` and assigned to this
        same `agent` is allowed and is a no-op status-wise (see ADR-041):
        `claim()` persists `IN_PROGRESS` immediately, before the caller's
        actual work (e.g. `implement_next()`'s call to the programmer)
        runs — if that later step fails (a network error, an invalid
        response, anything), the contract was previously left stranded in
        `IN_PROGRESS` with no valid transition back to a claimable status,
        requiring a manual file edit to recover. This is safe specifically
        because of Tr5-base decision 9: `agent` gets a brand-new, stateless
        thread for every single call, so there is no genuinely in-flight
        work an already-`IN_PROGRESS` status could be protecting — a
        second `claim()` call for the same agent is a retry of a call that
        never completed, not a conflict with concurrent work. The
        discovery "pre" snapshot is refreshed either way, so a retry still
        diffs against the repository's actual current state.
        """
        contract = self.load(number)
        if contract.handoff_to != agent:
            raise ValueError(
                f"Contract {number:04d} is handed off to agent {contract.handoff_to!r}, "
                f"not {agent!r}."
            )
        already_claimed = contract.status == "IN_PROGRESS" and contract.assigned_to == agent
        if not already_claimed and contract.status not in {"READY_FOR_PROGRAMMER", "CHANGES_REQUESTED"}:
            raise ValueError(
                f"Contract {number:04d} cannot be claimed in status {contract.status}."
            )
        if not already_claimed:
            contract.status = "IN_PROGRESS"
            contract.assigned_to = agent
            contract.handoff_to = agent
            self.save(contract)
        self._save_discovery_snapshot(number, "pre")
        return contract

    def _discovery_snapshot_path(self, number: int, stage: str) -> Path:
        return self.project_root / "contracts" / ".discovery" / f"{number:04d}_{stage}.json"

    def _save_discovery_snapshot(self, number: int, stage: str) -> None:
        """Snapshots the repository for later diffing (Tr5-base decision
        3) — "pre" when the programmer claims a contract, "post" when it
        hands back to the reviewer. Best-effort: a scan/write failure must
        never block the actual contract workflow over a discovery-tool
        problem, so it is swallowed here — `out_of_scope_diff()` falls
        back to `None` (no snapshot available) rather than raising.
        """
        try:
            artifacts = scan_repository(self.project_root)
            save_snapshot(self._discovery_snapshot_path(number, stage), artifacts)
        except OSError:
            pass

    def out_of_scope_diff(self, number: int) -> dict[str, list[str]] | None:
        """Diffs the "pre"/"post" discovery snapshots for a contract
        (Tr5-base decision 3), feeding the reviewer's Implementation
        Review Out of Scope check. Returns `None` if either snapshot is
        missing (e.g. `claim()` ran before this feature existed, or a
        snapshot failed to save) — the caller falls back to asking the
        reviewer to check manually rather than failing the review.

        The contract's own `.md` file is excluded from "changed" — it
        always changes between the two snapshots (the programmer's own
        notes are written into it), which is expected bookkeeping, not a
        signal the reviewer needs to see repeated on every single review.
        """
        pre_path = self._discovery_snapshot_path(number, "pre")
        post_path = self._discovery_snapshot_path(number, "post")
        if not pre_path.is_file() or not post_path.is_file():
            return None
        diff = diff_scans(load_snapshot(pre_path), load_snapshot(post_path))
        own_contract_path = self.path_for(number).relative_to(self.project_root).as_posix()
        diff["changed"] = [path for path in diff["changed"] if path != own_contract_path]
        return diff

    def record_programmer_result(
        self,
        number: int,
        *,
        summary: str,
        notes: list[dict[str, Any]],
        tests: list[str] | None = None,
        from_agent: str = "programmer",
        to_agent: str = "reviewer",
    ) -> Contract:
        contract = self.load(number)
        if contract.status != "IN_PROGRESS":
            raise ValueError(
                f"Programmer output can only be recorded in status IN_PROGRESS, "
                f"currently {contract.status}."
            )

        try:
            by_number = {int(item["point"]): item for item in notes}
        except KeyError as error:
            raise ValueError(
                f"Every programmer note must include a 'point' number. Missing key: {error}"
            ) from error
        missing = [point.number for point in contract.points if point.number not in by_number]
        if missing:
            raise ValueError(
                "The programmer must provide a note for every point. Missing points: "
                + ", ".join(map(str, missing))
            )

        global_tests = [str(item).strip() for item in (tests or []) if str(item).strip()]
        note_at = _timestamp()
        for point in contract.points:
            raw = by_number[point.number]
            note = str(raw.get("note", "")).strip()
            if not note:
                raise ValueError(f"Programmer note for point {point.number} is empty.")
            point.programmer_note = note
            point.programmer_note_author = from_agent
            point.programmer_note_at = note_at
            point.programmer_files = [
                str(item).strip() for item in raw.get("files", []) if str(item).strip()
            ]
            point.programmer_tests = [
                str(item).strip() for item in raw.get("tests", []) if str(item).strip()
            ] or global_tests
            point.status = "IMPLEMENTED"

        contract.completion_notes = summary.strip()
        contract.status = "READY_FOR_REVIEWER"
        contract.assigned_to = to_agent
        contract.handoff_to = to_agent
        self.save(contract)
        self._save_discovery_snapshot(number, "post")
        self.notify(
            to_agent=to_agent,
            from_agent=from_agent,
            contract=contract,
            event="Implementation is done and awaiting implementation review.",
        )
        return contract

    def record_implementation_review(
        self,
        number: int,
        *,
        approved: bool,
        summary: str,
        reviews: list[dict[str, Any]],
        out_of_scope_ok: bool,
        out_of_scope_findings: str,
        memory_updates: list[MemoryUpdate] | None = None,
        from_agent: str = "reviewer",
        to_agent: str | None = None,
    ) -> Contract:
        """`out_of_scope_ok`/`out_of_scope_findings` are required, not
        optional (Tr5-base decision 1): the reviewer must explicitly state
        whether anything beyond the contract's points was touched, not
        just whether the required points were done. `out_of_scope_ok=False`
        forces `CHANGES_REQUESTED` regardless of `approved` or the
        per-point statuses — an unexplained out-of-scope change is a
        defect on its own, not something the per-point verdicts alone
        would necessarily catch.
        """
        contract = self.load(number)
        if contract.status != "READY_FOR_REVIEWER":
            raise ValueError(
                f"Implementation review can only be recorded in status "
                f"READY_FOR_REVIEWER, currently {contract.status}."
            )
        to_agent = to_agent or contract.implementer
        out_of_scope_findings_text = out_of_scope_findings.strip()
        if not out_of_scope_findings_text:
            raise ValueError(
                "out_of_scope_findings must state what was checked, even when "
                "out_of_scope_ok is True."
            )

        try:
            by_number = {int(item["point"]): item for item in reviews}
        except KeyError as error:
            raise ValueError(
                f"Every review must include a 'point' number. Missing key: {error}"
            ) from error
        missing = [point.number for point in contract.points if point.number not in by_number]
        if missing:
            raise ValueError(
                "The reviewer must provide a review for every point. Missing points: "
                + ", ".join(map(str, missing))
            )

        any_changes = False
        note_at = _timestamp()
        for point in contract.points:
            raw = by_number[point.number]
            review = str(raw.get("review", "")).strip()
            status = str(raw.get("status", "")).upper()
            if status not in {"APPROVED", "CHANGES_REQUESTED"}:
                raise ValueError(
                    f"Invalid review status for point {point.number}: {status!r}."
                )
            if not review:
                raise ValueError(f"Review for point {point.number} is empty.")
            point.reviewer_note = review
            point.reviewer_note_author = from_agent
            point.reviewer_note_at = note_at
            point.status = status  # type: ignore[assignment]
            any_changes = any_changes or status == "CHANGES_REQUESTED"

        effective_approved = approved and not any_changes and out_of_scope_ok
        summary_text = summary.strip()
        round_number = len(contract.implementation_review_rounds) + 1
        contract.implementation_review_rounds.append(
            {
                "round": round_number,
                "date": _timestamp(),
                "verdict": "APPROVED" if effective_approved else "CHANGES_REQUESTED",
                "reviewer": from_agent,
                "summary": summary_text,
                "out_of_scope_ok": out_of_scope_ok,
                "out_of_scope_findings": out_of_scope_findings_text,
                "reviews": [
                    {"point": point.number, "status": point.status, "review": point.reviewer_note}
                    for point in contract.points
                ],
            }
        )
        contract.status = "APPROVED" if effective_approved else "CHANGES_REQUESTED"
        contract.assigned_to = "owner" if effective_approved else to_agent
        contract.handoff_to = "owner" if effective_approved else to_agent
        self.save(contract)

        for update in memory_updates or []:
            self.append_memory(update, source=f"IMPLEMENTATION_CONTRACT_{number:04d}")

        self.notify(
            to_agent=contract.handoff_to,
            from_agent=from_agent,
            contract=contract,
            event=(
                "Contract was approved."
                if effective_approved
                else "Implementation review requires further changes."
            ),
        )
        return contract

    def append_memory(self, update: MemoryUpdate, *, source: str) -> Path:
        relative = update.path.replace("\\", "/").strip("/")
        if not any(pattern.fullmatch(relative) for pattern in ALLOWED_MEMORY_TARGETS):
            raise ValueError(
                f"Disallowed memory target {update.path!r}. "
                "Only memory/*.md, agents/*/MEMORY.md, and "
                "PRINCIPLES.md are allowed."
            )
        text = update.text.strip()
        if not text:
            raise ValueError("A memory entry must not be empty.")

        path = (self.project_root / relative).resolve()
        if self.project_root not in path.parents:
            raise ValueError("Memory target is outside the project.")
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").rstrip() if path.exists() else ""
        entry = (
            f"## {_timestamp()} — {source}\n\n"
            f"{text}\n"
        )
        path.write_text(
            (existing + "\n\n" + entry).lstrip(),
            encoding="utf-8",
        )
        return path

    def notify(
        self,
        *,
        to_agent: str,
        from_agent: str,
        contract: Contract,
        event: str,
    ) -> Path:
        if to_agent == "owner":
            path = self.contracts_dir / "OWNER_INBOX.md"
        else:
            path = self.project_root / "agents" / to_agent / "INBOX.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").rstrip() if path.exists() else (
            f"# Inbox: {to_agent}\n"
        )
        relative_contract = self.path_for(contract.number).relative_to(self.project_root)
        entry = (
            f"\n\n## {_timestamp()} — IMPLEMENTATION_CONTRACT_{contract.number:04d}\n\n"
            f"- From: `{from_agent}`\n"
            f"- Status: `{contract.status}`\n"
            f"- File: `{relative_contract.as_posix()}`\n"
            f"- Message: {event}\n"
        )
        path.write_text(existing + entry, encoding="utf-8")
        return path


def _build_points(points: list[dict[str, Any]]) -> list[ContractPoint]:
    if not points:
        raise ValueError("A contract must contain at least one point.")
    contract_points: list[ContractPoint] = []
    for index, raw in enumerate(points, start=1):
        assignment = str(raw.get("assignment") or raw.get("description") or "").strip()
        if not assignment:
            raise ValueError(f"Point {index} has no assignment.")
        criteria = raw.get("acceptance_criteria", [])
        if not isinstance(criteria, list):
            raise ValueError(f"acceptance_criteria for point {index} must be a list.")
        contract_points.append(
            ContractPoint(
                number=index,
                assignment=assignment,
                acceptance_criteria=[str(item).strip() for item in criteria if str(item).strip()],
            )
        )
    return contract_points


def render_contract_summary(contract: Contract) -> str:
    """Short, human-readable recap of one contract's full round, printed to
    the console right after its final `- REVIEWED` checkpoint lands
    (Tr5-base decision 11). Motivated by the first real end-to-end test:
    with the pipeline able to pause on `high` risk, get interrupted by an
    unrelated environment failure (e.g. a git credential problem), or be
    walked through manually via `/work`/`/review`/`/commit`, there was no
    single point that confirmed "yes, this whole round finished, and here
    is what actually happened" without opening the contract file or
    running `/status`. A handful of lines, not the full contract."""
    lines = [
        f"--- IMPLEMENTATION_CONTRACT_{contract.number:04d} summary ---",
        contract.title,
        f"Risk: {contract.risk_level} | Final status: {contract.status}",
    ]

    if contract.architecture_review_rounds:
        latest = contract.architecture_review_rounds[-1]
        lines.append(
            f"Architecture Review: {latest['verdict']} "
            f"(round {latest['round']}, by {latest['reviewer']})"
        )

    approved_points = sum(1 for point in contract.points if point.status == "APPROVED")
    lines.append(f"Implementation: {approved_points}/{len(contract.points)} point(s) approved")

    files = sorted({f for point in contract.points for f in point.programmer_files})
    if files:
        lines.append(f"Files touched: {', '.join(files)}")

    if contract.implementation_review_rounds:
        latest = contract.implementation_review_rounds[-1]
        out_of_scope = "OK" if latest["out_of_scope_ok"] else "FLAGGED"
        lines.append(
            f"Implementation Review: {latest['verdict']} "
            f"(round {latest['round']}, by {latest['reviewer']}) | "
            f"Out of Scope: {out_of_scope}"
        )

    return "\n".join(lines)


def render_contract(contract: Contract) -> str:
    meta = json.dumps(asdict(contract), ensure_ascii=False, indent=2)
    lines: list[str] = [
        f"# IMPLEMENTATION_CONTRACT_{contract.number:04d}",
        "",
        f"Status: {contract.status}",
        "",
        "---",
        "",
        "# Workflow",
        "",
        f"- Created by: `{contract.created_by}`",
        f"- Reviewer (both review gates): `{contract.reviewer}`",
        f"- Implementer: `{contract.implementer}`",
        f"- Risk level: `{contract.risk_level}`",
        f"- Currently with: `{contract.assigned_to}`",
        f"- Handed off to: `{contract.handoff_to}`",
        f"- Created at: `{contract.created_at}`",
        f"- Updated at: `{contract.updated_at}`",
        "",
        "---",
        "",
        "# Title",
        "",
        contract.title,
        "",
        "---",
        "",
        "# Purpose",
        "",
        contract.purpose or "_Not filled in._",
        "",
        "---",
        "",
        "# Intent",
        "",
        contract.intent or "_Not filled in._",
        "",
        "---",
        "",
        "# Current State",
        "",
        contract.current_state or "_Not filled in._",
        "",
        "---",
        "",
        "# Inputs",
        "",
        contract.inputs or "_Not filled in._",
        "",
        "---",
        "",
        "# Outputs",
        "",
        contract.outputs or "_Not filled in._",
        "",
        "---",
        "",
        "# Functional Requirements",
        "",
    ]

    for point in contract.points:
        lines.extend(
            [
                f"## Point {point.number}",
                "",
                f"SHALL: {point.assignment}",
                "",
                "Acceptance criteria:",
            ]
        )
        if point.acceptance_criteria:
            lines.extend(f"- {item}" for item in point.acceptance_criteria)
        else:
            lines.append("- Not explicitly stated; the result must match the point's assignment.")

        lines.extend(
            [
                "",
                f"> Status: {point.status}",
                "",
                "Programmer note:",
                "",
            ]
        )
        if point.programmer_note:
            lines.append(f"_By `{point.programmer_note_author}`, {point.programmer_note_at}._")
            lines.append("")
            lines.append(point.programmer_note)
        else:
            lines.append("_Awaiting implementation._")
        lines.append("")
        if point.programmer_files:
            lines.append("Files touched:")
            lines.extend(f"- `{item}`" for item in point.programmer_files)
            lines.append("")
        if point.programmer_tests:
            lines.append("Tests:")
            lines.extend(f"- {item}" for item in point.programmer_tests)
            lines.append("")
        lines.append("Reviewer's implementation review for this point:")
        lines.append("")
        if point.reviewer_note:
            lines.append(f"_By `{point.reviewer_note_author}`, {point.reviewer_note_at}._")
            lines.append("")
            lines.append(point.reviewer_note)
        else:
            lines.append("_Awaiting review._")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "# Out of Scope",
            "",
            contract.out_of_scope or "_Not filled in._",
            "",
            "---",
            "",
            "# Acceptance Criteria",
            "",
            "Acceptance criteria are listed per point in the Functional "
            "Requirements section.",
            "",
            "---",
            "",
            "# Architecture Review",
            "",
        ]
    )
    if contract.architecture_review_rounds:
        for round_data in contract.architecture_review_rounds:
            lines.extend(
                [
                    f"### Round {round_data['round']} — {round_data['date']} — "
                    f"Verdict: {round_data['verdict']} — "
                    f"Reviewer: `{round_data.get('reviewer', 'reviewer')}`",
                    "",
                    round_data["findings"],
                    "",
                ]
            )
    else:
        lines.extend(["_Awaiting architecture review._", ""])

    lines.extend(
        [
            "---",
            "",
            "# Future Evolution",
            "",
            contract.future_evolution or "_Not filled in._",
            "",
            "---",
            "",
            "# Completion Notes",
            "",
            contract.completion_notes or "_Awaiting implementation._",
            "",
            "---",
            "",
            "# Implementation Review",
            "",
        ]
    )
    if contract.implementation_review_rounds:
        for round_data in contract.implementation_review_rounds:
            out_of_scope_ok = round_data.get("out_of_scope_ok")
            out_of_scope_label = (
                "OK" if out_of_scope_ok else "ISSUE FOUND" if out_of_scope_ok is not None else "N/A"
            )
            lines.extend(
                [
                    f"### Round {round_data['round']} — {round_data['date']} — "
                    f"Verdict: {round_data['verdict']} — "
                    f"Reviewer: `{round_data.get('reviewer', 'architect')}`",
                    "",
                    round_data["summary"],
                    "",
                    f"Out of Scope check: {out_of_scope_label} — "
                    f"{round_data.get('out_of_scope_findings', '_not recorded_')}",
                    "",
                ]
            )
    else:
        lines.extend(["_Awaiting implementation review._", ""])

    lines.extend(
        [
            "---",
            "",
            "# Lessons Learned",
            "",
            contract.lessons_learned or "_Not filled in._",
            "",
            "---",
            "",
            "<!-- CONTRACT-META",
            meta,
            "CONTRACT-META -->",
            "",
        ]
    )
    return "\n".join(lines)


def parse_contract(content: str) -> Contract:
    match = META_RE.search(content)
    if not match:
        raise ValueError("File does not contain CONTRACT-META.")
    data = json.loads(match.group(1))
    data["points"] = [ContractPoint(**item) for item in data["points"]]
    return Contract(**data)


def parse_json_response(
    text: str, *, required_keys: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Parse JSON from a plain response or from a ```json ... ``` block.

    On failure, the raised error includes a bounded diagnostic snippet of
    the actual response (see `_diagnostic_snippet`) — found missing during
    the first real end-to-end test: "The agent did not return valid JSON"
    on its own gave no way to tell prose-with-no-JSON-at-all apart from
    JSON truncated mid-generation, and the raw response was otherwise
    discarded the moment this exception propagated (see ADR-037).

    `required_keys` extends that same diagnosability to a second failure
    mode ADR-037 did not cover: JSON that parses fine but is missing a
    field a caller (`agents/pipeline.py`) is about to read unconditionally
    (`data["title"]`, `data["verdict"]`, ...). Without this check that
    missing field surfaced as a bare `KeyError` past this function's own
    error handling, with the raw response already out of scope by the time
    it propagated — the exact loss of diagnostic evidence ADR-037 fixed
    for invalid JSON, left open for valid-JSON-missing-field.

    A third case (ADR-042): a response that is neither cleanly fenced nor
    itself pure JSON, e.g. a leading sentence before an otherwise
    well-formed object ("Now creating the file per the contract.\n{...}"),
    with no ```` ``` ```` fence around it — every command template already
    asks for "only valid JSON", but that is a text instruction, not a
    structural guarantee a model actually follows it every time (see
    `PRINCIPLES.md` P4). `_extract_first_json_object` looks for a balanced
    `{...}` object anywhere in the text as a fallback, so a near-miss
    response like this one is still recovered instead of rejected outright.
    """
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        candidate = _extract_first_json_object(stripped) or stripped
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(
            "The agent did not return valid JSON. The response was not "
            "written to the contract. Raw response, for diagnosis:\n"
            f"{_diagnostic_snippet(stripped)}"
        ) from error
    if not isinstance(value, dict):
        raise ValueError("The root of the agent's response must be a JSON object.")
    missing = [key for key in required_keys if key not in value]
    if missing:
        raise ValueError(
            "The agent's JSON response is missing required field(s): "
            f"{', '.join(missing)}. Raw response, for diagnosis:\n"
            f"{_diagnostic_snippet(stripped)}"
        )
    return value


def _extract_first_json_object(text: str) -> str | None:
    """Finds the first complete, top-level `{...}` object in `text` by
    brace-matching (string- and escape-aware, so a `{`/`}` inside a quoted
    value never miscounts), regardless of what precedes or follows it.
    Returns `None` if no balanced object is found — the caller falls back
    to treating the whole text as the candidate, unchanged from before
    (ADR-042).
    """
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None


def _diagnostic_snippet(text: str, *, head: int = 1200, tail: int = 800) -> str:
    """Bounds how much of a failed response gets echoed into an error
    message: enough to actually diagnose it (is this prose with no JSON in
    it at all? JSON that looks fine at the start but got cut off?) without
    dumping an entire oversized response — e.g. one padded out by a
    still-too-large `memory/CURRENT_STATE.md` — straight into the
    console. Keeps both ends since a truncation failure shows up at the
    tail, not the head."""
    if len(text) <= head + tail:
        return text
    omitted = len(text) - head - tail
    return f"{text[:head]}\n...[{omitted} characters omitted]...\n{text[-tail:]}"


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
