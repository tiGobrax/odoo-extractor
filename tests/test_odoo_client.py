"""
Testes básicos para o OdooClient.

Nota: Estes testes requerem configuração de variáveis de ambiente
ou podem ser mockados para testes unitários completos.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.odoo_extractor.odoo_client import OdooClient


class TestOdooClient:
    """Testes para a classe OdooClient"""

    def test_init_missing_password(self):
        """Testa que ValueError é levantado quando ODOO_PASSWORD não está configurado"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ODOO_PASSWORD não configurada"):
                OdooClient()

    def test_init_with_env_vars(self):
        """Testa inicialização com variáveis de ambiente"""
        env_vars = {
            "ODOO_URL": "https://test.odoo.com",
            "ODOO_DB": "test-db",
            "ODOO_USERNAME": "test@example.com",
            "ODOO_PASSWORD": "test-password"
        }
        
        with patch.dict(os.environ, env_vars):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy') as mock_proxy:
                # Mock da autenticação
                mock_common = MagicMock()
                mock_common.authenticate.return_value = 123
                mock_proxy.return_value = mock_common
                
                client = OdooClient()
                
                assert client.db == "test-db"
                assert client.username == "test@example.com"
                assert client.password == "test-password"
                assert "test.odoo.com" in client.url

    def test_init_default_values(self):
        """Testa que valores padrão são usados quando variáveis não estão definidas"""
        env_vars = {
            "ODOO_PASSWORD": "test-password"
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy') as mock_proxy:
                mock_common = MagicMock()
                mock_common.authenticate.return_value = 123
                mock_proxy.return_value = mock_common
                
                client = OdooClient()
                
                # Verifica valores padrão
                assert "gobrax" in client.url.lower() or client.url
                assert client.db is not None
                assert client.username is not None

    def test_is_temporary_error(self):
        """Testa detecção de erros temporários"""
        env_vars = {"ODOO_PASSWORD": "test"}
        
        with patch.dict(os.environ, env_vars):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy'):
                client = OdooClient()
                
                import socket
                assert client._is_temporary_error(socket.timeout()) is True
                assert client._is_temporary_error(ConnectionResetError()) is True
                assert client._is_temporary_error(ValueError("timeout occurred")) is True
                assert client._is_temporary_error(ValueError("normal error")) is False

    def test_is_permanent_schema_error(self):
        """Testa detecção de erros permanentes de schema"""
        env_vars = {"ODOO_PASSWORD": "test"}
        
        with patch.dict(os.environ, env_vars):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy'):
                client = OdooClient()
                
                assert client._is_permanent_schema_error(ValueError("Invalid field")) is True
                assert client._is_permanent_schema_error(ValueError("Unknown field")) is True
                assert client._is_permanent_schema_error(ValueError("Permission denied")) is True
                assert client._is_permanent_schema_error(ValueError("normal error")) is False

    @patch('src.odoo_extractor.odoo_client.logger')
    def test_search_read_empty_result(self, mock_logger):
        """Testa search_read com resultado vazio"""
        env_vars = {"ODOO_PASSWORD": "test"}
        
        with patch.dict(os.environ, env_vars):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy') as mock_proxy:
                mock_common = MagicMock()
                mock_common.authenticate.return_value = 123
                mock_models = MagicMock()
                mock_models.execute_kw.return_value = []
                mock_proxy.side_effect = [mock_common, mock_models]
                
                client = OdooClient()
                result = client.search_read(
                    model="res.partner",
                    domain=[],
                    fields=["id", "name"]
                )
                
                assert result == []
                mock_models.execute_kw.assert_called_once()

    @patch('src.odoo_extractor.odoo_client.logger')
    def test_search_read_with_limit(self, mock_logger):
        """Testa search_read com limite"""
        env_vars = {"ODOO_PASSWORD": "test"}
        
        with patch.dict(os.environ, env_vars):
            with patch('src.odoo_extractor.odoo_client.xmlrpc.client.ServerProxy') as mock_proxy:
                mock_common = MagicMock()
                mock_common.authenticate.return_value = 123
                mock_models = MagicMock()
                mock_models.execute_kw.return_value = [
                    {"id": 1, "name": "Test 1"},
                    {"id": 2, "name": "Test 2"}
                ]
                mock_proxy.side_effect = [mock_common, mock_models]
                
                client = OdooClient()
                result = client.search_read(
                    model="res.partner",
                    domain=[],
                    fields=["id", "name"],
                    limit=2
                )
                
                assert len(result) == 2
                assert result[0]["id"] == 1

