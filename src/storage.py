import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import polars as pl
from google.cloud import storage
from loguru import logger

_storage_client: Optional[storage.Client] = None


def _get_storage_client() -> storage.Client:
    """Retorna uma instância singleton do cliente do Google Cloud Storage."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def _build_object_name(model: str, timestamp_str: str, chunk_suffix: Optional[str] = None) -> str:
    """Monta o caminho do objeto dentro do bucket."""
    base_path = os.getenv("GCS_BASE_PATH", "data-lake/odoo").strip("/")
    safe_model_name = model.replace(".", "_")
    file_name = timestamp_str
    if chunk_suffix:
        file_name = f"{timestamp_str}_{chunk_suffix}"
    return f"{base_path}/{safe_model_name}/{file_name}.parquet"


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
    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise ValueError("Variável de ambiente GCS_BUCKET não configurada.")

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
