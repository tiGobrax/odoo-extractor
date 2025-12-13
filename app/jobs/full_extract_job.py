import os
from loguru import logger

from app.engine.extractor import run_extraction
from app.engine.models_registry import ModelsRegistry


def main() -> None:
    """
    Entrypoint do Cloud Run Job para FULL EXTRACT.

    - Não sobe servidor
    - Não usa FastAPI
    - Não retorna HTTP
    - Executa e termina
    """

    logger.info("🚀 Iniciando FULL EXTRACT (Cloud Run Job)")

    # Configurações de execução batch
    batch_size = int(os.getenv("ODOO_BATCH_SIZE", "5000"))
    limit = None  # full load nunca usa limit
    fields = None  # extrai todos os campos

    # Carrega registry de models
    registry = ModelsRegistry()
    models = registry.load()

    if not models:
        logger.error("❌ Nenhum model encontrado no registry. Job abortado.")
        raise SystemExit(1)

    logger.info(f"📋 {len(models)} models carregados para full extract")

    # Executa engine
    result = run_extraction(
        models=models,
        fields=fields,
        limit=limit,
        batch_size=batch_size,
        incremental=False,
    )

    logger.success(
        "🏁 Full extract finalizado — "
        f"{result['successful']} sucesso, "
        f"{result['empty']} vazios, "
        f"{result['skipped']} ignorados, "
        f"{result['failed']} erros"
    )


if __name__ == "__main__":
    main()
