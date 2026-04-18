"""
S3 client — upload PPTX and generate pre-signed download URLs.

Key format: exports/{presentation_id}/{sanitized_title}.pptx
URL expiry is tiered by plan: free=1h, pro=24h, enterprise=7d.

File security:
  - Server-side encryption: AES-256 (S3 managed keys)
  - Content-Disposition: attachment forces browser download
  - ContentType: exact MIME type for .pptx files
"""
from __future__ import annotations
import logging
import re
from core.config import get_settings
from core.logging import get_logger

settings = get_settings()
logger   = get_logger("s3_client")

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )
    return _s3_client


def upload_pptx(
    presentation_id: str,
    pptx_bytes:      bytes,
    deck_title:      str = "presentation",
) -> str:
    """
    Upload PPTX bytes to S3 and return the S3 object key.

    Parameters
    ----------
    presentation_id : UUID string from deck JSON
    pptx_bytes      : raw .pptx file bytes from renderer.render()
    deck_title      : used in the filename (sanitised for safety)

    Returns
    -------
    S3 object key (not a URL — call generate_signed_url() separately)
    """
    # Sanitise: keep alphanumeric, spaces, hyphens, underscores; truncate
    safe_title = re.sub(r"[^a-zA-Z0-9 _-]", "_", deck_title).strip()[:80] or "presentation"
    safe_title = safe_title.replace(" ", "_")

    key = f"exports/{presentation_id}/{safe_title}.pptx"

    _get_s3().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=pptx_bytes,
        ContentType=(
            "application/vnd.openxmlformats-officedocument"
            ".presentationml.presentation"
        ),
        ContentDisposition=f'attachment; filename="{safe_title}.pptx"',
        ServerSideEncryption="AES256",
    )

    logger.info("pptx_uploaded", key=key, size_bytes=len(pptx_bytes))
    return key


def generate_signed_url(key: str, plan_tier: str = "free") -> str:
    """
    Generate a pre-signed S3 GET URL with tier-appropriate expiry.

    plan_tier | expiry
    ----------|--------
    free      | 1 hour  (3600 s)
    pro       | 24 hours (86400 s)
    enterprise| 7 days  (604800 s)
    """
    expiry_map = {
        "free":       settings.url_expiry_free,
        "pro":        settings.url_expiry_pro,
        "enterprise": settings.url_expiry_enterprise,
    }
    expiry = expiry_map.get(plan_tier, settings.url_expiry_free)

    url = _get_s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expiry,
    )

    logger.info("signed_url_generated", key=key, expiry_s=expiry, tier=plan_tier)
    return url


async def check_s3() -> str:
    """Health check — verify S3 bucket is accessible."""
    try:
        _get_s3().head_bucket(Bucket=settings.s3_bucket)
        return "ok"
    except Exception as exc:
        return f"error: {str(exc)[:100]}"
