from typing import List
from urllib.parse import urlparse


def is_allowed_host(host: str, allowed_hosts: List[str]) -> bool:
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


def allowed_hosts_from_env(raw_value: str) -> List[str]:
    return [entry.strip() for entry in raw_value.split(",") if entry.strip()]


def validate_endpoint_url(url: str, env_var_name: str, default_allowed_hosts: str, env_getter: callable) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise RuntimeError(f"invalid_url_scheme:{env_var_name}")
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise RuntimeError(f"invalid_url_host:{env_var_name}")

    raw = env_getter(env_var_name, default_allowed_hosts)
    allowed_hosts = allowed_hosts_from_env(raw)
    if not is_allowed_host(host, allowed_hosts):
        raise RuntimeError(f"disallowed_url_host:{env_var_name}:{host}")
