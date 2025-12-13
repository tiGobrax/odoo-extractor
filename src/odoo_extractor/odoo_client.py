import os
import time
import socket
import xmlrpc.client
from loguru import logger
from xmlrpc.client import Transport


class ModelExtractionError(Exception):
    """Erro controlado indicando que um model não pode ser processado."""

    def __init__(self, model: str, reason: str, *, category: str = "unknown"):
        super().__init__(reason)
        self.model = model
        self.reason = reason
        self.category = category


class OdooClient:
    def __init__(self):
        # --- Variáveis de ambiente ---
        base_url = os.getenv("ODOO_URL", "https://gobrax.odoo.com")
        self.db = os.getenv("ODOO_DB", "gobrax-sh-main-22440471")
        self.username = os.getenv("ODOO_USERNAME", "odoo@gobrax.com")
        self.password = os.getenv("ODOO_PASSWORD")

        # --- Validação de variáveis obrigatórias ---
        if not self.password:
            raise ValueError("Variável de ambiente ODOO_PASSWORD não configurada.")
        if not self.db:
            raise ValueError("Variável de ambiente ODOO_DB não configurada.")
        if not self.username:
            raise ValueError("Variável de ambiente ODOO_USERNAME não configurada.")

        # --- Força HTTPS e limpa barras extras ---
        if not base_url.startswith("https://"):
            base_url = f"https://{base_url.lstrip('http://')}"
        self.url = base_url.rstrip("/")

        # --- Classe de transporte com timeout ---
        class TimeoutTransport(Transport):
            def __init__(self, timeout=300, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.timeout = timeout

            def make_connection(self, host):
                conn = super().make_connection(host)
                conn.timeout = self.timeout
                return conn

        self._TransportClass = TimeoutTransport  # salva referência

        # --- Inicializa endpoints XML-RPC ---
        self._init_connections()

    def _init_connections(self):
        """Inicializa ou reinicializa conexões XML-RPC"""
        self.common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common",
            allow_none=True,
            transport=self._TransportClass(timeout=120)
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
            transport=self._TransportClass(timeout=120)
        )

        # --- Autenticação ---
        try:
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            if not self.uid:
                raise Exception("Falha na autenticação com o Odoo. Verifique usuário, banco e API key.")
            logger.info(f"🔗 Conectado ao Odoo: UID {self.uid} | Banco {self.db} | URL {self.url}")
        except xmlrpc.client.ProtocolError as e:
            logger.error(f"🧱 Erro de protocolo na autenticação ({e.errcode}): {e.errmsg}")
            raise
        except Exception as e:
            logger.error(f"🚫 Erro na autenticação com o Odoo: {e}")
            raise

    def _is_temporary_error(self, err: Exception) -> bool:
        """Determina se um erro é temporário (ex: timeout, rede, servidor)"""
        transient = (
            isinstance(err, (socket.timeout, ConnectionResetError, xmlrpc.client.ProtocolError))
            or "timeout" in str(err).lower()
            or "temporarily unavailable" in str(err).lower()
        )
        return transient

    def _is_permanent_schema_error(self, err: Exception) -> bool:
        """Identifica erros permanentes relacionados a schema ou payload inválido"""
        message = str(err)
        return any(
            token.lower() in message.lower()
            for token in [
                "invalid field",
                "unknown field",
                "unknown model",
                "does not exist",
                "permission denied",
                "dictionary key must be string",
                "psycopg2.errors.syntaxerror",
                "from (0) as",
                "notimplementederror",
                "operator does not exist",
            ]
        )

    def _summarize_error(self, model: str, err: Exception) -> str:
        """Gera mensagem curta e amigável para logs/retorno"""
        if isinstance(err, xmlrpc.client.Fault):
            message = err.faultString or str(err)
        else:
            message = str(err)

        normalized = message.lower()
        if "notimplementederror" in normalized:
            return f"O model {model} não implementa busca (NotImplementedError)."
        if "operator does not exist" in normalized:
            return "Erro de schema no Postgres: operator inexistente para o tipo solicitado."
        if "dictionary key must be string" in normalized:
            return "Estrutura retornada pelo Odoo possui chaves inválidas."
        if "unknown field" in normalized:
            return "Campo solicitado não existe no model."
        if "permission denied" in normalized:
            return "Usuário/API Key sem permissão para ler este model."

        lines = [line.strip().strip("'") for line in message.splitlines() if line.strip()]
        if lines:
            return lines[-1]
        return message or "Erro desconhecido"

    def get_all_fields(self, model: str):
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
        batch_size: int = 5000,
        limit: int = None,
    ):
        """Generator que executa search_read em lotes, respeitando limite e repetindo em caso de falha."""
        try:
            offset = 0
            fetched = 0

            while True:
                current_limit = batch_size
                if limit is not None:
                    remaining = max(limit - fetched, 0)
                    if remaining <= 0:
                        break
                    current_limit = min(batch_size, remaining)

                kwargs = {"fields": fields, "limit": current_limit, "offset": offset}

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
                        break  # sucesso
                    except ModelExtractionError:
                        raise
                    except Exception as e:
                        reason = self._summarize_error(model, e)

                        # Falha de schema (permanente)
                        if self._is_permanent_schema_error(e):
                            logger.warning(f"⚙️ Modelo {model} ignorado: {reason}")
                            raise ModelExtractionError(model, reason, category="schema")

                        # Falha temporária (timeout, rede, etc.)
                        if self._is_temporary_error(e):
                            logger.warning(
                                f"⏳ Tentativa {attempt+1}/3 falhou em {model} (erro temporário): {reason}"
                            )
                            time.sleep(5 * (attempt + 1))
                            self._init_connections()
                            continue

                        # Falha desconhecida — considera permanente
                        logger.error(f"❌ Erro inesperado em {model}: {reason}")
                        raise ModelExtractionError(model, reason, category="unexpected")
                else:
                    reason = "Falha após 3 tentativas (erros temporários consecutivos)."
                    logger.error(f"🚨 {reason} em {model}.")
                    raise ModelExtractionError(model, reason, category="temporary")

                if not batch:
                    break

                fetched += len(batch)
                offset += len(batch)
                logger.info(f"📦 {len(batch)} registros carregados (total: {fetched})")

                yield batch

                if limit is not None and fetched >= limit:
                    break

        except ModelExtractionError:
            raise
        except Exception as e:
            reason = self._summarize_error(model, e)
            logger.error(f"💥 Erro fatal ao buscar dados de {model}: {reason}")
            raise ModelExtractionError(model, reason, category="fatal") from e

    def iter_batches(self, model: str, domain: list, fields: list, batch_size: int = 5000, limit: int = None):
        """Expõe os lotes de registros do search_read como um iterador."""
        yield from self._search_read_batches(model, domain, fields, batch_size, limit)

    def search_read(self, model: str, domain: list, fields: list, batch_size: int = 5000, limit: int = None):
        """Executa search_read retornando todos os registros em memória (compatibilidade)."""
        all_records = []
        for batch in self._search_read_batches(model, domain, fields, batch_size, limit):
            all_records.extend(batch)

        logger.success(f"✅ Extração concluída: {len(all_records)} registros de {model}")
        return all_records
