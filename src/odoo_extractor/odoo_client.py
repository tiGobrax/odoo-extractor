import os
import time
import socket
import xmlrpc.client
from loguru import logger
from xmlrpc.client import Transport


class OdooClient:
    def __init__(self):
        # --- Variáveis fixas (hardcoded) ---
        base_url = "https://gobrax.odoo.com"
        self.db = "gobrax-sh-main-22440471"
        self.username = "odoo@gobrax.com"

        # --- Apenas o password vem do ambiente ---
        self.password = os.getenv("ODOO_PASSWORD")
        if not self.password:
            raise ValueError("Variável de ambiente ODOO_PASSWORD não configurada.")

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
        return any(
            msg in str(err)
            for msg in [
                "Invalid field",
                "Unknown field",
                "Unknown model",
                "does not exist",
                "Permission denied",
                "dictionary key must be string",
                "psycopg2.errors.SyntaxError",  # <--- adiciona este
                "FROM (0) AS", 
            ]
        )

    def search_read(self, model: str, domain: list, fields: list, batch_size: int = 5000, limit: int = None):
        """Executa search_read com paginação automática, retry inteligente e categorização de erros."""
        try:
            all_records = []
            offset = 0

            while True:
                kwargs = {"fields": fields, "limit": batch_size, "offset": offset}
                if limit and offset + batch_size > limit:
                    kwargs["limit"] = max(0, limit - offset)

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
                    except Exception as e:
                        # Falha de schema (permanente)
                        if self._is_permanent_schema_error(e):
                            logger.warning(f"⚙️ Modelo {model} ignorado (erro de schema: {e}).")
                            return []

                        # Falha temporária (timeout, rede, etc.)
                        if self._is_temporary_error(e):
                            logger.warning(f"⏳ Tentativa {attempt+1}/3 falhou em {model} (erro temporário): {e}")
                            time.sleep(5 * (attempt + 1))
                            self._init_connections()
                            continue

                        # Falha desconhecida — considera permanente
                        logger.error(f"❌ Erro inesperado em {model}: {e}")
                        return []
                else:
                    logger.error(f"🚨 Falha após 3 tentativas em {model}. Pulando este modelo.")
                    return all_records

                if not batch:
                    break

                all_records.extend(batch)
                offset += batch_size
                logger.info(f"📦 {len(batch)} registros carregados (total: {len(all_records)})")

                if limit and len(all_records) >= limit:
                    all_records = all_records[:limit]
                    break

            logger.success(f"✅ Extração concluída: {len(all_records)} registros de {model}")
            return all_records

        except Exception as e:
            logger.error(f"💥 Erro fatal ao buscar dados de {model}: {e}")
            return []
