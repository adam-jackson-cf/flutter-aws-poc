# Runtime Implementation

This file explains when you need to change the shared runtime and where to do it.

## What The Runtime Does

The shared runtime loads the governed artifacts, executes supported capabilities, calls adapters, records audit data, and returns invocation results.

Primary files:

- [`runtime/engine.py`](../../../runtime/engine.py)
- [`runtime/agentcore_main.py`](../../../runtime/agentcore_main.py)
- [`runtime/repository.py`](../../../runtime/repository.py)
- [`runtime/models.py`](../../../runtime/models.py)

## When You Need A Runtime Change

You need a runtime change when:

- the new workflow needs new execution logic
- a new specialist must be dispatched
- a new tool path needs runtime handling
- the output shape changes materially

You do not need a runtime change for every workflow tweak. Some changes are artifact-only.

## How The Current Scenarios Work

### Player Protection

Runtime execution lives in:

- [`runtime/engine.py`](../../../runtime/engine.py)

Look at:

- `_run_player_protection`
- `_run_customer_360_specialist`

### SDLC PR Verifier

Runtime execution also lives in:

- [`runtime/engine.py`](../../../runtime/engine.py)

Look at:

- `_run_pr_verifier`
- `_run_diff_review_specialist`

## How To Add A New Workflow Path

1. Add the governed artifacts first.
2. Load them through the existing repository model.
3. Add the workflow execution branch in [`runtime/engine.py`](../../../runtime/engine.py) if the runtime does not already support the new capability.
4. Add or update adapter support as needed.
5. Add tests in `tests/test_shared_workflow_runtime.py`.
6. Run the strict gate.

## Publication And Bootstrap Support

The runtime also exposes a publication manifest and scenario bootstrap helpers:

- [`runtime/repository.py`](../../../runtime/repository.py)
- [`runtime/bootstrap.py`](../../../runtime/bootstrap.py)

Use these when your new workflow should appear in the shared published manifest.

## Common Mistakes

- editing runtime behavior before the governed artifacts exist
- adding a new capability id but forgetting to handle it in the runtime
- changing output structure without updating tests
