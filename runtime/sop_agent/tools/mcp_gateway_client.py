import json
from typing import Any, Dict, List
from urllib.request import Request, urlopen

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def mcp_signed_post(gateway_url: str, region: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = AWSRequest(
        method="POST",
        url=gateway_url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    credentials = boto3.Session(region_name=region).get_credentials()
    if credentials is None:
        raise RuntimeError("missing_aws_credentials_for_mcp")
    SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", region).add_auth(request)
    signed_headers = dict(request.headers.items())
    http_request = Request(gateway_url, data=body, headers=signed_headers, method="POST")
    with urlopen(http_request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_gateway_tools(gateway_url: str, region: str) -> List[Dict[str, Any]]:
    response = mcp_signed_post(
        gateway_url=gateway_url,
        region=region,
        payload={"jsonrpc": "2.0", "id": "tools-list", "method": "tools/list"},
    )
    tools = response.get("result", {}).get("tools", [])
    if not isinstance(tools, list):
        raise RuntimeError("invalid_tools_list_payload")
    return tools


def call_gateway_tool(gateway_url: str, region: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return mcp_signed_post(
        gateway_url=gateway_url,
        region=region,
        payload={
            "jsonrpc": "2.0",
            "id": "tools-call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )


def extract_gateway_tool_payload(call_response: Dict[str, Any]) -> Dict[str, Any]:
    content = call_response.get("result", {}).get("content", [])
    if not isinstance(content, list) or not content:
        raise RuntimeError("invalid_gateway_tool_response_content")
    text = content[0].get("text", "")
    if not text:
        raise RuntimeError("empty_gateway_tool_response_content")
    return json.loads(text)
