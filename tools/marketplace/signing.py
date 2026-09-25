"""Sign artifacts with the minisign CLI and self-verify before anything is uploaded."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

Runner = Callable[..., Any]


def minisign_signer(
    secret_key_path: Path,
    public_key: str,
    binary: str = "minisign",
    runner: Runner = subprocess.run,
) -> Callable[[Path, str], str]:
    """Return a Signer. Key must be unencrypted (`minisign -G -W`) -- CI has no TTY."""
    from tools.marketplace.publish import PublishError

    def sign(artifact: Path, trusted_comment: str) -> str:
        sig_path = artifact.with_name(artifact.name + ".minisig")
        try:
            runner(
                [
                    binary,
                    "-S",
                    "-s",
                    str(secret_key_path),
                    "-m",
                    str(artifact),
                    "-x",
                    str(sig_path),
                    "-t",
                    trusted_comment,
                ],
                check=True,
                capture_output=True,
                input=b"",
            )
            # Self-verify before letting the caller treat this as a valid signature: a
            # misconfigured key or broken CLI must fail loudly here, not ship silently.
            runner(
                [binary, "-V", "-P", public_key, "-m", str(artifact), "-x", str(sig_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = (
                (e.stderr or b"").decode(errors="replace")
                if isinstance(e.stderr, bytes)
                else str(e.stderr)
            )
            raise PublishError(f"minisign failed for {artifact.name}: {stderr.strip()}") from e
        return sig_path.read_text(encoding="utf-8")

    return sign
