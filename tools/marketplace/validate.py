"""CLI: validate plugin manifests (PR mode = changed plugins only, --all = every plugin)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from tools.marketplace.manifest_rules import (
    PluginDir,
    check_version_bump,
    discover_plugin_dirs,
    load_manifest,
    plugin_ids_for_changed_files,
    validate_manifest,
)

BaseVersionReader = Callable[[Path, str, PluginDir], "str | None"]


def git_base_version(repo_root: Path, base_ref: str, pd: PluginDir) -> str | None:
    """Read plugin.yaml version at base_ref via `git show`; None if absent there."""
    proc = subprocess.run(
        ["git", "show", f"{base_ref}:{pd.repository_path}/plugin.yaml"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    data = yaml.safe_load(proc.stdout) or {}
    return str(data.get("version")) if data.get("version") is not None else None


def main(argv: list[str] | None = None, base_version_reader: BaseVersionReader = git_base_version) -> int:
    """Return 0 when valid, 1 otherwise."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--changed-files", type=Path)
    ap.add_argument("--base-ref", default="origin/main")
    ap.add_argument("--list-dirs", action="store_true", help="print validated plugin dirs")
    args = ap.parse_args(argv)

    root: Path = args.repo_root
    by_id = {d.plugin_id: d for d in discover_plugin_dirs(root)}
    errors: list[str] = []
    if args.all:
        targets = list(by_id.values())
    else:
        changed = args.changed_files.read_text(encoding="utf-8").splitlines()
        ids, structure_errors = plugin_ids_for_changed_files(changed)
        errors.extend(structure_errors)
        # ids missing from disk were deleted in this PR: nothing to validate.
        targets = [by_id[i] for i in sorted(ids) if i in by_id]

    for pd in targets:
        manifest = load_manifest(pd.path)
        errors.extend(validate_manifest(pd, manifest))
        if not args.all:
            bump = check_version_bump(
                base_version_reader(root, args.base_ref, pd), str(manifest.get("version", ""))
            )
            if bump:
                errors.append(f"{pd.plugin_id}: {bump}")

    for e in errors:
        print(f"ERROR {e}")
    if args.list_dirs:
        for pd in targets:
            print(pd.repository_path)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
