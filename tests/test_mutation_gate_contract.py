import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run-mutation-gate.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_mutation_gate", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mutation_gate_targets_core_enforcement_modules() -> None:
    module = _load_module()

    targets = {
        target.file_path: {
            "tests": target.test_paths,
            "coverage": target.coverage_target,
            "package_dirs": target.package_dirs,
        }
        for target in module.TARGETS
    }

    assert targets == {
        "scripts/linters/flutter_design_support/artifacts.py": {
            "tests": (
                "tests/test_flutter_design_support.py",
                "tests/test_artifact_schema_linter.py",
            ),
            "coverage": "scripts/linters/flutter_design_support",
            "package_dirs": ("scripts",),
        },
        "scripts/linters/flutter_design_support/publish_readiness.py": {
            "tests": (
                "tests/test_flutter_design_support.py",
                "tests/test_publish_readiness_linter.py",
                "tests/test_flutter_design_compliance.py",
            ),
            "coverage": "scripts/linters/flutter_design_support",
            "package_dirs": ("scripts",),
        },
    }
