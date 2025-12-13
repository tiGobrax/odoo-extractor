import os
from loguru import logger
import polars as pl

from src.odoo_extractor.odoo_client import OdooClient, ModelExtractionError
from src.storage import save_dataframe_to_gcs
from src.utils import sanitize_records


def main() -> None:
    """
    Delta extract simples, pensado para execuções rápidas.
    Parâmetros vêm via variáveis de ambiente.
    """
    model = os.getenv("ODOO_MODEL")
    if not model:
        raise ValueError("Variável de ambiente ODOO_MODEL é obrigatória para delta extract.")

    logger.info(f"⚡ Iniciando DELTA EXTRACT do model: {model}")

    client = OdooClient()

    try:
        fields = client.get_all_fields(model)
        # Domain vazio por enquanto; depois você pode usar filtros por updated_at, ids, etc.
        records = client.search_read(
            model=model,
            domain=[],
            fields=fields,
            limit=1000,  # limite defensivo para chamadas frequentes
        )
    except ModelExtractionError as err:
        logger.error(f"❌ Falha no delta extract de {model}: {err.reason}")
        raise SystemExit(1)

    if not records:
        logger.info(f"ℹ️ Nenhum registro novo para {model}.")
        return

    df = pl.DataFrame(sanitize_records(records), strict=False)
    logger.success(f"✅ {df.shape[0]} registros extraídos de {model}")

    gcs_uri = save_dataframe_to_gcs(df, model)
    logger.info(f"💾 Delta extract salvo em {gcs_uri}")


if __name__ == "__main__":
    main()
