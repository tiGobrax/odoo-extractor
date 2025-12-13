import time
from loguru import logger

from src.odoo_extractor.connection import OdooConnection
from src.odoo_extractor.errors import (
    ModelExtractionError,
    is_temporary_error,
    is_permanent_schema_error,
    summarize_error,
)


class OdooClient:
    """
    Client de alto nível para leitura de dados do Odoo via XML-RPC.

    Responsabilidades:
    - Orquestrar chamadas search_read
    - Controlar retry e classificação de erro
    - Expor APIs simples para o restante do sistema
    """

    def __init__(self):
        self.conn = OdooConnection()
        self._refresh_connection_refs()

    def _refresh_connection_refs(self) -> None:
        """
        Reaponta referências locais para os proxies/atributos da conexão.
        Importante após reconexão (retry).
        """
        self.db = self.conn.db
        self.uid = self.conn.uid
        self.password = self.conn.password
        self.models = self.conn.models

    def get_all_fields(self, model: str) -> list[str]:
        """Retorna todos os campos disponíveis para um model."""
        try:
            metadata = self.models.execute_kw(
                self.db,
                self.uid,
                self.password,
                model,
                "fields_get",
                [],
                {"attributes": ["string"]},
            )
            return list(metadata.keys())
        except Exception as e:
            logger.error(f"❌ Erro ao listar campos de {model}: {e}")
            raise

    def _search_read_batches(
        self,
        model: str,
        domain: list,
        fields: list,
        *,
        batch_size: int = 5000,
        limit: int | None = None,
    ):
        """
        Generator que executa search_read em lotes, com retry e classificação de erro.
        """
        offset = 0
        fetched = 0

        while True:
            current_limit = batch_size
            if limit is not None:
                remaining = max(limit - fetched, 0)
                if remaining <= 0:
                    break
                current_limit = min(batch_size, remaining)

            kwargs = {
                "fields": fields,
                "limit": current_limit,
                "offset": offset,
            }

            for attempt in range(3):
                try:
                    batch = self.models.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        model,
                        "search_read",
                        [domain],
                        kwargs,
                    )
                    break

                except Exception as e:
                    reason = summarize_error(model, e)

                    # Erro permanente (schema/permissão/etc.)
                    if is_permanent_schema_error(e):
                        logger.warning(f"⚙️ Modelo {model} ignorado: {reason}")
                        raise ModelExtractionError(model, reason, category="schema")

                    # Erro temporário (rede/timeout/etc.) -> retry + reconnect
                    if is_temporary_error(e):
                        logger.warning(
                            f"⏳ Tentativa {attempt + 1}/3 falhou em {model} "
                            f"(erro temporário): {reason}"
                        )
                        time.sleep(5 * (attempt + 1))
                        self.conn._connect()
                        self._refresh_connection_refs()
                        continue

                    # Erro inesperado
                    logger.error(f"❌ Erro inesperado em {model}: {reason}")
                    raise ModelExtractionError(model, reason, category="unexpected")

            else:
                reason = "Falha após 3 tentativas (erros temporários consecutivos)."
                logger.error(f"🚨 {reason} em {model}")
                raise ModelExtractionError(model, reason, category="temporary")

            if not batch:
                break

            fetched += len(batch)
            offset += len(batch)

            logger.info(f"📦 {len(batch)} registros carregados (total: {fetched})")
            yield batch

            if limit is not None and fetched >= limit:
                break

    def iter_batches(
        self,
        model: str,
        domain: list,
        fields: list,
        *,
        batch_size: int = 5000,
        limit: int | None = None,
    ):
        """Expõe os lotes de registros como iterador."""
        yield from self._search_read_batches(
            model=model,
            domain=domain,
            fields=fields,
            batch_size=batch_size,
            limit=limit,
        )

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list,
        *,
        batch_size: int = 5000,
        limit: int | None = None,
    ) -> list[dict]:
        """Executa search_read retornando todos os registros em memória."""
        records: list[dict] = []

        for batch in self._search_read_batches(
            model=model,
            domain=domain,
            fields=fields,
            batch_size=batch_size,
            limit=limit,
        ):
            records.extend(batch)

        logger.success(f"✅ Extração concluída: {len(records)} registros de {model}")
        return records
