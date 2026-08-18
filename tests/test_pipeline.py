from __future__ import annotations

import json
from pathlib import Path

import pytest

import agents.pipeline as pipeline
from agents.contract_workflow import ContractStore


class ScriptedAgent:
    """Minimal stand-in for Agent: only needs .run_command(name, **vars)
    plus the context-manager surface `pipeline.py` uses when it constructs
    a reviewer/programmer from a factory (Tr5-base decision 9)."""

    def __init__(self, responses: dict[str, list[str]]) -> None:
        self.responses = responses
        self.calls: list[str] = []
        self.call_variables: list[dict[str, str]] = []
        self.closed = False

    def run_command(self, command_name: str, **variables: str) -> str:
        self.calls.append(command_name)
        self.call_variables.append(variables)
        queue = self.responses[command_name]
        return queue.pop(0)

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "ScriptedAgent":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class FakeGit:
    """Stand-in for git_ops.commit_and_push — no real git repo needed."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def __call__(self, project_root: Path, message: str) -> bool:
        self.calls.append((project_root, message))
        return True


@pytest.fixture(autouse=True)
def fake_git(monkeypatch: pytest.MonkeyPatch) -> FakeGit:
    fake = FakeGit()
    monkeypatch.setattr(pipeline, "commit_and_push", fake)
    return fake


def create_store(tmp_path: Path) -> ContractStore:
    (tmp_path / "agents" / "architect").mkdir(parents=True)
    (tmp_path / "agents" / "reviewer").mkdir(parents=True)
    (tmp_path / "agents" / "programmer").mkdir(parents=True)
    return ContractStore(tmp_path)


def test_create_contract_chains_through_to_implementation_review(
    tmp_path: Path, fake_git: FakeGit
) -> None:
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                        "purpose": "P",
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps(
                    {"verdict": "ACCEPTED", "findings": "fine", "memory_updates": []}
                )
            ],
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Only a.py touched, matches point 1.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {
                                "point": 1,
                                "note": "did it",
                                "files": ["a.py"],
                                "tests": [],
                            }
                        ],
                        "tests": [],
                    }
                )
            ],
        }
    )

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    contract = store.load(1)
    assert contract.status == "APPROVED"
    assert reviewer.calls == ["architecture_review", "review_contract"]
    assert programmer.calls == ["implement_contract"]
    assert architect.calls == ["create_contract"]
    assert reviewer.closed and programmer.closed
    # standard-risk contracts auto-chain through all three checkpoints
    # (Tr5-base decision 5): CONTRACT_NNNN, - IMPLEMENTED, - REVIEWED.
    assert fake_git.calls == [
        (tmp_path.resolve(), "CONTRACT_0001"),
        (tmp_path.resolve(), "CONTRACT_0001 - IMPLEMENTED"),
        (tmp_path.resolve(), "CONTRACT_0001 - REVIEWED"),
    ]


def test_commit_approved_contract_commits_with_reviewed_suffix(
    tmp_path: Path, fake_git: FakeGit
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": [], "tests": []}],
    )
    store.record_implementation_review(
        1,
        approved=True,
        summary="good",
        reviews=[{"point": 1, "status": "APPROVED", "review": "ok"}],
        out_of_scope_ok=True,
        out_of_scope_findings="No extra files touched.",
    )

    pipeline.commit_approved_contract(store, 1)

    assert fake_git.calls == [(tmp_path.resolve(), "CONTRACT_0001 - REVIEWED")]


def test_commit_approved_contract_refuses_when_not_approved(
    tmp_path: Path, fake_git: FakeGit
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])

    pipeline.commit_approved_contract(store, 1)

    assert fake_git.calls == []


def test_run_architecture_review_prints_a_mid_pipeline_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression test: previously the only place a round summary printed
    was right after the final `- REVIEWED` checkpoint — a manual/
    conversational step (`/work`, `/review`, or their ADR-040
    conversational-action equivalents) that does not auto-chain further
    left the owner with only a single terse status line and no visibility
    into where the contract actually stood until the whole round finished.
    `render_contract_summary()` already degrades gracefully with whatever
    is filled in so far (see its own docstring) — this asserts it is
    actually shown at each individual step, not only the last one."""
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps({"verdict": "ACCEPTED", "findings": "fine", "memory_updates": []})
            ]
        }
    )
    capsys.readouterr()

    pipeline.run_architecture_review(lambda: reviewer, store, 1)

    out = capsys.readouterr().out
    assert "IMPLEMENTATION_CONTRACT_0001 summary" in out
    assert "Architecture Review: ACCEPTED" in out


def test_implement_next_prints_a_mid_pipeline_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {"point": 1, "note": "did it", "files": ["a.py"], "tests": []}
                        ],
                        "tests": [],
                    }
                )
            ]
        }
    )
    capsys.readouterr()

    pipeline.implement_next(lambda: programmer, store, number=1)

    out = capsys.readouterr().out
    assert "IMPLEMENTATION_CONTRACT_0001 summary" in out
    assert "a.py" in out


def test_run_implementation_review_prints_a_summary_even_when_changes_requested(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The mid-pipeline summary is shown regardless of verdict — a
    CHANGES_REQUESTED result is exactly when the owner most needs to see
    the current state at a glance, not only on the eventual APPROVED
    path."""
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    store.record_programmer_result(1, summary="done", notes=[{"point": 1, "note": "did it"}])
    reviewer = ScriptedAgent(
        {
            "review_contract": [
                json.dumps(
                    {
                        "approved": False,
                        "summary": "Needs work",
                        "reviews": [
                            {"point": 1, "status": "CHANGES_REQUESTED", "review": "no"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Checked.",
                        "memory_updates": [],
                    }
                )
            ]
        }
    )
    capsys.readouterr()

    pipeline.run_implementation_review(lambda: reviewer, store, number=1)

    out = capsys.readouterr().out
    assert "IMPLEMENTATION_CONTRACT_0001 summary" in out
    assert "Final status: CHANGES_REQUESTED" in out


def test_create_contract_auto_chain_prints_the_summary_only_once_per_step(
    tmp_path: Path, fake_git: FakeGit, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression guard for the de-duplication in `_review_and_commit()`:
    once `run_implementation_review()` started printing its own
    mid-pipeline summary, the previous unconditional summary print right
    after the final checkpoint would have shown the exact same content
    twice in the fully-automatic APPROVED path."""
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                        "purpose": "P",
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps(
                    {"verdict": "ACCEPTED", "findings": "fine", "memory_updates": []}
                )
            ],
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Only a.py touched, matches point 1.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {
                                "point": 1,
                                "note": "did it",
                                "files": ["a.py"],
                                "tests": [],
                            }
                        ],
                        "tests": [],
                    }
                )
            ],
        }
    )
    capsys.readouterr()

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    out = capsys.readouterr().out
    # Three distinct summaries are expected — one after architecture
    # review (READY_FOR_PROGRAMMER), one after implementation
    # (READY_FOR_REVIEWER), one after implementation review (APPROVED) —
    # but the final APPROVED one exactly once, not printed again after
    # the checkpoint commit.
    assert out.count("IMPLEMENTATION_CONTRACT_0001 summary") == 3
    assert out.count("Final status: APPROVED") == 1


def test_commit_approved_contract_prints_a_round_summary(
    tmp_path: Path, fake_git: FakeGit, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tr5-base decision 11: a short recap prints right after the final
    checkpoint, whether the pipeline got there automatically or (as in the
    first real test) the owner pieced it together via /work, /review, and
    finally /commit."""
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": ["a.py"], "tests": []}],
    )
    store.record_implementation_review(
        1,
        approved=True,
        summary="good",
        reviews=[{"point": 1, "status": "APPROVED", "review": "ok"}],
        out_of_scope_ok=True,
        out_of_scope_findings="No extra files touched.",
    )
    capsys.readouterr()  # discard setup noise, if any

    pipeline.commit_approved_contract(store, 1)

    out = capsys.readouterr().out
    assert "IMPLEMENTATION_CONTRACT_0001 summary" in out
    assert "Final status: APPROVED" in out
    assert "a.py" in out


def test_create_contract_auto_chain_prints_a_round_summary(
    tmp_path: Path, fake_git: FakeGit, capsys: pytest.CaptureFixture[str]
) -> None:
    """Same recap, but reached through the fully automatic standard-risk
    chain (/new) rather than the manual /commit override."""
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                        "purpose": "P",
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps(
                    {"verdict": "ACCEPTED", "findings": "fine", "memory_updates": []}
                )
            ],
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Only a.py touched, matches point 1.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {
                                "point": 1,
                                "note": "did it",
                                "files": ["a.py"],
                                "tests": [],
                            }
                        ],
                        "tests": [],
                    }
                )
            ],
        }
    )
    capsys.readouterr()

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    out = capsys.readouterr().out
    assert "IMPLEMENTATION_CONTRACT_0001 summary" in out
    assert "Final status: APPROVED" in out


def test_create_contract_stops_when_changes_requested_at_architecture_review(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps({"verdict": "CHANGES_REQUESTED", "findings": "needs work"})
            ],
        }
    )
    programmer = ScriptedAgent({})

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    contract = store.load(1)
    assert contract.status == "ARCHITECTURE_CHANGES_REQUESTED"
    assert programmer.calls == []


def test_create_contract_stops_after_changes_requested_implementation_review(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps({"verdict": "ACCEPTED", "findings": "fine"})
            ],
            "review_contract": [
                json.dumps(
                    {
                        "approved": False,
                        "summary": "Not quite",
                        "reviews": [
                            {
                                "point": 1,
                                "status": "CHANGES_REQUESTED",
                                "review": "missing test",
                            }
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "No extra files touched.",
                    }
                )
            ],
        }
    )
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {"point": 1, "note": "did it", "files": [], "tests": []}
                        ],
                        "tests": [],
                    }
                )
            ],
        }
    )

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    contract = store.load(1)
    assert contract.status == "CHANGES_REQUESTED"
    # The chain stops here — a second automatic programmer round must not run.
    assert programmer.calls == ["implement_contract"]


def test_opening_briefing_includes_status_and_inbox(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Point 1"}])

    briefing = pipeline.opening_briefing(store, tmp_path)

    assert "IMPLEMENTATION_CONTRACT_0001" in briefing
    assert "agenda" in briefing.lower()


def test_high_risk_contract_pauses_before_implementation(
    tmp_path: Path, fake_git: FakeGit
) -> None:
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps(
                    {
                        "title": "Test",
                        "points": [
                            {"assignment": "Do X", "acceptance_criteria": ["X works"]}
                        ],
                        "risk_level": "high",
                    }
                )
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps({"verdict": "ACCEPTED", "findings": "fine"})
            ],
        }
    )
    programmer = ScriptedAgent({})

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    contract = store.load(1)
    assert contract.status == "READY_FOR_PROGRAMMER"
    assert contract.risk_level == "high"
    assert programmer.calls == []
    # Only checkpoint 1 fires before a high-risk pause — decision 7.
    assert fake_git.calls == [(tmp_path.resolve(), "CONTRACT_0001")]


def test_proceed_resumes_high_risk_contract_through_both_pause_points(
    tmp_path: Path, fake_git: FakeGit
) -> None:
    store = create_store(tmp_path)
    store.create_contract(
        "Test", [{"assignment": "Do X"}], risk_level="high"
    )
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")

    reviewer = ScriptedAgent(
        {
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Only a.py touched.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )
    programmer = ScriptedAgent(
        {
            "implement_contract": [
                json.dumps(
                    {
                        "summary": "done",
                        "notes": [
                            {"point": 1, "note": "did it", "files": ["a.py"], "tests": []}
                        ],
                        "tests": [],
                    }
                )
            ],
        }
    )

    # First /proceed: resumes implementation, then pauses again before review.
    pipeline.proceed(lambda: reviewer, lambda: programmer, store, 1)
    contract = store.load(1)
    assert contract.status == "READY_FOR_REVIEWER"
    assert programmer.calls == ["implement_contract"]
    assert reviewer.calls == []
    assert fake_git.calls == [
        (tmp_path.resolve(), "CONTRACT_0001 - IMPLEMENTED"),
    ]

    # Second /proceed: resumes implementation review. Approved, but the
    # final REVIEWED commit is not pushed automatically for high risk.
    pipeline.proceed(lambda: reviewer, lambda: programmer, store, 1)
    contract = store.load(1)
    assert contract.status == "APPROVED"
    assert reviewer.calls == ["review_contract"]
    assert fake_git.calls == [
        (tmp_path.resolve(), "CONTRACT_0001 - IMPLEMENTED"),
    ]

    # The owner finalizes it manually via /commit.
    pipeline.commit_approved_contract(store, 1)
    assert fake_git.calls == [
        (tmp_path.resolve(), "CONTRACT_0001 - IMPLEMENTED"),
        (tmp_path.resolve(), "CONTRACT_0001 - REVIEWED"),
    ]


def test_proceed_reports_no_pause_point_for_unrelated_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Do X"}])

    reviewer = ScriptedAgent({})
    programmer = ScriptedAgent({})
    pipeline.proceed(lambda: reviewer, lambda: programmer, store, 1)

    assert "not at a pause point" in capsys.readouterr().out
    assert reviewer.calls == []
    assert programmer.calls == []


def test_create_contract_runs_discovery_scan_first(tmp_path: Path) -> None:
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps({"title": "Test", "points": [{"assignment": "Do X"}]})
            ],
        }
    )
    reviewer = ScriptedAgent(
        {
            "architecture_review": [
                json.dumps({"verdict": "CHANGES_REQUESTED", "findings": "no"})
            ],
        }
    )
    programmer = ScriptedAgent({})

    pipeline.create_contract(
        architect, lambda: reviewer, lambda: programmer, store, "Add X"
    )

    current_state = tmp_path / "memory" / "CURRENT_STATE.md"
    assert current_state.is_file()
    assert "# Current State" in current_state.read_text(encoding="utf-8")


def test_run_implementation_review_passes_discovery_diff_to_reviewer(
    tmp_path: Path,
) -> None:
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Do X"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    (tmp_path / "extra_file.py").write_text("x = 1\n", encoding="utf-8")
    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": ["extra_file.py"], "tests": []}],
    )

    reviewer = ScriptedAgent(
        {
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "extra_file.py matches point 1.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )

    pipeline.run_implementation_review(lambda: reviewer, store, number=1)

    diff_text = reviewer.call_variables[0]["out_of_scope_diff"]
    assert "extra_file.py" in diff_text


def test_run_implementation_review_handles_missing_snapshot_gracefully(
    tmp_path: Path,
) -> None:
    # A contract claimed/finished without ever going through claim()'s
    # snapshot hook (e.g. state seeded directly, as in this test) should
    # not crash implementation review — it just tells the reviewer to
    # check manually.
    store = create_store(tmp_path)
    store.create_contract("Test", [{"assignment": "Do X"}])
    store.record_architecture_review(1, verdict="ACCEPTED", findings="fine")
    store.claim(1)
    # Remove the snapshot claim() just wrote, to simulate it being absent.
    for snapshot in (tmp_path / "contracts" / ".discovery").glob("*.json"):
        snapshot.unlink()
    store.record_programmer_result(
        1,
        summary="done",
        notes=[{"point": 1, "note": "did it", "files": [], "tests": []}],
    )

    reviewer = ScriptedAgent(
        {
            "review_contract": [
                json.dumps(
                    {
                        "approved": True,
                        "summary": "Good",
                        "reviews": [
                            {"point": 1, "status": "APPROVED", "review": "ok"}
                        ],
                        "out_of_scope_ok": True,
                        "out_of_scope_findings": "Checked manually.",
                        "memory_updates": [],
                    }
                )
            ],
        }
    )

    pipeline.run_implementation_review(lambda: reviewer, store, number=1)

    diff_text = reviewer.call_variables[0]["out_of_scope_diff"]
    assert "No discovery snapshot available" in diff_text


def test_reviewer_and_programmer_get_a_fresh_agent_for_every_call(
    tmp_path: Path,
) -> None:
    """Tr5-base decision 9: the reviewer and programmer get a brand-new
    thread for every single call — no carryover between contracts, and
    none between a contract's own Architecture Review and its later
    Implementation Review either. `chat_architect.py` previously
    constructed one reviewer/programmer `Agent` per session and reused it
    for every command, silently defeating this guarantee even though
    `config.json`/command templates/ADR-029 all documented it as true —
    this test exercises `pipeline.py`'s factory-based fix directly, so a
    regression here (someone passing a live `Agent` back in instead of a
    factory) is caught without needing to drive `chat_architect.py`
    itself."""
    store = create_store(tmp_path)
    architect = ScriptedAgent(
        {
            "create_contract": [
                json.dumps({"title": "Test", "points": [{"assignment": "Do X"}]})
            ],
        }
    )

    reviewer_instances: list[ScriptedAgent] = []

    def make_reviewer() -> ScriptedAgent:
        agent = ScriptedAgent(
            {
                "architecture_review": [
                    json.dumps({"verdict": "ACCEPTED", "findings": "fine"})
                ],
                "review_contract": [
                    json.dumps(
                        {
                            "approved": True,
                            "summary": "Good",
                            "reviews": [
                                {"point": 1, "status": "APPROVED", "review": "ok"}
                            ],
                            "out_of_scope_ok": True,
                            "out_of_scope_findings": "fine",
                            "memory_updates": [],
                        }
                    )
                ],
            }
        )
        reviewer_instances.append(agent)
        return agent

    programmer_instances: list[ScriptedAgent] = []

    def make_programmer() -> ScriptedAgent:
        agent = ScriptedAgent(
            {
                "implement_contract": [
                    json.dumps(
                        {
                            "summary": "done",
                            "notes": [
                                {"point": 1, "note": "did it", "files": [], "tests": []}
                            ],
                            "tests": [],
                        }
                    )
                ],
            }
        )
        programmer_instances.append(agent)
        return agent

    pipeline.create_contract(architect, make_reviewer, make_programmer, store, "Add X")

    # Architecture Review and Implementation Review are two different
    # calls to the reviewer — each must get its own fresh instance, not
    # the same one carrying the other's conversation.
    assert len(reviewer_instances) == 2
    assert reviewer_instances[0] is not reviewer_instances[1]
    assert reviewer_instances[0].calls == ["architecture_review"]
    assert reviewer_instances[1].calls == ["review_contract"]
    assert all(agent.closed for agent in reviewer_instances)

    assert len(programmer_instances) == 1
    assert all(agent.closed for agent in programmer_instances)


# --- Conversational actions (ADR-040) ----------------------------------


def test_parse_conversational_action_extracts_the_block_and_strips_it() -> None:
    response = (
        "Sure, I'll rewrite the filename.\n\n"
        '```action\n{"type": "revise_contract", "number": 1, "topic": "rename to hello.md"}\n```'
    )
    display_text, action = pipeline.parse_conversational_action(response)
    assert display_text == "Sure, I'll rewrite the filename."
    assert action == {"type": "revise_contract", "number": 1, "topic": "rename to hello.md"}


def test_parse_conversational_action_returns_none_when_no_block_present() -> None:
    display_text, action = pipeline.parse_conversational_action("Just a normal reply.")
    assert display_text == "Just a normal reply."
    assert action is None


def test_parse_conversational_action_ignores_a_malformed_block() -> None:
    """A block that fails to parse must not crash the conversation over
    a one-off bad response — the raw text (block included) is shown as-is
    instead of being silently discarded."""
    response = "Some text.\n```action\n{not valid json\n```"
    display_text, action = pipeline.parse_conversational_action(response)
    assert display_text == response
    assert action is None


def test_parse_conversational_action_ignores_a_block_without_a_type() -> None:
    response = 'Text.\n```action\n{"number": 1}\n```'
    display_text, action = pipeline.parse_conversational_action(response)
    assert display_text == response
    assert action is None


def test_describe_conversational_action_for_each_type() -> None:
    assert (
        pipeline.describe_conversational_action({"type": "new_contract", "topic": "add a check"})
        == "/new add a check"
    )
    assert (
        pipeline.describe_conversational_action(
            {"type": "revise_contract", "number": 1, "topic": "rename to hello.md"}
        )
        == "/revise 1 rename to hello.md"
    )
    assert pipeline.describe_conversational_action({"type": "work", "number": 2}) == "/work 2"
    assert pipeline.describe_conversational_action({"type": "work"}) == "/work"
    assert pipeline.describe_conversational_action({"type": "review"}) == "/review"
    assert (
        pipeline.describe_conversational_action({"type": "proceed", "number": 3}) == "/proceed 3"
    )
    assert pipeline.describe_conversational_action({"type": "commit", "number": 4}) == "/commit 4"


def test_describe_conversational_action_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unknown conversational action type"):
        pipeline.describe_conversational_action({"type": "delete_everything"})


def test_describe_conversational_action_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="missing required field"):
        pipeline.describe_conversational_action({"type": "revise_contract", "number": 1})


def test_dispatch_conversational_action_routes_new_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline,
        "create_contract",
        lambda architect, reviewer_factory, programmer_factory, store, topic: calls.append(
            ("new_contract", architect, reviewer_factory, programmer_factory, store, topic)
        ),
    )
    pipeline.dispatch_conversational_action(
        {"type": "new_contract", "topic": "add X"},
        architect="architect-sentinel",
        reviewer_factory="reviewer-factory-sentinel",
        programmer_factory="programmer-factory-sentinel",
        store="store-sentinel",
    )
    assert calls == [
        (
            "new_contract",
            "architect-sentinel",
            "reviewer-factory-sentinel",
            "programmer-factory-sentinel",
            "store-sentinel",
            "add X",
        )
    ]


def test_dispatch_conversational_action_routes_revise_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline,
        "revise_contract",
        lambda architect, reviewer_factory, programmer_factory, store, number, topic: calls.append(
            (number, topic)
        ),
    )
    pipeline.dispatch_conversational_action(
        {"type": "revise_contract", "number": 1, "topic": "rename it"},
        architect=None,
        reviewer_factory=None,
        programmer_factory=None,
        store=None,
    )
    assert calls == [(1, "rename it")]


def test_dispatch_conversational_action_routes_work_with_and_without_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline,
        "implement_next",
        lambda programmer_factory, store, *, number=None: calls.append(number),
    )
    pipeline.dispatch_conversational_action(
        {"type": "work", "number": 3}, architect=None, reviewer_factory=None,
        programmer_factory=None, store=None,
    )
    pipeline.dispatch_conversational_action(
        {"type": "work"}, architect=None, reviewer_factory=None,
        programmer_factory=None, store=None,
    )
    assert calls == [3, None]


def test_dispatch_conversational_action_routes_review(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline,
        "run_implementation_review",
        lambda reviewer_factory, store, *, number=None: calls.append(number),
    )
    pipeline.dispatch_conversational_action(
        {"type": "review", "number": 5}, architect=None, reviewer_factory=None,
        programmer_factory=None, store=None,
    )
    assert calls == [5]


def test_dispatch_conversational_action_routes_proceed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline,
        "proceed",
        lambda reviewer_factory, programmer_factory, store, number: calls.append(number),
    )
    pipeline.dispatch_conversational_action(
        {"type": "proceed", "number": 7}, architect=None, reviewer_factory=None,
        programmer_factory=None, store=None,
    )
    assert calls == [7]


def test_dispatch_conversational_action_routes_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        pipeline, "commit_approved_contract", lambda store, number: calls.append(number)
    )
    pipeline.dispatch_conversational_action(
        {"type": "commit", "number": 9}, architect=None, reviewer_factory=None,
        programmer_factory=None, store=None,
    )
    assert calls == [9]


def test_dispatch_conversational_action_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unknown conversational action type"):
        pipeline.dispatch_conversational_action(
            {"type": "delete_everything"},
            architect=None,
            reviewer_factory=None,
            programmer_factory=None,
            store=None,
        )
