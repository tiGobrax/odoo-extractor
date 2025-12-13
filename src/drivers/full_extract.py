from loguru import logger
import polars as pl

from src.odoo_extractor.odoo_client import OdooClient, ModelExtractionError
from src.storage import save_dataframe_to_gcs
from src.utils import sanitize_records

# Lista inicial de models para full extract.
# Depois você pode externalizar para env, arquivo ou tabela de controle.
MODELS = [
    "res.partner",
    # "sale.order",
    # "account.move",
]


def extract_model(client: OdooClient, model: str) -> None:
    logger.info(f"🚚 Iniciando full extract do model: {model}")

    try:
        fields = client.get_all_fields(model)
        records = client.search_read(model=model, domain=[], fields=fields)
    except ModelExtractionError as err:
        logger.warning(f"⚠️ Model {model} ignorado ({err.category}): {err.reason}")
        return

    if not records:
        logger.info(f"ℹ️ Nenhum registro encontrado para {model}.")
        return

    df = pl.DataFrame(sanitize_records(records), strict=False)
    logger.success(f"✅ {df.shape[0]} registros extraídos de {model}")

    gcs_uri = save_dataframe_to_gcs(df, model)
    logger.info(f"💾 Dados do model {model} salvos em {gcs_uri}")


def main() -> None:
    logger.info("🚀 Iniciando FULL EXTRACT do Odoo (job batch)")
    client = OdooClient()

    for model in MODELS:
        extract_model(client, model)

    logger.success("🏁 Full extract finalizado com sucesso")


if __name__ == "__main__":
    main()
