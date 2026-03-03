# Test Quality Checklist (Lambda + Eval harness)

Use this checklist before landing harness-heavy changes.

## Test design
- Keep individual test functions focused to a single behavior branch group.
- Prefer one assertion theme per test:
  - argument parsing
  - module boundary behavior
  - retry/error behavior
  - payload formatting or schema validation
- Split long tests into helper-backed scenarios when line count or branch count grows.

## Complexity and readability checks
- Watch for function-length and branch depth in tests:
  - >80 lines or visibly multi-scenario should be split.
  - Cyclomatic hotspots should be covered by focused subtests.
- Replace in-function setup with small local helpers to reduce cognitive load.
- Add targeted comments only when intent is non-obvious.

## LLM and runtime-path hygiene
- Assert provider routing, timeout, and retry behavior explicitly.
- Include both happy-path and degraded-path assertions for:
  - parsing and validation failures
  - missing credentials/config
  - malformed payloads
  - empty/invalid schema structures
- Keep coverage of compatibility wrappers only where required for older call sites.

## Coverage expectations
- For any module touched in this repo, add/keep tests for:
  - one success case
  - one malformed input case
  - one boundary/retry/exception case
  - one cross-module integration callout where practical

## Review gate
Before merge, verify:
- duplicated utility logic is extracted into shared helpers where repeated across modules.
- wrapper functions still exist only when direct compatibility is required.
- new or changed helper imports are covered by targeted tests around wrappers.
- no new test exceeds the complexity budget without an explicit split.
