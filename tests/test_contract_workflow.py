from __future__ import annotations

from pathlib import Path

import pytest

from agents.contract_workflow import (
    ContractStore,
    MemoryUpdate,
    parse_json_response,
    render_contract_summary,
)


def create_store(tmp_path: Path) -> ContractStore:
    (tmp_path / "agents" / "architect").mkdir(parents=True)
    (tmp_path / "agents" / "reviewer").mkdir(parents=True)
    (tmp_path / "agents" / "programmer").mkdir(parents=True)
    return ContractStore(tmp_path)


def test_contract_full_cycle(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    contract = store.create_contract(
        "Test workflow",
        [
            {
                "assignment": "Add a feature.",
                "acceptance_criteria": ["The feature is tested."],
            },
            {
                "assignment": "Update the documentation.",
                "acceptance_criteria": ["README contains an example."],
            },
        ],
        purpose="Verify the contract cycle.",
    )
    assert contract.number == 1
    assert contract.status == "DRAFT"
    assert contract.handoff_to == "reviewer"
    assert store.path_for(1).name == "IMPLEMENTATION_CONTRACT_0001.md"
    assert store.next_for_architecture_review() is not None
    assert store.next_for_programmer() is None

    reviewed_draft = store.record_architecture_review(
        1,
        verdict="ACCEPTED",
        findings="Requirements match AGENTS.md, points are actionable in order.",
    )
    assert reviewed_draft.status == "READY_FOR_PROGRAMMER"
    assert reviewed_draft.handoff_to == "programmer"
    assert len(reviewed_draft.architecture_review_rounds) == 1
    assert store.next_for_programmer() is not None

    store.claim(1)
    store.record_programmer_result(
        1,
        summary="Implemented.",
        notes=[
            {
                "point": 1,
                "note": "Feature added.",
                "files": ["module.py"],
                "tests": ["pytest — passed"],
            },
            {
                "point": 2,
                "note": "README updated.",
                "files": ["README.md"],
                "tests": [],
            },
        ],
    )

    assert store.next_for_implementation_review() is not None
    reviewed = store.record_implementation_review(
        1,
        approved=True,
        summary="Looks good.",
        reviews=[
            {"point": 1, "status": "APPROVED", "review": "Implementation matches."},
            {"point": 2, "status": "APPROVED", "review": "Documentation matches."},
        ],
        out_of_scope_ok=True,
        out_of_scope_findings="Diff only touches module.py and README.md, both in scope.",
        memory_updates=[
            MemoryUpdate(
                path="memory/DECISIONS.md",
                text="Contract workflow is approved.",
            )
        ],
    )
    assert reviewed.status == "APPROVED"
    assert reviewed.handoff_to == "owner"
    assert len(reviewed.implementation_review_rounds) == 1
    assert "Contract workflow" in (
        tmp_path / "memory" / "DECISIONS.md"
    ).read_text(encoding="utf-8")


def test_render_contract_summary_recaps_a_completed_cycle(tmp_path: Path) -> None:
    """The console summary printed after the final `- REVIEWED` checkpoint
    (Tr5-base decision 11) — motivated by the first real end-to-end test,
    where a manually pieced-together `/work`/`/review`/`/commit` sequence
    left no single point confirming how the whole round actually went."""
    store = create_store(tmp_path)
    store.create_contract(
        "Test workflow",
        [
            {
                "assignment": "Add a feature.",
                "acceptance_criteria": ["The feature is tested."],
            },
            {
                "assignment": "Update the documentation.",
                "acceptance_criteria": ["README contains an example."],
            },
        ],
        purpose="Verify the contract cycle.",
    )
    store.record_architecture_review(
        1,
        verdict="ACCEPTED",
        findings="Requirements match AGENTS.md, points are actionable in order.",
    )
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="Implemented.",
        notes=[
            {"point": 1, "note": "Feature added.", "files": ["module.py"], "tests": []},
            {"point": 2, "note": "README updated.", "files": ["README.md"], "tests": []},
        ],
    )
    contract = store.record_implementation_review(
        1,
        approved=True,
        summary="Looks good.",
        reviews=[
            {"point": 1, "status": "APPROVED", "review": "Implementation matches."},
            {"point": 2, "status": "APPROVED", "review": "Documentation matches."},
        ],
        out_of_scope_ok=True,
        out_of_scope_findings="Diff only touches module.py and README.md, both in scope.",
    )

    summary = render_contract_summary(contract)

    assert "IMPLEMENTATION_CONTRACT_0001" in summary
    assert "Test workflow" in summary
    assert "Risk: standard" in summary
    assert "Final status: APPROVED" in summary
    assert "Architecture Review: ACCEPTED (round 1, by reviewer)" in summary
    assert "Implementation: 2/2 point(s) approved" in summary
    assert "module.py" in summary and "README.md" in summary
    assert "Implementation Review: APPROVED (round 1, by reviewer) | Out of Scope: OK" in summary


def test_render_contract_summary_flags_out_of_scope_findings(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract(
        "Test workflow",
        [{"assignment": "Add a feature.", "acceptance_criteria": ["Done."]}],
    )
    store.record_architecture_review(1, verdict="ACCEPTED", findings="Fine.")
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="Implemented.",
        notes=[{"point": 1, "note": "Done.", "files": ["module.py"], "tests": []}],
    )
    contract = store.record_implementation_review(
        1,
        approved=True,
        summary="Touched an extra file.",
        reviews=[{"point": 1, "status": "APPROVED", "review": "Matches."}],
        out_of_scope_ok=False,
        out_of_scope_findings="Also modified unrelated_file.py.",
    )

    summary = render_contract_summary(contract)

    assert "Out of Scope: FLAGGED" in summary


def test_architecture_review_accepts_memory_updates(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(
        1,
        verdict="ACCEPTED",
        findings="Requirements are actionable.",
        memory_updates=[
            MemoryUpdate(
                path="memory/DECISIONS.md",
                text="Found during architecture review: recurring risk worth tracking.",
            )
        ],
    )
    assert "recurring risk worth tracking" in (
        tmp_path / "memory" / "DECISIONS.md"
    ).read_text(encoding="utf-8")


def test_architecture_review_changes_requested_allows_revision(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    changed = store.record_architecture_review(
        1,
        verdict="CHANGES_REQUESTED",
        findings="Point 1 has no verifiable criterion.",
    )
    assert changed.status == "ARCHITECTURE_CHANGES_REQUESTED"
    assert changed.handoff_to == "architect"
    assert store.next_for_revision() is not None
    assert store.next_for_architecture_review() is None

    revised = store.revise_contract(
        1,
        title="Test (revised)",
        points=[
            {"assignment": "Point 1", "acceptance_criteria": ["Tests pass."]},
        ],
    )
    assert revised.status == "DRAFT"
    assert revised.handoff_to == "reviewer"
    # The architecture review round history is never cleared, even after revision.
    assert len(revised.architecture_review_rounds) == 1

    accepted = store.record_architecture_review(
        1, verdict="ACCEPTED", findings="Criterion added, looks good."
    )
    assert accepted.status == "READY_FOR_PROGRAMMER"
    assert len(accepted.architecture_review_rounds) == 2


def test_cannot_claim_before_architecture_review(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    with pytest.raises(ValueError, match="handed off to agent 'reviewer'"):
        store.claim(1)


def test_reclaiming_an_in_progress_contract_for_the_same_agent_is_allowed(
    tmp_path: Path,
) -> None:
    """Regression test (ADR-041): `claim()` persists `IN_PROGRESS`
    immediately, before the caller's actual work runs. If that work then
    fails (e.g. the programmer's own call errors out), a real run left
    the contract permanently stranded — `claim()` refused every retry
    with 'cannot be claimed in status IN_PROGRESS', and nothing else
    transitions `IN_PROGRESS` back to a claimable status. Safe to retry
    specifically because of Tr5-base decision 9: `agent` is a fresh,
    stateless thread per call, so there is no real in-flight work an
    already-`IN_PROGRESS` status could be protecting."""
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")

    first = store.claim(1)
    assert first.status == "IN_PROGRESS"

    # Simulates the programmer's own call failing after claim() already
    # persisted IN_PROGRESS — a second claim() (the retry) must succeed,
    # not raise.
    second = store.claim(1)
    assert second.status == "IN_PROGRESS"
    assert second.assigned_to == "programmer"
    assert second.handoff_to == "programmer"


def test_reclaiming_refreshes_the_pre_discovery_snapshot(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")
    store.claim(1)

    snapshot_path = tmp_path / "contracts" / ".discovery" / "0001_pre.json"
    assert snapshot_path.is_file()
    first_mtime = snapshot_path.stat().st_mtime_ns

    store.claim(1)
    assert snapshot_path.stat().st_mtime_ns >= first_mtime


def test_cannot_reclaim_an_in_progress_contract_for_a_different_agent(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")
    store.claim(1, agent="programmer")

    with pytest.raises(ValueError, match="handed off to agent 'programmer'"):
        store.claim(1, agent="someone_else")


def test_review_requires_every_point(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract(
        "Test",
        [{"assignment": "Point 1"}, {"assignment": "Point 2"}],
    )
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="Done.",
        notes=[
            {"point": 1, "note": "A"},
            {"point": 2, "note": "B"},
        ],
    )
    with pytest.raises(ValueError, match="Missing points: 2"):
        store.record_implementation_review(
            1,
            approved=True,
            summary="Review",
            reviews=[
                {"point": 1, "status": "APPROVED", "review": "OK"},
            ],
            out_of_scope_ok=True,
            out_of_scope_findings="No extra files touched.",
        )


def test_rejects_unsafe_memory_path(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    with pytest.raises(ValueError, match="Disallowed memory target"):
        store.append_memory(
            MemoryUpdate(path="../outside.md", text="No"),
            source="TEST",
        )


def test_allows_principles_memory_target(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    path = store.append_memory(
        MemoryUpdate(path="PRINCIPLES.md", text="Review flag: P6 — example."),
        source="architect",
    )
    assert path == (tmp_path / "PRINCIPLES.md").resolve()
    assert "Review flag: P6" in path.read_text(encoding="utf-8")


def test_parse_fenced_json() -> None:
    data = parse_json_response('```json\n{"approved": true}\n```')
    assert data["approved"] is True


def test_parse_json_response_error_includes_the_raw_response(tmp_path: Path) -> None:
    """Regression test: the original error swallowed the agent's actual
    response, leaving no way to tell prose-with-no-JSON apart from JSON
    truncated mid-generation once the exception propagated up to
    chat_architect.py's generic "Error while creating the contract: ..."
    print (see ADR-037)."""
    with pytest.raises(ValueError, match="Sorry, I could not draft that contract today"):
        parse_json_response("Sorry, I could not draft that contract today.")


def test_parse_json_response_error_keeps_both_ends_of_a_long_response() -> None:
    """A truncation failure shows up at the *end* of a long response, so
    the diagnostic snippet must keep the tail, not just the head."""
    long_response = "{" + ("x" * 5000) + '"unterminated'

    with pytest.raises(ValueError) as excinfo:
        parse_json_response(long_response)

    message = str(excinfo.value)
    assert "characters omitted" in message
    assert long_response[:50] in message
    assert long_response[-20:] in message
    # Bounded, not a full dump of the oversized response.
    assert len(message) < len(long_response)


def test_parse_json_response_missing_required_key_includes_raw_response() -> None:
    """Regression test: valid JSON missing a field a caller reads
    unconditionally (e.g. `data["title"]`) used to fall through this
    function's own error handling and surface as a bare `KeyError` in
    `agents/pipeline.py`, with the raw response already out of scope —
    the same loss of diagnostic evidence ADR-037 fixed for invalid JSON,
    left open for this case."""
    with pytest.raises(ValueError) as excinfo:
        parse_json_response('{"points": []}', required_keys=("title", "points"))

    message = str(excinfo.value)
    assert "missing required field(s): title" in message
    assert '"points": []' in message


def test_parse_json_response_required_keys_satisfied_passes_through() -> None:
    data = parse_json_response('{"title": "T", "points": []}', required_keys=("title", "points"))
    assert data == {"title": "T", "points": []}


def test_parse_json_response_recovers_a_bare_object_with_leading_prose() -> None:
    """Regression test (ADR-042): a real live run's programmer response —
    `implement_contract.md` asks for "only valid JSON", but the model
    prefixed it with one sentence and did not wrap it in a ```json fence.
    Neither of `parse_json_response`'s two previously-supported shapes
    (a fenced block, or the whole stripped text being pure JSON) covered
    this near-miss; it must still be recovered, not rejected."""
    raw = (
        "Now creating the file per the contract.\n"
        '{"summary": "Created project/hello.md.", "notes": '
        '[{"point": 1, "note": "Done.", "files": ["project/hello.md"], "tests": []}]}'
    )
    data = parse_json_response(raw, required_keys=("summary", "notes"))
    assert data["summary"] == "Created project/hello.md."
    assert data["notes"][0]["point"] == 1


def test_parse_json_response_recovers_a_bare_object_with_trailing_prose() -> None:
    raw = '{"approved": true}\nLet me know if you need anything else.'
    data = parse_json_response(raw)
    assert data == {"approved": True}


def test_parse_json_response_prefers_a_fenced_block_when_present() -> None:
    """A ```` ``` ```` fence still wins over the bare-object fallback, even
    if the surrounding prose happens to also contain a `{`/`}` pair."""
    raw = 'Note: {"not": "this one"}.\n```json\n{"approved": true}\n```'
    data = parse_json_response(raw)
    assert data == {"approved": True}


def test_record_programmer_result_note_missing_point_key_raises_clear_error(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")
    store.claim(1)

    with pytest.raises(ValueError, match="must include a 'point' number"):
        store.record_programmer_result(
            1,
            summary="Done.",
            notes=[{"note": "forgot the point number"}],
        )


def test_record_implementation_review_missing_point_key_raises_clear_error(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="OK")
    store.claim(1)
    store.record_programmer_result(1, summary="Done.", notes=[{"point": 1, "note": "A"}])

    with pytest.raises(ValueError, match="must include a 'point' number"):
        store.record_implementation_review(
            1,
            approved=True,
            summary="Review",
            reviews=[{"status": "APPROVED", "review": "forgot the point number"}],
            out_of_scope_ok=True,
            out_of_scope_findings="Checked.",
        )


def test_save_generates_working_state_md(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])

    working_state = (tmp_path / "agents" / "architect" / "WORKING_STATE.md").read_text(
        encoding="utf-8"
    )
    assert "IMPLEMENTATION_CONTRACT_0001" in working_state
    assert "DRAFT" in working_state
    assert "Generated automatically" in working_state


def test_working_state_md_reflects_the_latest_transition(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")

    working_state = (tmp_path / "agents" / "architect" / "WORKING_STATE.md").read_text(
        encoding="utf-8"
    )
    assert "READY_FOR_PROGRAMMER" in working_state
    assert "DRAFT" not in working_state


def test_working_state_md_is_not_a_valid_memory_update_target(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    with pytest.raises(ValueError, match="Disallowed memory target"):
        store.append_memory(
            MemoryUpdate(
                path="agents/architect/WORKING_STATE.md", text="manual note"
            ),
            source="TEST",
        )


def test_claim_saves_pre_discovery_snapshot(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")

    store.claim(1)

    assert (tmp_path / "contracts" / ".discovery" / "0001_pre.json").is_file()


def test_out_of_scope_diff_reports_files_touched_between_claim_and_result(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)

    (tmp_path / "new_module.py").write_text("x = 1\n", encoding="utf-8")

    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": ["new_module.py"], "tests": []}],
    )

    diff = store.out_of_scope_diff(1)
    assert diff is not None
    assert "new_module.py" in diff["added"]


def test_out_of_scope_diff_excludes_the_contracts_own_file(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": [], "tests": []}],
    )

    diff = store.out_of_scope_diff(1)
    assert diff is not None
    assert "contracts/IMPLEMENTATION_CONTRACT_0001.md" not in diff["changed"]


def test_out_of_scope_diff_returns_none_without_snapshots(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])

    assert store.out_of_scope_diff(1) is None


def test_create_contract_defaults_to_standard_risk(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    contract = store.create_contract("Test", [{"assignment": "Point 1"}])
    assert contract.risk_level == "standard"


def test_create_contract_accepts_high_risk(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    contract = store.create_contract(
        "Test", [{"assignment": "Point 1"}], risk_level="high"
    )
    assert contract.risk_level == "high"


def test_create_contract_rejects_invalid_risk_level(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    with pytest.raises(ValueError, match="Invalid risk_level"):
        store.create_contract("Test", [{"assignment": "Point 1"}], risk_level="extreme")


def test_reviewer_can_escalate_risk_level_during_architecture_review(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    reviewed = store.record_architecture_review(
        1, verdict="ACCEPTED", findings="fine", risk_level="high"
    )
    assert reviewed.risk_level == "high"


def test_reviewer_cannot_downgrade_risk_level(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}], risk_level="high")
    reviewed = store.record_architecture_review(
        1, verdict="ACCEPTED", findings="fine", risk_level="standard"
    )
    # "standard" from the reviewer is a no-op — it never lowers risk_level
    # (Tr5-base decision 7).
    assert reviewed.risk_level == "high"


def test_revise_contract_preserves_risk_level_unless_given(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}], risk_level="high")
    store.record_architecture_review(
        1, verdict="CHANGES_REQUESTED", findings="needs work"
    )
    revised = store.revise_contract(
        1, title="Test (revised)", points=[{"assignment": "Point 1 fixed"}]
    )
    assert revised.risk_level == "high"

    store.record_architecture_review(
        1, verdict="CHANGES_REQUESTED", findings="still needs work"
    )
    not_lowered = store.revise_contract(
        1,
        title="Test (revised again)",
        points=[{"assignment": "Point 1 fixed again"}],
        risk_level="standard",
    )
    # Tr5-base decision 7: "never downgraded back to standard by anyone" —
    # explicitly passing "standard" here is a no-op, not a downgrade, the
    # same as the equivalent case in record_architecture_review.
    assert not_lowered.risk_level == "high"


def test_revise_contract_can_still_escalate_risk_level(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}], risk_level="standard")
    store.record_architecture_review(
        1, verdict="CHANGES_REQUESTED", findings="needs work"
    )
    escalated = store.revise_contract(
        1,
        title="Test (revised)",
        points=[{"assignment": "Point 1 fixed"}],
        risk_level="high",
    )
    assert escalated.risk_level == "high"
