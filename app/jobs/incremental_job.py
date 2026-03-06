import os
from loguru import logger

from app.engine.extractor import run_extraction
from app.engine.models_registry import ModelsRegistry


def _select_models(prefix: str | None) -> list[str]:
    registry = ModelsRegistry()
    all_models = registry.load()

    if not all_models:
        logger.error("Nenhum model encontrado no registry. Job abortado.")
        raise SystemExit(1)

    if prefix:
        models = [model for model in all_models if model.startswith(prefix)]
        logger.info(f"Prefix '{prefix}': {len(models)} models")
        if not models:
            logger.error(f"Nenhum model encontrado para o prefix '{prefix}'.")
            raise SystemExit(1)
        return models

    logger.info(f"{len(all_models)} models carregados para incremental extract")
    return all_models


def main() -> None:
    """
    Entrypoint do Cloud Run Job para INCREMENTAL EXTRACT.
    """

    logger.info("Iniciando INCREMENTAL EXTRACT (Cloud Run Job)")

    batch_size = int(os.getenv("ODOO_BATCH_SIZE", "5000"))
    prefix = os.getenv("ODOO_MODELS_PREFIX")
    limit_env = os.getenv("ODOO_LIMIT")
    limit = int(limit_env) if limit_env else None
    fields = None

    models = _select_models(prefix)

    result = run_extraction(
        models=models,
        fields=fields,
        limit=limit,
        batch_size=batch_size,
        incremental=True,
    )

    logger.success(
        "Incremental extract finalizado - "
        f"{result['successful']} sucesso, "
        f"{result['empty']} vazios, "
        f"{result['skipped']} ignorados, "
        f"{result['failed']} erros"
    )


if __name__ == "__main__":
    main()
