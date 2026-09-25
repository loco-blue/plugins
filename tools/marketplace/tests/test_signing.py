import shutil
import subprocess
from pathlib import Path

import pytest

from tools.marketplace.publish import PublishError, build_signer_from_env
from tools.marketplace.signing import minisign_signer


def test_signer_invokes_minisign_then_verifies(tmp_path: Path) -> None:
    artifact = tmp_path / "1.0.0.lpk"
    artifact.write_bytes(b"PK")
    calls: list[list[str]] = []

    def runner(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "-S":
            Path(cmd[cmd.index("-x") + 1]).write_text("SIG-TEXT")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    sign = minisign_signer(tmp_path / "k.key", "PUBKEY", runner=runner)
    assert sign(artifact, "acme/hello@1.0.0") == "SIG-TEXT"
    assert calls[0][:3] == ["minisign", "-S", "-s"]
    assert calls[0][calls[0].index("-t") + 1] == "acme/hello@1.0.0"
    assert calls[1][:4] == ["minisign", "-V", "-P", "PUBKEY"]


def test_signer_raises_when_minisign_fails(tmp_path: Path) -> None:
    artifact = tmp_path / "1.0.0.lpk"
    artifact.write_bytes(b"PK")

    def runner(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, b"", b"bad key")

    with pytest.raises(PublishError, match="minisign"):
        minisign_signer(tmp_path / "k.key", "PUB", runner=runner)(artifact, "x@1")


def test_build_signer_from_env_requires_keys() -> None:
    with pytest.raises(PublishError, match="MINISIGN_SECRET_KEY"):
        build_signer_from_env({})


@pytest.mark.skipif(shutil.which("minisign") is None, reason="minisign CLI not installed")
def test_real_minisign_roundtrip(tmp_path: Path) -> None:
    subprocess.run(
        ["minisign", "-G", "-W", "-p", str(tmp_path / "t.pub"), "-s", str(tmp_path / "t.key")],
        check=True,
        capture_output=True,
    )
    pub = (tmp_path / "t.pub").read_text().splitlines()[1]
    artifact = tmp_path / "1.0.0.lpk"
    artifact.write_bytes(b"PK\x03\x04data")
    sig = minisign_signer(tmp_path / "t.key", pub)(artifact, "acme/hello@1.0.0")
    assert "trusted comment: acme/hello@1.0.0" in sig
