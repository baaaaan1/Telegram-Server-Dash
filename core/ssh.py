"""SSH connection management using asyncssh."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncssh

if TYPE_CHECKING:
    from config.servers import ServerConfig


@dataclass(slots=True)
class CommandResult:
    """Result from a remote command execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration: float


class SSHConnection:
    """Async SSH connection wrapper with context manager support."""

    def __init__(self, server: ServerConfig):
        self._server = server
        self._conn: asyncssh.SSHClientConnection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish SSH connection to server."""
        async with self._lock:
            if self._conn is not None:
                return

            conn_kwargs: dict = {
                "host": self._server.host,
                "port": self._server.port,
                "user": self._server.user,
                "known_hosts": None,
                "client_host_keys": [],
                "connect_timeout": self._server.connect_timeout,
            }

            if self._server.auth == "key" and self._server.key_path:
                key_path = self._server.key_path.replace("~", "~")
                conn_kwargs["client_keys"] = [key_path]
            elif self._server.auth == "password" and self._server.get_resolved_password():
                conn_kwargs["password"] = self._server.get_resolved_password()

            self._conn = await asyncssh.connect(**conn_kwargs)

    async def run(self, command: str, timeout: float | None = None) -> CommandResult:
        """Execute a command on the remote server."""
        timeout = timeout or self._server.command_timeout
        import time

        start = time.monotonic()
        try:
            if self._conn is None:
                await self.connect()
            assert self._conn is not None
            result = await asyncio.wait_for(self._conn.run(command, check=False), timeout=timeout)
            duration = time.monotonic() - start
            return CommandResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_status or 0,
                duration=duration,
            )
        except TimeoutError:
            duration = time.monotonic() - start
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=124,
                duration=duration,
            )
        except Exception as e:
            duration = time.monotonic() - start
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                duration=duration,
            )

    async def close(self) -> None:
        """Close the SSH connection."""
        async with self._lock:
            if self._conn is not None:
                self._conn.close()
                await self._conn.wait_closed()
                self._conn = None

    async def __aenter__(self) -> SSHConnection:
        await self.connect()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()


class LocalConnection:
    """Local subprocess connection for testing."""

    def __init__(self, server: ServerConfig):
        self._server = server

    async def run(self, command: str, timeout: float | None = None) -> CommandResult:
        """Execute a command locally."""
        import time

        timeout = timeout or 30.0
        start = time.monotonic()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            duration = time.monotonic() - start
            return CommandResult(
                stdout=stdout.decode(),
                stderr=stderr.decode(),
                exit_code=proc.returncode or 0,
                duration=duration,
            )
        except TimeoutError:
            duration = time.monotonic() - start
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=124,
                duration=duration,
            )
        except Exception as e:
            duration = time.monotonic() - start
            return CommandResult(stdout="", stderr=str(e), exit_code=1, duration=duration)

    async def close(self) -> None:
        """Match the SSH connection lifecycle interface."""


def create_ssh_pool(servers: dict[str, ServerConfig]) -> dict[str, SSHConnection | LocalConnection]:
    """Create connection pool for all configured servers."""
    from config.servers import Transport

    pool: dict[str, SSHConnection | LocalConnection] = {}
    for name, server in servers.items():
        if server.transport == Transport.LOCAL:
            pool[name] = LocalConnection(server)
        else:
            pool[name] = SSHConnection(server)
    return pool
