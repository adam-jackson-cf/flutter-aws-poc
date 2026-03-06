# Flutter Design Linter

This linter enforces architecture controls derived from the Flutter solution design docs in `docs/flutter-uki-ai-platform-arch/`.

## Portability model

- Rule engine: `scripts/linters/flutter-design/check-flutter-design-compliance.py`
- Portable policy: `scripts/linters/flutter-design/policy/flutter-design-policy.json`
- Project adapter: `scripts/linters/flutter-design/flutter-design-linter-profile.json`

The policy defines reusable rule intent (`rule_id`, `tier`, `check_name`).
The adapter maps those rules to this repo's file sets, allowlists, and markers.

## Tier model

- `R1`: non-bypass LLM gateway routing, MCP gateway usage, region pinning
- `R2`: route-metadata parity, infra IAM boundary, gateway host validation
- `R3`: process-scope drift controls
- `R4`: regulated-scope drift controls

## Usage

Run all tiers:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py
```

Run PoC scope (`R1` and `R2`):

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --skip R3,R4
```

Emit machine-readable results:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --output json --timings
```

List rule catalog from policy:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --list-rules
```

## Waiver governance

Waivers are validated by:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-waivers.py
```

Expired waivers fail strict lanes.

## CI lanes

Use the central runner with explicit lanes:

```bash
bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2
bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
bash scripts/run-ci-quality-gates.sh --lane=extended-r3r4
```

The control ownership matrix is documented in `docs/references/flutter-design-control-ownership.md`.
