import json
import sys
import types
from pathlib import Path

import pytest

from tools.marketplace.build import CATALOG_KEY, ingest_entry_key
from tools.marketplace.manifest_rules import PluginDir
from tools.marketplace.publish import (
    PublishError,
    R2ObjectStore,
    fetch_oidc_token,
    publish_plugin,
    run_publish,
)
from tools.marketplace.tests.conftest import write_plugin

SHA = "0123456789abcdef0123456789abcdef01234567"
WHEN = "2026-09-24T10:00:00Z"


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.meta: dict[str, str] = {}
        self.puts: list[str] = []

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def head_sha256(self, key: str) -> str | None:
        return self.meta.get(key) if key in self.objects else None

    def put(self, key: str, data: bytes, content_type: str, sha256: str | None = None) -> None:
        self.objects[key] = data
        if sha256:
            self.meta[key] = sha256
        self.puts.append(key)


class _FakeClientError(Exception):
    """Stand-in for botocore.exceptions.ClientError: same `.response` shape."""

    def __init__(self, error_response: dict, operation_name: str) -> None:
        self.response = error_response
        super().__init__(f"{operation_name}: {error_response}")


@pytest.fixture
def fake_botocore(monkeypatch: pytest.MonkeyPatch):
    """Install a stub `botocore.exceptions` module.

    `R2ObjectStore` imports `botocore.exceptions.ClientError` lazily, inside each
    method, so boto3/botocore need not be installed for these tests: we plant a
    fake module in `sys.modules` whose `ClientError` matches the real one's
    interface (`.response["Error"]["Code"]`), which is all `R2ObjectStore` relies on.
    """
    botocore_mod = types.ModuleType("botocore")
    exceptions_mod = types.ModuleType("botocore.exceptions")
    exceptions_mod.ClientError = _FakeClientError
    botocore_mod.exceptions = exceptions_mod
    monkeypatch.setitem(sys.modules, "botocore", botocore_mod)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", exceptions_mod)
    return _FakeClientError


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3Client:
    """Stand-in for a boto3 S3 client, scripted per test with `_FakeClientError`."""

    def __init__(self, client_error: type[Exception]) -> None:
        self._client_error = client_error
        self.objects: dict[str, dict] = {}  # key -> {"Body": bytes, "Metadata": dict}
        self.put_calls: list[dict] = []
        self.next_error_code: str | None = None

    def _raise_not_found(self, code: str, op: str) -> None:
        raise self._client_error({"Error": {"Code": code}}, op)

    def get_object(self, Bucket: str, Key: str):
        if self.next_error_code is not None:
            code, self.next_error_code = self.next_error_code, None
            self._raise_not_found(code, "GetObject")
        if Key not in self.objects:
            self._raise_not_found("NoSuchKey", "GetObject")
        return {"Body": _FakeBody(self.objects[Key]["Body"])}

    def head_object(self, Bucket: str, Key: str):
        if self.next_error_code is not None:
            code, self.next_error_code = self.next_error_code, None
            self._raise_not_found(code, "HeadObject")
        if Key not in self.objects:
            self._raise_not_found("NoSuchKey", "HeadObject")
        return {"Metadata": self.objects[Key]["Metadata"]}

    def put_object(self, **kwargs) -> None:
        self.put_calls.append(kwargs)
        self.objects[kwargs["Key"]] = {
            "Body": kwargs["Body"],
            "Metadata": kwargs.get("Metadata", {}),
        }


def _r2_store(client: FakeS3Client) -> R2ObjectStore:
    return R2ObjectStore("acct", "key-id", "secret", "bucket", client=client)


def _pd(repo: Path) -> PluginDir:
    write_plugin(repo, "acme", "hello")
    return PluginDir("acme", "hello", repo / "plugins" / "acme" / "hello")


def test_publish_plugin_uploads_new_version(repo: Path, tmp_path: Path) -> None:
    store = FakeStore()
    signed: list[str] = []

    def sign(path: Path, comment: str) -> str:
        signed.append(comment)
        return "SIG"

    entry = publish_plugin(store, _pd(repo), tmp_path, SHA, WHEN, sign=sign)
    assert store.puts == ["acme/hello/1.0.0.lpk", "acme/hello/1.0.0.ingest.json"]
    assert store.meta["acme/hello/1.0.0.lpk"] == entry["sha256"]
    assert entry["signature"] == "SIG" and signed == ["acme/hello@1.0.0"]
    assert json.loads(store.objects[ingest_entry_key("acme", "hello", "1.0.0")]) == entry


def test_publish_plugin_reuses_existing_entry_when_sha_matches(repo: Path, tmp_path: Path) -> None:
    store = FakeStore()
    pd = _pd(repo)
    first = publish_plugin(store, pd, tmp_path / "1", SHA, WHEN, sign=lambda p, c: "SIG1")
    store.puts.clear()
    second = publish_plugin(
        store, pd, tmp_path / "2", "f" * 40, WHEN, sign=lambda p, c: pytest.fail("must not re-sign")
    )
    assert second == first
    assert store.puts == []


def test_publish_plugin_rejects_changed_content(repo: Path, tmp_path: Path) -> None:
    store = FakeStore()
    pd = _pd(repo)
    publish_plugin(store, pd, tmp_path / "1", SHA, WHEN)
    (pd.path / "nodes" / "run.py").write_text("x = 999\n", encoding="utf-8")
    with pytest.raises(PublishError, match="not bumped"):
        publish_plugin(store, pd, tmp_path / "2", SHA, WHEN)


def test_publish_plugin_rejects_orphan_artifact_with_different_sha(
    repo: Path, tmp_path: Path
) -> None:
    store = FakeStore()
    store.put("acme/hello/1.0.0.lpk", b"old", "application/zip", sha256="deadbeef")
    with pytest.raises(PublishError, match="manual cleanup"):
        publish_plugin(store, _pd(repo), tmp_path, SHA, WHEN)


def test_run_publish_posts_ingest_with_catalog(repo: Path) -> None:
    write_plugin(repo, "acme", "hello")
    write_plugin(repo, "loco", "gmail", version="0.1.3")
    store = FakeStore()
    seen: dict = {}

    def poster(url: str, token: str, payload: dict) -> dict:
        seen.update(url=url, token=token, payload=payload)
        return {"status": "success"}

    result = run_publish(
        repo,
        store,
        SHA,
        WHEN,
        "https://cloud.test/api/v1/marketplace/ingest",
        token_provider=lambda: "OIDC",
        poster=poster,
    )
    assert result == {"status": "success"}
    assert seen["token"] == "OIDC"
    assert seen["payload"]["catalog_plugin_ids"] == ["acme/hello", "loco/gmail"]
    assert [p["plugin_id"] for p in seen["payload"]["plugins"]] == ["acme/hello", "loco/gmail"]
    assert json.loads(store.objects[CATALOG_KEY])["commit_sha"] == SHA


def test_fetch_oidc_token_requests_audience() -> None:
    captured = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self) -> bytes:
            return b'{"value": "jwt-token"}'

    def opener(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return Resp()

    env = {
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://gh.test/token?x=1",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "rt",
    }
    assert fetch_oidc_token("loco-cloud-marketplace", env=env, opener=opener) == "jwt-token"
    assert captured["url"] == "https://gh.test/token?x=1&audience=loco-cloud-marketplace"
    assert captured["auth"] == "bearer rt"


@pytest.mark.parametrize("code", ["NoSuchKey", "404", "NotFound"])
def test_r2_get_returns_none_for_absent_object(fake_botocore, code: str) -> None:
    client = FakeS3Client(fake_botocore)
    client.next_error_code = code
    assert _r2_store(client).get("missing/key.lpk") is None


@pytest.mark.parametrize("code", ["NoSuchKey", "404", "NotFound"])
def test_r2_head_sha256_returns_none_for_absent_object(fake_botocore, code: str) -> None:
    client = FakeS3Client(fake_botocore)
    client.next_error_code = code
    assert _r2_store(client).head_sha256("missing/key.lpk") is None


def test_r2_get_propagates_unexpected_client_error(fake_botocore) -> None:
    client = FakeS3Client(fake_botocore)
    client.next_error_code = "AccessDenied"
    with pytest.raises(fake_botocore):
        _r2_store(client).get("some/key.lpk")


def test_r2_head_sha256_propagates_unexpected_client_error(fake_botocore) -> None:
    client = FakeS3Client(fake_botocore)
    client.next_error_code = "AccessDenied"
    with pytest.raises(fake_botocore):
        _r2_store(client).head_sha256("some/key.lpk")


def test_r2_put_then_get_and_head_sha256_roundtrip(fake_botocore) -> None:
    client = FakeS3Client(fake_botocore)
    store = _r2_store(client)
    store.put("acme/hello/1.0.0.lpk", b"payload", "application/zip", sha256="abc123")
    assert store.get("acme/hello/1.0.0.lpk") == b"payload"
    assert store.head_sha256("acme/hello/1.0.0.lpk") == "abc123"
    assert client.put_calls[0]["Metadata"] == {"sha256": "abc123"}


def test_r2_head_sha256_returns_empty_string_when_metadata_has_no_sha(fake_botocore) -> None:
    """The exact divergence the reviewer flagged: FakeStore.head_sha256 returns None
    for a key that exists without a recorded sha, but the real R2ObjectStore returns
    "" (via dict.get default) since it never returns None for an object that exists."""
    client = FakeS3Client(fake_botocore)
    client.objects["acme/hello/1.0.0.lpk"] = {"Body": b"unrelated bytes", "Metadata": {}}
    assert _r2_store(client).head_sha256("acme/hello/1.0.0.lpk") == ""


def test_r2_orphan_object_without_sha_metadata_still_blocks_publish(
    fake_botocore, repo: Path, tmp_path: Path
) -> None:
    """Confirms publish_plugin's orphan-artifact check behaves correctly against the
    real "" value (not just FakeStore's None): an object that exists with no sha256
    metadata must still be treated as a mismatch and rejected, never silently reused
    or overwritten."""
    client = FakeS3Client(fake_botocore)
    client.objects["acme/hello/1.0.0.lpk"] = {"Body": b"unrelated bytes", "Metadata": {}}
    store = _r2_store(client)
    with pytest.raises(PublishError, match="manual cleanup"):
        publish_plugin(store, _pd(repo), tmp_path, SHA, WHEN)
    # and it must not have uploaded anything on top of the pre-existing orphan
    assert client.put_calls == []
