import io
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

from app.core.config import get_settings
from app.core.errors import AppError

log = logging.getLogger("routeproof.storage")

ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove an object. Deleting a missing key is not an error."""

    @abstractmethod
    def list(self, prefix: str) -> Iterator[tuple[str, datetime]]:
        """Yield (key, last_modified UTC) for objects under prefix."""


def delete_quietly(st: Storage, keys) -> list[str]:
    """Compensating cleanup after a failed DB transaction. Never raises; returns keys that could not be removed
    (those are left for the orphan sweep in app.services.uploads.cleanup)."""
    failed = []
    for k in dict.fromkeys(k for k in keys if k):
        try:
            st.delete(k)
            log.info("storage.compensating_delete", extra={"storage_key": k})
        except Exception:
            failed.append(k)
            log.exception("storage.compensating_delete_failed", extra={"storage_key": k})
    return failed


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key, data, content_type):
        p = self._p(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key):
        return self._p(key).read_bytes()

    def delete(self, key):
        self._p(key).unlink(missing_ok=True)

    def list(self, prefix):
        base = self._p(prefix) if prefix else self.root
        if not base.exists():
            return
        for f in base.rglob("*"):
            if f.is_file():
                yield f.relative_to(self.root).as_posix(), datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)


class S3Storage(Storage):
    """Private bucket; objects are only served through authenticated API endpoints (no public/presigned exposure)."""

    def __init__(self):
        import boto3

        s = get_settings()
        self.bucket = s.storage_bucket
        self.client = boto3.client(
            "s3", endpoint_url=s.storage_endpoint or None, region_name=s.storage_region,
            aws_access_key_id=s.storage_access_key, aws_secret_access_key=s.storage_secret_key,
        )

    def put(self, key, data, content_type):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def list(self, prefix):
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            for o in page.get("Contents", []):
                yield o["Key"], o["LastModified"]


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage() if s.storage_provider == "s3" else LocalStorage(s.storage_local_dir)
    return _storage


def set_storage(st: Storage | None) -> None:
    global _storage
    _storage = st


def validate_image(data: bytes) -> tuple[str, str]:
    """Validate by decoding (not by trusting the client Content-Type). Returns (content_type, extension)."""
    s = get_settings()
    if not data:
        raise AppError(400, "empty_file", "Empty file")
    if len(data) > s.upload_max_size_bytes:
        raise AppError(413, "file_too_large", f"Image exceeds {s.upload_max_size_bytes} bytes")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise AppError(415, "unsupported_image", "File is not a valid JPEG, PNG or WebP image")
    if fmt not in ALLOWED:
        raise AppError(415, "unsupported_image", "Only JPEG, PNG or WebP images are accepted")
    return ALLOWED[fmt]


def sharpness_score(data: bytes) -> float:
    """Edge-energy heuristic. Very low values suggest a blank/blurred photo; used only as a pre-check hint."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            g = im.convert("L")
            g.thumbnail((800, 800))
            edges = g.filter(ImageFilter.FIND_EDGES)
            edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))  # PIL leaves border pixels unfiltered
            return float(ImageStat.Stat(edges).var[0])
    except Exception:
        return 0.0
