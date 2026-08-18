# Change Log

Log of small fixes made without a contract (light path, see `AGENTS.md`
section "Light path for small fixes"). One line per fix: what, where, by
whom. Contract changes are not logged here — those have their own history
directly in `contracts/IMPLEMENTATION_CONTRACT_NNNN.md`.

Never deleted or overwritten — only a new entry is added.

- 2026-07-28: `agents/architect/commands/review_contract.md` — added an
  explicit instruction to also check the contract's `# Architecture Review`
  section (the reviewer's findings) during implementation review, not only
  the original point text. By Claude, during the PRINCIPLES.md migration
  (P10).
- 2026-07-28: `agents/programmer/ROLE.md` and
  `agents/programmer/commands/implement_contract.md` — added an explicit
  instruction to report a real architectural gap in a point's note instead
  of deciding it, rather than only covering "blocked". By Claude, during
  the PRINCIPLES.md migration (P13).
- 2026-07-28: `.gitignore` — added `.pytest-tmp/` and `.idea/` (previously
  flagged in the first review, revision point 1-2, and deferred); untracked
  the 6 already-committed `.idea/*` files via `git rm --cached` so they
  stop propagating into every project cloned from this repo as "point
  zero". `.pytest-tmp/` was not tracked in this particular checkout, so
  only the `.gitignore` entry was needed here — the fix was verified
  against a separate clone (`bod-nula`) where `.pytest-tmp/` was tracked
  with 25 leftover files; that clone needs the same `git rm --cached -r
  .pytest-tmp` applied directly. By Claude, checking `bod-nula`'s clonability.
- 2026-08-16: Removed `_to_delete/` (an accidentally committed leftover
  from transferring Tr5-base's ADR-028 bootstrap onto the owner's machine
  via Claude's device bridge — a temp transfer archive and a stale git
  lock placeholder, never meant to be tracked). By Claude, verifying the
  first push to `Tr5-base`.
- 2026-08-18: Removed `agents/architect/commands/review_contract.md` — a
  stale duplicate never actually deleted when ADR-029 moved implementation
  review to the `reviewer` (only `agents/reviewer/commands/review_contract.md`
  is loaded by any code path; the architect's own `COMMANDS.md` never
  listed it). Also removed `agents/reviewer/WORKING_STATE.md` and
  `agents/programmer/WORKING_STATE.md`, which ADR-031 already documented
  as deleted ("vestigial... never loaded, never a valid write target")
  but which were never actually removed from disk. Regenerated
  `memory/CURRENT_STATE.md` via `run_discovery_scan()` afterward so the
  checked-in scan matches the checked-in tree. By Claude, during a
  requested deep code review.
- 2026-08-18: `README.md` ("Installation") and `requirements.txt` —
  corrected the claim that `pyaudio` "installs from a prebuilt wheel with
  no extra steps" on Windows: verified against PyPI that `PyAudio` 0.2.14
  only publishes Windows wheels up to cp313, none yet for cp314+, so
  `pip install -r requirements.txt` on this checkout's own Python 3.14
  venv fell back to building `pyaudio` from source and failed on a
  missing `portaudio.h` (confirmed with `pip install --only-binary=:all:
  pyaudio --dry-run`, which found no matching distribution at all). Added
  a "Requires Python 3.13 or earlier" note to both files. By Claude,
  prompted by the owner after this exact failure occurred live during the
  deep code review's own test-dependency install.
