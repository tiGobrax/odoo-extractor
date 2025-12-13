from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import polars as pl
from loguru import logger

from app.engine.cursor_store import CursorStore
from src.odoo_extractor.odoo_client import OdooClient, ModelExtractionError
from src.storage import save_dataframe_to_gcs
from src.utils import sanitize_records


class ExtractionResult:
    """
    Resultado estruturado da extração de um único model.
    Engine NÃO retorna HTTP nem levanta HTTPException.
    """

    def __init__(
        self,
        model: str,
        status: str,
        records_count: int = 0,
        file_paths: Optional[List[str]] = None,
        error: Optional[str] = None,
    ):
        self.model = model
        self.status = status
        self.records_count = records_count
        self.file_paths = file_paths or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "status": self.status,
            "records_count": self.records_count,
            "file_paths": self.file_paths,
            "file_path": self.file_paths[-1] if self.file_paths else None,
            "error": self.error,
        }


def _parse_cursor_value(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return None


def _compare_cursor(
    current: Optional[Tuple[datetime, str, Optional[int]]],
    candidate: Tuple[datetime, str, Optional[int]],
) -> Tuple[datetime, str, Optional[int]]:
    if current is None:
        return candidate

    current_dt, _, current_id = current
    candidate_dt, candidate_value, candidate_id = candidate

    if candidate_dt > current_dt:
        return candidate

    if candidate_dt == current_dt:
        current_id_val = current_id or 0
        candidate_id_val = candidate_id or 0
        if candidate_id_val > current_id_val:
            return candidate

    return current


def _extract_batch_cursor(
    batch: List[Dict[str, Any]],
    *,
    cursor_field: str,
) -> Optional[Tuple[datetime, str, Optional[int]]]:
    best: Optional[Tuple[datetime, str, Optional[int]]] = None
    for record in batch:
        value = record.get(cursor_field)
        record_id_raw = record.get("id")
        parsed = _parse_cursor_value(value)
        if not parsed:
            continue

        record_id: Optional[int] = None
        if isinstance(record_id_raw, int):
            record_id = record_id_raw
        else:
            try:
                record_id = int(record_id_raw)
            except (TypeError, ValueError):
                record_id = None

        best = _compare_cursor(best, (parsed, str(value), record_id))

    return best


def _build_incremental_domain(
    *,
    cursor_field: str,
    last_value: str,
    last_id: Optional[int],
) -> List[Any]:
    if not last_value:
        return []

    if last_id is None:
        return [(cursor_field, ">", last_value)]

    return [
        "|",
        (cursor_field, ">", last_value),
        "&",
        (cursor_field, "=", last_value),
        ("id", ">", last_id),
    ]


def run_extraction(
    *,
    models: List[str],
    fields: Optional[List[str]],
    limit: Optional[int],
    batch_size: int,
    incremental: bool = True,
) -> Dict[str, Any]:
    """
    Engine principal de extração.
    - Não sabe o que é HTTP
    - Não sabe o que é Cloud Run
    - Não sabe quem chamou
    """

    logger.info("🚀 Engine de extração iniciada")
    client = OdooClient()
    cursor_store = CursorStore() if incremental else None

    results: List[ExtractionResult] = []

    for model in models:
        try:
            logger.info(f"📊 Processando model: {model}")

            all_fields = client.get_all_fields(model)
            if fields:
                model_fields = list(fields)
            else:
                model_fields = list(all_fields)

            domain: List[Any] = []
            cursor_field: Optional[str] = None
            cursor_data = None

            if incremental and cursor_store:
                has_write_date = "write_date" in all_fields
                if has_write_date:
                    cursor_field = "write_date"
                    cursor_data = cursor_store.load(model)

                    if cursor_field not in model_fields:
                        model_fields.append(cursor_field)
                    if "id" not in model_fields:
                        model_fields.append("id")

                    if cursor_data and cursor_data.last_value:
                        domain = _build_incremental_domain(
                            cursor_field=cursor_field,
                            last_value=cursor_data.last_value,
                            last_id=cursor_data.last_id,
                        )
                        logger.info(
                            "🔁 Incremental %s a partir de %s (id>%s)",
                            model,
                            cursor_data.last_value,
                            cursor_data.last_id,
                        )
                    else:
                        logger.info(
                            "🔁 Incremental habilitado para %s, sem cursor salvo — full inicial",
                            model,
                        )
                else:
                    logger.info(
                        "ℹ️ %s sem write_date — executando full refresh.",
                        model,
                    )
                    if "id" not in model_fields:
                        model_fields.append("id")
            else:
                if "id" not in model_fields:
                    model_fields.append("id")
                logger.info("📥 Full refresh em %s", model)

            chunk_paths: List[str] = []
            model_records = 0
            chunk_index = 1
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            latest_cursor: Optional[Tuple[datetime, str, Optional[int]]] = None

            for batch in client.iter_batches(
                model=model,
                domain=domain,
                fields=model_fields,
                batch_size=batch_size,
                limit=limit,
            ):
                if not batch:
                    continue

                sanitized = sanitize_records(batch)
                if not sanitized:
                    continue

                df = pl.DataFrame(sanitized, strict=False)

                if cursor_field:
                    candidate = _extract_batch_cursor(
                        batch,
                        cursor_field=cursor_field,
                    )
                    if candidate:
                        latest_cursor = _compare_cursor(latest_cursor, candidate)

                gcs_uri = save_dataframe_to_gcs(
                    df,
                    model,
                    object_timestamp=timestamp_str,
                    chunk_index=chunk_index,
                )

                chunk_paths.append(gcs_uri)
                model_records += len(batch)
                chunk_index += 1

            if not chunk_paths:
                logger.warning(f"⚠️ Nenhum registro encontrado para {model}")
                results.append(
                    ExtractionResult(
                        model=model,
                        status="empty",
                    )
                )
                continue

            logger.success(
                f"✅ {model}: {model_records} registros em {len(chunk_paths)} arquivos"
            )

            if cursor_field and latest_cursor and cursor_store:
                _, cursor_value, cursor_id = latest_cursor
                cursor_store.save(
                    model,
                    cursor_field=cursor_field,
                    last_value=cursor_value,
                    last_id=cursor_id,
                )

            results.append(
                ExtractionResult(
                    model=model,
                    status="success",
                    records_count=model_records,
                    file_paths=chunk_paths,
                )
            )

        except ModelExtractionError as e:
            logger.warning(f"⚠️ Model {model} ignorado: {e.reason}")
            results.append(
                ExtractionResult(
                    model=model,
                    status="skipped",
                    error=e.reason,
                )
            )

        except Exception as e:
            logger.error(f"❌ Erro inesperado no model {model}: {e}")
            results.append(
                ExtractionResult(
                    model=model,
                    status="error",
                    error=str(e),
                )
            )

    # --- Resumo global ---
    summary = {
        "total_models": len(models),
        "successful": sum(r.status == "success" for r in results),
        "empty": sum(r.status == "empty" for r in results),
        "skipped": sum(r.status == "skipped" for r in results),
        "failed": sum(r.status == "error" for r in results),
        "total_records": sum(r.records_count for r in results),
        "results": [r.to_dict() for r in results],
    }

    logger.success(
        "🏁 Engine finalizada — "
        f"sucesso={summary['successful']}, "
        f"vazios={summary['empty']}, "
        f"ignorados={summary['skipped']}, "
        f"erros={summary['failed']}, "
        f"registros={summary['total_records']}"
    )

    return summary
