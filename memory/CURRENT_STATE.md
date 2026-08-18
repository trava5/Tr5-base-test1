# Current State

Generator: Tr5-base Discovery Engine v2.0

Generated automatically before every `create_contract`/`revise_contract` call — do not edit by hand, edits are overwritten on the next scan.

---

## Repository Structure

- agents/
  - architect/
    - commands/
      - analyze_architecture.md
      - create_contract.md
      - delegate.md
      - plan.md
      - propose_change.md
      - review_design.md
      - summarize.md
      - update_memory.md
    - runtime/
      - .gitkeep
      - session.log
    - COMMANDS.md
    - INBOX.md
    - MEMORY.md
    - ROLE.md
    - WORKING_STATE.md
    - config.json
  - programmer/
    - commands/
      - implement_contract.md
    - runtime/
      - session.log
    - COMMANDS.md
    - INBOX.md
    - MEMORY.md
    - ROLE.md
    - config.json
  - reviewer/
    - commands/
      - architecture_review.md
      - review_contract.md
    - runtime/
      - .gitkeep
      - session.log
    - COMMANDS.md
    - INBOX.md
    - MEMORY.md
    - ROLE.md
    - config.json
  - __init__.py
  - agent.py
  - agent_profile.py
  - contract_workflow.py
  - git_ops.py
  - pipeline.py
  - progress.py
  - voice.py
- contracts/
  - .gitkeep
  - IMPLEMENTATION_CONTRACT_0001.md
  - IMPLEMENTATION_CONTRACT_0002.md
  - IMPLEMENTATION_CONTRACT_0003.md
  - OWNER_INBOX.md
  - README.md
- memory/
  - CHANGE_LOG.md
  - CURRENT_STATE.md
  - DECISIONS.md
  - OPEN_TASKS.md
  - PROJECT_STATE.md
  - TEMPLATE_ORIGINS.md
- project/
  - README.md
  - checklist.md
  - hello.md
  - hello_world.html
- source/
  - README.md
- templates/
  - voice_module/
    - README.md
    - __init__.py
    - audio_io.py
    - gemini_voice_bridge.py
    - live_voice_session.py
  - __init__.py
- tests/
  - test_agent.py
  - test_agent_profile.py
  - test_contract_workflow.py
  - test_discovery_engine.py
  - test_git_ops.py
  - test_pipeline.py
  - test_progress.py
  - test_voice.py
  - test_voice_module.py
- tools/
  - discovery_engine/
    - README.md
    - __init__.py
    - generate_current_state.py
  - __init__.py
- .env.example
- .gitignore
- AGENTS.md
- AGENTS_SUGGESTIONS.md
- PRINCIPLES.md
- README.md
- UPDATE_NOTES.md
- chat_architect.py
- requirements.txt

---

## Artifacts

| Name | Relative Path | Type |
|---|---|---|
| .env.example | .env.example | Unknown |
| .gitignore | .gitignore | Unknown |
| AGENTS.md | AGENTS.md | Governance Document |
| AGENTS_SUGGESTIONS.md | AGENTS_SUGGESTIONS.md | Markdown Document |
| PRINCIPLES.md | PRINCIPLES.md | Governance Document |
| README.md | README.md | Markdown Document |
| UPDATE_NOTES.md | UPDATE_NOTES.md | Markdown Document |
| agents | agents | Directory |
| __init__.py | agents/__init__.py | Python Source |
| agent.py | agents/agent.py | Python Source |
| agent_profile.py | agents/agent_profile.py | Python Source |
| architect | agents/architect | Directory |
| COMMANDS.md | agents/architect/COMMANDS.md | Agent Commands |
| INBOX.md | agents/architect/INBOX.md | Agent Inbox |
| MEMORY.md | agents/architect/MEMORY.md | Agent Memory |
| ROLE.md | agents/architect/ROLE.md | Agent Role |
| WORKING_STATE.md | agents/architect/WORKING_STATE.md | Agent Working State |
| commands | agents/architect/commands | Directory |
| analyze_architecture.md | agents/architect/commands/analyze_architecture.md | Agent Command Template |
| create_contract.md | agents/architect/commands/create_contract.md | Agent Command Template |
| delegate.md | agents/architect/commands/delegate.md | Agent Command Template |
| plan.md | agents/architect/commands/plan.md | Agent Command Template |
| propose_change.md | agents/architect/commands/propose_change.md | Agent Command Template |
| review_design.md | agents/architect/commands/review_design.md | Agent Command Template |
| summarize.md | agents/architect/commands/summarize.md | Agent Command Template |
| update_memory.md | agents/architect/commands/update_memory.md | Agent Command Template |
| config.json | agents/architect/config.json | Agent Config |
| runtime | agents/architect/runtime | Directory |
| .gitkeep | agents/architect/runtime/.gitkeep | Unknown |
| session.log | agents/architect/runtime/session.log | Unknown |
| contract_workflow.py | agents/contract_workflow.py | Python Source |
| git_ops.py | agents/git_ops.py | Python Source |
| pipeline.py | agents/pipeline.py | Python Source |
| programmer | agents/programmer | Directory |
| COMMANDS.md | agents/programmer/COMMANDS.md | Agent Commands |
| INBOX.md | agents/programmer/INBOX.md | Agent Inbox |
| MEMORY.md | agents/programmer/MEMORY.md | Agent Memory |
| ROLE.md | agents/programmer/ROLE.md | Agent Role |
| commands | agents/programmer/commands | Directory |
| implement_contract.md | agents/programmer/commands/implement_contract.md | Agent Command Template |
| config.json | agents/programmer/config.json | Agent Config |
| runtime | agents/programmer/runtime | Directory |
| session.log | agents/programmer/runtime/session.log | Unknown |
| progress.py | agents/progress.py | Python Source |
| reviewer | agents/reviewer | Directory |
| COMMANDS.md | agents/reviewer/COMMANDS.md | Agent Commands |
| INBOX.md | agents/reviewer/INBOX.md | Agent Inbox |
| MEMORY.md | agents/reviewer/MEMORY.md | Agent Memory |
| ROLE.md | agents/reviewer/ROLE.md | Agent Role |
| commands | agents/reviewer/commands | Directory |
| architecture_review.md | agents/reviewer/commands/architecture_review.md | Agent Command Template |
| review_contract.md | agents/reviewer/commands/review_contract.md | Agent Command Template |
| config.json | agents/reviewer/config.json | Agent Config |
| runtime | agents/reviewer/runtime | Directory |
| .gitkeep | agents/reviewer/runtime/.gitkeep | Unknown |
| session.log | agents/reviewer/runtime/session.log | Unknown |
| voice.py | agents/voice.py | Python Source |
| chat_architect.py | chat_architect.py | Python Source |
| contracts | contracts | Directory |
| .gitkeep | contracts/.gitkeep | Unknown |
| IMPLEMENTATION_CONTRACT_0001.md | contracts/IMPLEMENTATION_CONTRACT_0001.md | Implementation Contract |
| IMPLEMENTATION_CONTRACT_0002.md | contracts/IMPLEMENTATION_CONTRACT_0002.md | Implementation Contract |
| IMPLEMENTATION_CONTRACT_0003.md | contracts/IMPLEMENTATION_CONTRACT_0003.md | Implementation Contract |
| OWNER_INBOX.md | contracts/OWNER_INBOX.md | Markdown Document |
| README.md | contracts/README.md | Markdown Document |
| memory | memory | Directory |
| CHANGE_LOG.md | memory/CHANGE_LOG.md | Project Memory |
| CURRENT_STATE.md | memory/CURRENT_STATE.md | Project Memory |
| DECISIONS.md | memory/DECISIONS.md | Project Memory |
| OPEN_TASKS.md | memory/OPEN_TASKS.md | Project Memory |
| PROJECT_STATE.md | memory/PROJECT_STATE.md | Project Memory |
| TEMPLATE_ORIGINS.md | memory/TEMPLATE_ORIGINS.md | Project Memory |
| project | project | Directory |
| README.md | project/README.md | Markdown Document |
| checklist.md | project/checklist.md | Markdown Document |
| hello.md | project/hello.md | Markdown Document |
| hello_world.html | project/hello_world.html | Unknown |
| requirements.txt | requirements.txt | Unknown |
| source | source | Directory |
| README.md | source/README.md | Markdown Document |
| templates | templates | Directory |
| __init__.py | templates/__init__.py | Python Source |
| voice_module | templates/voice_module | Directory |
| README.md | templates/voice_module/README.md | Markdown Document |
| __init__.py | templates/voice_module/__init__.py | Python Source |
| audio_io.py | templates/voice_module/audio_io.py | Python Source |
| gemini_voice_bridge.py | templates/voice_module/gemini_voice_bridge.py | Python Source |
| live_voice_session.py | templates/voice_module/live_voice_session.py | Python Source |
| tests | tests | Directory |
| test_agent.py | tests/test_agent.py | Python Source |
| test_agent_profile.py | tests/test_agent_profile.py | Python Source |
| test_contract_workflow.py | tests/test_contract_workflow.py | Python Source |
| test_discovery_engine.py | tests/test_discovery_engine.py | Python Source |
| test_git_ops.py | tests/test_git_ops.py | Python Source |
| test_pipeline.py | tests/test_pipeline.py | Python Source |
| test_progress.py | tests/test_progress.py | Python Source |
| test_voice.py | tests/test_voice.py | Python Source |
| test_voice_module.py | tests/test_voice_module.py | Python Source |
| tools | tools | Directory |
| __init__.py | tools/__init__.py | Python Source |
| discovery_engine | tools/discovery_engine | Directory |
| README.md | tools/discovery_engine/README.md | Markdown Document |
| __init__.py | tools/discovery_engine/__init__.py | Python Source |
| generate_current_state.py | tools/discovery_engine/generate_current_state.py | Python Source |
