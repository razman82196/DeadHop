#!/usr/bin/env python3
"""
Run Ruff and Black repeatedly until the repository is clean.
- Applies fixes via `python -m ruff check --fix .` and `python -m black .`
- Verifies cleanliness via `python -m ruff check .` and `python -m black --check .`
- Respects configuration in pyproject.toml
- Stops when both are clean or after a max number of iterations.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_ITERS = 10


def run(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True)
    return proc.returncode


def ensure_tools():
    missing = []
    try:
        import ruff  # type: ignore  # noqa: F401
    except Exception:
        missing.append("ruff")
    try:
        import black  # type: ignore  # noqa: F401
    except Exception:
        missing.append("black")
    if missing:
        py = sys.executable
        print(
            "ERROR: Missing tools: "
            + ", ".join(missing)
            + "\nInstall them with:\n  "
            + f"{py} -m pip install "
            + " ".join(missing)
            + "\nOr install all:  "
            + f"{py} -m pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        sys.exit(1)


def py_module(cmd: list[str]) -> list[str]:
    """Build a command that runs a module via the current interpreter.

    Example: py_module(["ruff", "check", "--fix", "."]) ->
             [sys.executable, "-m", "ruff", "check", "--fix", "."]
    """
    return [sys.executable, "-m", *cmd]


def main() -> int:
    ensure_tools()

    for i in range(1, MAX_ITERS + 1):
        print(f"\n=== Iteration {i} ===")

        # Apply fixes (include Ruff unsafe fixes per request)
        ruff_fix_rc = run(py_module(["ruff", "check", "--fix", "--unsafe-fixes", "."]))
        black_fix_rc = run(py_module(["black", "."]))  # formats in-place

        # Check cleanliness
        ruff_check_rc = run(py_module(["ruff", "check", "."]))  # 0 when no violations
        black_check_rc = run(py_module(["black", "--check", "."]))  # 0 when already formatted

        print(
            f"ruff_fix_rc={ruff_fix_rc} ruff_check_rc={ruff_check_rc} "
            f"black_fix_rc={black_fix_rc} black_check_rc={black_check_rc}"
        )

        if ruff_check_rc == 0 and black_check_rc == 0:
            # Avoid non-ASCII output for Windows consoles under cp1252
            print("\nCLEAN: no further changes needed.")
            return 0

        # If nothing changed this iteration but still not clean, continue up to MAX_ITERS
        # (some rules require multiple passes as tools may influence each other)

    # Avoid non-ASCII output for Windows consoles under cp1252
    print(
        f"\nWARNING: Reached MAX_ITERS={MAX_ITERS} but there may still be issues. "
        "Consider fixing remaining Ruff diagnostics that are not auto-fixable."
    )
    # Return the last check status combined (non-zero indicates remaining issues)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
