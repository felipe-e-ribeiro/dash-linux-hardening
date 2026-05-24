import os
import tempfile
from pathlib import Path

from app.parser import parse_xccdf


def _parse_temp(file_bytes: bytes, source: str) -> dict:
    fd, tmp_path = tempfile.mkstemp(suffix='.xml', prefix='oscap_')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(file_bytes)
        return parse_xccdf(tmp_path, source=source)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def load_upload(file_bytes: bytes, filename: str = "upload.xml") -> dict:
    return _parse_temp(file_bytes, source=f"upload:{filename}")


def load_nfs(mount_path: str, filename: str) -> dict:
    full = Path(mount_path) / filename
    if not full.exists():
        raise FileNotFoundError(f"NFS file not found: {full}")
    return parse_xccdf(str(full), source=f"nfs:{full}")


def load_s3(bucket: str, key: str, region: str = "") -> dict:
    import boto3
    kwargs = {}
    if region:
        kwargs['region_name'] = region
    client = boto3.client('s3', **kwargs)
    obj = client.get_object(Bucket=bucket, Key=key)
    body = obj['Body'].read()
    return _parse_temp(body, source=f"s3://{bucket}/{key}")
