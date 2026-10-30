"""S3-compatible object storage access for MinIO, AWS S3, or R2."""

from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from ycc.config import Settings


class ObjectStorage(Protocol):
    """Operations required by the TLC extractor."""

    def upload_file(
        self,
        path: Path,
        key: str,
        *,
        sha256: str,
        source_etag: str | None,
    ) -> None:
        """Upload a checksummed source object."""
        ...

    def object_matches(self, key: str, sha256: str) -> bool:
        """Check whether an object has the expected checksum."""
        ...


class S3ObjectStore:
    """Upload and verify objects using environment-driven S3 settings."""

    def __init__(
        self,
        settings: Settings,
        client: BaseClient | None = None,
    ) -> None:
        """Create an S3 client or use an injected client in tests."""
        self.bucket = settings.s3_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 4}),
        )

    def ensure_bucket(self) -> None:
        """Create the configured bucket if it does not already exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code not in {"404", "NoSuchBucket", "NotFound"} and status != 404:
                raise
            region = self.client.meta.region_name or "us-east-1"
            try:
                if region != "us-east-1":
                    self.client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={"LocationConstraint": region},
                    )
                else:
                    self.client.create_bucket(Bucket=self.bucket)
            except ClientError as create_error:
                code = str(create_error.response.get("Error", {}).get("Code", ""))
                if code not in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                    raise

    def upload_file(
        self,
        path: Path,
        key: str,
        *,
        sha256: str,
        source_etag: str | None,
    ) -> None:
        """Upload a file with checksum metadata and ensure the bucket exists."""
        self.ensure_bucket()
        metadata = {"sha256": sha256}
        if source_etag:
            metadata["source-etag"] = source_etag
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": "application/vnd.apache.parquet",
                "Metadata": metadata,
            },
        )

    def object_matches(self, key: str, sha256: str) -> bool:
        """Check whether an existing S3 object has the expected checksum."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return False
            raise
        metadata = response.get("Metadata", {})
        return metadata.get("sha256") == sha256
