import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "deploy" / "bootstrap-shared-sandbox.sh"


@dataclass(frozen=True)
class BootstrapRunOptions:
    runtime_exists: bool
    endpoint_exists: bool
    extra_env: dict[str, str] = field(default_factory=dict)

FAKE_AWS_CLI_SCRIPT = """#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="${AWS_FAKE_LOG:?}"
STATE_DIR="${AWS_FAKE_STATE_DIR:?}"
mkdir -p "$STATE_DIR"
echo "$*" >> "$LOG_FILE"

while [[ "${1:-}" == "--region" || "${1:-}" == "--profile" ]]; do
  shift 2
done

SERVICE="${1:-}"
OPERATION="${2:-}"
shift 2 || true

case "${SERVICE}/${OPERATION}" in
  sts/get-caller-identity)
    if [[ "$*" == *"--query Account"* ]]; then
      echo "123456789012"
    else
      echo '{"Account":"123456789012","Arn":"arn:aws:iam::123456789012:user/test"}'
    fi
    ;;
  cloudformation/deploy)
    echo '{}'
    ;;
  cloudformation/describe-stacks)
    if [[ "$*" == *"RuntimeArtifactsBucketName"* ]]; then
      echo "agent-runtime-artifacts"
    elif [[ "$*" == *"RuntimeExecutionRoleArn"* ]]; then
      echo "arn:aws:iam::123456789012:role/agent-runtime"
    else
      echo ""
    fi
    ;;
  bedrock-agentcore-control/list-agent-runtimes)
    if [[ "${AWS_FAKE_RUNTIME_EXISTS:-1}" == "1" ]]; then
      echo '{"agentRuntimeId":"runtime-abcdefghij","agentRuntimeArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agent/abc:1","agentRuntimeVersion":"1","status":"READY","agentRuntimeName":"flutter_shared_platform_sandbox"}'
    else
      echo "null"
    fi
    ;;
  bedrock-agentcore-control/get-agent-runtime)
    echo '{"agentRuntimeId":"runtime-abcdefghij","agentRuntimeArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agent/abc:1","agentRuntimeVersion":"1","status":"READY","agentRuntimeName":"flutter_shared_platform_sandbox"}'
    ;;
  bedrock-agentcore-control/create-agent-runtime)
    printf "created" > "$STATE_DIR/runtime_created"
    echo '{"agentRuntimeId":"runtime-abcdefghij","agentRuntimeArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agent/abc:1","agentRuntimeVersion":"1","status":"CREATING","agentRuntimeName":"flutter_shared_platform_sandbox"}'
    ;;
  bedrock-agentcore-control/get-agent-runtime-endpoint)
    if [[ "${AWS_FAKE_ENDPOINT_EXISTS:-1}" == "1" || -f "$STATE_DIR/endpoint_created" ]]; then
      VERSION="${AWS_FAKE_ENDPOINT_VERSION:-1}"
      if [[ "${AWS_FAKE_OMIT_TARGET_VERSION:-0}" == "1" ]]; then
        printf '{"status":"READY","liveVersion":"%s","agentRuntimeEndpointArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agentEndpoint/ep-123"}\n' "$VERSION"
      else
        printf '{"status":"READY","liveVersion":"%s","targetVersion":"%s","agentRuntimeEndpointArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agentEndpoint/ep-123"}\n' "$VERSION" "$VERSION"
      fi
    else
      exit 255
    fi
    ;;
  bedrock-agentcore-control/create-agent-runtime-endpoint)
    printf "created" > "$STATE_DIR/endpoint_created"
    echo '{"status":"CREATING","liveVersion":"1","targetVersion":"1","agentRuntimeEndpointArn":"arn:aws:bedrock-agentcore:eu-west-1:123456789012:agentEndpoint/ep-123"}'
    ;;
  bedrock-agentcore-control/update-agent-runtime-endpoint)
    echo '{"status":"UPDATING"}'
    ;;
  s3/cp)
    printf "uploaded" > "$STATE_DIR/s3_uploaded"
    echo '{}'
    ;;
  *)
    echo "unexpected aws call: ${SERVICE}/${OPERATION}" >&2
    exit 1
    ;;
esac
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _install_fake_aws_cli(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    aws_path = bin_dir / "aws"
    _write_executable(aws_path, FAKE_AWS_CLI_SCRIPT)


def _install_fake_npm(tmp_path: Path) -> None:
    npm_path = tmp_path / "bin" / "npm"
    _write_executable(
        npm_path,
        """#!/usr/bin/env bash
set -euo pipefail
echo "PWD=$PWD ARGS=$*" >> "${NPM_FAKE_LOG:?}"
exit 0
""",
    )


def _install_fake_guard(tmp_path: Path) -> Path:
    guard_path = tmp_path / "fake-guard.sh"
    _write_executable(
        guard_path,
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "${GUARD_FAKE_LOG:?}"
echo "OVERALL_STATUS=PASS"
""",
    )
    return guard_path


def _run_bootstrap(
    tmp_path: Path,
    args: list[str],
    options: BootstrapRunOptions,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
    env["AWS_FAKE_LOG"] = str(tmp_path / "aws.log")
    env["AWS_FAKE_STATE_DIR"] = str(tmp_path / "state")
    env["NPM_FAKE_LOG"] = str(tmp_path / "npm.log")
    env["GUARD_FAKE_LOG"] = str(tmp_path / "guard.log")
    env["AWS_FAKE_RUNTIME_EXISTS"] = "1" if options.runtime_exists else "0"
    env["AWS_FAKE_ENDPOINT_EXISTS"] = "1" if options.endpoint_exists else "0"
    env["AWS_REGION"] = "eu-west-1"
    env["BEDROCK_REGION"] = "eu-west-1"
    env["CDK_DEFAULT_REGION"] = "eu-west-1"
    if options.extra_env:
        env.update(options.extra_env)

    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_bootstrap_uses_existing_runtime_and_endpoint(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    _install_fake_npm(tmp_path)
    guard_path = _install_fake_guard(tmp_path)

    completed = _run_bootstrap(
        tmp_path,
        ["--guard-script-path", str(guard_path)],
        BootstrapRunOptions(runtime_exists=True, endpoint_exists=True),
    )

    assert completed.returncode == 0
    npm_log = (tmp_path / "npm.log").read_text(encoding="utf-8")
    assert "PWD=" in npm_log and "/infra" in npm_log
    assert "exec -- cdk deploy FlutterAgentCorePocStack" in npm_log
    assert "AgentRuntimeEndpointArn=arn:aws:bedrock-agentcore:eu-west-1:123456789012:agentEndpoint/ep-123" in npm_log
    guard_log = (tmp_path / "guard.log").read_text(encoding="utf-8")
    assert "--mode enforce" in guard_log
    assert "--endpoint-name sandbox" in guard_log


def test_bootstrap_creates_runtime_and_endpoint_when_missing(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    _install_fake_npm(tmp_path)
    guard_path = _install_fake_guard(tmp_path)

    completed = _run_bootstrap(
        tmp_path,
        [
            "--guard-script-path",
            str(guard_path),
            "--runtime-role-arn",
            "arn:aws:iam::123456789012:role/agent-runtime",
            "--runtime-artifact-mode",
            "code",
            "--runtime-code-s3-bucket",
            "agent-runtime-artifacts",
            "--runtime-code-s3-prefix",
            "runtime/build",
        ],
        BootstrapRunOptions(runtime_exists=False, endpoint_exists=False),
    )

    assert completed.returncode == 0
    aws_log = (tmp_path / "aws.log").read_text(encoding="utf-8")
    assert "s3 cp" in aws_log
    assert "bedrock-agentcore-control create-agent-runtime" in aws_log
    assert "--agent-runtime-name flutter_shared_platform_sandbox" in aws_log
    assert "--role-arn arn:aws:iam::123456789012:role/agent-runtime" in aws_log
    assert "bedrock-agentcore-control create-agent-runtime-endpoint" in aws_log


def test_bootstrap_provisions_iac_bootstrap_resources_when_code_inputs_omitted(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    _install_fake_npm(tmp_path)
    guard_path = _install_fake_guard(tmp_path)

    completed = _run_bootstrap(
        tmp_path,
        ["--guard-script-path", str(guard_path)],
        BootstrapRunOptions(runtime_exists=False, endpoint_exists=False),
    )

    assert completed.returncode == 0
    aws_log = (tmp_path / "aws.log").read_text(encoding="utf-8")
    assert "cloudformation deploy" in aws_log
    assert "s3 cp" in aws_log
    assert "bedrock-agentcore-control create-agent-runtime" in aws_log
    assert "--agent-runtime-name flutter_shared_platform_sandbox" in aws_log
    assert "--role-arn arn:aws:iam::123456789012:role/agent-runtime" in aws_log


def test_bootstrap_accepts_ready_endpoint_without_target_version(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    _install_fake_npm(tmp_path)
    guard_path = _install_fake_guard(tmp_path)

    completed = _run_bootstrap(
        tmp_path,
        ["--guard-script-path", str(guard_path)],
        BootstrapRunOptions(
            runtime_exists=True,
            endpoint_exists=True,
            extra_env={"AWS_FAKE_OMIT_TARGET_VERSION": "1"},
        ),
    )

    assert completed.returncode == 0


def test_bootstrap_rejects_non_eu_west_1_region(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    _install_fake_npm(tmp_path)
    guard_path = _install_fake_guard(tmp_path)

    completed = _run_bootstrap(
        tmp_path,
        ["--guard-script-path", str(guard_path), "--region", "us-east-1"],
        BootstrapRunOptions(runtime_exists=True, endpoint_exists=True),
    )

    assert completed.returncode == 2
    assert "Region must be eu-west-1." in completed.stderr
