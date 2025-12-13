import csv
import io
from typing import List, Optional

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


class ModelsRegistry:
    """
    Responsável apenas por persistir e recuperar a lista de models.
    NÃO sabe nada sobre HTTP, Odoo ou extração.
    """

    def __init__(
        self,
        *,
        bucket_name: Optional[str] = None,
        base_path: Optional[str] = None,
        file_name: str = "models_list.csv",
    ):
        self.bucket_name = (bucket_name or _GCS_BUCKET).strip()

        base = (base_path or _GCS_BASE_PATH).strip("/")
        self.object_name = f"{base}/{file_name}".lstrip("/")

    def _get_blob(self) -> storage.Blob:
        client = _get_storage_client()
        bucket = client.bucket(self.bucket_name)
        return bucket.blob(self.object_name)

    def load(self) -> List[str]:
        """Carrega a lista de models persistida no GCS."""
        blob = self._get_blob()
        try:
            if not blob.exists():
                logger.warning("📂 Lista de models ainda não existe no GCS")
                return []

            csv_content = blob.download_as_text(encoding="utf-8")
            buffer = io.StringIO(csv_content)
            models = [
                row[0].strip()
                for row in csv.reader(buffer)
                if row and row[0].strip()
            ]

            logger.info(f"📖 {len(models)} models carregados do registry (GCS)")
            return models

        except NotFound:
            logger.warning("📂 Lista de models não encontrada no GCS")
            return []

        except Exception as e:
            logger.error(f"❌ Erro ao carregar models registry no GCS: {e}")
            return []

    def save(self, models: List[str]) -> None:
        """Persiste a lista de models no GCS."""
        unique_models = sorted(set(models))
        blob = self._get_blob()

        try:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for model in unique_models:
                writer.writerow([model])

            blob.upload_from_string(buffer.getvalue(), content_type="text/csv")

            logger.success(
                f"💾 Registry atualizado no GCS com {len(unique_models)} models"
            )

        except Exception as e:
            logger.error(f"❌ Erro ao salvar models registry no GCS: {e}")
            raise
