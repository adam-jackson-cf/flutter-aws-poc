# Flutter Design Linter

This repository enforces the Flutter solution design through contract artifacts and cross-artifact governance rules, not source-code marker scans.

## Enforcement Model

- Rule engine: `scripts/linters/flutter-design/check-flutter-design-compliance.py`
- Portable policy: `scripts/linters/flutter-design/policy/flutter-design-policy.json`
- Project adapter: `scripts/linters/flutter-design/flutter-design-linter-profile.json`
- Core logic: `scripts/linters/flutter_design_support/`

The policy defines the rules. The adapter maps those rules to the repository artifact roots and schema files. The support package evaluates schema validity, identity requirements, publish readiness, workflow requirements, and evaluation evidence.

## Tier Model

- `R1`: Capability Definition and Safety Envelope schema integrity plus identity-context routing requirements
- `R2`: Evaluation Pack schema integrity plus publish-readiness evidence checks
- `R3`: Workflow Contract schema integrity plus process-contract requirements for higher-risk or process-scoped capabilities

There is no active `R4` lane in this baseline.

## Baseline State

The repo starts with empty artifact roots. That means the compliance linter is expected to fail until real contract artifacts are authored. This is intentional and should be treated as the BDD starting state.

## Usage

Run all active tiers:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py
```

Run the faster `R1/R2` view:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --skip R3
```

Emit machine-readable results:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --output json --timings
```

List the active rule catalog:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --list-rules
```

Validate waivers:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-waivers.py
```

## CI Lanes

Use the central runner:

```bash
bash scripts/run-ci-quality-gates.sh --lane=fast-r1r2
bash scripts/run-ci-quality-gates.sh --lane=quality-gates-core
bash scripts/run-ci-quality-gates.sh --lane=strict-r3
```

The ownership matrix is documented in `docs/references/flutter-design-control-ownership.md`.
