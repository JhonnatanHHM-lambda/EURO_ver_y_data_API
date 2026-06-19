from django.conf import settings
import io
import logging

logger = logging.getLogger(__name__)


def _get_bucket():
    return getattr(settings, 'MINIO_BUCKET_CONTRATOS', 'euro-contratos')


def get_minio_client():
    from minio import Minio
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_USE_HTTPS,
        cert_check=settings.MINIO_CERT_CHECK,
    )


def get_public_minio_client():
    from minio import Minio
    return Minio(
        endpoint=settings.MINIO_PUBLIC_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_PUBLIC_USE_HTTPS,
        cert_check=settings.MINIO_CERT_CHECK,
    )


def _ensure_bucket(client, bucket: str):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def upload_to_minio(file_obj, key: str, content_type: str = 'application/octet-stream') -> str:
    client = get_minio_client()
    bucket = _get_bucket()
    _ensure_bucket(client, bucket)
    data = file_obj.read() if hasattr(file_obj, 'read') else file_obj
    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def download_from_minio(key: str) -> bytes:
    client = get_minio_client()
    bucket = _get_bucket()
    response = client.get_object(bucket, key)
    return response.read()


def delete_from_minio(key: str):
    from minio.error import S3Error
    client = get_minio_client()
    bucket = _get_bucket()
    try:
        client.remove_object(bucket, key)
    except S3Error as e:
        logger.warning(f'Error eliminando {key} de MinIO: {e}')


def generate_presigned_url(key: str, expires_seconds: int = 3600) -> str:
    from datetime import timedelta
    # Generar con cliente interno (minio:9000 es alcanzable desde Docker)
    # y reemplazar el host por el endpoint público para que el navegador pueda abrirlo
    client = get_minio_client()
    bucket = _get_bucket()
    _ensure_bucket(client, bucket)
    url = client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires_seconds))
    scheme = 'https' if settings.MINIO_PUBLIC_USE_HTTPS else 'http'
    internal_prefix = f'http://{settings.MINIO_ENDPOINT}'
    public_prefix = f'{scheme}://{settings.MINIO_PUBLIC_ENDPOINT}'
    return url.replace(internal_prefix, public_prefix)
