from typing import List, Optional

from fastapi import FastAPI, HTTPException
from loguru import logger

from app.engine.extractor import run_extraction
from app.engine.models_registry import ModelsRegistry
from src.odoo_extractor.odoo_client import OdooClient


app = FastAPI(
    title="Odoo Extractor API",
    description="API para extração de dados do Odoo",
    version="1.0.0",
)


# ----------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "healthy"}


# ----------------------------------------------------------------------
# Models registry endpoints
# ----------------------------------------------------------------------
@app.post("/models/update")
async def update_models_list():
    """
    Atualiza o registry de models consultando o Odoo.
    """
    logger.info("🔄 Atualizando registry de models via API")

    client = OdooClient()

    try:
        model_ids = client.models.execute_kw(
            client.db,
            client.uid,
            client.password,
            "ir.model",
            "search",
            [[]],
            {},
        )

        models_data = client.models.execute_kw(
            client.db,
            client.uid,
            client.password,
            "ir.model",
            "read",
            [model_ids],
            {"fields": ["model"]},
        )

        models = [m["model"] for m in models_data if m.get("model")]

        registry = ModelsRegistry()
        registry.save(models)

        logger.success(f"✅ Registry atualizado com {len(models)} models")

        return {
            "status": "success",
            "models_count": len(models),
        }

    except Exception as e:
        logger.error(f"❌ Erro ao atualizar registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/list")
async def list_models():
    """
    Retorna models atualmente registrados.
    """
    registry = ModelsRegistry()
    models = registry.load()

    return {
        "status": "success",
        "models_count": len(models),
        "models": models,
    }


def _select_models(prefix: Optional[str]) -> List[str]:
    registry = ModelsRegistry()
    all_models = registry.load()

    if not all_models:
        raise HTTPException(
            status_code=400,
            detail="Registry de models vazio. Execute /models/update primeiro.",
        )

    if prefix:
        models = [m for m in all_models if m.startswith(prefix)]
        logger.info(f"🔍 Prefix '{prefix}': {len(models)} models")
        return models

    logger.info(f"📋 Processando {len(all_models)} models")
    return all_models


def _run_etl(
    *,
    prefix: Optional[str],
    fields: Optional[List[str]],
    limit: Optional[int],
    incremental: bool,
) -> dict:
    models = _select_models(prefix)

    if not models:
        return {
            "status": "success",
            "message": "Nenhum model para processar",
            "results": [],
        }

    try:
        return run_extraction(
            models=models,
            fields=fields,
            limit=limit,
            batch_size=2000,
            incremental=incremental,
        )
    except Exception as e:
        logger.error(f"💥 Falha na execução do ETL via API: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------------------------------------------------
# ETL endpoints
# ----------------------------------------------------------------------
@app.post("/run/inc")
async def run_incremental(
    prefix: Optional[str] = None,
    fields: Optional[List[str]] = None,
    limit: Optional[int] = None,
):
    """
    Executa extração incremental (append) usando cursor persistido.
    """

    return _run_etl(
        prefix=prefix,
        fields=fields,
        limit=limit,
        incremental=True,
    )


@app.post("/run/full")
async def run_full(
    prefix: Optional[str] = None,
    fields: Optional[List[str]] = None,
    limit: Optional[int] = None,
):
    """
    Executa extração full refresh ignorando cursores incrementais.
    """

    return _run_etl(
        prefix=prefix,
        fields=fields,
        limit=limit,
        incremental=False,
    )


@app.post("/etl/run")
async def run_etl(
    prefix: Optional[str] = None,
    fields: Optional[List[str]] = None,
    limit: Optional[int] = None,
):
    """
    Endpoint legada — mantém comportamento incremental por compatibilidade.
    """
    return _run_etl(
        prefix=prefix,
        fields=fields,
        limit=limit,
        incremental=True,
    )
