import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import polars as pl
from google.cloud import storage
from loguru import logger

_storage_client: Optional[storage.Client] = None
_GCS_BUCKET = "gobrax-data-lake"
_GCS_BASE_PATH = "data-lake/odoo"


def _get_storage_client() -> storage.Client:
    """Retorna uma instância singleton do cliente do Google Cloud Storage."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def _build_object_name(model: str, timestamp_str: str, chunk_suffix: Optional[str] = None) -> str:
    """Monta o caminho do objeto dentro do bucket."""
    base_path = _GCS_BASE_PATH.strip("/")
    safe_model_name = model.replace(".", "_")
    file_name = timestamp_str
    if chunk_suffix:
        file_name = f"{timestamp_str}_{chunk_suffix}"
    return f"{base_path}/{safe_model_name}/{file_name}.parquet"


def _build_model_prefix(model: str) -> str:
    """Monta o prefixo da pasta da model no bucket."""
    base_path = _GCS_BASE_PATH.strip("/")
    safe_model_name = model.replace(".", "_")
    return f"{base_path}/{safe_model_name}/"


def cleanup_model_folder(model: str, keep_timestamp: Optional[str] = None) -> int:
    """
    Remove objetos antigos da pasta da model no GCS.

    Se keep_timestamp for informado, preserva arquivos da execução atual
    (ex.: 20260306_180846_chunk0001.parquet).
    Se keep_timestamp for None, remove todos os arquivos da model.

    Returns:
        int: quantidade de arquivos removidos.
    """
    client = _get_storage_client()
    bucket = client.bucket(_GCS_BUCKET)
    prefix = _build_model_prefix(model)

    deleted = 0
    for blob in client.list_blobs(bucket, prefix=prefix):
        file_name = blob.name.rsplit("/", 1)[-1]
        if keep_timestamp and (
            file_name.startswith(f"{keep_timestamp}_")
            or file_name == f"{keep_timestamp}.parquet"
        ):
            continue
        blob.delete()
        deleted += 1

    if keep_timestamp:
        logger.info(
            "🧹 Limpeza pós-full da model '{}' (preservando timestamp={}): {} arquivos removidos em gs://{}/{}",
            model,
            keep_timestamp,
            deleted,
            _GCS_BUCKET,
            prefix,
        )
    else:
        logger.info(
            "🧹 Limpeza total da model '{}': {} arquivos removidos em gs://{}/{}",
            model,
            deleted,
            _GCS_BUCKET,
            prefix,
        )
    return deleted


def save_dataframe_to_gcs(
    df: pl.DataFrame,
    model: str,
    *,
    object_timestamp: Optional[str] = None,
    chunk_index: Optional[int] = None,
) -> str:
    """
    Persiste um DataFrame no Google Cloud Storage.

    Args:
        df: DataFrame com os dados.
        model: Nome do model (usado para montar o caminho no bucket).

    Returns:
        str: URI gs:// do arquivo salvo.
    """
    bucket_name = _GCS_BUCKET
    now = datetime.now(timezone.utc)
    timestamp_str = object_timestamp or now.strftime("%Y%m%d_%H%M%S")
    ingestion_ts = now.isoformat()

    df_to_save = df.with_columns(pl.lit(ingestion_ts).alias("ingestion_ts"))

    chunk_suffix = None
    if chunk_index is not None:
        chunk_suffix = f"chunk{chunk_index:04d}"

    object_name = _build_object_name(model, timestamp_str, chunk_suffix)
    client = _get_storage_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        temp_path = tmp.name

    df_to_save.write_parquet(temp_path)

    try:
        blob.upload_from_filename(temp_path)
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass

    gcs_uri = f"gs://{bucket_name}/{object_name}"
    logger.info(f"💾 Upload concluído: {gcs_uri}")
    return gcs_uri
