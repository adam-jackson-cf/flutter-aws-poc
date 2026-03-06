import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLUTTER_LINTER_PATH = REPO_ROOT / "scripts" / "linters" / "flutter-design" / "check-flutter-design-compliance.py"
LEGACY_LINTER_PATH = REPO_ROOT / "scripts" / "linters" / "llm-gateway-boundary" / "check-llm-gateway-boundary.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_gateway_rule_parity_between_flutter_and_legacy_checker(tmp_path: Path) -> None:
    flutter_mod = _load_module(FLUTTER_LINTER_PATH, "flutter_design_linter")
    legacy_mod = _load_module(LEGACY_LINTER_PATH, "legacy_gateway_linter")

    repo_root = tmp_path / "repo"
    service_dir = repo_root / "aws" / "lambda"
    runtime_dir = repo_root / "runtime"
    service_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)

    violating_source = (
        "import boto3\n"
        "from bedrock_client import call_model\n"
        "client = boto3.client('bedrock-runtime')\n"
        "OPENAI_BASE_URL = 'https://api.openai.com'\n"
    )
    service_path = service_dir / "service.py"
    service_path.write_text(violating_source, encoding="utf-8")

    # Flutter linter path
    flutter_mod.REPO_ROOT = repo_root
    adapter = {
        "file_sets": {
            "python_service_code": ["aws/lambda", "runtime"],
        },
        "exclude_dirs": [],
        "allowlists": {
            "llm_gateway_boundary": [],
        },
        "markers": {
            "direct_provider_transport_markers": [
                "api.openai.com",
                "/responses",
                "OPENAI_BASE_URL",
            ]
        },
    }
    context = flutter_mod.RuleContext(adapter)
    flutter_violations = set(flutter_mod._check_r1_llm_gateway_non_bypass(context))

    # Legacy linter path
    legacy_mod.REPO_ROOT = repo_root
    legacy_mod.SCAN_ROOTS = (
        repo_root / "aws" / "lambda",
        repo_root / "runtime",
    )
    legacy_mod.ALLOWLIST = set()
    legacy_violations: set[str] = set()
    for path in legacy_mod.iter_python_files():
        legacy_violations.update(
            legacy_mod.path_violations(
                path=path,
                repo_root=repo_root,
                allowlist=legacy_mod.ALLOWLIST,
                direct_markers=legacy_mod.DIRECT_PROVIDER_TRANSPORT_MARKERS,
            )
        )

    assert flutter_violations == legacy_violations
