from pathlib import Path

from tools.marketplace import validate
from tools.marketplace.tests.conftest import write_plugin


def test_cli_passes_for_valid_changed_plugin(repo: Path, tmp_path: Path, capsys) -> None:
    write_plugin(repo, "acme", "hello")
    changed = tmp_path / "changed.txt"
    changed.write_text("plugins/acme/hello/plugin.yaml\n", encoding="utf-8")
    rc = validate.main(
        ["--repo-root", str(repo), "--changed-files", str(changed), "--base-ref", "origin/main"],
        base_version_reader=lambda _root, _ref, _pd: None,
    )
    assert rc == 0


def test_cli_fails_when_changed_without_bump(repo: Path, tmp_path: Path, capsys) -> None:
    write_plugin(repo, "acme", "hello")
    changed = tmp_path / "changed.txt"
    changed.write_text("plugins/acme/hello/nodes/run.py\n", encoding="utf-8")
    rc = validate.main(
        ["--repo-root", str(repo), "--changed-files", str(changed), "--base-ref", "origin/main"],
        base_version_reader=lambda _root, _ref, _pd: "1.0.0",
    )
    assert rc == 1
    assert "must be bumped" in capsys.readouterr().out


def test_cli_deleted_plugin_is_not_validated(repo: Path, tmp_path: Path) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_text("plugins/acme/gone/plugin.yaml\n", encoding="utf-8")
    rc = validate.main(
        ["--repo-root", str(repo), "--changed-files", str(changed), "--base-ref", "origin/main"],
        base_version_reader=lambda _root, _ref, _pd: "1.0.0",
    )
    assert rc == 0


def test_cli_all_mode_and_list_dirs(repo: Path, capsys) -> None:
    write_plugin(repo, "acme", "hello")
    rc = validate.main(["--repo-root", str(repo), "--all", "--list-dirs"])
    assert rc == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "plugins/acme/hello"
