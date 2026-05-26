"""Proxy configuration management.

Supports three sources, resolved in priority order:
1. Environment variables (HTTP_PROXY, HTTPS_PROXY, ALL_PROXY)
2. Config file (~/.codex-relay/config.yaml)
3. Auto-fetch from a proxy provider URL (e.g. proxy-cheap)
"""

import os
from pathlib import Path
from typing import Optional

import requests
import yaml

CONFIG_DIR = Path.home() / ".codex-relay"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data


def _save_config(config: dict) -> None:
    _ensure_config_dir()
    CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))


def get_proxy_config() -> dict:
    """Return the current proxy configuration as a dict with keys:
    ``http``, ``https``, ``provider_url``.
    """
    config = _load_config()
    return {
        "http": config.get("http"),
        "https": config.get("https"),
        "provider_url": config.get("provider_url"),
    }


def set_proxy(http: Optional[str] = None, https: Optional[str] = None) -> None:
    """Persist manual proxy settings."""
    config = _load_config()
    if http is not None:
        config["http"] = http
    if https is not None:
        config["https"] = https
    _save_config(config)


def set_provider_url(url: str) -> None:
    """Persist a proxy provider URL (e.g. proxy-cheap auto-config endpoint)."""
    config = _load_config()
    config["provider_url"] = url
    _save_config(config)


def unset_proxy() -> None:
    """Remove all persisted proxy settings."""
    config = _load_config()
    config.pop("http", None)
    config.pop("https", None)
    config.pop("provider_url", None)
    if config:
        _save_config(config)
    elif CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def fetch_proxies_from_provider(url: str, timeout: int = 10) -> list[dict]:
    """Fetch proxy list from a provider URL.

    Returns a list of dicts with ``http`` and ``https`` keys.
    Handles both JSON and plain-text proxy list formats.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")

    if "json" in content_type:
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "proxies" in data:
            return data["proxies"]
        return [data]
    else:
        lines = [line.strip() for line in resp.text.strip().splitlines() if line.strip()]
        proxies = []
        for line in lines:
            proxies.append({"http": line, "https": line})
        return proxies


def resolve_proxy() -> dict[str, str]:
    """Resolve effective proxy env vars.

    Priority: env vars > config file > provider auto-fetch.

    Returns a dict with keys ready to merge into ``os.environ``:
    ``HTTP_PROXY``, ``HTTPS_PROXY``, ``ALL_PROXY`` (and lowercase variants).
    """
    # 1. Check environment variables first (highest priority)
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")

    if http_proxy or https_proxy or all_proxy:
        result = {}
        if http_proxy:
            result["HTTP_PROXY"] = http_proxy
            result["http_proxy"] = http_proxy
        if https_proxy:
            result["HTTPS_PROXY"] = https_proxy
            result["https_proxy"] = https_proxy
        if all_proxy:
            result["ALL_PROXY"] = all_proxy
            result["all_proxy"] = all_proxy
        return result

    # 2. Check config file
    config = get_proxy_config()
    config_http = config.get("http")
    config_https = config.get("https")
    if config_http or config_https:
        result = {}
        proxy_url = config_https or config_http
        if config_http:
            result["HTTP_PROXY"] = config_http
            result["http_proxy"] = config_http
        if config_https:
            result["HTTPS_PROXY"] = config_https
            result["https_proxy"] = config_https
        result["ALL_PROXY"] = proxy_url
        result["all_proxy"] = proxy_url
        return result

    # 3. Auto-fetch from provider URL
    provider_url = config.get("provider_url")
    if provider_url:
        try:
            proxies = fetch_proxies_from_provider(provider_url)
            if proxies:
                first = proxies[0]
                http = first.get("http", "")
                https = first.get("https", http)
                result = {}
                if http:
                    result["HTTP_PROXY"] = http
                    result["http_proxy"] = http
                if https:
                    result["HTTPS_PROXY"] = https
                    result["https_proxy"] = https
                if http:
                    result["ALL_PROXY"] = http
                    result["all_proxy"] = http
                return result
        except Exception:
            pass

    return {}


def test_proxy(
    proxy_url: str | None = None, test_url: str = "https://api.openai.com", timeout: int = 10
) -> dict:
    """Test proxy connectivity by making a request through it."""
    import time

    if proxy_url is None:
        resolved = resolve_proxy()
        proxy_url = resolved.get("HTTPS_PROXY") or resolved.get("HTTP_PROXY")

    if not proxy_url:
        return {
            "success": False,
            "status_code": None,
            "latency_ms": None,
            "error": "No proxy configured. Set one via: codex-relay config proxy set <url>",
            "proxy_url": "",
        }

    proxies = {"http": proxy_url, "https": proxy_url}
    start = time.monotonic()
    try:
        resp = requests.get(test_url, proxies=proxies, timeout=timeout, allow_redirects=False)
        latency = (time.monotonic() - start) * 1000
        return {
            "success": resp.status_code < 500,
            "status_code": resp.status_code,
            "latency_ms": round(latency, 1),
            "error": None,
            "proxy_url": proxy_url,
        }
    except requests.exceptions.ProxyError as e:
        latency = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "status_code": None,
            "latency_ms": round(latency, 1),
            "error": f"Proxy connection failed: {e}",
            "proxy_url": proxy_url,
        }
    except requests.exceptions.Timeout as e:
        latency = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "status_code": None,
            "latency_ms": round(latency, 1),
            "error": f"Proxy timeout after {timeout}s",
            "proxy_url": proxy_url,
        }
    except requests.exceptions.ConnectionError as e:
        latency = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "status_code": None,
            "latency_ms": round(latency, 1),
            "error": f"Connection failed: {e}",
            "proxy_url": proxy_url,
        }
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "status_code": None,
            "latency_ms": round(latency, 1),
            "error": str(e),
            "proxy_url": proxy_url,
        }
