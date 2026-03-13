import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "guards" / "apply-flutter-design-aws-guards.sh"


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
    if [[ "$*" == *"--query Account"* ]]; then
      echo "123456789012"
    elif [[ "$*" == *"--query Arn"* ]]; then
      echo "arn:aws:iam::123456789012:user/test"
    else
      echo '{"Account":"123456789012","Arn":"arn:aws:iam::123456789012:user/test"}'
    fi
    ;;
  cloudformation/describe-stacks)
    if [[ "$*" == *"RuntimeArn"* ]]; then
      echo "arn:aws:bedrock-agentcore:eu-west-1:123456789012:runtime/runtime-123"
    elif [[ "$*" == *"RuntimeId"* ]]; then
      echo "runtime-123"
    elif [[ "$*" == *"GatewayUrl"* ]]; then
      echo "https://gateway.example.com"
    elif [[ "$*" == *"RuntimeEndpointArn"* ]]; then
      echo "arn:aws:bedrock-agentcore:eu-west-1:123456789012:endpoint/runtime-123/production"
    elif [[ "$*" == *"RuntimeEndpointStatus"* ]]; then
      echo "READY"
    else
      echo ""
    fi
    ;;
  cloudformation/describe-stack-resources)
    echo "llm-gateway-fn"
    ;;
  lambda/get-function)
    echo "arn:aws:iam::123456789012:role/llm-gateway-role"
    ;;
  bedrock-agentcore-control/get-agent-runtime-endpoint)
    echo '{"status":"READY","liveVersion":"1","targetVersion":"1"}'
    ;;
  bedrock-agentcore-control/update-agent-runtime-endpoint)
    echo '{"status":"UPDATING"}'
    ;;
  organizations/describe-organization)
    if [[ "${AWS_FAKE_ORG_AVAILABLE:-0}" == "1" ]]; then
      echo '{"Organization":{"Id":"o-test"}}'
    else
      exit 255
    fi
    ;;
  organizations/list-policies-for-target)
    if [[ -f "$STATE_DIR/policy_id" ]]; then
      cat "$STATE_DIR/policy_id"
    else
      echo "None"
    fi
    ;;
  organizations/create-policy)
    POLICY_ID="p-test123"
    CONTENT=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --content)
          CONTENT="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    printf "%s" "$POLICY_ID" > "$STATE_DIR/policy_id"
    printf "%s" "$CONTENT" > "$STATE_DIR/policy_content"
    echo '{"Policy":{"PolicySummary":{"Id":"p-test123"}}}'
    ;;
  organizations/describe-policy)
    if [[ -f "$STATE_DIR/policy_content" ]]; then
      cat "$STATE_DIR/policy_content"
    else
      echo '{}'
    fi
    ;;
  organizations/update-policy)
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --content)
          printf "%s" "${2:-}" > "$STATE_DIR/policy_content"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    echo '{}'
    ;;
  organizations/list-targets-for-policy)
    if [[ -f "$STATE_DIR/attached_target" ]]; then
      cat "$STATE_DIR/attached_target"
    else
      echo "None"
    fi
    ;;
  organizations/attach-policy)
    TARGET=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --target-id)
          TARGET="${2:-}"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done
    printf "%s" "$TARGET" > "$STATE_DIR/attached_target"
    echo '{}'
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
    *,
    org_available: bool,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AWS_PROFILE", None)
    env.pop("AWS_REGION", None)
    env["PATH"] = f"{tmp_path / 'bin'}:{env.get('PATH', '')}"
    env["AWS_FAKE_LOG"] = str(tmp_path / "aws.log")
    env["AWS_FAKE_STATE_DIR"] = str(tmp_path / "state")
    env["AWS_FAKE_ORG_AVAILABLE"] = "1" if org_available else "0"

    return subprocess.run(
        [str(SCRIPT_PATH), *args],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def test_help_lists_required_modes_and_scope() -> None:
    completed = subprocess.run(
        [str(SCRIPT_PATH), "--help"],
        cwd=str(REPO_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert "--mode <detect|enforce>" in completed.stdout
    assert "--target-scope <account|org>" in completed.stdout


def test_detect_mode_reports_drift_when_org_api_unavailable(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)

    completed = _run_script(
        tmp_path,
        [
            "--mode",
            "detect",
            "--target-scope",
            "account",
            "--target-id",
            "123456789012",
            "--stack-name",
            "FlutterAgentCorePocStack",
            "--region",
            "eu-west-1",
        ],
        org_available=False,
    )

    assert completed.returncode == 3
    assert "G1_REGION_GUARD=DRIFT" in completed.stdout
    assert "G2_NON_BYPASS=DRIFT" in completed.stdout
    assert "OVERALL_STATUS=DRIFT" in completed.stdout


def test_enforce_mode_creates_and_attaches_policy(tmp_path: Path) -> None:
    _install_fake_aws_cli(tmp_path)

    completed = _run_script(
        tmp_path,
        [
            "--mode",
            "enforce",
            "--target-scope",
            "account",
            "--target-id",
            "123456789012",
            "--stack-name",
            "FlutterAgentCorePocStack",
            "--region",
            "eu-west-1",
        ],
        org_available=True,
    )

    assert completed.returncode == 0
    assert "G1_REGION_GUARD=PASS" in completed.stdout
    assert "G2_NON_BYPASS=PASS" in completed.stdout
    assert "Applied changes:" in completed.stdout
    assert "Created SCP policy" in completed.stdout
    assert "Attached SCP policy" in completed.stdout
    assert "OVERALL_STATUS=PASS" in completed.stdout
