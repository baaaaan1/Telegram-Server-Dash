"""Tests for configuration models."""

import pytest
from pydantic import ValidationError

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

    def test_empty_optional_log_chat_id_is_ignored(self, monkeypatch):
        """An empty systemd environment value uses the optional default."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("LOG_CHAT_ID", "")
        settings = BotSettings(_env_file=None)
        assert settings.log_chat_id is None


class TestUserIdsParsing:
    """Regression tests for whitelist env parsing (setup.sh writes plain IDs)."""

    def test_single_admin_id_from_env(self, monkeypatch):
        """A single numeric ID must become a one-element list."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "123456789")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == [123456789]

    def test_comma_separated_admin_ids_from_env(self, monkeypatch):
        """Comma-separated IDs are parsed without JSON decoding errors."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "1, 2,3")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == [1, 2, 3]

    def test_json_like_ids_are_tolerated(self, monkeypatch):
        """Legacy JSON-style values keep working."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "[1, 2]")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == [1, 2]

    def test_empty_whitelist_stays_empty(self, monkeypatch):
        """An empty env value yields an empty whitelist, not a crash."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == []


class TestUsernameBindings:
    """Tests for ID:username whitelist bindings."""

    def test_id_username_binding_from_env(self, monkeypatch):
        """An ID:username entry binds the account to that username."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "123456789:MyName,987")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == [123456789, 987]
        assert settings.admin_usernames == {123456789: "myname"}
        assert settings.username_bindings == {123456789: "myname"}

    def test_at_prefix_and_role_merge(self, monkeypatch):
        """A leading @ is accepted and bindings from all roles are merged."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "1:alpha")
        monkeypatch.setenv("OPERATOR_USER_IDS", "2:@bravo")
        monkeypatch.setenv("VIEWER_USER_IDS", "3")
        settings = BotSettings(_env_file=None)
        assert settings.admin_user_ids == [1]
        assert settings.operator_user_ids == [2]
        assert settings.username_bindings == {1: "alpha", 2: "bravo"}

    def test_invalid_username_binding_is_rejected(self, monkeypatch):
        """Usernames must satisfy Telegram's 5-32 character rule."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "1:no")
        with pytest.raises(ValidationError):
            BotSettings(_env_file=None)

    def test_entry_without_id_is_rejected(self, monkeypatch):
        """A username without a numeric ID cannot grant access."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("ADMIN_USER_IDS", "alice")
        with pytest.raises(ValidationError):
            BotSettings(_env_file=None)

    def test_strict_username_flag_parses(self, monkeypatch):
        """STRICT_USERNAME_MATCH accepts common boolean spellings."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("STRICT_USERNAME_MATCH", "true")
        assert BotSettings(_env_file=None).strict_username_match is True
        monkeypatch.setenv("STRICT_USERNAME_MATCH", "0")
        assert BotSettings(_env_file=None).strict_username_match is False


class TestAuthSettings:
    """Tests for RBAC, PIN, and throttling settings."""

    def test_operator_and_viewer_ids_parse(self, monkeypatch):
        """Operator and viewer whitelists accept comma-separated values."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("OPERATOR_USER_IDS", "1, 2")
        monkeypatch.setenv("VIEWER_USER_IDS", "3")
        settings = BotSettings(_env_file=None)
        assert settings.operator_user_ids == [1, 2]
        assert settings.viewer_user_ids == [3]

    def test_auth_defaults(self, monkeypatch):
        """Safe defaults are applied when auth settings are absent."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        settings = BotSettings(_env_file=None)
        assert settings.pin is None
        assert settings.rate_limit_per_minute == 30
        assert settings.auth_max_attempts == 5
        assert settings.auth_lockout_seconds == 900
        assert settings.pin_ttl_seconds == 300

    def test_valid_pin_is_accepted(self, monkeypatch):
        """A numeric 4-8 digit PIN is accepted."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("TSD_PIN", "482913")
        settings = BotSettings(_env_file=None)
        assert settings.pin == "482913"

    def test_invalid_pin_is_rejected(self, monkeypatch):
        """Non-numeric or too short PIN values fail fast at startup."""
        monkeypatch.setenv("BOT_TOKEN", "test:token")
        monkeypatch.setenv("TSD_PIN", "12ab")
        with pytest.raises(ValidationError):
            BotSettings(_env_file=None)


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
