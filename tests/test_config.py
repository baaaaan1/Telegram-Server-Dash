"""Tests for configuration models."""

import pytest

from config.servers import AuthMethod, ServerConfig, ServerRegistry, Transport
from config.settings import BotSettings


class TestBotSettings:
    """Tests for BotSettings pydantic model."""

    def test_loads_with_token(self, monkeypatch):
        """Test that BotSettings loads with BOT_TOKEN."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        settings = BotSettings()
        assert settings.bot_token == "test:token"

    def test_default_environment(self, monkeypatch):
        """Test default environment value."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        settings = BotSettings()
        assert settings.environment == "dev"
        assert settings.log_chat_id is None


class TestServerConfig:
    """Tests for ServerConfig model."""

    def test_local_transport_defaults(self):
        """Test local transport configuration."""
        config = ServerConfig(name="test", transport=Transport.LOCAL)
        assert config.host == "127.0.0.1"
        assert config.port == 22

    def test_ssh_key_config(self):
        """Test valid SSH key config."""
        config = ServerConfig(
            name="ssh-test",
            transport=Transport.SSH,
            auth=AuthMethod.KEY,
            key_path="/path/to/key",
        )
        assert config.name == "ssh-test"

    def test_ssh_requires_key_path(self):
        """Test that SSH key auth requires key_path."""
        with pytest.raises(ValueError, match="key auth requires key_path"):
            ServerConfig(name="test", transport=Transport.SSH, auth=AuthMethod.KEY)

    def test_ssh_requires_password_env(self):
        """Test that SSH password auth requires password_env."""
        with pytest.raises(ValueError, match="password auth requires password_env"):
            ServerConfig(name="test", transport=Transport.SSH, auth=AuthMethod.PASSWORD)

    def test_ssh_password_config(self, monkeypatch):
        """Test valid SSH password config."""
        monkeypatch.setenv("TEST_PWD", "secret123")
        config = ServerConfig(
            name="test",
            transport=Transport.SSH,
            auth=AuthMethod.PASSWORD,
            password_env="TEST_PWD",
        )
        assert config.get_resolved_password() == "secret123"


class TestServerRegistry:
    """Tests for ServerRegistry model."""

    def test_empty_registry(self):
        """Test empty registry."""
        registry = ServerRegistry()
        assert registry.servers == {}
        assert registry.get_enabled_servers() == {}

    def test_enabled_servers_filter(self):
        """Test filtering enabled servers."""
        registry = ServerRegistry(
            servers={
                "s1": ServerConfig(name="s1", transport=Transport.LOCAL, enabled=True),
                "s2": ServerConfig(name="s2", transport=Transport.LOCAL, enabled=False),
            }
        )
        enabled = registry.get_enabled_servers()
        assert list(enabled.keys()) == ["s1"]

    def test_get_by_group(self):
        """Test getting servers by group."""
        registry = ServerRegistry(
            servers={
                "prod1": ServerConfig(name="prod1", group="production", transport=Transport.LOCAL),
                "prod2": ServerConfig(name="prod2", group="production", transport=Transport.LOCAL),
                "dev1": ServerConfig(
                    name="dev1", group="dev", enabled=False, transport=Transport.LOCAL
                ),
            }
        )
        production = registry.get_by_group("production")
        assert len(production) == 2
