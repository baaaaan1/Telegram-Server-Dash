"""Server connectivity probes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.ssh import CommandResult


@dataclass(frozen=True, slots=True)
class ServerMetrics:
    """Snapshot of read-only server health metrics."""

    online: bool
    hostname: str = "unknown"
    uptime: str = "unknown"
    load: str = "unknown"
    memory: str = "unknown"
    disk: str = "unknown"
    latency_ms: float = -1


async def connectivity_test(connection, command: str = "echo ok") -> bool:
    """Simple connectivity test to server."""
    result = await connection.run(command)
    return result.exit_code == 0


async def latency_test(connection, host: str | None = None) -> float:
    """Measure latency to server using ping (local only)."""
    result = await connection.run("ping -c 1 -W 1 127.0.0.1 2>/dev/null || echo 1")
    if result.exit_code != 0:
        return -1

    import re

    match = re.search(r"time=(\d+\.?\d*)", result.stdout)
    if match:
        return float(match.group(1))

    return -1


async def check_uptime(connection) -> CommandResult:
    """Get system uptime from server."""
    return await connection.run(
        "uptime -p 2>/dev/null || cat /proc/uptime | awk '{print $1\" seconds\"}' || echo 'unknown'"
    )


async def check_load_avg(connection) -> str:
    """Get load average."""
    result = await connection.run('cat /proc/loadavg | awk \'{print $1" " $2" " $3}\'')
    if result.exit_code == 0:
        return result.stdout.strip()
    return "unknown"


async def check_hostname(connection) -> str:
    """Get the server hostname."""
    result = await connection.run("hostname 2>/dev/null || echo unknown")
    return result.stdout.strip() if result.exit_code == 0 else "unknown"


async def check_memory(connection) -> str:
    """Get used and total memory in MiB."""
    result = await connection.run(
        "free -m | awk 'NR==2 {printf \"%s/%s MiB (%.0f%%)\", $3, $2, ($3/$2)*100}'"
    )
    return result.stdout.strip() if result.exit_code == 0 and result.stdout.strip() else "unknown"


async def check_disk(connection) -> str:
    """Get root filesystem usage."""
    result = await connection.run("df -hP / | awk 'NR==2 {printf \"%s/%s (%s)\", $3, $2, $5}'")
    return result.stdout.strip() if result.exit_code == 0 and result.stdout.strip() else "unknown"


async def collect_server_metrics(connection) -> ServerMetrics:
    """Collect a single server status snapshot."""
    if not await connectivity_test(connection):
        return ServerMetrics(online=False)

    latency, uptime_result, load, hostname, memory, disk = await asyncio.gather(
        latency_test(connection),
        check_uptime(connection),
        check_load_avg(connection),
        check_hostname(connection),
        check_memory(connection),
        check_disk(connection),
    )
    uptime = (
        uptime_result.stdout.strip()
        if uptime_result.exit_code == 0 and uptime_result.stdout.strip()
        else "unknown"
    )
    return ServerMetrics(
        online=True,
        hostname=hostname,
        uptime=uptime,
        load=load,
        memory=memory,
        disk=disk,
        latency_ms=latency,
    )
