import hashlib
import json
import zipfile
from pathlib import Path

from tools.marketplace.build import (
    build_catalog,
    build_lpk,
    ingest_entry_key,
    source_digest,
)
from tools.marketplace.manifest_rules import PluginDir, discover_plugin_dirs
from tools.marketplace.tests.conftest import write_plugin

SHA = "0123456789abcdef0123456789abcdef01234567"
WHEN = "2026-09-24T10:00:00+07:00"


def _pd(repo: Path) -> PluginDir:
    write_plugin(repo, "acme", "hello")
    d = repo / "plugins" / "acme" / "hello"
    (d / "tests").mkdir()
    (d / "tests" / "test_x.py").write_text("def test(): pass\n", encoding="utf-8")
    (d / "nodes" / "__pycache__").mkdir()
    (d / "nodes" / "__pycache__" / "run.cpython-312.pyc").write_bytes(b"\x00")
    (d / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    return PluginDir("acme", "hello", d)


def test_build_is_deterministic(repo: Path, tmp_path: Path) -> None:
    pd = _pd(repo)
    a = build_lpk(pd, tmp_path / "a", SHA, WHEN)
    b = build_lpk(pd, tmp_path / "b", SHA, WHEN)
    assert a.sha256 == b.sha256
    assert a.artifact_path.read_bytes() == b.artifact_path.read_bytes()


def test_build_layout_mirrors_packager_and_excludes_noise(repo: Path, tmp_path: Path) -> None:
    res = build_lpk(_pd(repo), tmp_path, SHA, WHEN)
    names = zipfile.ZipFile(res.artifact_path).namelist()
    assert names == sorted(names[:-1]) + [".loco-metadata.json"]
    assert "plugin.yaml" in names and "README.md" in names and "nodes/run.py" in names
    assert "assets/icon.svg" in names
    assert not any("__pycache__" in n or n.startswith("tests/") for n in names)
    assert "requirements-dev.txt" not in names


def test_metadata_records_commit(repo: Path, tmp_path: Path) -> None:
    res = build_lpk(_pd(repo), tmp_path, SHA, WHEN)
    meta = json.loads(zipfile.ZipFile(res.artifact_path).read(".loco-metadata.json"))
    assert meta == {
        "build_date": WHEN,
        "build_tool": "loco-plugins-ci",
        "commit_sha": SHA,
        "plugin": "hello",
        "version": "1.0.0",
    }


def test_ingest_entry_contract(repo: Path, tmp_path: Path) -> None:
    res = build_lpk(_pd(repo), tmp_path, SHA, WHEN)
    e = res.ingest_entry
    data = res.artifact_path.read_bytes()
    assert res.artifact_path == tmp_path / "acme" / "hello" / "1.0.0.lpk"
    assert e["artifact_key"] == "acme/hello/1.0.0.lpk"
    assert e["sha256"] == hashlib.sha256(data).hexdigest() == res.sha256
    assert e["size_bytes"] == len(data) == res.size_bytes
    assert e["plugin_id"] == "acme/hello" and e["namespace"] == "acme" and e["name"] == "hello"
    assert e["repository_path"] == "plugins/acme/hello"
    assert e["commit_sha"] == SHA and e["version"] == "1.0.0"
    assert e["manifest"]["author"] == "acme"
    assert e["readme_md"] == "# hello\n"
    assert e["signature"] == ""
    assert e["source_sha256"] == source_digest(res.plugin.path)
    assert ingest_entry_key("acme", "hello", "1.0.0") == "acme/hello/1.0.0.ingest.json"


def test_source_digest_changes_with_content(repo: Path) -> None:
    pd = _pd(repo)
    before = source_digest(pd.path)
    (pd.path / "nodes" / "run.py").write_text("x = 2\n", encoding="utf-8")
    assert source_digest(pd.path) != before


def test_build_catalog(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", version="1.2.0")
    write_plugin(repo, "loco", "gmail", version="0.1.3")
    cat = build_catalog(discover_plugin_dirs(repo), SHA)
    assert cat == {
        "commit_sha": SHA,
        "plugins": [
            {"plugin_id": "acme/hello", "version": "1.2.0"},
            {"plugin_id": "loco/gmail", "version": "0.1.3"},
        ],
    }
