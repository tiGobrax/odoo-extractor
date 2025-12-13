import socket
import xmlrpc.client


class ModelExtractionError(Exception):
    """
    Erro controlado indicando que um model não pode ser processado.
    """

    def __init__(self, model: str, reason: str, *, category: str = "unknown"):
        super().__init__(reason)
        self.model = model
        self.reason = reason
        self.category = category


def is_temporary_error(err: Exception) -> bool:
    """
    Determina se um erro é temporário (rede, timeout, indisponibilidade).
    """
    return (
        isinstance(err, (socket.timeout, ConnectionResetError, xmlrpc.client.ProtocolError))
        or "timeout" in str(err).lower()
        or "temporarily unavailable" in str(err).lower()
    )


def is_permanent_schema_error(err: Exception) -> bool:
    """
    Identifica erros permanentes relacionados a schema ou payload inválido.
    """
    message = str(err).lower()
    return any(
        token in message
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


def summarize_error(model: str, err: Exception) -> str:
    """
    Gera mensagem curta e amigável para logs/retorno.
    """
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
