import json
import os
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class AgentCoreMcpClientError(RuntimeError):
    pass


def _is_allowed_host(host: str, allowed_hosts: List[str]) -> bool:
    for candidate in allowed_hosts:
        normalized = candidate.strip().lower()
        if not normalized:
            continue
        if normalized.startswith("."):
            if host.endswith(normalized):
                return True
            continue
        if host == normalized:
            return True
    return False


def _validate_gateway_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise AgentCoreMcpClientError("invalid_gateway_url_scheme")
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise AgentCoreMcpClientError("invalid_gateway_url_host")
    allowed_hosts = [entry.strip() for entry in os.environ.get("MCP_GATEWAY_ALLOWED_HOSTS", ".gateway.bedrock-agentcore.eu-west-1.amazonaws.com").split(",") if entry.strip()]
    if not _is_allowed_host(host, allowed_hosts):
        raise AgentCoreMcpClientError("disallowed_gateway_host")


class AgentCoreMcpClient:
    def __init__(self, gateway_url: str, region: str) -> None:
        if not gateway_url:
            raise AgentCoreMcpClientError("MCP gateway URL is required")
        _validate_gateway_url(gateway_url)
        self._gateway_url = gateway_url
        self._region = region
        self._session = boto3.Session(region_name=region)

    def _signed_post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = AWSRequest(
            method="POST",
            url=self._gateway_url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        credentials = self._session.get_credentials()
        if credentials is None:
            raise AgentCoreMcpClientError("No AWS credentials available for MCP gateway invocation")
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", self._region).add_auth(request)

        signed_headers = dict(request.headers.items())
        http_request = Request(self._gateway_url, data=body, headers=signed_headers, method="POST")
        try:
            with urlopen(http_request, timeout=30) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise AgentCoreMcpClientError(f"mcp_http_error:{exc.code}") from exc
        except URLError as exc:
            raise AgentCoreMcpClientError("mcp_url_error") from exc
        except TimeoutError as exc:
            raise AgentCoreMcpClientError("mcp_timeout") from exc

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentCoreMcpClientError("mcp_invalid_json_response") from exc

    def list_tools(self) -> List[Dict[str, Any]]:
        payload = {
            "jsonrpc": "2.0",
            "id": "tools-list",
            "method": "tools/list",
        }
        response = self._signed_post(payload)
        tools = response.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise AgentCoreMcpClientError("MCP tools/list returned non-list tools payload")
        return tools

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": "tools-call",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        return self._signed_post(payload)

    @staticmethod
    def extract_json_payload(call_result: Dict[str, Any]) -> Dict[str, Any]:
        result = call_result.get("result", {})
        content = result.get("content", [])
        if not isinstance(content, list) or not content:
            raise AgentCoreMcpClientError("MCP tools/call result missing content")

        text = content[0].get("text", "")
        if not text:
            raise AgentCoreMcpClientError("MCP tools/call content text is empty")

        return json.loads(text)
