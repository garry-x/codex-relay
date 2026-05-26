"""Install the ``codex`` CLI binary via npm.

Supports:
- npm global install (primary method, works cross-platform)
- npm global update
- Proxy configuration for the install process
"""

import subprocess
import sys


def find_npm() -> str | None:
    """Locate ``npm`` on PATH."""
    import shutil

    return shutil.which("npm")


def check_codex_installed() -> bool:
    """Check if ``codex`` is already available on PATH."""
    import shutil

    return shutil.which("codex") is not None


def get_codex_version() -> str | None:
    """Return the installed codex version string, or None."""
    import shutil

    codex = shutil.which("codex")
    if not codex:
        return None
    try:
        result = subprocess.run(
            [codex, "--version"], capture_output=True, text=True, timeout=10
        )
        return (result.stdout + result.stderr).strip() or None
    except Exception:
        return None


def install_codex(
    proxy_env: dict[str, str] | None = None,
    version: str | None = None,
) -> int:
    """Install the ``codex`` CLI globally via npm.

    Args:
        proxy_env: Optional proxy environment variables for npm.
        version: Specific version to install (e.g. ``@openai/codex@0.1.0``).
                 If None, installs latest.

    Returns:
        Exit code (0 on success).
    """
    npm = find_npm()
    if npm is None:
        print(
            "error: 'npm' not found on PATH. Install Node.js first: https://nodejs.org",
            file=sys.stderr,
        )
        return 1

    pkg = "@openai/codex"
    if version:
        pkg = f"{pkg}@{version}"

    cmd = [npm, "install", "-g", pkg]

    env = None
    if proxy_env:
        import os

        env = os.environ.copy()
        for key, value in proxy_env.items():
            env[key] = value
            env[key.lower()] = value

    print(f"[codex-relay] Running: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, env=env, check=False)
        return proc.returncode
    except KeyboardInterrupt:
        print("\nInstallation cancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def update_codex(proxy_env: dict[str, str] | None = None) -> int:
    """Update the globally installed ``codex`` CLI to the latest version."""
    npm = find_npm()
    if npm is None:
        print(
            "error: 'npm' not found on PATH. Install Node.js first: https://nodejs.org",
            file=sys.stderr,
        )
        return 1

    cmd = [npm, "update", "-g", "@openai/codex"]

    env = None
    if proxy_env:
        import os

        env = os.environ.copy()
        for key, value in proxy_env.items():
            env[key] = value
            env[key.lower()] = value

    print(f"[codex-relay] Running: {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, env=env, check=False)
        return proc.returncode
    except KeyboardInterrupt:
        print("\nUpdate cancelled.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
