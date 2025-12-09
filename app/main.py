import csv
import os
from pathlib import Path
from typing import List, Optional

import polars as pl
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from src.odoo_extractor.odoo_client import OdooClient
from src.storage import save_dataframe_to_gcs
from src.utils import sanitize_records

load_dotenv()

app = FastAPI(
    title="Odoo Extractor API",
    description="API para extração de dados do Odoo",
    version="1.0.0"
)

security = HTTPBearer()

# Token de autenticação (configure via variável de ambiente)
API_TOKEN = os.getenv("API_TOKEN", "meu_token")

# Arquivo para armazenar lista de models
MODELS_FILE = Path("data/models_list.csv")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifica o token de autenticação"""
    if credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido")
    return credentials

def load_models_list() -> List[str]:
    """Carrega a lista de models do arquivo CSV"""
    if MODELS_FILE.exists():
        try:
            models = []
            with open(MODELS_FILE, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and row[0].strip():  # Ignora linhas vazias
                        models.append(row[0].strip())
            return models
        except Exception as e:
            logger.error(f"Erro ao carregar lista de models: {e}")
            return []
    return []

def save_models_list(models: List[str]):
    """Salva a lista de models no arquivo CSV"""
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MODELS_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for model in sorted(models):  # Salva ordenado
            writer.writerow([model])

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "Odoo Extractor API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/models/update")
async def update_models_list(
    token: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """
    Atualiza a lista de models disponíveis no Odoo
    
    Busca todos os models disponíveis no Odoo e salva em um arquivo local.
    """
    try:
        logger.info("🔄 Atualizando lista de models do Odoo...")
        
        client = OdooClient()
        
        # Busca todos os models disponíveis
        # Usa ir.model para listar todos os models
        try:
            model_ids = client.models.execute_kw(
                client.db,
                client.uid,
                client.password,
                'ir.model',
                'search',
                [[]],
                {}
            )
            
            models_data = client.models.execute_kw(
                client.db,
                client.uid,
                client.password,
                'ir.model',
                'read',
                [model_ids],
                {'fields': ['model']}
            )
            
            models_list = [model['model'] for model in models_data if model.get('model')]
            models_list = sorted(list(set(models_list)))  # Remove duplicatas e ordena
            
            # Salva a lista
            save_models_list(models_list)
            
            logger.success(f"✅ Lista de models atualizada: {len(models_list)} models encontrados")
            
            return {
                "status": "success",
                "message": f"Lista de models atualizada com sucesso",
                "models_count": len(models_list),
                "models": models_list[:50]  # Retorna primeiros 50 para preview
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao buscar models: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao buscar models: {str(e)}")
            
    except Exception as e:
        logger.error(f"💥 Erro ao atualizar lista de models: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar lista: {str(e)}")

@app.get("/models/list")
async def get_models_list(
    token: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """Retorna a lista de models salva"""
    models = load_models_list()
    return {
        "status": "success",
        "models_count": len(models),
        "models": models
    }

@app.post("/etl/run")
async def run_etl(
    prefix: Optional[str] = None,
    fields: Optional[List[str]] = None,
    limit: Optional[int] = None,
    token: HTTPAuthorizationCredentials = Depends(verify_token)
):
    """
    Executa a extração de dados do Odoo
    
    Args:
        prefix: Prefixo para filtrar models (ex: "res." para todos os models que começam com "res.")
                Se None, processa todas as models da lista salva
        fields: Lista de campos a extrair. Se não fornecido, usa campos padrão
        limit: Limite de registros por model
        token: Token de autenticação via Bearer
    """
    try:
        logger.info("🚀 Iniciando extração do Odoo via API...")
        
        # Carrega lista de models
        all_models = load_models_list()
        
        if not all_models:
            raise HTTPException(
                status_code=400, 
                detail="Lista de models vazia. Execute /models/update primeiro."
            )
        
        # Filtra models por prefix se fornecido
        if prefix:
            models_to_process = [m for m in all_models if m.startswith(prefix)]
            logger.info(f"🔍 Filtrando models com prefix '{prefix}': {len(models_to_process)} models encontrados")
        else:
            models_to_process = all_models
            logger.info(f"📋 Processando todas as models: {len(models_to_process)} models")
        
        if not models_to_process:
            return {
                "status": "success",
                "message": f"Nenhum model encontrado com prefix '{prefix}'",
                "processed_models": 0,
                "results": []
            }
        
        # Inicializa cliente Odoo
        client = OdooClient()
        
        results = []
        # Processa cada model
        for model in models_to_process:
            try:
                logger.info(f"📊 Processando model: {model}")
                
                # Extração de registros
                records = client.search_read(
                    model=model,
                    domain=[],
                    fields=fields or client.get_all_fields(model),
                    limit=limit
                )
                
                if not records:
                    logger.warning(f"⚠️ Nenhum registro encontrado no model {model}")
                    results.append({
                        "model": model,
                        "status": "empty",
                        "records_count": 0,
                        "file_path": None
                    })
                    continue
                
                # Conversão para DataFrame Polars
                sanitized = sanitize_records(records)
                df = pl.DataFrame(sanitized, strict=False)
                
                # Gravação em Parquet (GCS)
                gcs_uri = save_dataframe_to_gcs(df, model)
                
                logger.success(f"✅ {model}: {len(records)} registros extraídos -> {gcs_uri}")
                
                results.append({
                    "model": model,
                    "status": "success",
                    "records_count": len(records),
                    "file_path": gcs_uri
                })
                
            except Exception as e:
                logger.error(f"❌ Erro ao processar model {model}: {e}")
                results.append({
                    "model": model,
                    "status": "error",
                    "error": str(e),
                    "records_count": 0,
                    "file_path": None
                })
                continue
        
        # Resumo
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'error')
        empty = sum(1 for r in results if r['status'] == 'empty')
        total_records = sum(r.get('records_count', 0) for r in results)
        
        logger.success(
            f"✅ Extração concluída: {successful} sucesso, {empty} vazios, {failed} erros. "
            f"Total de registros: {total_records}"
        )
        
        return {
            "status": "success",
            "message": "Extração concluída",
            "prefix": prefix,
            "total_models": len(models_to_process),
            "successful": successful,
            "empty": empty,
            "failed": failed,
            "total_records": total_records,
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Erro ao executar ETL: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao executar extração: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
