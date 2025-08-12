#!/usr/bin/env python3
"""
Clean workspace by removing or backing up common build/cache/log artifacts.

Usage:
  py scripts/clean_workspace.py --dry-run
  py scripts/clean_workspace.py --delete
  py scripts/clean_workspace.py --backup

Default is --dry-run if neither --delete nor --backup is provided.

Safety:
- Skips .venv/ and backup/ by default.
- Only targets known junk patterns.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / "backup"

TOP_LEVEL_DIRS = [
    # Python / builds
    "build",
    "dist",
    "logs",
    os.path.join("app", "logs"),
    "coverage",
    # Node/Web
    "node_modules",
    ".parcel-cache",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
]

RECURSIVE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

ROOT_FILES = [
    ".coverage",
    "coverage.xml",
]

ROOT_LOG_GLOB = "*.log"
OS_JUNK_FILENAMES = {".DS_Store", "Thumbs.db"}

EXCLUDES_PREFIX = [str(ROOT / ".venv"), str(BACKUP_ROOT)]


def is_excluded(path: Path) -> bool:
    p = str(path)
    for prefix in EXCLUDES_PREFIX:
        if p.startswith(prefix):
            return True
    return False


def ensure_backup_dir() -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / f"clean-{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def move_to_backup(src: Path, backup_root: Path) -> None:
    rel = src.resolve().relative_to(ROOT)
    dst = backup_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def delete_path(p: Path) -> None:
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show what would be removed/moved")
    mode.add_argument("--delete", action="store_true", help="delete items instead of backing up")
    mode.add_argument("--backup", action="store_true", help="move items into backup/clean-<ts>/")
    args = ap.parse_args(argv)

    action = "dry-run"
    if args.delete:
        action = "delete"
    elif args.backup:
        action = "backup"

    print(f"Workspace root: {ROOT}")
    print(f"Action: {action}")

    candidates: list[Path] = []

    # 1) Top-level dirs
    for d in TOP_LEVEL_DIRS:
        p = ROOT / d
        if p.exists() and not is_excluded(p):
            candidates.append(p)

    # 2) Recursive cache dirs
    for dirpath, dirnames, _filenames in os.walk(ROOT):
        # Prune excluded paths early
        if any(str(Path(dirpath)).startswith(prefix) for prefix in EXCLUDES_PREFIX):
            # mutate dirnames to prevent descending
            dirnames[:] = []
            continue
        for name in list(dirnames):
            if name in RECURSIVE_DIR_NAMES:
                p = Path(dirpath) / name
                if p.exists() and not is_excluded(p):
                    candidates.append(p)
                    # don't descend into these
                    try:
                        dirnames.remove(name)
                    except ValueError:
                        pass

    # 3) Root files
    for f in ROOT_FILES:
        p = ROOT / f
        if p.exists() and not is_excluded(p):
            candidates.append(p)

    # 4) Root .log files
    for p in ROOT.glob(ROOT_LOG_GLOB):
        if p.is_file() and not is_excluded(p):
            candidates.append(p)

    # 5) OS junk anywhere
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if any(str(Path(dirpath)).startswith(prefix) for prefix in EXCLUDES_PREFIX):
            continue
        for name in filenames:
            if name in OS_JUNK_FILENAMES:
                p = Path(dirpath) / name
                if p.exists() and not is_excluded(p):
                    candidates.append(p)

    # Deduplicate while preserving order
    seen = set()
    uniq: list[Path] = []
    for p in candidates:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)

    if not uniq:
        print("Nothing to clean.")
        return 0

    print(f"Found {len(uniq)} item(s) to clean:")
    for p in uniq:
        print(" -", p)

    if action == "dry-run":
        print("Dry-run complete. Use --backup or --delete to apply.")
        return 0

    if action == "backup":
        backup_root = ensure_backup_dir()
        print(f"Backing up to: {backup_root}")
        for p in uniq:
            if not p.exists():
                continue
            print(" -> moving", p)
            move_to_backup(p, backup_root)
        print("Backup completed.")
        return 0

    # action == delete
    for p in uniq:
        if not p.exists():
            continue
        print(" -> deleting", p)
        delete_path(p)
    print("Delete completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
