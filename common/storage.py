"""The data lake, behind one tiny interface.

STORAGE=local -> files under LAKE_DIR (laptop)
STORAGE=s3    -> objects in s3://BUCKET   (AWS)

Keys are identical in both modes, e.g. raw/prices.klines/dt=2026-11-20/hour=14/1763650800.json,
so moving to AWS changes nothing but the .env file.
"""
import os
import pathlib

BACKEND = os.environ.get("STORAGE", "local")
LOCAL_ROOT = pathlib.Path(os.environ.get("LAKE_DIR", "data/lake"))

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client("s3")
    return _s3


def put_bytes(key: str, body: bytes) -> str:
    """Write one object/file. Returns its location (for logs)."""
    if BACKEND == "s3":
        bucket = os.environ["BUCKET"]
        _client().put_object(Bucket=bucket, Key=key, Body=body)
        return f"s3://{bucket}/{key}"
    path = LOCAL_ROOT / key
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)  # atomic: readers never see half a file
    return str(path)


def exists(key: str) -> bool:
    if BACKEND == "s3":
        from botocore.exceptions import ClientError
        try:
            _client().head_object(Bucket=os.environ["BUCKET"], Key=key)
            return True
        except ClientError:
            return False
    return (LOCAL_ROOT / key).exists()


def location(prefix: str = "") -> str:
    """Where a prefix lives, for pandas/Spark readers (s3://... or a folder path)."""
    if BACKEND == "s3":
        return f"s3://{os.environ['BUCKET']}/{prefix}"
    return str(LOCAL_ROOT / prefix)
