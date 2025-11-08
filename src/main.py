from src.odoo_extractor.odoo_client import OdooClient
from loguru import logger
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()

if __name__ == "__main__":
    logger.info("🚀 Testando conexão com Odoo...")
    client = OdooClient()

    model = os.getenv("ODOO_MODEL", "res.partner")
    fields = ["id", "name", "email", "phone"]

    records = client.search_read(model=model, domain=[], fields=fields, limit=10)
    df = pd.DataFrame(records)

    logger.success(f"✅ {len(df)} registros extraídos de {model}")
    print(df.head())
