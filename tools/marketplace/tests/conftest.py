"""Shared fixtures for marketplace tooling tests."""

from pathlib import Path

import pytest
import yaml


def write_plugin(root: Path, ns: str, dir_name: str, **overrides) -> Path:
    """Create a minimal valid plugin dir under root/plugins/<ns>/<name>."""
    d = root / "plugins" / ns / dir_name
    (d / "assets").mkdir(parents=True, exist_ok=True)
    (d / "nodes").mkdir(exist_ok=True)
    manifest = {
        "name": dir_name,
        "version": "1.0.0",
        "type": "node",
        "author": ns,
        "label": {"en_US": dir_name.title()},
        "icon": "icon.svg",
        "license": "MIT",
        "tags": ["utility"],
    }
    manifest.update(overrides)
    manifest = {k: v for k, v in manifest.items() if v is not None}
    (d / "plugin.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (d / "README.md").write_text(f"# {dir_name}\n", encoding="utf-8")
    (d / "__init__.py").write_text("", encoding="utf-8")
    (d / "assets" / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (d / "nodes" / "run.py").write_text("x = 1\n", encoding="utf-8")
    return d


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "plugins").mkdir()
    return tmp_path
