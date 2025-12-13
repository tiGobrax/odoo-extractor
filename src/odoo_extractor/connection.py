import os
import xmlrpc.client
from loguru import logger
from xmlrpc.client import Transport


class TimeoutTransport(Transport):
    """
    Transporte XML-RPC com timeout configurável.
    """

    def __init__(self, timeout: int = 300, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn


class OdooConnection:
    """
    Responsável apenas por:
    - Ler variáveis de ambiente
    - Criar conexões XML-RPC
    - Autenticar no Odoo
    """

    def __init__(self):
        base_url = os.getenv("ODOO_URL", "https://gobrax.odoo.com")
        self.db = os.getenv("ODOO_DB", "gobrax-sh-main-22440471")
        self.username = os.getenv("ODOO_USERNAME", "odoo@gobrax.com")
        self.password = os.getenv("ODOO_PASSWORD")

        if not self.password:
            raise ValueError("Variável de ambiente ODOO_PASSWORD não configurada.")
        if not self.db:
            raise ValueError("Variável de ambiente ODOO_DB não configurada.")
        if not self.username:
            raise ValueError("Variável de ambiente ODOO_USERNAME não configurada.")

        if not base_url.startswith("https://"):
            base_url = f"https://{base_url.lstrip('http://')}"
        self.url = base_url.rstrip("/")

        self._connect()

    def _connect(self):
        """
        Inicializa proxies XML-RPC e autentica.
        """
        transport = TimeoutTransport(timeout=120)

        self.common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common",
            allow_none=True,
            transport=transport,
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
            transport=transport,
        )

        try:
            self.uid = self.common.authenticate(
                self.db,
                self.username,
                self.password,
                {},
            )
            if not self.uid:
                raise RuntimeError(
                    "Falha na autenticação com o Odoo. Verifique usuário, banco e API key."
                )

            logger.info(
                f"🔗 Conectado ao Odoo | UID={self.uid} | DB={self.db} | URL={self.url}"
            )

        except xmlrpc.client.ProtocolError as e:
            logger.error(
                f"🧱 Erro de protocolo na autenticação ({e.errcode}): {e.errmsg}"
            )
            raise
        except Exception as e:
            logger.error(f"🚫 Erro na autenticação com o Odoo: {e}")
            raise
