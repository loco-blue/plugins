"""Pure validation rules for marketplace plugins (no I/O besides reading the plugin dir)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from loco_sdk.plugin.validate import check_version_bump as _check_version_bump
from loco_sdk.plugin.validate import validate_all

STRUCTURE_ERROR = "files must live under plugins/<namespace>/<name>/"


@dataclass(frozen=True)
class PluginDir:
    """A plugin directory at plugins/<namespace>/<name>."""

    namespace: str
    name: str
    path: Path

    @property
    def plugin_id(self) -> str:
        return f"{self.namespace}/{self.name}"

    @property
    def repository_path(self) -> str:
        return f"plugins/{self.namespace}/{self.name}"


def discover_plugin_dirs(repo_root: Path) -> list[PluginDir]:
    """Return every plugins/<ns>/<name> directory, sorted by plugin_id."""
    base = repo_root / "plugins"
    dirs = [
        PluginDir(ns.name, p.name, p)
        for ns in base.iterdir()
        if ns.is_dir()
        for p in ns.iterdir()
        if p.is_dir() and not p.name.startswith((".", "__"))
    ]
    return sorted(dirs, key=lambda d: d.plugin_id)


def plugin_ids_for_changed_files(changed: list[str]) -> tuple[set[str], list[str]]:
    """Map changed repo paths to plugin ids; files directly under plugins/ are errors."""
    ids: set[str] = set()
    errors: list[str] = []
    for raw in changed:
        f = raw.strip()
        if not f:
            continue
        parts = Path(f).parts
        if not parts or parts[0] != "plugins":
            continue
        if len(parts) < 4:
            errors.append(f"{f}: {STRUCTURE_ERROR}")
            continue
        ids.add(f"{parts[1]}/{parts[2]}")
    return ids, errors


def load_manifest(plugin_dir: Path) -> dict[str, Any]:
    """Parse plugin.yaml (top level only; file references are not resolved)."""
    data = yaml.safe_load((plugin_dir / "plugin.yaml").read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def validate_manifest(pd: PluginDir, manifest: dict[str, Any]) -> list[str]:
    """Return human-readable errors (empty list == valid).

    CI never ran the AST/provider checks (`include_code`/`include_providers`
    are left False) — those are CLI-only, not marketplace policy.
    """
    result = validate_all(
        pd.path,
        pd.namespace,
        pd.name,
        manifest,
        include_code=False,
        include_providers=False,
    )
    p = pd.plugin_id
    return [f"{p}: {e}" for e in result.all_errors]


def check_version_bump(base_version: str | None, head_version: str) -> str | None:
    """Changed plugin dirs must bump version vs base branch (None base == new plugin)."""
    return _check_version_bump(base_version, head_version)
