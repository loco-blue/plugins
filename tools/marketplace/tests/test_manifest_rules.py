from pathlib import Path

from tools.marketplace.manifest_rules import (
    PluginDir,
    check_version_bump,
    discover_plugin_dirs,
    load_manifest,
    plugin_ids_for_changed_files,
    validate_manifest,
)
from tools.marketplace.tests.conftest import write_plugin


def _validate(repo: Path, ns: str, name: str) -> list[str]:
    pd = PluginDir(ns, name, repo / "plugins" / ns / name)
    return validate_manifest(pd, load_manifest(pd.path))


def test_valid_plugin_has_no_errors(repo: Path) -> None:
    write_plugin(repo, "acme", "hello")
    assert _validate(repo, "acme", "hello") == []


def test_author_must_equal_namespace(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", author="loco")
    errors = _validate(repo, "acme", "hello")
    assert any("author" in e and "namespace" in e for e in errors)


def test_missing_author_is_rejected(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", author=None)
    assert any("author" in e for e in _validate(repo, "acme", "hello"))


def test_name_must_equal_directory(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", name="other")
    assert any("name" in e and "directory" in e for e in _validate(repo, "acme", "hello"))


def test_reserved_namespace_is_rejected(repo: Path) -> None:
    # "marketplace" would be shadowed by console route /plugins/marketplace/<ns>/<name>.
    write_plugin(repo, "marketplace", "hello")
    assert any("reserved" in e for e in _validate(repo, "marketplace", "hello"))


def test_non_semver_version_is_rejected(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", version="1.0")
    assert any("semver" in e for e in _validate(repo, "acme", "hello"))


def test_unknown_license_is_rejected(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", license="Proprietary")
    assert any("license" in e for e in _validate(repo, "acme", "hello"))


def test_tags_must_be_kebab_case_and_bounded(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", tags=["Bad Tag"])
    assert any("tag" in e for e in _validate(repo, "acme", "hello"))
    write_plugin(repo, "acme", "hello2", tags=[f"t{i}" for i in range(9)])
    assert any("at most 8" in e for e in _validate(repo, "acme", "hello2"))
    write_plugin(repo, "acme", "hello3", tags=[])
    assert any("at least 1" in e for e in _validate(repo, "acme", "hello3"))


def test_readme_required(repo: Path) -> None:
    d = write_plugin(repo, "acme", "hello")
    (d / "README.md").unlink()
    assert any("README.md" in e for e in _validate(repo, "acme", "hello"))


def test_icon_must_exist_in_assets(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", icon="missing.svg")
    assert any("icon" in e for e in _validate(repo, "acme", "hello"))


def test_schema_violation_is_reported(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", permissions="not-a-list")
    assert any("permissions" in e for e in _validate(repo, "acme", "hello"))


def test_deprecated_must_be_boolean(repo: Path) -> None:
    write_plugin(repo, "acme", "hello", deprecated="yes")
    assert any("deprecated" in e for e in _validate(repo, "acme", "hello"))
    write_plugin(repo, "acme", "hello2", deprecated=True)
    assert _validate(repo, "acme", "hello2") == []


def test_discover_plugin_dirs_sorted(repo: Path) -> None:
    write_plugin(repo, "zeta", "b")
    write_plugin(repo, "acme", "a")
    assert [d.plugin_id for d in discover_plugin_dirs(repo)] == ["acme/a", "zeta/b"]


def test_changed_files_outside_structure_are_errors() -> None:
    ids, errors = plugin_ids_for_changed_files(
        ["plugins/acme/hello/nodes/run.py", "plugins/stray.py", "tools/x.py", "README.md"]
    )
    assert ids == {"acme/hello"}
    assert errors == ["plugins/stray.py: files must live under plugins/<namespace>/<name>/"]


def test_config_schema_select_without_options_is_rejected(repo: Path) -> None:
    write_plugin(
        repo,
        "acme",
        "hello",
        config_schema=[{"name": "mode", "type": "select"}],
    )
    errors = _validate(repo, "acme", "hello")
    assert any("select" in e for e in errors)


def test_version_bump_rules() -> None:
    assert check_version_bump(None, "1.0.0") is None
    assert check_version_bump("1.0.0", "1.0.1") is None
    assert "must be bumped" in (check_version_bump("1.0.0", "1.0.0") or "")
    assert "must be bumped" in (check_version_bump("1.2.0", "1.1.9") or "")
