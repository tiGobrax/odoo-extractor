import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from google.api_core.exceptions import NotFound
from google.cloud import storage
from loguru import logger

_storage_client: Optional[storage.Client] = None
_GCS_BUCKET = "gobrax-data-lake"
_GCS_BASE_PATH = "data-lake/odoo"


def _get_storage_client() -> storage.Client:
    """Retorna instância singleton do client do GCS."""
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client


def _safe_model_name(model: str) -> str:
    return model.replace(".", "_")


@dataclass
class CursorData:
    cursor_field: str
    last_value: str
    last_id: Optional[int]
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "CursorData":
        return cls(
            cursor_field=data.get("cursor_field", "write_date"),
            last_value=data["last_value"],
            last_id=data.get("last_id"),
            updated_at=data.get("updated_at", ""),
        )

    def to_dict(self) -> dict:
        return {
            "cursor_field": self.cursor_field,
            "last_value": self.last_value,
            "last_id": self.last_id,
            "updated_at": self.updated_at,
        }


class CursorStore:
    """
    Persiste e recupera o cursor incremental por model (write_date/id).
    Armazena arquivos JSON no mesmo bucket do data lake.
    """

    def __init__(
        self,
        *,
        bucket_name: Optional[str] = None,
        base_path: Optional[str] = None,
    ):
        self.bucket_name = (bucket_name or _GCS_BUCKET).strip()

        base = (base_path or _GCS_BASE_PATH).strip("/")
        if base:
            self.base_prefix = f"{base}/cursors"
        else:
            self.base_prefix = "cursors"

    def _get_blob(self, model: str) -> storage.Blob:
        safe_name = _safe_model_name(model)
        object_name = f"{self.base_prefix}/{safe_name}.json".lstrip("/")
        client = _get_storage_client()
        bucket = client.bucket(self.bucket_name)
        return bucket.blob(object_name)

    def load(self, model: str) -> Optional[CursorData]:
        """Carrega o cursor salvo para o model."""
        blob = self._get_blob(model)
        try:
            if not blob.exists():
                return None

            raw = blob.download_as_text(encoding="utf-8")
            payload = json.loads(raw)
            last_value = payload.get("last_value")
            if not last_value:
                return None

            return CursorData.from_dict(payload)

        except NotFound:
            return None
        except Exception as exc:
            logger.warning(f"⚠️ Falha ao carregar cursor de {model}: {exc}")
            return None

    def save(
        self,
        model: str,
        *,
        cursor_field: str,
        last_value: str,
        last_id: Optional[int],
    ) -> None:
        """Persiste o cursor atualizado para o model."""
        blob = self._get_blob(model)

        payload = CursorData(
            cursor_field=cursor_field,
            last_value=last_value,
            last_id=last_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
        ).to_dict()

        try:
            blob.upload_from_string(
                json.dumps(payload, ensure_ascii=False),
                content_type="application/json",
            )
            logger.info(
                f"🧭 Cursor atualizado para {model} "
                f"({cursor_field}={last_value}, id={last_id})"
            )
        except Exception as exc:
            logger.error(f"❌ Erro ao salvar cursor de {model}: {exc}")
            raise
