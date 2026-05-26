"""Codex CLI wrapper — locate and execute the real ``codex`` binary with proxy env."""

import os
import shutil
import subprocess
import sys


def find_codex() -> str | None:
    """Locate the ``codex`` binary on PATH. Returns None if not found."""
    return shutil.which("codex")


def run_codex(args: list[str], proxy_env: dict[str, str] | None = None) -> int:
    """Execute ``codex`` with the given arguments and optional proxy environment.

    Args:
        args: Command-line arguments to pass to codex (excluding the binary name).
        proxy_env: Dict of extra environment variables (e.g. HTTP_PROXY).

    Returns:
        The exit code of the codex process.
    """
    codex_bin = find_codex()
    if codex_bin is None:
        print(
            "error: 'codex' not found on PATH. "
            "Install it from https://github.com/openai/codex",
            file=sys.stderr,
        )
        return 1

    env = os.environ.copy()
    if proxy_env:
        # Only override if not already explicitly set by the caller
        for key, value in proxy_env.items():
            if key.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
                env.setdefault(key, value)
                env.setdefault(key.lower(), value)

    try:
        proc = subprocess.run([codex_bin, *args], env=env, check=False)
        return proc.returncode
    except FileNotFoundError:
        print(f"error: '{codex_bin}' not found", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
