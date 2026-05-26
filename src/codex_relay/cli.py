"""Click CLI — ``codex-relay`` entry point."""

import sys
from importlib.metadata import version as pkg_version
from typing import Optional

import click

from codex_relay import __version__
from codex_relay.codex import find_codex, run_codex
from codex_relay.install import (
    check_codex_installed,
    get_codex_version,
    install_codex,
    update_codex,
)
from codex_relay.proxy import (
    fetch_proxies_from_provider,
    get_proxy_config,
    resolve_proxy,
    set_provider_url,
    set_proxy,
    test_proxy,
    unset_proxy,
)


def _show_version():
    """Print version info for both codex-relay and the underlying codex CLI."""
    click.echo(f"codex-relay {__version__}")
    codex_bin = find_codex()
    if codex_bin:
        import subprocess

        try:
            result = subprocess.run(
                [codex_bin, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                click.echo(f"codex: {result.stdout.strip()}")
        except Exception:
            pass
    else:
        click.echo("codex: not found on PATH")


# ── config group ──────────────────────────────────────────────────────────


@click.group()
def config_cmd():
    """Manage codex-relay configuration."""


@config_cmd.group()
def proxy():
    """Manage HTTP proxy settings."""


@proxy.command("set")
@click.argument("url")
def proxy_set(url: str):
    """Set proxy provider URL (e.g. proxy-cheap auto-config endpoint).

    \b
    Examples:
      codex-relay config proxy set https://proxy-cheap.com/api/proxies
      codex-relay config proxy set http://user:pass@proxy.example.com:8080
    """
    if url.startswith("http://") or url.startswith("https://"):
        if "/api/" in url or "/proxy" in url.lower() or "list" in url.lower():
            set_provider_url(url)
            click.echo(f"Proxy provider URL set to: {url}")
            click.echo("Proxies will be auto-fetched on each run.")
        else:
            set_proxy(http=url, https=url)
            click.echo(f"Proxy set to: {url}")
    else:
        set_proxy(http=url, https=url)
        click.echo(f"Proxy set to: {url}")


@proxy.command("show")
def proxy_show():
    """Display current proxy configuration."""
    config = get_proxy_config()
    env_proxy = (
        __import__("os").environ.get("HTTP_PROXY")
        or __import__("os").environ.get("http_proxy")
    )

    if env_proxy:
        click.echo(f"HTTP_PROXY (env): {env_proxy}")
    if config.get("http"):
        click.echo(f"HTTP proxy (config): {config['http']}")
    if config.get("https"):
        click.echo(f"HTTPS proxy (config): {config['https']}")
    if config.get("provider_url"):
        click.echo(f"Provider URL (config): {config['provider_url']}")

    if not env_proxy and not any(config.values()):
        resolved = resolve_proxy()
        if resolved:
            click.echo("Resolved effective proxy:")
            for k, v in resolved.items():
                if k == k.upper():
                    click.echo(f"  {k}={v}")
        else:
            click.echo("No proxy configured.")


@proxy.command("unset")
def proxy_unset():
    """Remove all persisted proxy settings."""
    unset_proxy()
    click.echo("Proxy configuration cleared.")


@proxy.command("fetch")
@click.argument("url")
def proxy_fetch(url: str):
    """Test-fetch proxies from a provider URL."""
    click.echo(f"Fetching proxies from: {url}")
    try:
        proxies = fetch_proxies_from_provider(url)
        click.echo(f"Got {len(proxies)} proxy entries:")
        for i, p in enumerate(proxies[:10]):
            click.echo(f"  [{i}] http={p.get('http')} https={p.get('https')}")
        if len(proxies) > 10:
            click.echo(f"  ... and {len(proxies) - 10} more")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@proxy.command("test")
@click.option(
    "--url",
    "test_url",
    default="https://api.openai.com",
    help="URL to test through the proxy.",
)
@click.option(
    "--timeout",
    default=10,
    show_default=True,
    help="Connection timeout in seconds.",
)
def proxy_test(test_url: str, timeout: int):
    """Test proxy connectivity.

    Sends a request through the configured proxy and reports
    success/failure, status code, and latency.

    \b
    Examples:
      codex-relay config proxy test
      codex-relay config proxy test --url https://httpbin.org/ip
      codex-relay config proxy test --timeout 5
    """
    result = test_proxy(test_url=test_url, timeout=timeout)
    click.echo(f"Proxy:    {result['proxy_url'] or '(none configured)'}")
    click.echo(f"Test URL: {test_url}")
    click.echo(f"Status:   {result['status_code'] or 'N/A'}")
    click.echo(f"Latency:  {result['latency_ms']}ms" if result["latency_ms"] else "Latency:  N/A")

    if result["success"]:
        click.echo("Result:   OK — proxy is reachable")
    else:
        click.echo(f"Result:   FAIL — {result['error']}")
        raise SystemExit(1)


# ── run command ────────────────────────────────────────────────────────────


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run(args: tuple[str, ...]):
    """Run codex with the configured proxy applied.

    All arguments after ``run`` are passed directly to the ``codex`` binary.

    \b
    Examples:
      codex-relay run chat
      codex-relay run --help
      codex-relay run generate "Hello, world"
    """
    proxy_env = resolve_proxy()
    if proxy_env:
        http = proxy_env.get("HTTP_PROXY", "")
        click.echo(f"[codex-relay] using proxy: {http}", err=True)
    exit_code = run_codex(list(args), proxy_env=proxy_env)
    raise SystemExit(exit_code)


# ── install command ────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--version",
    "codex_version",
    default=None,
    help="Install a specific codex version (e.g. 0.1.0).",
)
@click.option(
    "--update",
    "update_mode",
    is_flag=True,
    help="Update an existing codex installation to the latest version.",
)
def install(codex_version: str | None, update_mode: bool):
    """Install or update the OpenAI Codex CLI via npm.

    Downloads and installs @openai/codex globally using npm.
    Proxy settings are automatically applied for the install process.

    \b
    Examples:
      codex-relay install                # install latest codex
      codex-relay install --version 0.1.0 # install specific version
      codex-relay install --update        # update existing installation
    """
    proxy_env = resolve_proxy()

    if update_mode:
        if not check_codex_installed():
            click.echo("codex is not installed. Use 'codex-relay install' to install it.")
            raise SystemExit(1)

        current = get_codex_version()
        click.echo(f"Current codex version: {current or 'unknown'}")
        if proxy_env:
            http = proxy_env.get("HTTP_PROXY", "")
            click.echo(f"[codex-relay] using proxy: {http}", err=True)

        exit_code = update_codex(proxy_env=proxy_env)
        if exit_code == 0:
            new_ver = get_codex_version()
            click.echo(f"Updated codex to: {new_ver or 'latest'}")
        else:
            click.echo("Update failed.", err=True)
        raise SystemExit(exit_code)

    if check_codex_installed() and not codex_version:
        current = get_codex_version()
        click.echo(f"codex is already installed ({current or 'unknown'}).")
        click.echo("Use --update to upgrade, or --version to install a specific version.")
        return

    if proxy_env:
        http = proxy_env.get("HTTP_PROXY", "")
        click.echo(f"[codex-relay] using proxy: {http}", err=True)

    click.echo("Installing @openai/codex via npm ...")
    exit_code = install_codex(proxy_env=proxy_env, version=codex_version)
    if exit_code == 0:
        new_ver = get_codex_version()
        click.echo(f"Install complete: {new_ver or 'latest'}")
    else:
        click.echo("Install failed.", err=True)
    raise SystemExit(exit_code)


# ── main CLI group ─────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Show version information.")
@click.pass_context
def main(ctx: click.Context, version: bool):
    """codex-relay — A wrapper for the OpenAI Codex CLI with proxy support.

    \b
    Commands:
      config     Manage proxy and other configuration
      install    Install or update the OpenAI Codex CLI
      run        Run codex with proxy applied

    \b
    Any unrecognized command is passed directly to the ``codex`` binary.
    Examples:
      codex-relay chat          # runs: codex chat (with proxy)
      codex-relay generate "..." # runs: codex generate "..."
    """
    if version:
        _show_version()
        ctx.exit()

    if ctx.invoked_subcommand is None:
        # Passthrough mode: forward everything as codex args
        # sys.argv[1:] are what came after 'codex-relay'
        args = sys.argv[1:]
        if not args:
            click.echo(ctx.get_help())
            return
        proxy_env = resolve_proxy()
        if proxy_env:
            http = proxy_env.get("HTTP_PROXY", "")
            click.echo(f"[codex-relay] using proxy: {http}", err=True)
        exit_code = run_codex(args, proxy_env=proxy_env)
        ctx.exit(exit_code)


main.add_command(config_cmd, name="config")
main.add_command(install)
main.add_command(run)
