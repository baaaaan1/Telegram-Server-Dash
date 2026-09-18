"""Server registry configuration from YAML file."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class Transport(StrEnum):
    """Transport method for server communication."""

    LOCAL = "local"
    SSH = "ssh"


class AuthMethod(StrEnum):
    """Authentication method for SSH connections."""

    KEY = "key"
    PASSWORD = "password"


class ServerConfig(BaseModel):
    """Configuration for a single server."""

    model_config = ConfigDict(extra="forbid")

    name: str
    group: str = "default"
    description: str = ""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 22
    user: str = "root"
    transport: Transport = Transport.SSH
    auth: AuthMethod = AuthMethod.KEY
    key_path: str | None = None
    password_env: str | None = None
    connect_timeout: float = 10.0
    command_timeout: float = 30.0
    monitor_interval: int = 30

    @model_validator(mode="after")
    def _validate_ssh_config(self) -> ServerConfig:
        if self.transport == Transport.SSH:
            if self.auth == AuthMethod.PASSWORD and not self.password_env:
                msg = f"Server '{self.name}': password auth requires password_env"
                raise ValueError(msg)
            if self.auth == AuthMethod.KEY and not self.key_path:
                msg = f"Server '{self.name}': key auth requires key_path"
                raise ValueError(msg)
        if self.transport == Transport.LOCAL:
            self.host = "127.0.0.1"
            self.port = 22
        return self

    def get_resolved_password(self) -> str | None:
        """Resolve password from environment variable."""
        if self.password_env is None:
            return None
        return os.environ.get(self.password_env)


class ServerRegistry(BaseModel):
    """Registry of all configured servers."""

    servers: dict[str, ServerConfig] = {}

    @model_validator(mode="after")
    def _validate_unique_names(self) -> ServerRegistry:
        names = list(self.servers.keys())
        if len(names) != len(set(names)):
            raise ValueError("Duplicate server names in config")
        return self

    def get_enabled_servers(self) -> dict[str, ServerConfig]:
        """Return only enabled servers."""
        return {k: v for k, v in self.servers.items() if v.enabled}

    def get_by_name(self, name: str) -> ServerConfig | None:
        """Get server by name."""
        return self.servers.get(name)

    def get_by_group(self, group: str) -> list[ServerConfig]:
        """Get all servers in a group."""
        return [s for s in self.servers.values() if s.group == group and s.enabled]


def load_server_registry(config_path: Path | str) -> ServerRegistry:
    """Load server registry from YAML config file."""
    path = Path(config_path)
    if not path.exists():
        return ServerRegistry(servers={})

    content = yaml.safe_load(path.read_text())
    if not content:
        return ServerRegistry(servers={})

    raw_servers = content.get("servers", [])
    servers_dict = {}
    for raw in raw_servers:
        name = raw.get("name")
        if name:
            servers_dict[name] = ServerConfig(**raw)

    return ServerRegistry(servers=servers_dict)
