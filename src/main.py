import os

import polars as pl
from dotenv import load_dotenv
from loguru import logger

from src.odoo_extractor.odoo_client import ModelExtractionError, OdooClient
from src.storage import save_dataframe_to_gcs
from src.utils import sanitize_records

load_dotenv()

if __name__ == "__main__":
    logger.info("🚀 Iniciando extração do Odoo com Polars...")
    client = OdooClient()

    model = os.getenv("ODOO_MODEL", "res.partner")
    fields = client.get_all_fields(model)

    # --- Extração de registros ---
    try:
        records = client.search_read(model=model, domain=[], fields=fields, limit=10)
    except ModelExtractionError as err:
        logger.error(f"❌ Model {model} ignorado: {err.reason}")
        raise SystemExit(1)

    if not records:
        logger.warning(f"⚠️ Nenhum registro encontrado no modelo {model}.")
        exit(0)

    # --- Conversão para DataFrame Polars ---
    sanitized = sanitize_records(records)
    df = pl.DataFrame(sanitized, strict=False)
    logger.success(f"✅ {df.shape[0]} registros extraídos de {model}")

    # --- Gravação em Parquet no GCS ---
    gcs_uri = save_dataframe_to_gcs(df, model)
    logger.info(f"💾 Dados salvos em {gcs_uri}")

    # --- Exibição de amostra ---
    logger.info("📊 Prévia dos dados extraídos:")
    print(df.head())
