import shutil
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig

from ..config import get_settings


class Storage:
    def __init__(self):
        self.settings = get_settings()
        self.root = self.settings.storage_local_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.s3 = None
        self.s3_presign = None
        if self.settings.storage_backend == "s3":
            kwargs = {
                "region_name": self.settings.storage_s3_region,
                "endpoint_url": self.settings.storage_s3_endpoint_url,
                "config": BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
            }
            if self.settings.storage_s3_access_key and self.settings.storage_s3_secret_key:
                kwargs["aws_access_key_id"] = self.settings.storage_s3_access_key.get_secret_value()
                kwargs["aws_secret_access_key"] = self.settings.storage_s3_secret_key.get_secret_value()
            self.s3 = boto3.client("s3", **kwargs)
            presign_kwargs = dict(kwargs)
            presign_kwargs["endpoint_url"] = self.settings.storage_s3_public_endpoint_url or self.settings.storage_s3_endpoint_url
            self.s3_presign = boto3.client("s3", **presign_kwargs)

    def _local_path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def presign_put(self, key: str, content_type: str, expires: int = 900) -> str:
        if self.s3:
            return self.s3_presign.generate_presigned_url(
                "put_object", Params={"Bucket": self.settings.storage_s3_bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires,
            )
        return f"{self.settings.api_prefix}/uploads/local/{key.rsplit('/', 2)[-2]}"

    def put_fileobj(self, key: str, body: BinaryIO, content_type: str) -> None:
        if self.s3:
            self.s3.upload_fileobj(body, self.settings.storage_s3_bucket, key, ExtraArgs={"ContentType": content_type})
        else:
            destination = self._local_path(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            body.seek(0)
            with destination.open("wb") as output:
                shutil.copyfileobj(body, output, length=1024 * 1024)

    def upload_file(self, key: str, filename: Path, content_type: str) -> None:
        with filename.open("rb") as body:
            self.put_fileobj(key, body, content_type)

    def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.s3:
            self.s3.download_file(self.settings.storage_s3_bucket, key, str(destination))
        else:
            shutil.copyfile(self._local_path(key), destination)

    def head(self, key: str) -> tuple[int, str | None]:
        if self.s3:
            response = self.s3.head_object(Bucket=self.settings.storage_s3_bucket, Key=key)
            return int(response["ContentLength"]), response.get("ContentType")
        path = self._local_path(key)
        return path.stat().st_size, None

    def read_prefix(self, key: str, length: int = 32) -> bytes:
        if self.s3:
            response = self.s3.get_object(Bucket=self.settings.storage_s3_bucket, Key=key, Range=f"bytes=0-{length - 1}")
            return response["Body"].read(length)
        with self._local_path(key).open("rb") as body:
            return body.read(length)

    def presign_get(self, key: str, filename: str, expires: int = 900) -> str:
        if not self.s3:
            raise RuntimeError("Signed remote downloads are available only with S3 storage")
        return self.s3_presign.generate_presigned_url(
            "get_object", Params={"Bucket": self.settings.storage_s3_bucket, "Key": key,
                                  "ResponseContentDisposition": f'attachment; filename="{filename.replace(chr(34), "")}"'},
            ExpiresIn=expires,
        )

    def delete(self, key: str) -> None:
        if self.s3:
            self.s3.delete_object(Bucket=self.settings.storage_s3_bucket, Key=key)
        else:
            self._local_path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> None:
        """Remove every stored object for a scan, including objects left without DB rows."""
        if not prefix or not prefix.endswith("/"):
            raise ValueError("Storage prefixes must be non-empty and directory-scoped")
        if self.s3:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.settings.storage_s3_bucket, Prefix=prefix):
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                for start in range(0, len(objects), 1000):
                    response = self.s3.delete_objects(
                        Bucket=self.settings.storage_s3_bucket,
                        Delete={"Objects": objects[start:start + 1000], "Quiet": True},
                    )
                    errors = response.get("Errors", [])
                    if errors:
                        raise RuntimeError(f"Could not delete {len(errors)} object(s) under storage prefix")
            return

        path = self._local_path(prefix.rstrip("/"))
        if path.exists():
            shutil.rmtree(path)


storage = Storage()
