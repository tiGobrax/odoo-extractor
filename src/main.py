from src.odoo_extractor.odoo_client import OdooClient
from loguru import logger
from dotenv import load_dotenv
import os
import polars as pl
from datetime import datetime

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

    # --- Gravação em Parquet ---
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parquet_path = f"{output_dir}/{model.replace('.', '_')}_{timestamp}.parquet"

    df.write_parquet(parquet_path)
    logger.info(f"💾 Dados salvos em {parquet_path}")

    # --- Exibição de amostra ---
    logger.info("📊 Prévia dos dados extraídos:")
    print(df.head())
