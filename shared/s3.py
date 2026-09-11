"""S3-обёртка (boto3, Signature v4) и контентно-адресуемые ключи."""
import hashlib
import os


def sha256_hex(data: bytes) -> str:
    """SHA-256 байтов MP3 -> hex (используется как mp3_hash и ключ S3)."""
    return hashlib.sha256(data).hexdigest()


def build_s3_key(mp3_hash: str) -> str:
    """Контентно-адресуемый ключ: calls/{hash[:2]}/{hash}.mp3."""
    if not mp3_hash:
        raise ValueError("mp3_hash обязателен")
    return f"calls/{mp3_hash[:2]}/{mp3_hash}.mp3"


def s3_client():
    """boto3 S3-клиент (Signature v4) + имя бакета из env."""
    import boto3
    from botocore.client import Config

    bucket = os.getenv("S3_BUCKET_NAME")
    access = os.getenv("S3_ACCESS_KEY")
    secret = os.getenv("S3_SECRET_KEY")
    if not bucket or not access or not secret:
        raise RuntimeError("S3_BUCKET_NAME/S3_ACCESS_KEY/S3_SECRET_KEY обязательны")
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "https://s3.twcstorage.ru"),
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4"),
    )
    return client, bucket


def presigned_url(s3_key: str, expires: int = 900):
    """Временная GET-ссылка (TTL по умолчанию 15 мин)."""
    if not s3_key:
        return None
    client, bucket = s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=expires,
    )
