"""
S3 client for raw document and extracted image storage.

Raw documents are stored for re-ingestion if the pipeline improves.
Extracted images (from vision enrichment) are stored for audit/debugging.
"""
import logging
from core.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
    return _s3


def upload_raw_document(file_bytes: bytes, doc_id: str, filename: str) -> str:
    """
    Upload raw document bytes to S3 for potential re-ingestion.
    Returns S3 URI: s3://{bucket}/{key}
    """
    key = f"raw/{doc_id}/{filename}"
    _get_s3().put_object(
        Bucket=settings.s3_raw_documents_bucket,
        Key=key,
        Body=file_bytes,
        ServerSideEncryption="AES256",
    )
    uri = f"s3://{settings.s3_raw_documents_bucket}/{key}"
    logger.debug(f"Raw document uploaded: {uri}")
    return uri
