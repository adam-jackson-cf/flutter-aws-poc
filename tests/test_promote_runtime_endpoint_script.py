import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "promote-runtime-endpoint.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _install_fake_aws_cli(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    aws_path = bin_dir / "aws"
    _write_executable(
        aws_path,
        """#!/usr/bin/env bash
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
    echo '{"Account":"123456789012","Arn":"arn:aws:iam::123456789012:user/test"}'
    ;;
  cloudformation/describe-stacks)
    echo "${AWS_FAKE_STACK_RUNTIME_ID:-runtime-from-stack}"
    ;;
  bedrock-agentcore-control/list-agent-runtime-versions)
    DEFAULT_VERSION_LIST='{"runtimeVersions":[{"version":"1","status":"READY"},{"version":"10","status":"READY"},{"version":"2","status":"READY"}]}'
    echo "${AWS_FAKE_VERSION_LIST_JSON:-$DEFAULT_VERSION_LIST}"
    ;;
  bedrock-agentcore-control/update-agent-runtime-endpoint)
    TARGET_VERSION=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --target-version)
          TARGET_VERSION="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    echo "$TARGET_VERSION" > "$STATE_DIR/target_version"
    echo '{"status":"UPDATING"}'
    ;;
  bedrock-agentcore-control/get-agent-runtime-endpoint)
    COUNT=0
    if [[ -f "$STATE_DIR/get_count" ]]; then
      COUNT="$(cat "$STATE_DIR/get_count")"
    fi
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$STATE_DIR/get_count"

    READY_AFTER="${AWS_FAKE_READY_AFTER:-2}"
    TARGET_VERSION="$(cat "$STATE_DIR/target_version" 2>/dev/null || echo "${AWS_FAKE_FALLBACK_TARGET:-0}")"
    if (( COUNT < READY_AFTER )); then
      printf '{"status":"UPDATING","liveVersion":"%s","targetVersion":"%s"}\n' "${AWS_FAKE_INITIAL_LIVE_VERSION:-0}" "$TARGET_VERSION"
    else
      printf '{"status":"READY","liveVersion":"%s","targetVersion":"%s"}\n' "$TARGET_VERSION" "$TARGET_VERSION"
    fi
    ;;
  *)
    echo "unexpected aws call: ${SERVICE}/${OPERATION}" >&2
    exit 1
    ;;
esac
""",
    )


def _run_script(
    tmp_path: Path,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AWS_PROFILE", None)
    env.pop("AWS_REGION", None)
    env.update(extra_env or {})
    env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_help_includes_eu_west_default_and_candidate_hook() -> None:
    completed = subprocess.run(
        [str(SCRIPT_PATH), "--help"],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert "eu-west-1" in completed.stdout
    assert "--candidate-eval-cmd" in completed.stdout


def test_script_promotes_latest_ready_and_waits_for_ready(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    fake_log = tmp_path / "aws.log"
    fake_state = tmp_path / "state"
    completed = _run_script(
        tmp_path=tmp_path,
        args=[
            "--runtime-id",
            "runtime-test-123",
            "--poll-interval-seconds",
            "1",
            "--wait-timeout-seconds",
            "5",
        ],
        extra_env={
            "AWS_FAKE_LOG": str(fake_log),
            "AWS_FAKE_STATE_DIR": str(fake_state),
            "AWS_FAKE_INITIAL_LIVE_VERSION": "9",
            "AWS_FAKE_READY_AFTER": "2",
        },
    )

    assert completed.returncode == 0
    assert "CandidateVersion: 10" in completed.stdout
    assert "EndpointStatus=READY LiveVersion=10 TargetVersion=10" in completed.stdout

    aws_calls = fake_log.read_text(encoding="utf-8")
    assert "sts get-caller-identity" in aws_calls
    assert "bedrock-agentcore-control update-agent-runtime-endpoint" in aws_calls
    assert "--target-version 10" in aws_calls


def test_candidate_hook_failure_blocks_promotion(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)
    fake_log = tmp_path / "aws.log"
    fake_state = tmp_path / "state"
    hook_script = tmp_path / "candidate_hook.sh"
    hook_capture = tmp_path / "hook_capture.txt"
    _write_executable(
        hook_script,
        f"""#!/usr/bin/env bash
set -euo pipefail
echo "${{PROMOTION_RUNTIME_ID}}|${{PROMOTION_REGION}}|${{PROMOTION_ENDPOINT_NAME}}|${{PROMOTION_TARGET_VERSION}}" > "{hook_capture}"
exit 9
""",
    )

    completed = _run_script(
        tmp_path=tmp_path,
        args=[
            "--runtime-id",
            "runtime-hook-999",
            "--candidate-eval-cmd",
            str(hook_script),
        ],
        extra_env={
            "AWS_FAKE_LOG": str(fake_log),
            "AWS_FAKE_STATE_DIR": str(fake_state),
        },
    )

    assert completed.returncode != 0
    assert "Candidate eval hook failed; aborting promotion." in completed.stderr
    assert hook_capture.read_text(encoding="utf-8").strip() == "runtime-hook-999|eu-west-1|production|10"

    aws_calls = fake_log.read_text(encoding="utf-8")
    assert "bedrock-agentcore-control list-agent-runtime-versions" in aws_calls
    assert "bedrock-agentcore-control update-agent-runtime-endpoint" not in aws_calls
