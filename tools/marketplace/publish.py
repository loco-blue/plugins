"""Publish plugins at HEAD: build -> sign -> upload R2 (immutable keys) -> catalog -> POST ingest.

Idempotent: a version whose ingest entry already exists in storage is reused as-is
(never rebuilt, never re-signed). A changed plugin without version bump fails loudly.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from tools.marketplace.build import (
    CATALOG_KEY,
    build_catalog,
    build_lpk,
    ingest_entry_key,
    source_digest,
)
from tools.marketplace.manifest_rules import PluginDir, discover_plugin_dirs, load_manifest

Signer = Callable[[Path, str], str]


class PublishError(RuntimeError):
    """Publishing must stop; human action required."""


class ObjectStore(Protocol):
    def get(self, key: str) -> bytes | None: ...

    def head_sha256(self, key: str) -> str | None: ...

    def put(self, key: str, data: bytes, content_type: str, sha256: str | None = None) -> None: ...


def no_signature(_artifact: Path, _trusted_comment: str) -> str:
    return ""


class R2ObjectStore:
    """Cloudflare R2 via its S3-compatible API."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        client: Any = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
            )
        self._s3 = client
        self._bucket = bucket

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    def head_sha256(self, key: str) -> str | None:
        from botocore.exceptions import ClientError

        try:
            resp = self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return resp.get("Metadata", {}).get("sha256", "")

    def put(self, key: str, data: bytes, content_type: str, sha256: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if sha256:
            kwargs["Metadata"] = {"sha256": sha256}
        self._s3.put_object(**kwargs)


def publish_plugin(
    store: ObjectStore,
    pd: PluginDir,
    out_dir: Path,
    commit_sha: str,
    commit_time: str,
    sign: Signer = no_signature,
) -> dict[str, Any]:
    """Ensure pd's current version is in storage; return its ingest entry."""
    version = str(load_manifest(pd.path)["version"])
    entry_key = ingest_entry_key(pd.namespace, pd.name, version)
    prior_raw = store.get(entry_key)
    if prior_raw is not None:
        prior = json.loads(prior_raw)
        if prior.get("source_sha256") != source_digest(pd.path):
            raise PublishError(
                f"{pd.plugin_id}@{version}: content changed but version was not bumped"
            )
        return prior

    result = build_lpk(pd, out_dir, commit_sha, commit_time)
    key = result.ingest_entry["artifact_key"]
    existing_sha = store.head_sha256(key)
    if existing_sha is not None and existing_sha != result.sha256:
        raise PublishError(
            f"{pd.plugin_id}@{version}: {key} exists with a different sha256 and no ingest "
            "entry; manual cleanup required (verify it was never ingested, then delete it)"
        )
    entry = dict(result.ingest_entry)
    entry["signature"] = sign(result.artifact_path, f"{pd.plugin_id}@{version}")
    if existing_sha is None:
        store.put(key, result.artifact_path.read_bytes(), "application/zip", sha256=result.sha256)
    store.put(entry_key, json.dumps(entry, sort_keys=True).encode("utf-8"), "application/json")
    return entry


def fetch_oidc_token(
    audience: str,
    env: Mapping[str, str] = os.environ,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """GitHub Actions OIDC token (job needs `permissions: id-token: write`)."""
    url = f"{env['ACTIONS_ID_TOKEN_REQUEST_URL']}&audience={urllib.parse.quote(audience)}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"bearer {env['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"}
    )
    with opener(req, timeout=30) as resp:
        return json.loads(resp.read())["value"]


def post_ingest(
    url: str,
    token: str,
    payload: dict[str, Any],
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with opener(req, timeout=120) as resp:
        body = resp.read()
    return json.loads(body) if body else {}


def run_publish(
    repo_root: Path,
    store: ObjectStore,
    commit_sha: str,
    commit_time: str,
    ingest_url: str,
    token_provider: Callable[[], str],
    sign: Signer = no_signature,
    poster: Callable[[str, str, dict[str, Any]], dict[str, Any]] = post_ingest,
) -> dict[str, Any]:
    out_dir = Path(tempfile.mkdtemp(prefix="lpk-"))
    dirs = discover_plugin_dirs(repo_root)
    entries = [publish_plugin(store, pd, out_dir, commit_sha, commit_time, sign) for pd in dirs]
    catalog = build_catalog(dirs, commit_sha)
    store.put(CATALOG_KEY, json.dumps(catalog, sort_keys=True).encode("utf-8"), "application/json")
    payload = {
        "commit_sha": commit_sha,
        "plugins": entries,
        "catalog_plugin_ids": [d.plugin_id for d in dirs],
    }
    return poster(ingest_url, token_provider(), payload)


def _commit_time(repo_root: Path, sha: str) -> str:
    out = subprocess.run(
        ["git", "show", "-s", "--format=%cI", sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def build_signer_from_env(env: Mapping[str, str] = os.environ) -> Signer:
    """Signer from MINISIGN_SECRET_KEY (file content) + MINISIGN_PUBLIC_KEY (base64 line)."""
    from tools.marketplace.signing import minisign_signer

    secret = env.get("MINISIGN_SECRET_KEY", "")
    public = env.get("MINISIGN_PUBLIC_KEY", "")
    if not secret or not public:
        raise PublishError("MINISIGN_SECRET_KEY and MINISIGN_PUBLIC_KEY are required to publish")
    key_path = Path(tempfile.mkdtemp(prefix="minisign-")) / "marketplace.key"
    key_path.write_text(secret, encoding="utf-8")
    key_path.chmod(0o600)
    return minisign_signer(key_path, public.strip().splitlines()[-1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, required=True)
    ap.add_argument("--commit-sha", required=True)
    ap.add_argument("--ingest-url", default=os.environ.get("CLOUD_INGEST_URL", ""))
    ap.add_argument("--audience", default=os.environ.get("OIDC_AUDIENCE", "loco-cloud-marketplace"))
    args = ap.parse_args(argv)
    if not args.ingest_url:
        print("ERROR CLOUD_INGEST_URL is required", file=sys.stderr)
        return 2
    store = R2ObjectStore(
        os.environ["R2_ACCOUNT_ID"],
        os.environ["R2_ACCESS_KEY_ID"],
        os.environ["R2_SECRET_ACCESS_KEY"],
        os.environ["R2_BUCKET"],
    )
    try:
        sign = build_signer_from_env()
        result = run_publish(
            args.repo_root,
            store,
            args.commit_sha,
            _commit_time(args.repo_root, args.commit_sha),
            args.ingest_url,
            token_provider=lambda: fetch_oidc_token(args.audience),
            sign=sign,
        )
    except PublishError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
