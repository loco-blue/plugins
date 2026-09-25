"""Deterministic .lpk builder — CI-specific glue (ingest entries, catalog)
around loco_sdk.plugin.build's shared deterministic zip builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loco_sdk.plugin.build import build_lpk as _build_lpk
from loco_sdk.plugin.build import source_digest
from tools.marketplace.manifest_rules import PluginDir, load_manifest

CATALOG_KEY = "catalog/index.json"


def artifact_key(ns: str, name: str, version: str) -> str:
    return f"{ns}/{name}/{version}.lpk"


def ingest_entry_key(ns: str, name: str, version: str) -> str:
    return f"{ns}/{name}/{version}.ingest.json"


@dataclass(frozen=True)
class BuildResult:
    plugin: PluginDir
    version: str
    artifact_path: Path
    sha256: str
    size_bytes: int
    ingest_entry: dict[str, Any]


def build_lpk(pd: PluginDir, out_dir: Path, commit_sha: str, commit_time: str) -> BuildResult:
    """Build {out_dir}/{ns}/{name}/{version}.lpk and its ingest entry."""
    manifest = load_manifest(pd.path)
    version = str(manifest["version"])
    key = artifact_key(pd.namespace, pd.name, version)
    artifact = out_dir / key
    metadata = {
        "build_date": commit_time,
        "build_tool": "loco-plugins-ci",
        "commit_sha": commit_sha,
        "plugin": pd.name,
        "version": version,
    }
    sha, size = _build_lpk(pd.path, artifact, metadata)
    readme = pd.path / "README.md"
    entry: dict[str, Any] = {
        "plugin_id": pd.plugin_id,
        "namespace": pd.namespace,
        "name": pd.name,
        "version": version,
        "commit_sha": commit_sha,
        "repository_path": pd.repository_path,
        "manifest": manifest,
        "readme_md": readme.read_text(encoding="utf-8") if readme.is_file() else "",
        "artifact_key": key,
        "sha256": sha,
        "signature": "",
        "size_bytes": size,
        "source_sha256": source_digest(pd.path),
    }
    return BuildResult(pd, version, artifact, sha, size, entry)


def build_catalog(dirs: list[PluginDir], commit_sha: str) -> dict[str, Any]:
    """Current HEAD catalog; cloud reconcile marks anything absent as removed."""
    return {
        "commit_sha": commit_sha,
        "plugins": [
            {"plugin_id": d.plugin_id, "version": str(load_manifest(d.path)["version"])}
            for d in sorted(dirs, key=lambda x: x.plugin_id)
        ],
    }
