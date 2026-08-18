from __future__ import annotations

import os
from contextlib import ExitStack
from pathlib import Path

from agents.agent import AgentConfig, WORKSPACE
from agents.agent_profile import create_agent
from agents.contract_workflow import ContractStore
from agents.git_ops import sync_origin_from_env
from agents.pipeline import (
    commit_approved_contract,
    create_contract,
    describe_conversational_action,
    dispatch_conversational_action,
    implement_next,
    opening_briefing,
    parse_conversational_action,
    proceed,
    revise_contract,
    run_implementation_review,
    print_status,
    show_inbox,
)
from agents.voice import start_voice_session


CONFIRM_WORDS = {"ano", "a", "yes", "y", "ok"}

HELP = """
Talk to the architect directly — plain text goes straight to them. If the
architect judges from the conversation itself that you clearly confirmed
moving a specific contract forward (no exact slash command needed), it
proposes the equivalent command and asks you to confirm again before
anything actually runs — reply "ano"/"yes" to proceed, anything else
cancels and the conversation just continues.

Commands available alongside the conversation:
  /new <topic>       drafts a new contract; the pipeline then runs on its
                      own (architecture review, and if accepted,
                      implementation and implementation review) and stops
                      once it returns to the architect/owner — unless the
                      contract is high-risk, which pauses twice for /proceed
  /revise <n> <topic> rewrites contract <n>'s requirements after
                      CHANGES_REQUESTED and continues the same way
  /proceed <n>      resumes a high-risk contract paused before
                      implementation or before implementation review
                      (no-op for standard-risk contracts, which never pause)
  /work [n]         manual override: programmer picks up contract <n> (or
                      the next ready one)
  /review [n]       manual override: reviewer runs implementation review
                      on contract <n> (or the next ready one)
  /commit <n>       pushes contract <n>'s final "- REVIEWED" checkpoint
                      (must be APPROVED); routine for standard-risk
                      contracts (already auto-pushed), the actual manual
                      step for high-risk ones
  /voice            switches to voice input/output with the architect
                      (text is still echoed to the screen); needs
                      GEMINI_API_KEY in .env — used only for speech-to-text/
                      text-to-speech, never for the architect's own reasoning
  /voice end        returns to typed-only input
  /status           shows the contract queue
  /inbox            shows the architect's inbox
  /help             shows this help
  /exit             exits (aliases: /quit, exit, quit)
""".strip()


def main(project_root: Path = WORKSPACE) -> None:
    project_root = project_root.resolve()
    config = AgentConfig.load(project_root / ".env")
    store = ContractStore(project_root)

    try:
        origin_message = sync_origin_from_env(project_root, os.environ.get("GIT_REPO"))
        if origin_message:
            print(f"\n{origin_message}\n")
    except Exception as error:
        print(f"\nCould not sync origin from GIT_REPO: {error}\n")

    # Tr5-base decision 9: the architect is the one role allowed to stay
    # naturally continuous within a session (persistent memory, one
    # standing thread) — created once, above, and kept for the whole
    # session. The reviewer and the programmer get NO carryover, not even
    # within this same session: `reviewer_factory`/`programmer_factory`
    # are passed to `agents/pipeline.py` instead of a constructed `Agent`,
    # so a brand-new thread is created (and closed) for every single call
    # — every Architecture Review, every Implementation Review, every
    # implementation — never reused across contracts, and never reused
    # between one contract's own Architecture Review and its later
    # Implementation Review either.
    def reviewer_factory():
        return create_agent("reviewer", config=config, project_root=project_root)

    def programmer_factory():
        return create_agent("programmer", config=config, project_root=project_root)

    with ExitStack() as stack:
        architect = stack.enter_context(
            create_agent("architect", config=config, project_root=project_root)
        )

        try:
            greeting = architect.ask(opening_briefing(store, project_root))
            print(f"\nArchitect:\n{greeting}\n")
        except Exception as error:
            print(f"\nCould not reach the architect for the opening greeting: {error}\n")

        print("(/help for commands, /exit to quit)\n")

        voice_session = None

        def _stop_voice_session() -> None:
            nonlocal voice_session
            if voice_session is not None:
                voice_session.stop()
                voice_session = None

        while True:
            try:
                raw = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not raw:
                continue
            if raw in {"/exit", "/quit", "exit", "quit"}:
                _stop_voice_session()
                break
            if raw == "/help":
                print(HELP)
                continue
            if raw == "/status":
                print_status(store)
                continue
            if raw == "/inbox":
                show_inbox(project_root, "architect")
                continue
            if raw == "/voice":
                if voice_session is not None and voice_session.is_running:
                    print("\nVoice session already running — say '/voice end' to stop it first.\n")
                    continue
                try:
                    voice_session = start_voice_session(
                        architect.ask,
                        on_error=lambda error: print(f"\nVoice session error: {error}\n"),
                    )
                    print(
                        "\nVoice session started — speak into your microphone. "
                        "Type '/voice end' to stop.\n"
                    )
                except Exception as error:
                    print(f"\nCould not start the voice session: {error}\n")
                continue
            if raw == "/voice end":
                if voice_session is None or not voice_session.is_running:
                    print("\nNo voice session is running.\n")
                    voice_session = None
                else:
                    _stop_voice_session()
                    print("\nVoice session stopped.\n")
                continue
            if raw.startswith("/new "):
                try:
                    create_contract(
                        architect,
                        reviewer_factory,
                        programmer_factory,
                        store,
                        raw.split(maxsplit=1)[1],
                    )
                except Exception as error:
                    print(f"\nError while creating the contract: {error}")
                continue
            if raw.startswith("/revise "):
                try:
                    _, rest = raw.split(maxsplit=1)
                    number_str, task = rest.split(maxsplit=1)
                    revise_contract(
                        architect,
                        reviewer_factory,
                        programmer_factory,
                        store,
                        int(number_str),
                        task,
                    )
                except Exception as error:
                    print(f"\nError while revising the contract: {error}")
                continue
            if raw == "/work" or raw.startswith("/work "):
                try:
                    number = int(raw.split(maxsplit=1)[1]) if " " in raw else None
                    implement_next(programmer_factory, store, number=number)
                except Exception as error:
                    print(f"\nError while implementing the contract: {error}")
                continue
            if raw == "/review" or raw.startswith("/review "):
                try:
                    number = int(raw.split(maxsplit=1)[1]) if " " in raw else None
                    run_implementation_review(reviewer_factory, store, number=number)
                except Exception as error:
                    print(f"\nError while reviewing the contract: {error}")
                continue
            if raw.startswith("/proceed "):
                try:
                    proceed(
                        reviewer_factory,
                        programmer_factory,
                        store,
                        int(raw.split(maxsplit=1)[1]),
                    )
                except Exception as error:
                    print(f"\nError while resuming the contract: {error}")
                continue
            if raw.startswith("/commit "):
                try:
                    commit_approved_contract(store, int(raw.split(maxsplit=1)[1]))
                except Exception as error:
                    print(f"\nError while committing: {error}")
                continue

            try:
                reply = architect.ask(raw)
            except Exception as error:
                print(f"\nError: {error}\n")
                continue

            display_text, action = parse_conversational_action(reply)
            print(f"\nArchitect:\n{display_text}\n")

            if action is not None:
                try:
                    description = describe_conversational_action(action)
                except ValueError as error:
                    print(f"(Could not act on the detected action: {error})\n")
                    continue

                confirm = input(
                    f"Run {description}? (ano/yes to confirm, anything else cancels): "
                ).strip().lower()
                if confirm in CONFIRM_WORDS:
                    try:
                        dispatch_conversational_action(
                            action,
                            architect=architect,
                            reviewer_factory=reviewer_factory,
                            programmer_factory=programmer_factory,
                            store=store,
                        )
                    except Exception as error:
                        print(f"\nError while running {description}: {error}\n")
                else:
                    print("Cancelled.\n")


if __name__ == "__main__":
    main()
