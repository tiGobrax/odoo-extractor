import os

import polars as pl
from dotenv import load_dotenv
from loguru import logger

from src.odoo_extractor.odoo_client import OdooClient
from src.storage import save_dataframe_to_gcs

load_dotenv()

if __name__ == "__main__":
    logger.info("🚀 Iniciando extração do Odoo com Polars...")
    client = OdooClient()

    model = os.getenv("ODOO_MODEL", "res.partner")
    fields = ["id", "name", "email", "phone"]

    # --- Extração de registros ---
    records = client.search_read(model=model, domain=[], fields=fields, limit=10)

    if not records:
        logger.warning(f"⚠️ Nenhum registro encontrado no modelo {model}.")
        exit(0)

    # --- Conversão para DataFrame Polars ---
    df = pl.DataFrame(records)
    logger.success(f"✅ {df.shape[0]} registros extraídos de {model}")

    # --- Gravação em Parquet no GCS ---
    gcs_uri = save_dataframe_to_gcs(df, model)
    logger.info(f"💾 Dados salvos em {gcs_uri}")

    # --- Exibição de amostra ---
    logger.info("📊 Prévia dos dados extraídos:")
    print(df.head())
