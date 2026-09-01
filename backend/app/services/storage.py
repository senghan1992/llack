"""Pluggable blob storage for uploaded files.

Two backends behind one interface:

* `LocalStorage` — files under LLACK_STORAGE_LOCAL_DIR. Downloads stream back
  through the API, so authorisation is enforced on every request.
* `S3Storage`    — any S3-compatible bucket (AWS, MinIO, Ceph). Uploads and
  downloads use presigned URLs so bytes never transit the API process.

Storage keys are content-addressed by upload date + file ULID:
`<workspace_id>/<YYYY>/<MM>/<file_id>/<sanitised name>`. Grouping by date keeps
any single prefix from growing without bound, which matters for both S3 request
sharding and local directory listings.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.core.logging import get_logger

log = get_logger(__name__)

_UNSAFE = re.compile(r"[^\w.\-가-힣]+", re.UNICODE)
CHUNK_SIZE = 1024 * 512  # 512 KiB


def sanitise_filename(name: str) -> str:
    """Make a filename safe for a filesystem and an S3 key.

    Rejects path traversal outright rather than stripping it — a filename
    containing `../` is never a legitimate upload.
    """
    normalised = unicodedata.normalize("NFC", name).strip().replace("\x00", "")
    normalised = normalised.replace("\\", "/").split("/")[-1]
    if normalised in ("", ".", ".."):
        return "file"
    cleaned = _UNSAFE.sub("_", normalised).strip("._")
    return (cleaned or "file")[:200]


def display_filename(name: str) -> str:
    """The name shown in the UI.

    Keeps spaces and non-ASCII (a Korean filename should survive intact) but
    drops any directory component, so a crafted upload cannot make the Files
    list read like a filesystem path.
    """
    normalised = unicodedata.normalize("NFC", name).strip().replace("\x00", "")
    basename = normalised.replace("\\", "/").split("/")[-1]
    if basename in ("", ".", ".."):
        return "file"
    return basename[:400]


def build_storage_key(workspace_id: str, file_id: str, filename: str) -> str:
    now = datetime.now(UTC)
    return f"{workspace_id}/{now:%Y/%m}/{file_id}/{sanitise_filename(filename)}"


class Storage(ABC):
    name: str

    @abstractmethod
    async def write_stream(self, key: str, stream: AsyncIterator[bytes]) -> tuple[int, str]:
        """Persist a stream. Returns (bytes written, sha256 hex)."""

    @abstractmethod
    async def read_stream(self, key: str) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    async def presigned_put_url(self, key: str, *, content_type: str, ttl: int = 900) -> str | None:
        """Return a direct-upload URL, or None if the backend has no such thing."""
        return None

    async def presigned_get_url(self, key: str, *, ttl: int = 900) -> str | None:
        return None


class LocalStorage(Storage):
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Defence in depth: a crafted key must not escape the root.
        if not candidate.is_relative_to(self.root):
            raise AppError("Invalid storage key.", code="invalid_storage_key")
        return candidate

    async def write_stream(self, key: str, stream: AsyncIterator[bytes]) -> tuple[int, str]:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".part")
        digest = hashlib.sha256()
        total = 0
        try:
            with temp.open("wb") as handle:
                async for chunk in stream:
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise AppError(
                            "Upload exceeds the maximum allowed size.",
                            code="payload_too_large",
                            status_code=413,
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            # Atomic publish: readers never see a partial file.
            temp.replace(path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return total, digest.hexdigest()

    async def read_stream(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        if not path.is_file():
            raise NotFound("File contents are missing.", code="file_missing")
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                yield chunk

    async def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink(missing_ok=True)
            # Clean up the now-empty per-file directory.
            parent = path.parent
            if parent != self.root and not any(parent.iterdir()):
                shutil.rmtree(parent, ignore_errors=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage(Storage):
    name = "s3"

    def __init__(self, bucket: str, *, region: str, endpoint_url: str | None = None) -> None:
        if not bucket:
            raise AppError("LLACK_S3_BUCKET is required when storage_backend=s3.")
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url or None

    def _session(self) -> Any:  # noqa: ANN401
        import aioboto3

        return aioboto3.Session()

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"region_name": self.region}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return kwargs

    async def write_stream(self, key: str, stream: AsyncIterator[bytes]) -> tuple[int, str]:
        digest = hashlib.sha256()
        total = 0
        parts: list[dict[str, Any]] = []

        async with self._session().client("s3", **self._client_kwargs()) as s3:
            created = await s3.create_multipart_upload(Bucket=self.bucket, Key=key)
            upload_id = created["UploadId"]
            try:
                buffer = bytearray()
                part_number = 1
                # S3 requires >= 5 MiB per part except the last one.
                min_part = 5 * 1024 * 1024

                async def flush(final: bool = False) -> None:
                    nonlocal buffer, part_number
                    if not buffer and not final:
                        return
                    if not buffer:
                        return
                    result = await s3.upload_part(
                        Bucket=self.bucket,
                        Key=key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=bytes(buffer),
                    )
                    parts.append({"ETag": result["ETag"], "PartNumber": part_number})
                    part_number += 1
                    buffer = bytearray()

                async for chunk in stream:
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise AppError(
                            "Upload exceeds the maximum allowed size.",
                            code="payload_too_large",
                            status_code=413,
                        )
                    digest.update(chunk)
                    buffer.extend(chunk)
                    if len(buffer) >= min_part:
                        await flush()
                await flush(final=True)

                if not parts:
                    # Zero-byte upload: multipart requires at least one part.
                    await s3.abort_multipart_upload(
                        Bucket=self.bucket, Key=key, UploadId=upload_id
                    )
                    await s3.put_object(Bucket=self.bucket, Key=key, Body=b"")
                    return 0, digest.hexdigest()

                await s3.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
            except BaseException:
                await s3.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
                raise
        return total, digest.hexdigest()

    async def read_stream(self, key: str) -> AsyncIterator[bytes]:
        async with self._session().client("s3", **self._client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
            except Exception as exc:  # noqa: BLE001
                raise NotFound("File contents are missing.", code="file_missing") from exc
            async for chunk in response["Body"].iter_chunks(CHUNK_SIZE):
                yield chunk

    async def delete(self, key: str) -> None:
        async with self._session().client("s3", **self._client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with self._session().client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
            except Exception:  # noqa: BLE001
                return False
            return True

    async def presigned_put_url(self, key: str, *, content_type: str, ttl: int = 900) -> str | None:
        async with self._session().client("s3", **self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=ttl,
            )

    async def presigned_get_url(self, key: str, *, ttl: int = 900) -> str | None:
        async with self._session().client("s3", **self._client_kwargs()) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=ttl,
            )


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "s3":
            _storage = S3Storage(
                settings.s3_bucket,
                region=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
            )
        else:
            _storage = LocalStorage(settings.storage_local_dir)
        log.info("storage.configured", backend=_storage.name)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None
