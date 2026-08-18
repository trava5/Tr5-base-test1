# Architectural Decisions

## ADR-001: Separation of thread and agent

- `vytvor_vlakno()` remains the low-level, backward-compatible API.
- `vytvor_agenta()` is a higher layer for role, memory, commands, and
  future runtime persistence.
- All agents use the same project root as their working directory.

## ADR-002: Two levels of memory

- Short-term memory is the active thread's history.
- Long-term memory lives in Markdown files.

## ADR-003: Contract logic merged with the Tr5 Platform Document Standard

Decided while migrating values from the Tr5-platform project
(`github.com/trava5/Tr5-platform`).

- Contract files are named `IMPLEMENTATION_CONTRACT_NNNN.md` (no hyphens,
  four-digit number, never reused) instead of the previous
  `CONTRACT - NNNN.md`.
- The visible contract structure matches the Tr5 Implementation Contract
  Template (Title/Purpose/Intent/Current State/Inputs/Outputs/Functional
  Requirements/Out of Scope/Acceptance Criteria/Architecture
  Review/Future Evolution/Completion Notes/Implementation
  Review/Lessons Learned) — with no change to the automation underneath:
  `contract_workflow.py` still drives status programmatically via the
  `CONTRACT-META` JSON, it just renders it into Tr5's vocabulary.
- Added a second review gate: Architecture Review (the contract is
  assessed before implementation, new status `DRAFT` →
  `ARCHITECTURE_CHANGES_REQUESTED` / `REJECTED` / `READY_FOR_PROGRAMMER`)
  alongside the existing Implementation Review (after implementation, no
  change in logic, just renamed `record_architect_review` →
  `record_implementation_review`).
- The history of both review gates is append-only
  (`architecture_review_rounds`, `implementation_review_rounds`) — older
  review rounds are never overwritten, only new ones are added. The
  contract's requirements (points, Purpose, Intent, ...) may only be
  rewritten via `revise_contract`, and only while the contract has not yet
  passed architecture review with verdict `ACCEPTED`.
- Kept the per-point granularity (assignment + acceptance criteria +
  programmer note + architect review + status at the level of each
  individual point) — Tr5 reviews the contract as a whole, but per-point
  tracking is more precise and agentCodex already had it working, so it
  remains as a deliberate extension beyond the Tr5 template.

## ADR-004: Third agent `reviewer` — independent architecture review

Decided while migrating values from the Tr5-platform project, as a
follow-up to ADR-003.

- Tr5 distinguishes three roles: Architect / Implementation Agent /
  Architecture Reviewer. After ADR-003, agentCodex only had two
  (`architect` ran architecture review on its own proposal). Added a
  separate `agents/reviewer/` profile (`config.json`, `ROLE.md`,
  `MEMORY.md`, `WORKING_STATE.md`, `COMMANDS.md`,
  `commands/architecture_review.md`, `permission_profile: review`) — the
  architect no longer approves its own contract.
- `Contract.reviewer` (default `"reviewer"`) determines who the contract is
  handed off to after creation/revision. `create_contract`/`revise_contract`
  set `handoff_to` to the reviewer instead of the architect.
  `record_architecture_review` is now reserved for status `DRAFT` (the
  earlier re-review from `ARCHITECTURE_CHANGES_REQUESTED` now goes through
  `revise_contract`, which returns the contract to `DRAFT` and hands it
  back to the reviewer).
- Added the `next_for_revision()` method — the architect's queue of
  contracts returned by the reviewer for rewriting, separate from
  `next_for_architecture_review()` (the reviewer's queue of new/revised
  drafts).
- Implementation review (after implementation) stays with `architect` —
  Tr5 itself does not unambiguously name a role for this step (the roles
  table in Tr5's `PRINCIPLES.md` and `DOCUMENT_STANDARD.md` §3.2 do not
  agree on this point), and in Tr5-platform's actual practice (see
  `CLAUDE.md`) the same party (Claude) plays both the Architect and the
  Reviewer role, so full separation would go beyond what Tr5 itself
  practices.

## ADR-005: Four general principles adopted from Tr5 PRINCIPLES.md into AGENTS.md

Decided while migrating values from the Tr5-platform project.

- Tr5's `PRINCIPLES.md` contains principles P14–P24, derived from specific
  incidents. Most of them (P14, P15, P16, P17, P22, P23) are tied to
  specific technologies and tools that agentCodex does not use and does
  not have (Discovery Engine, pyaudio, Google Calendar API, Gemini,
  `platform_shell`) — these are not adopted.
- Only four principles were adopted, rewritten into a general,
  technology-neutral form with no mention of the original incident or
  technology, as a new "Principles" section in `AGENTS.md`:
  - P19 → verify deferred imports too, not just module-level ones.
  - P20 → an uncommitted local fix is invisible to the next review.
  - P21 → isolation from real external systems must be structural, not
    just instructed.
  - P24 → a gitignore entry for a sensitive/temporary path is an
    acceptance criterion of the change that introduces it, not a
    follow-up cleanup.
- Decided not to create a separate, immutable "worldview" document (like
  Tr5's `FOUNDATIONAL_WORLDVIEW.md`) — agentCodex is a smaller, practical
  project; values are folded directly into `AGENTS.md` (rules) and
  `DECISIONS.md` (rationale and origin), with no extra documentation layer.
- P20 already has a real precedent in agentCodex: while working on
  ADR-003/ADR-004, uncommitted local changes were found in the repository
  (`chat_architect.py`, `agents/architect/runtime/thread.json`, `.idea/*`)
  predating this migration — exactly the scenario P20 describes.

## ADR-006: Light path for small fixes without a contract (P12)

Decided while migrating values from the Tr5-platform project. Purpose
adopted unchanged from Tr5: allow quick fixes such as a typo or a broken
link on the fly, without disrupting the contract workflow, while clearly
separating a mechanical fix from a case where the architecture needs to be
stopped and rethought.

- New "Light path for small fixes" section in `AGENTS.md`: mechanical
  fixes (typos, dead links, formatting, clearly incorrect text in
  documentation/comments) do not need a contract, as long as they do not
  introduce a new abstraction/file/dependency and do not change behavior
  or the public API. When in doubt, choose the contract.
- Every such fix is logged as one line in `memory/CHANGE_LOG.md` — a file
  that was unused and empty until now (see the agentCodex review, item
  1-4) now has a concrete purpose.
- `agents/programmer/ROLE.md` got an explicit exception to the "do not
  edit long-term memory directly" rule for `memory/CHANGE_LOG.md` —
  otherwise the new `AGENTS.md` section and the existing role boundary
  would directly conflict. Other memory files (`DECISIONS.md`,
  `PROJECT_STATE.md`, `OPEN_TASKS.md`, `agents/<agent>/MEMORY.md`) are not
  affected by this exception — those are still only written to through
  architect-approved `memory_updates` during implementation review.
- No code-level enforcement layer (unlike `ContractStore`) — the light
  path is, by nature, outside the contract state machine; direct file
  edits have no such mechanism, just as in Tr5.

## ADR-007: Tr5's directory structure (`artifacts/foundation`, `tools/`, `projects/`) is not adopted

Decided while migrating values from the Tr5-platform project. agentCodex
has its own, already established and working structure (`agents/<name>/`,
`contracts/`, `memory/`, code at the project root) and it is kept
unchanged. Values and rules are adopted (contract logic, roles, principles
— ADR-003 through ADR-006), not the physical layout of directories. This
is consistent with ADR-005 (no separate `artifacts/foundation` layer for a
worldview) — agentCodex does not adopt Tr5's "platform vs. tools vs.
projects" layering, because it does not itself host nested projects.

## ADR-008: Formalizing the naming convention from the Tr5 Document Standard

Decided while migrating values from the Tr5-platform project. agentCodex
already followed the convention in practice (`UPPERCASE.md` for
ROLE/MEMORY/COMMANDS/WORKING_STATE/AGENTS/README,
`lowercase_with_underscores` for directories and code), it just was never
written down as a rule — it was a coincidence, not a deliberate choice.

- New "Naming convention" section in `AGENTS.md`:
  `lowercase_with_underscores` for directories/code,
  `UPPERCASE_WITH_UNDERSCORES.md` for rule-bearing documents, no
  diacritics or hyphens in names (prose, comments, and commit messages
  keep diacritics), a four-digit, never-reused contract number.
- Verified with a repository scan that no existing file/directory in the
  project (other than `.venv`/`__pycache__`, which are not subject to the
  convention) violates the rule — this is not a retroactive cleanup, just
  writing down what already held true.
- The rule was also added to `agents/architect/ROLE.md` (a new
  file/directory proposed in a contract), `agents/programmer/ROLE.md`
  (what the programmer itself names), and to the checklist in
  `agents/reviewer/commands/architecture_review.md` — so it holds even
  when `AGENTS.md` itself may not be part of a given provider's context
  (Codex/Claude SDK), while `ROLE.md` always is
  (`agent_profile.py::build_agent_instructions`).

## ADR-009: Project documentation and generated text translated to English

Decided after a discussion outside this project, applied here as well:
all `.md` files, and any Python code that generates `.md`-like or
agent/user-facing text, are written in English — matching the language
Tr5-platform's own `.md` files are written in.

- Scope: every `.md` file in the repository (governance docs, `ROLE.md`/
  `MEMORY.md`/`WORKING_STATE.md`/`COMMANDS.md`/`INBOX.md` for every agent,
  command prompts, `README.md` files, `memory/*.md`, this file), plus the
  Python-generated text that used to be Czech: `contract_workflow.py`
  (`render_contract` section labels, exception messages, docstrings,
  `notify()` event text), `agent.py`, `agent_profile.py`, and
  `agent_console.py` (help text, status/error messages, docstrings). Test
  files were updated to match the new English strings and messages.
- Explicitly out of scope: Python identifiers (function, variable, class,
  and attribute names, e.g. `vytvor_agenta`, `poloz_dotaz`, `vytvor_vlakno`,
  `zavri`, `nazev`). Renaming those is a public-API/code-style decision,
  not a documentation-language decision, and was not part of what was
  asked; changing them would be a much larger, higher-risk, unrelated
  change.
- Conversational language is unchanged: `AGENTS.md`'s "Communicate in
  Czech" rule stays in force for actual conversation with an agent (or
  with Claude in this migration) — only the written artifacts changed
  language, not how people and agents talk to each other.
- `PRINCIPLES.md` (see the "Principles" discussion, P1–P13 and P18) is
  created directly in English once that work resumes; it did not need
  translating since it did not exist yet at the time of this decision.

## ADR-010: Python identifiers translated to English

Supersedes the "explicitly out of scope" note in ADR-009: Czech is reserved
strictly for live conversation with agents/Claude; nothing else — including
internal code identifiers — stays Czech.

- Renamed across `agent.py`, `agent_profile.py`, `agent_console.py`,
  `chat_architect.py`, `example_architect.py`, and both test files:
  `vytvor_vlakno`→`create_thread`, `vytvor_agenta`→`create_agent`,
  `poloz_dotaz`→`ask`, `spust_prikaz`→`run_command`, `zavri`→`close`,
  `nazev`→`name`, `AgentVlakno`→`AgentThread`, `CodexVlakno`→`CodexThread`,
  `ClaudeVlakno`→`ClaudeThread`, `AgentConfig.nacti`→`.load`,
  `.over`→`.validate`, `.modely_pro`→`.models_for`, and the internal
  `_over_*`/`_codex_opravneni`/`_claude_opravneni`/`prihlaseni*`/
  `inicializuj_prihlaseni`/`_zavreno`/`_spustit_loop`/`loop_bezi`/`_spusti`/
  `_poloz_dotaz_async` helpers and locals.
- Updated references in `README.md`, `agents/architect/MEMORY.md`,
  `agents/architect/WORKING_STATE.md`, `memory/PROJECT_STATE.md`, and
  `AGENTS_SUGGESTIONS.md` to the new names.
- ADR-001 and ADR-009 are left as-is (append-only); their text reflects the
  names that were current at the time each was written.
- Verified with `py_compile` on all `.py` files and a full pytest run.

## ADR-011: Standalone PRINCIPLES.md, always loaded in full

Created `PRINCIPLES.md` as the single home for the project's operating
principles (see the "Principles" discussion, A7). Resolves both the "where
do principles live" question and the AGENTS.md-may-not-load-automatically
risk already known from ROLE.md (see ADR context around the naming
convention).

- `PRINCIPLES.md` follows the Tr5 format: Purpose, Revision Process (Status:
  Active / Under Review / Revised / Deprecated, append-only, never
  renumbered), then numbered principles. Numbering is local to this
  document (assigned in adoption order), with a `Source: Tr5 P#` note for
  traceability where a principle comes from Tr5.
- The 4 principles already adopted in C4 (Tr5 P19/P20/P21/P24, previously
  living directly in `AGENTS.md`) were moved into `PRINCIPLES.md` as P2-P5,
  so there is one canonical list instead of two. `AGENTS.md`'s "Principles"
  section is now a one-line pointer.
- P1 in `PRINCIPLES.md` is the already-agreed merge of Tr5 P1 + P2
  ("architecture defines direction, implementation reflects today's
  understanding").
- Delivery mechanism: `agent_profile.py::build_agent_instructions()` now
  always loads the full content of `PRINCIPLES.md` into every agent's
  instructions (new `AgentProfile.load_principles()`, new
  `AgentProfileConfig.load_principles` flag, default `True`), the same
  guaranteed way `ROLE.md` is loaded — chosen over a pointer-only reference
  or a short always-loaded summary, to make sure principles reach the model
  regardless of provider-side `AGENTS.md` auto-loading behavior.
- Remaining Tr5 candidates (P3-P13, P18) are being reviewed one at a time
  and appended to `PRINCIPLES.md` as each is agreed.

## ADR-012: Tr5 P3 ("Discovery observes reality") deferred, not adopted

Tr5 P3 states that a tool whose purpose is to describe current system state
(the Discovery Engine, generating `TR5_CURRENT_STATE.md`) must only report
what exists, never prescribe structure. agentCodex has no Discovery Engine
and none is planned.

- The underlying need P3 protects against — drift between assumed and
  actual repo state — is already covered here by a different mechanism:
  git history itself, `memory/CHANGE_LOG.md` (light-path fixes),
  `memory/PROJECT_STATE.md`, `memory/DECISIONS.md`, and each contract's own
  manually-written "Current State" section.
- Building an automated Discovery Engine now, without a concrete case of
  drift actually occurring, would itself violate P1 (implement today's
  understanding, not tomorrow's assumption) and P13 (standards are
  extracted from a working system, not invented in advance) — both already
  adopted.
- Decision: not added to `PRINCIPLES.md`. Deferred, not rejected — revisit
  if agentCodex's scale or number of concurrent contributors ever produces
  a real, observed mismatch between assumed and actual repo state.

## ADR-013: Tr5 P18 ("not every entity is a platform Artifact") not adopted

Tr5 P18 distinguishes a "platform Artifact" (something with its own
identity, lifecycle, and review history at the platform level — a
Contract, a foundational document, a project) from an implementation
detail inside one (e.g. a single action function), so that not every
internal detail gets full-ceremony tracking.

- The term "Artifact" comes from Tr5's `FOUNDATIONAL_WORLDVIEW.md` ontology,
  which this project already declined to adopt as a separate document (C5).
- The underlying concern — don't apply contract-level ceremony to
  something smaller than a meaningful unit of work — is already covered in
  spirit by P14 (process weight matches decision weight) and by how a
  contract's points are scoped (a point covers a feature, not each
  individual file or function inside it).
- Unlike P9/P11 (P11/P13 in this document), there is no observed agentCodex
  case where over-granular contract tracking was actually attempted or
  caused a real problem.
- Decision: not added to `PRINCIPLES.md`, per P15 (standards are extracted
  from a working system, not invented in advance) — no demonstrated need
  yet. This closes the initial A7 review of Tr5 P1-P13 and P18; P1-P13
  produced this project's own P1-P15 (see ADR-011, ADR-012 above).

## ADR-014: Principle revision process, and PRINCIPLES.md as an allowed memory target

Resolves A8 (how principles get revised, tied to the `Status` field
already defined in `PRINCIPLES.md`'s Revision Process). Not on a fixed
schedule or a full audit after every contract — that would itself violate
P14/P15 — but triggered when a real contract (typically during
implementation review, sometimes architecture review) actually runs into
a conflict with a principle, the same way Tr5's own P19-P24 were each
extracted from a specific incident.

- `contract_workflow.py`'s `ALLOWED_MEMORY_TARGETS` now includes
  `PRINCIPLES.md` (previously only `memory/*.md` and
  `agents/*/(MEMORY|WORKING_STATE).md`), so the architect (or reviewer) can
  propose a review entry via `memory_updates` during review, the same
  mechanism already used for other memory files. This is a change to a
  write-permission boundary, not a light-path fix, so it is recorded here
  rather than in `memory/CHANGE_LOG.md`.
- `append_memory()` only appends a timestamped entry — it does not edit a
  specific principle's `Status` field in place. A proposed entry describes
  the conflict and which principle it concerns; formalizing the actual
  status change and rewriting the principle's text is done deliberately
  afterward, referencing that entry — mirroring how this document's own
  principles were drafted through discussion rather than generated
  automatically.
- Documented directly in `PRINCIPLES.md`'s "Revision Process" section
  ("When a principle gets reconsidered"), `README.md`'s list of allowed
  memory-update targets, and a new test
  (`test_allows_principles_memory_target`).
- Verified with `py_compile` and a full pytest run (14/14 passing).

## ADR-015: Tr5's README standard adopted for future sub-units, not the root README

Resolves A9. Tr5's `DOCUMENT_STANDARD.md` defines a minimal, rarely-changing
README shape for every significant Artifact/tool: `# <Name>` /
`## Purpose` / `## Current capabilities (vX.Y)` / `## Current limitations`
/ `## Planned evolution`.

- Adopted for future README files describing a self-contained unit inside
  this repository (e.g. `project/README.md`, and any future
  `agents/<name>/README.md` if one is ever added) — see `project/README.md`
  for the first real use.
- Not applied to the root `README.md`: Tr5's standard targets one Artifact
  among many inside a multi-project platform, describing responsibility
  rather than usage. agentCodex's root README currently serves a different,
  still-needed role for a single project — installation, login, usage
  examples, permissions, roles — that a minimal status summary would not
  replace. Revisit only if the root README's role actually changes.

## ADR-016: `project/` directory added; this repository is the reusable starting state for new projects

Following up on the wider direction discussed after A9: this repository is
copied as the starting state ("point zero" — governance, principles,
agentic framework already set up) for each new project; each copy then
lives its own life (its own `.md` files, its own memory), independent of
other copies.

- Added `project/` at the repository root, per `project/README.md` (using
  the ADR-015 README standard): holds the actual application code being
  built through the contract pipeline, kept separate from the
  framework/governance layer (`agent.py`, `agent_profile.py`,
  `contract_workflow.py`, `agents/`, `memory/`, `contracts/`, `AGENTS.md`,
  `PRINCIPLES.md`). Referenced from `AGENTS.md`.
- Confirmed unchanged: the review order built in C1/C3 (architect drafts →
  reviewer's architecture review BEFORE implementation → programmer →
  architect's implementation review AFTER, architect never approves its
  own proposal). A description of the pipeline in conversation used a
  shorthand order (contract → programmer → reviewer → architect); this did
  not mean to reopen C3.
- Confirmed human-approval point: the owner approves before the architect
  hands a contract off to the reviewer; after that, the existing gates
  (architecture review, implementation) proceed via the existing
  `agent_console.py` commands. Automatically chaining those steps into one
  unattended run (a "run" mode that only stops again once the pipeline
  returns to the architect) was discussed and explicitly deferred, not
  built now — directory structure and other foundations come first.
- Agent memory scope confirmed as already-intended: an agent's own
  conversational memory only needs to last for the current task/session;
  once a contract is hand off, the contract file itself is sufficient
  context for the next agent. This matches the existing default
  (`persistent_thread: false`) rather than requiring a new mechanism.
- Still open, not decided here: what the architect's own longer-lived
  memory should look like across sessions/contracts (distinct from the
  per-task point above).

## ADR-017: Architecture review can also propose memory_updates

Resolves the "architect's long-term memory" open item from ADR-016. An
agent (architect or reviewer) does not need to retain the conversation
behind a contract — the contract itself is the durable record of that
decision. What still needs a home is a fact that surfaces during review
and is worth keeping *beyond* that one contract (a recurring risk, a
principle worth revisiting, project-wide state) — the existing
`memory_updates` mechanism (`ALLOWED_MEMORY_TARGETS`: `memory/*.md`,
`agents/<agent>/(MEMORY|WORKING_STATE).md`, `PRINCIPLES.md`, see ADR-014)
already exists for exactly this, but was previously only reachable from
implementation review (`record_implementation_review`).

- `record_architecture_review()` now accepts an optional `memory_updates`
  parameter, applied via the existing `append_memory()` the same way
  implementation review already does. This was a gap, not a new
  mechanism — architecture review is precisely the point where a reviewer
  is likely to notice something worth remembering, before implementation
  even starts (the same way Tr5's own P19-P24 were each extracted from a
  specific review finding).
- `agents/reviewer/commands/architecture_review.md` now documents the
  optional `memory_updates` field, with the same guidance already given
  elsewhere: don't store the discussion, only a fact worth keeping.
- `agent_console.py::run_architecture_review()` forwards
  `memory_updates` from the reviewer's response, mirroring
  `review_next()`.
- `agents/architect/MEMORY.md` (and any agent's private `MEMORY.md`) is
  not retired and not scope-restricted — it stays one of the allowed
  targets, written to only when a review actually surfaces something
  worth keeping, not maintained as a standing reference document. This
  also explains why it went stale before: nothing wrote to it in the
  normal flow of work.
- New test: `test_architecture_review_accepts_memory_updates`. Verified
  with `py_compile` and a full pytest run (15/15 passing).

## ADR-018: `/new` and `/revise` auto-chain the pipeline through to the architect

Previously `agent_console.py` required three manual commands per contract
(`/new`, then `/work`, then `/review`) even on the happy path. Per the
owner's description of the intended workflow: approval happens once, when
the owner is satisfied enough with the discussed intent to issue `/new` (or
`/revise`) — from there the pipeline should run unattended and stop again
only once it returns to the architect, where the owner and architect
discuss the outcome together.

- `create_contract()` and `revise_contract()` now call the reviewer's
  architecture review as before, then, only if the verdict produced
  `READY_FOR_PROGRAMMER`, automatically continue through the programmer's
  implementation and the architect's implementation review via a new
  `continue_pipeline()` helper. `CHANGES_REQUESTED`/`REJECTED` from
  architecture review already stop at the architect/owner today — nothing
  to chain, no change there.
- The chain always stops once implementation review returns — whether
  `APPROVED` or `CHANGES_REQUESTED` — rather than automatically retrying
  the programmer. Every return to the architect is a checkpoint for the
  owner, not a loop the system should keep running unattended; a second
  attempt (if requested) goes back through `/work`/`/review` deliberately,
  same as before.
- `implement_next()` and `review_next()` now accept an optional `number`
  parameter (chained calls target the specific contract just handed off,
  instead of picking "whatever is next in the queue," which could have
  grabbed an unrelated contract if more than one was in flight). Bare
  `/work` and `/review` (no argument) keep the old queue-picking behavior
  as a manual override; `/work <n>` and `/review <n>` now also work
  directly on a specific contract.
- If any step in the chain fails (e.g. invalid JSON from a model), it
  raises the same way `/work`/`/review` already did — nothing partially
  written, the contract stays in its last valid state, the owner resumes
  manually via `/work`/`/review` once the cause is clear. No new
  error-handling behavior was introduced.
- Explicitly out of scope for now (per the owner): letting `agent_console.py`
  itself launch the very first `/new` unattended, or any change to where
  the owner-approval point sits. Only the already-approved middle of the
  pipeline was automated.
- New tests in `tests/test_agent_console.py`
  (`test_create_contract_chains_through_to_implementation_review`,
  `test_create_contract_stops_when_changes_requested_at_architecture_review`,
  `test_create_contract_stops_after_changes_requested_implementation_review`),
  using a scripted fake agent (`.run_command()` only) instead of a real
  provider thread. Verified with `py_compile` and a full pytest run
  (18/18 passing).

## ADR-019: Git checkpoints wired into the pipeline (before implementation, after approval)

Per the owner's direction: the pipeline now commits and pushes at two
points, giving every contract a git-level "before" and "after" of the
programmer's work — a concrete implementation of `PRINCIPLES.md` P3
("an uncommitted local fix is invisible to the next review").

- New `git_ops.py` (`commit_and_push(project_root, message)`): stages
  everything (`git add -A`), checks via `git diff --cached --quiet`
  whether there is anything to commit (returns `False`, not an error, if
  the tree is already clean), commits, and pushes. Any git failure
  (including a failed push) raises `RuntimeError` — the caller does not
  proceed on top of an unsaved state, same policy as the rest of the
  pipeline (nothing partially done, no silent retry).
- `continue_pipeline()` (`agent_console.py`) now commits as
  `CONTRACT_NNNN` right after architecture review produces
  `READY_FOR_PROGRAMMER`, before calling the programmer — the last clean
  checkpoint before implementation starts.
- New `/commit <n>` console command runs `commit_approved_contract()`,
  which requires the contract's status to be `APPROVED` (refuses
  otherwise) and commits as `CONTRACT_NNNN - IMPLEMENTED`. This is
  deliberately a separate, explicit, owner-issued command rather than
  something `review_next()` triggers automatically on `APPROVED` — the
  owner explicitly wants to discuss the implementation review result with
  the architect first and only commit once they agree it is sufficient,
  not fold that judgment into an automatic status check.
- Message format follows the owner's own wording literally
  (`CONTRACT_NNNN`, not `IMPLEMENTATION_CONTRACT_NNNN` as used elsewhere)
  — a deliberate, narrower, git-log-specific label, not a naming
  convention change (`AGENTS.md`'s naming convention still governs file
  and identifier names, not commit message text).
- New `tests/test_git_ops.py`, exercising `commit_and_push()` against a
  real local git repository and a real (local, bare) remote — commit and
  push both verified to actually happen, not mocked. New tests in
  `tests/test_agent_console.py` verify `continue_pipeline()` and
  `commit_approved_contract()` call `commit_and_push()` with the right
  message at the right point, using a fake in place of `git_ops` (no real
  repository needed for the console-level tests). Verified with
  `py_compile` and a full pytest run (23/23 passing).

## ADR-020: `bod-nula` is a periodic snapshot; `agentCodex` stays the dev repo

Checked whether `github.com/mtravnicekarmex/bod-nula.git` (a separate
repository the owner pushed a copy of this project's content to, under a
new name) was a faithful, clonable "point zero" for future projects. It
was — content was file-for-file identical to `agentCodex` (only the
README title was intentionally changed) and 23/23 tests passed from a
fresh clone. Found and fixed the same pre-existing hygiene gap in both
repositories: `.pytest-tmp/` (25 leftover test-fixture files, `bod-nula`
only) and `.idea/` (7 files, both repos, including two conflicting
`.iml` files in `bod-nula` — direct evidence of drift from copying without
cleanup) were tracked in git despite `.gitignore` never covering them
(this is revision point 1-2 from the very first review, previously
deferred). Fixed in both: `.gitignore` now excludes both paths, and the
already-tracked files were untracked via `git rm -r --cached` (owner
connected the `bod nula` local folder for direct access, same as
`agentCodex`, rather than being handed manual commands).

- Decided relationship going forward: `agentCodex` remains the framework's
  own development repository — this is where governance, principles, and
  the agentic pipeline itself keep evolving. `bod-nula` is a periodic,
  manually-refreshed snapshot of `agentCodex`, meant to be cloned as the
  clean starting point for an actual new project; once cloned for a real
  project it lives its own independent life (own `.md` files, own memory,
  no further syncing back). `bod-nula`'s own `README.md` now states this
  explicitly, pointing back to this ADR.
- Practical note for future snapshots: refresh `bod-nula` from a clean
  `agentCodex` state (tests passing, no local IDE/test-run cruft) rather
  than an arbitrary local checkout, so this specific problem does not
  recur on the next refresh.
- A stale `.git/index.lock` was left behind by `git rm --cached` in both
  local folders (the same mounted-filesystem permission quirk seen before
  with `rm`/`mv`) — harmless to read-only git commands, but needs manual
  deletion before the owner's next local `git add`/`commit` in either
  folder.
- Confirmed explicitly: this connected `bod nula` folder/repo stays a
  clean template forever. The first project (and every subsequent one) is
  started from a fresh, separate clone of `bod-nula` into its own new
  folder/repo — never by developing directly inside this connected copy.
- Refresh procedure for future updates (manual, triggered by the owner,
  not automated — no tooling built for this yet, per P15, until the
  manual process actually proves painful): (1) confirm `agentCodex` is
  clean and its tests pass; (2) copy the framework/governance layer from
  `agentCodex` into the connected `bod nula` folder, excluding `.git/`,
  `.venv/`, cache directories, `.idea/`, `.env`, and `project/` (which
  stays the empty placeholder in `bod-nula` regardless of what
  `agentCodex`'s own `project/` contains by then); (3) manually reapply
  `bod-nula`'s two deliberate differences from `agentCodex` (the README
  title and this ADR's snapshot-role note), since the copy would otherwise
  overwrite them; (4) the owner reviews the diff and commits/pushes
  `bod-nula` themselves, same as today.

## ADR-021: Root directory decluttered to one entry point; framework code moved into agents/

Per the owner's direction: the repository root should hold exactly one
`.py` file — the one used to open a window onto the architect — with
everything else the framework needs living under `agents/`. The owner
also no longer wants a multi-agent console; going forward they only ever
talk to the architect directly, with the reviewer and programmer working
purely as internal pipeline agents.

- Moved into a new `agents` Python package (new `agents/__init__.py`,
  alongside the existing per-role profile directories
  `agents/architect/`, `agents/reviewer/`, `agents/programmer/`, which are
  data directories, not Python modules, and coexist without conflict):
  `agents/agent.py` (from root `agent.py`), `agents/agent_profile.py`
  (from root `agent_profile.py`, import updated to `from .agent import
  ...`), `agents/contract_workflow.py` (from root `contract_workflow.py`,
  unchanged otherwise), `agents/git_ops.py` (from root `git_ops.py`,
  unchanged).
- Fixed a real bug the move would otherwise have introduced:
  `agent.py`'s `WORKSPACE = Path(__file__).parent.resolve()` assumed the
  file lives at the repository root. Moved one level down into
  `agents/agent.py`, that same expression would have resolved to
  `agents/` instead of the actual project root — silently breaking every
  default (`.env` lookup, agent profile directories, provider `cwd`).
  Fixed to `Path(__file__).parent.parent.resolve()`.
- New `agents/pipeline.py` absorbs `agent_console.py`'s orchestration
  logic verbatim (`create_contract`, `revise_contract`,
  `continue_pipeline`, `run_architecture_review`, `implement_next`,
  `review_next`, `commit_approved_contract`, `print_status`,
  `show_inbox`), plus two new functions: `status_text()` and
  `opening_briefing()`, used to ground the new entry point's opening
  greeting in the real contract queue and the architect's real inbox
  content, rather than a static or guessed greeting (see below).
- `agent_console.py` (multi-agent console: `/chat <agent>` switching,
  direct chat with reviewer/programmer) is retired — no longer part of
  the intended workflow. `example_architect.py` (a pre-pipeline demo
  script) is removed — fully superseded by the real pipeline and the new
  entry point, with no remaining purpose.
- The single root entry point, `chat_architect.py`, is rewritten: creates
  all three agents internally (architect, reviewer, programmer — the
  latter two never exposed for direct chat), sends `opening_briefing()`
  to the architect as its first message so its opening greeting reflects
  real state ("what's on the agenda today" grounded in the actual
  contract queue and inbox, not a guess — see `PRINCIPLES.md` P4/P6),
  then a plain input loop: free text goes straight to the architect;
  `/new`, `/revise`, `/work`, `/review`, `/commit`, `/status`, `/inbox`,
  `/help`, `/exit` remain available alongside the conversation, calling
  into `agents/pipeline.py`.
- Tests updated to the new import paths
  (`agents.agent`, `agents.agent_profile`, `agents.contract_workflow`,
  `agents.git_ops`); `tests/test_agent_console.py`'s tests moved to new
  `tests/test_pipeline.py` (importing `agents.pipeline`), plus one new
  test for `opening_briefing()`. Verified with `py_compile` and a full
  pytest run (24/24 passing), including confirming
  `agents.agent.WORKSPACE` resolves to the true project root after the
  move.
- The connected-folder sandbox cannot delete files (a known limitation —
  see the ADR-013-era note on `git rm`/`mv`). The retired root files
  (`agent.py`, `agent_profile.py`, `contract_workflow.py`, `git_ops.py`,
  `agent_console.py`, `example_architect.py`, `tests/test_agent_console.py`)
  were overwritten with a short redirect note each, pointing here and
  asking the owner to `git rm` them manually.
- This is `agentCodex`-only for now, per the owner's own framing
  ("agentCodex jako vývojové repo") — `bod-nula` is refreshed from this
  state later, following the ADR-020 refresh procedure, once the owner
  judges the project ready to deploy.

## ADR-022: `project/` is the default write scope once it holds real code

The owner asked for a check: once `bod-nula` is cloned for a new project
and `project/` starts holding that project's real code, is it clearly
stated anywhere that contract work is scoped to `project/`, with the
framework/governance layer only in scope when a contract explicitly calls
for it? It was not — three places actually said or implied the opposite:

- `AGENTS.md` said "The working directory is the project root," with no
  mention of `project/` scoping at all.
- `agents/agent_profile.py`'s `build_agent_instructions()` always injects
  "Work across the whole project. Do not limit yourself to your own
  subfolder under `agents/`." into every agent's instructions — read
  guidance that, unqualified, doubles as write guidance.
- `agents/architect/ROLE.md` had no scoping statement either, and its
  "Allowed memory targets" list was already stale (missing
  `PRINCIPLES.md`, added to the actual `ALLOWED_MEMORY_TARGETS` code list
  back in ADR-014 but never propagated here).

Fixed, owner confirmed ("ano"):

- `AGENTS.md`: replaced the "working directory is the project root" line
  with an explicit rule — once `project/` holds real code, contract work
  is implemented there by default; touching `agents/*.py`,
  `chat_architect.py`, or a governance `.md` file (`AGENTS.md`,
  `PRINCIPLES.md`, `ROLE.md`, `COMMANDS.md`) is in scope only when the
  contract explicitly calls for it; reading outside `project/` for
  context stays unrestricted — this is a write scope, not a read scope.
  When in doubt, a change outside `project/` gets its own contract point
  rather than silent inclusion.
- `agents/agent_profile.py`: reworded the always-injected "Technical
  profile" text to split reading (unrestricted, across the whole project)
  from writing (scoped to `project/` by default, per the same rule as
  above), so every agent gets this in its instructions regardless of
  role.
- `agents/architect/ROLE.md`: added `PRINCIPLES.md` to "Allowed memory
  targets", matching the code.

Verified: `py_compile` on the touched `.py` files, and a full pytest run
(24/24 passing; had to pass `--confcutdir=tests` to route around the
still-unreadable `.pytest-tmp` directory at the repo root — see the open
git thread below, unrelated to this change).

## ADR-023: `login_claude()` failed to trigger login on a fresh clone

The owner's first real run of a `bod-nula` clone (`chat_architect.py` on a
brand-new project, before ever running `claude auth login`) crashed instead
of prompting for login:

```
RuntimeError: Could not verify Claude login status: {
  "loggedIn": false,
  "authMethod": "none",
  "apiProvider": "firstParty"
}
```

Root cause: `agents/agent.py::login_claude()` treated any non-zero exit
code from `claude auth status --json` as a failure to check status at all,
raising immediately without looking at stdout. In practice the CLI exits
non-zero for the ordinary "not logged in" case too, while still printing
valid JSON with `loggedIn: false` — confirmed by running the command
directly (`claude auth status --json` → exit 1, valid JSON body). So the
one case the function exists to handle (a brand-new machine, nobody has
run `claude auth login` yet) was exactly the case it crashed on instead of
walking the owner through login.

Fixed: `login_claude()` no longer branches on the exit code. It parses
`stdout` and only trusts the result if it is a JSON object containing a
`loggedIn` key (regardless of exit code) — `loggedIn: true` returns
immediately, `loggedIn: false` (or missing/absent) falls through to the
existing `claude auth login --claudeai` flow. Only a body that is empty or
does not parse as that shape is treated as a real failure to verify status
(covers an actual CLI crash, a changed output format, etc.).

Added `tests/test_agent.py` (new file, none existed for this module
before) covering all four paths via a monkeypatched `_run_claude_cli`:
already logged in; not logged in with non-zero exit (the bug's exact
scenario) triggering and completing the login flow; unparseable/empty
status output raising with the original detail; and the login flow itself
failing. Full suite: 28/28 passing.

This is a framework-layer bug (`agents/agent.py`), not project code, so it
was fixed directly here rather than treated as light-path — changes
behavior, and light-path is explicitly for changes that do not (see
`AGENTS.md`). Synced to `bod-nula` the same way as the ADR-021/ADR-022
refresh, since every future clone hits this exact code path on its very
first run. The owner's already-cloned project needs the same one-function
patch applied by hand, since that folder is not connected here.

## ADR-024: `bod-nula` reset to a clean point-zero template; `source/` added for migrating an existing project

The owner used this specific clone (`bod-nula`) directly for real work —
`project/` grew a real SMS/Streamlit application through four implemented
contracts (`CONTRACT_0001`–`CONTRACT_0004`) — instead of cloning it first,
the way ADR-020 assumes ("each cloned copy lives its own independent
life"). The owner now wants a genuinely empty starting point again, to
`git clone` fresh for the next (different) project: migrating an existing
codebase onto this pipeline.

- Local working tree and history reset to the last commit before
  `CONTRACT_0001` (`6b7ef57`, the ADR-023 login fix) — framework at its
  current, most up-to-date state (ADR-021's `agents/` layout,
  `chat_architect.py` entry point, ADR-022's `project/`-scoping rule,
  ADR-023's login fix), with no project-specific content: `project/`,
  `contracts/`, and every `agents/<name>/INBOX.md` /`MEMORY.md`/
  `WORKING_STATE.md` back to template-empty.
- Added `source/` at the repository root, per `source/README.md` (using
  the ADR-015 README standard): holds the original/input source of the
  project being migrated, copied in as-is and kept untouched — a
  read-only reference the architect and programmer read while drafting
  and implementing contracts. `project/` keeps its existing role
  unchanged (ADR-016): migrated/rewritten code lands there, contract by
  contract, while `source/` stays exactly as copied in. Referenced from
  `AGENTS.md`, `README.md`, and `project/README.md`.
- "Untouched" is a documentation-level convention (`AGENTS.md`), not a
  technical write restriction — same caveat as ADR-022's `project/`
  scoping.
- The real SMS/Streamlit application built on `bod-nula` (`CONTRACT_0001`
  through `CONTRACT_0004`, still on `origin/master`) was deliberately left
  alone — this reset only changed the owner's local working copy, nothing
  was pushed, so that work stays fully recoverable from git history /
  `origin/master` if ever needed again.

## ADR-025: `commit_and_push()` refuses to push while `origin` is still a template repo

Root cause of the ADR-024 situation: cloning `bod-nula` (or now `bod_zero`)
for a new project and never redirecting `origin` was only a documented
step, not enforced anywhere. The pipeline's automatic git checkpoints
(ADR-019, `commit_and_push()` in `agents/git_ops.py`) push to whatever
`origin` happens to be — so a forgotten manual step silently sent real
project work straight back into the template repository. Per
`PRINCIPLES.md` P4 ("isolation must be structurally tied to the mechanism,
not just instructed"), a documented step alone was not going to be enough
a second time.

- Added `TEMPLATE_ORIGINS.md` at the repository root (tracked, one origin
  URL per line, `#` comments): the list of git remotes considered
  point-zero templates — currently `bod_zero` and `bod-nula`.
- `commit_and_push()` now runs `_refuse_template_origin()` after the local
  commit but before `git push`: reads `TEMPLATE_ORIGINS.md`, resolves the
  actual `origin` remote URL, normalizes both (case, trailing `/`,
  trailing `.git`) and raises `RuntimeError` with an actionable message if
  they match. The local commit still happens either way — only the push
  is refused, the same as any other push failure (`PRINCIPLES.md` P3: the
  checkpoint is not lost, the caller just sees the error and stops).
- If `TEMPLATE_ORIGINS.md` is absent, or `origin` cannot be resolved (no
  such remote), the check is a silent no-op — existing callers (including
  the test suite's throwaway repositories) are unaffected.
- README.md gained a "Starting a new project from this template" section
  (clone → create a new dedicated repo → `git remote set-url origin
  <new-repo-url>`); `AGENTS.md` gained the corresponding rule. New tests
  in `tests/test_git_ops.py` cover both the refusal (local commit made,
  remote unchanged) and the non-match case (push proceeds normally).
- This is deliberately generic (a plain list of URLs, not
  `bod_zero`-specific logic) so any future point-zero snapshot repo can be
  added to the list without touching code.

## ADR-026: `GIT_REPO` in `.env` auto-redirects `origin` on startup

ADR-025's guard only blocks the mistake; it doesn't make the correct step
easier. The owner wanted the redirect itself automated rather than a
manual `git remote set-url` command to remember for every new project.

- Added `GIT_REPO=` to `.env` and `.env.example` (empty by default, left
  blank in the template itself). `.env` is already per-clone and
  gitignored, matching how `PROVIDER_*`/`MODEL_*` are already project-local
  config, not something ADR-025's `TEMPLATE_ORIGINS.md` (which is tracked
  and shared) could hold.
- New `sync_origin_from_env(project_root, git_repo)` in `agents/git_ops.py`:
  no-op if `git_repo` is empty; if `origin` doesn't exist yet, adds it; if
  it exists and differs (compared with the same normalization as
  ADR-025's guard), redirects it via `git remote set-url`; no-op if it
  already matches. Returns a message describing what changed, or `None`.
- `chat_architect.py::main()` calls it right after `AgentConfig.load()`
  on every run, using `GIT_REPO` from the now-loaded `.env`, wrapped in a
  try/except that prints a warning and continues rather than blocking
  startup — a redirect failure (e.g. an invalid URL) should not prevent
  talking to the architect, since ADR-025's push-time guard is the actual
  safety net either way.
- End-to-end flow for a new project: clone → create a new empty repo →
  fill in `GIT_REPO` in `.env` → run `chat_architect.py` once (origin
  redirects itself, printed to confirm) → the pipeline's git checkpoints
  now push to the right place. Leaving `GIT_REPO` blank is still safe,
  just inconvenient: ADR-025 keeps blocking pushes to the template until
  `origin` is redirected, whether that happens via this automation or by
  hand.
- New tests in `tests/test_git_ops.py`: empty/blank `git_repo` is a no-op,
  redirecting an existing mismatched origin, no-op when already matching,
  and adding `origin` when none exists yet.

## ADR-027: `TEMPLATE_ORIGINS.md` moved to `memory/`; root stays a fixed set of files

ADR-025 added `TEMPLATE_ORIGINS.md` at the repository root — a new
top-level file, the same drift ADR-021 already fixed once (decluttering
the root to a single entry point). New framework state should never
default to landing in the root just because that is where a related file
happened to get created.

- Moved `TEMPLATE_ORIGINS.md` to `memory/TEMPLATE_ORIGINS.md` — it is
  long-term project state (a list of protected git remotes), the same
  category `memory/` already holds (`DECISIONS.md`, `PROJECT_STATE.md`,
  `OPEN_TASKS.md`, `CHANGE_LOG.md`), not code or a root governance
  document like `AGENTS.md`/`PRINCIPLES.md`.
- `agents/git_ops.py::_refuse_template_origin()` now reads
  `project_root / "memory" / "TEMPLATE_ORIGINS.md"`; error message and
  docstrings updated to the new path; `tests/test_git_ops.py` updated to
  create the file under a `memory/` subdirectory in its throwaway repos.
- `README.md` and `AGENTS.md` updated to the new path. ADR-025 and
  ADR-026's own text is left as-is (append-only, same as ADR-010's
  precedent for ADR-001/ADR-009) — it accurately describes what was
  decided at the time; this entry is the record of the later move.
- Added an explicit rule to `AGENTS.md`: the repository root is a fixed
  set of files (`AGENTS.md`, `PRINCIPLES.md`, `README.md`,
  `AGENTS_SUGGESTIONS.md`, `UPDATE_NOTES.md`, `requirements.txt`,
  `.env`/`.env.example`, `chat_architect.py`). New framework state or
  config goes in `memory/` or `agents/`, or as a new section in an
  existing root `.md` file — never a new top-level file — so this
  category of drift does not need rediscovering a third time.

## ADR-028: `Tr5-base` bootstrapped from `bod_zero`, as a deliberate merge with `Tr5-platform`

The owner reviewed `bod_zero`'s pipeline against `Tr5-platform`'s own
(`github.com/trava5/Tr5-platform` — a live, running platform with real
production incidents behind several of its principles, distinct from
`bod_zero`'s more abstract, general-purpose template). Conclusion: not a
question of which is "better" — both are explorations that took different
paths from a common origin (`bod_zero`'s own `PRINCIPLES.md` already
credits Tr5's `PRINCIPLES.md` as its source). The owner wants a new
template, `Tr5-base`, that takes the best of both, to become the seed for
every future project going forward. `Tr5-platform` itself is not
deprecated or migrated — it keeps running as-is, including its
`voice_agent` project, which becomes a read-only reference source for
later extraction work (mirroring ADR-024's `source/` pattern).

- This repository (`github.com/trava5/Tr5-base`) is seeded from
  `bod_zero`'s current state (closer starting skeleton: independent-
  project template, SDK-agnostic agents, contract pipeline already
  built) — a plain file copy of every file `git ls-files` reports in
  `bod_zero`, excluding `.git` itself. `bod_zero`'s own
  `memory/DECISIONS.md` (ADR-001 through ADR-027) is carried forward
  unchanged, append-only, same as this entry — it explains why the
  inherited skeleton is shaped the way it is.
- `memory/TEMPLATE_ORIGINS.md`: added this repository's own origin
  (`https://github.com/trava5/Tr5-base.git`) to the protected-origin
  list, alongside the inherited `bod_zero`/`bod-nula` entries — so
  `commit_and_push()`'s existing guard (ADR-025) also refuses to push a
  future project's real work back into `Tr5-base` itself.
- `README.md`: title and opening paragraph updated to state `Tr5-base`'s
  own identity and provenance (bootstrapped from `bod_zero`, enriched
  from `Tr5-platform`) rather than describing `bod_zero`'s relationship
  to `agentCodex`, which no longer applies here — matching how ADR-020
  already gave `bod-nula`'s own README a stated relationship back to
  `agentCodex`.
- The specific enrichments this bootstrap sets up to receive are recorded
  in detail outside this repository for now (a decisions log and
  implementation plan produced in conversation with the owner, covering:
  an independent Reviewer holding both review gates instead of the
  Architect self-reviewing after implementation; a per-contract
  `standard`/`high` risk flag that gates full automation vs. step-by-step
  human pacing; a ported, extended Discovery Engine; a three-checkpoint
  commit convention; two new principles (fake realism/timing,
  native-library thread-sharing); a `/voice` mode for talking to the
  Architect plus a separately extractable voice module; a memory model
  where only the Architect keeps persistent memory and
  `WORKING_STATE.md` becomes a generated artifact instead of
  agent-authored). Each will land here as its own ADR, in the phase it is
  actually implemented, rather than as one large entry up front — per
  P13/P15, each change is recorded once it is real, not speculatively.
- This directly revisits several prior `bod_zero`/`agentCodex` decisions,
  each to be formally superseded by its own ADR when that specific phase
  lands rather than here: ADR-004 (implementation review staying with the
  architect because Tr5's own practice did not separate the roles either
  — the owner now wants genuine separation regardless of Tr5's practice);
  ADR-005 and ADR-007 (Tr5 principles/directory layout tied to specific
  tools `bod_zero` did not have, e.g. Discovery Engine, `pyaudio` — no
  longer true once this repository actually carries a ported Discovery
  Engine and an extracted voice module); ADR-012 (Discovery Engine
  deferred for lack of a concrete case — the case now exists,
  `Tr5-platform`'s own working implementation).
- Verification: fresh copy diffed file-for-file against `bod_zero`'s
  `git ls-files` output (identical set, no drift); no tests changed in
  this bootstrap step, so the existing suite's pass/fail state carries
  over unchanged from `bod_zero`.

## ADR-029: `reviewer` holds both review gates; supersedes ADR-004's implementation-review-stays-with-architect stance

Tr5-base decision 1 (Phase 1 + Phase 2 of the implementation plan
referenced in ADR-028). Formally supersedes the last bullet of ADR-004,
which kept implementation review with `architect` because Tr5 itself did
not unambiguously separate the roles either. The owner wants genuine
separation regardless of what Tr5's own practice did, so that stance no
longer holds; everything else in ADR-004 (the `reviewer` agent's
existence, its `permission_profile: review`, `Contract.reviewer` /
`next_for_revision()`) is unaffected and still applies.

- `agents/contract_workflow.py`: `ContractPoint.architect_review` renamed
  to `reviewer_note`, with new `programmer_note_author`/`_at` and
  `reviewer_note_author`/`_at` fields so every note states who wrote it
  and when. `Contract.risk_level: Literal["standard", "high"] = "standard"`
  added (groundwork for decision 7's automation dial, not yet wired into
  pipeline pausing — that is a later phase). Status
  `READY_FOR_ARCHITECT_REVIEW` renamed to `READY_FOR_REVIEWER`.
  `record_programmer_result()` now hands off to `"reviewer"` (was
  `"architect"`). `record_implementation_review()` now requires
  `out_of_scope_ok: bool` and `out_of_scope_findings: str` — an
  unexplained out-of-scope change forces `CHANGES_REQUESTED` on its own,
  regardless of the per-point verdicts — and defaults `from_agent` to
  `"reviewer"`. `record_architecture_review()` accepts an optional
  `risk_level` escalation (the reviewer may raise `standard` to `high`,
  never lower it) and records which agent reviewed in the round history.
  `next_for_implementation_review()` now queues on
  `assigned_to="reviewer"` (was `"architect"`), matching the new handoff.
  `render_contract()` shows the attribution lines and the Out of Scope
  check result.
- `agents/architect/commands/review_contract.md` moved to
  `agents/reviewer/commands/review_contract.md` (`git mv`), alongside the
  existing `architecture_review.md` — extended to request
  `out_of_scope_ok`/`out_of_scope_findings` and to describe the Out of
  Scope check explicitly. `agents/pipeline.py`: `review_next()` now takes
  the `reviewer` agent (was `architect`) and passes the two new fields
  through; `continue_pipeline()` takes `reviewer` instead of `architect`
  and hands implementation review to it; `create_contract()` /
  `revise_contract()` updated to match. `chat_architect.py`'s `/review`
  manual override now calls `review_next(reviewer, ...)`.
- `agents/reviewer/config.json`: `load_private_memory`/`load_working_state`
  set to `false` (was `true`) — the reviewer runs both gates on a fresh
  thread with no memory of past contracts (Tr5-base decision 9), so a
  persisted private memory or working-state file would go stale and
  unread by design, not by omission. `agents/programmer/config.json` gets
  the same two flags for the same reason (decision 9 applies the
  fresh-agent-per-call model to the programmer too, not only the
  reviewer); code consistency without memory is instead carried by
  `PRINCIPLES.md` (always loaded) plus a new required first step in
  `agents/programmer/commands/implement_contract.md`: read the related
  files in the same module/directory before writing any code.
  `agents/architect/config.json` needed no change — it already had
  `load_private_memory`/`load_working_state: true`, matching decision 9's
  architect-keeps-memory stance.
- `ROLE.md`/`COMMANDS.md` rewritten for all three agents to state the new
  split plainly (architect: drafts, non-gating post-review pass; reviewer:
  both gates plus Out of Scope and risk escalation; programmer:
  unchanged duties, reviewer instead of architect approves its memory
  writes). `AGENTS.md` and `PRINCIPLES.md` (P10, P13) updated to match —
  P10's own explanation of why implementation review is taken seriously
  no longer rests on "a different agent than the one who accepted the
  contract" (no longer true) but on the reviewer never checking a
  contract it authored, plus decision 9's fresh-thread independence even
  from its own earlier verdict on the same contract.
- Deliberately deferred to later phases, per the plan referenced in
  ADR-028: `risk_level`-based pipeline pausing and the `/proceed` command
  (Phase 3); the third `- REVIEWED` git checkpoint (Phase 5); Discovery
  Engine and generated `WORKING_STATE.md` (Phase 4).
- Verification: `python -m pytest -q` — 34/34 passing (test doubles for
  the agent roles, so the `commands/` file move does not affect the unit
  suite directly; the real `AgentProfile.load_command()` path was
  verified by inspection — `chat_architect.py` and `agents/pipeline.py`
  now request `"review_contract"` from the `reviewer` agent, whose
  `commands_directory` is where the file now lives).

## ADR-030: Risk-based pipeline pausing (`/proceed`) and the third `- REVIEWED` git checkpoint

Tr5-base decisions 5, 7, and 8 (Phase 3 + Phase 5 of the implementation
plan referenced in ADR-028, done together because Phase 3's pause
branching and Phase 5's third checkpoint each only make sense with the
other — Phase 3's "skip the final commit for high-risk contracts" needs
the commit to exist; Phase 5's "auto-push it for standard-risk" needs the
risk branch to know when not to).

- `agents/pipeline.py`: `continue_pipeline()` now branches on
  `contract.risk_level` after committing checkpoint 1 (`CONTRACT_NNNN`,
  unchanged timing). `"standard"` continues straight through; `"high"`
  stops and prints an instruction to run `/proceed <n>`. New `proceed()`
  function resumes a paused high-risk contract from either of its two
  pause points (`READY_FOR_PROGRAMMER` or `READY_FOR_REVIEWER`) — a
  no-op message for any other status. Two new private helpers,
  `_implement_and_review()` and `_review_and_commit()`, hold the shared
  logic between `continue_pipeline()`'s first automatic run and
  `proceed()`'s resumption, so the two paths cannot drift apart.
- New checkpoint 2: right after the programmer finishes (in
  `_implement_and_review()`), `CONTRACT_NNNN - IMPLEMENTED` is committed
  and pushed automatically, regardless of risk_level — only checkpoint 3
  is risk-gated. This retimes bod_zero's original single post-cycle
  `- IMPLEMENTED` commit (previously fired manually via `/commit`, only
  after implementation review passed) to fire right after the
  programmer's own self-verification, matching Tr5's timing.
- New checkpoint 3: right after implementation review returns `APPROVED`
  (in `_review_and_commit()`), `CONTRACT_NNNN - REVIEWED` is committed
  and pushed automatically for `"standard"` contracts. For `"high"`
  contracts this auto-push is skipped; a message with the exact
  `git commit`/`git push` command is printed instead.
- `commit_approved_contract()` (the existing `/commit <n>` manual
  override) is retimed to match: it now pushes `- REVIEWED` (was
  `- IMPLEMENTED`), gated on status `APPROVED` as before. For
  `"standard"` contracts this is now usually a no-op (already
  auto-committed by the pipeline); for `"high"` contracts it is how the
  owner actually pushes the final checkpoint — an equivalent, in-app
  alternative to running the printed raw git command by hand.
- `review_next()` renamed to `run_implementation_review()` (matching the
  existing `run_architecture_review()` naming) — a pure rename, same
  behavior, no call sites left on the old name (the rename in `CONTRACT
  0002`/ADR-029 already routed it through the `reviewer` agent).
- `run_architecture_review()` now forwards an optional `risk_level` from
  the reviewer's JSON response into `record_architecture_review()` — the
  escalation mechanic already existed in `contract_workflow.py` since
  `CONTRACT 0001`, this wires it to the actual pipeline call.
  `create_contract()`/`revise_contract()` forward the architect's
  `risk_level` the same way (`revise_contract` only if explicitly given —
  omitting the key preserves the contract's current value, so a prior
  escalation to `"high"` is never silently lost by a routine revision).
- `chat_architect.py`: new `/proceed <n>` command; `/commit <n>`'s help
  text and behavior updated for the `- REVIEWED` retiming; `/review`
  updated to call the renamed `run_implementation_review()`.
- `agents/architect/commands/create_contract.md`: requests `risk_level`
  in the JSON response, with the criteria from decision 7 (real
  credentials/API keys, real external calls, native/hardware libraries,
  risk of landing personal/real data in git) and an explicit note that
  the reviewer can still escalate. `agents/reviewer/commands/
  architecture_review.md`: documents the escalation check and that
  `risk_level` should be included in the response only when escalating,
  never to lower it.
- `print_status()`/`status_text()` now show `risk_level` per contract.
- `README.md`/`contracts/README.md`: `/proceed` documented, the Lifecycle
  section rewritten for the three-checkpoint, risk-gated pipeline
  instead of the old two-checkpoint description.
- Verification: `python -m pytest -q` — 43/43 passing. Six new tests
  cover `risk_level` at the `contract_workflow.py` level (default,
  explicit, invalid rejection, reviewer escalation, reviewer cannot
  downgrade, `revise_contract` preserves unless given); three new tests
  cover the pipeline level (`create_contract` pauses before
  implementation for a high-risk contract with only checkpoint 1
  committed and the programmer never called; `proceed()` resumes through
  both pause points across two calls, committing `- IMPLEMENTED`
  automatically but not auto-pushing `- REVIEWED`, which `/commit`
  finalizes manually; `proceed()` on a contract not at a pause point
  prints a message and calls neither agent). The existing full-chain
  test for a `standard`-risk contract was updated to expect all three
  checkpoints; the existing `/commit` test was renamed and updated for
  the `- REVIEWED` suffix.
- Deliberately deferred to later phases, per the plan referenced in
  ADR-028: Discovery Engine and generated `WORKING_STATE.md` (Phase 4,
  still independent of this one); new principles and the Backlog section
  (Phase 6); voice (Phase 7).

## ADR-031: Discovery Engine ported from `Tr5-platform`; `WORKING_STATE.md` becomes generated

Tr5-base decisions 3 and 10 (Phase 4 of the implementation plan
referenced in ADR-028). Supersedes ADR-012's deferral ("Discovery Engine
deferred for lack of a concrete case") — the case now exists,
`Tr5-platform`'s own working implementation, ported here — and the
Discovery Engine half of ADR-007/ADR-005's "Tr5 tooling this repository
doesn't have" reasoning: it does now.

- New `tools/` top-level package (a new kind of layer this repository
  did not have before — the first concrete use of the `tools/` pattern
  ADR-007 rejected for lack of need). `tools/discovery_engine/
  generate_current_state.py` ported from `Tr5-platform`'s own
  `tools/discovery_engine/generate_current_state.py`, kept close to the
  original (gitignore-aware recursive scan, `.git/` always excluded,
  deterministic Markdown rendering) but with real changes:
  - `classify_artifact()` takes a `relative_path` string instead of a
    filesystem `Path`, and recognizes this template's own governance/
    agent-memory files as their own category — `Agent Memory`, `Agent
    Working State`, `Agent Role`, `Agent Commands`, `Agent Inbox`,
    `Agent Config`, `Agent Command Template`, `Implementation Contract`,
    `Project Memory`, `Governance Document` — instead of everything
    falling into generic `Markdown Document`/`JSON Document` (decision
    3's "extended classification").
  - Every file artifact now carries a sha256 `content_hash` (`None` for
    directories) — not shown in the rendered Markdown, but the basis for
    the new diff mode: `save_snapshot()`/`load_snapshot()` (a scan
    serialized to JSON) and `diff_scans()` (added/removed/changed file
    paths between two scans, by path and hash) plus
    `render_diff_markdown()` for embedding the result in a prompt.
  - Output moved from repository root (`TR5_CURRENT_STATE.md` in
    `Tr5-platform`) to `memory/CURRENT_STATE.md` — this repository's own
    root file set is deliberately fixed (`AGENTS.md`, ADR-027), and
    `memory/` is where `AGENTS.md` already says new framework state
    belongs (the same place `TEMPLATE_ORIGINS.md` lives).
  - `run_discovery_scan()` is the new single entry point wiring scan +
    render + save together — the "structural trigger."
- `agents/pipeline.py`: `create_contract()`/`revise_contract()` call
  `run_discovery_scan()` as their first action, before the architect
  drafts anything — `memory/CURRENT_STATE.md` is always fresh by the
  time `create_contract.md`'s new instruction tells the architect to
  read it. `run_implementation_review()` calls
  `store.out_of_scope_diff(number)` and renders it into a new
  `{{OUT_OF_SCOPE_DIFF}}` variable for `review_contract.md`, replacing
  the vague "compare the actual diff" instruction with a concrete,
  mechanically-produced added/removed/changed list (falls back to "no
  snapshot available, check yourself" if snapshots are missing — never
  blocks the review).
- `agents/contract_workflow.py`: `ContractStore.claim()` saves a "pre"
  discovery snapshot after claiming; `record_programmer_result()` saves
  a "post" snapshot after handing back to the reviewer. Both live at
  `contracts/.discovery/<NNNN>_{pre,post}.json` — gitignored (`.discovery/`
  added to `.gitignore`; matched by bare directory name, the same
  simplified model the engine's own `.gitignore` parser uses, same as
  the existing `.idea/` entry), disposable working data, not permanent
  history. Snapshot save is best-effort (an `OSError` is swallowed, not
  raised) — a discovery-tool problem must never block the actual
  contract workflow. New `out_of_scope_diff(number)` diffs the pair,
  returning `None` if either is missing, and excludes the contract's own
  `.md` file from "changed" — it always changes between the two
  snapshots (the programmer's notes are written into it), which is
  expected bookkeeping, not an out-of-scope signal worth repeating on
  every single review.
- `ContractStore.save()` — the single write path every mutating method
  already funnels through — now also calls the new
  `refresh_working_state()`, which regenerates
  `agents/architect/WORKING_STATE.md` from a new
  `render_queue_summary()` (the same rendering `pipeline.status_text()`
  used to compute inline — that function now just delegates to
  `store.render_queue_summary()`, one source of truth instead of two).
  This replaces the previous mechanism (an agent optionally proposing a
  `memory_update` onto that path) with unconditional generation on every
  state transition (decision 10) — it structurally cannot drift, the way
  a discipline-dependent proposal could.
  `agents/<agent>/WORKING_STATE.md` is removed from
  `ALLOWED_MEMORY_TARGETS` (was `agents/*/(MEMORY|WORKING_STATE).md`, now
  `agents/*/MEMORY.md` only) — writing there via `memory_updates` would
  just be overwritten on the next `save()`, for any of the three agents,
  not only the architect. `agents/reviewer/WORKING_STATE.md` and
  `agents/programmer/WORKING_STATE.md` (already unloaded since `CONTRACT
  0002`/ADR-029's `load_working_state: false`) are deleted as vestigial —
  never loaded, never a valid write target, never generated for those
  two roles.
- `ROLE.md`/`COMMANDS.md`/command templates and `README.md` updated to
  match: the "Allowed memory targets" lists no longer mention
  `WORKING_STATE.md`; a new README "Discovery Engine and generated
  state" section explains both wirings.
- Verification: `python -m pytest -q` — 64/64 passing. 11 new tests for
  the discovery engine module itself (governance classification, generic
  classification, gitignore/`.git` exclusion, content hashing,
  `render_markdown` shape, `run_discovery_scan` writes the file,
  snapshot round-trip, `diff_scans` added/removed/changed, `diff_scans`
  excludes directories, `render_diff_markdown` no-changes and
  all-categories cases). 7 new tests at the `contract_workflow.py`
  level (`WORKING_STATE.md` generated on save and reflects the latest
  transition, `WORKING_STATE.md` rejected as a memory target, `claim()`
  saves a pre-snapshot, `out_of_scope_diff` reports a touched file,
  excludes the contract's own file, returns `None` without snapshots).
  3 new tests at the pipeline level (`create_contract` writes
  `memory/CURRENT_STATE.md` first, `run_implementation_review` passes
  the rendered diff to the reviewer, and handles a missing snapshot
  gracefully).
- Deliberately deferred: new principles and the Backlog section (Phase
  6); voice (Phase 7).

## ADR-032: Tr5 P22/P23 adopted as PRINCIPLES.md P16/P17; Backlog section added; P6's stale Discovery Engine note fixed

Tr5-base decision 6 (Phase 6 of the implementation plan referenced in
ADR-028), completing the principles review Phase 4/ADR-031 left
outstanding.

- `PRINCIPLES.md` P16 added, source Tr5 P22 ("A fake must be realistic
  enough not to manufacture failures a real dependency would never
  cause") — adopted verbatim in substance, citing Tr5's own fake
  microphone incident (an unpaced fake stream made a correctly-working
  client look hung; a timing-accurate fake resolved it). Directly
  relevant to this template's own upcoming voice module (Phase 7).
- `PRINCIPLES.md` P17 added, source Tr5 P23 ("Native/hardware library
  instances often need to be shared across threads, not created
  per-thread") — adopted verbatim in substance, citing Tr5's own
  `pyaudio.PyAudio()` per-thread instantiation incident (a native-layer
  thread-safety failure invisible to Python-level testing). Also
  directly relevant to Phase 7's voice module, called out explicitly in
  the principle's own text.
- Tr5 P25 ("browser-only globals need explicit stubs when testing
  frontend JS outside a browser") reviewed and **not** adopted — narrow
  to Tr5's `platform_shell` frontend, which this template does not
  carry, and this template has no frontend JS of its own yet. Per
  P11/P15 (validate on a real case, don't write in speculatively), left
  out; revisit if a real case appears.
- This closes the review of Tr5 P19-P25 into `PRINCIPLES.md`: P19→P2,
  P20→P3, P21→P4, P24→P5 were already adopted before this bootstrap
  (see the pre-ADR-028 history); P22→P16 and P23→P17 adopted here; P25
  not adopted.
- P6's parenthetical about the Discovery Engine was stale as of
  ADR-031: it still said the engine "was considered and deferred... not
  adopted, since `agentCodex` had no such engine and none was planned"
  (true when it was first written, false since Phase 4 ported it).
  Updated to note the deferral no longer holds, referencing ADR-031, so
  the document does not contradict its own repository's current state
  (per P6's own rule: current-state text must be fact, not stale
  interpretation).
- New "Open Questions (Backlog)" section added to `PRINCIPLES.md`,
  mirroring Tr5's own `PRINCIPLES.md` Backlog section. First entry logs
  the idea parked during Tr5-base decision 9 (per-role memory model):
  whether an Architect's memory should ever be shared or pooled across
  separate projects cloned from this same template. Not designed now —
  no second cloned project exists yet to validate it against, and each
  clone is meant to live its own independent life (ADR-020/ADR-028).
  Explicitly deferred, not decided either way; revisit once one
  project's own Architect memory has actually proven itself useful in
  practice.
- No code changes — this phase is documentation only. Verification:
  `python -m pytest -q` — 64/64 passing (unchanged from ADR-031, as
  expected for a documentation-only phase).
- Deliberately deferred: voice (Phase 7).

## ADR-033: Voice — `/voice` in `chat_architect.py` plus a reusable, decoupled `templates/voice_module/`

Tr5-base decision 4 (Phase 7 of the implementation plan referenced in
ADR-028), the last phase of the plan.

- New top-level directory `templates/`, sibling to `agents/`, `tools/`,
  `memory/`, `contracts/`, `project/`, `source/` — not a subdirectory of
  `agents/` or `tools/` (a template is a seed a project's own code copies
  from, not framework code that runs directly, and not a Discovery-Engine-
  style tool that observes the repository). `templates/voice_module/` is
  its first (and, so far, only) member: `audio_io.py`
  (`AudioBackend`/`AudioStream` Protocols plus `PyAudioBackend`, wrapping
  exactly one shared `pyaudio.PyAudio()` instance for the whole session —
  PRINCIPLES.md P17), `gemini_voice_bridge.py` (`VoiceBridge` Protocol
  plus `GeminiVoiceBridge`), `live_voice_session.py`
  (`LiveVoiceSession`, the orchestrator), and its own `README.md`
  explaining the design and how a project copies it into `project/` for
  its own product's voice feature (decision 4, item 3b) — see that
  `README.md` for the full reasoning, only summarized here.
- **Resolved the plan's own open design question** before writing code:
  `chat_architect.py` talks to the Architect through its own Codex/Claude
  Agent SDK thread (`agents/agent.py`), never through Gemini — so Gemini
  is used purely for speech-to-text/text-to-speech duty, decoupled from
  whichever provider actually reasons about the conversation. This is why
  `gemini_voice_bridge.py` opens **two independent, short-lived** Gemini
  Live sessions per conversational turn — `transcribe_turn()` (STT only;
  the session's own generated reply is never read, only
  `input_transcription` text) and `speak_text()` (TTS only, given a strict
  system instruction to read the supplied text verbatim) — instead of
  reusing `Tr5-platform`'s `gemini_live_audio_handler.py` pattern of "one
  Live session IS the assistant," which is right for `voice_agent` but
  wrong here.
- Also unlike `voice_agent`: no FastAPI backend, no websocket hop.
  `chat_architect.py` is already the one local process holding the
  conversation, so `LiveVoiceSession` talks to Gemini and the local
  microphone/speakers directly — a deliberate simplification, not a
  partial port.
- `LiveVoiceSession`'s turn loop is sequential, not simultaneous: open a
  mic stream, transcribe one turn to completion, close it; then open a
  speaker stream, speak the reply to completion, close it; then listen
  again. A plain CLI mic/speaker setup has no echo cancellation, so
  streaming the mic while playback is active would let the assistant hear
  itself.
- **Real concurrency bug found and fixed during implementation, not just
  during review**: an early version of `GeminiVoiceBridge.
  _transcribe_turn_async()`'s `_send()` coroutine iterated the (blocking,
  synchronous) mic-chunk generator directly inside the coroutine — each
  `next()` call blocks on a real `stream.read()`, which would have
  blocked the single-threaded asyncio event loop for the duration of
  every chunk read, starving the concurrently-scheduled `_receive()` task
  and delaying `turn_complete` detection on every chunk sent during an
  utterance, not just once. Fixed by offloading each `next()` call via
  `asyncio.to_thread`. This is exactly the class of bug PRINCIPLES.md P16
  describes (a fake with an instant `next()` would never expose it) —
  caught here by reasoning about the real blocking call's effect on the
  event loop while writing the code, then verified with a regression test
  that checks *which thread* runs the mic-chunk `next()` calls (must never
  be the event-loop's own calling thread), not a wall-clock timing
  threshold, which proved too fragile as a discriminator once actually
  measured (an `asyncio.run()`-per-call design pays a small, bounded,
  unavoidable shutdown-wait for one orphaned worker thread regardless —
  documented in the test itself, not hidden).
- `agents/voice.py` (new, framework layer, alongside `agents/git_ops.py`
  as a non-core-dataclass support module) wires `templates/voice_module/`
  into `chat_architect.py`: `VoiceConfig.load()` reads `GEMINI_API_KEY`/
  `GEMINI_LIVE_MODEL` from `.env` and raises a clear `RuntimeError` if the
  key is missing (checked before any hardware/SDK object is constructed —
  `/voice` fails fast, not partway into opening a session);
  `start_voice_session(ask_callback, ...)` builds a real `PyAudioBackend`,
  `GeminiVoiceBridge`, and `LiveVoiceSession` and starts it.
- `chat_architect.py`: new `/voice` / `/voice end` commands (HELP text
  updated); a `voice_session` variable in `main()`'s closure tracks the
  running session so `/exit` also stops it cleanly instead of leaving a
  background thread and an open `pyaudio.PyAudio()` instance behind.
- `requirements.txt`: added `pyaudio`, `google-genai` — decision 4, item
  3a states `/voice` "ships with every project cloned from the new bod_zero
  template," i.e. as a base dependency of the single root entry point, not
  a separately-installed extra (unlike `templates/voice_module/`'s *second*
  use, item 3b, which is genuinely opt-in per project and copied in only
  when wanted). `.env.example`: added `GEMINI_API_KEY`/`GEMINI_LIVE_MODEL`,
  both blank by default — every other command works without them.
  `AGENTS.md`'s framework-layer file list updated to include
  `agents/voice.py`, `tools/discovery_engine/`, and
  `templates/voice_module/` (the last two were themselves missing from
  that list since ADR-031 — fixed here rather than left stale further,
  same spirit as this phase's own fix to `PRINCIPLES.md` P6 in ADR-032).
- **Verification**: `python -m pytest -q` — 77/77 passing (13 new). Real
  deferred-import checks (PRINCIPLES.md P2) — `PyAudioBackend()` and
  `GeminiVoiceBridge()` are actually constructed for real in this
  repository's own CI environment (both packages are real dependencies,
  not skipped/mocked at the import boundary): `pyaudio.PyAudio()`
  succeeds even with zero audio devices present; `genai.Client(api_key=
  ...)` makes no network call on construction, so a fake key is safe to
  use here. `LiveVoiceSession` orchestration (full turn, empty-transcript
  turns skip ask/speak, idempotent `stop()`, double-`start()` raises,
  errors reported via `on_error` instead of crashing silently) is tested
  against fake `AudioBackend`/`VoiceBridge` implementations — no real
  hardware or network reachable from these tests (P4). `agents/voice.py`
  is tested for the fail-fast-without-`GEMINI_API_KEY` path (asserting
  `PyAudioBackend`/`GeminiVoiceBridge` are never even constructed) and for
  correctly wiring `ask_callback` into a (fake) `LiveVoiceSession`. What
  these tests cannot and do not claim to cover — an actual microphone,
  actual speakers, an actual `GEMINI_API_KEY`, and a real conversation —
  is real-world verification the person does once on their own machine,
  the same way `Tr5-platform`'s own PortAudio/threading incidents (the
  source of P17 itself) were only ever found by a person actually running
  the client.
- `Tr5-platform`'s `projects/voice_agent/` was read only, as a reference
  source — left completely untouched (decision 4, item 3c).
- Deliberately deferred (see `templates/voice_module/README.md`'s own
  Future Evolution note): the TTS-verbatim system-instruction design has
  not been validated against a real conversation yet — that first real
  `/voice` session is its actual test.

This completes `tr5_base_implementation_plan.md`'s Phase 0–7 sequence.

## ADR-034: Post-migration audit — two real gaps found and fixed, plus stale-branding cleanup

Requested by the owner after Phase 7 landed: "thoroughly review the whole
repo and confirm every intended migration step is correctly implemented
and the project fits together as a whole, as intended." Five independent
audits ran against a fresh clone of the pushed repository (not the local
working copy), one per decision cluster (1/5/7/8, 3/10, 6/9, 4, and a
whole-repo consistency/hygiene sweep), each explicitly told to be
skeptical and cite file:line evidence rather than trust prose claims. Two
real implementation gaps were found and are fixed by this same commit;
everything else audited came back confirmed correct.

**Gap 1 — decision 9 ("fresh thread per call") was not actually true.**
`chat_architect.py` constructed the `reviewer` and `programmer` agents
**once**, at session start, inside the top-level `ExitStack`, and reused
those same two long-lived `Agent` objects (and therefore the same
underlying SDK conversational thread) for every `/new`, `/revise`,
`/work`, `/review`, and `/proceed` call for the rest of the session —
across every contract, and even between one contract's own Architecture
Review and its later Implementation Review. `config.json`'s
`load_private_memory: false`/`load_working_state: false`, the command
templates' own claims ("you are given a fresh thread with no memory of
past contracts"), `PRINCIPLES.md` P10's revision note, and ADR-029 itself
all asserted this was already true; none of it was backed by an actual
mechanism. `AgentProfileConfig.persistent_thread` — the flag that sounds
like it should govern this — is parsed from `config.json` but was never
read anywhere in `create_agent()`/`create_thread()`/`Agent`, so it had no
effect either way.

Fixed structurally, not by convention: `agents/pipeline.py`'s functions
that talk to the reviewer/programmer (`run_architecture_review`,
`implement_next`, `run_implementation_review`) now take a zero-argument
`AgentFactory` (`Callable[[], Agent]`) instead of a constructed `Agent`,
and construct-use-close a brand-new one inside a `with` block for that one
call only (`Agent` already supported the context-manager protocol —
`agent.py`'s `close()`/`__enter__`/`__exit__` — this only needed to
actually be invoked per call). The pass-through functions
(`create_contract`, `revise_contract`, `continue_pipeline`, `proceed`,
`_implement_and_review`, `_review_and_commit`) were renamed to take
`reviewer_factory`/`programmer_factory` and forward them unchanged — they
never call `.run_command()` themselves. `chat_architect.py` now builds
`reviewer_factory = lambda: create_agent("reviewer", ...)` and
`programmer_factory = lambda: create_agent("programmer", ...)` instead of
constructing those two agents once; only the `architect` stays a single
long-lived `Agent` for the whole session, exactly as decision 9 always
intended ("naturally continuous within one session," the one role
allowed that). `tests/test_pipeline.py`'s `ScriptedAgent` gained
`close()`/`__enter__`/`__exit__`; every existing call site now passes a
factory (`lambda: reviewer`, returning the same scripted double, to keep
existing call-sequence assertions meaningful); a new dedicated test,
`test_reviewer_and_programmer_get_a_fresh_agent_for_every_call`, uses a
factory that constructs a genuinely new `ScriptedAgent` per call and
asserts Architecture Review and Implementation Review get two distinct
instances, each closed — the coverage gap the audit specifically flagged
(no prior test would have caught the bug even though it existed).

**Gap 2 — decision 7's "never downgraded back to standard by anyone" had
one real exception.** `record_architecture_review()` correctly enforces
escalation-only (passing `"standard"` there is a documented no-op). But
`ContractStore.revise_contract()` set `contract.risk_level` unconditionally
whenever a caller passed one — silently allowing the architect to lower a
`"high"` contract back to `"standard"` via `/revise`, contradicted by
decision 7's own text ("never downgraded back to `standard` by anyone")
and by `architect/commands/create_contract.md`'s instruction ("only
include risk_level if you are deliberately changing it," worded as if
downgrading were an intended, ordinary case). `tests/
test_contract_workflow.py` had a test literally named around a variable
`lowered`, asserting the downgrade as correct behavior — so this wasn't
just an implementation slip, it was asserted as intended by the test
suite itself.

Fixed to match the sibling function's own pattern exactly: `revise_contract`
now only ever raises `risk_level` to `"high"`; passing `"standard"`
explicitly (or omitting it) both leave the current value untouched. Test
renamed/split: the old downgrade case now asserts the value stays `"high"`
(`test_revise_contract_preserves_risk_level_unless_given`), and a new
`test_revise_contract_can_still_escalate_risk_level` confirms escalation
via `/revise` still works. `create_contract.md`'s instruction reworded to
say "only include risk_level if you are escalating it," not "changing" it.

**Stale-branding and drift cleanup** (no behavioral bug, but the audit's
whole-repo sweep found real factual inaccuracies a reader — or an agent —
would trust):
- `PRINCIPLES.md`'s own title and Purpose section still said "agentCodex
  Principles" / "the `agentCodex` project" — never rebranded when
  `README.md`/`AGENTS.md` were (ADR-028). Fixed; historical references to
  the pre-bootstrap `agentCodex` review (P6's own text) were left as-is
  since those are accurate history, not branding.
- `project/README.md` still said "this clone of agentCodex" and its own
  framework-layer file list omitted `agents/voice.py`,
  `tools/discovery_engine/`, `templates/voice_module/` — the same gap
  `AGENTS.md`'s own list had until this file was fixed for it in ADR-033;
  `project/README.md` was missed at the time. Fixed.
- `agents/architect/MEMORY.md` — the architect's own persistent long-term
  memory, loaded into every architect session — still described the
  pre-bootstrap two-role, no-contracts, no-discovery-engine, no-voice
  project. Rewritten to describe Tr5-base's actual current shape (reviewer
  holds both gates, risk_level, generated WORKING_STATE.md, Discovery
  Engine, voice's provider decoupling) at the same level of summary the
  original had — not expanded into full documentation, since that's
  README.md/AGENTS.md/this file's job, not MEMORY.md's.
- `memory/PROJECT_STATE.md` — same kind of staleness, same fix, for the
  "Current Project State" doc a session (not just the architect) might
  read.
- `memory/CURRENT_STATE.md` — the Discovery Engine's own generated
  snapshot — was stale relative to the real tree (missing `agents/voice.py`
  and all of `templates/`) simply because no `/new`/`/revise` had run
  since ADR-033 landed; this is expected staleness by design (it
  regenerates on the next real contract), not a bug, but was refreshed
  here via a direct `run_discovery_scan()` call so the checked-in file
  matches the checked-in tree right now.
- `memory/OPEN_TASKS.md` — "Add controlled writes to agents' private
  memory" was still listed unchecked, but is in fact implemented
  (`ALLOWED_MEMORY_TARGETS`/`ContractStore.append_memory()`, wired from
  both review-recording functions' `memory_updates` handling, present
  since well before this bootstrap). Checked off with a one-line pointer
  to where; the other three open items were independently verified as
  still genuinely open and left as-is.
- `AGENTS.md`'s "repository root does not grow new files" rule was
  accurate in practice but ambiguous in wording — it never stated whether
  it meant files, top-level directories, or both, which the audit flagged
  as worth resolving explicitly rather than leaving implicit. Clarified:
  the rule is about root-level files; a genuinely new top-level
  *directory* for a new kind of layer (as `tools/`/`templates/` already
  were) is the documented alternative, each justified by its own ADR.
- `chat_architect.py`/`README.md`: `/quit`, `exit`, `quit` were handled as
  working aliases for `/exit` but were undocumented in both `HELP` and the
  README's command table. Documented rather than removed — no reason to
  take away a working, harmless alias.

**Verification**: `python -m pytest -q` — 79/79 passing (2 new: the
fresh-agent-per-call regression test, and the risk-escalation-still-works
test alongside the corrected downgrade test). Every other audited area
(decisions 1, 3, 4, 5, 6, 8, 10, and the 14-point whole-repo hygiene
sweep) came back confirmed with no discrepancies — not re-summarized here
since nothing about them changed.

## ADR-035: Discovery Engine gitignore parser did not exclude a bare
(no-trailing-slash) directory pattern — found by the first real clone's
first `/new`

**Context.** This is the first bug this template has produced under real
use rather than under its own tests or an internal audit: the owner
cloned `Tr5-base` into a genuinely new project (`Tr5-base-test`), filled
in `GIT_REPO`, and ran `/new` for the very first time. The architect's
own pre-draft Discovery Engine scan (decision 3) walked into the
project's freshly created `.venv/` — a real Python virtualenv with
thousands of vendored package files — and indexed the whole tree into
`memory/CURRENT_STATE.md`, ballooning it to roughly 33k tokens. The
resulting Claude call to draft `IMPLEMENTATION_CONTRACT_0001.md` failed
with "The agent did not return valid JSON," and nothing was written.
This is exactly the kind of gap the project's own Future Evolution notes
(`templates/voice_module/README.md`, `IMPLEMENTATION_CONTRACT_0013`)
anticipated: a first real run surfaces what no internal review can.

The owner's own architect, running inside that separate `Tr5-base-test`
session, diagnosed the root cause independently and correctly, citing
exact file:line evidence, before this was ever reported here. That
diagnosis was independently re-verified against this repository's own
canonical copy of the same code before any fix was made.

**Root cause.** `tools/discovery_engine/generate_current_state.py`'s
`_load_gitignore_patterns()` classified a `.gitignore` line as a
directory-exclusion pattern only if it ended with a trailing `/`. This
project's own `.gitignore` (like most hand-written ones) listed `.venv`
without a trailing slash — real git treats a bare name as matching a
file *or* a directory of that name, but this parser routed a bare name
into `file_patterns` only. `_is_excluded_directory()` therefore never
matched `.venv` as a directory to prune, `os.walk()` descended into it,
and every vendored file underneath was scanned and classified like any
other project artifact. `BASELINE_EXCLUDED_DIRECTORY_NAMES` (only
`.git`) has no built-in fallback for common virtualenv directory names
either, so nothing else caught this before it reached
`memory/CURRENT_STATE.md`.

**Fix — framework layer, matching the architect's own recommendation**
(not a one-off workaround in a single project's `.gitignore`, since
every future clone would otherwise hit the same failure the first time
its own `.venv/` existed):

- `_load_gitignore_patterns()` now adds a bare (no-trailing-slash)
  pattern to *both* `file_patterns` and `directory_patterns`, matching
  real git semantics — a trailing slash still restricts a pattern to
  directories only; a bare pattern now correctly matches either.
- This repository's own `.gitignore` was additionally tightened from
  `.venv` to `.venv/` — belt-and-suspenders consistency with every other
  directory entry already in that file (`__pycache__/`, `.pytest_cache/`,
  `.pytest-tmp/`, `.idea/`), not a substitute for the parser fix, since
  the parser fix is what protects every other project's own
  hand-written `.gitignore` too.
- New regression test,
  `test_scan_repository_excludes_a_directory_ignored_without_a_trailing_slash`
  (`tests/test_discovery_engine.py`): builds a fake `.venv/lib/
  site-packages/somepkg.py` tree under a `.gitignore` containing bare
  `.venv`, and asserts none of those paths appear in `scan_repository()`'s
  output while an unrelated `keep.md` does.

**Verification**: `python -m pytest -q` — 80/80 passing (1 new).

**Scope note — this fix does not reach already-cloned projects.**
Per decision 2/ADR-020 ("no live sync... each cloned copy lives its own
independent life from here on"), this fix updates only the canonical
`Tr5-base` template. The owner's own `Tr5-base-test` clone has its own
independent copy of the same buggy file and will not receive this fix
automatically — it needs either a manual backport of the same two
changes, or (truer to this project's own design, and a good second real
test of the full pipeline) a contract run through `Tr5-base-test`'s own
architect, which had already offered to prepare exactly that contract
before this fix was written. That choice was left to the owner rather
than made on their behalf.

## ADR-036: Tr5-base decision 11 — a printed round summary after the
final checkpoint; git operations made non-interactive throughout

**Context.** Two further friction points came directly out of the same
first controlled real-world test (see ADR-035): with `IMPLEMENTATION_
CONTRACT_0001`'s architecture-review checkpoint push failing on a stale
credential (ADR-035's second finding), the owner had to resume the
pipeline manually through `/work 1` → `/review 1` → `/commit 1` rather
than the normal unattended `standard`-risk chain. Two things fell out of
that manual detour:

1. `/work 1` appeared to hang for an unusual length of time with no
   console output and no error. Root cause: a `git push` (the
   `- IMPLEMENTED` checkpoint) fell back to an interactive credential
   prompt — either git's own terminal prompt or a Git Credential Manager
   popup window — that was easy to miss behind other windows. The process
   wasn't frozen; it was correctly waiting on input nobody knew it needed.
   This directly contradicts `AGENTS.md`'s own existing rule ("Only
   provider login may be interactive; nothing else should require
   confirmation") — a rule that was true in intent but not enforced in
   `agents/git_ops.py`'s code.
2. Once the contract finally reached `APPROVED` via the manual `/work`/
   `/review` sequence, there was no single point confirming "the whole
   round is actually done, and here's what happened" — the owner had to
   ask what happened, then run `/status`, to piece together the outcome.
   `/review` is a deliberate manual override (Tr5-base decision 1) that
   does not itself push the final checkpoint (by design — see `README.md`
   Lifecycle), so it wasn't obviously the finishing line either.

**Decision 11 — print a short recap after the final checkpoint.** New
`render_contract_summary(contract)` in `agents/contract_workflow.py`:
title, risk level, final status, the latest Architecture Review verdict
(round + reviewer), how many points were approved (`n/total`), the
distinct files the programmer touched across all points, and the latest
Implementation Review verdict plus its Out of Scope result (`OK` /
`FLAGGED`). A handful of lines, not the full contract — `render_contract`
already exists for that.

Wired into both places the final `- REVIEWED` checkpoint can land, so the
summary prints regardless of which path got there:
- `_review_and_commit()` (`agents/pipeline.py`) — the automatic
  `standard`-risk chain, right after its `commit_and_push` call.
- `commit_approved_contract()` — the manual `/commit <n>` override,
  covering both the `high`-risk owner-paced path and exactly the
  situation this test hit: a `standard`-risk contract finished by hand.

Deliberately not wired into `/review`'s bare `run_implementation_review`
call itself — that function can return `CHANGES_REQUESTED`, which isn't
"done," and printing a "final" summary there would be misleading.

**Non-interactive git, throughout `agents/git_ops.py`.** New
`_non_interactive_env()` merges `GIT_TERMINAL_PROMPT=0` and
`GCM_INTERACTIVE=Never` onto the current environment; every
`subprocess.run` git call in the module (`_run_git`, the cached-diff
check in `commit_and_push`, and both `git remote get-url` reads) now
passes it. A stale or missing credential now fails immediately with the
same clear `RuntimeError` any other git failure already produces (see
`commit_and_push`'s own docstring, PRINCIPLES.md P3 — never proceed on
top of unsaved state) instead of hanging indefinitely behind a prompt
nobody may notice. This isn't a new behavior being invented — it's
`AGENTS.md`'s existing "only provider login may be interactive" rule
actually being enforced by the code that runs git, closing a real gap
between the stated rule and what `git_ops.py` did.

**Tests**: `tests/test_contract_workflow.py` —
`test_render_contract_summary_recaps_a_completed_cycle` (asserts every
field appears: contract number, title, risk, final status, architecture
review verdict, points-approved count, touched files, implementation
review verdict, Out of Scope result) and
`test_render_contract_summary_flags_out_of_scope_findings` (a `False`
`out_of_scope_ok` renders as `FLAGGED`, not `OK`). `tests/
test_pipeline.py` — `test_commit_approved_contract_prints_a_round_summary`
and `test_create_contract_auto_chain_prints_a_round_summary` (via
`capsys`, confirm the summary actually reaches the console at both call
sites). `tests/test_git_ops.py` —
`test_run_git_disables_interactive_credential_prompts` (monkeypatches
`subprocess.run` to capture the `env` kwarg, asserts both variables are
set) and `test_commit_and_push_disables_interactive_credential_prompts_
throughout` (a real local-remote `commit_and_push` still succeeds
end-to-end with the non-interactive env in place, i.e. this doesn't break
credential-free git operations).

**Verification**: `python -m pytest -q` — 86/86 passing (6 new: 2 in
`test_contract_workflow.py`, 2 in `test_pipeline.py`, 2 in
`test_git_ops.py`).

## ADR-037: `parse_json_response` failures now include a bounded snippet
of the actual response

**Context.** After ADR-035's fix landed, the owner deleted and re-cloned
`Tr5-base-test` fresh from the now-fixed `Tr5-base` and re-ran the exact
same first reference command (`/new create project/HELLO.md ...`). It
failed the same way as before: `Error while creating the contract: The
agent did not return valid JSON. The response was not written to the
contract.` — with no way to tell, from that message alone, whether this
was a recurrence of ADR-035's root cause (something else now inflating
`memory/CURRENT_STATE.md`), a different cause entirely (e.g. the model
adding prose outside the expected JSON fence, or genuinely truncating
mid-generation), or a one-off nondeterministic slip.

**The actual gap.** `chat_architect.py`'s `/new` handler only prints
`str(error)` on failure (`print(f"\nError while creating the contract:
{error}")`); `parse_json_response`'s `ValueError` never carried anything
beyond the fixed sentence above. The moment the exception propagated, the
model's actual response — the one piece of evidence that could tell these
different failure modes apart — was gone. Nothing else in the codebase
retains it either (it's a local variable in `create_contract`/
`revise_contract`, never written to a file or notified anywhere). This
made every occurrence of this error, past or future, essentially
undiagnosable after the fact — a real gap independent of whatever
actually caused this specific instance.

**Fix.** `parse_json_response` (`agents/contract_workflow.py`) now embeds
a bounded diagnostic snippet of the actual response in the raised error:
the first 1200 and last 800 characters (with an "N characters omitted"
marker between them, when it's longer than that), via a new
`_diagnostic_snippet()` helper. Keeping the tail is deliberate, not
incidental: a truncation failure (a still-too-large input padding out
generation until an output-token cap cuts it off mid-object) shows up at
the *end* of the response, not the start — a head-only snippet would
have hidden exactly the evidence that failure mode needs. Bounded on both
ends so a response inflated by the same kind of oversized-input problem
ADR-035 fixed once doesn't get dumped whole into the console either.

**Tests** (`tests/test_contract_workflow.py`):
`test_parse_json_response_error_includes_the_raw_response` (prose with no
JSON at all surfaces verbatim in the error) and
`test_parse_json_response_error_keeps_both_ends_of_a_long_response` (a
long, deliberately unterminated response keeps both its head and tail,
shows the omitted-character count, and stays bounded — not a full dump).

**Verification**: `python -m pytest -q` — 88/88 passing (2 new).

**Status of the original incident**: unresolved as of this entry — this
ADR only fixes the *diagnosability* gap the recurrence exposed, not
necessarily the recurrence's own root cause, which was not yet known
when this was written (the raw response that would explain it was never
captured). Whether it happens again with this fix in place, and what the
newly-visible raw response actually shows, is the next real signal.

## ADR-038: Deep code review — a thread-leak on `ClaudeThread.close()` failure, and valid-JSON-missing-field left undiagnosable by ADR-037

Requested by the owner as a standalone "review the whole project deeply"
pass, independent of any specific incident. Read every `.py` module, every
agent role/command/config file, and the full `memory/DECISIONS.md` history
before drawing conclusions, then verified each finding against the actual
code/tests (grep for call sites, not just reading a docstring's claim)
before treating it as real. Two behavior-changing bugs were found and
fixed; two dead/vestigial files were also found and removed (logged in
`memory/CHANGE_LOG.md` instead, as light-path cleanup — see that entry).

**Bug 1 — `ClaudeThread.close()` (`agents/agent.py`) leaked its background
event-loop thread if `disconnect()` raised.** `close()` set `self._closed
= True`, then ran `self._client.disconnect()`, then stopped the loop and
joined the thread — with no `try`/`finally` between them. If `disconnect()`
raised, the loop was never told to stop and the thread was never joined;
since `_closed` was already `True`, a retried `close()` call would also be
a no-op, so the leak was permanent for the life of the process. This
mattered more here than in a typical long-lived client: Tr5-base decision
9 constructs and closes a brand-new `Agent` (and therefore a brand-new
`ClaudeThread`) for every single reviewer/programmer call, so any
transient disconnect failure (a dropped connection, a closed pipe) would
leak one thread per occurrence rather than once per process lifetime. The
constructor already handled the equivalent failure correctly (a
`connect()` failure inside `__init__`'s `try` stops the loop and joins the
thread before re-raising) — `close()` just never got the same treatment.
Fixed by wrapping the `disconnect()` call in `try`/`finally`, so the loop
stop and thread join always run, whether or not `disconnect()` raised; the
original exception still propagates to the caller afterward (this is not
a place to swallow it — the caller, e.g. `agents/pipeline.py`'s
`with reviewer_factory() as reviewer:` block, still needs to see a
disconnect failure). New test in `tests/test_agent.py`,
`test_claude_thread_close_stops_the_loop_even_if_disconnect_raises`:
constructs a `ClaudeThread` via `object.__new__` (bypassing `__init__`,
which needs a real login and a real `ClaudeSDKClient`) with a real
background event-loop thread and a fake client whose `disconnect()`
raises, then asserts the thread actually stops and joins even though the
exception propagates — a real thread, not a mock, so the assertion that
it stops is meaningful (in the spirit of P16/P4: don't verify a concurrency
fix against something that can't actually exhibit the bug).

**Bug 2 — a valid JSON response missing a field a caller reads
unconditionally fell through `parse_json_response`'s own error handling as
a bare `KeyError`.** ADR-037 fixed diagnosability for JSON that fails to
*parse* (embeds a bounded snippet of the raw response in the raised
`ValueError`), but a response that parses fine while missing e.g.
`"title"` (`create_contract`), `"verdict"`/`"findings"` (architecture
review), `"summary"`/`"notes"` (implementation), or
`"approved"`/`"reviews"`/`"out_of_scope_ok"`/`"out_of_scope_findings"`
(implementation review) was never checked by that function at all — the
first place any of those fields was actually read was a plain
`data["title"]`-style access in `agents/pipeline.py`, which raised an
undecorated `KeyError`. `chat_architect.py`'s generic `except Exception`
handlers print `str(error)`, so this surfaced as e.g. `Error while
creating the contract: 'title'` — the exact loss of diagnostic evidence
ADR-037 fixed for invalid JSON, left open for this closely related
failure mode. A second instance of the same root problem existed one
layer deeper: `ContractStore.record_programmer_result()` and
`record_implementation_review()` (`agents/contract_workflow.py`) built
`{int(item["point"]): item for item in notes}` (respectively `reviews`)
directly — a note or review missing its `"point"` key raised the same
kind of undecorated `KeyError`.

Fixed at both layers:
- `parse_json_response` now accepts an optional `required_keys:
  tuple[str, ...]` parameter; after parsing, it checks all are present
  and raises the same style of `ValueError` (missing-key names plus the
  same bounded raw-response snippet) if not. `agents/pipeline.py`'s four
  call sites (`create_contract`/`revise_contract`,
  `run_architecture_review`, `implement_next`,
  `run_implementation_review`) now pass the required keys for their own
  JSON schema.
- `record_programmer_result`/`record_implementation_review` now catch the
  `KeyError` from the `by_number` dict comprehension and re-raise a
  `ValueError` naming which key was missing, instead of letting the raw
  `KeyError` escape.
- New tests in `tests/test_contract_workflow.py`:
  `test_parse_json_response_missing_required_key_includes_raw_response`,
  `test_parse_json_response_required_keys_satisfied_passes_through`,
  `test_record_programmer_result_note_missing_point_key_raises_clear_error`,
  `test_record_implementation_review_missing_point_key_raises_clear_error`.

**Dead/vestigial files removed** (see `memory/CHANGE_LOG.md` for the
light-path entry): `agents/architect/commands/review_contract.md` (never
actually deleted when ADR-029 moved implementation review to the
`reviewer`) and `agents/reviewer/WORKING_STATE.md`/
`agents/programmer/WORKING_STATE.md` (ADR-031 documented these as already
deleted; they were not). `memory/CURRENT_STATE.md` regenerated afterward
via `run_discovery_scan()` to match.

**Verification**: `python -m pytest -q` — 93 total, 92 passed, 1
pre-existing environment failure unrelated to this review
(`test_pyaudio_backend_real_import_and_lifecycle` — this checkout's
`.venv` has no prebuilt `pyaudio` wheel for its Python version and no
system PortAudio headers to build one from source; not something this
review's changes touch or could fix, and not new — the dependency was
never installed in this checkout before this review either).
