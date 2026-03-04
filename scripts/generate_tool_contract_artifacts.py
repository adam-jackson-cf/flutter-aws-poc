#!/usr/bin/env python3
import json
from pathlib import Path


def py_literal(value: object) -> str:
    return json.dumps(value, indent=4, sort_keys=True)


def ts_literal(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _load_contract(repo_root: Path) -> dict[str, object]:
    contract_path = repo_root / "contracts" / "jira_tools.contract.json"
    return json.loads(contract_path.read_text(encoding="utf-8"))


def _runtime_lines(contract: dict[str, object]) -> list[str]:
    contract_version = str(contract["version"])
    return [
        "# Auto-generated from contracts/jira_tools.contract.json.",
        "# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
        "",
        f"CONTRACT_VERSION = {json.dumps(contract_version)}",
        "",
        f"ISSUE_KEY_PATTERN = {json.dumps(r'\b[A-Z][A-Z0-9]+-\d+\b')}",
        "",
        f"INTENT_KEYWORDS = {py_literal(contract['intent_keywords'])}",
        "",
        f"RISK_HINT_TOKENS = {py_literal(contract['risk_hint_tokens'])}",
        "",
        f"MCP_TOOL_SCOPE_BY_INTENT = {py_literal(contract['mcp_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_SCOPE_BY_INTENT = {py_literal(contract['native_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_DESCRIPTIONS = {py_literal(contract['native_tool_descriptions'])}",
        "",
        f"TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {py_literal(contract['tool_completeness_fields_by_operation'])}",
        "",
        f"RUNTIME_INVOCATION_REQUEST_CONTRACT = {py_literal(contract['runtime_invocation_request_contract'])}",
        "",
        f"RUNTIME_INVOCATION_RESPONSE_CONTRACT = {py_literal(contract['runtime_invocation_response_contract'])}",
        "",
    ]


def _lambda_lines(contract: dict[str, object]) -> list[str]:
    contract_version = str(contract["version"])
    return [
        "# Auto-generated from contracts/jira_tools.contract.json.",
        "# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
        "",
        f"CONTRACT_VERSION = {json.dumps(contract_version)}",
        "",
        f"INTENT_KEYWORDS = {py_literal(contract['intent_keywords'])}",
        "",
        f"RISK_HINT_TOKENS = {py_literal(contract['risk_hint_tokens'])}",
        "",
        f"MCP_TOOL_SCOPE_BY_INTENT = {py_literal(contract['mcp_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_SCOPE_BY_INTENT = {py_literal(contract['native_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_DESCRIPTIONS = {py_literal(contract['native_tool_descriptions'])}",
        "",
        f"TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {py_literal(contract['tool_completeness_fields_by_operation'])}",
        "",
        f"GATEWAY_TOOLS = {py_literal(contract['gateway_tools'])}",
        "",
    ]


def _infra_lines(contract: dict[str, object]) -> list[str]:
    contract_version = str(contract["version"])
    return [
        "// Auto-generated from contracts/jira_tools.contract.json.",
        "// Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
        "",
        f"export const CONTRACT_VERSION = {json.dumps(contract_version)};",
        "",
        'export type ContractType = "string" | "array_string";',
        "",
        "export interface ContractProperty {",
        "  type: ContractType;",
        "  description?: string;",
        "}",
        "",
        "export interface ContractSchema {",
        "  properties: Record<string, ContractProperty>;",
        "  required: string[];",
        "}",
        "",
        "export interface GatewayToolContract {",
        "  name: string;",
        "  description: string;",
        "  input_schema: ContractSchema;",
        "  output_schema: ContractSchema;",
        "}",
        "",
        f"export const MCP_TOOL_SCOPE_BY_INTENT: Record<string, string[]> = {ts_literal(contract['mcp_tool_scope_by_intent'])};",
        "",
        f"export const GATEWAY_TOOLS: GatewayToolContract[] = {ts_literal(contract['gateway_tools'])};",
        "",
    ]


def _write_runtime_artifact(repo_root: Path, contract: dict[str, object]) -> None:
    runtime_out = repo_root / "runtime" / "sop_agent" / "domain" / "contracts.py"
    runtime_out.write_text("\n".join(_runtime_lines(contract)), encoding="utf-8")


def _write_lambda_artifact(repo_root: Path, contract: dict[str, object]) -> None:
    lambda_out = repo_root / "aws" / "lambda" / "contract_values.py"
    lambda_out.write_text("\n".join(_lambda_lines(contract)), encoding="utf-8")


def _write_infra_artifact(repo_root: Path, contract: dict[str, object]) -> None:
    infra_dir = repo_root / "infra" / "lib" / "generated"
    infra_dir.mkdir(parents=True, exist_ok=True)
    infra_out = infra_dir / "jira-tool-contract.ts"
    infra_out.write_text("\n".join(_infra_lines(contract)), encoding="utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contract = _load_contract(repo_root)
    _write_runtime_artifact(repo_root, contract)
    _write_lambda_artifact(repo_root, contract)
    _write_infra_artifact(repo_root, contract)


if __name__ == "__main__":
    main()
