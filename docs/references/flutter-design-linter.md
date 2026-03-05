# Flutter Design Linter

This linter enforces architecture controls derived from the Flutter solution design docs in `docs/flutter-uki-ai-platform-arch/`.

## Portability model

- Rule engine: `scripts/linters/flutter-design/check-flutter-design-compliance.py`
- Project adapter profile: `scripts/linters/flutter-design/flutter-design-linter-profile.json`

The engine is reusable. To apply it in another repo, keep the script and provide a new profile file (file sets, allowlists, and scope markers).

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

Run the current PoC quality-gate scope (`R1` and `R2` only):

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --skip R3,R4
```

Quality gate wrapper default:

```bash
bash scripts/run-ci-quality-gates.sh
```

The gate script passes `--skip R3,R4` by default through `FLUTTER_DESIGN_LINTER_SKIP`. Override it to run additional tiers.

List rule catalog:

```bash
python3 scripts/linters/flutter-design/check-flutter-design-compliance.py --list-rules
```
