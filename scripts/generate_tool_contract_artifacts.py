#!/usr/bin/env python3
import json
from pathlib import Path


def py_literal(value: object) -> str:
    return json.dumps(value, indent=4, sort_keys=True)


def ts_literal(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    contract_path = repo_root / "contracts" / "jira_tools.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    runtime_lines = [
        "# Auto-generated from contracts/jira_tools.contract.json.",
        "# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
        "",
        f"ISSUE_KEY_PATTERN = {json.dumps(r'\b[A-Z][A-Z0-9]+-\d+\b')}",
        "",
        f"INTENT_KEYWORDS = {py_literal(contract['intent_keywords'])}",
        "",
        f"RISK_HINT_TOKENS = {py_literal(contract['risk_hint_tokens'])}",
        "",
        f"MCP_EXPECTED_TOOL = {json.dumps(contract['mcp_expected_tool'])}",
        f"NATIVE_EXPECTED_TOOL = {json.dumps(contract['native_expected_tool'])}",
        "",
        f"MCP_TOOL_SCOPE_BY_INTENT = {py_literal(contract['mcp_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_SCOPE_BY_INTENT = {py_literal(contract['native_tool_scope_by_intent'])}",
        "",
        f"NATIVE_TOOL_DESCRIPTIONS = {py_literal(contract['native_tool_descriptions'])}",
        "",
        f"TOOL_COMPLETENESS_FIELDS_BY_OPERATION = {py_literal(contract['tool_completeness_fields_by_operation'])}",
        "",
    ]
    runtime_out = repo_root / "runtime" / "sop_agent" / "domain" / "contracts.py"
    runtime_out.write_text("\n".join(runtime_lines), encoding="utf-8")

    lambda_lines = [
        "# Auto-generated from contracts/jira_tools.contract.json.",
        "# Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
        "",
        f"INTENT_KEYWORDS = {py_literal(contract['intent_keywords'])}",
        "",
        f"RISK_HINT_TOKENS = {py_literal(contract['risk_hint_tokens'])}",
        "",
        f"MCP_EXPECTED_TOOL = {json.dumps(contract['mcp_expected_tool'])}",
        f"NATIVE_EXPECTED_TOOL = {json.dumps(contract['native_expected_tool'])}",
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
    lambda_out = repo_root / "aws" / "lambda" / "contract_values.py"
    lambda_out.write_text("\n".join(lambda_lines), encoding="utf-8")

    infra_dir = repo_root / "infra" / "lib" / "generated"
    infra_dir.mkdir(parents=True, exist_ok=True)
    infra_lines = [
        "// Auto-generated from contracts/jira_tools.contract.json.",
        "// Do not edit by hand; run scripts/generate_tool_contract_artifacts.py.",
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
        f"export const MCP_EXPECTED_TOOL = {json.dumps(contract['mcp_expected_tool'])};",
        f"export const MCP_TOOL_SCOPE_BY_INTENT: Record<string, string[]> = {ts_literal(contract['mcp_tool_scope_by_intent'])};",
        "",
        f"export const GATEWAY_TOOLS: GatewayToolContract[] = {ts_literal(contract['gateway_tools'])};",
        "",
    ]
    infra_out = infra_dir / "jira-tool-contract.ts"
    infra_out.write_text("\n".join(infra_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
