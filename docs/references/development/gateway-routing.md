# Gateway Routing

This file explains the LLM routing surface for workflows on this platform.

## What The Workflow Sees

Every current Capability Definition routes through:

- `routing.llm_route = "llm_gateway"`

The allowed model families are declared per capability.

Schema source:

- [`contracts/schemas/capability-definition.schema.json`](../../../contracts/schemas/capability-definition.schema.json)

## Where Gateway Logic Lives

Primary file:

- [`infra/lib/shared-gateway.ts`](../../../infra/lib/shared-gateway.ts)

Related deployment wiring:

- [`infra/lib/flutter-agentcore-poc-stack.ts`](../../../infra/lib/flutter-agentcore-poc-stack.ts)
- [`infra/lib/runtime-bindings.ts`](../../../infra/lib/runtime-bindings.ts)

## When You Need To Change Gateway Routing

You need a gateway change when:

- adding a new provider family
- changing how the shared gateway is wired into the stack
- changing runtime environment bindings for the gateway

You do not need a gateway change just because you created a new workflow that still uses the existing shared route.

## How The Existing Workflows Use It

Both PP and SDLC:

- set `llm_route` to `llm_gateway`
- allow `bedrock`

Examples:

- [`capability-definitions/player-protection-case-orchestrator.json`](../../../capability-definitions/player-protection-case-orchestrator.json)
- [`capability-definitions/pr-verifier-orchestrator.json`](../../../capability-definitions/pr-verifier-orchestrator.json)

## How To Add A New Provider Or Route

1. Confirm the new workflow cannot use the existing gateway behavior unchanged.
2. Update the gateway implementation in [`infra/lib/shared-gateway.ts`](../../../infra/lib/shared-gateway.ts).
3. Update the capability `allowed_model_families` if needed.
4. Update infra wiring if the provider needs new environment bindings.
5. Add or update tests and strict gate coverage.
6. Deploy when the change requires real provider or environment proof.

## Common Mistakes

- changing `allowed_model_families` without gateway support
- treating gateway routing as a per-scenario stack concern
- assuming a new workflow automatically requires a new gateway route
