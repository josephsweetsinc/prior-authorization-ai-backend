"""S3 actions for file upload and management."""

import uuid
from datetime import UTC, datetime
from typing import Any, BinaryIO

from config.settings import Settings
from core.constants import MIME_TO_EXTENSION
from services.aws.base import AWSActions
from services.aws.mixins import FileActionMixin

settings = Settings.load()


def generate_storage_key(prefix: str, file_extension: str) -> str:
    """Generate a unique storage key with date-based path structure.

    Creates a storage key with the format:
    {prefix}/{year}/{month:02d}/{day:02d}/{uuid}{extension}

    This structure helps organize files by date and ensures uniqueness
    through UUID generation.

    Args:
        prefix: Storage prefix (e.g., 'drawings', 'images').
        file_extension: File extension with dot (e.g., '.pdf', '.jpg').

    Returns:
        Storage key string in the format described above.

    Example:
        >>> generate_storage_key('drawings', '.pdf')
        'drawings/2024/01/15/550e8400-e29b-41d4-a716-446655440000.pdf'

    """
    now = datetime.now(UTC)
    return (
        f'{prefix}/{now.year}/{now.month:02d}/{now.day:02d}/'
        f'{uuid.uuid4()}{file_extension}'
    )


class S3Actions(AWSActions, FileActionMixin):
    """S3 service actions for file upload, download, and management.

    Provides methods for uploading files to S3, generating presigned URLs,
    and managing file metadata. Inherits from AWSActions for AWS session
    management and FileActionMixin for file validation.

    Attributes:
        s3_resource: Boto3 S3 resource object.
        s3_client: Boto3 S3 client object.
        aws_bucket_name: Name of the S3 bucket.
        aws_region: AWS region for the bucket.
        bucket: Boto3 Bucket resource object.

    """

    S3_EXPIRATION_TIME = 1800  # 30 Minutes

    def __init__(self) -> None:
        """Initialize S3 client and resource connections.

        Sets up boto3 S3 client and resource, and initializes bucket reference.

        """
        super().__init__()
        self.s3_resource = super().get_client(service_name='s3', resource=True)
        self.s3_client = super().get_client(service_name='s3', resource=False)
        self.aws_bucket_name = settings.aws_settings.BUCKET_NAME
        self.aws_region = settings.aws_settings.REGION
        self.bucket = self.s3_resource.Bucket(self.aws_bucket_name)

    def upload_file(
        self,
        file_obj: BinaryIO,
        *,
        file_name: str,
        file_size: int,
        declared_content_type: str | None = None,
        prefix: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Upload a file to S3 with validation and automatic key generation.

        Validates file type and size, generates a unique storage key,
        and uploads the file to S3 with appropriate metadata.

        Args:
            file_obj: Binary file object to upload.
            file_name: Original filename of the file.
            file_size: Size of the file in bytes.
            declared_content_type: Optional MIME type declared by the client.
            prefix: Optional storage prefix.
            metadata: Optional dictionary of metadata to attach to the file.

        Returns:
            Tuple of (storage_key, content_type) for the uploaded file.

        Raises:
            UnknownFiletypeException: If file type cannot be determined.
            IncorrectFileSizeException: If file size exceeds maximum allowed.

        """
        file_type, category = self.determine_file_type(
            file_name, declared_content_type
        )
        self.validate_file_size(file_size, file_type)
        resolved_prefix = prefix or self.get_category_prefix(category)
        file_extension = self._get_file_extension(file_type)

        key = generate_storage_key(
            prefix=resolved_prefix,
            file_extension=file_extension,
        )
        file_obj.seek(0)
        self.upload_to_s3(key, file_obj, file_type, metadata=metadata)
        return key, file_type

    def upload_to_s3(
        self,
        key: str,
        file_obj: BinaryIO,
        content_type: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload file object to S3.

        Args:
            key: S3 storage key (path) for the file.
            file_obj: Binary file object to upload.
            content_type: MIME type of the file.
            metadata: Optional dictionary of metadata to attach to the file.

        """
        extra_args: dict[str, object] = {
            'ContentType': content_type,
            'CacheControl': 'max-age=31536000',
            'ContentDisposition': 'inline',
        }
        if metadata:
            extra_args['Metadata'] = metadata

        self.bucket.upload_fileobj(
            file_obj,
            key,
            ExtraArgs=extra_args,
        )

    def create_presigned_upload(
        self,
        *,
        file_name: str,
        file_size: int,
        declared_content_type: str | None = None,
        prefix: str | None = None,
        metadata: dict[str, str] | None = None,
        expires_in: int = 900,
    ) -> tuple[str, str, str, dict[str, str], int]:
        """Generate presigned upload data for direct S3 uploads.

        Args:
            file_name: Original filename of the file.
            file_size: Size of the file in bytes.
            declared_content_type: Optional MIME type declared by the client.
            prefix: Optional storage prefix.
            metadata: Optional metadata to attach to the uploaded object.
            expires_in: URL expiration time in seconds (default: 15 minutes).

        Returns:
            Tuple containing:
                - storage_key: Generated S3 key for the object.
                - content_type: Resolved MIME type.
                - upload_url: Presigned URL for PUT request.
                - upload_headers: Headers that must accompany the upload.
                - expires_in: Expiration time in seconds.

        """
        file_type, category = self.determine_file_type(
            file_name,
            declared_content_type,
        )
        self.validate_file_size(file_size, file_type)
        resolved_prefix = prefix or self.get_category_prefix(category)
        file_extension = self._get_file_extension(file_type)

        key = generate_storage_key(
            prefix=resolved_prefix,
            file_extension=file_extension,
        )

        put_params: dict[str, Any] = {
            'Bucket': self.aws_bucket_name,
            'Key': key,
            'ContentType': file_type,
            'CacheControl': 'max-age=31536000',
            'ContentDisposition': 'inline',
        }
        if metadata:
            put_params['Metadata'] = metadata

        upload_url = self.s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params=put_params,
            ExpiresIn=expires_in,
        )
        upload_headers: dict[str, str] = {
            'Content-Type': file_type,
            'Cache-Control': 'max-age=31536000',
            'Content-Disposition': 'inline',
        }
        if metadata:
            upload_headers.update(
                {f'x-amz-meta-{key}': value for key, value in metadata.items()}
            )

        return key, file_type, upload_url, upload_headers, expires_in

    def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        *,
        require_object: bool = True,
    ) -> Any:
        """Generate a presigned URL for downloading a file from S3.

        First verifies that the object exists in the bucket, then generates
        a time-limited presigned URL that allows direct access to the file.

        Args:
            key: S3 storage key (path) of the file.
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour).
            require_object: Whether to check for object existence before
                generating the URL. Set to False when the object may not exist.

        Returns:
            Presigned URL string for accessing the file.

        Raises:
            ClientError: If the object does not exist in the bucket.

        """
        if require_object:
            self.s3_client.head_object(Bucket=self.aws_bucket_name, Key=key)
        return self.s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': self.aws_bucket_name, 'Key': key},
            ExpiresIn=expires_in,
        )

    def download_from_s3(self, key: str) -> tuple[bytes, str]:
        """Download an object's raw bytes and content type from S3.

        Args:
            key: S3 storage key (path) of the file.

        Returns:
            Tuple of (content bytes, content type).

        Raises:
            ClientError: If the object does not exist in the bucket.

        """
        response = self.s3_client.get_object(
            Bucket=self.aws_bucket_name, Key=key
        )
        content = response['Body'].read()
        content_type = response.get('ContentType', 'application/octet-stream')
        return content, content_type

    def _get_file_extension(self, content_type: str) -> str:
        """Get file extension from MIME type.

        Args:
            content_type: MIME type of the file.

        Returns:
            File extension with dot (e.g., '.pdf', '.doc').
            Returns '.bin' if content type is not recognized.

        """
        return MIME_TO_EXTENSION.get(content_type, '.bin')
