"""Private Blob workspace manifests with conditional, per-file merge writes.

The Python SDK does not yet expose ifMatch. The wire headers below follow
vercel/storage put-helpers.ts; keep the CAS integration test when upgrading.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

import httpx


class WriteConflict(Exception):
    pass


class PrivateBlobStore:
    def __init__(self, token: str | None = None, transport=None):
        self.token = token or os.environ["BLOB_READ_WRITE_TOKEN"]
        match = re.match(r"vercel_blob_rw_([^_]+)_", self.token)
        if not match:
            raise ValueError("invalid private Blob token")
        self.read_base = f"https://{match[1].lower()}.private.blob.vercel-storage.com/"
        self.client = httpx.Client(timeout=30, transport=transport)

    def close(self):
        self.client.close()

    def get(self, key: str):
        response = self.client.get(self.read_base + key, params={"cache":"0"} if key.endswith("manifest.json") else None, headers={
            "Authorization": f"Bearer {self.token}", "Cache-Control": "no-cache",
            **({"Accept-Encoding": "identity"} if key.endswith("manifest.json") else {}),
        })
        if response.status_code == 404:
            return None, None
        response.raise_for_status()
        return response.content, response.headers["etag"]

    def put(self, key: str, content: bytes, etag: str | None = None, overwrite=False):
        headers = {"Authorization": f"Bearer {self.token}", "x-api-version": "11",
                   "x-vercel-blob-access": "private", "x-add-random-suffix": "0",
                   "x-allow-overwrite": "1" if etag or overwrite else "0",
                   "x-content-type": "application/octet-stream", "x-cache-control-max-age": "0"}
        if etag:
            headers["x-if-match"] = etag
        response = self.client.put("https://vercel.com/api/blob/", params={"pathname": key}, content=content, headers=headers)
        if response.status_code in (409, 412) or (response.status_code == 400 and any(term in response.text.lower() for term in ("precondition", "already exists"))):
            raise WriteConflict(key)
        response.raise_for_status()
        return response.json().get("etag")


class BlobWorkspace:
    def __init__(self, store, owner: str, root: Path):
        if not re.fullmatch(r"[a-f0-9]{48}", owner):
            raise ValueError("invalid owner")
        self.store, self.owner, self.root = store, owner, root
        self.manifest_key = f"workspaces/{owner}/manifest.json"
        self.base = {}

    def _manifest(self):
        raw, etag = self.store.get(self.manifest_key)
        return json.loads(raw) if raw else {}, etag

    def checkout(self):
        self.base, _ = self._manifest()
        for name, digest in self.base.items():
            rel = PurePosixPath(name)
            if rel.is_absolute() or ".." in rel.parts or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("invalid manifest entry")
            cache = Path('/tmp/coursebook-object-cache') / self.owner / digest
            content = cache.read_bytes() if cache.exists() else None
            if content is None or hashlib.sha256(content).hexdigest() != digest:
                content, _ = self.store.get(f"workspaces/{self.owner}/objects/{digest}")
                if content is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    import tempfile
                    with tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as stream:
                        stream.write(content)
                        temporary = stream.name
                    os.replace(temporary, cache)
            if content is None or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("workspace object missing or corrupted")
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def flush(self):
        current, payloads = {}, {}
        for path in self.root.rglob("*"):
            if path.is_file() and not path.is_symlink() and not path.name.endswith((".tmp", "-journal", "-wal", "-shm")):
                body = path.read_bytes()
                digest = hashlib.sha256(body).hexdigest()
                name = path.relative_to(self.root).as_posix()
                current[name] = digest
                if self.base.get(name) != digest:
                    payloads[digest] = body
        changed = {name for name in self.base.keys() | current.keys() if self.base.get(name) != current.get(name)}
        if not changed:
            return
        for digest, body in payloads.items():
            try:
                self.store.put(f"workspaces/{self.owner}/objects/{digest}", body)
            except WriteConflict:
                pass  # Content-addressed objects are immutable and already present.
        for _ in range(5):
            latest, etag = self._manifest()
            for name in changed:
                if latest.get(name) not in (self.base.get(name), current.get(name)):
                    raise WriteConflict(name)
            merged = dict(latest)
            for name in changed:
                if name in current:
                    merged[name] = current[name]
                else:
                    merged.pop(name, None)
            try:
                self.store.put(self.manifest_key, json.dumps(merged, sort_keys=True).encode(), etag=etag)
                self.base = current
                return
            except WriteConflict:
                continue
        raise WriteConflict("workspace changed concurrently")
